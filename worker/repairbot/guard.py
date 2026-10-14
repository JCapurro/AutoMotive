"""PreToolUse guard for the repair bot's Claude session: an allowlist, default-deny.

    python -I guard.py --root <clone> --python <interpreter> --log <file> [--allow <path> ...]

Reads the hook JSON on stdin. Exit 0 lets the tool call through; exit 2 blocks it and
the reason on stderr goes back to the model. Claude Code does NOT treat any other exit
code as a block, so everything here ends in 0 or 2, and whatever the guard does not
understand (its own failures included) is a block.

Stdlib only and run isolated (-I): it cannot import the package it protects. It narrows
what the model can do; it is not a sandbox (a test the model writes still runs as the
user). The launcher's gates are the second line.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import fnmatch
import json
import ntpath
import os
from pathlib import Path
import posixpath
import re
import shlex
import sys

CANARY = 'REPAIRBOT_GUARD_ACTIVE'
TOOLS = ('Bash', 'Read', 'Edit', 'Write', 'Glob', 'Grep', 'StructuredOutput')
DEFAULT_ALLOWED = ('worker/collectors/', 'worker/tests/', 'worker/http_clients.py')
# File names never touched, wherever they sit under root; '.git' is only closed to writes.
PROTECTED = ('.env*', '.ssh', '.claude', '*credentials*', '*_state.json', '*chrome_profile*',
             'id_*', '*.pem', '*.key')
WRITE_PROTECTED = ('.git',)

_DRIVE = re.compile(r'[A-Za-z]:[\\/]')
_MSYS = re.compile(r'/(?:cygdrive/)?([A-Za-z])(?:/|$)')   # Git Bash spelling of a drive: /c/dir
_DEVICE = re.compile(r'(?i)(con|prn|aux|nul|com\d|lpt\d|conin\$|conout\$)(\..*)?')
_NUMBER = re.compile(r'[+-]?\d+(\.\d+)?[A-Za-z%]?')
_SOURCE = re.compile(r'[A-Za-z0-9_-]{1,64}')
_PAIR = re.compile(r'[A-Za-z_]\w*=')
_REV = r'[\w^~@-][\w./^~@-]*'
_RANGE = re.compile(rf'({_REV})?\.\.\.?({_REV})?')
_SED_ADDRESS = r'(?:\d+|\$|/(?:[^/\\\n]|\\.)*/[IM]*)'
_SED_COMMAND = rf'\s*(?:{_SED_ADDRESS}(?:\s*,\s*(?:{_SED_ADDRESS}|[+~]\d+))?)?\s*!?\s*[pq=]\s*'
_SED_SCRIPT = re.compile(rf'{_SED_COMMAND}(?:;{_SED_COMMAND})*;?')


class Block(Exception):
    """The reason a tool call is refused."""


class Scope:
    """What the session may read (root) and write (allowed paths under root).

    A Windows root also understands the Git Bash spelling of the same place (/c/dir).
    """

    def __init__(self, root, allowed=DEFAULT_ALLOWED):
        text = str(root)
        self.windows = bool(_DRIVE.match(text))
        self.flavour = ntpath if self.windows else posixpath
        if not self.windows and not text.startswith('/'):
            raise Block('root tiene que ser una ruta absoluta')
        self.root = self.flavour.normpath(text)
        self.allowed = tuple(self._key(entry.replace('\\', '/')) for entry in allowed)

    def _key(self, text: str) -> str:
        return text.lower() if self.windows else text

    def _relative(self, full: str, base: str) -> str | None:
        """`full` relative to `base` with '/' separators; None when it is not inside."""
        base = base.rstrip('\\/')
        if self._key(full) == self._key(base):
            return ''
        if not self._key(full).startswith(self._key(base) + self.flavour.sep):
            return None
        return full[len(base) + 1:].replace('\\', '/')

    def absolute(self, token: str, cwd: str | None = None) -> str:
        """Normalised absolute path of `token` seen from `cwd`; spellings it cannot place are refused."""
        if not token or any(ord(char) < 32 for char in token):
            raise Block('ruta vacía o con caracteres de control')
        if not self.windows:
            return posixpath.normpath(token if token.startswith('/') else posixpath.join(cwd or self.root, token))
        if token[0] in '\\/' and token[1:2] in ('\\', '/'):
            raise Block(f'ruta de red o de dispositivo: {token}')
        drive = _MSYS.match(token)
        if drive:
            token = f'{drive[1]}:/{token[drive.end():]}'
        elif token[0] in '\\/':
            raise Block(f'ruta absoluta fuera de root: {token}')
        elif token[1:2] == ':' and token[0].isalpha():
            if not _DRIVE.match(token):
                raise Block(f'ruta relativa a una unidad: {token}')
        else:
            token = ntpath.join(cwd or self.root, token)
        if ':' in token[2:]:
            raise Block(f'":" dentro de la ruta: {token}')   # NTFS streams: .git::$INDEX_ALLOCATION
        for part in re.split(r'[\\/]+', token[3:]):
            # Windows drops trailing dots and spaces and maps device names: 'x.' is 'x'.
            if part not in ('', '.', '..') and (part[-1] in '. ' or _DEVICE.fullmatch(part)):
                raise Block(f'nombre que Windows reinterpreta: {part}')
        return ntpath.normpath(token)

    def locate(self, token: str, cwd: str | None = None, *, write: bool = False) -> str:
        """Root-relative path of something the session may read (or write); Block otherwise."""
        full = self.absolute(token, cwd)
        found = [self._relative(full, self.root)]
        if os.path is self.flavour:   # same kind of path as this machine: follow links and junctions too
            try:
                found.append(self._relative(os.path.realpath(full), os.path.realpath(self.root)))
            except (OSError, ValueError):
                raise Block(f'no se pudo resolver la ruta: {token}') from None
        for relative in found:
            if relative is None:
                raise Block(f'ruta fuera de root: {token}')
            key = self._key(relative)
            for part in key.split('/'):
                if any(fnmatch.fnmatchcase(part, pattern)
                       for pattern in PROTECTED + (WRITE_PROTECTED if write else ())):
                    raise Block(f'nombre protegido ({part}): {token}')
            if write and not any(key == entry or (entry.endswith('/') and key.startswith(entry))
                                 for entry in self.allowed):
                raise Block(f'solo se puede escribir en {", ".join(self.allowed)}: {token}')
        return found[0]


# --------------------------------------------------------------------------------------
# Bash: tokens
# --------------------------------------------------------------------------------------

_OPERATOR_CHARS = ';&|<>()'
_SEPARATORS = ('&&', '||', ';', '|', '\n')
_REDIRECTS = ('>', '>>', '<', '&>', '&>>', '>&', '<&')
_FORBIDDEN_TEXT = (('`', 'comillas invertidas'), ('$(', 'sustitución de comandos $( )'),
                   ('<(', 'sustitución de procesos <( )'), ('>(', 'sustitución de procesos >( )'))


class Word:
    """A shell word after quote removal; mask says which characters were bare ('u') or quoted ('q')."""
    __slots__ = ('text', 'mask', 'glued')

    def __init__(self, text: str, mask: str, glued: bool = False):
        self.text, self.mask, self.glued = text, mask, glued   # glued: an operator follows with no blank

    def bare(self, chars: str) -> bool:
        return any(char in chars and kind == 'u' for char, kind in zip(self.text, self.mask))


def _lex(command: str) -> list:
    """Words and operators of a command line, refusing every expansion bash would perform."""
    tokens, text, mask, i, size = [], [], [], 0, len(command)
    open_word = False

    def flush(glued=False):
        nonlocal open_word
        if open_word:
            tokens.append(Word(''.join(text), ''.join(mask), glued))
            text.clear()
            mask.clear()
            open_word = False

    def literal(chars):
        nonlocal open_word
        if '\n' in chars:
            raise Block('salto de línea dentro de comillas')
        text.extend(chars)
        mask.extend('q' * len(chars))
        open_word = True

    while i < size:
        char = command[i]
        if char in ' \t':
            flush()
            i += 1
        elif char == '\n':
            flush()
            tokens.append('\n')
            i += 1
        elif char in _OPERATOR_CHARS:
            end = i
            while end < size and command[end] in _OPERATOR_CHARS:
                end += 1
            flush(glued=True)
            tokens.append(command[i:end])
            i = end
        elif char == '\\':
            if i + 1 >= size or command[i + 1] == '\n':
                raise Block('barra invertida al final de la línea')
            literal(command[i + 1])
            i += 2
        elif char == "'":
            end = command.find("'", i + 1)
            if end < 0:
                raise Block('comilla sin cerrar')
            literal(command[i + 1:end])
            i = end + 1
        elif char == '"':
            i += 1
            literal('')
            while i < size and command[i] != '"':
                char = command[i]
                if char == '\\' and command[i + 1:i + 2] in ('\\', '"', '$', '`'):
                    i += 1
                    char = command[i]
                elif char == '$' and command[i + 1:i + 2] not in ('"', '|', ')', ' '):
                    raise Block('expansión de variables ($)')
                literal(char)
                i += 1
            if i >= size:
                raise Block('comilla sin cerrar')
            i += 1
        elif char == '$':
            raise Block('expansión de variables ($)')
        elif char == '#' and not open_word:
            raise Block('comentario (#) dentro del comando')
        else:
            text.append(char)
            mask.append('u')
            open_word = True
            i += 1
    flush()
    return tokens


def _tokens(command: str) -> list:
    """Tokens of the command. shlex has to read it the same way, or it is refused."""
    tokens = _lex(command)
    reference = []
    try:
        for line in command.split('\n'):
            lexer = shlex.shlex(line, posix=True, punctuation_chars=True)
            lexer.whitespace_split, lexer.commenters = True, ''
            reference += [*lexer, '\n']
    except ValueError as error:
        raise Block(f'no se pudo separar el comando: {error}') from None
    if reference[:-1] != [token.text if isinstance(token, Word) else token for token in tokens]:
        raise Block('el comando admite más de una lectura; usá comillas simples y sin escapes')
    return tokens


def _segments(tokens: list) -> list[tuple[str | None, list[Word], list[tuple[str, Word]]]]:
    """Simple commands as (operator before it, words, redirections), split at &&, ||, ;, | and line breaks."""
    segments, words, redirects, joiner = [], [], [], None
    index = 0
    while index < len(tokens):
        token = tokens[index]
        index += 1
        if isinstance(token, Word):
            words.append(token)
        elif token in _SEPARATORS:
            if words or redirects:
                segments.append((joiner, words, redirects))
                words, redirects, joiner = [], [], token
            elif token != '\n':
                raise Block(f'"{token}" sin un comando antes')
        elif token in _REDIRECTS:
            # A bare number glued to the operator is its file descriptor (2>file), not an argument.
            if token[0] != '&' and words and words[-1].glued and words[-1].text.isdigit() \
                    and 'q' not in words[-1].mask:
                words.pop()
            if index >= len(tokens) or not isinstance(tokens[index], Word):
                raise Block('redirección sin destino')
            redirects.append((token, tokens[index]))
            index += 1
        else:
            raise Block(f'operador no permitido: {token}')
    if words or redirects:
        segments.append((joiner, words, redirects))
    elif joiner in ('&&', '||', '|'):
        raise Block('el comando termina en un operador')
    return segments


def _expansions(word: Word) -> None:
    """What bash still expands in a word the lexer accepted: braces, ~ and globs."""
    if word.text in ('eval', 'exec'):
        raise Block(f'{word.text} no está permitido')
    if word.bare('{}'):
        raise Block('llaves sin comillas (expansión de llaves)')
    for index, (char, kind) in enumerate(zip(word.text, word.mask)):
        if char == '~' and kind == 'u' and (index == 0 or word.text[index - 1] in ':='):
            raise Block('expansión de ~')
    if word.bare('*?['):
        if word.mask[0] == 'u' and word.text[0] in '*?[':
            raise Block('un comodín al inicio puede expandirse a una opción; anteponé ./')
        if re.search(r'(^|/)\.[^/]*[*?\[]', word.text):
            raise Block('comodín que puede coincidir con ".."')


# --------------------------------------------------------------------------------------
# Bash: programs
# --------------------------------------------------------------------------------------

class Shell:
    """Paths as one command sees them: from every directory the earlier `cd`s may have left it in."""

    def __init__(self, scope: Scope, python: str, cwd: str):
        self.scope, self.python = scope, python
        self.cwds = [cwd]     # where the command being checked may run
        self.moved = None     # where a `cd` in that command leads

    def path(self, token: str, write: bool = False) -> None:
        if token == '/dev/null':
            return
        for cwd in self.cwds:
            try:
                self.scope.locate(token, cwd, write=write)
            except Block as block:
                if len(self.cwds) == 1:
                    raise
                raise Block(f'{block} (vista desde {cwd}: un cd anterior puede no haberse hecho; '
                            'encadenalo con &&)') from None

    def cd(self, token: str) -> None:
        self.path(token)
        self.moved = _merge([], [self.scope.absolute(token, cwd) for cwd in self.cwds])

    def is_python(self, name: str) -> bool:
        if name == 'python':
            return True
        try:
            mine, theirs = self.scope.absolute(self.python), self.scope.absolute(name)
        except Block:
            return False
        return '/' in name.replace('\\', '/') and self.scope._key(mine) == self.scope._key(theirs)


def _options(args: list[str], shell: Shell, short: str = '', long: str = '', valued: dict | None = None,
             digits: bool = False, attached: bool = False) -> tuple[list[str], dict[str, list[str]]]:
    """Operands and the options seen. Options that are not listed are refused.

    short: boolean letters. long: boolean names, 'name=' when --name=value is optional.
    valued: option -> 'num' | 'text' | 'path' (paths are checked here). digits: accepts -<n>.
    attached: text and path values must be glued (--opt=value, -ovalue), so an argument can
    never hide behind an option this table wrongly believes takes a value.
    """
    valued, names = valued or {}, set(long.split())
    operands, seen = [], {}
    index = 0

    def take(option: str, value: str | None) -> None:
        nonlocal index
        kind = valued[option]
        if value is None:
            if index >= len(args):
                raise Block(f'falta el valor de {option}')
            if attached and kind != 'num':
                raise Block(f'{option}: pasá el valor pegado a la opción')
            value = args[index]
            index += 1
        if kind == 'num' and not _NUMBER.fullmatch(value):
            raise Block(f'{option} espera un número')
        if kind == 'path':
            shell.path(value)
        seen.setdefault(option, []).append(value)

    while index < len(args):
        arg = args[index]
        index += 1
        if arg == '--':
            operands += args[index:]
            break
        if arg == '-' or not arg.startswith('-'):
            operands.append(arg)
        elif arg.startswith('--'):
            name, equals, value = arg.partition('=')
            if name in valued:
                take(name, value if equals else None)
            elif f'{name[2:]}=' in names or (name[2:] in names and not equals):
                seen.setdefault(name, []).append(value)
            else:
                raise Block(f'opción no permitida: {name}')
        elif digits and arg[1:].isdigit():
            seen.setdefault('-<n>', []).append(arg[1:])
        else:
            for position, letter in enumerate(arg[1:], start=2):
                option = f'-{letter}'
                if option in valued:
                    take(option, arg[position:] or None)
                    break
                if letter not in short:
                    raise Block(f'opción no permitida: {option}')
                seen.setdefault(option, []).append('')
    return operands, seen


def _reader(operands: int | None = None, **spec):
    """A program that only reads the paths it is given."""
    def check(args: list[str], shell: Shell) -> None:
        paths, _ = _options(args, shell, **spec)
        if operands is not None and len(paths) > operands:
            raise Block('demasiados argumentos')
        for path in paths:
            shell.path(path)
    return check


def _search(pattern_options: tuple[str, ...], **spec):
    """grep and rg: the first operand is the pattern unless an option already gave it."""
    def check(args: list[str], shell: Shell) -> None:
        paths, seen = _options(args, shell, **spec)
        if not seen.keys() & set(pattern_options):
            if not paths:
                raise Block('falta el patrón')
            paths = paths[1:]
        for path in paths:
            shell.path(path)
    return check


def _nothing(args: list[str], shell: Shell) -> None:
    if args:
        raise Block('no acepta argumentos')


def _cd(args: list[str], shell: Shell) -> None:
    if len(args) != 1 or args[0].startswith('-'):
        raise Block('cd acepta solo una ruta dentro de root')
    shell.cd(args[0])


_FIND_FLAGS = set('-print -print0 -prune -empty -readable -writable -executable -depth -xdev -mount -daystart '
                  '-true -false -not -o -or -a -and -ls -quit ! ( ) ,'.split())
_FIND_VALUED = {**dict.fromkeys(
    '-name -iname -path -ipath -wholename -iwholename -regex -iregex -regextype -type -maxdepth -mindepth '
    '-mtime -mmin -atime -amin -ctime -cmin -size -perm -user -group -links -printf'.split(), 'text'),
    '-newer': 'path', '-anewer': 'path', '-cnewer': 'path', '-samefile': 'path'}


def _find(args: list[str], shell: Shell) -> None:
    index = 0
    while index < len(args) and not (args[index].startswith('-') or args[index] in ('(', '!')):
        shell.path(args[index])
        index += 1
    while index < len(args):
        test = args[index]
        index += 1
        if test in _FIND_VALUED:
            if index >= len(args):
                raise Block(f'find: falta el valor de {test}')
            if _FIND_VALUED[test] == 'path':
                shell.path(args[index])
            index += 1
        elif test not in _FIND_FLAGS:
            raise Block(f'find: {test} no está permitido (nada de -exec, -delete ni escritura)')


def _sed(args: list[str], shell: Shell) -> None:
    paths, seen = _options(args, shell, short='nEr', long='quiet silent regexp-extended',
                           valued={'-e': 'text', '--expression': 'text'})
    if not seen.keys() & {'-n', '--quiet', '--silent'}:
        raise Block('sed solo como sed -n (imprimir líneas)')
    scripts = seen.get('-e', []) + seen.get('--expression', [])
    if not scripts:
        if not paths:
            raise Block('sed: falta el script')
        scripts, paths = paths[:1], paths[1:]
    for script in scripts:
        if not _SED_SCRIPT.fullmatch(script):
            raise Block('sed: solo direcciones con p, q o = (por ejemplo sed -n "10,20p")')
    for path in paths:
        shell.path(path)


def _plus(base: dict, short: str = '', long: str = '', valued: dict | None = None, **more) -> dict:
    return {**base, **more, 'short': base.get('short', '') + short, 'long': f'{base.get("long", "")} {long}',
            'valued': {**base.get('valued', {}), **(valued or {})}}


_GIT_DIFF = dict(
    short='pusqwbRaz',
    long='patch no-patch stat= shortstat numstat name-only name-status summary raw check cached staged quiet '
         'exit-code color= no-color word-diff= minimal patience histogram ignore-all-space ignore-space-change '
         'ignore-space-at-eol ignore-blank-lines no-renames find-renames= full-index abbrev= text no-ext-diff '
         'no-textconv no-prefix compact-summary function-context',
    valued={'-U': 'num', '--unified': 'num', '-S': 'text', '-G': 'text', '--diff-filter': 'text',
            '--diff-algorithm': 'text'})
_GIT_LOG = _plus(
    _GIT_DIFF, short='iEF', digits=True,
    long='oneline graph decorate= no-decorate all branches= tags= remotes= reverse merges no-merges first-parent '
         'follow abbrev-commit date-order topo-order full-history left-right pretty= invert-grep',
    valued={'-n': 'num', '--max-count': 'num', '--skip': 'num', '--since': 'text', '--after': 'text',
            '--until': 'text', '--before': 'text', '--author': 'text', '--committer': 'text', '--grep': 'text',
            '--format': 'text', '--date': 'text', '-L': 'text'})
# No -C, -c, --git-dir, --work-tree, --output, --no-index, --ext-diff, -p/-i/-e on add or restore.
_GIT = {
    'status': dict(short='sbvz', long='short branch long verbose null show-stash renames no-renames ahead-behind '
                                      'no-ahead-behind porcelain= untracked-files= ignored= column= no-column'),
    'diff': _GIT_DIFF,
    'show': _plus(_GIT_DIFF, long='oneline abbrev-commit pretty= no-notes',
                  valued={'--format': 'text', '--date': 'text'}),
    'log': _GIT_LOG,
    'blame': dict(short='beflnpstw', long='porcelain line-porcelain root show-name show-number show-email '
                                          'show-stats abbrev= minimal',
                  valued={'-L': 'text', '--date': 'text'}),
    'ls-files': dict(short='cdmoistuz', long='cached deleted modified others ignored stage unmerged killed '
                                             'directory exclude-standard full-name error-unmatch deduplicate abbrev=',
                     valued={'-x': 'text', '--exclude': 'text'}),
    'rev-parse': dict(short='q', long='short= abbrev-ref= symbolic-full-name verify quiet show-toplevel '
                                      'show-prefix show-cdup is-inside-work-tree all'),
    'add': dict(short='AuNvn', long='all update intent-to-add verbose dry-run'),
    'restore': dict(short='SWq', long='staged worktree quiet', valued={'-s': 'text', '--source': 'text'}),
}


def _git_operand(item: str, shell: Shell) -> None:
    """A revision, a range, <rev>:<path> or a path. Whatever could name a file is checked as one:
    git diff compares files outside the repository when it is handed two of them."""
    revision, colon, path = item.partition(':')
    span = _RANGE.fullmatch(item)
    if colon and len(revision) > 1 and re.fullmatch(_REV, revision):
        shell.path(path or '.')
    elif span and (span[1] or span[2]):
        for side in filter(None, span.groups()):
            shell.path(side)
    else:
        shell.path(item)


def _git(args: list[str], shell: Shell) -> None:
    while args and args[0] in ('--no-pager', '-P', '--no-optional-locks'):
        args = args[1:]
    command, rest = (args[0] if args else ''), args[1:]
    if command == 'branch':
        if rest != ['--show-current']:
            raise Block('git branch solo con --show-current')
        return
    if command == 'stash':
        if rest[:1] != ['list']:
            raise Block('git stash solo con list')
        command, rest = 'log', rest[1:]
    if command not in _GIT:
        raise Block(f'git {command or "sin subcomando"} no está permitido (status, diff, log, show, blame, '
                    'ls-files, rev-parse, branch --show-current, add, restore, stash list; sin opciones globales)')
    operands, _ = _options(rest, shell, attached=True, **_GIT[command])
    for operand in operands:
        _git_operand(operand, shell)


def _pytest(args: list[str], shell: Shell) -> None:
    if any(arg.startswith('@') for arg in args):
        # pytest replaces @file by the arguments written in it, and quotes them back when they are wrong.
        raise Block('pytest: sin archivos de argumentos (@archivo)')
    operands, seen = _options(
        args, shell, short='qvxsl',
        long='quiet verbose exitfirst showlocals lf last-failed ff failed-first nf new-first sw stepwise '
             'collect-only co no-header no-summary disable-warnings strict-markers strict-config setup-show '
             'fixtures markers version',
        valued={'-k': 'text', '-m': 'text', '-r': 'text', '-p': 'text', '-W': 'text', '--tb': 'text',
                '--maxfail': 'num', '--durations': 'num', '--color': 'text', '--capture': 'text',
                '--deselect': 'text', '--ignore': 'path'})
    if any(not plugin.startswith('no:') for plugin in seen.get('-p', [])):
        raise Block('pytest -p solo para desactivar plugins (-p no:...)')
    for operand in operands:
        shell.path(operand.split('::', 1)[0])   # tests/test_x.py::test_name[param]


def _py_compile(args: list[str], shell: Shell) -> None:
    operands, _ = _options(args, shell, short='q')
    if not operands or '-' in operands:
        raise Block('py_compile necesita archivos dentro de root')
    for operand in operands:
        shell.path(operand)


def _collector_cli(args: list[str], shell: Shell, long: str, valued: dict, source: bool = True) -> None:
    """<source> [options] [key=value ...], as tools.repro_target and repairbot.vps take them."""
    operands, _ = _options(args, shell, long=long, valued=valued)
    if source and not (operands and _SOURCE.fullmatch(operands[0])):
        raise Block('falta el nombre de la fuente')
    for operand in operands[1 if source else 0:]:
        if not _PAIR.match(operand):
            raise Block(f'argumento no permitido: {operand} (solo clave=valor)')


def _repro_target(args: list[str], shell: Shell) -> None:
    _collector_cli(args, shell, 'json no-db', {'--target-id': 'num', '--limit-sample': 'num', '--timeout': 'num'})


def _vps(args: list[str], shell: Shell) -> None:
    if not args or args[0] not in ('status', 'logs', 'probe'):
        raise Block('repairbot.vps solo acepta status, logs o probe')
    _collector_cli(args[1:], shell, '', {'--target-id': 'num', '--minutes': 'num', '--lines': 'num'},
                   source=args[0] != 'status')


_MODULES = {'pytest': _pytest, 'py_compile': _py_compile, 'tools.repro_target': _repro_target,
            'repairbot.vps': _vps}


def _python(args: list[str], shell: Shell) -> None:
    if len(args) < 2 or args[0] != '-m' or args[1] not in _MODULES:
        raise Block(f'python solo como -m {" | -m ".join(_MODULES)}')
    _MODULES[args[1]](args[2:], shell)


_CONTEXT = {'-A': 'num', '-B': 'num', '-C': 'num', '-m': 'num', '--after-context': 'num',
            '--before-context': 'num', '--context': 'num', '--max-count': 'num'}
_PROGRAMS = {
    'cd': _cd, 'pwd': _nothing, 'true': _nothing, 'echo': lambda args, shell: None,
    'find': _find, 'sed': _sed, 'git': _git,
    'ls': _reader(short='aAbBcCdfFgGhiklmnNopqQrRsStuUvxX1',
                  long='all almost-all human-readable recursive reverse directory size classify= color= '
                       'group-directories-first numeric-uid-gid no-group inode si',
                  valued={'-I': 'text', '-w': 'num', '-T': 'num', '--ignore': 'text', '--hide': 'text',
                          '--sort': 'text', '--time': 'text', '--time-style': 'text', '--block-size': 'text'}),
    'cat': _reader(short='AbeEnstTuv', long='show-all number-nonblank show-ends number squeeze-blank show-tabs '
                                            'show-nonprinting'),
    'head': _reader(short='qvz', long='quiet silent verbose zero-terminated', digits=True,
                    valued={'-n': 'num', '-c': 'num', '--lines': 'num', '--bytes': 'num'}),
    'tail': _reader(short='qvz', long='quiet silent verbose zero-terminated', digits=True,
                    valued={'-n': 'num', '-c': 'num', '--lines': 'num', '--bytes': 'num'}),
    'wc': _reader(short='clmwL', long='bytes chars lines words max-line-length'),
    'diff': _reader(short='abBcdeEiNpqrstTuwyZ',
                    long='brief recursive new-file text ignore-case ignore-all-space ignore-space-change '
                         'ignore-blank-lines ignore-trailing-space ignore-tab-expansion strip-trailing-cr '
                         'side-by-side minimal report-identical-files suppress-common-lines expand-tabs '
                         'no-dereference show-c-function unified= context= color=',
                    valued={'-U': 'num', '-C': 'num', '-W': 'num', '-I': 'text', '-x': 'text', '-L': 'text',
                            '-F': 'text', '--width': 'num', '--label': 'text', '--exclude': 'text',
                            '--ignore-matching-lines': 'text', '--show-function-line': 'text'}),
    'sort': _reader(short='bdfghiMnRrVsuzcCm',
                    long='ignore-leading-blanks dictionary-order ignore-case general-numeric-sort '
                         'ignore-nonprinting month-sort human-numeric-sort numeric-sort random-sort reverse '
                         'version-sort stable unique zero-terminated merge check=',
                    valued={'-k': 'text', '-t': 'text', '--key': 'text', '--field-separator': 'text',
                            '--sort': 'text'}),
    # uniq INPUT OUTPUT writes its second operand.
    'uniq': _reader(operands=1, short='cdDiuz',
                    long='count repeated unique ignore-case zero-terminated all-repeated= group=',
                    valued={'-f': 'num', '-s': 'num', '-w': 'num', '--skip-fields': 'num',
                            '--skip-chars': 'num', '--check-chars': 'num'}),
    'grep': _search(('-e', '-f', '--regexp', '--file'), digits=True, short='abcEFGhHiIlLnoPqrsTUvwxzZ',
                    long='extended-regexp fixed-strings basic-regexp perl-regexp ignore-case no-ignore-case '
                         'word-regexp line-regexp invert-match count files-with-matches files-without-match '
                         'only-matching quiet silent no-messages byte-offset with-filename no-filename '
                         'line-number initial-tab null null-data text recursive line-buffered color= colour=',
                    valued={**_CONTEXT, '-e': 'text', '-f': 'path', '-d': 'text', '-D': 'text',
                            '--regexp': 'text', '--file': 'path', '--include': 'text', '--exclude': 'text',
                            '--exclude-dir': 'text', '--binary-files': 'text', '--label': 'text',
                            '--directories': 'text', '--devices': 'text'}),
    # No --pre / --hostname-bin (they run programs), -f, --ignore-file, --follow, --search-zip.
    'rg': _search(('-e', '--regexp', '--files', '--type-list'), short='acFHiIlnNopPqsSuUvwx0.',
                  long='files files-with-matches files-without-match count count-matches ignore-case smart-case '
                       'case-sensitive word-regexp line-regexp fixed-strings invert-match only-matching '
                       'line-number no-line-number column no-column heading no-heading with-filename '
                       'no-filename hidden no-hidden no-ignore no-ignore-vcs multiline multiline-dotall pcre2 '
                       'text json stats trim vimgrep quiet null pretty no-messages no-config passthru '
                       'type-list unrestricted',
                  valued={**_CONTEXT, '-e': 'text', '-g': 'text', '-t': 'text', '-T': 'text', '-d': 'num',
                          '-M': 'num', '-j': 'num', '-r': 'text', '-E': 'text', '--regexp': 'text',
                          '--glob': 'text', '--iglob': 'text', '--type': 'text', '--type-not': 'text',
                          '--max-depth': 'num', '--max-columns': 'num', '--threads': 'num',
                          '--replace': 'text', '--encoding': 'text', '--color': 'text', '--colors': 'text',
                          '--sort': 'text', '--sortr': 'text', '--max-filesize': 'text'}),
}


def _redirect(operator: str, target: Word, shell: Shell) -> None:
    if operator in ('>&', '<&') and (target.text.isdigit() or target.text == '-'):
        return   # 2>&1
    if operator == '<&' or target.bare('*?['):
        raise Block('redirección no permitida')
    shell.path(target.text, write=operator != '<')   # writes only where Edit and Write may


def _bash(command: str, shell: Shell) -> None:
    command = command.replace('\r\n', '\n')
    if not command.strip():
        raise Block('comando vacío')
    if any((ord(char) < 32 and char not in '\t\n') or char == '\x7f' for char in command):
        raise Block('caracteres de control en el comando')
    for needle, name in _FORBIDDEN_TEXT:
        if needle in command:
            raise Block(f'no se permite: {name}')
    segments = _segments(_tokens(command))
    # Directories the shell may be in after the commands so far succeeded / failed. A `cd` only
    # counts for what `&&` chains to it: it can fail, and inside a pipe it runs in a subshell.
    succeeded, failed = list(shell.cwds), []
    index = 0
    while index < len(segments):
        end = index + 1
        while end < len(segments) and segments[end][0] == '|':
            end += 1
        joiner = segments[index][0]
        entry = succeeded if joiner == '&&' else failed if joiner == '||' else _merge(succeeded, failed)
        if not entry:
            raise Block('no se pudo seguir el directorio de trabajo')
        shell.cwds, shell.moved = entry, None
        for _, words, redirects in segments[index:end]:
            _command(words, redirects, shell)
        after = shell.moved if shell.moved and end - index == 1 else entry
        if joiner == '&&':
            succeeded, failed = after, _merge(failed, entry)
        elif joiner == '||':
            succeeded, failed = _merge(succeeded, after), entry
        else:
            succeeded, failed = after, entry
        if len(succeeded) + len(failed) > 32:
            raise Block('demasiados cd en un solo comando')
        index = end


def _merge(first: list[str], second: list[str]) -> list[str]:
    return list(dict.fromkeys([*first, *second]))


def _command(words: list[Word], redirects: list[tuple[str, Word]], shell: Shell) -> None:
    for word in [*words, *(target for _, target in redirects)]:
        _expansions(word)
    if not words:
        raise Block('redirección sin comando')
    for operator, target in redirects:
        _redirect(operator, target, shell)
    name = words[0].text
    check = _PROGRAMS.get(name) or (_python if shell.is_python(name) else None)
    if not check and _PAIR.match(name):
        raise Block(f'no se pueden definir variables delante del comando: {name}')
    if not check:
        raise Block(f'programa no permitido: {name}')
    check([word.text for word in words[1:]], shell)


# --------------------------------------------------------------------------------------
# Tools
# --------------------------------------------------------------------------------------

def _text(data: dict, key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value:
        raise Block(f'falta {key}')
    return value


def _glob(pattern: str) -> None:
    """Braces in a glob can spell any path ({..,x}/, {C:/Users,x}/): keep them to file names."""
    depth = 0
    for char in pattern:
        if char in '{}':
            depth += 1 if char == '{' else -1
            if depth not in (0, 1):
                raise Block(f'llaves anidadas o sin cerrar en el patrón: {pattern}')
        elif depth and char in '/\\:':
            raise Block(f'rutas dentro de llaves en el patrón: {pattern}')
    if depth or '..' in pattern:
        raise Block(f'patrón no permitido: {pattern}')


def _check(tool, data, scope: Scope, python: str, cwd) -> None:
    if tool not in TOOLS:
        raise Block(f'herramienta no permitida: {tool}')
    if not isinstance(data, dict):
        raise Block('entrada de la herramienta inválida')
    if tool == 'StructuredOutput':
        return
    if cwd is not None and not isinstance(cwd, str):
        raise Block('cwd inválido')
    here = scope.absolute(cwd) if cwd else scope.root
    if scope._relative(here, scope.root) is None:
        raise Block(f'el directorio de trabajo está fuera de root: {cwd}')
    if tool == 'Bash':
        if data.get('run_in_background') or data.get('dangerouslyDisableSandbox'):
            raise Block('sin ejecuciones en segundo plano ni fuera del sandbox')
        _bash(_text(data, 'command'), Shell(scope, python, here))
    elif tool == 'Glob':
        base = here
        if data.get('path') is not None:
            scope.locate(_text(data, 'path'), here)
            base = scope.absolute(data['path'], here)
        _glob(_text(data, 'pattern'))
        scope.locate(data['pattern'], base)
    elif tool == 'Grep':
        _text(data, 'pattern')
        if data.get('path') is not None:
            scope.locate(_text(data, 'path'), here)
        if data.get('glob') is not None:
            _glob(_text(data, 'glob'))
            scope.locate(data['glob'].lstrip('!/'), here)
    else:
        scope.locate(_text(data, 'file_path'), here, write=tool != 'Read')


def decide(tool_name: str, tool_input: dict, root: Path, python: Path, *, cwd: str | None = None,
           allowed: tuple[str, ...] = DEFAULT_ALLOWED) -> str | None:
    """Why this tool call is blocked, or None to let it through."""
    try:
        _check(tool_name, tool_input, Scope(root, allowed), str(python), cwd)
    except Block as block:
        return str(block) or 'bloqueado'
    except Exception as error:   # a bug here must never open the door
        return f'el guard falló ({type(error).__name__}); se bloquea por las dudas'
    return None


def _log(path: Path, tool: object, reason: str | None, detail: object) -> None:
    record = {'ts': datetime.now(timezone.utc).isoformat(timespec='seconds'), 'tool': str(tool)[:60],
              'verdict': 'block' if reason else 'allow', 'reason': reason or '', 'command': str(detail)[:300]}
    with open(path, 'a', encoding='utf-8') as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + '\n')


def _run(argv: list[str] | None, stdin: bytes | None) -> int:
    parser = argparse.ArgumentParser(description='Guard PreToolUse del bot de reparación.')
    parser.add_argument('--root', required=True)
    parser.add_argument('--python', required=True)
    parser.add_argument('--log', required=True, type=Path)
    parser.add_argument('--allow', action='append')
    parser.add_argument('--canary', metavar='RUN_ID', help='SessionStart: prueba esta misma línea de comando')
    args = parser.parse_args(argv)
    allowed = tuple(args.allow or DEFAULT_ALLOWED)
    if args.canary:
        Scope(args.root, allowed)
        if not Path(args.root).is_dir() or not Path(args.python).is_file():
            raise Block('root o python no existen')
        _log(args.log, 'SessionStart', None, args.canary)
        print(f'{CANARY} {args.canary}', flush=True)
        return 0
    payload = json.loads((sys.stdin.buffer.read() if stdin is None else stdin).decode('utf-8'))
    if not isinstance(payload, dict) or payload.get('hook_event_name', 'PreToolUse') != 'PreToolUse':
        raise Block('entrada del hook inválida')
    tool, data = payload.get('tool_name'), payload.get('tool_input')
    reason = 'entrada del hook inválida' if not isinstance(tool, str) else decide(
        tool, data, args.root, args.python, cwd=payload.get('cwd'), allowed=allowed)
    detail = data if not isinstance(data, dict) else next(
        (data[key] for key in ('command', 'file_path', 'pattern', 'path') if key in data), '')
    _log(args.log, tool, reason, detail)
    if reason:
        print(f'Bloqueado por el guard: {reason}', file=sys.stderr)
        return 2
    return 0


def main(argv: list[str] | None = None, stdin: bytes | None = None) -> int:
    """0 or 2, never anything else: an exit code of 1 would let the tool call through."""
    try:
        if hasattr(sys.stderr, 'reconfigure'):
            sys.stderr.reconfigure(encoding='utf-8', errors='replace')
        return _run(argv, stdin)
    except SystemExit:   # argparse: bad arguments (and --help) are a block too
        return 2
    except BaseException as error:
        try:
            print(f'Bloqueado por el guard: {error if isinstance(error, Block) else type(error).__name__}',
                  file=sys.stderr)
        except Exception:
            pass
        return 2


if __name__ == '__main__':
    sys.exit(main())

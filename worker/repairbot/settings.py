"""Bot configuration (no secrets) and the two environments it builds.

config.json lives in the bot home, outside any checkout. Secrets stay in the
main checkout's .env: the launcher loads only ENV_KEYS from it, and the Claude
child process gets none of them.
"""
from __future__ import annotations

from dataclasses import dataclass, fields
import json
import os
from pathlib import Path

DEFAULT_CONFIG = Path('C:/automotive-bot/config.json')
ENV_KEYS = ('DATABASE_URL', 'RESEND_API_KEY', 'EMAIL_FROM', 'PLATFORM_HEALTH_EMAIL', 'WEB_BASE_URL')
THREAD_PREFIX = 'claude-bot:'
ORIGIN_URL = 'https://github.com/JCapurro/AutoMotive.git'

# Variables the Claude child inherits from this process; everything else is dropped.
_INHERITED = ('SystemRoot', 'WINDIR', 'USERPROFILE', 'HOMEDRIVE', 'HOMEPATH', 'APPDATA', 'LOCALAPPDATA',
              'TEMP', 'TMP', 'USERNAME', 'COMSPEC', 'PATH', 'PATHEXT', 'ProgramFiles', 'ProgramFiles(x86)',
              'ProgramData')
_PATHS = ('home', 'repo', 'env_file', 'python', 'claude', 'git_bash')
_OPTIONAL_PATHS = ('launcher',)
_TUPLES = ('retry_delays_s', 'allowed_paths')


@dataclass(frozen=True)
class Settings:
    home: Path
    repo: Path                    # Claude's workspace: reset to origin/main around every attempt
    env_file: Path
    python: Path
    claude: Path
    git_bash: Path
    launcher: Path | None = None  # the clone the scheduled task runs from; None: home/'launcher'
    ssh_host: str = 'automotive-vps'
    vps_hostname: str = 'vps-6488403-x'
    vps_root: str = '/opt/automotive'
    owner: str = 'claude-repair-bot'
    model: str = 'opus'
    effort: str = 'high'
    max_turns: int = 150
    claude_timeout_s: int = 2700
    max_attempts: int = 3
    max_sessions_per_day: int = 6
    retry_delays_s: tuple[int, ...] = (1800, 7200, 21600)
    verify_timeout_s: int = 1500
    wait_idle_s: int = 300
    max_diff_lines: int = 400
    max_probes: int = 8
    allowed_paths: tuple[str, ...] = ('worker/collectors/', 'worker/tests/', 'worker/http_clients.py')
    enabled: bool = True

    def __post_init__(self) -> None:
        if self.launcher is None:   # configs written before the launcher had its own clone
            object.__setattr__(self, 'launcher', Path(self.home) / 'launcher')

    @property
    def state_dir(self) -> Path:
        return self.home / 'state'

    @property
    def runs_dir(self) -> Path:
        return self.home / 'runs'


def from_dict(raw: dict) -> Settings:
    known = {field.name for field in fields(Settings)}
    unknown = sorted(set(raw) - known)
    if unknown:
        raise ValueError(f'config.json: claves desconocidas: {", ".join(unknown)}')
    values = dict(raw)
    for key in _PATHS:
        if key not in values:
            raise ValueError(f'config.json: falta {key}')
        values[key] = Path(values[key])
    for key in _OPTIONAL_PATHS:
        if values.get(key) is not None:
            values[key] = Path(values[key])
    for key in _TUPLES:
        if key in values:
            values[key] = tuple(values[key])
    return Settings(**values)


def load(path: Path | None = None) -> Settings:
    path = Path(path or os.environ.get('REPAIRBOT_CONFIG') or DEFAULT_CONFIG)
    return from_dict(json.loads(path.read_text(encoding='utf-8')))


def load_env(settings: Settings) -> None:
    """Load only ENV_KEYS from the main checkout's .env into this process."""
    from dotenv import dotenv_values

    values = dotenv_values(settings.env_file)
    for key in ENV_KEYS:
        if values.get(key):
            os.environ[key] = values[key]


def child_env(settings: Settings, run_id: str, config_path: Path | None = None) -> dict[str, str]:
    """Whitelisted environment for the Claude child: no secrets, no inherited Claude session."""
    env = {key: os.environ[key] for key in _INHERITED if key in os.environ}
    env.update({
        'DISABLE_AUTOUPDATER': '1',
        'CLAUDE_CODE_DISABLE_AUTO_MEMORY': '1',
        'CLAUDE_CODE_DISABLE_BACKGROUND_TASKS': '1',
        'BASH_DEFAULT_TIMEOUT_MS': '300000',
        'BASH_MAX_TIMEOUT_MS': '900000',
        'CLAUDE_CODE_GIT_BASH_PATH': str(settings.git_bash),
        'GIT_TERMINAL_PROMPT': '0',
        'GCM_INTERACTIVE': 'never',
        'PYTHONDONTWRITEBYTECODE': '1',
        'PYTHONUTF8': '1',
        'TEST_DATABASE_URL': '',
        'LLM_SMOKE': '',
        'REPAIRBOT_CONFIG': str(config_path or os.environ.get('REPAIRBOT_CONFIG') or DEFAULT_CONFIG),
        'REPAIRBOT_RUN_ID': run_id,
    })
    return env

# Bot autónomo de reparación de collectors

Juan pidió el 9/10/2026 un bot que detecte collectors con fallas, analice, diagnostique,
corrija y despliegue sin intervención humana. Decisiones suyas: corre en **esta PC**
(Programador de tareas, cada 5 min, `claude -p` con su suscripción), **reemplaza** a la
automatización de Codex sobre la misma cola y **pushea directo a `main`** antes de desplegar.

Este documento es el contrato entre módulos. Lo que no esté acá se resuelve con el criterio
del resto del repo (Python 3.12, sin dependencias nuevas, comentarios escasos y útiles).

## Principio de seguridad

El modelo lee datos no confiables (errores de corridas, HTML de terceros). Por eso el modelo
**solo diagnostica y edita código de collectors**; todo lo que tiene efecto afuera lo ejecuta
el lanzador con código determinístico y compuertas:

| Acción | Quién |
| --- | --- |
| Leer el repo, editar `worker/collectors/**`, `worker/tests/**`, `worker/http_clients.py` | Claude |
| Correr pytest y reproducciones sin ingesta (local y en el VPS vía `repairbot.vps probe`) | Claude, solo con comandos permitidos por el guard |
| Reclamar incidentes, escribir en la base, commit, push, deploy, reinicio, rollback, email | Lanzador |

Claude nunca recibe `DATABASE_URL` ni otras credenciales en su entorno, no tiene `git push`
ni `ssh` libre, y un hook `PreToolUse` deniega por defecto todo comando no listado.
No existe sandbox de sistema operativo en Windows nativo: el guard reduce el riesgo, no lo
elimina (un test malicioso podría leer archivos del usuario). Las compuertas del lanzador
(alcance del diff, tamaño, tests, rollback automático, email por cada deploy) son la segunda línea.

## Ubicaciones

- `C:\automotive-bot\` — home del bot, fuera de `C:\Users\Juan` (el guard bloquea todo `C:\Users`).
  - `config.json` — configuración sin secretos (ver `Settings`).
  - `repo\` — clon completo dedicado de GitHub donde trabaja Claude. El lanzador lo deja igual a `origin/main` antes de cada intento y al terminar uno que no publicó nada. Nunca se usa el checkout del usuario.
  - `launcher\` (`Settings.launcher`) — otro clon propio de GitHub (no un worktree), del que corre la tarea programada. El guard no deja que la sesión lo lea ni lo edite; el lanzador lo avanza por fast-forward a `origin/main` al final de cada tick (`gitops.update_launcher`) y nunca lo resetea. Así el proceso que tiene las claves nunca importa código de una sesión sin revisar.
  - `state\` — `<incident-uuid>.json`, `events.jsonl`, `bot.lock`, `bot.log`, `bot-bootstrap.log`.
  - `runs\<run_id>\` — prompt, settings generados, stream de Claude, guard.log, resultados de probes.
- Código: paquete `worker/repairbot/` (se ejecuta desde el clon del lanzador: `python -m repairbot` con cwd `launcher\worker`; las compuertas corren la suite en `repo\worker`).
- VPS: staging de probes en `/opt/automotive/.repairbot/<run_id>/` (dueño `automotive`, 0700). Está ignorado por git.

## Ciclo (un tick cada 5 minutos)

1. Lock de instancia única (`state\bot.lock`, `msvcrt.locking`). Si está tomado, salir 0.
2. `Settings.enabled` falso → salir. Cargar del `.env` del checkout principal **solo** `ENV_KEYS`.
3. Leer incidentes activos (`resolved_at IS NULL`). Para cada uno del bot (`thread_id LIKE 'claude-bot:%'`):
   - estado local `deployed` → **verificar** (sin Claude): corrida `ok` posterior al deploy de cada target pateado → `fixed` (email). Corrida `failed` posterior → **rollback** (revert + push + deploy) y el intento cuenta como fallido. Sin corridas y dentro de `verify_timeout_s` → esperar al próximo tick. Vencido → intento `unverified` (sin rollback), se reintenta.
   - estado `waiting` con `retry_after` vencido e intentos < `max_attempts` → nuevo intento.
   - intentos agotados → `needs_input` en la cola + email "me rendí" con el historial.
   - incidente del bot sin estado local (estado perdido) → se adopta con 1 intento consumido.
   - Estados locales cuyo incidente ya está resuelto/cancelado → `done`. Con un deploy `live` sin verificar: `fixed` solo si cada target pateado tuvo una corrida `ok` (con `found > 0` si `require_found`) después de `deployed_at`; si no, intento `unverified` + email `unverified` (un kick limpia el reloj de una búsqueda vencida y el monitor cierra sin que haya corrido). Un push o un revert a medias se resuelve igual que en `verify` (abajo) y nunca se informa como `fixed`.
4. Si no quedó un intento por correr: `claim` (dueño `claude-repair-bot`) y `attach` inmediato con `claude-bot:<run_id>`; el incidente queda `open` y nadie más lo reclama.
5. Como máximo **un intento con Claude por tick** y `max_sessions_per_day` por día.
6. Al final de todo tick que tomó el lock (también si falló o `enabled` es falso; nunca en `--dry-run`): `gitops.update_launcher(settings.launcher)`. Un error se registra y se avisa como `bot_error` con su propio tope de uno por día (`incident_id` `launcher`, evento `launcher_error`); el tick siguiente corre el código que había.

### Etapas del deploy (`IncidentState.deploy['stage']`, fase `deployed`)

Cada etapa se guarda **antes** del paso que la puede dejar a medias; un tick posterior la retoma desde `verify`:

| Etapa | Qué se sabe | Al retomar |
| --- | --- | --- |
| `pushing` | Commit local `local`; el push pudo llegar o no. | `gitops.landed(run_id)`: sha → `pushed` y deploy; None → `publish_failed`; GitError → sigue `pushing` (error del tick). |
| `pushed` | En `main`; el VPS no confirmó el deploy. | Deploy otra vez (`already` si ya está). |
| `live` | Desplegado y reiniciado; en verificación. | Verificar. |
| `reverting` | Se decidió deshacerlo (`undo`: `kind` rollback/unpublish, `why`, `label`, `deploy_it`, `blocked`); el revert pudo llegar o no. | `landed(run_id, reverts=commit)`: sha → `reverted`; None → sync + revert + push otra vez. |
| `reverted` | Revert `revert` en `main`. | Deploy del revert si `deploy_it`, reinicio si `kind` es rollback, email `rollback` o `deploy_blocked`, fin del intento. |
| `blocked` | Lo tiene una persona (fase `needs_input`). | — |

### Intento

1. `gitops.sync(repo)` → `origin/main` limpio. `vps.status()`; si el VPS no es alcanzable el intento sigue (Claude diagnostica), pero no habrá deploy.
2. Prompt = política (system) + contexto saneado del incidente + intentos previos + últimas líneas del journal del VPS para esa fuente.
3. `claude_runner.run_claude(...)` con guard, canario y tope de reloj. Salida estructurada (`OUTPUT_SCHEMA`).
4. Según `outcome`:
   - `fixed` → compuertas (`scope_violations` vacío, diff ≤ `max_diff_lines`, hay cambios, `py_compile`, suite no-DB completa corrida **por el lanzador**) → commit → push a `origin/main` → deploy en el VPS → patear targets fallidos → reiniciar worker → fase `deployed`; verificar dentro del mismo tick hasta agotar el tiempo disponible y seguir en ticks posteriores.
   - `external` (caída/bloqueo temporal del sitio, sin cambio de código) → `waiting`, reintento con `retry_delays_s`.
   - `needs_human` (captcha, sesión vencida, credenciales, cambio fuera del alcance permitido) → `needs_input` con `human_action` + email.
   - `recovered` → `done`; el monitor cierra el incidente.
   - `no_fix`, error, timeout, compuerta fallida → intento fallido, `waiting`.
5. Todo intento que no publicó (`attempt.commit` vacío, también si algo levantó una excepción) termina con `gitops.sync`: lo que dejó la sesión sale del clon en el acto.

### Deploy (solo lanzador)

`vps.deploy(sha, base)`:
1. `hostname` == `vps_hostname`; árbol sin modificaciones (`git status --porcelain --untracked-files=no` vacío); si no, abortar con motivo (`dirty` informa igual el HEAD real y `contains`).
2. `prev = HEAD` del VPS. Si `prev` es `sha` o desciende de él (`contains`), `already` (ok). Si `prev != base` (hay commits de `main` sin desplegar que no son del bot): permitido solo si `git diff --name-only prev base` no toca `worker/` ni `supabase/`; si los toca → abortar (`pending_changes`: "hay cambios sin desplegar que requieren a una persona").
3. `git fetch origin` + `git merge --ff-only <sha>` como `automotive`; verificar `HEAD == sha`; `python -m py_compile` de los `.py` cambiados. Si la respuesta se pierde o no trae HEAD, se relee el HEAD (`DEPLOY_HEAD`); si tampoco contesta → `unknown_state` (head None: el VPS puede estar o no en `sha`).
4. El lanzador: `vps_has_it = head == sha or contains` en todo código salvo `unknown_state`. `unknown_state` (o head None al retomar un deploy de un tick cortado) nunca revierte: queda `pushed`, se reintenta en los ticks siguientes y, pasado `verify_timeout_s` desde el primero, `needs_input` + `deploy_blocked` sin revertir. Otro rechazo → revert en `main` (y deploy del revert si `vps_has_it`); un rechazo para una persona (`dirty`, `pending_changes`, `wrong_host`) con `vps_has_it` no revierte nada (`main` no quedó adelantado) y va a `needs_input`.
5. Esperar hasta `wait_idle_s` a que no haya corridas `running` de la fuente (consulta en la base desde la PC), recién ahí `failing_targets`, `systemctl restart` + comprobar que quede estable, y patear los targets.
6. Rollback = `gitops.revert` + push + `deploy` del revert + reinicio, por las etapas `reverting`/`reverted`.

Nunca `git reset --hard` ni `checkout --` en el VPS; nunca escribir como root dentro de `/opt/automotive` (siempre `sudo -u automotive`).

## Contratos de módulos (`worker/repairbot/`)

Todos los módulos son importables sin efectos; nada lee red/DB al importar. Las funciones que
ejecutan procesos aceptan un `runner` inyectable para tests.

### `settings.py`

```python
ENV_KEYS = ('DATABASE_URL', 'RESEND_API_KEY', 'EMAIL_FROM', 'PLATFORM_HEALTH_EMAIL', 'WEB_BASE_URL')
THREAD_PREFIX = 'claude-bot:'

@dataclass(frozen=True)
class Settings:
    home: Path; repo: Path; env_file: Path; python: Path; claude: Path; git_bash: Path
    launcher: Path | None = None      # opcional en config.json; None → home/'launcher' (__post_init__)
    ssh_host: str = 'automotive-vps'
    vps_hostname: str = 'vps-6488403-x'
    vps_root: str = '/opt/automotive'
    owner: str = 'claude-repair-bot'
    model: str = 'opus'; effort: str = 'high'; max_turns: int = 150
    claude_timeout_s: int = 2700
    max_attempts: int = 3; max_sessions_per_day: int = 6
    retry_delays_s: tuple[int, ...] = (1800, 7200, 21600)
    verify_timeout_s: int = 1500; wait_idle_s: int = 300
    max_diff_lines: int = 400; max_probes: int = 8
    allowed_paths: tuple[str, ...] = ('worker/collectors/', 'worker/tests/', 'worker/http_clients.py')
    enabled: bool = True
    @property state_dir / runs_dir  # home/'state', home/'runs'

def load(path: Path | None = None) -> Settings   # REPAIRBOT_CONFIG o C:/automotive-bot/config.json; claves desconocidas → error
def load_env(settings) -> None                    # dotenv_values(env_file); solo ENV_KEYS → os.environ
def child_env(settings, run_id: str) -> dict[str, str]   # entorno en lista blanca para Claude (ver abajo)
```

`child_env`: solo `SystemRoot, WINDIR, USERPROFILE, HOMEDRIVE, HOMEPATH, APPDATA, LOCALAPPDATA,
TEMP, TMP, USERNAME, COMSPEC, PATH, PATHEXT, ProgramFiles, ProgramFiles(x86), ProgramData` del
proceso actual, más `DISABLE_AUTOUPDATER=1`, `CLAUDE_CODE_DISABLE_AUTO_MEMORY=1`,
`CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1`, `BASH_DEFAULT_TIMEOUT_MS=300000`,
`BASH_MAX_TIMEOUT_MS=900000`, `CLAUDE_CODE_GIT_BASH_PATH`, `GIT_TERMINAL_PROMPT=0`,
`GCM_INTERACTIVE=never`, `PYTHONDONTWRITEBYTECODE=1`, `PYTHONUTF8=1`, `TEST_DATABASE_URL=`,
`LLM_SMOKE=`, `REPAIRBOT_CONFIG`, `REPAIRBOT_RUN_ID`. Nunca `ANTHROPIC_*`, `CLAUDE_*` heredadas,
`CLAUDECODE` ni ninguna de `ENV_KEYS`.

### `state.py`

```python
@dataclass
class Attempt: n: int; run_id: str; started_at: str; finished_at: str | None = None
               outcome: str | None = None; root_cause: str = ''; summary: str = ''; commit: str | None = None
@dataclass
class IncidentState:
    incident_id: str; source: str
    phase: str = 'new'            # new | deployed | waiting | needs_input | done
    attempts: list[Attempt] = []
    retry_after: str | None = None
    deploy: dict | None = None    # {stage, commit, run_id, local, base, prev_head, deployed_at, targets: [int],
                                  #  require_found, verify_until, unknown_since, undo, revert}; ver "Etapas del deploy"
class Store:
    def __init__(self, state_dir: Path)
    def load(self, incident_id) -> IncidentState | None
    def save(self, state) -> None          # escritura atómica (tmp + os.replace)
    def all_open(self) -> list[IncidentState]   # phase no 'done'
    def event(self, kind: str, **data) -> None  # agrega a events.jsonl con ts UTC
    def sessions_today(self) -> int        # eventos 'claude_run' del día local
class Lock:  # context manager; acquire() -> bool, no bloqueante
```
Fechas en ISO-8601 UTC. `Store` tolera archivos corruptos (los renombra `.bad` y devuelve None).

### `guard.py`

Script autónomo (solo stdlib; se ejecuta `python -I guard.py --root <clon> --python <intérprete> --log <archivo>`),
hook `PreToolUse` para `Bash|Read|Edit|Write|Glob|Grep` y cualquier otra herramienta. Lee el JSON
del hook por stdin; sale 0 para permitir y 2 (motivo en stderr) para bloquear. También expone
`decide(tool_name: str, tool_input: dict, root: Path, python: Path) -> str | None` (None = permitir).
Ante cualquier excepción o entrada que no entiende: **bloquea**.

- Herramientas que no sean Bash/Read/Edit/Write/Glob/Grep/StructuredOutput → bloqueadas.
- Rutas (Read/Edit/Write/Glob/Grep): resueltas contra `cwd`; deben quedar dentro de `root`. Edit/Write además solo en `allowed_paths` (misma lista que `Settings`, pasada con `--allow` repetido). Bloqueados en cualquier herramienta los nombres: `.env*`, `.git/` (escritura), `.ssh`, `.claude`, `credentials`, `*_state.json`, `*chrome_profile*`, `id_*`, `*.pem`, `*.key`.
- Bash: se rechaza si contiene `` ` ``, `$(`, `<(`, `>(`, `eval`, `exec`, redirección a archivos fuera de `root`, o here-docs. Se separa por `&&`, `||`, `;`, `|`, saltos de línea; **cada** segmento debe coincidir con la lista permitida:
  - `cd <ruta dentro de root>`, `pwd`, `ls`, `cat`, `head`, `tail`, `wc`, `grep`, `rg`, `find` (sin `-exec/-delete`), `sed -n`, `diff`, `sort`, `uniq`, `echo`, `true` — con argumentos de ruta dentro de `root`.
  - `git` solo `status|diff|log|show|blame|ls-files|rev-parse|branch --show-current|add|restore|stash list` (sin `-C`, `-c`, `--git-dir`, `--work-tree`); `restore` sin `-s`/`--source`, con rutas solo dentro de `allowed_paths` (misma regla que Edit/Write).
  - `<python>` (ruta exacta configurada, o `python` a secas) solo como `-m pytest ...`, `-m py_compile ...`, `-m tools.repro_target ...`, `-m repairbot.vps (status|logs|probe) ...`. Nada de `-c`, scripts sueltos ni `-m pip`.
  - Cualquier otro programa (ssh, scp, curl, wget, powershell, cmd, node, npm, rm, mv, cp fuera de root, chmod, taskkill, schtasks, reg, net, …) → bloqueado.
- Cada decisión se agrega a `--log` (herramienta, veredicto, motivo, comando truncado a 300 caracteres).

### `claude_runner.py`

```python
OUTPUT_SCHEMA: dict   # ver "Salida de Claude"
@dataclass
class RunResult:
    ok: bool; reason: str        # success | timeout | guard_inactive | init_mismatch | max_turns | error | rate_limited | no_output
    output: dict | None; session_id: str; num_turns: int = 0; cost_usd: float = 0.0
    denials: int = 0; rate_limit: dict | None = None; detail: str = ''
def preflight(settings, runner=subprocess.run) -> str | None      # `claude auth status --json`; None si loggedIn
def build_settings_file(settings, run_dir: Path) -> Path          # JSON con permissions + hooks; lo valida antes de escribir
def build_args(settings, session_id: str, settings_file: Path, system_prompt_file: Path) -> list[str]
def run_claude(settings, *, prompt: str, system_prompt: str, session_id: str, run_dir: Path,
               deadline_s: int | None = None, popen=subprocess.Popen) -> RunResult
```
- Args: `-p --output-format stream-json --verbose --include-hook-events --session-id <uuid> --model <model> --effort <effort> --setting-sources "" --settings <file> --strict-mcp-config --disable-slash-commands --tools Bash,Read,Edit,Write,Glob,Grep --permission-mode dontAsk --append-system-prompt-file <file> --json-schema <schema> --max-turns <n>`. Prompt por stdin (UTF-8) y stdin cerrado. cwd = `repo`. Entorno = `child_env`. `creationflags = CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW` en Windows.
- Settings generados: `permissions.allow` = `Read`, `Glob`, `Grep`, `Edit`, `Write`, `Bash`; `permissions.deny` con los patrones obvios (`Bash(git push:*)`, `Bash(ssh:*)`, `Bash(curl:*)`, `PowerShell`, `WebFetch`, `WebSearch`, `Task`); hooks `SessionStart` (imprime `REPAIRBOT_GUARD_ACTIVE <run_id>`) y `PreToolUse` (matcher `.*` → `guard.py`). El guard decide; `allow` amplio existe solo para que `dontAsk` no niegue lo que el guard permite.
- **Fail-closed**: un settings inválido se ignora en silencio en `-p`. Por eso el lanzador lee el stream y **mata el proceso** si antes del evento `system/init` no vio un `hook_response` de `SessionStart` con el canario, o si `init` no muestra `permissionMode == 'dontAsk'`, `mcp_servers == []` y exactamente las herramientas esperadas (+`StructuredOutput`). Resultado `guard_inactive` / `init_mismatch`.
- Tope de reloj: al vencer, `taskkill /PID <pid> /T /F` (árbol completo). Resultado `timeout`.
- Guarda `stream.jsonl` y `stderr.log` en `run_dir`. Lee `structured_output` del evento `result`; `subtype == 'error_max_turns'` → `max_turns`; `rate_limit_event` con estado distinto de `allowed` y sin resultado → `rate_limited`.

### `gitops.py`

```python
class GitError(RuntimeError)
def sync(repo: Path) -> str                      # fetch; checkout -B main origin/main; reset --hard; clean -fdx (solo en el clon del bot); devuelve sha
def changed_paths(repo: Path) -> list[str]       # modificados + sin seguimiento, con '/' como separador
def diff_lines(repo: Path) -> int                # agregadas + quitadas (incluye archivos nuevos)
def scope_violations(paths: list[str], allowed: tuple[str, ...]) -> list[str]
def commit(repo: Path, message: str) -> str      # add -A + commit; devuelve sha
def push(repo: Path) -> str                      # fetch; si origin/main avanzó: rebase (conflicto → abort + GitError); push origin HEAD:main; devuelve sha final
def revert(repo: Path, sha: str, message: str, *, run_id: str | None = None) -> str   # agrega 'Repair-Revert: <sha completo>' (y 'Repair-Run' con run_id)
def landed(repo: Path, run_id: str, *, reverts: str | None = None) -> str | None     # fetch; sha en origin/main del arreglo del run (o de su revert), o None
def update_launcher(path: Path, *, settings=None) -> str   # fetch + merge --ff-only en el clon del lanzador; devuelve HEAD
def commit_message(source: str, summary: str, root_cause: str, incident_id: str, run_id: str) -> str
```
`sync` se niega a operar (GitError) si `repo` no es exactamente `Settings.repo` o si su `origin` no es
el remoto de GitHub esperado: es la única función destructiva. Mensaje de commit:
`fix(<source>): <summary>` + causa + `Repair-Incident: <uuid>` + `Repair-Run: <run_id>` +
`Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Push con `GIT_TERMINAL_PROMPT=0`.

- `push` publica exactamente un commit nuevo encima de `origin/main`: si después del rebase HEAD no
  tiene a `origin/main` como único padre (el rebase lo vació porque `main` ya tenía el cambio, o no
  había nada nuevo), GitError sin pushear. **Un GitError de `push` no significa que no llegó** (la
  respuesta se pudo perder): el llamador pregunta a `landed` antes de darlo por fallido.
- `landed` reconoce los commits por líneas exactas del mensaje: el arreglo tiene `Repair-Run: <run_id>`
  y ninguna `Repair-Revert:`; su revert tiene las dos (`reverts` = sha completo del arreglo). Un fetch
  fallido es GitError: el resultado es desconocido y se reintenta en otro tick.
- `update_launcher` solo hace fast-forward y nunca resetea ni limpia: se niega (GitError `lanzador: ...`)
  si el clon es `Settings.repo` o está dentro de él, contiene el `.env`, no es un clon propio (un
  worktree o una subcarpeta), tiene otro `origin`, cambios locales o commits que no están en `origin/main`.

### `vps.py`

```python
class VpsError(RuntimeError)
def ssh(settings, script: str, *, timeout: int = 60, stdin: bytes | None = None, runner=subprocess.run) -> str
    # ssh -o BatchMode=yes -o ConnectTimeout=15 <host> bash -s  (script por stdin; salida != 0 → VpsError saneado)
def status(settings, **kw) -> dict        # {hostname, head, dirty: [paths], worker_active: bool, watchdog_active: bool}
def logs(settings, source: str, minutes: int = 180, max_lines: int = 150, **kw) -> str   # journalctl del worker filtrado por la fuente, saneado con safe_text
def probe(settings, repo: Path, source: str, *, target_id: int | None, filters: dict | None,
          run_id: str, timeout: int = 420, **kw) -> dict
def deploy(settings, sha: str, base: str, **kw) -> dict   # {ok, code, reason, prev_head, head, contains}; ver "Deploy"
    # code: deployed | already (ok) | dirty | pending_changes | wrong_host | missing_commit | not_on_main |
    #       moved | ff_failed | head_mismatch | py_compile | ssh_error | unknown_state
def restart_worker(settings, **kw) -> dict                # {ok, active}
def cleanup(settings, run_id: str, **kw) -> None
def main(argv=None) -> int   # CLI para Claude: SOLO `status`, `logs <source>`, `probe <source> [--target-id N] [k=v ...]`; imprime JSON
```
- `probe`: comprueba `scope_violations(changed_paths(repo))` y el contador de probes del intento
  (`runs/<run_id>/probes`, tope `max_probes`); empaqueta `worker/` del clon (sin `tests/`, `__pycache__`)
  con `tar` y lo extrae en `/opt/automotive/.repairbot/<run_id>/worker` como `automotive`; ejecuta ahí
  `python -m tools.repro_target ... --json` con `DISPLAY=:99`, `XAUTHORITY`, y rutas absolutas
  `FB_STORAGE_STATE`, `INSTAGRAM_STORAGE_STATE`, `ML_BROWSER_PROFILE_DIR` a los archivos reales.
  El código probado es siempre el del clon (sin cambios = el desplegado; con cambios = candidato).
  `mercadolibre` no se prueba así (el worker tiene tomado el perfil de Chrome): devuelve
  `{"supported": false, "reason": ...}`.
- `run_id` y nombres de fuente se validan con `^[A-Za-z0-9_-]{1,64}$` antes de entrar a un script remoto.
  Los scripts remotos usan `set -euo pipefail`.
- El CLI no expone `deploy`, `restart_worker` ni `cleanup`.

### `queue.py` (async, sobre `db`)

```python
async def active_incidents(cx) -> list[dict]
async def claim(cx, owner) -> dict | None                # db.repos.collector_repairs.claim
async def attach(cx, incident_id, token, thread) -> bool
async def needs_input(cx, incident_id, note) -> bool
async def incident_context(cx, incident: dict) -> dict   # tools.collector_repairs.build_context
async def failing_targets(cx, source: str, limit: int = 5) -> list[int]   # targets monitoreados cuya última corrida terminada es 'failed' (aunque haya un reintento en curso) o cuya última lleva >30 min 'running'
async def running_runs(cx, source: str) -> int           # corridas 'running' de los últimos 30 min
async def kick(cx, source: str, target_ids: list[int]) -> list[int]       # UPDATE crawl_targets SET next_run_at = now() ... RETURNING id
async def runs_since(cx, source: str, target_ids: list[int], since: datetime) -> list[dict]
```

### `tools/collector_repairs.py` (cambios)

- `build_context(incident, health, targets, runs) -> dict` extraído de `build_dispatch` (que lo usa; su salida y los tests actuales no cambian).
- `safe_text`: la redacción de `token=`, `cookie:` etc. pasa a ser **por línea** (hoy borra todo el resto del texto, incluida la excepción final). Los tests existentes siguen pasando.
- `json_text`: escapar `<` y `>` (`\u003c`, `\u003e`) para que un error no pueda cerrar `</incident_context>`.
- Docstring del módulo: la cola la consume el bot (`repairbot`), no Codex.

### `tools/repro_target.py` (nuevo)

Reproduce una búsqueda **sin ingesta**: nunca escribe corridas, avisos ni `geocode_cache`.

```
python -m tools.repro_target <source> [--target-id N] [--no-db] [--json] [--limit-sample 5] [k=v ...]
```
- `--target-id N`: lee (SELECT) el target y arma los filtros como el scheduler (`pipeline.crawl.scraper_filters` + fechas de publicación conocidas). Sin `--target-id`, usa los `k=v`.
- `--no-db`: no abre el pool (incompatible con `--target-id`).
- Salida JSON: `{source, target_id, found, complete, reason, unknown_dates, seconds, error_type, error, sample: [{id, title, price, url}]}`; `error` pasa por `safe_text`.
- Códigos de salida: 0 ok, 2 incompleta, 3 `CollectorBlocked` (login/captcha/sesión), 4 red/HTTP 5xx/timeout, 1 otro error.
- Siempre cierra los navegadores (`collectors._browser.shutdown`).

### `notify.py`

```python
def send(settings, *, incident_id: str, source: str, kind: str, subject: str, text: str, n: int = 0, sender=None) -> bool
```
`kind`: `fixed | needs_input | gave_up | rollback | deploy_blocked | bot_error | unverified`. Usa
`tools.platform_health.send_email` con `Idempotency-Key = repairbot-<incident>-<kind>-<n>`.
Nunca levanta: un fallo de correo se registra y devuelve False.

### `prompt.py`

```python
def system_prompt(settings) -> str
def task_prompt(context: dict, state: IncidentState, journal: str, settings) -> str
```
En castellano rioplatense como el resto del repo. La política vive en el system prompt; el
contexto va entre `<incident_context>` con `json_text`.

### `bot.py` y `__main__.py`

```python
@dataclass
class Deps: ...    # fachada inyectable: db, claude, git, vps, notify, clock
def tick(settings, deps=None, *, dry_run: bool = False) -> dict   # resumen JSON del tick
```
`python -m repairbot [--dry-run] [--once] [--status]`. `--dry-run` no reclama, no escribe en la
base, no corre Claude, no toca git ni el VPS: informa qué haría. `--status` imprime incidentes y
estado local. Código de salida 0 salvo error interno (2). Log rotativo en `state\bot.log`.

## Salida de Claude (`OUTPUT_SCHEMA`)

```json
{"outcome": "fixed | external | needs_human | recovered | no_fix",
 "root_cause": "string", "summary": "string, una oración para el dueño",
 "evidence": "string", "human_action": "string (si needs_human)",
 "tests": "string", "retry_in_minutes": 0}
```
Todos requeridos salvo `human_action` y `retry_in_minutes`.

## Pruebas

Unitarias sin red ni base para cada módulo (`worker/tests/test_repairbot_*.py`,
`test_repro_target.py`): guard (tabla de casos permitidos/bloqueados, incluidos intentos de
evasión), runner (un "claude" falso que emite stream-json: éxito, sin canario, init distinto,
timeout con árbol de procesos, max-turns), gitops (repos temporales con `git init`, incluido el
rechazo de `sync` fuera del clon), vps (runner falso; validación de argumentos), state/lock,
bot (máquina de estados completa con `Deps` falsos: fixed→deployed→verificado, rollback,
external→retry, agotado→needs_input, adopción, tope diario, dry-run). Las consultas nuevas de
`queue.py` llevan tests `db` con el patrón de `test_collector_repairs_postgres.py`.

## Operación

- `ops/install-repairbot.ps1`: crea el home, los dos clones (`repo\` y `launcher\`, separados, sin el `.env` y con `.git` como carpeta) y `config.json` solo si falta (con `launcher`; uno existente decide las rutas); registra `\AutoMotive\RepairBot` con `WorkingDirectory` `<launcher>\worker` (cada 5 min, usuario actual, interactivo, `MultipleInstances IgnoreNew`, límite 90 min). `ops/uninstall-repairbot.ps1` la quita.
- Pausar: `"enabled": false` en `config.json` o deshabilitar la tarea. Los incidentes siguen acumulándose en Postgres.
- `docs/COLLECTOR_REPAIR.md` se reescribe para el bot.

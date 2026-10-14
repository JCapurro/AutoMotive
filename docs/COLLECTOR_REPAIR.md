# Reparación automática de collectors

El dueño autorizó el 9/10/2026 diagnóstico, corrección y despliegue automáticos cuando un collector entra en **Revisar**. Desde el 13/10/2026 lo hace un bot propio (`worker/repairbot/`) que corre en **esta PC**: una tarea programada cada 5 minutos, `claude -p` con la suscripción del dueño, **push directo a `main`** y deploy en el VPS. Reemplaza a la automatización de Codex sobre la misma cola. El diseño completo está en `docs/superpowers/specs/2026-10-13-repair-bot-design.md`.

## Qué dispara un incidente

La fuente es `platform_health_checks`, el mismo snapshot privado de `/app/health`. El chequeo considera fallos repetidos del target, corridas trabadas, búsquedas vencidas y corridas sin resultados después de obtener avisos. Los fallos de base, web y heartbeat del worker conservan sus avisos existentes y no abren incidentes de collectors.

El chequeo incluye los targets de inventario compartido (`query.inventory=true`, sin marca/modelo), siempre que un perfil con acceso activo seleccione esa fuente. Esto cubre Only Cars Usados, SC Clasificados y los otros catálogos completos, con la misma elegibilidad que el scheduler.

En Mercado Libre y Facebook, una corrida exitosa sin avisos dentro de la ventana de publicaciones recientes no dispara un error de parser. Los fallos, corridas trabadas y búsquedas vencidas siguen alertando.

`collector_repair_incidents` tiene RLS y no permite lectura ni escritura desde los roles del navegador. Una fuente tiene un solo incidente sin resolver. Cambiar el error no abre otro incidente. Un snapshot fresco que vuelve a OK lo resuelve; retirar la fuente del monitoreo lo cancela. Snapshots vencidos, problemas de base y corridas iniciadas no confirman recuperación. Los incidentes se registran en Postgres desde el chequeo del VPS aunque la PC esté apagada; el bot los toma cuando vuelve.

## Quién hace qué

El modelo lee datos no confiables (errores de corridas, HTML de terceros), así que **solo diagnostica y edita código de collectors**. Todo lo que tiene efecto afuera lo hace el lanzador (`python -m repairbot`) con código determinístico:

| Acción | Quién |
| --- | --- |
| Leer el repo; editar `worker/collectors/**`, `worker/tests/**`, `worker/http_clients.py` | Claude |
| Correr pytest, `tools.repro_target` sin ingesta y `repairbot.vps status/logs/probe` | Claude, solo con los comandos que deja pasar el guard |
| Reclamar incidentes, escribir en la base, commit, push, deploy, reinicio, rollback, email | Lanzador |

## El ciclo (cada 5 minutos)

1. Lock de instancia única (`state\bot.lock`). Si otra instancia corre, sale sin hacer nada. Con `"enabled": false` en `config.json` no hace nada más que el último paso.
2. Carga del `.env` del checkout principal **solo** `DATABASE_URL`, `RESEND_API_KEY`, `EMAIL_FROM`, `PLATFORM_HEALTH_EMAIL` y `WEB_BASE_URL`.
3. Lee los incidentes activos. Los estados locales cuyo incidente ya se cerró pasan a `done`, después de cerrar lo que hubiera en curso (ver "Publicación, verificación y rollback"). Para cada incidente del bot (`thread_id` `claude-bot:<run_id>`):
   - **desplegado**: verifica sin Claude (ver abajo);
   - **en espera** con `retry_after` vencido e intentos disponibles: queda para un intento;
   - **intentos agotados** (3 por defecto): `needs_input` en la cola y email "me rendí";
   - **sin estado local** (se perdió `state\`): lo adopta con un intento consumido;
   - en `needs_input` en la base: no lo toca, lo tiene una persona.
4. Si no hay un intento pendiente, reclama el incidente pendiente más viejo (dueño `claude-repair-bot`, solo con un snapshot de salud fresco) y lo asocia en el acto; queda `open` y nadie más lo toma.
5. Como máximo **una sesión de Claude por tick** y 6 por día. Después de un límite de uso de la suscripción no abre sesiones hasta que se libera.
6. Al final de cada tick (también si falló o está pausado; nunca con `--dry-run`) avanza el clon del lanzador (`launcher\`) a `origin/main`, solo por fast-forward: el tick siguiente corre el código nuevo de `main`. Si no puede (cambios o commits locales en ese clon, otro `origin`, GitHub sin respuesta), sigue con el código que tenía, lo anota en `state\bot.log` y manda un `bot_error` "no se actualizó el lanzador" como máximo una vez por día, aparte de los otros errores.

Mientras corre un tick, la PC no entra en suspensión por inactividad (cerrar la tapa la suspende igual).

## Un intento

1. `git` deja el clon del bot igual a `origin/main`. Consulta el VPS (si no responde, Claude igual diagnostica, pero no habrá deploy).
2. Prompt = política (system) + contexto saneado del incidente + intentos previos + journal del worker para esa fuente. Todo lo que viene de la base, de las corridas o del VPS va en bloques cercados como datos no confiables.
3. `claude -p` con guard, canario, tope de turnos y tope de reloj (45 minutos). Termina con una salida estructurada:

| `outcome` | Qué hace el lanzador |
| --- | --- |
| `fixed` | Compuertas → commit → push a `main` → deploy → reinicio → verificación. Si algo falla, nada queda publicado sin revertir. |
| `external` | Sitio caído o 5xx temporal: espera (`retry_in_minutes` acotado entre 15 minutos y 24 horas; si no viene, 30 min / 2 h / 6 h) y reintenta. |
| `needs_human` | Captcha, sesión o credenciales vencidas, bloqueo, o un arreglo fuera del alcance: `needs_input` con la acción concreta + email. |
| `recovered` | La fuente ya anda: `done`; el monitor cierra el incidente. Si una hora después sigue abierto, se reabre. |
| `no_fix`, error, timeout | Intento fallido; reintento a los 30 min / 2 h / 6 h. |

Todo intento que no llega a pushear (cualquier `outcome` salvo un `fixed` publicado, también un error o un límite de uso) termina con un `sync` del clon de Claude: lo que dejó la sesión se descarta en el acto, no en el intento siguiente.

### Compuertas antes de publicar (las corre el lanzador, no Claude)

- Hay cambios, y todos dentro de `worker/collectors/`, `worker/tests/` o `worker/http_clients.py`.
- Un arreglo de código trae prueba de regresión (algún cambio en `worker/tests/`).
- Diff de 400 líneas como máximo (un binario cuenta como 10.000).
- Todos los `.py` cambiados compilan.
- La suite completa sin base (`python -m pytest -q -p no:cacheprovider -m "not db"` desde `worker/`, tope 15 minutos) pasa, con un entorno sin secretos, y no deja archivos nuevos.
- El VPS responde, es el host esperado y su checkout no tiene cambios sin commitear. Si no, no se pushea nada.

### Publicación, verificación y rollback

- Commit `fix(<fuente>): <resumen>` con `Repair-Incident` y `Repair-Run`, push a `origin/main` (con rebase si `main` avanzó; un conflicto es un intento fallido). Un push que da error puede haber llegado igual (la respuesta se perdió): el bot busca en `origin/main` el commit con el `Repair-Run` del intento. Si está, sigue con el deploy; si no, el intento es `publish_failed`; si GitHub no contesta, vuelve a mirar en el próximo tick (y avisa con `bot_error`).
- Deploy: en el VPS, como `automotive`, `git fetch` + `merge --ff-only` del commit + `py_compile` de lo cambiado. Si el VPS ya contiene el commit (está en él o en un commit posterior de `main`), no toca nada y sigue (`already`). Si el VPS tiene commits de `main` sin desplegar que tocan `worker/` o `supabase/`, se niega. Nunca `reset --hard`, `checkout --` ni `clean` en el VPS.
- Si el deploy no se puede hacer, el commit se revierte en `main` en el acto, y también en el VPS cuando el VPS ya lo tenía: `main` nunca queda adelantado a lo desplegado sin avisar. Un rechazo que necesita una persona (checkout sucio, cambios pendientes, host equivocado) termina en `needs_input` + email `deploy_blocked`; si el VPS ya tenía el arreglo (checkout sucio sobre ese commit), no se revierte nada y el worker no se reinicia.
- Si la respuesta del deploy se pierde y el VPS tampoco contesta después en qué commit quedó (`unknown_state`), el bot **no revierte a ciegas**: vuelve a desplegar en los ticks siguientes (si el commit ya está, sigue) y, pasados 25 minutos sin confirmarlo, deja `needs_input` + `deploy_blocked` sin revertir. Lo mismo cuando un tick retoma un deploy cortado y el VPS no responde.
- Espera hasta 5 minutos a que no haya corridas en curso de esa fuente y recién ahí elige los targets fallidos: los que tienen su última corrida terminada en `failed` (aunque ya tengan un reintento en curso) o una corrida trabada. Reinicia el worker, comprueba que quede estable y los "patea" (`next_run_at = now()`): las corridas posteriores ya usan el código nuevo. Sin targets fallidos (parser sin avisos, búsqueda vencida) patea hasta 5 targets activos y exige que traigan avisos.
- Verificación: una corrida `ok` posterior al deploy en cada target pateado → **verificado** + email. Una corrida `failed` → **rollback** (revert + push + deploy + reinicio) + email, y el intento cuenta como fallido. Sin corridas concluyentes en 25 minutos → **sin verificar** + email (no se revierte; se reintenta con el arreglo puesto). La verificación sigue hasta 10 minutos dentro del mismo tick y continúa en los siguientes.
- Si el monitor cierra el incidente antes, cuenta como **verificado** (`fixed`) solo si cada target pateado tuvo una corrida `ok` (con avisos, si se exigían) después del deploy; si no, queda **sin verificar** + email `unverified`. Patear una búsqueda vencida alcanza para que el monitor deje de verla, aunque todavía no haya corrido.
- Cada paso queda en `state\<incidente>.json` antes de hacerse (`deploy.stage`: `pushing` → `pushed` → `live`; para deshacer, `reverting` → `reverted`). Si el tick se corta (límite de 90 minutos, reinicio, suspensión), el siguiente lo retoma: confirma el push, hace el deploy o termina el revert (deploy del revert, reinicio si el arreglo había quedado andando y el email `rollback` o `deploy_blocked`). Un revert también se busca por su `Repair-Run` antes de repetirlo. Si el monitor cierra el incidente con un revert a medias, el bot lo termina igual y nunca lo informa como `fixed`.

## Modelo de seguridad

- **Claude no tiene secretos**: su entorno es una lista blanca, sin `DATABASE_URL` ni claves; tampoco `git push`, `ssh` libre, red propia ni PowerShell.
- **Guard** (`worker/repairbot/guard.py`, hook `PreToolUse` de todas las herramientas): lista permitida, bloquea por defecto y ante cualquier duda. Lecturas solo dentro del clon; escrituras solo en el alcance permitido; Bash solo con los programas y opciones listados. Los hooks corren una copia del guard fuera del clon.
- **El lanzador no corre el clon de Claude**: la tarea corre desde `launcher\worker`, un clon aparte que el guard no deja leer ni editar a la sesión y que solo avanza por fast-forward a `main`. Lo que deja una sesión sin revisar nunca se importa en el proceso que tiene las claves.
- **Fail-closed**: `claude -p` ignora en silencio un settings inválido, así que el lanzador mata la sesión si antes de `init` no vio el canario del guard, o si `init` no muestra `dontAsk`, ninguna MCP y exactamente las herramientas pedidas.
- **Compuertas y rollback** (arriba) son la segunda línea. Cada deploy termina en un email, y también cada rechazo o rendición.
- `vps.probe` lleva al VPS solo código dentro del alcance permitido y lo corre como `automotive`, sin ingesta, con tope de 8 probes por intento.

## Dónde vive cada cosa

- `C:\automotive-bot\` (fuera del checkout del dueño):
  - `config.json`: configuración sin secretos (rutas, topes, `enabled`). Una clave desconocida es un error. `launcher` es opcional: sin ella, el clon del lanzador es `<home>\launcher`.
  - `repo\`: clon de GitHub donde trabaja Claude. Se resetea a `origin/main` antes de cada intento y después de uno que no publicó nada: no editarlo a mano.
  - `launcher\`: otro clon de GitHub, el código que corre la tarea programada. El bot lo avanza a `main` al final de cada tick y nunca lo resetea: no editarlo a mano (con cambios locales deja de actualizarse y avisa).
  - `state\`: `<incidente>.json` (fase, intentos, deploy), `events.jsonl` (reclamos, sesiones, errores, límites), `bot.log` (rotativo, 2 MB × 5), `bot.lock` y `bot-bootstrap.log` (lo que falla antes de que exista `bot.log`).
  - `runs\<run_id>\`: `prompt.md`, `system_prompt.md`, `settings.json`, `guard.py`, `guard.log`, `stream.jsonl`, `stderr.log` y `probe-<n>.json`.
- VPS: staging de probes en `/opt/automotive/.repairbot/<run_id>/`, ignorado por git y borrado al final de cada intento.

## Instalar y activar

1. Incorporar `worker/repairbot/` y `worker/tools/repro_target.py` a `main`: el bot corre el código de `main` desde su clon del lanzador.
2. `claude auth status` tiene que decir `loggedIn` con el `claude.exe` nativo (no el `.cmd`).
3. `ssh -o BatchMode=yes automotive-vps true` tiene que andar sin contraseña.
4. Desde la raíz del checkout principal: `powershell -ExecutionPolicy Bypass -File ops\install-repairbot.ps1` (parámetros `-BotHome`, `-Python`, `-EnvFile`, `-Claude`, `-GitBash`). Es idempotente: crea el home y los dos clones (`repo\` y `launcher\`, carpetas separadas y sin el `.env`), copia `user.name`/`user.email` al de Claude, escribe `config.json` solo si no existe (si existe, toma sus rutas) y registra `\AutoMotive\RepairBot` (cada 5 minutos, `pythonw -m repairbot --config ...` desde `launcher\worker`, límite de 90 minutos, sin instancias superpuestas). Una instalación anterior se actualiza corriéndolo otra vez: agrega `launcher\` y apunta la tarea ahí.
5. Probar sin efectos desde `C:\automotive-bot\launcher\worker`: `python -m repairbot --dry-run` y `python -m repairbot --status`.
6. Desactivar en Codex la automatización **Reparar collectors en Revisar**: las dos no pueden consumir la misma cola.

## Pausar y desinstalar

- Pausar: `"enabled": false` en `C:\automotive-bot\config.json`, o `Disable-ScheduledTask -TaskPath \AutoMotive\ -TaskName RepairBot`. Los incidentes se siguen acumulando en Postgres.
- Desinstalar: `ops\uninstall-repairbot.ps1` (solo quita la tarea; `C:\automotive-bot` queda).

## Leer lo que pasó

- `python -m repairbot --status`: incidentes activos (saneados), estado local y sesiones del día. `--dry-run`: qué haría el próximo tick.
- Cada tick deja una línea JSON en `state\bot.log`; el código de salida es 2 si hubo un error interno. Lo que falla antes de que exista ese log (un `config.json` roto, argumentos inválidos, un log que no se puede abrir) deja una línea con fecha en `<carpeta de config.json>\state\bot-bootstrap.log` (normalmente `C:\automotive-bot\state\`) o, si esa carpeta no se puede escribir, en `%LOCALAPPDATA%\repairbot\bot-bootstrap.log`.
- Emails (uno por incidente, tipo e intento): `fixed`, `rollback`, `unverified`, `needs_input`, `gave_up`, `deploy_blocked` y `bot_error` (como máximo uno por día). Cada deploy termina en exactamente uno de `fixed`, `rollback`, `unverified` o `deploy_blocked`.
- Resultado de cada intento en `state\<incidente>.json`: `verified`, `deployed` (esperando verificación), `rolled_back`, `unverified`, `gate_failed`, `publish_failed`, `deploy_blocked`, `external`, `needs_human`, `recovered`, `no_fix`, `timeout`, `max_turns`, `no_output`, `error`, `guard_inactive` / `init_mismatch` (configuración del guard: también manda `bot_error`), `rate_limited` (no consume intento) y `lost` (estado adoptado). `detail` tiene el motivo del lanzador.
- La cola a mano, desde `worker/` del checkout principal: `python -m tools.collector_repairs list` (también `context <uuid>` y `needs-input <uuid> --note "..."`). Estados: `pending`, `dispatching`, `open`, `needs_input`, `resolved`, `cancelled`.

## Cuando el bot pide una persona

- **`needs_input` / `gave_up`**: el email dice la acción (renovar la sesión de Instagram, resolver un captcha, un cambio fuera del alcance) o el historial de intentos. Al resolverlo, el monitor cierra el incidente cuando ve la fuente sana. Para devolvérselo al bot con un presupuesto nuevo de intentos, volver el incidente a `open` (SQL con el rol del worker):

  ```sql
  update collector_repair_incidents set status = 'open', note = null, updated_at = now()
  where id = '<uuid>' and resolved_at is null and status = 'needs_input';
  ```

- **`deploy_blocked`**: el VPS tiene parches en caliente, commits de `main` sin desplegar que tocan `worker/` o `supabase/`, o respondió otro host; un deploy quedó sin confirmar (`unknown_state`: no se sabe si el VPS tiene el arreglo, y el bot no lo revirtió); o un revert no se pudo hacer o desplegar solo. Mirar en qué commit está el VPS (`python -m repairbot.vps status`), commitear los parches en `main` o desplegar a mano (abajo) y después devolver el incidente como arriba. El email dice si quedó un commit del bot en `main` sin desplegar.
- **`bot_error`**: ver `state\bot.log`. Causas típicas: Claude Code sin sesión (`claude auth login`), VPS o GitHub inalcanzables (un push sin confirmar se vuelve a mirar solo en el próximo tick), `DATABASE_URL` ausente, el guard que no arrancó. Con el asunto "no se actualizó el lanzador": el clon `launcher\` tiene cambios o commits locales, u otro `origin`; dejarlo igual a `origin/main` a mano (`git -C C:\automotive-bot\launcher status`).

## Desplegar main a mano

```bash
# Como root (ssh automotive-vps). Git siempre como `automotive`, dueño del
# checkout: como root falla por "dubious ownership". `set -e` evita reiniciar
# el código viejo si la actualización falla.
set -e
G="sudo -u automotive -H git -C /opt/automotive"
$G fetch origin
test -z "$($G status --porcelain --untracked-files=no)"   # sin parches en caliente
$G merge --ff-only origin/main
test "$($G rev-parse HEAD)" = "$($G rev-parse origin/main)"
systemctl restart automotive-worker.service
systemctl status automotive-worker.service --no-pager
```

Si `status` muestra archivos modificados, son parches en caliente: commitearlos en `main` antes de desplegar. Nunca usar `git clean` en el VPS (borra `.env`, las sesiones `*_state.json`, `.ml_chrome_profile/` y `logs/`).

## Herramientas de la sesión

- `python -m tools.repro_target <fuente> [--target-id N] [--no-db] [--json] [--limit-sample 5] [--timeout 270] [k=v ...]`: una búsqueda sin ingesta (no escribe corridas, avisos ni `geocode_cache`). `--target-id` lee el target (solo lectura) y arma los filtros como el scheduler; `--no-db` no abre la base. Códigos: 0 ok, 2 incompleta, 3 bloqueada (login, captcha, sesión), 4 red / HTTP 5xx / timeout, 1 otro error.
- `python -m repairbot.vps status | logs <fuente> [--minutes N] [--lines N] | probe <fuente> [--target-id N] [k=v ...]`: lo único del VPS que ve Claude. `probe` solo corre dentro de un intento (`REPAIRBOT_RUN_ID`); declina las fuentes de `vps.UNSUPPORTED` (hoy ninguna). Este CLI no tiene `deploy`, `restart` ni `cleanup`.

## Riesgos residuales

- **No hay sandbox de sistema operativo** en Windows: el guard reduce el riesgo, no lo elimina. Un test escrito por el modelo corre con los permisos del usuario de Windows (sin las claves del bot en su entorno, pero puede leer y escribir archivos del usuario, el clon del lanzador incluido: si lo cambia, el lanzador deja de actualizarse y avisa, pero el código cambiado ya corre).
- **Push directo a `main`** sin revisión humana: un arreglo malo llega a producción y se revierte solo si una corrida posterior falla. Un arreglo "sin verificar" queda desplegado.
- **El probe es ejecución remota de código** dentro del alcance permitido, como `automotive` y con el `.env` de producción del VPS.
- **Inyección por datos de terceros**: el prompt cerca y marca los datos no confiables, pero un modelo puede equivocarse; las compuertas limitan qué puede salir de eso.
- **Verificación heurística**: una corrida fallida por otra causa (un 503 del sitio) provoca un rollback de más, y los targets de reemplazo (cuando no hay targets fallidos) pueden no ser los rotos.
- **Archivos sueltos**: Claude no puede borrar archivos, así que lo que deje dentro del alcance entra en el commit (y cuenta para el tope de líneas).
- Depende de que la PC esté prendida, de la suscripción de Claude y de que la automatización de Codex esté desactivada.

## Estado de activación

### 9/10/2026 (automatización de Codex)

- Migración `20261015120000` aplicada en producción; trigger habilitado y permisos privados verificados.
- Automatización **Reparar collectors en Revisar** activa en Codex cada cinco minutos.
- 53 pruebas pasaron y el flujo completo del CLI pasó en una base local aislada. Incluyen cobertura de inventarios y regresiones para ventanas de publicaciones recientes.
- Chequeo instalado y observado en el VPS a las 15:17 ART: 13 fuentes, incluyendo Only Cars Usados y SC Clasificados sanos. Se conservó el ajuste remoto para ventanas recientes; worker y timer continúan activos.
- Captura y despacho reales verificados con Autocity (tres fallos HTTP 403): incidente `a183b3b6-ae12-4bf1-add2-c2569ad64fa2`, chat `01a121e3-2fac-73a1-95d5-bd1d1f3e957f`, asociación persistida y diagnóstico iniciado. El incidente sigue abierto hasta observar recuperación real.

### 13/10/2026 (bot propio)

- Código del bot escrito en la rama `claude/repair-bot`: `worker/repairbot/` (lanzador, guard, sesión de Claude, git, VPS, estado, emails, prompt), `worker/tools/repro_target.py`, `ops/install-repairbot.ps1` y `ops/uninstall-repairbot.ps1`, con pruebas unitarias sin red ni base.
- **Activación pendiente**: falta incorporar la rama a `main`, correr las pruebas con base, verificar en vivo el stream de `claude -p`, el guard, ssh y el deploy, instalar la tarea y desactivar la automatización de Codex. Hasta entonces sigue el flujo de Codex del 9/10.

### 14/10/2026 (bot activo)

- En `main` desde `cd83a92`, y el VPS está en ese commit. La revisión adversarial confirmó 14 hallazgos y quedaron corregidos. El único aceptado es el de cerrar la tapa en medio de una sesión, que cuenta como intento. Hay 1981 pruebas sin base.
- Verificado en vivo:
  - con `claude -p` 2.1.278 y la suscripción Max: el canario aparece antes de `init`, `dontAsk` sin servidores MCP y exactamente las herramientas esperadas; el guard bloqueó `curl` y `git restore --source`, y con un settings inválido la corrida terminó `guard_inactive`;
  - `--status` y `--dry-run` contra producción en solo lectura;
  - las consultas nuevas sobre el esquema real (`EXPLAIN` para el `UPDATE`);
  - `vps.probe` en el VPS: Mardel Usados encontró 323 avisos, y Mercado Libre, target 7 por `--target-id`, 2 avisos completos;
  - un tick real desde el lanzador y la tarea programada con `pythonw` (resultado 0).
- Instalado con `ops\install-repairbot.ps1`: `C:\automotive-bot\repo`, `C:\automotive-bot\launcher` y la tarea `\AutoMotive\RepairBot` cada 5 minutos.
- Al activarlo no había incidentes abiertos: el de Mercado Libre (security challenge) se cerró a las 13:37, con el collector HTTP. El primer arreglo de punta a punta (Claude, push, deploy y verificación) va a ocurrir con el próximo incidente real; cada resultado llega por email.
- Pendiente del dueño: pausar la automatización **Reparar collectors en Revisar** en Codex.

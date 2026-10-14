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

1. Lock de instancia única (`state\bot.lock`). Si otra instancia corre, sale sin hacer nada. Con `"enabled": false` en `config.json`, también.
2. Carga del `.env` del checkout principal **solo** `DATABASE_URL`, `RESEND_API_KEY`, `EMAIL_FROM`, `PLATFORM_HEALTH_EMAIL` y `WEB_BASE_URL`.
3. Lee los incidentes activos. Los estados locales cuyo incidente ya se cerró pasan a `done` (si había un arreglo desplegado sin verificar, avisa la recuperación). Para cada incidente del bot (`thread_id` `claude-bot:<run_id>`):
   - **desplegado**: verifica sin Claude (ver abajo);
   - **en espera** con `retry_after` vencido e intentos disponibles: queda para un intento;
   - **intentos agotados** (3 por defecto): `needs_input` en la cola y email "me rendí";
   - **sin estado local** (se perdió `state\`): lo adopta con un intento consumido;
   - en `needs_input` en la base: no lo toca, lo tiene una persona.
4. Si no hay un intento pendiente, reclama el incidente pendiente más viejo (dueño `claude-repair-bot`, solo con un snapshot de salud fresco) y lo asocia en el acto; queda `open` y nadie más lo toma.
5. Como máximo **una sesión de Claude por tick** y 6 por día. Después de un límite de uso de la suscripción no abre sesiones hasta que se libera.

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
| `no_fix`, error, timeout | Intento fallido; reintento a los 30 min / 2 h / 6 h. Lo que quedó en el clon se descarta en el próximo `sync`. |

### Compuertas antes de publicar (las corre el lanzador, no Claude)

- Hay cambios, y todos dentro de `worker/collectors/`, `worker/tests/` o `worker/http_clients.py`.
- Un arreglo de código trae prueba de regresión (algún cambio en `worker/tests/`).
- Diff de 400 líneas como máximo (un binario cuenta como 10.000).
- Todos los `.py` cambiados compilan.
- La suite completa sin base (`python -m pytest -q -p no:cacheprovider -m "not db"` desde `worker/`, tope 15 minutos) pasa, con un entorno sin secretos, y no deja archivos nuevos.
- El VPS responde, es el host esperado y su checkout no tiene cambios sin commitear. Si no, no se pushea nada.

### Publicación, verificación y rollback

- Commit `fix(<fuente>): <resumen>` con `Repair-Incident` y `Repair-Run`, push a `origin/main` (con rebase si `main` avanzó; un conflicto es un intento fallido).
- Deploy: en el VPS, como `automotive`, `git fetch` + `merge --ff-only` del commit + `py_compile` de lo cambiado. Si el VPS tiene commits de `main` sin desplegar que tocan `worker/` o `supabase/`, se niega. Nunca `reset --hard`, `checkout --` ni `clean` en el VPS.
- Si el deploy no se puede hacer, el commit se revierte en `main` en el acto: `main` nunca queda adelantado a lo desplegado sin avisar. Un rechazo que necesita una persona (checkout sucio, cambios pendientes, host equivocado) termina en `needs_input` + email `deploy_blocked`.
- Espera hasta 5 minutos a que no haya corridas en curso de esa fuente, reinicia el worker, comprueba que quede estable y recién ahí "patea" los targets fallidos (`next_run_at = now()`): las corridas posteriores ya usan el código nuevo. Sin targets fallidos (parser sin avisos, búsqueda vencida) patea hasta 5 targets activos y exige que traigan avisos.
- Verificación: una corrida `ok` posterior al deploy en cada target pateado → **verificado** + email. Una corrida `failed` → **rollback** (revert + push + deploy + reinicio) + email, y el intento cuenta como fallido. Sin corridas concluyentes en 25 minutos → **sin verificar** + email (no se revierte; se reintenta con el arreglo puesto). La verificación sigue hasta 10 minutos dentro del mismo tick y continúa en los siguientes. Si el monitor cierra el incidente antes, cuenta como recuperado.
- Si el tick se corta entre el push y el deploy, el siguiente retoma el deploy.

## Modelo de seguridad

- **Claude no tiene secretos**: su entorno es una lista blanca, sin `DATABASE_URL` ni claves; tampoco `git push`, `ssh` libre, red propia ni PowerShell.
- **Guard** (`worker/repairbot/guard.py`, hook `PreToolUse` de todas las herramientas): lista permitida, bloquea por defecto y ante cualquier duda. Lecturas solo dentro del clon; escrituras solo en el alcance permitido; Bash solo con los programas y opciones listados. Los hooks corren una copia del guard fuera del clon.
- **Fail-closed**: `claude -p` ignora en silencio un settings inválido, así que el lanzador mata la sesión si antes de `init` no vio el canario del guard, o si `init` no muestra `dontAsk`, ninguna MCP y exactamente las herramientas pedidas.
- **Compuertas y rollback** (arriba) son la segunda línea. Cada deploy termina en un email, y también cada rechazo o rendición.
- `vps.probe` lleva al VPS solo código dentro del alcance permitido y lo corre como `automotive`, sin ingesta, con tope de 8 probes por intento. Mercado Libre no se prueba así (el worker tiene tomado su perfil de Chrome).

## Dónde vive cada cosa

- `C:\automotive-bot\` (fuera del checkout del dueño):
  - `config.json`: configuración sin secretos (rutas, topes, `enabled`). Una clave desconocida es un error.
  - `repo\`: clon dedicado de GitHub. Se resetea a `origin/main` antes de cada intento: no editarlo a mano.
  - `state\`: `<incidente>.json` (fase, intentos, deploy), `events.jsonl` (reclamos, sesiones, errores, límites), `bot.log` (rotativo, 2 MB × 5) y `bot.lock`.
  - `runs\<run_id>\`: `prompt.md`, `system_prompt.md`, `settings.json`, `guard.py`, `guard.log`, `stream.jsonl`, `stderr.log` y `probe-<n>.json`.
- VPS: staging de probes en `/opt/automotive/.repairbot/<run_id>/`, ignorado por git y borrado al final de cada intento.

## Instalar y activar

1. Incorporar `worker/repairbot/` y `worker/tools/repro_target.py` a `main`: el bot corre el código de `main` desde su clon.
2. `claude auth status` tiene que decir `loggedIn` con el `claude.exe` nativo (no el `.cmd`).
3. `ssh -o BatchMode=yes automotive-vps true` tiene que andar sin contraseña.
4. Desde la raíz del checkout principal: `powershell -ExecutionPolicy Bypass -File ops\install-repairbot.ps1` (parámetros `-BotHome`, `-Python`, `-EnvFile`, `-Claude`, `-GitBash`). Es idempotente: crea el home, clona, copia `user.name`/`user.email`, escribe `config.json` solo si no existe y registra `\AutoMotive\RepairBot` (cada 5 minutos, `pythonw -m repairbot --config ...`, límite de 90 minutos, sin instancias superpuestas).
5. Probar sin efectos desde `C:\automotive-bot\repo\worker`: `python -m repairbot --dry-run` y `python -m repairbot --status`.
6. Desactivar en Codex la automatización **Reparar collectors en Revisar**: las dos no pueden consumir la misma cola.

## Pausar y desinstalar

- Pausar: `"enabled": false` en `C:\automotive-bot\config.json`, o `Disable-ScheduledTask -TaskPath \AutoMotive\ -TaskName RepairBot`. Los incidentes se siguen acumulando en Postgres.
- Desinstalar: `ops\uninstall-repairbot.ps1` (solo quita la tarea; `C:\automotive-bot` queda).

## Leer lo que pasó

- `python -m repairbot --status`: incidentes activos (saneados), estado local y sesiones del día. `--dry-run`: qué haría el próximo tick.
- Cada tick deja una línea JSON en `state\bot.log`; el código de salida es 2 si hubo un error interno.
- Emails (uno por incidente, tipo e intento): `fixed`, `rollback`, `unverified`, `needs_input`, `gave_up`, `deploy_blocked` y `bot_error` (como máximo uno por día). Cada deploy termina en exactamente uno de `fixed`, `rollback`, `unverified` o `deploy_blocked`.
- Resultado de cada intento en `state\<incidente>.json`: `verified`, `deployed` (esperando verificación), `rolled_back`, `unverified`, `gate_failed`, `publish_failed`, `deploy_blocked`, `external`, `needs_human`, `recovered`, `no_fix`, `timeout`, `max_turns`, `no_output`, `error`, `guard_inactive` / `init_mismatch` (configuración del guard: también manda `bot_error`), `rate_limited` (no consume intento) y `lost` (estado adoptado). `detail` tiene el motivo del lanzador.
- La cola a mano, desde `worker/` del checkout principal: `python -m tools.collector_repairs list` (también `context <uuid>` y `needs-input <uuid> --note "..."`). Estados: `pending`, `dispatching`, `open`, `needs_input`, `resolved`, `cancelled`.

## Cuando el bot pide una persona

- **`needs_input` / `gave_up`**: el email dice la acción (renovar la sesión de Instagram, resolver un captcha, un cambio fuera del alcance) o el historial de intentos. Al resolverlo, el monitor cierra el incidente cuando ve la fuente sana. Para devolvérselo al bot con un presupuesto nuevo de intentos, volver el incidente a `open` (SQL con el rol del worker):

  ```sql
  update collector_repair_incidents set status = 'open', note = null, updated_at = now()
  where id = '<uuid>' and resolved_at is null and status = 'needs_input';
  ```

- **`deploy_blocked`**: el VPS tiene parches en caliente, commits de `main` sin desplegar que tocan `worker/` o `supabase/`, o respondió otro host; o un revert no se pudo hacer solo. Commitear los parches en `main` o desplegar a mano (abajo) y después devolver el incidente como arriba. El email dice si quedó un commit del bot en `main` sin desplegar.
- **`bot_error`**: ver `state\bot.log`. Causas típicas: Claude Code sin sesión (`claude auth login`), VPS o GitHub inalcanzables, `DATABASE_URL` ausente, el guard que no arrancó.

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
- `python -m repairbot.vps status | logs <fuente> [--minutes N] [--lines N] | probe <fuente> [--target-id N] [k=v ...]`: lo único del VPS que ve Claude. `probe` solo corre dentro de un intento (`REPAIRBOT_RUN_ID`) y declina `mercadolibre`. Este CLI no tiene `deploy`, `restart` ni `cleanup`.

## Riesgos residuales

- **No hay sandbox de sistema operativo** en Windows: el guard reduce el riesgo, no lo elimina. Un test escrito por el modelo corre con los permisos del usuario de Windows (sin las claves del bot en su entorno, pero puede leer archivos del usuario).
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

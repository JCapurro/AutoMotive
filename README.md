# AutoMotive

Monitorea publicaciones de autos usados en Argentina, detecta las que coinciden
con tus búsquedas, las prioriza con un Opportunity Score y te avisa por la web,
Telegram o email.

El plan del MVP (web + Supabase) está en [docs/TECHNICAL_PLAN.md](docs/TECHNICAL_PLAN.md);
cómo publicarlo para el piloto, en [docs/PILOT_SETUP.md](docs/PILOT_SETUP.md).
Estado: **F7 en curso** (puesta en producción del piloto; por ahora corre en local) — la web ([web/](web/README.md), Next.js + Supabase) es donde se
crean y editan las búsquedas, se ven los resultados, el detalle de cada
publicación (¿por qué apareció?, análisis de precio, histórico, red flags,
preguntas al vendedor), los estados, la watchlist y el inbox con Realtime. El
bot de Telegram ya no tiene wizard: vincula la cuenta (`/start <código>`) y
resuelve los botones de las alertas. Debajo siguen F1–F3: scraping por *crawl
target*, matching con razones y Opportunity Score, y el motor de
notificaciones. F5 suma el modo asistido con LLM, F6 el backoffice
(`/admin`), las métricas del piloto y el experimento de monetización, y F7
lo necesario para abrirlo a usuarios reales: páginas de privacidad y términos,
baja del email y borrado de cuenta, retención de datos y una base de tests
separada de la del piloto.

## Estructura

```
worker/       bot de Telegram, collectors, pipeline (Python, raíz de imports)
  collectors/     scrapers por fuente: search() y fetch_detail()
  normalization/  vehicle (catálogo + rapidfuzz), drafts (borradores del LLM), transmission, listing,
                  price_check, geo, fx
  intelligence/   matching, comparables, scoring, levels, red_flags, seller_questions (puros)
  pipeline/       crawl (targets + cadencia), ingest (upsert/snapshots/eventos),
                  enrich, watchlist, rematch, scoring, rescore, llm_jobs, scheduler (loop + alertas de Telegram)
  llm/            capa LLM (modo asistido): LLMProvider, claude_cli (claude -p), anthropic_api (API key), local (stub), schemas, prompts
  bot/            Telegram: /start <código> (vinculación) y botones de las alertas
  db/             psycopg 3 (pool async) + repos por tabla
  tools/          scraper_cli, migrate_sqlite, explain_match, rematch, simulate_alert, llm_jobs, record_llm,
                  test_db, watchdog, supabase_keys
  tests/
web/          Next.js (App Router) + @supabase/ssr + Tailwind/shadcn: landing, app, admin, /r/<id>, legales y /baja
ops/          el piloto en esta PC (F7): tareas programadas, supervisor, backup y actualización (docs/PILOT_SETUP.md)
supabase/     migraciones, seed.sql, templates de email y tests pgTAP (supabase CLI)
docs/         PRD y plan técnico
```

## Fuentes

| Fuente | Tipo | Notas |
|--------|------|-------|
| **MercadoLibre** | Playwright web + sesión | Mayor volumen. Requiere `ml_state.json` si aparece verificación |
| **Facebook Marketplace** | Headless browser + sesión | Particulares — donde aparecen las gangas. Requiere login una vez |
| **V6** | Headless browser | Particulares + concesionarias, fotos directas |
| **Kavak** | Headless browser | Inventario certificado, precios estables — buen anclaje para la mediana |
| **Autocosmos** | HTTP | Mayormente concesionarias; los avisos con solo "Anticipo" quedan como precio parcial |

La cadencia de cada fuente es `sources.crawl_interval_seconds` (ML 10 min,
Kavak/V6/Autocosmos 30 min, Facebook 60 min) y el ritmo de las fichas,
`sources.detail_interval_seconds`. Se editan en la base, sin deploy.
## Cómo funciona

1. Creás una búsqueda en la web (`/app/searches/new`): marca, modelo y versión
   del catálogo, años, precio máximo (USD o ARS), km, transmisión, combustible,
   zona + radio (o el preset AMBA), fuentes, preferencias blandas, frecuencia y
   nivel mínimo de alerta. Mientras la escribís ves cuántas publicaciones
   actuales coinciden. Un modelo por búsqueda (§13).
2. **Crawl targets** ([crawl.py](worker/pipeline/crawl.py)): en cada tick
   (`TICK_INTERVAL_SECONDS`, 5 min) las búsquedas habilitadas se agrupan por
   (fuente, marca, modelo) con el rango más amplio de años y km y **sin precio**.
   Dos usuarios que buscan el mismo modelo comparten un solo scrapeo. Un target
   corre cuando vence su `next_run_at`; las fuentes van en paralelo y los
   targets de una fuente en serie, con jitter (`CRAWL_JITTER_SECONDS`).
3. **Normalización v2**: marca/modelo/versión salen del título y los atributos
   contra `vehicle_catalog` (alias + `rapidfuzz`), no del filtro de búsqueda; si
   no se resuelven se usa el del target con `normalization_confidence` baja.
   También transmisión, combustible, tipo de vendedor y `price_usd` con la
   cotización del día, que queda congelada en `fx_rates`.
4. **Upsert canónico** ([ingest.py](worker/pipeline/ingest.py)): una fila por
   (fuente, id) con `first_seen_at` fijo; `listing_snapshots` solo cuando cambia
   precio, km, descripción, imágenes o atributos clave, y eventos
   `listing_new` / `listing_updated` / `price_drop` (baja ≥ `price_drop_min_pct`).
   Un aviso nuevo con el mismo *fingerprint* que otro de los últimos 60 días y
   precio ±10% se marca `probable_repost_of` y sale de los comparables.
5. **Bootstrap silencioso**: la primera corrida de un target, y una búsqueda
   nueva o editada (se matchea contra lo guardado de los últimos 30 días), quedan
   como *backfill*: no notifican — evita el diluvio inicial.
6. **Matching y alertas**: cada lote de un target se matchea contra las
   búsquedas de ese modelo (filtros con razones, radio con geocodificación,
   recencia `RECOMMENDED_MAX_AGE_DAYS` cuando la fuente expone la fecha) y se
   puntúa (ver *Matching y Opportunity Score*). Los matches nuevos y las bajas
   de precio pasan al motor de notificaciones
   ([notifications/](worker/notifications)), que decide según el nivel mínimo,
   la frecuencia, el tope diario y el dedupe, y envía por Telegram, email y el
   inbox web (o los junta en el digest diario). Lo ya visto no se re-notifica.
7. **Enrichment** ([enrich.py](worker/pipeline/enrich.py)): las publicaciones
   con al menos un match se completan con `fetch_detail()` (descripción,
   versión, transmisión, vendedor, todas las fotos), con una cola por fuente.
8. **Watchlist** ([watchlist.py](worker/pipeline/watchlist.py)): una vez por día
   se revisan las publicaciones guardadas o en seguimiento; si dan 404, están
   pausadas o vendidas pasan a `gone`.
9. **Observabilidad**: cada corrida queda en `collector_runs` (encontrados,
   nuevos, actualizados, error) y cada falla de normalización, ingesta,
   enrichment o notificación en `pipeline_errors`. Al arrancar, el worker
   loguea en `WARNING` cada canal o métrica que el `.env` deja apagado.
10. **Retención** ([retention.py](worker/pipeline/retention.py)): cada noche,
    después del re-score, se borran las publicaciones que no se ven hace
    `app_config.retention.listing_days` (180) y que ningún usuario tocó (sin
    interacción, alerta ni compra), con sus snapshots y matches.

## Setup

```powershell
cd C:\Users\Juan\Desktop\AutoMotive
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r worker\requirements.txt
python -m playwright install chromium
copy .env.example .env
# editá .env: TELEGRAM_TOKEN y DATABASE_URL
```

`.env`, `fb_state.json` y `ml_state.json` siguen en la raíz del repo. Los
comandos de Python se corren desde `worker/`.

### Base de datos (Supabase)

Local, con Docker y la [CLI de Supabase](https://supabase.com/docs/guides/local-development)
(`npx supabase ...` funciona sin instalarla):

```powershell
copy supabase\.env.example supabase\.env                        # URLs y SMTP (desarrollo: Mailpit)
cd worker; python -m tools.supabase_keys generate; cd ..         # claves propias en vez de las de demo
npx supabase start          # levanta Postgres + Auth y aplica migraciones + seed
cd worker; python -m tools.supabase_keys sync; cd ..             # copia las claves a web\.env.local
npx supabase db reset       # recrea la base desde cero
npx supabase test db        # tests de RLS (pgTAP)
```

`DATABASE_URL` local: `postgresql://postgres:postgres@127.0.0.1:54322/postgres`.
Contra el proyecto hosteado usá la conexión directa o el *session pooler*; con
el *transaction pooler* (puerto 6543) el worker desactiva los prepared statements.

### Migrar la base SQLite vieja

```powershell
cd worker
python -m tools.migrate_sqlite ..\automotive.db --dry-run   # muestra qué haría, no escribe
python -m tools.migrate_sqlite ..\automotive.db --email 864987866=vos@mail.com
```

Copia listings (con su snapshot inicial), alertas → `search_profiles` (una por
marca+modelo del catálogo), `seen_listings` → `matches` de backfill (no se
re-notifica nada) y el cache de geocoding. Es idempotente. Con `--email` crea
el usuario vía Admin API (`SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY`); sin
email, el usuario de Telegram queda como usuario anónimo, igual que los que
crea el bot.

### Login de Facebook (una vez)

Facebook requiere sesión.

```powershell
cd worker
python -m collectors.facebook
```

Se abre Chromium → entrás a tu cuenta → volvés a la consola → Enter. Genera
`fb_state.json`. Recomendación: usá una cuenta secundaria, FB es agresivo
detectando automatización en cuentas con poco historial.

### Probar un scraper sin levantar el bot

```powershell
cd worker
python -m tools.scraper_cli mercadolibre marca=Toyota modelo=Corolla anio_min=2018
python -m tools.scraper_cli v6 marca=Volkswagen modelo=Gol
python -m tools.scraper_cli kavak marca=Ford modelo=Ranger
python -m tools.scraper_cli facebook marca=Renault modelo=Duster
python -m tools.scraper_cli mercadolibre marca=Toyota modelo=Corolla origin_lat=-34.6037 origin_lon=-58.3816 radio_km=75
```

Imprime una tabla con los resultados — sirve para verificar que los selectores
siguen vivos y para probar nuevos filtros antes de cargarlos como alerta.

### MercadoLibre: sesion web

El scraper de MercadoLibre usa Playwright sobre la pagina publica de busqueda.
La API oficial (`/sites/MLA/search`) esta bloqueada por el PolicyAgent de
MercadoLibre para apps no-Partner (devuelve 403 con cualquier scope OAuth), asi
que no se usa.

Para que el navegador headless no quede atrapado por la verificacion de cuenta
de MercadoLibre, guarda una sesion web una vez:

```powershell
cd worker
python -m collectors.mercadolibre
```

Se abre Chromium -> inicia sesion o completa la verificacion -> volve a la
consola -> Enter. Genera `ml_state.json` y las siguientes corridas lo reutilizan
en modo headless.

### Correr el bot

```powershell
cd worker
python main.py
```

Con `WEB_BASE_URL` apuntando a la web, los links de las alertas pasan por
`/r/<id>` (clics trackeados) y el bot manda a la web para crear búsquedas.

Sin esperar al loop:

```powershell
cd worker
python -m tools.rematch                     # backfill de las búsquedas nuevas o editadas
python -m tools.simulate_alert <listing_id> # una publicación "recién llegada": match, score y alerta al inbox web
python -m tools.llm_jobs                    # procesa los pedidos del modo asistido en cola (--replay: respuestas grabadas)
```

### Backoffice y métricas (F6)

`/admin` es solo para `profiles.role = 'admin'` (proxy + chequeo en el
servidor; lee con la service role). Para dar acceso:

```sql
update public.profiles set role = 'admin' where email = 'vos@ejemplo.com';
```

- **Resumen**: los 6 criterios del §53 (`v_validation_criteria`) contra sus
  umbrales (`app_config.validation_criteria`), North Star, activación, ruido y
  estado de las fuentes.
- **Inspector "¿por qué se envió?"**: desde Notificaciones (o Resumen) un clic
  en «¿Por qué?» muestra la decisión del motor, el bloque del §45 (`model =
  true`… `score = 87`), las razones campo por campo, el `score_breakdown`, los
  comparables con el nivel de la cascada y los red flags. También por match
  (`/admin/matches/<id>`).
- **Métricas**: las vistas de la sección 11 (`v_north_star_weekly`,
  `v_activation`, `v_first_value`, `v_alert_funnel`,
  `v_high_score_engagement`, `v_alerts_per_user_day`, `v_outcomes`), el embudo
  del CTA Pro y la latencia del LLM. No cuentan a los admins.
- **Fuentes, Errores, Usuarios, Búsquedas, Listings, Matches, Config**: la
  cadencia de cada fuente y todo `app_config` se editan desde ahí.
- **Alerta de collector caído**: con `TELEGRAM_ADMIN_CHAT_ID` en `.env`, una
  fuente que falla `collector_failure_alert_after` veces seguidas (3) manda un
  Telegram al admin, y otro cuando vuelve a funcionar.
- **Monetización (§52)**: después de 3 alertas clickeadas (o de pasar el
  límite de búsquedas) el dashboard muestra «Probar Automotive Pro» → planes
  (Pro mensual, Search Pass 30/90 días) → lista de espera. Eventos
  `pro_cta_viewed`, `pro_cta_clicked`, `waitlist_joined`. No hay cobro.
- **Límites de plan** (`app_config.plan_limits`): con `enforced = false` (el
  piloto) todo está habilitado y cada vez que un usuario free pasa un límite
  (búsquedas, alertas inmediatas, resultados visibles) se registra
  `plan_limit_hit`. Con `true` se aplican: la segunda búsqueda se rechaza, las
  alertas inmediatas pasan a diarias y los resultados se cortan en 50.

### Modo asistido (LLM)

La pestaña **Asistido** de `/app/searches/new` escribe el texto en `llm_jobs`;
el worker lo interpreta con `claude -p` (`LLM_PROVIDER=claude_cli`, ver
`.env.example`), normaliza los borradores contra `vehicle_catalog` y la web
muestra un formulario editable por vehículo. Si el LLM falla o tarda más de
60 s, la web cae al formulario estructurado vacío. Con `claude_cli` el host del
worker necesita Claude Code instalado y logueado (en Windows, `CLAUDE_CLI_PATH`
con la ruta a `claude.exe`) y usa esa suscripción; para los usuarios del piloto,
`LLM_PROVIDER=anthropic` usa la API de Claude con `ANTHROPIC_API_KEY` (Haiku 4.5
por defecto, `ANTHROPIC_MODEL`), mismo prompt, mismo esquema y mismos tests de contrato.

```powershell
cd worker
python -m tools.record_llm --text "Busco Fiesta Titanium 2017"  # probar una frase contra claude -p
python -m tools.record_llm            # regrabar las 20 frases doradas (tras cambiar un prompt o schema)
```

### Correr la web

Ver [web/README.md](web/README.md): `npx supabase start` en la raíz y
`npm run dev -- --hostname 127.0.0.1` en `web/`.

### Tests

```powershell
pytest                                  # desde la raíz o desde worker/
cd worker; python -m tools.test_db; cd ..   # crea/actualiza la base automotive_test (después de cada migración)
$env:TEST_DATABASE_URL = "postgresql://postgres:postgres@127.0.0.1:54322/automotive_test"
pytest                                  # suma los tests contra Postgres
$env:LLM_SMOKE = "1"; pytest worker/tests/test_llm_contract.py -k smoke   # las 20 frases contra claude -p real
npx supabase test db                    # pgTAP: RLS, las funciones SQL de la web y las vistas de métricas
cd web; npm test; npm run e2e           # vitest y Playwright (desktop + 375 px)
```

Los tests de Postgres vacían las tablas de datos (`listings`, `matches`,
`notifications`…), así que **nunca corren sobre la base del piloto**: solo
aceptan una base local cuyo nombre termina en `_test` y que no sea la de
`DATABASE_URL`; si no, se saltean con el motivo. `tools.test_db` la clona del
stack local (esquema + `sources`, `app_config` y `vehicle_catalog`, sin datos
de usuarios). pgTAP corre cada archivo en una transacción que se descarta, y el
e2e solo toca sus propios datos con prefijo `e2e`.

## Comandos del bot

| Comando | Acción |
|---------|--------|
| `/start <código>` | vincula Telegram con tu cuenta de la web (el link de Ajustes → Telegram) |
| `/start`, `/help` | qué hace el bot y links a la web |
| `/nuevaalerta`, `/editar`, `/alertas`, `/pausar`, `/activar`, `/borrar`, `/cancelar` | el wizard se retiró en F4: responden con el link a la web |

Las alertas traen ⭐ Me interesa · ✖ Descartar · 🔎 Ver en Automotive. Si ya
tenías alertas creadas con el wizard, al vincular la cuenta se pasan a tu
usuario de la web.

## Matching y Opportunity Score

Todo es determinístico y vive en funciones puras en
[worker/intelligence/](worker/intelligence) (plan técnico, sección 6). Para
cada publicación nueva o actualizada de un crawl target, y para cada search
profile de ese modelo:

1. **Matching con razones** ([matching.py](worker/intelligence/matching.py)):
   cada hard filter da `ok`, `fail` o `unknown`. Un `fail` descarta; un
   `unknown` (la publicación no lo informa) deja pasar pero baja el score. Los
   precios se comparan **convirtiendo de moneda** (el `price_usd` congelado del
   día en que se vio el aviso): un aviso en ARS se compara contra un tope en USD.
2. **Comparables** (función SQL `public.comparables(listing_id)`): misma marca y
   modelo, año ±1, km ±25%, vistos en 30 días, sin precios parciales ni
   re-publicaciones. Cascada: misma versión y transmisión → misma transmisión →
   solo el modelo; se usa el primer nivel con `n ≥ comparables.min_n`.
3. **Opportunity Score 0–100** ([scoring.py](worker/intelligence/scoring.py)):
   precio 35, match 25, km 15, versión 10, recencia 10, completitud 5. Pesos y
   curvas en `app_config` (`score_weights`, `score_curves`): se ajustan sin deploy.
   Guardas de [price_check.py](worker/normalization/price_check.py): ≥65% bajo
   la mediana se trata como anticipo y se excluye; 50–65% queda como máximo en
   🟢 y con red flag; `price_partial` se excluye.
4. **Niveles** (`app_config.level_thresholds`): 🔥 ≥85 · 🟢 ≥70 · 🟡 ≥50 · ⚪.
5. **Red flags** y **preguntas al vendedor** con templates
   ([red_flags.py](worker/intelligence/red_flags.py),
   [seller_questions.py](worker/intelligence/seller_questions.py)). Siempre
   "conviene verificar"; el copy vive en [copy.py](worker/intelligence/copy.py)
   y un test impide los términos prohibidos del §19 ("vale", "precio real", "tasación").

Todo se guarda en `matches` (score, level, `score_breakdown`, `match_reasons`,
`price_ref`, `red_flags`). El motor de notificaciones avisa los matches nuevos
que no son backfill según el nivel mínimo de cada búsqueda. Los matches se
re-scorean después del enrichment, todas las noches (`app_config.rescore`,
últimos 14 días) y al arrancar si cambió `SCORING_VERSION`.

### Por qué matcheó (o no) un aviso

```powershell
cd worker
python -m tools.explain_match 123                       # por id de match
python -m tools.explain_match --profile 7 --listing 4521
python -m tools.explain_match 123 --json
```

Muestra cada razón, los comparables usados, el breakdown del score, los red
flags y las preguntas, y lo compara con lo guardado.

La primera corrida de cada target es silenciosa (backfill).

## Limitaciones

- **Facebook**: el DOM cambia seguido. Si los selectores se rompen, el ajuste
  vive en [facebook.py](worker/collectors/facebook.py). Va contra ToS de FB.
- **MercadoLibre**: usa Playwright sobre la búsqueda pública. La API oficial
  `/sites/MLA/search` está bloqueada para apps no-Partner, así que el flujo
  operativo es sesión web guardada en `ml_state.json`.
- **Tasa USD/ARS**: se toma en vivo del dólar blue ([dolarapi.com](https://dolarapi.com)),
  con cache de 1h y fallback al oficial. Lógica en [fx.py](worker/normalization/fx.py).
- **Geocodificación**: primero usa una tabla local de ciudades argentinas y
  luego Nominatim/OpenStreetMap con cache en `geocode_cache`. Si un aviso no
  tiene ubicación o no se puede geocodificar, la razón `location` queda
  `unknown`: no se descarta, pero baja el score.
- **Cache de comparables**: vive 30 días. En zonas de inventario chico
  (modelos raros) puede faltar volumen — bajá `comparables.min_n` en la
  tabla `app_config` o usá el techo duro `precio_max_oportunidad` por alerta.

## Agregar una nueva fuente

1. Crear `worker/collectors/<nombre>.py` con una clase que herede `BaseScraper`, un
   método async `search(filters) -> list[Listing]` y `fetch_detail(url) -> ListingDetail`.
   Conviene que el parseo sean funciones puras sobre HTML (`parse_search`,
   `parse_detail`) con un fixture en `worker/tests/fixtures/html/`.
2. Registrarla en [collectors/__init__.py](worker/collectors/__init__.py) `REGISTRY`.
3. Agregarla a `SOURCES` en [config.py](worker/config.py) y a la tabla `sources`
   (en `supabase/seed.sql` y con una migración para bases existentes).
4. Probar con `python -m tools.scraper_cli <nombre> marca=... modelo=...`.

# AutoMotive Alerts

Scraper en tiempo real de plataformas de autos en Argentina con detección
automática de oportunidades y notificación al Telegram.

El plan del MVP (web + Supabase) está en [docs/TECHNICAL_PLAN.md](docs/TECHNICAL_PLAN.md).
Estado: **F1** — ingesta centrada en la publicación: se scrapea por *crawl
target* (fuente + marca + modelo) y no por alerta, cada publicación se guarda
una sola vez con su historial, y el bot de Telegram sigue alertando igual que antes.

## Estructura

```
worker/       bot de Telegram, collectors, pipeline (Python, raíz de imports)
  collectors/     scrapers por fuente: search() y fetch_detail()
  normalization/  vehicle (catálogo + rapidfuzz), transmission, listing, price_check, geo, fx
  intelligence/   opportunity (motor legacy hasta F2)
  pipeline/       crawl (targets + cadencia), ingest (upsert/snapshots/eventos),
                  enrich, watchlist, rematch, scheduler (loop + alertas de Telegram)
  bot/            wizard de Telegram
  db/             psycopg 3 (pool async) + repos por tabla
  tools/          scraper_cli, migrate_sqlite
  tests/
supabase/     migraciones, seed.sql y tests pgTAP (supabase CLI)
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

1. Configurás una alerta desde Telegram (`/nuevaalerta`) eligiendo:
   - **Marcas** (multi-select por botones — podés tildar Toyota + VW + Ford)
   - **Modelos** (texto coma-separado: "Corolla, Hilux, Etios")
   - **Años** (multi-select por pills + texto: tipeá "2018-2022" o tocá los pills)
   - Versión (opcional), km min/max, moneda, combustible, transmisión,
     vendedor, ubicación de Telegram, radio en km, plataformas.
   - **% mínimo por debajo del precio de mercado** para alertar — el control
     central: *no* se fija un precio min/max, cada aviso se compara contra la
     mediana de comparables y se notifica si está al menos ese % por debajo.
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
6. **Alertas de Telegram**: cada lote de un target pasa por las alertas de ese
   modelo con sus filtros, el radio (`radio_km`, geocodificación con cache), la
   recencia (`RECOMMENDED_MAX_AGE_DAYS`, 15 días, cuando la fuente expone la
   fecha) y el motor de oportunidad. Lo ya visto (`matches`) no se re-notifica.
7. **Enrichment** ([enrich.py](worker/pipeline/enrich.py)): las publicaciones
   con al menos un match se completan con `fetch_detail()` (descripción,
   versión, transmisión, vendedor, todas las fotos), con una cola por fuente.
8. **Watchlist** ([watchlist.py](worker/pipeline/watchlist.py)): una vez por día
   se revisan las publicaciones guardadas o en seguimiento; si dan 404, están
   pausadas o vendidas pasan a `gone`.
9. **Observabilidad**: cada corrida queda en `collector_runs` (encontrados,
   nuevos, actualizados, error) y cada falla de normalización, ingesta,
   enrichment o notificación en `pipeline_errors`.

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
npx supabase start          # levanta Postgres + Auth y aplica migraciones + seed
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

En Telegram: `/start` → `/nuevaalerta`. Una alerta con varias marcas/modelos se
guarda como una alerta por combinación (un vehículo por búsqueda); un aviso que
matchea dos de tus alertas se notifica una sola vez.

### Tests

```powershell
pytest                                  # desde la raíz o desde worker/
$env:TEST_DATABASE_URL = "postgresql://postgres:postgres@127.0.0.1:54322/postgres"
pytest                                  # suma los tests contra Postgres (solo host local)
```

## Comandos del bot

| Comando | Acción |
|---------|--------|
| `/nuevaalerta` | wizard paso a paso |
| `/editar <id>` | reabre el wizard precargado con los filtros actuales (conserva el historial de vistos; si agregás modelos, se crean alertas nuevas para esos) |
| `/alertas` | listar tus alertas |
| `/pausar <id>` | pausar |
| `/activar <id>` | reactivar |
| `/borrar <id>` | borrar |
| `/cancelar` | abortar wizard |

## Detección de oportunidad

Para cada listing nuevo:

1. **Filtro de precio trampa** ([price_check.py](worker/normalization/price_check.py)): si el título
   tiene keywords típicos de anticipos/planes (`anticipo`, `cuota`, `plan
   adjudicado`, `permuta`, `/mes`, `plan rombo`, etc.), el listing se marca
   `price_partial=True`, **no entra en la mediana** y nunca se notifica como
   oportunidad.
2. Se busca cache de comparables (excluyendo los `price_partial`): misma
   `marca` y `modelo` normalizados (`VW`==`Volkswagen`), año ±1, km ±25%,
   scrapeados en los últimos 30 días.
3. Si hay menos de `comparables.min_n` de `app_config` (default 5), se ignora
   el listing — no hay datos suficientes para juzgar — salvo que el usuario
   haya seteado `precio_max_oportunidad` (techo duro).
4. Se calcula la mediana en USD (precios ARS se convierten con `usd_rate_ars`
   en [opportunity.py](worker/intelligence/opportunity.py)).
5. **Filtro estadístico** post-mediana:
   - Listing **≥65% bajo la mediana** → casi seguro anticipo/plan oculto, se descarta.
   - Listing **50–65% bajo la mediana** → oportunidad pero marcada como
     "⚠️ Oportunidad sospechosa" en la notificación.
6. Si está `>= descuento_pct` por debajo y pasa los filtros → se notifica.

La primera corrida de cada target es silenciosa mientras se llena el cache.

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
  tiene ubicación o no se puede geocodificar, se descarta cuando la alerta usa
  `radio_km`.
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

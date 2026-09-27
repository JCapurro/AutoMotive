# AutoMotive Alerts

Scraper en tiempo real de plataformas de autos en Argentina con detección
automática de oportunidades y notificación al Telegram.

El plan del MVP (web + Supabase) está en [docs/TECHNICAL_PLAN.md](docs/TECHNICAL_PLAN.md).
Estado: **F0** — el bot corre sobre Postgres (Supabase) y el repo ya tiene la
forma de monorepo.

## Estructura

```
worker/       bot de Telegram, collectors, pipeline (Python, raíz de imports)
  collectors/     scrapers por fuente (Playwright)
  normalization/  normalize, price_check, geo, fx
  intelligence/   opportunity (motor legacy hasta F2)
  pipeline/       scheduler
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
2. **Bootstrap silencioso**: la primera corrida de una alerta marca todo lo
   que vea como "ya conocido" sin notificar — evita el diluvio inicial.
3. **Cadencia per-alerta**: cada alerta se re-scrapea a lo sumo cada
   `ALERT_RESCRAPE_INTERVAL_SECONDS` (default 3h). El scheduler tiquea cada
   `TICK_INTERVAL_SECONDS` (default 5min) pero solo corre las alertas que
   ya están "vencidas". Las 4 fuentes se scrapean en paralelo.
4. **Filtro de recencia**: una vez bootstrapeada, solo se recomiendan
   publicaciones cuya fecha conocida sea menor o igual a
   `RECOMMENDED_MAX_AGE_DAYS` (default 15 días). Si la fuente no expone la
   fecha (ej. Kavak, ML), se confía en `matches` (lo ya visto) para detectar lo nuevo.
5. Toda publicación nueva se filtra por distancia: el bot toma tu ubicación
   de Telegram, geocodifica la ubicación textual del aviso y solo conserva los
   autos dentro de `radio_km`. Las geocodificaciones se cachean en Postgres.
6. Toda publicación nueva pasa por el filtro de **precio trampa** y se
   compara contra la mediana de "comparables" recientes (mismo modelo, año
   ±1, km ±25%, normalizado a USD).
7. Si la publicación pasa todos los filtros y está al menos `descuento_pct`
   por debajo de la mediana, te llega al Telegram. Las ya vistas no se
   re-notifican.

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

Las primeras 1-2 corridas son silenciosas mientras se llena el cache.

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

1. Crear `worker/collectors/<nombre>.py` con una clase que herede `BaseScraper` y un
   método async `search(filters) -> list[Listing]`.
2. Registrarla en [collectors/__init__.py](worker/collectors/__init__.py) `REGISTRY`.
3. Agregarla a `SOURCES` en [config.py](worker/config.py) y a la tabla `sources`
   (en `supabase/seed.sql` y con una migración para bases existentes).
4. Probar con `python -m tools.scraper_cli <nombre> marca=... modelo=...`.

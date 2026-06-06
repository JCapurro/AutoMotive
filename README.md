# AutoMotive Alerts

Scraper en tiempo real de plataformas de autos en Argentina con detección
automática de oportunidades y notificación al Telegram.

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
   - Versión (opcional), km min/max, precio min/max, moneda, combustible,
     transmisión, vendedor, ubicación de Telegram, radio en km, % mínimo de
     descuento, plataformas.
2. **Bootstrap silencioso**: la primera corrida de una alerta marca todo lo
   que vea como "ya conocido" sin notificar — evita el diluvio inicial.
3. **Cadencia per-alerta**: cada alerta se re-scrapea a lo sumo cada
   `ALERT_RESCRAPE_INTERVAL_SECONDS` (default 6h). El scheduler tiquea cada
   `TICK_INTERVAL_SECONDS` (default 5min) pero solo corre las alertas que
   ya están "vencidas". Las 4 fuentes se scrapean en paralelo.
4. **Filtro de recencia**: una vez bootstrapeada, solo se recomiendan
   publicaciones cuya fecha conocida sea menor o igual a
   `RECOMMENDED_MAX_AGE_DAYS` (default 15 días). Si la fuente no expone la
   fecha (ej. Kavak, ML), se confía en `seen_listings` para detectar lo nuevo.
5. Toda publicación nueva se filtra por distancia: el bot toma tu ubicación
   de Telegram, geocodifica la ubicación textual del aviso y solo conserva los
   autos dentro de `radio_km`. Las geocodificaciones se cachean en SQLite.
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
pip install -r requirements.txt
python -m playwright install chromium
copy .env.example .env
# editá .env y poné TELEGRAM_TOKEN
```

### Login de Facebook (una vez)

Facebook requiere sesión.

```powershell
python -m scrapers.facebook
```

Se abre Chromium → entrás a tu cuenta → volvés a la consola → Enter. Genera
`fb_state.json`. Recomendación: usá una cuenta secundaria, FB es agresivo
detectando automatización en cuentas con poco historial.

### Probar un scraper sin levantar el bot

```powershell
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
python -m scrapers.mercadolibre
```

Se abre Chromium -> inicia sesion o completa la verificacion -> volve a la
consola -> Enter. Genera `ml_state.json` y las siguientes corridas lo reutilizan
en modo headless.

### Correr el bot

```powershell
python main.py
```

En Telegram: `/start` → `/nuevaalerta`.

## Comandos del bot

| Comando | Acción |
|---------|--------|
| `/nuevaalerta` | wizard paso a paso |
| `/alertas` | listar tus alertas |
| `/pausar <id>` | pausar |
| `/activar <id>` | reactivar |
| `/borrar <id>` | borrar |
| `/cancelar` | abortar wizard |

## Detección de oportunidad

Para cada listing nuevo:

1. **Filtro de precio trampa** ([price_check.py](price_check.py)): si el título
   tiene keywords típicos de anticipos/planes (`anticipo`, `cuota`, `plan
   adjudicado`, `permuta`, `/mes`, `plan rombo`, etc.), el listing se marca
   `price_partial=True`, **no entra en la mediana** y nunca se notifica como
   oportunidad.
2. Se busca cache de comparables (excluyendo los `price_partial`): misma
   `marca` y `modelo` normalizados (`VW`==`Volkswagen`), año ±1, km ±25%,
   scrapeados en los últimos 30 días.
3. Si hay menos de `OPPORTUNITY_MIN_COMPARABLES` (default 5), se ignora
   el listing — no hay datos suficientes para juzgar — salvo que el usuario
   haya seteado `precio_max_oportunidad` (techo duro).
4. Se calcula la mediana en USD (precios ARS se convierten con `usd_rate_ars`
   en [opportunity.py](opportunity.py)).
5. **Filtro estadístico** post-mediana:
   - Listing **≥65% bajo la mediana** → casi seguro anticipo/plan oculto, se descarta.
   - Listing **50–65% bajo la mediana** → oportunidad pero marcada como
     "⚠️ Oportunidad sospechosa" en la notificación.
6. Si está `>= descuento_pct` por debajo y pasa los filtros → se notifica.

Las primeras 1-2 corridas son silenciosas mientras se llena el cache.

## Limitaciones

- **Facebook**: el DOM cambia seguido. Si los selectores se rompen, el ajuste
  vive en [scrapers/facebook.py](scrapers/facebook.py). Va contra ToS de FB.
- **MercadoLibre**: usa Playwright sobre la búsqueda pública. La API oficial
  `/sites/MLA/search` está bloqueada para apps no-Partner, así que el flujo
  operativo es sesión web guardada en `ml_state.json`.
- **Tasa USD/ARS**: se toma en vivo del dólar blue ([dolarapi.com](https://dolarapi.com)),
  con cache de 1h y fallback al oficial. Lógica en [fx.py](fx.py).
- **Geocodificación**: primero usa una tabla local de ciudades argentinas y
  luego Nominatim/OpenStreetMap con cache en `geocode_cache`. Si un aviso no
  tiene ubicación o no se puede geocodificar, se descarta cuando la alerta usa
  `radio_km`.
- **Cache de comparables**: vive 30 días. En zonas de inventario chico
  (modelos raros) puede faltar volumen — bajá `OPPORTUNITY_MIN_COMPARABLES`
  en `.env` o usá el techo duro `precio_max_oportunidad` por alerta.

## Agregar una nueva fuente

1. Crear `scrapers/<nombre>.py` con una clase que herede `BaseScraper` y un
   método async `search(filters) -> list[Listing]`.
2. Registrarla en [scrapers/__init__.py](scrapers/__init__.py) `REGISTRY`.
3. Agregarla a `SOURCES` en [config.py](config.py).
4. Probar con `python -m tools.scraper_cli <nombre> marca=... modelo=...`.

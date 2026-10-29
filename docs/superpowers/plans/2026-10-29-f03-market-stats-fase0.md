# F-03 Fase 0: zona por aviso y `market_stats` semanal (dry-run)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Track the steps below during implementation.

**Goal:** Empezar a acumular semanas de datos de mercado sin UI ni gating: (1) una región por aviso derivada de sus coordenadas y (2) la tabla `market_stats` con un job semanal idempotente que nace apagado (`mode: off`) y arranca en `dry_run`. Diseño aprobado por Juan: [2026-10-29-f03-market-stats-fase0-design.md](../specs/2026-10-29-f03-market-stats-fase0-design.md). Ítem F-03 del [backlog de producto](../../BACKLOG_PRODUCTO_2026-10.md).

**Architecture:** `normalization/zone.py` (función pura, sin I/O) busca la localidad de Georef más cercana a las `lat/lon` del aviso y devuelve provincia, departamento y precisión. `listing_zones` (tabla auxiliar, 1 fila por aviso) guarda esos hechos; la **región se calcula al agregar** con el mapa `app_config.market_zones`. `pipeline/market_zones.py` hace `sync_zones()` (carga inicial y delta) y `tools/backfill_zones.py` lo expone por CLI. `pipeline/market_stats.py` trae filas planas por SQL, agrega en Python puro (percentiles, banda de año, `todas`) y hace upsert idempotente en `market_stats`; `market_stats_loop` lo lanza los lunes según `app_config.market_stats`. `purge_market_stats()` en `pipeline/retention.py` poda a 26 semanas. Sin UI, sin tocar `ingest.py`, `rescore.py`, `comparables()` ni migraciones viejas.

**Tech Stack:** Python 3.12 (psycopg async, pytest/unittest), PostgreSQL/Supabase (migración + pgTAP), JSON de Georef copiado al worker. Sin código de `web/` escrito a mano.

## Alcance y decisiones aprobadas

Juan aprobó **todas** las propuestas de «Decisiones que necesita de Juan» del diseño, tal cual (salvo lo que se aclara en «Tareas de Juan»):

1. **Regiones (8):** `amba` (CABA `02` + los 24 partidos del GBA de la provincia `06`), `buenos_aires_resto` (resto de `06`, incluye La Plata, Costa Atlántica, Escobar y Pilar), `cordoba` (`14`), `litoral` (Santa Fe `82`, Entre Ríos `30`), `nea` (Corrientes `18`, Misiones `54`, Chaco `22`, Formosa `34`), `cuyo` (Mendoza `50`, San Juan `70`, San Luis `74`), `noa` (Salta `66`, Tucumán `90`, Jujuy `38`, Santiago del Estero `86`, Catamarca `10`, La Rioja `46`), `patagonia` (Neuquén `58`, Río Negro `62`, Chubut `26`, Santa Cruz `78`, Tierra del Fuego `94`, La Pampa `42`).
2. **Mínimos de muestra:** `min_n.price = 8`, `min_n.days = 5`; por debajo, percentiles en null y conteos guardados igual. Banda de 2 años alineada a pares (`year_from = año − año % 2`); avisos sin año fuera. Semana ISO lunes 00:00 a domingo, hora de Argentina (UTC-3, sin DST).
3. **Zona en tabla auxiliar `listing_zones`** derivada de las coordenadas (no columna en `listings`). La región se calcula al agregar, no se guarda por aviso.
4. **Semanas pasadas:** sin `--retro`. El job rechaza semanas anteriores a `recompute_weeks` (2) y se empieza a acumular desde la primera corrida real. (El flag `--retro` del diseño queda **fuera** de este plan.)
5. **Mercado Libre cuenta bajas desde el 24/10/2026** (`app_config.market_stats.confirm_since.mercadolibre`).
6. **Grupo Randazzo y otras fuentes sin ubicación quedan sin región** (no se agrega nada a `SOURCE_DEFAULT_LOCATIONS`). Rosario Garage conserva su default (Rosario) con `precision = source_default`.
7. **Cronograma:** lunes 06:00 hora de Argentina; dos semanas en `dry_run` antes de escribir.
8. **Presupuesto de base:** `market_stats` ≤ 100 MB a 26 semanas; si la proyección del dry-run lo supera, se guardan solo las zonas con muestra mínima (`store_min_active`, que se agrega recién entonces).
9. **Aplicar la migración en producción y desplegar el worker con `wait_idle`:** la decisión 9 del diseño pide ese OK, pero **no lo dio todavía** (ver «Tareas de Juan»). Este plan no aplica nada a producción ni reinicia el worker.

Definiciones de métricas (todas excluyen reposts, `probable_repost_of is not null`): `active_count`, `active_confirmed_count`, `new_count` (sin `attributes._not_news`), `gone_count` y días solo de fuentes en `confirm_sources` con `listing_unconfirmed()` no vacío, baja estimada = `greatest(last_seen_at, last_full_seen_at)`, días = baja − `coalesce(published_at, first_seen_at)` (se descartan sin `published_at` con `_not_news`, y negativos), `days_source = 'confirm_sources'`; precios sobre activos con `price_usd > 0` y `not price_partial` (mediana, p25, p75 por interpolación lineal). Sin `drop_share`, `median_total_drop_pct` ni `demand_count` en esta entrega. «Dejó de publicarse» nunca se presenta como «se vendió».

**Rama:** `claude/f03-market-stats-fase0` (cortar de `main` actual). F-03 es **independiente** del resto: no toca `email_html.py`, `templates.py`, snapshots ni `match_cards`/`search_results`.

**Orden de edición con las demás piezas del backlog:** H-01 (PR #50 sin mergear, rama `claude/email-seller-questions`) → X-01 → PAR-03 → PAR-02 tramo 1 comparten `email_html.py`, `templates.py`, snapshots y la migración de `match_cards`/`search_results`; van en ese orden y **no** con este plan. F-03 corre en paralelo con todos. La migración de F-03 es la **n.º 1 de la cadena** del plan por fases: se nombra `20261119110000_f03_market_stats.sql` para quedar antes de la provisoria de X-01 (`20261119120000_x01_tracking.sql`). Si al implementar cambia `max(version)` de producción, renombrar sin chocar con las otras. Único punto de contacto de archivos compartidos: `worker/tests/pgcase.py` (`_TRUNCATE`) y `web/types/database.ts` (generado: ante conflicto, regenerar con `npm run gen:types`, no resolver a mano); `worker/main.py` y `worker/pipeline/retention.py` reciben líneas aisladas.

**Comandos de prueba** (todos desde la raíz del repo salvo que se diga otra cosa; `pytest.ini` ya pone `pythonpath = worker`):

- Offline: `python -m pytest worker/tests/test_zone.py worker/tests/test_market_zones_config.py worker/tests/test_market_stats.py worker/tests/test_backfill_zones.py -q`
- Suite completa sin base: `python -m pytest worker/tests -q -m "not db"`
- Base de pruebas: `npx supabase start`, `npx supabase migration up` (aplica la migración nueva en la base **local**; `npx supabase db reset` la recrea entera si hace falta), luego `cd worker; python -m tools.test_db; cd ..`, y en PowerShell `$env:TEST_DATABASE_URL = "postgresql://postgres:postgres@127.0.0.1:54322/automotive_test"`.
- Contra `*_test`: `python -m pytest worker/tests/test_market_stats_postgres.py -q` (y la suite completa sin `-m "not db"` para el cierre).
- pgTAP: `npx supabase test db` (README: «tests de RLS (pgTAP)»; un archivo en `supabase/tests/`, cada uno en una transacción que se descarta).
- Tipos de web: `cd web; npm run gen:types; cd ..` (`web/package.json`: `supabase gen types typescript --local --schema public > web/types/database.ts`).
- vitest/Playwright (`cd web; npm test; npm run e2e`): **no aplican**, no hay UI; solo correr `npm test` una vez para confirmar que el archivo de tipos regenerado no rompe nada.

## Tareas de Juan (fuera de este plan, no inventar)

- [ ] **OK explícito para aplicar la migración en producción** (transacción + versión exacta en `supabase_migrations.schema_migrations` + releer `max(version)`; el 29/10 era `20261118130000`). No lo dio. Lo ejecuta/autoriza Juan; el plan solo deja el paso descrito en la Tarea 9.
- [ ] **OK para desplegar el worker** (`python -m tools.wait_idle facebook mercadolibre --max-wait 1200 --poll 5` antes de reiniciar). Con `mode: off` el despliegue no cambia comportamiento.
- [ ] **OK para correr `tools.backfill_zones` (sin `--dry-run`) y `tools.market_stats` en el VPS** y para pasar `app_config.market_stats` a `mode: dry_run`, después a `write_enabled: true` / `mode: write` (los prende solo Juan, desde `/admin/config`).
- [ ] Textos legales, links oficiales y texto de Privacidad/Términos: **no hay ninguno en esta entrega** (no hay UI ni datos personales; `market_stats` es agregado). Si Juan decide exponer algo al usuario, queda para la entrega de consumo (PAR-03/PRO-02/PRO-04) y sus textos los define él.
- [ ] Opcional: cargar un default de ubicación para Grupo Randazzo en `SOURCE_DEFAULT_LOCATIONS` (hoy decidido: sin región).

## Task 0: leer las reglas de `web/` y preparar la rama

- [x] Leer `web/CLAUDE.md` → `web/AGENTS.md` y la guía correspondiente de `web/node_modules/next/dist/docs/` (`01-app`, `02-pages`, `03-architecture`) **antes de tocar `web/`**. En esta entrega `web/` solo cambia por el archivo generado `web/types/database.ts`; no se escribe código de web a mano, así que la lectura es de verificación (si algo exigiera código, parar y consultar).
- [x] `git switch main && git pull && git switch -c claude/f03-market-stats-fase0`. Confirmar que el árbol está limpio de cambios ajenos (hay `graphify-out/` y `docs/*.json` sin commitear de otras sesiones: no incluirlos).
- [x] Línea base: `python -m pytest worker/tests -q -m "not db"` verde antes de empezar.

## Task 1: mapa de regiones y `zone.py` (tests primero)

Files: `worker/normalization/data/ar_localities.json` (copia exacta de `web/lib/data/argentina-locations.json`), `worker/normalization/zone.py`, `worker/tests/test_zone.py`, `worker/tests/test_market_zones_config.py`.

- [x] Copiar el JSON (`copy web\lib\data\argentina-locations.json worker\normalization\data\ar_localities.json`). Forma verificada: `{source, provinces: [[id, nombre]], cities: [[id, nombre, province_id, departamento, lat, lon]]}` (4.022 localidades, 24 provincias). El deploy del VPS no se verificó que incluya `web/lib/data/`: por eso el worker lee solo su copia.
- [x] Escribir `worker/tests/test_zone.py` que falle: (a) el JSON del worker es idéntico byte a byte al de `web/lib/data/` (lee ambos con `Path(__file__)`); (b) `nearest_locality()` devuelve la localidad esperada para una coordenada conocida (Rosario, La Plata, Córdoba, Ushuaia) y `dist_km` coherente; (c) caché por coordenada (la segunda llamada no recalcula: contar con un parche sobre `haversine_km`); (d) `derive_zone()` sin lat/lon devuelve `None`; (e) texto limpio igual a nombre de provincia o «argentina» → `precision = 'province'` y, si la provincia es «Buenos Aires» a secas, `region_for()` da `None` (no se infla AMBA con la coordenada de CABA); (f) fuente en `SOURCE_DEFAULT_LOCATIONS` sin texto → `precision = 'source_default'`; (g) un caso por región; (h) límites AMBA: San Isidro → `amba`, Pilar → `buenos_aires_resto`, La Plata → `buenos_aires_resto`, Escobar → `buenos_aires_resto`.
- [x] Escribir `worker/tests/test_market_zones_config.py` que falle: el mapa inicial (constante `DEFAULT_ZONE_MAP` en `zone.py`, la misma que va a la migración) cubre las 24 provincias de Georef, las claves de `rules[].region` existen en `regions`, cada departamento citado existe en el JSON para esa provincia (los 24 partidos del GBA se verificaron presentes), `resolve_region()` respeta «gana la primera regla que coincide» (GBA antes que el resto de `06`), y las etiquetas de `regions` pasan `FORBIDDEN_TERMS` normalizando con `normalize_text`/`_fold` como en `worker/tests/test_intelligence_copy.py`.
- [x] Implementar `worker/normalization/zone.py`: `load_localities()` (cacheado con `functools.lru_cache`), `nearest_locality(lat, lon)` reutilizando `normalization.geo.haversine_km` (no reescribirla), `derive_zone(lat, lon, location_text, source) -> ZoneFacts | None` (`province_id`, `department`, `locality_id`, `dist_km`, `precision`, `lat`, `lon`; usa `clean_location_text` y `SOURCE_DEFAULT_LOCATIONS` de `geo.py`), `resolve_region(zone_map, province_id, department, precision) -> str | None`, `DEFAULT_ZONE_MAP` (con `version: 1`). Función pura: sin red ni base. Rendimiento: unos cientos de puntos distintos contra 4.022 localidades; si el test de volumen lo pide, prefiltrar por caja de lat/lon.
- [x] Correr `python -m pytest worker/tests/test_zone.py worker/tests/test_market_zones_config.py -q` y `python -m pytest worker/tests/test_intelligence_copy.py -q` (que el lint de copy no vea literales nuevos prohibidos).

## Task 2: migración y pgTAP (tests primero)

Files: `supabase/tests/market_stats_test.sql`, `supabase/migrations/20261119110000_f03_market_stats.sql`, `worker/tests/pgcase.py` (`_TRUNCATE`), `web/types/database.ts` (generado).

- [x] Escribir `supabase/tests/market_stats_test.sql` (patrón de `supabase/tests/product_feedback_test.sql`: `begin; select no_plan(); ... select * from finish(); rollback;`, usuarios en `auth.users` con `insert`, `set local role authenticated; set local request.jwt.claim.sub=...`) que falle: un usuario común cuenta 0 filas en `listing_zones`, `market_stats` y `market_stats_runs`; `anon` denegado (`42501`); insert directo como `authenticated` denegado; tras `update public.profiles set role='admin'` el admin lee `market_stats` y `market_stats_runs` pero **no** `listing_zones` (sin política); `service_role` inserta en las tres; el CHECK de `group_kind` (`model|body_type`) y de `mode` (`dry_run|write`) rechazan otros valores; la unicidad `(week_start, group_kind, make, model, body_type, year_from, zone)` con `nulls not distinct` rechaza un duplicado con nulls; `listing_zones` se borra en cascada al borrar el aviso; `app_config.market_stats` y `app_config.market_zones` existen con `mode = 'off'`, `write_enabled = false`, `min_n = {"price":8,"days":5}`; `retention.market_stats_weeks = 26`.
- [x] Escribir la migración (encabezado `--` citando `docs/superpowers/specs/2026-10-29-f03-market-stats-fase0-design.md` y F-03; releer `max(version)` de producción **antes de nombrarla** y confirmar que sigue siendo mayor a `20261118130000`): `listing_zones` (`listing_id bigint primary key references public.listings(id) on delete cascade`, `province_id`, `department`, `locality_id`, `dist_km`, `precision` con CHECK `locality|province|source_default`, `lat`, `lon`, `derived_at`); `market_stats_runs` (id, `week_start`, `mode` CHECK `dry_run|write`, `started_at`, `finished_at`, `status` CHECK `running|ok|failed`, `rows_computed`, `rows_written`, `listings_read`, `no_zone_by_source jsonb`, `params jsonb`, `error`); `market_stats` (`week_start date`, `group_kind` CHECK `model|body_type`, `make`, `model`, `body_type`, `year_from`, `zone`, `active_count`, `active_confirmed_count`, `new_count`, `gone_count`, `price_n`, `median_price_usd`, `p25_price_usd`, `p75_price_usd`, `days_n`, `median_days_to_gone`, `p25_days_to_gone`, `p75_days_to_gone`, `days_source`, `zone_map_version`, `as_of`, `computed_at`, `run_id references market_stats_runs`, `basis`; `constraint market_stats_unique unique nulls not distinct (week_start, group_kind, make, model, body_type, year_from, zone)`); índices por `(week_start, group_kind, zone)` y `(make, model)`; `insert ... on conflict (key) do nothing` de `app_config.market_stats` (`{mode:"off", write_enabled:false, min_n:{price:8,days:5}, year_band:2, recompute_weeks:2, confirm_since:{mercadolibre:"2026-10-24"}, schedule:{weekday:1,hour:"06:00"}}`) y `app_config.market_zones` (el mismo `DEFAULT_ZONE_MAP` de `zone.py`); `update public.app_config set value = value || '{"market_stats_weeks": 26}' where key = 'retention' and not value ? 'market_stats_weeks'` (mismo patrón que `raw_page_days`, `20261006120000`); `enable row level security` en las tres, `revoke all ... from public, anon, authenticated`, `grant all ... to service_role`, y `create policy ... for select to authenticated using (exists (select 1 from public.profiles p where p.id = (select auth.uid()) and p.role = 'admin'))` solo en `market_stats` y `market_stats_runs`. No redefine `comparables()` ni funciones existentes.
- [x] Agregar `listing_zones`, `market_stats` y `market_stats_runs` a `_TRUNCATE` de `worker/tests/pgcase.py` (`listing_zones` ya cae por `CASCADE` desde `listings`, pero las otras dos no).
- [ ] Aplicar **solo en la base local** (`npx supabase migration up`), correr `npx supabase test db` y confirmar verde (incluidos los pgTAP existentes, p. ej. `comparables_test.sql`). Recrear la base de pruebas con `cd worker; python -m tools.test_db; cd ..`.
- [ ] `cd web; npm run gen:types; cd ..`, revisar que el diff de `web/types/database.ts` solo agrega las tres tablas, y correr `cd web; npm test; cd ..`.
- [x] **No** aplicar a producción (queda en las Tareas de Juan / Tarea 9).

## Task 3: `sync_zones()` y `backfill_zones` (tests primero)

Files: `worker/pipeline/market_zones.py`, `worker/tools/backfill_zones.py`, `worker/tests/test_backfill_zones.py`, `worker/tests/test_market_stats_postgres.py` (clase de zonas).

- [x] Escribir `worker/tests/test_backfill_zones.py` (offline, estilo `worker/tests/test_backfill_geo.py`) que falle: `plan_zones(rows)` sobre filas `{id, source, location_text, lat, lon, zone_lat, zone_lon}` devuelve inserts para avisos sin fila, re-derivación para los que cambiaron de `lat/lon`, nada para los que no cambiaron ni para los que no tienen coordenadas; el informe por fuente cuenta `con región`, `provincia sin región`, `sin coordenadas`, `source_default`; `--dry-run` no escribe.
- [x] Escribir en `worker/tests/test_market_stats_postgres.py` (marcado `pytestmark = [pytest.mark.db, requires_db]`, base `PostgresTestCase` como `worker/tests/test_intelligence_postgres.py`) los tests que fallen: `sync_zones()` inserta la fila de un aviso con coordenadas de San Isidro, incluye avisos `gone`, no crea fila sin `lat/lon`, es idempotente y re-deriva cuando el aviso cambia de `lat/lon`.
- [x] Implementar `sync_zones(*, dry_run=False, source=None) -> Counter` en `worker/pipeline/market_zones.py` (trae avisos sin fila o con coordenadas distintas a las de `listing_zones`, llama `derive_zone`, `insert ... on conflict (listing_id) do update`) y `worker/tools/backfill_zones.py` (`python -m tools.backfill_zones [--dry-run] [--source X]`, mismo esqueleto que `tools/backfill_geo.py`: `argparse`, `db.open_pool()`/`close_pool()`, informe por fuente y `(simulación: no se escribió nada)`). Sin tocar `ingest.py`.
- [ ] Correr los tests offline de la tarea y, con `TEST_DATABASE_URL`, `python -m pytest worker/tests/test_market_stats_postgres.py -k Zones -q`.

## Task 4: agregación pura (tests primero)

Files: `worker/pipeline/market_stats.py` (parte pura), `worker/tests/test_market_stats.py`.

- [x] Escribir `worker/tests/test_market_stats.py` que falle, con filas planas inventadas: `percentile()` contra valores calculados a mano (interpolación lineal, igual que `percentile_cont`); mínimos `min_n` (7 precios → percentiles null y `price_n = 7`; 8 → calculados; igual 4/5 para días); banda de año (2018 y 2019 → `year_from = 2018`; 2020 → 2020; sin año fuera); exclusión de reposts y de `body_type` nulo en el grupo `body_type`; `todas` ≥ suma de las regiones y cuenta los avisos sin región; `new_count` ignora `_not_news`; `gone_count` y días **solo** de fuentes de `confirm_sources` con `unconfirmed = true`; Mercado Libre con baja estimada anterior a `confirm_since` queda fuera de `gone_count` y de días; días descartados sin `published_at` con `_not_news` y los negativos; `active_confirmed_count` ≤ `active_count`; `week_bounds('2026-W44')` y `last_closed_week(now)` en hora de Argentina (lunes 00:00 a domingo); mismo input → mismas filas (idempotencia/orden determinista); `make`/`model` agrupados con `lower()` (la consistencia de mayúsculas en `listings` no se verificó).
- [x] Implementar en `worker/pipeline/market_stats.py`: `week_bounds()`, `last_closed_week()`, `percentile()`, `aggregate(rows, *, week, zone_map, cfg) -> list[StatRow]` y el informe (`report()`: filas, % sin zona por fuente, distribución de `price_n`, filas con muestra suficiente, proyección de tamaño a 26 semanas). Puro, sin I/O.
- [x] Correr `python -m pytest worker/tests/test_market_stats.py -q` verde.

## Task 5: lectura SQL y upsert (tests contra `*_test` primero)

Files: `worker/pipeline/market_stats.py` (parte con base), `worker/tests/test_market_stats_postgres.py`.

- [x] Escribir tests que fallen (en la misma clase de base): `fetch_rows(week, cfg)` devuelve una fila por aviso con banderas de confirmación y provincia/departamento de `listing_zones`, usando fixtures de `crawl_targets` con `last_full_read_at` posterior a `last_seen_at + 36 h` (patrón de `test_intelligence_postgres.py`) para que `listing_unconfirmed()` devuelva targets reales; `upsert_rows()` dos veces con la misma semana no duplica y reemplaza (idempotente); un aviso `gone` confirmado entra a `gone_count`, uno de Facebook (no está en `confirm_sources`) no.
- [x] Implementar `fetch_rows()` leyendo `app_config.comparables.confirm_sources`, `confirm_grace_hours` y `max_age_days` en cada corrida (no copiar la lista a una constante), cuidando el rendimiento de `listing_unconfirmed()`: llamarla solo para fuentes de `confirm_sources` (la migración de comparables documenta que el planificador es sensible); y `upsert_rows()` con `insert ... on conflict on constraint market_stats_unique do update`.
- [ ] Correr `python -m pytest worker/tests/test_market_stats_postgres.py -q` con `TEST_DATABASE_URL`.

## Task 6: corrida, modos y CLI (tests primero)

Files: `worker/pipeline/market_stats.py` (`run_market_stats`), `worker/tools/market_stats.py`, `worker/tests/test_market_stats.py`, `worker/tests/test_market_stats_postgres.py`.

- [x] Escribir tests que fallen: `--dry-run` no escribe nada (ni `market_stats` ni `market_stats_runs`) e imprime el informe; sin `--dry-run` hace falta `--write`, y con `write_enabled = false` aborta con mensaje claro; el modo programado `dry_run` deja **una** fila en `market_stats_runs` con `rows_written = 0`; `write` escribe y marca la corrida `ok`; un error en la corrida deja `status = 'failed'`, el texto en `market_stats_runs.error` y una fila en `pipeline_errors` con `stage = 'market_stats'` (vía `log_error()` de `db/repos/runs.py`); semana anterior a `recompute_weeks` rechazada (sin `--retro`); cada corrida recalcula también las `recompute_weeks` (2) anteriores; `sync_zones()` corre al empezar.
- [x] Implementar `run_market_stats(week=None, *, mode, write_enabled)` y `worker/tools/market_stats.py` (`python -m tools.market_stats --week [2026-W44] --dry-run`; sin valor, la última semana cerrada; `--write` explícito). Los errores nunca rompen el worker: se registran y se sigue.
- [ ] Correr `python -m pytest worker/tests/test_market_stats.py worker/tests/test_market_stats_postgres.py -q`.

## Task 7: loop semanal y enganche en `main.py` (tests primero)

Files: `worker/pipeline/market_stats.py` (`market_stats_loop`), `worker/main.py`, `worker/tests/test_market_stats.py`.

- [x] Escribir tests que fallen sobre la función pura `next_run(now, cfg)` (estilo `worker/tests/test_rescore_schedule.py`): próximo lunes 06:00 hora de Argentina según `schedule.weekday`/`schedule.hour`; `mode: off` no ejecuta nada; `dry_run` y `write` llaman a `run_market_stats` con el modo correcto.
- [x] Implementar `market_stats_loop(stop)` (lee `app_config.market_stats` en cada vuelta, usa `asyncio.wait_for(stop.wait(), timeout=...)` como `digest_loop`/`nightly_loop`, atrapa excepciones con `log_error("market_stats", "loop", traceback.format_exc())`). En `worker/main.py`: una línea de import (`from pipeline.market_stats import market_stats_loop`) y `asyncio.create_task(market_stats_loop(stop))` junto a `nightly_loop`. Nace en `mode: off`.
- [x] Correr `python -m pytest worker/tests/test_market_stats.py worker/tests/test_rescore_schedule.py -q`.

## Task 8: retención (tests primero)

Files: `worker/pipeline/retention.py`, `worker/tests/test_market_stats_postgres.py`.

- [x] Escribir tests que fallen: `purge_market_stats()` borra `market_stats` con `week_start` anterior a `retention.market_stats_weeks` (26) semanas y las corridas viejas de `market_stats_runs`, conserva las recientes, y devuelve el conteo; si falta la clave usa 26.
- [x] Implementar `purge_market_stats()` en `worker/pipeline/retention.py` (mismo estilo que `purge_raw_pages`, leyendo `db.get_config("retention", {})`) y llamarla **al final de cada corrida `write`** desde `run_market_stats`. No editar `rescore.py`.
- [ ] Correr `python -m pytest worker/tests/test_market_stats_postgres.py -k purge -q`.

## Task 9: verificación y cierre

- [ ] `python -m pytest worker/tests -q -m "not db"` verde; con `TEST_DATABASE_URL`, suite completa (`python -m pytest worker/tests -q`) y `npx supabase test db` verdes; `cd web; npm test; cd ..` verde con los tipos regenerados.
- [x] Revisar que ningún texto nuevo contenga `FORBIDDEN_TERMS` («vale», «valor real», «precio real», «tasación», «tasado») ni diga «se vendió» (usar «dejó de publicarse»).
- [x] `graphify update .` desde la raíz.
- [ ] Abrir PR de `claude/f03-market-stats-fase0` a `main` con el resumen y la lista de «Tareas de Juan». No mergear ni desplegar sin su OK.
- [ ] **Operación, solo con OK de Juan en cada paso** (no ejecutar por iniciativa propia): (1) aplicar la migración a producción en transacción + versión exacta tras releer `max(version)`; (2) desplegar el worker con `wait_idle` (con `mode: off` no cambia nada); (3) `python -m tools.backfill_zones --dry-run` en el VPS (`sudo -u automotive`, venv del worker) para medir cobertura real por fuente (meta ≥ 90 % de activos con región; si es menor, solo se publica `todas`), luego sin `--dry-run`; (4) `python -m tools.market_stats --week --dry-run` y revisar el informe (distribución de `price_n`, % sin zona, proyección de tamaño contra el presupuesto de 100 MB, rendimiento de `listing_unconfirmed()` sobre ~25 mil avisos); (5) `mode: dry_run` programado dos semanas; (6) `write_enabled: true` y `mode: write`.
- [ ] Marcar F-03 Fase 0 como entregada en `docs/BACKLOG_PRODUCTO_2026-10.md` y en el plan por fases al mergear (el plan por fases vive hoy en la rama de H-01).
- [ ] Si la primera escritura real es el lunes 9/11 (semana 45), las cuatro semanas que piden PAR-03 y PRO-02 se cumplen el lunes 30/11 (semanas 45 a 48); cada semana de demora corre esa fecha.

## Rollback

`app_config.market_stats.mode = 'off'` (desde `/admin/config`, sin deploy) apaga el job. Si hace falta sacar todo: `drop table public.market_stats, public.market_stats_runs, public.listing_zones;`, borrar las filas `market_stats` y `market_zones` de `app_config` y la clave `market_stats_weeks` de `retention`, y revertir las líneas de `main.py` y `retention.py`. Nada de producción depende de estas tablas; las migraciones viejas y `comparables()` no se tocaron.

## No verificado al escribir el plan

- Contenido real de `app_config.comparables.confirm_sources` en producción, cobertura actual de coordenadas y `body_type` por fuente, cantidad de avisos `gone`, `max(version)` de producción y tamaño real de la base.
- Que `npx supabase migration up` sea el comando exacto de tu CLI local (el README documenta `start`, `db reset` y `test db`); si no, usar `npx supabase db reset`.
- Que el deploy del VPS incluya `worker/normalization/data/` (es parte de `worker/`, pero conviene confirmarlo en el primer despliegue).
- Consistencia de mayúsculas de `make`/`model` en `listings` (el plan agrupa por `lower()`).
- Que el pgTAP no choque con `app_config` ya sembrado localmente si otra rama definió las mismas claves.

# F-03 Fase 0 · Zona por aviso y `market_stats` semanal (dry-run)

Ítem F-03 del [backlog de producto](../../BACKLOG_PRODUCTO_2026-10.md) y Fase 0 del [plan por fases](../../PLAN_FASES_BACKLOG_PRODUCTO_2026-10.md). Estado: **borrador para que Juan lo apruebe**; nada implementado, ninguna migración aplicada, nada tocó producción.

Alcance: dos piezas sin UI ni gating, para empezar a acumular semanas de datos mientras se hace el resto de la Fase 1. (1) Una región por aviso. (2) La tabla `market_stats` y un job semanal idempotente que arranca en dry-run. Primera entrega **sin** `drop_share`, `median_total_drop_pct` ni `demand_count`. No cambia scores, comparables, alertas ni qué ve cada plan. Decisión ya tomada por Juan: la zona es **región**, no provincia.

## Qué existe hoy (verificado en el repo)

- `listings` (`supabase/migrations/20260927120000_core_schema.sql`) no tiene provincia ni región: solo `location_text`, `lat`, `lon`. Sí tiene `first_seen_at`, `last_seen_at`, `status` (`active|gone`), `published_at`, `price_usd`, `price_partial`, `probable_repost_of`, `attributes` y, desde `20261030120000_body_type.sql`, `body_type`. No existe `gone_at`.
- `last_full_seen_at` (listings) y `last_full_read_at` (crawl_targets) vienen de `20261106120000_comparables_full_read.sql`. `app_config.comparables` trae `confirm_sources`, `confirm_grace_hours` (36), `max_age_days` (30) y `gone_max_age_days`.
- **`status = 'gone'` casi no se usa para esto**: solo lo escribe `mark_gone()` (`worker/db/repos/listings.py:228`) desde `pipeline/enrich.py` y `pipeline/watchlist.py`, que revisan guardados, seguidos y avisos con match. La confirmación de que un aviso dejó de publicarse es otra: `public.listing_unconfirmed(...)` (misma migración) devuelve targets cuya última lectura completa pasó `grace` después de la última vez que se vio el aviso. No guarda cuándo.
- `normalization/geo.py`: `geocode_location()` resuelve texto a lat/lon (tabla `KNOWN_LOCATIONS`, caché, Nominatim); `clean_location_text()`; `SOURCE_DEFAULT_LOCATIONS` (solo `rosariogarage` → «Rosario, Santa Fe»). **No devuelve provincia.** `tools/backfill_geo.py` ubica avisos sin coordenadas.
- Varias entradas de `KNOWN_LOCATIONS` son de nivel provincia (`_PROVINCE_FALLBACKS`) y «buenos aires» cae en las coordenadas de CABA. Un aviso cuyo texto es solo «Buenos Aires» queda con coordenadas de CABA.
- `web/lib/data/argentina-locations.json` (268 KB, Georef): 24 provincias (códigos INDEC), 4.022 localidades con lat/lon y departamento. Los 24 partidos del GBA están como departamentos de la provincia `06`; CABA es la provincia `02` con 15 comunas. `web/lib/argentina-locations.ts` solo sirve a los formularios; el worker no tiene copia.
- `worker/pipeline/retention.py`: `purge_stale_listings()` y `purge_raw_pages()` (clave `app_config.retention`; `raw_page_days` se agregó con `jsonb_set` en `20261006120000`). Se llaman desde el tramo anclado de `nightly_loop` (`pipeline/rescore.py:139`).
- `collector_runs.source` es `NOT NULL references sources(id)` y `finish_run()` actualiza `sources.consecutive_failures`. `pipeline_errors (stage, ref, error)` sí se puede usar tal cual (`log_error()` en `db/repos/runs.py`).
- `main.py` lanza los loops con `asyncio.create_task(...)` (líneas 150-166), incluido `nightly_loop`.
- `/admin/config` lista toda fila de `app_config` con un editor JSON genérico (`web/components/admin/config-editor.tsx`), sin deploy.
- `listing_snapshots` guarda un snapshot por cambio (`price`, `currency`, `price_usd`, `fx_rate`, `change_kind`).
- pgTAP en `supabase/tests/*.sql` (patrón RLS: `product_feedback_test.sql`); `tools/test_db.py` copia `sources`, `app_config` y `vehicle_catalog` a `automotive_test`.

### Correcciones al backlog

1. **No hay columna `province`**; el backlog la da por existente. Hay que derivarla.
2. **«Fila en `collector_runs`» no sirve**: la FK a `sources` obligaría a crear una fuente falsa que aparecería en `/admin/sources` y en el aviso de salud. Se usa una tabla propia (opción que el propio backlog admite) y `pipeline_errors` para errores.
3. **«`gone` confirmado por lectura completa» no es `status = 'gone'`** (ver arriba). Se usa `listing_unconfirmed()`, y la fecha de baja es una estimación.
4. La lista de 7 `confirm_sources` del backlog no está en ninguna migración (la migración `20261106` solo agrega `mercadolibre` si la clave ya existe): vive en `app_config` de producción. El job la lee en cada corrida; no se copia a una constante.
5. El backlog dice «nocturnos»; el criterio y la Fase 0 piden semana ISO. El job es **semanal**.

## Decisión de diseño

1. **Región por aviso en tabla auxiliar, no columna.** `listing_zones` (1 fila por aviso, `on delete cascade`) guarda solo hechos geográficos: `province_id` (INDEC), `department`, `locality_id`, `dist_km` a la localidad usada, `precision` (`locality | province | source_default`), y las `lat/lon` con las que se derivó. La **región se calcula al armar las estadísticas** a partir del mapa de `app_config`, no se guarda en el aviso: editar el mapa no obliga a reescribir 12 mil filas. Por qué no una columna en `listings`: es la tabla caliente, hay funciones `returns setof public.listings` (`comparable_listings`) y vistas con `l.*` que conviene no tocar en una fase pensada para no chocar, y `ingest.py` pisa columnas en cada reingesta. La tabla auxiliar se borra sin dejar rastros si se descarta.
2. **Cómo se deriva.** Función pura nueva `normalization/zone.py` (sin I/O): con las `lat/lon` del aviso busca la localidad Georef más cercana (haversine, con caché por coordenada: unos cientos de puntos distintos contra 4.022 localidades, sin llamadas externas) y toma su provincia y departamento. `precision = 'province'` cuando el texto limpio es un nombre de provincia o «argentina»; ahí la región solo se asigna si la provincia cae entera en una región (con «Buenos Aires» a secas queda sin región, para no inflar AMBA con la coordenada de CABA). Un aviso sin lat/lon no tiene fila. Los datos de localidades se copian a `worker/normalization/data/ar_localities.json` con un test que exige que sea idéntico al de `web/lib/data/` (no se lee la ruta de la web: no verifiqué que el deploy del VPS la incluya).
3. **Cuándo se deriva (sin tocar `ingest.py`).** `tools.backfill_zones [--dry-run]` (mismo estilo que `backfill_geo`) para la carga inicial, e idéntica función `sync_zones()` al comienzo de cada corrida del job: inserta los avisos sin fila y re-deriva los que cambiaron de `lat/lon`. Incluye avisos `gone` (los necesita la medición de días). Un hook en `ingest.py` queda para más adelante, si hace falta.
4. **Mapa de regiones en `app_config.market_zones`** (editable en `/admin/config`). Forma: `version` (entero que se sube cuando cambia la composición de alguna región), `regions` (clave → etiqueta) y `rules`, lista ordenada donde gana la primera que coincide: `{region, province, departments?}`. Un test valida que las 24 provincias queden cubiertas, que las claves existan, que cada departamento exista en el JSON de Georef y que las etiquetas pasen el lint de copy. **Propuesta inicial (a confirmar por Juan):**

   | Región | Incluye |
   |---|---|
   | `amba` · AMBA | CABA (`02`) + los 24 partidos del GBA de la provincia `06` (Almirante Brown, Avellaneda, Berazategui, Esteban Echeverría, Ezeiza, Florencio Varela, General San Martín, Hurlingham, Ituzaingó, José C. Paz, La Matanza, Lanús, Lomas de Zamora, Malvinas Argentinas, Merlo, Moreno, Morón, Quilmes, San Fernando, San Isidro, San Miguel, Tigre, Tres de Febrero, Vicente López) |
   | `buenos_aires_resto` · Resto de Buenos Aires | el resto de la provincia `06` (incluye La Plata, Costa Atlántica, Escobar, Pilar) |
   | `cordoba` · Córdoba | `14` |
   | `litoral` · Litoral | Santa Fe `82`, Entre Ríos `30` |
   | `nea` · NEA | Corrientes `18`, Misiones `54`, Chaco `22`, Formosa `34` |
   | `cuyo` · Cuyo | Mendoza `50`, San Juan `70`, San Luis `74` |
   | `noa` · NOA | Salta `66`, Tucumán `90`, Jujuy `38`, Santiago del Estero `86`, Catamarca `10`, La Rioja `46` |
   | `patagonia` · Patagonia | Neuquén `58`, Río Negro `62`, Chubut `26`, Santa Cruz `78`, Tierra del Fuego `94`, La Pampa `42` |

   Las pertenencias discutibles (La Rioja, La Pampa, La Plata y el GBA ampliado) son una propuesta mía, no un dato oficial.
5. **Qué agrega `market_stats`.** Una fila por (semana ISO, tipo de grupo, grupo, banda de año, zona). Tipo de grupo `model` (marca + modelo) o `body_type` (carrocería, para las búsquedas sin modelo; ignora los avisos con `body_type` nulo). Banda de 2 años alineada a pares (`year_from = año − año % 2`, ej. 2018-2019); avisos sin año quedan fuera. Zona: cada región más la fila `todas`, que **incluye también los avisos sin región**, de modo que la suma de las regiones es ≤ `todas` y el job informa cuántos quedaron sin zona, por fuente. Semana ISO de lunes 00:00 a domingo, hora de Argentina.
6. **Definición de cada métrica** (todas excluyen reposts, `probable_repost_of is not null`, igual que el pool de comparables):
   - `active_count`: `status = 'active'`, visto en los últimos `comparables.max_age_days` y, si la fuente está en `confirm_sources`, no «sin confirmar» según `listing_unconfirmed()`. `active_confirmed_count`: cuántos de esos vienen de fuentes de `confirm_sources` (las demás pueden estar inflando el conteo hasta 30 días: Facebook, V6, Kavak, Autocosmos; se dice, no se corrige).
   - `new_count`: `first_seen_at` dentro de la semana, sin `attributes._not_news` (ese marcador, de `pipeline/news.py`, evita contar como novedad el stock viejo de un target recién arrancado).
   - `gone_count` y días: **solo** fuentes de `confirm_sources` con `listing_unconfirmed()` no vacío. Fecha de baja estimada = `greatest(last_seen_at, last_full_seen_at)` (cota inferior; el error máximo es el intervalo entre lecturas completas del target). Días hasta dejar de publicarse = baja estimada − `coalesce(published_at, first_seen_at)`; se descartan los avisos sin `published_at` marcados `_not_news` (su `first_seen_at` es el arranque del rastreo, no la publicación) y los negativos. El campo `days_source` queda en `confirm_sources`. «Dejó de publicarse» no se presenta como «se vendió».
   - Mercado Libre antes del 24/10/2026 (`app_config.market_stats.confirm_since.mercadolibre`): no tenía lectura completa, así que sus bajas no se detectaban y los que quedaban eran sesgados. Sus bajas con última vista anterior a esa fecha no entran en `gone_count` ni en días.
   - Precios: sobre avisos activos con `price_usd > 0` y `not price_partial`: `price_n`, mediana, p25 y p75 (interpolación lineal, como `percentile_cont`). Días: `days_n`, mediana, p25 y p75. Por debajo de `app_config.market_stats.min_n` (`price` 8, `days` 5) los percentiles quedan en null y los conteos se guardan igual.
7. **Dónde vive el cálculo.** SQL solo para traer filas planas (un aviso por fila, con sus banderas de confirmación y la provincia/departamento de `listing_zones`) y para el upsert; la agregación es una función pura de Python (`pipeline/market_stats.py`), testeable offline. La clave única es `(week_start, group_kind, make, model, body_type, year_from, zone)` con `unique nulls not distinct` (precedente: `vehicle_catalog_unique`), así que repetir una semana **reemplaza** sus filas: idempotente. Cada corrida recalcula también las `recompute_weeks` (2) anteriores, porque las bajas se confirman unos días después de la última vista.
8. **Corridas y errores.** Tabla propia `market_stats_runs` (semana, modo `dry_run|write`, inicio/fin, estado, filas calculadas/escritas, avisos leídos, % sin zona por fuente, parámetros usados, error). Errores a `pipeline_errors` con `stage = 'market_stats'` vía `log_error()`. El CLI `--dry-run` no escribe nada (ni la corrida): imprime el informe. El modo programado `dry_run` sí deja una fila de corrida con 0 filas escritas, para ver que el job anda.
9. **Cómo se lanza.** `python -m tools.market_stats --week [2026-W44] --dry-run` (sin valor, la última semana cerrada). Sin `--dry-run` hay que pasar `--write`, y solo funciona si `app_config.market_stats.write_enabled` es `true` (lo prende Juan). Programado: `market_stats_loop(stop)` en el mismo archivo, con una línea de import y un `create_task` en `main.py` (como `digest_loop`); corre el lunes a la hora de `market_stats.schedule` y respeta `mode`: `off` (no hace nada), `dry_run`, `write`. Nace en `off`.
10. **Semanas pasadas.** No se reconstruyen bien y no se promete: el estado de un aviso se pisa (`last_seen_at`, `status`), la retención borra avisos no vistos a los 180 días, `listing_snapshots` solo guarda cambios (sirve para precios, no para saber si el aviso seguía publicado) y Mercado Libre estuvo sesgado hasta el 24/10. El job rechaza semanas anteriores a `recompute_weeks` salvo `--retro`, que escribe únicamente `new_count` y `gone_count` (calculables desde `first_seen_at` y la baja estimada), con `basis = 'retro'`, y deja precios y `active_count` en null. Propuesta: no usar `--retro` y empezar a acumular desde la primera corrida real.
11. **Retención.** `purge_market_stats()` en `pipeline/retention.py`, con `app_config.retention.market_stats_weeks = 26` (se agrega con `jsonb_set` si falta, como `raw_page_days`). Se llama al final de cada corrida `write`, sin editar `rescore.py`. Borra también corridas viejas.
12. **Acceso.** RLS activado en las tres tablas nuevas, `revoke all` a `public, anon, authenticated`, `grant all` a `service_role`. Una política de lectura solo para `profiles.role = 'admin'` en `market_stats` y `market_stats_runs` (para inspeccionar en `/admin`, como `product_feedback`); `listing_zones` sin política. Ningún usuario lee directo. Cuando haya consumidores (PAR-03, PRO-02, PRO-04) entran por funciones `security definer set search_path = ''` con `plan_feature()`; no en esta fase.

## Datos y migraciones

Una migración (la 1 de la cadena del plan), con timestamp **mayor a `20261118130000`**; hay que releer `max(version)` en producción antes de nombrarla. Encabezado `--` que cite este doc y F-03. Contenido:

- `listing_zones`, `market_stats_runs`, `market_stats` (campos de los puntos 1, 5, 6 y 8; `market_stats` suma `zone_map_version`, `as_of`, `computed_at`, `run_id`, `basis`), con índices por `(week_start, group_kind, zone)` y por `(make, model)`.
- Inserts idempotentes (`on conflict do nothing`): `app_config.market_stats` = `{mode: "off", write_enabled: false, min_n: {price: 8, days: 5}, year_band: 2, recompute_weeks: 2, confirm_since: {mercadolibre: "2026-10-24"}, schedule: {weekday: 1, hour: "06:00"}}` y `app_config.market_zones` (punto 4). `min_demand_n` (3) se reserva para la entrega de `demand_count`.
- `retention.market_stats_weeks = 26` con `jsonb_set` condicional.
- RLS y grants del punto 12. Después: `npm run gen:types` (único cambio en `web/`: el archivo generado; no hay código de web escrito a mano, así que `web/AGENTS.md` aplica recién cuando haya UI).
- Nada se edita de migraciones viejas ni de `comparables()`.

**Volumen (estimación gruesa, sin medir):** con ~12 mil avisos activos y 4 filas posibles por aviso por semana (modelo y carrocería, zona y `todas`), son del orden de 10 a 30 mil filas semanales; a 26 semanas, entre 260 y 780 mil filas, unos 50 a 150 MB. La base hospedada es el plan gratis de 500 MB. El dry-run imprime la proyección antes de activar la escritura, y hay una palanca: guardar solo las filas de zona con al menos `store_min_active` avisos (no existe todavía; se agrega si la proyección no entra).

## Cobertura esperada de zona por fuente (de leer el código y el doc de geocodificado; no consulté producción)

Base: `docs/PLAN_GEOCODIFICADO.md`, medido el 26/10/2026 sobre 11.937 activos, 19 % sin coordenadas, **antes** de `backfill_geo` (commit 5a30911). La cobertura actual hay que volver a medirla.

| Fuente | Qué trae | Zona esperada |
|---|---|---|
| deruedas, autocity, carone, kavak, mardelusados, v6 | 100 % con coordenadas (según el doc); autocity y carone ponen la sucursal | Alta; la región es la de la sucursal |
| mercadolibre | 146 de 4.170 sin coordenadas; texto «X - Bs.As. …» que `clean_location_text` ya convierte a «X, Buenos Aires» | Alta (~96 %); «Buenos Aires Interior» sin localidad queda sin región |
| autocosmos, usadossantafe | casi completas; «Barrio, Buenos Aires (A.M.B.A.)» ya se limpia | Alta |
| rosariogarage | 1.297 sin texto → `SOURCE_DEFAULT_LOCATIONS` («Rosario, Santa Fe») | Completa pero `precision = source_default`: todo Litoral |
| facebook | 491 de 1.164 sin coordenadas (373 eran CABA, corregidas luego; el resto, títulos o «Recién publicado») | Media; una parte queda sin región |
| gruporandazzo | 274 de 274 sin ubicación en el doc | **Nula** hasta que Juan cargue un default; no invento dónde opera |
| instagram | texto libre de la descripción | Baja y ruidosa |

Meta razonable: ≥ 90 % de los avisos activos con región. Si la medición real da menos, los recortes por zona no son confiables y solo se publica `todas`.

## Validación y operación

- **pytest offline:** `zone.py` (localidad más cercana, caché, provincia sin región, sin coordenadas, un caso por región, límites AMBA: San Isidro sí, Pilar no); mapa de regiones (24 provincias cubiertas, departamentos existentes, etiquetas sin términos prohibidos); agregación (percentiles contra valores a mano, mínimos `min_n`, banda de año, exclusión de reposts y de `_not_news`, `todas` ≥ suma de regiones, días solo de `confirm_sources`, descarte de ML anterior a `confirm_since`, `body_type` nulo ignorado); idempotencia (mismo input, mismas filas).
- **pytest contra `*_test`** (`python -m tools.test_db` después de migrar): traer filas con `listing_unconfirmed` real (fixtures de targets y lecturas completas, como `test_intelligence_postgres.py`), upsert doble sin duplicados, `purge_market_stats()`, `sync_zones()` con cambio de coordenadas, error de la corrida en `pipeline_errors`.
- **pgTAP** (`supabase/tests/market_stats_test.sql`): un usuario común cuenta 0 filas en las tres tablas, anon denegado, insert directo denegado, admin lee `market_stats` y `market_stats_runs`, `service_role` escribe, los CHECK de `group_kind` y la unicidad.
- **vitest / Playwright (desktop y 375 px):** no aplican, no hay UI. Los deberá cubrir la entrega que muestre algo.
- **Operación (con OK de Juan en cada paso):** 1) aplicar la migración (transacción + versión exacta + `max(version)` de producción); 2) desplegar el worker (`wait_idle` antes de reiniciar; con `mode: off` no cambia nada); 3) `tools.backfill_zones --dry-run` en el VPS para medir cobertura real por fuente, luego sin `--dry-run`; 4) `tools.market_stats --week --dry-run` y revisar el informe (distribución de `price_n`, % sin zona, proyección de tamaño, filas con muestra suficiente); 5) pasar a `mode: dry_run` programado un par de semanas; 6) prender `write_enabled` y `mode: write`. Rollback: `mode: off` y, si hace falta, `drop table` de las tres tablas (nada de producción depende de ellas).
- Si la primera escritura real es el lunes 9/11 (semana 45), las cuatro semanas que piden PAR-03 y PRO-02 se cumplen el lunes 30/11 (semanas 45 a 48). Cada semana de demora corre esa fecha.
- Después de cambiar código: `graphify update .`.

## Entregas siguientes (no entran en la Fase 0)

- **`drop_share` y `median_total_drop_pct`:** desde `listing_snapshots` (`change_kind = 'price'`), comparando precio en la moneda original para que un cambio de dólar no cuente como baja. Se suman columnas en una migración propia; las semanas ya guardadas quedan en null.
- **`demand_count`:** búsquedas activas que coinciden con el grupo y la zona; siempre agregado, nunca visible por debajo de `min_demand_n` (3) y sin identificadores. Necesita la zona del origen de cada búsqueda (`search_profiles.origin_lat/lon`; el campo `location_label` que cita el backlog no existe).
- **Consumo:** funciones con gating (`model_stats`) y copy con «publicaciones comparables»; sin UI en este diseño.

## Lo que no pude verificar

- Contenido real de `app_config.comparables.confirm_sources` en producción (el backlog lista 7 fuentes; la memoria del proyecto dice 6 más Mercado Libre).
- Cobertura de coordenadas y de `body_type` actual por fuente; cantidad de avisos `gone`; `max(version)` de producción; volumen y tamaño reales de la base.
- Que el deploy del VPS incluya `web/lib/data/` (por eso se copia el JSON).
- Fecha exacta del primer ciclo completo de lecturas de Mercado Libre (propongo el 24/10 según el plan; se confirma con `min(crawl_targets.last_full_read_at)` de esas fuentes).
- Rendimiento de `listing_unconfirmed()` sobre ~25 mil avisos en una sola corrida (la migración de comparables documenta trampas del planificador); se mide en el dry-run.
- Que las mayúsculas de `make` y `model` sean consistentes en `listings`; si no, el agrupamiento se hace por `lower()`.
- Exactitud geográfica de la localidad más cercana cerca de límites de provincia o de región (se mide con `dist_km` y un muestreo manual en el dry-run).

## Decisiones que necesita de Juan

1. ¿Aprobás la lista de 8 regiones y su composición (La Rioja en NOA, La Pampa en Patagonia, AMBA = CABA + 24 partidos, La Plata en «Resto de Buenos Aires»)?
2. Mínimos de muestra: 8 precios y 5 días de baja (propuesto, como el backlog). Banda de 2 años alineada a años pares y semana ISO lunes-domingo, hora de Argentina.
3. Zona en tabla auxiliar derivada de las coordenadas (propuesto) o columna en `listings`.
4. Semanas pasadas: sin `--retro` (propuesto) o también `new_count`/`gone_count` retroactivos.
5. Fecha desde la que Mercado Libre cuenta bajas: 24/10/2026 (propuesto).
6. Grupo Randazzo y otras fuentes sin ubicación: dejar sin región (propuesto) o cargar vos un default en `SOURCE_DEFAULT_LOCATIONS`. Rosario Garage queda con su default (Rosario).
7. Cronograma: lunes 06:00 hora de Argentina, dos semanas en `dry_run` antes de escribir (propuesto).
8. Presupuesto de base para `market_stats`: propuesto ≤ 100 MB a 26 semanas; si la proyección del dry-run lo supera, se guardan solo las zonas con muestra mínima.
9. OK para aplicar la migración en producción cuando esté lista, y para desplegar el worker con `wait_idle`.

## Siguiente paso

Con tu aprobación escribo el plan en `docs/superpowers/plans/2026-10-29-f03-market-stats-fase0.md` (tareas `- [ ]` con los comandos de prueba exactos, en este orden: mapa y `zone.py`, migración y pgTAP, `backfill_zones`, agregación, job y CLI, retención) y abro la rama `claude/f03-market-stats-fase0`.

# F-02 · Vendedor v2

Ítem F-02 del [backlog de producto](../../BACKLOG_PRODUCTO_2026-10.md) y Fase 2, fila 1, del [plan por fases](../../PLAN_FASES_BACKLOG_PRODUCTO_2026-10.md) (secciones 3, 4, 5 y 8). Estado: **borrador para que Juan lo apruebe**; nada implementado ni aplicado en producción. Plan de ejecución: [2026-10-30-f02-vendedor.md](../plans/2026-10-30-f02-vendedor.md).

## Alcance

Tres pasos, cada uno se puede frenar sin dejar nada a medias:

1. **Conteo y métrica.** Columna `listings.seller_listing_count` (avisos activos de los últimos 30 días por fuente y `seller_name` normalizado), recalculada por el nocturno, y métrica en `/admin/sources` con el % de `seller_type` y `seller_name` null por fuente. **Sin cambio visible** para usuarios; ningún score se mueve.
2. **`dealer_inferred` («posible agencia»).** Columna aparte `listings.dealer_inferred`; cuenta como agencia en la preferencia de vendedor (matching) y en el aviso de gastos; la ficha dice «Posible agencia (publica N autos)». **Mueve scores** de búsquedas con preferencia de vendedor (decisión de Juan): bump de `SCORING_VERSION`.
3. **Medianas por tipo en `price_ref`.** `dealer_median`, `dealer_n`, `private_median`, `private_n` sobre el mismo pool y el mismo nivel de la cascada. `diff_pct`, `median`, `n` y `level_used` no cambian: ningún score ni alerta se mueve. Solo datos (lo consume PRO-02); sin UI de usuario.

Fuera de alcance: filtro duro «solo particulares» (PRO-01), señal de riesgo `private_many_listings` (PAR-02, tras F-02), margen (PRO-02), mejorar la extracción de `seller_name`/`vendedor` en los collectors (posible F-02b si la métrica del paso 1 lo justifica).

## Estado actual (verificado en el repo, rama `claude/f02-vendedor`, HEAD `94908ab`)

- **Origen.** El contrato de collector trae `vendedor` (texto crudo) y `vendedor_nombre` (`worker/collectors/base.py:36,49`). `transmission.seller_type()` mapea a `private | dealer | None` (`worker/normalization/transmission.py:68-87`). `normalize_listing` guarda `seller_name` crudo y `seller_type` (`worker/normalization/listing.py:198-199`). Ambos están en `KEY_ATTRS` (`listing.py:31-32`): un cambio crea snapshot `attrs`. El fingerprint ya usa `normalize_text(seller_name)` (`listing.py:72`; `normalize_text` en `worker/normalization/normalize.py:36-40`: sin tildes, minúsculas, espacios colapsados). La detección de reposts compara `lower(seller_name)` en SQL, sin quitar tildes (`worker/db/repos/listings.py:181-182`).
- **Merge.** `seller_name` y `seller_type` son `_DESCRIPTIVE` en `worker/pipeline/ingest.py:51-52`: un valor vacío nunca borra y el lado autoritativo pisa. Una inferencia guardada en `seller_type` se perdería en la próxima reingesta (plan, nota 2).
- **Esquema.** `listings.seller_type text check (seller_type in ('private','dealer'))`, `seller_name text`, `source text` (`supabase/migrations/20260927120000_core_schema.sql:173-212`). Sin índice por vendedor. `listings` es legible por todo `authenticated` (`20260927120100_rls.sql:99`). `COLUMNS` del repo (`worker/db/repos/listings.py:18-24`) es la lista que escribe el pipeline: una columna fuera de esa lista **no la toca la ingesta**.
- **Cobertura por fuente (estructural, no medida).** `seller_type` siempre null en Mar del Usados e Instagram. `seller_name` siempre null en V6 y Usados Santa Fe, y null para particulares en deRuedas y Autocosmos. Kavak, Car One, Grupo Randazzo y Autocity: `seller_type = dealer` fijo y un único `seller_name` por fuente. Facebook pone `particular` salvo que el texto diga concesionaria (`worker/collectors/facebook.py:423`): un revendedor de Facebook hoy es `private`. Los porcentajes reales solo se ven con la métrica del paso 1 contra producción.
- **Consumidores de `seller_type`.** Worker: preferencia blanda en matching (`worker/intelligence/matching.py:348-353`: null → UNKNOWN «no informado», igual → OK, distinto → FAIL), completitud del score (`worker/intelligence/scoring.py:160`), copy (`worker/intelligence/copy.py:66-67,74`). Web: `DealerFeesNotice` solo con `=== 'dealer'` (`web/components/app/dealer-fees-notice.tsx:3-4`), hecho «Vendedor» de la ficha (`web/app/app/listings/[id]/page.tsx:180,186-189`), `SELLER` (`web/lib/copy.ts:116`), formularios con enum `'' | private | dealer` (`web/lib/search-form.ts:62`, `web/lib/assisted.ts:52`, `web/lib/types.ts:58`). Tarjeta, emails, Telegram y digest no muestran el vendedor. Ninguna función SQL lee `seller_type`.
- **`price_ref`.** `comparables()` vigente en `20261105120000_comparables_confirmed_pool.sql:174-231` (`language sql`, `set search_path = ''`, inlinea `comparable_listings`, que devuelve `setof public.listings` y por eso ve cualquier columna nueva). `PriceRef` (`worker/intelligence/comparables.py:27-55`) descarta claves que no conoce: sin campos nuevos ahí, las medianas por tipo no llegan a `matches.price_ref`. El score usa solo `n`, `median`, `diff_pct`, `median_km` (`scoring.py:74-85,104-113,190-200`).
- **Nocturno.** `nightly_loop` (`worker/pipeline/rescore.py:116-142`): `rescore_outdated` al arrancar; en cada slot `rescore_recent` (matches de avisos activos vistos en 14 días); en el slot ancla, retención.
- **Config/admin.** Las claves nuevas de `app_config` se insertan por migración (`on conflict do nothing`); `/admin/config` las lista solas, `validateConfigChange` (`web/lib/admin-config.ts:70-111`) valida por clave, `HINTS` (`web/app/admin/config/page.tsx:13-36`) las describe. El worker lee con `db.get_config` (caché 60 s). Precedente de métrica por fuente: vista `admin_source_health` (`security_invoker`, revocada a `anon`/`authenticated`) en `/admin/sources`.
- **No pude verificar:** porcentajes reales de null por fuente, cuántos vendedores pasan de 6 avisos, si `unaccent` está disponible en producción (el diseño no lo necesita), calidad real de `seller_name` en Facebook e Instagram.

## Decisiones de Juan (plan, sección 8)

- Un vendedor con **6 o más avisos activos en 30 días** (misma fuente y mismo `seller_name` normalizado) es `dealer_inferred`. Reemplaza el 4 propuesto en el backlog.
- Texto «posible agencia» con el motivo visible («publica 6 autos»).
- `dealer_inferred` **cuenta como agencia** en filtros y en el aviso de gastos.
- Umbral y ventana en `app_config.seller_classification`, editables en `/admin/config`.

## Decisiones de diseño

1. **Columnas aparte, no un tercer valor de `seller_type`.** El CHECK queda como está. Ampliarlo rompería el enum de los formularios, los `=== 'dealer'` y los `SELLER[...]`, y la ingesta lo pisaría. Columnas nuevas en `listings` (no en `attributes`): el nocturno las escribe con un `UPDATE` dirigido, la ingesta no las conoce (no están en `COLUMNS`), no hay carrera con el merge de `attributes` y llegan solas a `comparable_listings` (`o.*`), `rows_for_scoring` (`l.*`) y la ficha (`select('*')`). Se desvía del backlog («`attributes._seller` guarda la evidencia»): la evidencia es el conteo más la regla, y la regla vive en `app_config`. Son visibles para `authenticated` como el resto de `listings`; está bien porque la ficha las muestra.
2. **Normalización en Python, no en SQL.** La clave de agrupación es `(source, normalize_text(seller_name))`, la misma que el fingerprint. Evita depender de `unaccent` y de una función inmutable. Vacío tras normalizar → sin conteo. No se toca la comparación `lower()` de reposts (fuera de alcance; anotado como riesgo).
3. **Regla de precedencia.** `dealer_inferred = seller_listing_count >= min_listings and seller_type is distinct from 'dealer'`. Aplica aunque la fuente diga `private` o null (backlog: «aunque la fuente diga particular o null»), porque el caso que importa es Facebook, que marca todo como particular. Nunca baja un `dealer` explícito. Las fuentes de una sola tienda ya son `dealer`: no-op.
4. **Vendedor efectivo.** Un solo helper por lado: `effective_seller(listing)` en `worker/intelligence/seller.py` y `effectiveSeller(listing)` en `web/lib/seller.ts`: `'dealer'` si `seller_type = 'dealer'` o `dealer_inferred`; si no, `seller_type`. Todos los consumidores que «cuentan como agencia» pasan por ahí.
5. **Cuándo se recalcula.** En el slot ancla del nocturno, **antes** de `rescore_recent`, para que el rescore de esa noche ya vea la clasificación nueva. Solo escribe filas cuyo valor cambia (`is distinct from`). No crea snapshots (solo la ingesta los crea) ni eventos.

## Paso 1: conteo y métrica (sin cambio visible)

Migración `supabase/migrations/20261123120000_f02_seller_count.sql` (nombre provisorio; releer `max(version)` de producción antes de aplicar):

```sql
-- F-02 paso 1 (docs/superpowers/specs/2026-10-30-f02-vendedor-design.md).
-- Conteo por vendedor, config y métrica de cobertura. Sin RLS nueva, sin SCORING_VERSION.
alter table public.listings
  add column seller_listing_count integer,
  add column seller_classified_at timestamptz;

comment on column public.listings.seller_listing_count is
  'F-02: avisos activos vistos en app_config.seller_classification.window_days con la misma '
  'fuente y el mismo seller_name normalizado (normalize_text del worker). Lo escribe el nocturno.';

insert into public.app_config (key, value)
values ('seller_classification', '{"min_listings": 6, "window_days": 30}')
on conflict (key) do nothing;

create view public.admin_seller_coverage with (security_invoker = true) as
with cfg as (
  select case when jsonb_typeof(c.value->'min_listings') = 'number'
              then greatest((c.value->>'min_listings')::numeric, 1) else 6 end as min_listings
    from (select 1) one
    left join public.app_config c on c.key = 'seller_classification'
)
select s.id                                                              as source,
       s.name,
       count(l.id)                                                       as active,
       count(l.id) filter (where l.seller_type is null)                  as seller_type_null,
       round(100.0 * count(l.id) filter (where l.seller_type is null)
             / nullif(count(l.id), 0), 1)                                as seller_type_null_pct,
       count(l.id) filter (where l.seller_name is null)                  as seller_name_null,
       round(100.0 * count(l.id) filter (where l.seller_name is null)
             / nullif(count(l.id), 0), 1)                                as seller_name_null_pct,
       count(l.id) filter (where l.seller_listing_count >= cfg.min_listings) as over_threshold,
       max(l.seller_classified_at)                                       as classified_at
  from public.sources s
 cross join cfg
  left join public.listings l on l.source = s.id and l.status = 'active'
 group by s.id, s.name;

revoke all on public.admin_seller_coverage from anon, authenticated;
notify pgrst, 'reload schema';
```

Sin índice nuevo: el job lee activos de la ventana (índice `last_seen_at` parcial existente) y la vista es solo admin. Si el `EXPLAIN` de la Task 1 del plan lo pide, se discute aparte.

Worker:

- `worker/intelligence/config.py`: `DEFAULT_SELLER_CLASSIFICATION = {"min_listings": 6, "window_days": 30}` y `seller_classification(raw)` que valida (enteros, `min_listings >= 2`, `window_days` entre 1 y 180) y cae a defaults si no.
- `worker/pipeline/seller_classification.py`: `classify_sellers(now=None, dry_run=False) -> Summary`. Lee `id, source, seller_name, seller_type` de `status = 'active' and last_seen_at >= now - window`; agrupa por `(source, normalize_text(seller_name))`; escribe con un `UPDATE ... FROM unnest(ids, counts)` solo donde `seller_listing_count is distinct from` el nuevo valor; pone null en activos fuera de la ventana o sin nombre que tenían valor. Los `gone` conservan el último valor (evidencia congelada para el pool de comparables). Devuelve conteos por fuente.
- Repo: `worker/db/repos/sellers.py` (`window_rows`, `write_counts`, `clear_stale`).
- `worker/pipeline/rescore.py`: en el slot ancla, `classify_sellers()` antes de `rescore_recent()`, con su propio `try/except` y `log_error("seller_classification", "nightly", ...)`.
- CLI: `python -m tools.seller_classification --dry-run` imprime por fuente activos, grupos y avisos `>= min_listings`, sin escribir.

Web: `web/app/admin/sources/page.tsx` lee `admin_seller_coverage` y `web/components/admin/sources.tsx` suma una tabla «Vendedor por fuente» (Activos, % sin tipo, % sin nombre, Sobre el umbral, Calculado). `web/types/database.ts`: vista nueva y columnas nuevas de `listings` (Row/Insert/Update) a mano. `HINTS.seller_classification` y validador en `validateConfigChange`.

## Paso 2: `dealer_inferred` («posible agencia»)

Migración `supabase/migrations/20261123120100_f02_dealer_inferred.sql`:

```sql
-- F-02 paso 2. dealer_inferred aparte de seller_type (el CHECK no cambia).
alter table public.listings
  add column dealer_inferred boolean not null default false;

comment on column public.listings.dealer_inferred is
  'F-02: true si seller_listing_count >= app_config.seller_classification.min_listings y '
  'seller_type no es dealer. Cuenta como agencia en matching y en el aviso de gastos. Lo escribe el nocturno.';

create or replace view public.admin_seller_coverage with (security_invoker = true) as
-- misma definición del paso 1, con dos columnas nuevas al final:
--   count(l.id) filter (where l.dealer_inferred)                                   as dealer_inferred,
--   round(100.0 * count(l.id) filter (where l.seller_type is null and not l.dealer_inferred)
--         / nullif(count(l.id), 0), 1)                                            as seller_unknown_pct
...;
notify pgrst, 'reload schema';
```

`create or replace view` solo admite columnas nuevas al final: por eso el paso 1 deja `classified_at` último y el paso 2 agrega después. `seller_type_null_pct` (antes) y `seller_unknown_pct` (después de la inferencia) dan el «antes y después» que pide el backlog. Agregar una columna `not null default false` es solo metadato en Postgres 11+.

`classify_sellers` pasa a escribir también `dealer_inferred` con la regla de la decisión 3 (mismo `UPDATE`, condición `is distinct from` sobre las dos columnas). Un activo que baja del umbral vuelve a `false` esa noche.

### Cómo cuenta como agencia, consumidor por consumidor

| Consumidor | Hoy | Con F-02 |
|---|---|---|
| Matching, preferencia `seller_type` (`matching.py:348-353`) | compara `listing.seller_type` | compara `effective_seller(listing)`. Preferencia `dealer` + inferido → OK «vendedor posible agencia (publica 6 autos)». Preferencia `private` + inferido → FAIL «vendedor posible agencia (publica 6 autos), se prefiere particular». Null sin inferencia → UNKNOWN como hoy |
| Completitud del score (`scoring.py:160`) | `bool(seller_type)` | **sin cambio** (un inferido con tipo null sigue incompleto; limita cuánto se mueve el score) |
| `DealerFeesNotice` (`dealer-fees-notice.tsx`) | `sellerType === 'dealer'` | prop nueva `dealerInferred`; se muestra si `effectiveSeller(...) === 'dealer'` |
| Ficha, hecho «Vendedor» (`page.tsx:186-189`) | `SELLER[seller_type]`, nombre | `sellerLabel(listing)`: inferido → «Posible agencia (publica N autos)», nombre |
| Formularios de búsqueda, resumen, Telegram, LLM, `legacy_filters` | `'' \| private \| dealer` | sin cambio de valores (`dealer_inferred` es del aviso, no una preferencia). Pista bajo el select: «Incluye posibles agencias.» (propuesta) |
| Emails, digest, Telegram, tarjeta | no muestran vendedor | sin cambio |
| Collectors, `BaseScraper.matches_filters` | texto crudo | sin cambio |
| PRO-01 (futuro filtro duro) | — | debe usar el mismo helper; queda escrito en este diseño |

`SCORING_VERSION` pasa a `f2-v5-dealer-inferred`: al arrancar, `rescore_outdated` re-puntúa todo, así las razones viejas no quedan desfasadas. Se mueven solo matches de búsquedas con `preferences.seller_type` sobre avisos inferidos. Los ya insertados no generan alertas nuevas (`upsert_scored` solo alerta en inserts); un aviso nuevo sí puede entrar o no según el score nuevo. **Requiere el OK de Juan al bump** (regla transversal del plan) y un único bump por deploy.

### Copy

Aprobado por Juan: «posible agencia», motivo «publica N autos».

- Worker (`worker/intelligence/copy.py`): `SELLER_INFERRED = "posible agencia"`, `REASON["seller_inferred"] = "publica {n} autos"`; razones «vendedor posible agencia (publica 6 autos)» y «vendedor posible agencia (publica 6 autos), se prefiere particular».
- Web (`web/lib/copy.ts`): `SELLER_INFERRED = "Posible agencia"`, ficha «Posible agencia (publica 6 autos)». Con N = 1 no aplica (el umbral mínimo es 2), así que el plural es siempre correcto.
- **Propuestas para aprobar:** (a) si la fuente dice particular, agregar «; la publicación dice particular»; (b) pista del formulario «Incluye posibles agencias.»; (c) hint de `/admin/config` (abajo).

### Config

`app_config.seller_classification = {"min_listings": 6, "window_days": 30}`. Validador web: objeto con `min_listings` entero 2..100 y `window_days` entero 1..180; mensaje «min_listings debe ser un entero entre 2 y 100 y window_days entre 1 y 180.». El worker repite la validación y cae a defaults (el RPC `admin_update_setting` solo valida el tipo jsonb). Hint propuesto: «Vendedor v2 (F-02). min_listings: avisos activos del mismo vendedor y fuente para marcarlo «posible agencia» (6). window_days: ventana en días (30). Se aplica en el nocturno; mueve la preferencia de vendedor y el aviso de gastos, no las medianas generales.»

## Paso 3: medianas por tipo en `price_ref`

Migración `supabase/migrations/20261123120200_f02_price_ref_by_seller.sql`: `create or replace function public.comparables(...)` con la misma firma, `language sql stable set search_path = ''`, inlineando `comparable_listings` como hoy. Cambios exactos respecto de `20261105120000:174-231` (el resto del cuerpo, incluido el `where lv.n >= cfg.min_n or lv.rank = 3`, queda idéntico byte a byte):

```sql
  pool as (
    select o.price_usd, o.mileage_km,
           lower(o.trim) = lower(t.trim) and o.transmission = t.transmission as same_trim_transmission,
           o.transmission = t.transmission                                    as same_transmission,
           coalesce(o.seller_type = 'dealer' or o.dealer_inferred, false)     as is_dealer,
           coalesce(o.seller_type = 'private' and not o.dealer_inferred, false) as is_private
      from target t
     cross join public.comparable_listings(p_listing_id, p_year_tol, p_km_tol_pct, p_max_age_days) o
  ),
  levels as (
    select v.rank, v.level_used,
           count(p.price_usd)                                              as n,
           percentile_cont(0.5)  within group (order by p.price_usd)       as median,
           percentile_cont(0.25) within group (order by p.price_usd)       as p25,
           percentile_cont(0.75) within group (order by p.price_usd)       as p75,
           percentile_cont(0.5)  within group (order by p.mileage_km)      as median_km,
           count(p.price_usd) filter (where p.is_dealer)                   as dealer_n,
           percentile_cont(0.5)  within group (order by p.price_usd) filter (where p.is_dealer)  as dealer_median,
           count(p.price_usd) filter (where p.is_private)                  as private_n,
           percentile_cont(0.5)  within group (order by p.price_usd) filter (where p.is_private) as private_median
      ...
  )
  select jsonb_build_object(
           -- las 7 claves actuales, sin cambios, y:
           'dealer_median',  round(lv.dealer_median::numeric, 2),
           'dealer_n',       lv.dealer_n,
           'private_median', round(lv.private_median::numeric, 2),
           'private_n',      lv.private_n)
```

- Se calculan **en el nivel elegido** (mismas filas que `n`): `dealer_n + private_n <= n`; el resto es «sin dato». `count` da 0 (no null) en grupos vacíos; la mediana queda null con n = 0. No se ocultan medianas con pocos casos en SQL: el mínimo lo decide el consumidor (PRO-02 pide `dealer_n >= 5`).
- `comment on function` se re-declara con las claves nuevas. Los grants se conservan (`create or replace`).
- `PriceRef` suma `dealer_median`, `dealer_n`, `private_median`, `private_n` con default `None`; `to_json` redondea las medianas a 2; `from_json` las lee si están. Ningún cálculo de score las usa.
- `web/lib/types.ts` `PriceRef`: las cuatro claves opcionales. Sin UI de usuario en este paso; el inspector de `/admin` ya muestra el JSON.
- **Sin bump de `SCORING_VERSION`**: el rescore nocturno reescribe `price_ref` de los matches de avisos vistos en 14 días; los viejos quedan con 7 claves y los consumidores tratan las nuevas como opcionales. Si los pasos 2 y 3 salen en el mismo deploy, el bump del paso 2 re-escribe todo.

## Riesgos

- **Falsos «posible agencia»** por `seller_name` malo: Facebook toma la primera línea tras el encabezado del vendedor; Instagram, una etiqueta del caption; Mar del Usados, el texto del link de Instagram (puede ser la cuenta de la tienda, que en ese caso sí es agencia). Mitigación: el `--dry-run` y la métrica del paso 1 muestran los grupos antes de prender el paso 2; Juan revisa una muestra.
- **Falsos negativos:** fuentes sin `seller_name` (V6, Usados Santa Fe, particulares de deRuedas/Autocosmos) nunca se infieren. Un revendedor que cambia el nombre o reparte avisos entre fuentes no se agrupa (por diseño: misma fuente).
- **Scores que se mueven en el paso 2** para búsquedas con preferencia de vendedor; explícito, con bump y OK de Juan.
- **Desfase:** la clasificación se actualiza una vez por noche; un umbral editado en `/admin/config` se aplica en el próximo slot ancla.
- **Desacuerdo SQL/Python de normalización** (reposts con `lower()` y conteo con `normalize_text`): conocido, no se toca.
- **Rendimiento de `comparables()`:** las columnas nuevas vienen de `o.*` (sin join extra) y el plan sigue inlineado; se confirma con `EXPLAIN (ANALYZE)` antes/después en base `_test` (criterio: sin regresión mayor a 10 %).
- **Tipos a mano:** olvidar `web/types/database.ts` rompe `typecheck` (o deja `any`). `comparable_pool` hereda la fila de `listings`.
- **Tests de base que ya fallan en `main`** (`comparables_test.sql`, entre otros, según PAR-03): comparar contra la línea base, no exigir verde global.

## Qué NO cambia

- `listings.seller_type`, su CHECK, la ingesta, `KEY_ATTRS`, snapshots, fingerprint, detección de reposts.
- `diff_pct`, `median`, `p25`, `p75`, `median_km`, `n`, `level_used`; `price_component`, `km_component`, red flags, guards, umbrales de alerta.
- Completitud del score. Paso 1 y paso 3: ningún score ni alerta. Paso 2: solo la preferencia blanda de vendedor.
- Preferencias guardadas, formularios (valores), Telegram, LLM, emails, digest, tarjeta.

## Operación y rollback

- **Producción:** cada migración con OK explícito de Juan, en una transacción con el insert de su versión exacta, releyendo `max(version)` antes (hoy `20261122120100`). Worker con `wait_idle` antes de reiniciar. Deploy de la web en Vercel con su OK.
- **Orden:** paso 1 (migración + worker + web admin). Correr `--dry-run` en producción (solo lectura) y revisar la métrica unos días. Paso 2 (migración + worker con bump + web). Paso 3 (migración + worker). Cada paso se puede detener tras su deploy.
- **Rollback paso 1:** desactivar la llamada nocturna (revert del worker); las columnas quedan sin uso. Si hace falta, `drop view admin_seller_coverage; alter table listings drop column seller_listing_count, drop column seller_classified_at;` (antes del paso 2).
- **Rollback paso 2:** `update listings set dealer_inferred = false where dealer_inferred;` apaga el efecto sin deploy (el nocturno lo vuelve a prender: para dejarlo apagado, subir `min_listings` a 100 en `/admin/config`). Revert del worker vuelve a la versión anterior de `SCORING_VERSION` y re-puntúa.
- **Rollback paso 3:** re-aplicar el cuerpo de `20261105120000` (`create or replace`); `PriceRef` ignora claves faltantes.

## Tests

- pgTAP `supabase/tests/f02_seller_test.sql`: columnas y CHECK intacto (`'dealer_inferred'` en `seller_type` sigue fallando con 23514); fila `seller_classification` e idempotencia (re-correr el insert no pisa un valor editado); `authenticated` no lee `app_config` ni `admin_seller_coverage`; la vista cuenta bien con fixtures (null tipo, null nombre, sobre umbral, inferidos). Paso 3: `comparables()` con un pool de 3 agencias, 2 inferidos, 4 particulares y 2 sin dato: `dealer_n = 5`, `private_n = 4`, medianas esperadas, y `median/p25/p75/median_km/n/diff_pct/level_used` idénticos a la versión anterior (se guarda el resultado antes de aplicar el cuerpo nuevo dentro del test); grupos vacíos → `*_n = 0`, mediana null.
- Worker offline: `effective_seller`, copy (lint de `FORBIDDEN_TERMS`), matching con preferencia `dealer`/`private` y aviso inferido (OK/FAIL con el texto), `PriceRef` round-trip con y sin claves nuevas, validación de config.
- Worker `-m db`: fixtures con un mismo vendedor en 6 avisos (y 5 en otro, con tildes y mayúsculas distintas para probar la normalización): `classify_sellers` pone conteos y `dealer_inferred`; nunca toca `seller_type` ni `seller_name`; **no crea `listing_snapshots`** ni cambia `matches.score` en los pasos 1 y 3; un `dealer` fijo no se infiere; re-correr no escribe filas (idempotente); bajar del umbral vuelve a `false`; app_config se guarda y restaura con `clear_config_cache()`.
- Web vitest: `effectiveSeller`/`sellerLabel`, `DealerFeesNotice` con inferido, validador de config, vista admin.
- e2e: la ficha de un aviso inferido muestra «Posible agencia (publica 6 autos)» y el aviso de gastos (seed con modelo y fuente propios, para no mover `comparables.spec.ts`).

## Preguntas abiertas para Juan

1. **Precedencia con «particular» explícito.** El diseño marca «posible agencia» aunque la fuente diga particular (lo pide el backlog y es el caso Facebook). ¿Vale también para fuentes donde «particular» es una señal fuerte (deRuedas, Rosario Garage en detalle), o ahí gana la fuente?
2. **OK al bump de `SCORING_VERSION` en el paso 2** (re-puntúa todo al arrancar; solo cambian matches con preferencia de vendedor).
3. **Copy propuesto:** «; la publicación dice particular» en la ficha, «Incluye posibles agencias.» en el formulario y el hint de `/admin/config`.
4. **Medianas por tipo en la UI:** el paso 3 no las muestra; ¿se quedan solo para PRO-02 o se agrega una línea en la ficha (con mínimo de casos)?

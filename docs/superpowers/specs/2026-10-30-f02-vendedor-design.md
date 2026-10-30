# F-02 · Vendedor v2

Ítem F-02 del [backlog de producto](../../BACKLOG_PRODUCTO_2026-10.md) y Fase 2, fila 1, del [plan por fases](../../PLAN_FASES_BACKLOG_PRODUCTO_2026-10.md) (secciones 3, 4, 5 y 8). Estado: aprobado por Juan (30/10/2026, «Respuestas de Juan» al final); pasos 1 y 2 implementados en la rama, nada aplicado en producción. Plan de ejecución: [2026-10-30-f02-vendedor.md](../plans/2026-10-30-f02-vendedor.md). Revisión 2: incorpora las 18 observaciones de la crítica de `fb4fdcd`.

## Alcance

Tres pasos en orden. El 1 y el 2 se pueden frenar tras su deploy sin dejar nada a medias; **el 3 requiere el 2** (lee `dealer_inferred`; si el 2 se frena, el 3 sale con la variante «solo `seller_type`», ver Paso 3).

1. **Clave, conteo y métrica.** `listings.seller_key` (nombre normalizado, lo escribe la ingesta) con índice; `listings.seller_listing_count` (lo escribe el nocturno); tabla `seller_classification_runs`; métrica en `/admin/sources` con el % de `seller_type` y `seller_name` null por fuente. **Sin cambio visible**; ningún score se mueve.
2. **`dealer_inferred` («posible agencia»).** Columna aparte; se calcula **en la ingesta** para los grupos tocados (antes de puntuar) y en el nocturno para todos. Cuenta como agencia en la preferencia de vendedor y en el aviso de gastos; la ficha dice «Posible agencia (publica N autos)». **Mueve scores** de búsquedas con preferencia de vendedor: bump de `SCORING_VERSION` (ver «Bump»).
3. **Medianas por tipo en `price_ref`.** `dealer_median`, `dealer_n`, `private_median`, `private_n` en el nivel elegido de la cascada. `diff_pct`, `median`, `n`, `level_used` no cambian. Solo datos (lo consume PRO-02, solo Pro); sin UI.

Fuera de alcance: filtro duro «solo particulares» (PRO-01, solo Pro), `private_many_listings` (PAR-02), margen y medianas por tipo en la UI (PRO-02, solo Pro), aviso de gastos nuevo (PAR-01), mejorar la extracción de `seller_name` en collectors (posible F-02b según la métrica del paso 1), alinear la comparación `lower()` de reposts.

## Estado actual (verificado en el repo, rama `claude/f02-vendedor`)

La rama sale de `handoff/fase1-par03-par02` (27 commits sobre `main`; `main` llega a la migración `20261121120000`, el handoff a `20261122120100`). **El handoff se mergea a `main` antes del PR del paso 1.**

- **Origen.** El collector trae `vendedor` y `vendedor_nombre` (`worker/collectors/base.py:36,49`). `transmission.seller_type()` mapea a `private | dealer | None` (`worker/normalization/transmission.py:68-87`). `normalize_listing` guarda `seller_name` crudo y `seller_type` (`worker/normalization/listing.py:198-199`), ambos en `KEY_ATTRS` (`listing.py:31-32`). El fingerprint usa `normalize_text(seller_name)` (`listing.py:72`; `normalize_text` en `worker/normalization/normalize.py:36-40`: sin tildes, minúsculas, espacios colapsados; **conserva puntuación y emoji**). Reposts comparan `lower(seller_name)` (`worker/db/repos/listings.py:181-182`).
- **Merge.** `seller_name`/`seller_type` son `_DESCRIPTIVE` (`worker/pipeline/ingest.py:51-52`): un vacío nunca borra y el lado autoritativo pisa. Una inferencia guardada en `seller_type` se perdería en la próxima reingesta.
- **Esquema.** `seller_type text check in ('private','dealer')`, `seller_name text` (`20260927120000_core_schema.sql:173-212`); sin índice por vendedor; `listings` legible por `authenticated`. `COLUMNS` (`listings.py:18-24`) es lo que escribe la ingesta. Sin triggers en `listings`.
- **Ingesta → score.** `crawl.py:422` llama `ingest()` (commit) y después `news.classify` → `Scorer.prepare` lee la fila con `rows_for_scoring` (`listings.py:300`, `l.*`). La alerta `new_match` se deduplica por `match:<listing_id>`: si sale con el vendedor mal clasificado, no se corrige.
- **Cobertura por fuente (estructural).** `seller_type` siempre null en Mar del Usados e Instagram. `seller_name` siempre null en V6 y Usados Santa Fe. deRuedas detalle pone nombre solo a clientes (`deruedas.py:611`); Rosario Garage detalle no pone nombre (`rosariogarage.py:308`; el listado sí, para concesionarias, `:167-168`); Mercado Libre solo toma `.ui-pdp-seller-validated__title` (`mercadolibre.py:367`), casi siempre tiendas validadas. Facebook pone `particular` salvo que diga concesionaria (`facebook.py:423`) y toma como nombre la primera línea tras «Información del vendedor»; Instagram toma `vendedor|contacto|instagram: …`; Mar del Usados, el texto del link de Instagram.
- **Consumidores de `seller_type`.** Matching (`matching.py:348-353`: null → UNKNOWN, igual → OK, distinto → FAIL), completitud (`scoring.py:160`), copy (`copy.py:66-67,74`). Web: `DealerFeesNotice` con `=== 'dealer'` (`dealer-fees-notice.tsx:3-4`), hecho «Vendedor» (`listings/[id]/page.tsx:180,186-189`), `SELLER` (`web/lib/copy.ts:116`), formularios `'' | private | dealer`. Ninguna función SQL lo lee.
- **Alertas.** `notifications/engine.py`: `new_match`/`opportunity` por nivel del match nuevo; `price_drop` a un match solo si su nivel actual es ≥ `match`; el digest toma el top-N por score. `upsert_scored` alerta solo en inserts.
- **Nocturno.** `nightly_loop` (`worker/pipeline/rescore.py:116-142`): `rescore_outdated()` al arrancar; cada slot `rescore_recent` (activos vistos en 14 días); slot ancla, retención. Existe `rescore_listings(ids)` (`rescore.py:78`).
- **`price_ref`.** `comparables()` en `20261105120000_comparables_confirmed_pool.sql:174-231`; `PriceRef` (`comparables.py:27-55`) descarta claves desconocidas.
- **Config/admin.** `app_config` por migración (`on conflict do nothing`); `validateConfigChange` (`web/lib/admin-config.ts:70-111`); `HINTS` (`web/app/admin/config/page.tsx:13-36`); worker con `db.get_config` (caché 60 s). Precedente de registro de corridas: `market_stats_runs` (F-03).
- **No pude verificar:** porcentajes reales por fuente, cuántos vendedores pasan de 6, tamaño actual de `listings` en producción.

## Decisiones de Juan

- **6 o más avisos en 30 días** (misma fuente, mismo vendedor normalizado) → `dealer_inferred`. El significado exacto de la ventana queda como pregunta (abajo).
- Texto «posible agencia» con motivo visible («publica 6 autos»).
- `dealer_inferred` **cuenta como agencia** en filtros y en el aviso de gastos.
- Umbral y ventana en `app_config.seller_classification`, editables en `/admin/config`.
- PRO-01 y PRO-02 son solo Pro. Un bump de `SCORING_VERSION` aprobado para PRO-02; plan §2: uno por deploy.

## Decisiones de diseño

1. **Columnas aparte, no un tercer valor de `seller_type`.** El CHECK, los formularios y los `=== 'dealer'` quedan como están, y el merge no pisa la inferencia. Las columnas llegan solas a `comparable_listings` (`o.*`), `rows_for_scoring` (`l.*`) y la ficha (`select('*')`). Se desvía del backlog (`attributes._seller`): la evidencia es el conteo más la regla en `app_config`.
2. **Clave guardada.** `seller_key(name)` en `worker/normalization/seller.py`, en Python (sin `unaccent`):
   - `normalize_text`; después se borran `.` y `'` y el resto de la puntuación, símbolos y emoji pasan a espacio (queda `[a-z0-9 ]`), espacios colapsados: «Autos S.A.» y «Autos SA» → `autos sa`.
   - Solo dígitos (teléfono): se lleva al número nacional de 10 dígitos (sin `00`/+54, sin el 9 de celular tras el 54, sin el 0 del área, sin el 15 tras el área cuando sobran 2 dígitos), así «0341 15 555-1234» y «+54 9 341 555-1234» dan `tel:3415551234`; con 8 o más dígitos la clave es `tel:` + los últimos 10; con menos, sin clave.
   - **Stoplist** (coincidencia exacta tras normalizar), sin clave: largo < 3, `particular`, `dueno`, `dueno directo`, `vendedor`, `concesionaria`, `agencia`, `whatsapp`, `instagram`, `facebook`, `ver perfil`, `contacto`, `consultar`, `informacion del vendedor`. Constante en código (se amplía con lo que muestre el `--dry-run`).
   - La escribe el repo en `insert_listing`/`update_listing` a partir del `seller_name` **ya resuelto por el merge** (no se mergea sola). No está en `KEY_ATTRS`: no crea snapshots. El fingerprint no cambia.
3. **Conteo.** Por `(source, seller_key)`: `count(distinct coalesce(fingerprint, id::text))` de filas `status = 'active'` dentro de la ventana. Distintos fingerprints evitan contar dos veces el mismo auto publicado dos veces (el fingerprint ya incluye el vendedor); un repost probable no suma **solo mientras su original cuenta en el mismo grupo** (activo, misma clave, en la ventana): nunca se pierde la única copia viva. El conteo del grupo se escribe en **todas** sus filas activas; un grupo sin filas en la ventana queda en null. La corrida completa (arranque, nocturno, CLI) es la autoritativa: `news.classify` puede marcar reposts después de la ingesta, así que un conteo de la ingesta (paso 2) puede diferir hasta la próxima corrida.
4. **Ventana (propuesta, pendiente de Juan).** «Publicados (`coalesce(published_at, first_seen_at)`) en los últimos `window_days` días y todavía activos.» La versión anterior usaba `last_seen_at`, que en activos es casi siempre «ahora»: la ventana no filtraba nada y en Facebook (detección de vendidos débil) los activos viejos inflaban el conteo.
5. **Regla.** `dealer_inferred = enabled and seller_listing_count >= min_listings and seller_type is distinct from 'dealer'`. Aplica aunque la fuente diga `private` o null (caso Facebook). Nunca baja un `dealer` explícito.
6. **Vendedor efectivo, un helper por lado.** `effective_seller(listing)` (`worker/intelligence/seller.py`) y `effectiveSeller(listing)` (`web/lib/seller.ts`): `'dealer'` si `seller_type = 'dealer'` o `dealer_inferred`; si no, `seller_type`. **PRO-01 (filtro duro) y PAR-01 (reemplaza `DealerFeesNotice`) deben usarlo**; queda escrito en sus fichas del plan por fases al cerrar el paso 2.
7. **Cuándo se clasifica.** (a) Desde el paso 2, en la ingesta, después del commit de `ingest_rows` y antes de devolver a `crawl`/`enrich` (o sea, antes de puntuar), solo para los grupos `(source, seller_key)` de filas insertadas, cuya clave cambió, que volvieron a activas o cuyo `seller_type` entró o salió de `dealer` (p. ej. el detalle dice «dueño directo» donde la tarjeta decía concesionaria): una sentencia que usa el índice. Las filas viejas del grupo cuyo `dealer_inferred` cambió (o que, siguiendo inferidas, cambiaron de N) se re-puntúan **ahí mismo**, con `rescore_listings`, en el camino del crawl/enrich y antes de `process_batch`; el lote propio lo puntúa después el crawl. Si falla, `log_error("seller_classification", "ingest", …)`, se re-puntúa igual lo que ya se escribió y sigue (el nocturno corrige el resto). (b) Al arrancar el worker, **antes** de `rescore_outdated`. (c) En el slot ancla, antes de `rescore_recent`. (b) y (c) recorren todos los grupos y re-puntúan con `rescore_listings` las filas cuyo `dealer_inferred` cambió o que, siguiendo inferidas, cambiaron de N (el motivo guarda «publica N autos»); si una corrida falla a mitad, re-puntúa igual los lotes que ya commitearon. La misma SQL sirve para los tres: `write_groups(cx, source, keys | None, cfg)`.
8. **Escritura por lotes.** (b) y (c) escriben por fuente y en lotes de 2.000 grupos, cada lote en su transacción, ordenados por id; solo filas con `(seller_listing_count, dealer_inferred) is distinct from` el valor nuevo. El relleno de `seller_key` del paso 1 va en lotes de 1.000 ids (CLI `--backfill-keys`; el nocturno completa los activos que falten).

## Paso 1: clave, conteo y métrica

Migración `supabase/migrations/<versión>_f02_seller_count.sql` (versión: `max(version)` de producción releído justo antes, por encima de lo que hayan sumado PRO-01, PRO-02 o PAR-01):

```sql
-- F-02 paso 1 (docs/superpowers/specs/2026-10-30-f02-vendedor-design.md). Sin RLS nueva, sin SCORING_VERSION.
alter table public.listings
  add column seller_key text,
  add column seller_listing_count integer;
create index listings_seller_key_idx on public.listings (source, seller_key)
  where status = 'active' and seller_key is not null;

create table public.seller_classification_runs (
  id           bigint generated always as identity primary key,
  trigger      text not null check (trigger in ('startup', 'nightly', 'cli')),
  mode         text not null check (mode in ('dry_run', 'write')),
  started_at   timestamptz not null default now(),
  finished_at  timestamptz,
  status       text not null default 'running' check (status in ('running', 'ok', 'failed')),
  rows_read    integer, rows_written integer, inferred_changed integer,
  params       jsonb, error text);
alter table public.seller_classification_runs enable row level security;  -- sin policies: solo service role
revoke all on public.seller_classification_runs from anon, authenticated;

insert into public.app_config (key, value)
values ('seller_classification', '{"enabled": true, "min_listings": 6, "window_days": 30}')
on conflict (key) do nothing;

create view public.admin_seller_coverage with (security_invoker = true) as
-- por fuente: active, seller_type_null(_pct), seller_name_null(_pct), seller_key_null_pct,
-- over_threshold (seller_listing_count >= min_listings de la config, 6 si no es número).
...;
revoke all on public.admin_seller_coverage from anon, authenticated;
notify pgrst, 'reload schema';
```

`create index` sin `concurrently` (la migración va en transacción); con el tamaño actual de `listings` es un bloqueo corto, se mide en la Task 1 contra una base de tamaño parecido. `enabled` no tiene efecto en el paso 1 (no existe `dealer_inferred`).

Worker: `seller_classification(raw)` en `worker/intelligence/config.py` valida `enabled` booleano, `min_listings` entero **2..100**, `window_days` entero 1..180 (mismos límites que la web) y cae a defaults si no. `worker/normalization/seller.py` (`seller_key`), repo `worker/db/repos/sellers.py` (`write_groups`, `clear_stale`, `backfill_keys`, `start_run`/`finish_run`), `worker/pipeline/seller_classification.py` (`classify_sellers(trigger, dry_run=False)`), CLI `python -m tools.seller_classification [--dry-run] [--backfill-keys]` (por fuente: activos, grupos, avisos sobre el umbral, los 10 grupos más grandes con sus nombres crudos). `clear_stale`: activos sin clave o cuyo grupo ya no tiene filas en la ventana → `seller_listing_count = null` (en el paso 2, también `dealer_inferred = false`). Los `gone` conservan el último valor. `nightly_loop`: `classify_sellers("startup")` antes de `rescore_outdated()` y `classify_sellers("nightly")` antes de `rescore_recent()` en el slot ancla, cada uno con su `try/except` y `log_error`.

Web: tabla «Vendedor por fuente» en `/admin/sources` (Activos, % sin tipo, % sin nombre, % sin clave, Sobre el umbral) y «Calculado» = `max(finished_at)` de `seller_classification_runs` con `status = 'ok'` (la última corrida, no el último cambio). `web/types/database.ts` a mano; `HINTS.seller_classification` y validador.

## Paso 2: `dealer_inferred`

Migración `<versión>_f02_dealer_inferred.sql` (versión releída antes de este paso):

```sql
alter table public.listings add column dealer_inferred boolean not null default false;
-- Siembra con el conteo del paso 1, para que el rescore del bump ya vea la inferencia.
update public.listings l set dealer_inferred = true
  from (select coalesce((value->>'enabled')::boolean, true) as enabled,
               coalesce((value->>'min_listings')::int, 6) as min_listings
          from public.app_config where key = 'seller_classification') c
 where c.enabled and l.status = 'active' and l.seller_listing_count >= c.min_listings
   and l.seller_type is distinct from 'dealer';
create or replace view public.admin_seller_coverage ...;  -- misma vista + dealer_inferred y seller_unknown_pct al final
notify pgrst, 'reload schema';
```

La siembra es un `UPDATE` sobre los activos sobre el umbral (pocos); si la Task 6 mide más de unas decenas de miles de filas, se pasa a lotes desde el CLI. Además el worker clasifica al arrancar antes de `rescore_outdated` (decisión 7b): aun sin siembra, el rescore del bump sale con la inferencia.

`write_groups` escribe las dos columnas; `clear_stale` también pone `dealer_inferred = false`; con `enabled = false`, `classify_sellers` pone `false` en **todas** las filas (también `gone`, por el pool de comparables) y re-puntúa las afectadas. La razón «publica N autos» solo se arma con `dealer_inferred = true`, que implica N ≥ 2: nunca «publica null autos».

| Consumidor | Hoy | Con F-02 |
|---|---|---|
| Matching, preferencia (`matching.py:348-353`) | `seller_type` | `effective_seller`. Pref. `dealer` + inferido → OK «vendedor posible agencia (publica 6 autos)»; pref. `private` + inferido → FAIL «…, se prefiere particular»; null sin inferencia → UNKNOWN |
| Completitud (`scoring.py:160`) | `bool(seller_type)` | sin cambio |
| `DealerFeesNotice` | `sellerType === 'dealer'` | prop `dealerInferred`; `effectiveSeller(...) === 'dealer'`. PAR-01 hereda el helper |
| Ficha, «Vendedor» | `SELLER[seller_type]` | `sellerLabel`: inferido → «Posible agencia (publica N autos)» |
| Formularios, Telegram, LLM, `legacy_filters` | `'' \| private \| dealer` | sin cambio de valores |
| PRO-01 (filtro duro, Pro) | — | `effective_seller` / `effectiveSeller` |

**Efectos en alertas (no son reenvíos).** Para búsquedas que prefieren particular, un inferido baja de nivel: (a) un aviso nuevo de un grupo conocido entra con el nivel bajo desde la primera alerta (decisión 7a); (b) `price_drop` de un match existente sobre un inferido deja de salir si su nivel queda por debajo de `match`; (c) el top-N del digest cambia de orden. Con preferencia `dealer`, al revés. Los matches ya insertados no generan `new_match` nuevos (`upsert_scored` alerta solo en inserts). Un grupo que cruza el umbral en la ingesta marca también sus filas viejas; sus matches se re-puntúan al instante dentro de `ingest()` (decisión 7a), lo que suma latencia al crawl y corre `upsert_scored(backfill=True)` para esos perfiles a mitad del crawl; startup/nightly también re-puntúan al instante.

**Bump.** `SCORING_VERSION` cambia una sola vez por deploy. Si el paso 2 sale en el mismo deploy que PRO-02, **comparten una versión** (p. ej. `f2-v5-seller-margin`) y un solo rescore. Si sale solo, necesita su propio OK (pregunta 2).

**Decidido (Juan, 30/10):** el paso 2 hace el bump a `f2-v5-seller-margin` (`worker/intelligence/config.py`) y **PRO-02 lo reutiliza: no vuelve a cambiar `SCORING_VERSION`**. El paso 2 **no se despliega solo**: va en el mismo deploy que PRO-02.

Copy aprobado: worker `SELLER_INFERRED = "posible agencia"`, `REASON["seller_inferred"] = "publica {n} autos"`; web `SELLER_INFERRED = "Posible agencia"`. Config: hint «Vendedor v2 (F-02). enabled: prende la inferencia «posible agencia». min_listings: avisos del mismo vendedor y fuente (6). window_days: ventana en días (30). Se aplica en la ingesta y en el nocturno.»; mensaje del validador «enabled debe ser true/false, min_listings un entero entre 2 y 100 y window_days entre 1 y 180.».

## Paso 3: medianas por tipo en `price_ref`

Requiere el paso 2. Migración `<versión>_f02_price_ref_by_seller.sql` (versión releída antes): `create or replace function public.comparables(...)`, misma firma, `language sql stable set search_path = ''`, cuerpo de `20261105120000:174-231` con estos cambios y el resto idéntico:

```sql
  pool as (select o.price_usd, o.mileage_km, <igual que hoy>,
                  coalesce(o.seller_type = 'dealer' or o.dealer_inferred, false)      as is_dealer,
                  coalesce(o.seller_type = 'private' and not o.dealer_inferred, false) as is_private ...),
  levels as (select ..., count(p.price_usd) filter (where p.is_dealer) as dealer_n,
                  percentile_cont(0.5) within group (order by p.price_usd) filter (where p.is_dealer) as dealer_median,
                  <ídem private> ...)
  -- jsonb_build_object: las 7 claves actuales sin cambios + dealer_median, dealer_n, private_median, private_n
```

- `is_dealer` e `is_private` son excluyentes y cada uno exige `price_usd` contado en `n`, así que `dealer_n + private_n <= n` en cada nivel de la cascada; el test lo comprueba en los tres. `count` da 0 en grupos vacíos; la mediana, null. El mínimo de casos lo decide el consumidor (PRO-02: `dealer_n >= 5`).
- Variante si el paso 2 no salió: `is_dealer = coalesce(o.seller_type = 'dealer', false)`, `is_private = coalesce(o.seller_type = 'private', false)`; al salir el paso 2 se re-aplica con `dealer_inferred` (sin bump).
- `PriceRef` suma las cuatro claves con default `None`; ningún cálculo de score las usa. `web/lib/types.ts`: opcionales. **Sin bump**: el rescore nocturno las completa en los matches de los últimos 14 días; los viejos quedan con 7 claves.

## Riesgos

- **Falsos «posible agencia»** por nombres genéricos que pasen la stoplist. Mitigación: `--dry-run` con los 10 grupos más grandes por fuente y muestra revisada por Juan antes del paso 2; `enabled = false` lo apaga sin deploy.
- **Falsos negativos:** fuentes o vendedores sin nombre (V6, Usados Santa Fe, particulares de deRuedas, Rosario Garage detalle, Mercado Libre no validado) nunca se infieren; tampoco quien cambia de nombre o reparte entre fuentes.
- **Contención en la ingesta:** la sentencia de la decisión 7a corre en su propia transacción corta tras el commit, ordenada por id, para no alargar el lock de `ingest_rows` ni cruzar locks entre crawls concurrentes.
- **Desfase de N:** «publica N autos» queda en `match_reasons` hasta el próximo rescore; un `gone` conserva su último N. Aceptado.
- **`comparables()`:** `EXPLAIN (ANALYZE)` antes/después; criterio: sigue inlineado y menos de 10 % de diferencia.
- **Tests de base que ya fallan** (`comparables_test.sql`, entre otros): comparar contra la línea base.

## Qué NO cambia

`seller_type`, su CHECK, `KEY_ATTRS`, snapshots, fingerprint, detección de reposts; `diff_pct`, `median`, `p25`, `p75`, `median_km`, `n`, `level_used`, componentes del score, red flags, umbrales de alerta; completitud; valores de preferencias y formularios; emails, Telegram, tarjeta (no muestran vendedor).

## Operación y rollback

- **Producción:** cada migración con OK de Juan, en una transacción con el insert de su versión exacta, releyendo `max(version)` **antes de cada paso** y renombrando el archivo si otra migración quedó por encima. Worker con `wait_idle`; Vercel con su OK.
- **Orden:** handoff de Fase 1 mergeado → paso 1 (migración, worker, `--backfill-keys`, web admin); unos días de `--dry-run` y métrica → paso 2 → paso 3.
- **Rollback paso 1:** revert del worker; columnas, índice y tabla sin uso (o `drop` antes del paso 2).
- **Rollback paso 2:** `enabled = false` en `/admin/config` y reiniciar el worker (o esperar al slot ancla): todas las filas a `false` y sus matches re-puntuados (decisión 7). Revert del worker vuelve la versión anterior de `SCORING_VERSION` y re-puntúa todo.
- **Rollback paso 3:** re-aplicar el cuerpo de `20261105120000`; `PriceRef` ignora claves faltantes.

## Tests

- **pgTAP** `supabase/tests/f02_seller_test.sql`: columnas, índice parcial, CHECK intacto (`'dealer_inferred'` en `seller_type` → 23514); config e idempotencia del insert; `anon`/`authenticated` sin acceso a `app_config`, `seller_classification_runs` ni la vista; la vista con fixtures. Paso 3: pool de 3 agencias, 2 inferidos, 4 particulares, 2 sin dato → `dealer_n = 5`, `private_n = 4` y medianas, y **las 7 claves viejas comparadas con literales calculados a mano** (no se puede correr el cuerpo viejo tras aplicar la migración); fixtures que fuerzan los niveles 1, 2 y 3 con `dealer_n + private_n <= n` en cada uno; sin agencias → `dealer_n = 0`, mediana null; `prosecdef = false`, `search_path=""`, grants iguales.
- **Worker offline:** `seller_key` (tildes, «Autos S.A.»/«Autos SA», teléfonos con y sin `+54 9`, stoplist, emoji); validación de config (incluye `min_listings = 101` y `enabled` no booleano); `effective_seller`; matching OK/FAIL/UNKNOWN con textos; copy lint; `PriceRef` round-trip; `nightly_loop` llama `classify_sellers("startup")` antes de `rescore_outdated` y una excepción no impide el rescore; slot ancla sí, no ancla no.
- **Worker `-m db`:**
  - conteo: 6 avisos del mismo vendedor (tildes, mayúsculas, puntuación) → 6; dos filas con el mismo fingerprint cuentan 1; un repost probable no suma; un activo publicado hace 40 días no suma pero recibe el conteo del grupo; nombre en la stoplist → sin clave ni conteo; no toca `seller_type`, `seller_name`, `attributes` ni `listing_snapshots`; segunda corrida con `rows_written = 0` en `seller_classification_runs`;
  - paso 1 sin efecto: slot ancla (clasificar + `rescore_recent`) deja `matches.score` y `match_reasons` iguales a `rescore_recent` solo;
  - **ingesta**: 5 avisos activos de un grupo + búsqueda con preferencia `private`; se ingiere el 6.º por `ingest()` y se puntúa como en `crawl` → el match nuevo sale con FAIL «posible agencia» y la notificación `new_match` (si su nivel alcanza) no dice «vendedor particular»;
  - **startup**: conteos del paso 1, `dealer_inferred` en false, `SCORING_VERSION` nueva → tras la secuencia de arranque los matches tienen la versión nueva y la razón FAIL;
  - reset: un grupo que baja del umbral o pierde la clave vuelve a `false` con conteo null; `enabled = false` apaga todo y re-puntúa; `min_listings` 5 marca el grupo de 5; un `dealer` fijo nunca se infiere;
  - paso 3: `matches.price_ref` con las cuatro claves y `median`, `n`, `diff_pct`, `level_used`, `score` iguales a una corrida sin datos de vendedor.
- **Web vitest:** `effectiveSeller`, `sellerLabel`, `DealerFeesNotice` con inferido, validador (límites y `enabled`).
- **e2e:** ficha de un aviso sembrado con `dealer_inferred = true` y `seller_listing_count = 7` muestra «Posible agencia (publica 7 autos)» y el aviso de gastos (el N sale de la semilla; el test no espera que N cambie).

## Preguntas para Juan

1. **¿Qué cuenta como «6 avisos en 30 días»?** Propuesta: avisos **publicados en los últimos 30 días** (fecha de publicación, o la primera vez que lo vimos si la fuente no la da) **y todavía activos**. La alternativa, «activos vistos en los últimos 30 días», cuenta casi todo lo activo y en Facebook infla los números con autos ya vendidos. **Recomiendo la propuesta.**
2. **Cambio de versión del puntaje en el paso 2.** El paso 2 re-puntúa (cambia la preferencia de vendedor). Aprobaste un cambio para PRO-02 y la regla es uno por deploy. **Recomiendo** sacar el paso 2 junto con PRO-02 con un único cambio compartido; si el paso 2 sale antes, necesito tu OK para un cambio propio.
3. **«Posible agencia» aunque el aviso diga particular.** En la práctica solo pasa en Facebook (marca todo como particular), y en avisos de Rosario Garage donde el listado mostró el nombre de una agencia y el detalle dijo «dueño directo». En deRuedas, Rosario Garage (detalle) y Mercado Libre los particulares no traen nombre, así que nunca se marcan. **Recomiendo** que la marca gane igual, y agregar en la ficha «; la publicación dice particular».
4. **Textos propuestos.** Pista en el formulario de búsqueda «Incluye posibles agencias.» y la ayuda de `/admin/config` de la sección Paso 2. **Recomiendo** aprobarlos tal cual.

### Respuestas de Juan (30/10/2026): sí a todo

1. Ventana: avisos publicados (`coalesce(published_at, first_seen_at)`) en los últimos 30 días y todavía activos.
2. El paso 2 sale junto con PRO-02, con un único cambio de `SCORING_VERSION` compartido. El paso 2 no se despliega solo.
3. «Posible agencia» gana aunque la publicación diga particular, y la ficha agrega «; la publicación dice particular».
4. Textos aprobados tal cual: «Incluye posibles agencias.» en el formulario y la ayuda de `/admin/config`.

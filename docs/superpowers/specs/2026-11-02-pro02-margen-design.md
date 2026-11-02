# PRO-02 · Margen estimado (ciclo 1: margen v1 y umbral en USD)

Ítem PRO-02 del [backlog de producto](../../BACKLOG_PRODUCTO_2026-10.md) y Fase 2, fila 3, del [plan por fases](../../PLAN_FASES_BACKLOG_PRODUCTO_2026-10.md) (secciones 3, 4 y 8). Rama `claude/pro02-margen`, creada desde `origin/main` en `4f212bf`. Estado: **implementado en la rama (revisión 3: respuestas de Juan del 02/11 aplicadas)**, sin pushear ni aplicar en producción. Los cambios respecto de la revisión 1 están en «Implementación»; los de la revisión 3, en «Respuestas de Juan (02/11)».

## Alcance

Ciclo 1 = «margen v1 y umbral en USD»:

1. `matches.margin_ref` (jsonb) calculado por el worker en cada scoring/rescore, contra la mediana de agencias de `price_ref` (F-02 paso 3).
2. `app_config.dealer_margin` sembrada por la migración: acondicionamiento **5 % con mínimo USD 300** (decisión de Juan, plan §8).
3. Línea de margen en tarjeta, ficha y emails de Pro.
4. Orden «Mayor margen estimado» en resultados (solo Pro).
5. Umbral por margen: `search_profiles.opportunity_threshold_usd`, mínimo `plan_limits.pro.min_threshold_usd = 500`, con la misma regla que el umbral en % (inmediato, sin tope, no cuenta para el tope).
6. Eventos `margin_threshold_set` y `results_sorted_margin`.

Fuera de alcance: **rotación** («suele dejar de publicarse en ~N días»), que depende de F-03 y sale en el ciclo 2 (plan, Fase 3 fila 4). No hay copy, campo ni placeholder de rotación en este ciclo. Tampoco: margen en el digest, línea en la exportación CSV, margen para planes que no sean Pro, cascada propia de comparables para agencias, ítem en la tarjeta de planes.

Todo es **solo Pro**: una sola flag `plan_limits.pro.dealer_margin = true` gobierna la línea, el orden y el umbral (ver «Gating»).

## Estado actual (verificado en `4f212bf`)

- **Comparables por vendedor.** `public.comparables()` (`supabase/migrations/20261125120000_f02_price_ref_by_seller.sql`) devuelve, además de las siete claves de siempre, `dealer_median`, `dealer_n`, `private_median` y `private_n` **sobre el mismo pool y el mismo nivel de la cascada**, elegido por el `n` total. Agencia = `seller_type = 'dealer'` o `dealer_inferred`; particular = `'private'` y no inferido; los sin dato no están en ninguno. `PriceRef` (`worker/intelligence/comparables.py`) ya las lee; un `price_ref` anterior al paso 3 tiene solo siete claves. Nada del score las usa.
- **SCORING_VERSION.** `f2-v5-seller-margin` (`worker/intelligence/config.py:22`), ya desplegado. El comentario dice que PRO-02 lo reutiliza y no hace otro bump. Por eso el arranque del worker (`rescore_outdated`) **no** vuelve a puntuar los matches existentes: hay que rellenar `margin_ref` de otra forma (ver «Relleno sin bump»).
- **Rescore.** `pipeline/rescore.py`: `rescore()` arma un `Scorer`, evalúa y escribe con `matches_repo.upsert_scored(..., backfill=True)`; no crea notificaciones. Corre al arrancar (solo versiones viejas), cada `rescore.every_hours` (matches de avisos activos vistos en los últimos 14 días) y tras enriquecer.
- **Scorer.** `pipeline/scoring.py` carga config, cotización del día, filas (`rows_for_scoring`, `SELECT l.*`) y `price_ref` una vez por lote; `evaluate()` llama a `intelligence.engine.evaluate` (puro). `Evaluation.row()` define las columnas que se escriben; `matches_repo._EVALUATED` las lista.
- **Costo de transferencia (PAR-01).** `worker/intelligence/cost_estimator.py` (puro, sin defaults numéricos): `parse_config`, `search_zones`, `buyer_jurisdiction`, `build_input` (excluye precio parcial con `pipeline.ingest.published_partial`, moneda desconocida; dólar del aviso en ARS o última cotización guardada en USD si no supera `fx.max_age_days`) y `estimate`, que devuelve términos `arancel`, `sellos`, `formularios`, `patente` en ARS con `min`/`max`, `missing` con motivo (`no_zone`, `params`, `base`, `no_year`, `pre_min_year`, `no_fx`) y `rate`. La web tiene su gemela (`web/lib/cost-estimator.ts`) y calcula el costo en vivo.
- **Umbral en %.** `search_profiles.opportunity_threshold_pct` (1–90; migración `20261025120000_pro_threshold_export.sql`), leído por el worker solo con `plan_feature(user, 'threshold_alerts')` (`db/repos/notifications.py:_THRESHOLD`). `notifications/engine.py:classify`: si la búsqueda tiene umbral y el evento lo alcanza, `_Plan(..., capped=False, threshold=True)` y `payload.threshold_pct`; si no lo alcanza, va al digest (aunque la frecuencia sea inmediata). `sent_today` no cuenta las filas con `payload ? 'threshold_pct'`. El formulario usa `OpportunityThreshold` (`web/components/app/opportunity-threshold.tsx`) y `actions.ts` guarda el valor solo si `my_plan_feature('threshold_alerts')`.
- **Gating.** `plan_feature(user, key)` lee `plan_limits_for(user)->'limits'->>key = 'true'`; **los admins tienen todas las features** (también una que no existe en `plan_limits`). `my_plan_feature(key)` es la versión del usuario conectado.
- **Resultados.** `public.search_results(...)` (última definición en `20261119120000_x01_tracking.sql`) devuelve `setof match_cards` y ordena por `score`, `price`, `km` o reciente; un `p_sort` desconocido cae en el orden por fecha. `web/lib/sorts.ts` define las opciones y `SortSelect` empuja `?s=`.
- **Ficha.** `web/app/app/listings/[id]/page.tsx` lee los matches del aviso con un `select` explícito y toma `best` (mayor score). La tarjeta (`web/components/app/listing-card.tsx`) recibe líneas opcionales (`costLine`, `track`) calculadas en la página.
- **Eventos.** `web/lib/events.ts:track()` inserta en `public.events` (sin lista blanca ni CHECK de nombres). La única lista de nombres en la base es `human_events` dentro de `admin_decision_metrics` (actividad humana para el dashboard), que PRO-01 redefine.
- **Copy lint.** `FORBIDDEN_TERMS` en `web/lib/copy.ts` y `worker/intelligence/copy.py`; `web/lib/copy.test.ts` y `worker/tests/test_intelligence_copy.py` escanean el copy y permiten términos extra por bloque (PAR-01 agrega «precio final», «costo real», etc.).
- **Admin.** `/admin/config` es un editor JSON por clave con `HINTS` (`web/app/admin/config/page.tsx`) y `validateConfigChange` (`web/lib/admin-config.ts`); `plan_limits` tiene schema con claves conocidas y `.passthrough()`.

## Decisiones de diseño

### 1. Qué es el margen

```
asking_usd          = listings.price_usd (el precio efectivo: de contado si salió de la descripción)
reconditioning_usd  = max(asking_usd × pct / 100, min_usd)                 (dealer_margin.reconditioning)
transfer_usd        = (arancel + sellos + formularios) / dólar, en rango    (cost_estimator, PAR-01)
est_costs_usd       = reconditioning_usd + transfer_usd                     (rango)
acquisition_usd     = asking_usd + est_costs_usd                            (lo que cuesta comprar el auto, rango)
gross_margin_usd    = dealer_median − acquisition_usd                       (rango: min usa costos max)
gross_margin_pct    = gross_margin_usd / acquisition_usd × 100              (rango: min = margen min / costo max)
```

- **Contra qué.** `price_ref.dealer_median`, a nivel `price_ref.level_used`. Es la mediana de **precios publicados** por agencias, no de precios de venta: el copy lo dice.
- **Mínimo.** `margin_ref = null` si `price_ref` es null, si no tiene `dealer_n` (price_ref de siete claves) o si `dealer_median` no es positivo. Si `dealer_n < comparables.min_n` (el mismo `min_n`, hoy 5), `margin_ref = {v, status: "few_dealers", dealer_n, min_n, n, level_used}`: no hay margen pero la línea lo dice (pregunta 6, revisión 3).
- **Base del 5 %.** El precio de compra (`asking_usd`). Ver pregunta 2.
- **Porcentaje.** Sobre **lo que cuesta comprar el auto** (`acquisition_usd` = precio en USD + acondicionamiento + transferencia descontada), no sobre la mediana (decisión de Juan, pregunta 3). Como el margen baja cuando el costo sube, el extremo bajo es `margen_min / costo_max` y el alto `margen_max / costo_min`; vale también con margen negativo.
- **Patente.** No entra: es anual, no es parte de la transferencia. Tampoco deudas de patente ni multas (no las conocemos).
- **Precio parcial (PAR-03).** Un aviso con `price_partial` no genera match, pero uno cuyo precio publicado es un anticipo o una cuota y cuya descripción trae el precio de contado sí (`resolve_price` deja `price_partial = false` y `price_check.published_partial = true`). `build_input` excluye los dos y `margin.compute` los chequea con `published_partial` y devuelve null: nunca un margen sobre un anticipo. El relleno (§6) los excluye también, para converger. **Sin línea** (revisión 3): lo que falta es el precio, no las agencias, y la tarjeta y la ficha ya muestran el precio y su aviso de parcial; una línea más no agrega nada. Tiene prioridad sobre «pocas agencias».
- **Sin `price_usd`** (aviso en ARS sin cotización): null y sin línea, por la misma razón (el precio se ve en pesos).
- **Negativo.** Se guarda y se muestra (`USD -300`): para una agencia «la mediana de agencias está por debajo de lo que te costaría» es información. El orden lo deja al final de los positivos de forma natural.

### 2. Transferencia: solo con números reales y localidad conocida

Reglas de Juan: solo números con fuente; lo incierto va como rango hasta el resultado; si no se sabe la localidad, no se simula con otra zona.

- Se reutiliza PAR-01 tal cual: `cost_estimator.search_zones(profile)` (origen y `filters.extra_locations` de **la búsqueda del match**: el comprador es el Pro), `build_input(row, zones, fx_latest, cfg, today)` y `estimate(...)`. Del resultado se toman solo `arancel`, `sellos` y `formularios`, y se suman `min` con `min` y `max` con `max`. Vendedor: `effective_seller` del aviso (arancel y sellos dependen de él; sin dato, la unión de particular y agencia, como PAR-01).
- **Todo o nada.** La transferencia se descuenta solo si los tres términos están `ok` y hay dólar. Si no, `transfer_usd = null` y `transfer_status` dice por qué:
  - `no_zone`: la búsqueda no tiene localidad en Argentina (o una de sus zonas no se resuelve). Copy: «no descuenta la transferencia porque tu búsqueda no tiene localidad». **Nunca** se usa la tabla de otra jurisdicción.
  - `no_fx`: aviso en USD sin cotización vigente (las escalas están en pesos).
  - `params`/`base`: faltan parámetros en `cost_estimator`, o la base cargada no es el precio.
  - `disabled`: `dealer_margin.transfer.enabled = false`.
  - `no_official` / `no_official_some`: la búsqueda está (en todo o en parte) fuera de CABA y Buenos Aires (ver abajo).
  Sin descuento parcial (pregunta 4, confirmado).
- **Jurisdicción múltiple / AMBA**: el rango cubre todas (unión), igual que PAR-01, y el copy la nombra.
- **Fuera de CABA y Provincia de Buenos Aires** (decisión de Juan, pregunta 5): **no** se usa el rango «resto del país» de PAR-01 (Córdoba, Santa Fe y Mendoza). Si la búsqueda cae en otra provincia, `transfer.status = "no_official"` y no se descuenta: «no descuenta la transferencia porque no tenemos los valores oficiales de tu provincia».
- **Zona multi-jurisdicción con otra provincia** (p. ej. Palermo + Córdoba): se descuenta solo si **todas** las jurisdicciones de la búsqueda tienen valores oficiales (CABA, Buenos Aires). Si alguna no, `status = "no_official_some"`, no se descuenta nada (sin descuento parcial, coherente con «todo o nada») y se dice: «no descuenta la transferencia porque no tenemos los valores oficiales de todas las provincias de tu búsqueda». `jurisdiction` se guarda igual (`["caba", "rest"]`).
- **Dólar.** Aviso en ARS: el mismo del `price_usd` (`price / price_usd`). Aviso en USD: la última cotización guardada si no supera `cost_estimator.fx.max_age_days`. Se guarda `fx` en `margin_ref`.

### 3. Forma exacta de `margin_ref`

Siempre rangos `{min, max}` (iguales cuando no hay incertidumbre), en USD, sin redondear (2 decimales); el redondeo es de presentación.

```json
{
  "v": 1,
  "status": "ok",
  "dealer_median": 14500.0,
  "dealer_n": 6,
  "n": 10,
  "level_used": "transmission",
  "asking_usd": 12000.0,
  "price_label": "published",
  "currency": "ARS",
  "fx": {"rate": 1350.0, "kind": "listing", "date": null},
  "reconditioning": {"pct": 5, "min_usd": 300, "usd": 600.0},
  "transfer": {
    "status": "ok",
    "usd": {"min": 312.4, "max": 498.1},
    "terms": ["arancel", "sellos", "formularios"],
    "jurisdiction": ["caba"],
    "seller": "private"
  },
  "est_costs_usd": {"min": 912.4, "max": 1098.1},
  "acquisition_usd": {"min": 12912.4, "max": 13098.1},
  "gross_margin_usd": {"min": 1401.9, "max": 1587.6},
  "gross_margin_pct": {"min": 10.7, "max": 12.3},
  "as_of": {"dealer_margin": "2026-11-02", "cost_estimator": "2026-10-30"}
}
```

- `reconditioning = null` si `dealer_margin.reconditioning` falta o es inválido (el backlog lo pide: «el margen se muestra sin costos y lo dice»).
- `transfer.usd = null` con `status ≠ ok`; `jurisdiction`/`seller` se guardan igual para el copy.
- `est_costs_usd` = suma de lo que haya (puede ser `{0, 0}` sin parámetros).
- `v` permite cambiar la forma sin bump de `SCORING_VERSION`. La revisión 3 suma `status` y `acquisition_usd` sin subir `v` (nada se desplegó con la forma anterior); la web trata un `margin_ref` sin `status` como `ok` y sin `acquisition_usd` omite esa línea del detalle.
- Pocas agencias: `{"v": 1, "status": "few_dealers", "dealer_n": 2, "min_n": 5, "n": 10, "level_used": "transmission"}`, sin `gross_margin_usd` (no alcanza el umbral, va al final del orden).

### 4. `app_config.dealer_margin`

Sembrada por la migración (`on conflict (key) do nothing`):

```json
{
  "as_of": "2026-11-02",
  "source": "Decisión de Juan, 30/10/2026 (docs/PLAN_FASES_BACKLOG_PRODUCTO_2026-10.md §8)",
  "reconditioning": {"pct": 5, "min_usd": 300},
  "transfer": {"enabled": true}
}
```

Parser tolerante en `worker/intelligence/margin.py` (mismo estilo que `cost_estimator.parse_config`): `pct` en 0–100, `min_usd ≥ 0`; inválido → `reconditioning = null`, sin defaults numéricos en código. Editable en `/admin/config` (editor existente): `HINTS.dealer_margin`, `NAMES.dealer_margin = "Margen estimado (PRO-02)"` y un validador zod en `validateConfigChange` (bloque `reconditioning` con números válidos, `transfer.enabled` booleano). El cambio se refleja en los matches en el siguiente rescore (como cualquier parámetro del score).

### 5. Dónde se calcula

- **Nuevo** `worker/intelligence/margin.py`, puro: `parse_config(raw)`, `compute(row, price_ref, zones, dealer_cfg, cost_cfg, fx_latest, min_n, today) -> dict | None`, y helpers de presentación (`rounded`, `headline`, `email_payload`). Sin I/O.
- `pipeline/scoring.py`: `Scorer.create` lee además `dealer_margin`, `cost_estimator` (parseada) y, si hace falta, la última cotización (`fx_repo.latest_stored`), una vez por lote. `Scorer.evaluate` llama a `engine.evaluate` y, si hay evaluación, completa `ev.margin_ref = margin.compute(...)` con las zonas del `profile` (`origin_lat/lon`, `filters.location_label`, `filters.extra_locations`, que `profiles._SELECT` ya trae).
- `intelligence/engine.py`: `Evaluation` suma `margin_ref: dict | None = None` y `row()` agrega `"margin_ref"`. No cambia `assess`/`evaluate` (menos choque con PRO-01).
- `db/repos/matches.py`: `_EVALUATED` suma `margin_ref` (con `Jsonb` si no es null).
- Se calcula para **todos** los matches (no solo Pro): es barato y, si un usuario pasa a Pro, ya lo tiene. Lo que se gatea es la lectura (ver «Gating»). Los mismos números ya se pueden derivar de `price_ref`, que todos los planes leen.

### 6. Relleno sin bump

`rescore_queue` (`db/repos/matches.py`) suma, en **las dos** pasadas (la de arranque y la nocturna), los matches que deberían tener margen y no lo tienen:

```sql
OR (m.margin_ref IS NULL AND l.price_usd > 0
    AND (m.price_ref->>'dealer_n')::int IS NOT NULL
    AND ((m.price_ref->>'dealer_n')::int < %(min_n)s          -- revisión 3: few_dealers
         OR (m.price_ref->>'dealer_median')::numeric > 0)
    AND NOT coalesce(l.price_partial, false)
    AND l.description_facts #> '{price_check,published_partial}' IS DISTINCT FROM 'true'::jsonb
    AND NOT coalesce(l.description_facts #>> '{price_check,published_kind}' = ANY(%(partial_kinds)s), false))
```

- Converge: la condición replica todos los casos en que `margin.compute` devuelve null para un match que existe (`price_ref` sin `dealer_n`, agencias suficientes pero mediana ≤ 0, sin `price_usd`, precio publicado parcial según `published_partial`, con `PARTIAL_KINDS` pasado como parámetro). Tras recalcular, o `margin_ref` queda con valor, o el nuevo `price_ref` sale de la condición. Sin esto, un anticipo con precio de contado en la descripción volvía a la cola en cada arranque y en cada pasada. Un `price_ref` de siete claves no entra (no tiene `dealer_n`); lo completa la pasada nocturna de 14 días, que recalcula `price_ref` y margen juntos.
- Es idempotente y no reenvía alertas: `rescore()` solo hace `upsert_scored(..., backfill=True)`, que en una fila existente conserva `is_backfill` y `generated_at` y no pasa por el `Notifier`.
- Primer efecto: el primer arranque del worker después de aplicar la migración (que despliega con el worker nuevo, así que siempre hay un arranque). No hay `tools/rescore` en `worker/tools/` y no se agrega: la condición del arranque es el relleno.
- Matches de avisos `gone` o fuera de 14 días no se rellenan (la condición exige `l.status = 'active'`, como hoy): sin margen en el histórico.

### 7. Gating (solo Pro)

- `plan_limits.pro.dealer_margin = true` y `plan_limits.pro.min_threshold_usd = 500`, agregadas por la migración solo si faltan (mismo patrón que PRO-01). Validadas en `AdminPlanLimitsInput` (`dealer_margin` booleano, `min_threshold_usd` entero ≥ 1).
- **Worker.** `db/repos/notifications.py`: `public.plan_feature(sp.user_id, 'dealer_margin') AS dealer_margin` y
  `CASE WHEN plan_feature(..., 'dealer_margin') AND sp.opportunity_threshold_usd >= coalesce((plan_limits_for(sp.user_id)->'limits'->>'min_threshold_usd')::int, 500) THEN sp.opportunity_threshold_usd END AS threshold_usd`
  en `profile_audiences` y `listing_audiences` (esta también suma `m.margin_ref`). El payload lleva `margin` solo si `dealer_margin`.
- **Base.** `matches.margin_ref` no es legible por `anon`/`authenticated`: la RLS de `matches` deja a cualquier usuario leer sus propios matches sea cual sea el plan, y el worker calcula el margen para todos. La migración cambia el `SELECT` de tabla por una lista de columnas sin `margin_ref` (armada en un `do $$` con las columnas que existan). Una migración futura que agregue una columna a `matches` tiene que darle `grant select` a `authenticated` (y `anon`).
- **Auditoría del revoke (02/11).** Con el `SELECT` por columna, PostgREST rechaza (403, `42501`) solo lo que pide `margin_ref`: `select("*")`, `select()` sin columnas, `matches(*)` embebido y `HEAD` con `select=*`. La web de esta rama y la de `origin/main` (la de producción, que corre contra la base migrada hasta que se despliegue la web) leen `matches` con el cliente del usuario solo en `app/app/listings/[id]/page.tsx` y `app/app/saved/page.tsx`, y en los dos nombran las columnas. Los `select("*")` sobre `matches` (`lib/admin-inspect.ts`, `/admin`) usan `createAdminClient` (service role, sin grants por columna). Ninguna tabla embebe `matches` desde la web, ninguna policy de otra tabla consulta `matches`, `matches` no está en la publicación de realtime, y el worker entra por `DATABASE_URL` (rol `postgres`). Las vistas `security_invoker` sobre `matches` (`match_cards`, `admin_score_histogram`, `admin_searches`, `v_first_value`) se crearon antes de `margin_ref` y no la nombran, y la única función `security invoker` que lee `matches` directo es `admin_decision_metrics`; `search_results`, `search_result_counts`, `search_follow_counts`, `recent_opportunities`, `dashboard_summary` y `listing_price_tracks` siguen andando como `authenticated` (probado con JWT de usuario Free y Pro, por SQL y por PostgREST). No hace falta mover el margen a otra tabla. Lo cuidan `supabase/tests/pro02_margin_test.sql` (toda columna salvo `margin_ref` legible por `authenticated` y `anon`; las consultas de la web, las vistas y las RPC como el Pro; `select *` rechazado) y `web/lib/matches-select.test.ts` (ningún archivo con el cliente del usuario hace `select *` sobre `matches`).
- **Web.** Nueva RPC `public.my_match_margins(p_match_ids bigint[]) returns table (match_id bigint, margin_ref jsonb)`, `security definer` que chequea el dueño (`search_profiles.user_id = auth.uid()`, como la RLS) y vacía si `not my_plan_feature('dealer_margin')`. Ficha y tarjetas la usan; nada de la web selecciona `matches.margin_ref` directo (tampoco puede).
- **Admins** tienen todas las features: ven margen y orden. Para que un admin no rompa nada con la base vieja, la web exige además que el snapshot del plan traiga `min_threshold_usd` (ver «Base vieja»).

### 8. Umbral en USD (engine)

- Columna `search_profiles.opportunity_threshold_usd integer check (opportunity_threshold_usd between 1 and 1000000)`, null = sin umbral. El mínimo del plan no va en un CHECK (cambia sin migración): lo valida la web al guardar y el worker lo ignora si queda por debajo (CASE de arriba).
- `Audience.threshold_usd`. `classify`: «tiene umbral» pasa a ser `threshold_pct is not None or threshold_usd is not None`; **alcanza** si alcanza cualquiera de los dos (OR). Con uno solo cargado se comporta igual que hoy el de %. Mismo resultado en `MATCH` y `PRICE_DROP`: alcanza → inmediato, sin tope, no cuenta; no alcanza → digest; alcanzar avisa aunque esté debajo de `notify_min_level`; un guardado con baja sigue siempre inmediato.
- Alcanza en USD si `payload.margin.usd_low >= threshold_usd`: el **extremo bajo** del rango sin redondear (`margin.threshold_low`, conservador). No se compara `usd_min`, que es el número del copy: un valor único se redondea a la decena más cercana (USD 495 se muestra USD 500 pero no alcanza un umbral de USD 500). Sin margen (n insuficiente, sin dato) no alcanza.
- `decide`: si alcanzó por USD, `payload.threshold_usd = threshold_usd`; por %, `payload.threshold_pct` como hoy (si alcanza los dos, ambos).
- `sent_today`: `AND NOT (payload ? 'threshold_pct' OR payload ? 'threshold_usd')`.
- **Baja de precio.** `on_listing_events` corre después del rescore del lote, así que `m.margin_ref` ya refleja el precio nuevo.

### 9. Copy

Mismo texto en `worker/intelligence/copy.py` (`MARGIN`) y `web/lib/copy.ts` (`MARGIN`). Montos redondeados hacia afuera a USD 10 (`floor`/`ceil` con `EPS`, como PAR-01); rango «entre USD A y USD B», punto único «USD A»; porcentaje entero.

- **Línea (ficha y email; la tarjeta lleva la corta, ver «Respuestas de Juan (02/11)», 1):**
  «Margen bruto estimado: USD 1.400 a 1.590 (contra la mediana de USD 14.500 a la que publican las agencias este modelo, n = 6; descuenta acondicionamiento del 5 % y transferencia; sin impuestos)».
  Variantes del tramo final:
  - sin transferencia por zona: «…; descuenta acondicionamiento del 5 %; no descuenta la transferencia porque tu búsqueda no tiene localidad; sin impuestos)»;
  - fuera de CABA y Buenos Aires: «…porque no tenemos los valores oficiales de tu provincia…»; zona mixta: «…porque no tenemos los valores oficiales de todas las provincias de tu búsqueda…»;
  - sin dólar: «…porque falta el dólar del día…»; sin parámetros: «…porque faltan parámetros cargados…»;
  - sin acondicionamiento cargado: «…; sin descontar costos: faltan los parámetros de acondicionamiento; sin impuestos)».
- **Pocas agencias (revisión 3), en lugar de la línea, en tarjeta, ficha y email:** «Margen estimado: no hay suficientes agencias publicando este modelo para estimarlo (n = 2, mínimo 5)» (en el email con punto final y sin «Parámetros al»). En la ficha va sola, sin «Ver detalle».
- **Ficha, detalle debajo de la línea:** qué descuenta en números («Acondicionamiento: USD 600 (5 % del precio, mínimo USD 300). Transferencia: entre USD 310 y 500 (arancel, sellos y formularios de CABA, según tu búsqueda en «Palermo, CABA»).»), lo que cuesta comprar el auto y el % sobre eso («Lo que cuesta comprar el auto: USD 12.910 a 13.100 (precio de compra más los costos descontados).», «Margen sobre lo que cuesta comprar el auto: 10 % a 13 %.»), «No incluye impuestos de la venta, patente ni comisiones.», «Comparamos con precios publicados por agencias, no con precios de venta. Es una estimación orientativa.», nivel de comparables (`COMPARABLE_LEVEL`) y «Parámetros al dd/mm».
- **Tarjeta:** solo la línea (sin detalle), debajo de la línea de costo total si existe.
- **Email Pro:** la línea en `opportunity` y `new_match` inmediatos y en `price_drop`, después de la de costo total. Payload congelado al crear la fila: `payload.margin = margin.email_payload(margin_ref)` = `{usd_min, usd_max, dealer_median, dealer_n, transfer_status, reconditioning_pct, jurisdiction, as_of}` ya redondeados, más `usd_low` (sin redondear, solo para el umbral). El digest no la lleva en v1.
- **Lint.** Términos extra prohibidos para el bloque `MARGIN` (además de `FORBIDDEN_TERMS`): «ganancia», «ganancias», «garantiz», «rentab», «asegur», «seguro que», «vas a ganar», «precio de venta» (salvo en la frase «no con precios de venta», que el test permite explícitamente), «vale». Se prueba en `web/lib/copy.test.ts` y `worker/tests/test_intelligence_copy.py`, y sobre el texto renderizado de las variantes.

### 10. Orden «por margen estimado»

- `web/lib/sorts.ts`: `margin: "Mayor margen estimado"`, ofrecida por `SortSelect` solo si el usuario tiene margen (prop `options`). `isSort` acepta `margin`; para quien no lo tiene, la página lo trata como `score`.
- `search_results`: nueva rama
  `case when (select ok from margin_access) then mg.low end desc nulls last`, con `margin_access as (select p_sort = 'margin' and public.my_plan_feature('dealer_margin') ok)` una sola vez por consulta y un `left join` a `public.my_margin_sort_keys(p_profile_id)` (`security definer`: dueño y feature chequeados adentro, porque `search_results` es `security invoker` y `authenticated` no lee `margin_ref`). Sin margen, al final y luego por fecha. Se redefine `search_results` **sin tocar `match_cards`** (PRO-01 la redefine para agregar `seller_unknown`; si las dos ramas la tocaran, la segunda en aplicarse rompería con «cannot drop columns from view»).
- Ordena por el extremo bajo, como el umbral. Un `few_dealers` no tiene `gross_margin_usd`: `my_margin_sort_keys` le da `low = null` y queda al final, con los que no tienen margen (revisión 3).

### 11. Eventos

- `margin_threshold_set`: en `searches/actions.ts`, al guardar una búsqueda cuyo `opportunity_threshold_usd` cambió (incluido apagarlo). Props `{profile_id, threshold_usd, previous}`.
- `results_sorted_margin`: server action llamada por `SortSelect` al elegir `margin`. Props `{profile_id}`.
- Sin lista blanca en la base: `events` no tiene CHECK de nombres. No se agregan a `human_events` de `admin_decision_metrics`: `margin_threshold_set` siempre viene con `search_profile_updated` (mismo criterio de PRO-01 con `seller_filter_set`) y redefinir esa función chocaría con PRO-01. Si Juan quiere `results_sorted_margin` como actividad, va en una migración posterior a la de PRO-01.

### 12. Base vieja (la web en `main` sin la migración)

- `my_match_margins` no existe → el helper (`web/lib/margin-data.ts`) atrapa el error y devuelve un mapa vacío (patrón `fetchPriceTracks`): sin línea.
- `search_results` vieja ignora `p_sort = 'margin'` → orden por fecha. Además la opción solo aparece con `marginAccess`.
- `marginAccess = my_plan_feature('dealer_margin') && snapshot.limits.min_threshold_usd != null`: en la base vieja `plan_limits` no tiene `min_threshold_usd`, así que ni un admin ve el control ni se envía `opportunity_threshold_usd` en el insert/update (la columna no existe). `toColumns` solo incluye la clave si el valor está definido.
- `web/types/database.ts` se edita a mano: `matches.margin_ref`, `search_profiles.opportunity_threshold_usd`, `Functions.my_match_margins`.
- El **worker** sí necesita la migración (escribe `margin_ref`, lee `opportunity_threshold_usd`): orden de despliegue migración → worker → web, como F-02.

## Migración

`supabase/migrations/20261130120000_pro02_margin.sql` (después de PRO-01 `20261128…` y de la otra rama `20261129…`), aplicable desde base vacía:

1. `alter table public.matches add column if not exists margin_ref jsonb;` + comment.
2. `alter table public.search_profiles add column if not exists opportunity_threshold_usd integer check (...)` + comment.
3. `insert into public.app_config (key, value) values ('dealer_margin', ...) on conflict (key) do nothing;`
4. `update public.app_config set value = jsonb_set(...) where key = 'plan_limits'` agregando `dealer_margin` y `min_threshold_usd` solo si faltan.
5. `do $$ ... $$`: `revoke select on public.matches from anon, authenticated` y `grant select (<todas las columnas menos margin_ref>)`.
6. `create function public.my_match_margins(bigint[])` y `public.my_margin_sort_keys(bigint)` (`security definer`), revoke de `public, anon`, grant a `authenticated`.
7. `create or replace function public.search_results(...)` = la de `20261119120000_x01_tracking.sql` + rama `margin`.
8. `notify pgrst, 'reload schema';`

Sin `lock table` (dos `add column` sin default son solo catálogo). Rollback: dropear las funciones nuevas, re-aplicar el `search_results` de X-01, volver a `grant select on public.matches to anon, authenticated`; las columnas pueden quedar.

## Archivos

Worker: `intelligence/margin.py` (nuevo), `intelligence/copy.py`, `intelligence/engine.py` (campo y `row()`), `pipeline/scoring.py`, `db/repos/matches.py` (`_EVALUATED`, `rescore_queue`), `db/repos/notifications.py`, `notifications/engine.py`, `notifications/service.py`, `notifications/templates.py`, `notifications/email_html.py` (si la línea necesita estilo propio), `tools/explain_match.py` (mostrar `margin_ref`, opcional).

Web: `lib/margin-view.ts` (nuevo: línea y detalle desde `margin_ref`), `lib/margin-data.ts` (nuevo, `server-only`: `fetchMatchMargins`, `marginAccess`), `lib/copy.ts`, `lib/sorts.ts`, `components/app/sort-select.tsx`, `components/app/listing-card.tsx` (prop `marginLine`), `components/app/margin-estimate.tsx` (nuevo, ficha), `app/app/listings/[id]/page.tsx`, `app/app/searches/[id]/page.tsx` (y `app/app/page.tsx`, `app/app/saved/page.tsx` si muestran tarjetas con match), `components/app/opportunity-threshold-usd.tsx` (nuevo), `components/app/search-form.tsx`, `lib/search-form.ts`, `app/app/searches/actions.ts`, `app/app/searches/form-data.ts`, `lib/pro.ts` (tipo `limits`), `lib/admin-config.ts`, `app/admin/config/page.tsx`, `types/database.ts`.

Supabase: la migración y `supabase/tests/pro02_margin_test.sql` (pgTAP).

## Tests

Offline (corren en esta rama):

- `worker/tests/test_margin.py` (puro):
  - pool de **6 agencias y 4 particulares** (`PriceRef(n=10, dealer_n=6, private_n=4, ...)` con medianas distintas): el margen usa `dealer_median`, no `median` ni `private_median`;
  - `dealer_n = 4` con `min_n = 5` → null; `price_ref` de siete claves → null; precio parcial → null; sin `price_usd` → null;
  - ARS (dólar del aviso) y USD (cotización vigente / vencida → `no_fx`);
  - sin zona → `no_zone`, sin transferencia y sin usar otra jurisdicción; AMBA → rango CABA+BA; resto del país → `no_official`; CABA + Córdoba → `no_official_some`;
  - `dealer_n < min_n` → `few_dealers` con su línea; con precio parcial o sin `price_usd`, null;
  - % sobre lo que cuesta comprar el auto (`margen_min / costo_max`, `margen_max / costo_min`);
  - acondicionamiento: 5 % por encima y por debajo del mínimo de USD 300; config null → sin costos;
  - rangos: `gross_margin_usd.min` usa los costos máximos; negativo; redondeo hacia afuera.
- `worker/tests/test_notifications_engine*.py`: umbral USD alcanzado → inmediato, sin tope, no cuenta, `payload.threshold_usd`; no alcanzado → digest; sin margen → digest; % OR USD; baja de precio; por debajo de `notify_min_level` igual avisa.
- `worker/tests/test_notifications_margin.py`: `payload.margin` solo con `dealer_margin`; `few_dealers` no alcanza el umbral; **snapshots** `tests/snapshots/notifications/opportunity_margin.txt`, `opportunity_margin_no_zone.txt` y `opportunity_margin_few_dealers.txt` (email Pro).
- `worker/tests/test_intelligence_copy.py`: lint de `MARGIN` y de las variantes renderizadas.
- `Evaluation.row()` incluye `margin_ref`; `Scorer` lo completa (con fakes).
- Web (vitest): `lib/margin-view.test.ts` (línea, variantes, rangos, negativos), `lib/copy.test.ts` (lint), `lib/margin-data.test.ts` (RPC con error → mapa vacío; `marginAccess` con/sin `min_threshold_usd`), `lib/search-form.test.ts` (umbral USD: mínimo del plan, null, gating en el action), `lib/admin-config.test.ts` (`dealer_margin`, `plan_limits` nuevas claves), sorts (opción solo con acceso).
- `npx tsc --noEmit` y lint del web.

Contra la base local (corridos en la revisión 3):

- pgTAP `supabase/tests/pro02_margin_test.sql`: `my_match_margins` vacía sin la feature y con filas para Pro (incluido un `few_dealers`); `search_results('margin')` ordena por margen solo con la feature, con `few_dealers` y sin margen al final; claves de `plan_limits`; `authenticated`/`anon` sin `SELECT` sobre `matches.margin_ref` (un `select margin_ref` directo falla con 42501, Pro o no) y con el resto de las columnas; `my_margin_sort_keys` vacía sin la feature y para búsquedas ajenas; la migración se aplica desde base vacía.
- `pytest -m db`: 6 agencias + 4 particulares por `comparables()` → `rescore` → `margin_ref.dealer_n = 6`; `rescore_queue` toma un match con `dealer_n ≥ min_n` y `margin_ref` null, y no lo vuelve a tomar después; lo mismo con 0 agencias (`few_dealers`).

## Riesgos

- **Cobertura de vendedor.** Mardel e Instagram dejan el vendedor en null y la cascada elige nivel por `n` total, así que muchos matches tendrán `dealer_n < 5` y no mostrarán margen. Juan decidió salir igual (pregunta 6): esos matches muestran «no hay suficientes agencias…» en vez de nada. Conviene igual medir el porcentaje de matches Pro con margen.
- **Mediana de publicados.** Las agencias publican más caro de lo que venden; el margen sobre publicados sobreestima. El copy lo dice, pero es el riesgo comercial principal (BACKLOG_COMERCIAL prohíbe prometer rentabilidad).
- **Conflictos.** `email_html.py`/`templates.py`/snapshots, `listing-card.tsx`, ficha, `search-form`, `notifications.py` y `engine.py` los tocan también PRO-01 y `claude/sin-notas-costo-resumido`. Cambios acotados (líneas nuevas, sin reordenar). `match_cards` no se toca; `search_results` solo la redefine esta rama.
- **Desfase de parámetros.** Un cambio en `cost_estimator` o `dealer_margin` se ve en el margen recién en el próximo rescore (horas); el costo total de la web se calcula en vivo. Puede verse un costo de transferencia distinto entre la línea de costo total y el detalle del margen hasta el rescore.
- **Admins.** `plan_feature` les da todo; con la base vieja se cubre con `min_threshold_usd` en el snapshot.

## Implementación (revisión 2)

Lo que cambió al implementar, respecto de las secciones de arriba:

- **Acceso de la web.** No se usa `my_plan_feature('dealer_margin') && snapshot.limits.min_threshold_usd`: para un admin `plan_limits_for` devuelve `limits = {"immediate_alerts": true}`, así que el snapshot nunca trae el mínimo y un admin no vería nada. En su lugar hay una RPC `public.my_margin_access()` que devuelve `{enabled, min_threshold_usd}`. En una base sin la migración la RPC no existe, la web lo toma como «sin acceso» y no muestra línea, orden ni control, ni manda `opportunity_threshold_usd` en el insert o el update.
- **Mínimo del umbral.** `public.min_threshold_usd(user)`: el `min_threshold_usd` del plan y, si no tiene (admins), el de Pro. Lo usan el worker (`CASE … >= public.min_threshold_usd(sp.user_id)`) y `my_margin_access`. No hay un 500 escrito en el código: si no hay mínimo cargado, no aplica ningún umbral en USD.
- **Estados de la transferencia.** Se suma `no_price` (el aviso no tiene una moneda que el calculador lea), con su texto. El orden de los motivos es `disabled` → `params` → `no_price` → `no_zone` → `no_official`/`no_official_some` (revisión 3) → `no_fx` → el del término que falte.
- **Redondeo.** Si el margen no tiene rango (sin transferencia), se muestra un número redondeado a USD 10 («USD 1.850»), no «USD 1.840 a 1.850».
- **Vectores compartidos.** `worker/tests/fixtures/margin/golden.json` (11 casos: `margin_ref`, payload y línea). Lo leen `worker/tests/test_margin.py` y `web/lib/margin-view.test.ts`, así que la web y los emails imprimen la misma línea.
- **Superficies.** La línea va en las tarjetas de resultados, del inicio y de favoritos (estas toman el mejor match, que ahora trae su `id`), y en la ficha con un detalle cerrado («Ver detalle del margen»). En el email, la línea también llega a Telegram y a la bandeja web, porque usan el mismo contenido (igual que el costo total de PAR-01).
- **Formulario.** El control del umbral en USD está en el formulario estructurado (crear y editar). El asistido no lo muestra; si una búsqueda ya tiene un valor, el formulario lo conserva.
- **Evento de orden.** `results_sorted_margin` se registra con una server action propia (`app/app/searches/margin-actions.ts`) que llama `SortSelect`, para no tocar `actions.ts` de más.
- **Admin.** `/admin/config` valida `dealer_margin` (`DealerMarginInput`) y las claves nuevas de `plan_limits`; el formulario de límites suma el toggle «Margen estimado para agencias (PRO-02)» y el mínimo en USD.

En la revisión 3 corrieron contra la base local `supabase/tests/pro02_margin_test.sql`, `worker/tests/test_margin_postgres.py` y `worker/tests/test_notifications_postgres.py`.

- **Bug del merge con PRO-01 (revisión 3).** `Evaluation` tenía `margin_ref` antes de `contact_questions` y `assess` pasaba las preguntas por posición: caían en `margin_ref`. Ahora `contact_questions` va antes y se pasa por nombre (test de regresión en `test_intelligence.py`).
- **Vectores compartidos (revisión 3).** `golden.json` tiene 13 casos (suma «CABA y Córdoba» y «pocas agencias»; «resto del país» pasa a `no_official`). `GoldenTests` recalcula **todos** los `margin_ref` con `margin.compute` y se regenera con `UPDATE_GOLDEN=1 pytest tests/test_margin.py`.
- **Porcentaje de un solo valor.** Sin rango (sin transferencia), el % se muestra redondeado al entero («11 %»), no «11 % a 12 %», como el monto.

## Preguntas para Juan

1. **Copy de la línea**: ¿te sirve el texto de la sección 9 (con «descuenta acondicionamiento del 5 % y transferencia; sin impuestos») en las tres superficies, o la tarjeta va más corta?
2. **Base del 5 %**: ¿sobre el precio de compra (propuesto) o sobre la mediana de agencias?
3. **Margen %**: ¿sobre la mediana de agencias (margen, propuesto) o sobre el costo (lo que pusiste en el auto)?
4. **Transferencia incompleta**: sin localidad, ¿no se descuenta nada (propuesto, todo o nada) o se descuentan igual arancel y formularios, que son nacionales, y se dice que faltan los sellos?
5. **Resto del país**: ¿aceptás el rango de PAR-01 (Córdoba, Santa Fe y Mendoza) para una búsqueda en otra provincia, o preferís no descontar transferencia fuera de CABA y Buenos Aires?
6. **Cobertura**: ¿salimos aunque una parte grande de los matches no tenga margen por `dealer_n < 5`, o preferís medir primero y decidir si bajar el mínimo solo para margen?
7. **Umbral**: con % y USD cargados a la vez, ¿alcanza con cualquiera (propuesto, OR) o tienen que cumplirse los dos?

## Respuestas de Juan (02/11)

«ok a todo menos a 3 (sobre lo que cuesta comprar el auto), 5 (no lo usamos), 6 (salgamos igual, aclarando)». Aplicado en la revisión 3:

1. **Copy: como se propuso, salvo la tarjeta (Juan, 02/11, después de ver las capturas: ocupaba ~5 renglones).** Ficha y email llevan la línea completa. Las tarjetas (resultados, inicio y Guardados) llevan una corta, `marginCardLine` en `web/lib/margin-view.ts`: «Margen bruto estimado: USD 2.590 a 2.610 (n = 6 agencias)» y, con pocas agencias, «Margen estimado: pocas agencias para estimarlo (n = 2)». La mediana, los costos y «sin impuestos» quedan en la ficha. Telegram y la bandeja web usan el contenido del email y no cambian.
2. **Base del 5 %: como se propuso.** Sobre el precio de compra, con mínimo USD 300.
3. **Cambio: % sobre lo que cuesta comprar el auto.** `gross_margin_pct = gross_margin_usd / acquisition_usd × 100`, con `acquisition_usd = asking_usd + acondicionamiento + transferencia descontada` (nuevo en `margin_ref`). Rangos coherentes: `pct_min = margen_min / costo_max`, `pct_max = margen_max / costo_min`. Copy del detalle de la ficha: «Lo que cuesta comprar el auto: USD A a B (precio de compra más los costos descontados).» y «Margen sobre lo que cuesta comprar el auto: X % a Y %.» (antes «Margen sobre la mediana: …»). La línea no muestra el %, así que no cambia.
4. **Sin localidad: como se propuso.** No se descuenta transferencia y se dice.
5. **Cambio: no se usa «resto del país».** Fuera de CABA y Provincia de Buenos Aires no se descuenta transferencia (`transfer.status = "no_official"`): «…; no descuenta la transferencia porque no tenemos los valores oficiales de tu provincia; sin impuestos)». **Zona multi-jurisdicción** que incluye otra provincia: se descuenta solo si todas las jurisdicciones tienen valores oficiales; si no, no se descuenta nada (`no_official_some`, sin descuento parcial, como en la respuesta 4): «…porque no tenemos los valores oficiales de todas las provincias de tu búsqueda…». Se quitó la nota del detalle «Resto del país: rango de sellos armado con Córdoba, Santa Fe y Mendoza.».
6. **Cambio: salimos igual, aclarando.** Con `dealer_n < min_n` el worker guarda `{status: "few_dealers", dealer_n, min_n}` y, para Pro, la línea es «Margen estimado: no hay suficientes agencias publicando este modelo para estimarlo (n = Z, mínimo 5)». **Dónde:** ficha, tarjeta y email (recomendación: las tres, porque reemplaza la línea de margen, no se suma a ella, así que no satura más que un match con margen, y sin ella un Pro ve margen en unas tarjetas y nada en otras sin saber por qué). En el orden «Mayor margen estimado» van al final con los que no tienen margen; no alcanzan el umbral en USD. **Precio parcial o sin precio en USD:** no se muestra nada (ni línea de margen ni aclaración): lo que falta es el precio, que la tarjeta y la ficha ya muestran con su aviso; tiene prioridad sobre «pocas agencias». Un `price_ref` sin `dealer_n` (anterior a F-02 paso 3) tampoco muestra nada: no sabemos cuántas agencias hay. El relleno sin bump (§6) también completa los `few_dealers`.
7. **Umbral: como se propuso.** Alcanza con cualquiera (OR).

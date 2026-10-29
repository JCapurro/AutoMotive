# Ese Auto · backlog de producto (Particular y Pro)

Fecha: 26/10/2026. Objetivo: seguir desarrollando la plataforma para los dos públicos que ya pagan — Particular (`pass`) y Pro (`pro`) — partiendo de los dolores de cada uno, no de features sueltas. Cada ítem nace de un dolor, dice qué existe hoy en el repo (HEAD 9822d0d, PR #49) y qué falta.

Estado: **propuesta para revisar con Juan**. Incorporado al [backlog comercial](BACKLOG_COMERCIAL.md) el 29/10/2026 (sección 4.3), que ordena qué va primero según el canal de venta. Nada de este documento está implementado ni autorizado todavía; ningún ítem se aplica en producción sin un pedido posterior.

Contexto de precios y límites vigentes (`app_config.pro_offer` y `plan_limits`, ver [PLANES_2026-10](PLANES_2026-10.md)): Prueba 1 búsqueda/3 días, Particular ARS 15.000/30 días con 3 búsquedas, Pro ARS 100.000/mes con 20 búsquedas y umbral de oportunidad. Único canal de aviso activo: email (Resend).

## Cómo ejecutar cada ítem con Code

1. Cada ID empieza con un diseño corto en `docs/superpowers/specs/<fecha>-<slug>-design.md` (mismo formato que `2026-10-05-description-intelligence-design.md`: alcance, datos y procedencia, flujo, validación y operación) y un plan en `docs/superpowers/plans/<fecha>-<slug>.md` con tareas `- [ ]` y los comandos de prueba exactos. Juan aprueba el diseño antes del plan.
2. Rama `claude/<slug>` y PR. Antes de tocar `web/`, leer `web/CLAUDE.md` → `AGENTS.md` (Next 16: leer `node_modules/next/dist/docs/` antes de escribir código).
3. Base: una migración nueva por cambio, con encabezado `--` que cite este doc y el ID. Los timestamps de las migraciones son pseudo-fechas que van adelante del calendario: al 29/10/2026 la última aplicada en producción es `20261118130000_product_feedback_leads.sql`; antes de nombrar una nueva, releer `max(version)` en prod. Inserts idempotentes, RLS en toda tabla nueva, `security definer set search_path = ''` con grants explícitos, `npm run gen:types` después de migrar. No editar migraciones viejas.
4. Todo parámetro ajustable va a `app_config` (editable en `/admin/config`, sin deploy), nunca a constantes.
5. Tests: pytest offline + Postgres solo contra una base `*_test` (`python -m tools.test_db`), pgTAP para funciones SQL y RLS, vitest y Playwright en desktop y 375 px. Snapshots de notificaciones en `worker/tests/snapshots/notifications/`.
6. Copy: pasa el lint de `worker/intelligence/copy.py` y `web/lib/copy.ts` (prohibidos «vale», «valor real», «precio real», «tasación», «tasado»; en mails de plan también «en tiempo real», «todos los portales», «el más barato»). Todo lo que compara precios se dice como «publicaciones comparables»; toda estimación se llama estimación y dice en qué se basa.
7. `graphify update .` después de cambiar código. Nada de migraciones ni ingesta en producción sin pedido explícito de Juan.
8. Gating por plan: usar `plan_feature()` / `my_plan_feature()` con una clave nueva por función (como hoy `threshold_alerts`), no chequeos sueltos de `profiles.plan`.

Tamaños: S = hasta 1 día, M = 2–3 días, L = 4–6 días efectivos de desarrollo. P0 = próximo ciclo (datos ya guardados, impacto directo en retención y recompra), P1 = segundo ciclo, P2 = requiere las fundaciones F-01/F-03 o validación comercial previa.

## Resumen

| ID | Público | Dolor | Trabajo y resultado | Depende de | Prioridad | Tamaño |
|---|---|---|---|---|---|---|
| F-01 | — | — | `comparables_for_spec()`: comparables sin aviso (marca, modelo, versión, año, km, zona) | — | P1 | M |
| F-02 | — | — | Vendedor v2: menos `seller_type` nulos, conteo de avisos por vendedor, medianas por tipo de vendedor en `price_ref` | — | P0 | M |
| F-03 | — | — | `market_stats`: agregados nocturnos por modelo, banda de año y zona (oferta, precios, días hasta dejar de publicarse, demanda) | — | P1 | M |
| F-04 | — | — | Canal push (PWA + Web Push) como alternativa al email | — | P1 | L |
| PAR-01 | Particular | El precio publicado no es lo que termina pagando | Costo total estimado por aviso: precio + transferencia + patente anual + equivalente en pesos | — | P1 | M |
| PAR-02 | Particular | Miedo a la estafa y a señar a ciegas | Señales de riesgo nuevas (fotos repetidas, «particular» con muchos avisos, duplicados entre fuentes) + checklist antes de señar | F-02 | P1 | M |
| PAR-03 | Particular | No sabe cuánto ofertar ni si conviene esperar | Días publicado, bajas acumuladas y comportamiento observado del modelo en ficha, tarjeta y email | F-03 (parcial) | P0 | M |
| PAR-04 | Particular | Compra sin saber qué revisar de ese modelo | Guías por modelo con preguntas específicas, publicadas como páginas indexables | — | P1 | L |
| PAR-05 | Particular | Tiene que vender el suyo para comprar | «¿A cuánto publicarlo?»: referencia de precios publicados y tiempo observado + captación de vendedores con consentimiento | F-01, F-03 | P2 | L |
| PRO-01 | Pro | Pierde el auto por minutos y le llegan avisos de otras agencias | Filtro duro «solo particulares», push y mensaje listo para pegar | F-02, F-04 (push) | P0 | M |
| PRO-02 | Pro | Piensa en margen y rotación, no en «% debajo de comparables» | Margen bruto estimado y rotación por oportunidad; umbral de alerta por margen | F-02, F-03 (rotación) | P0 | M |
| PRO-03 | Pro | Capital clavado en stock que no rota | Monitor de mi stock: posición contra comparables, días contra el mercado, aviso cuando aparece uno más barato | F-01, F-03 | P2 | L |
| PRO-04 | Pro | Decide qué comprar por intuición | Radar de mercado por zona: rotación, oferta, demanda de los particulares de la plataforma, spread entre zonas | F-03 | P2 | M |
| PRO-05 | Pro | Compite con veinte revendedores por el mismo aviso | Avisos de particulares que quieren vender, antes de que publiquen | PAR-05 | P2 | M |
| X-01 | Pro | Lleva el seguimiento en WhatsApp y planilla | Estados de seguimiento (contactado, visita, comprado) y notas en la UI | — | P1 | S |
| H-01 | ambos | Promesa de la landing que el email no cumple | Llevar las 3 preguntas principales al email de oportunidad | — | P0 | S |

## Fundaciones

### F-01 · Comparables sin aviso

Hoy `comparables(listing_id)` (migraciones `20261105120000` y `20261106120000`, wrapper `worker/intelligence/comparables.py`) parte de un aviso existente. PAR-05, PRO-03 y PRO-04 necesitan el mismo pool a partir de una especificación.

Reutilizar `comparable_listings()`, la cascada versión+caja → caja → modelo y `comparables.min_n` (5).

Criterios de aceptación:

- `public.comparables_for_spec(make, model, trim, transmission, year, mileage_km, lat, lon, radius_km)` devuelve el mismo `price_ref` que `comparables()` ({median, p25, p75, median_km, n, level_used}) y la misma exclusión de precios parciales, reposts y avisos que una lectura completa ya no vio.
- `comparables(listing_id)` pasa a ser un wrapper de la nueva función; los tests pgTAP de comparables siguen verdes sin cambios de resultado.
- Radio opcional: sin lat/lon se comporta como hoy (sin filtro geográfico).
- `security invoker`, expuesta a la web solo a través de funciones con gating.

### F-02 · Vendedor v2

`seller_type` (`private | dealer | null`) sale de `worker/normalization/transmission.py` y cada collector lo resuelve con señales distintas; Mardel e Instagram siempre dejan null. `preferences.seller_type` es blanda: suma al score, no excluye. `price_ref` mezcla avisos de agencias y particulares en una sola mediana.

Reutilizar `listings.seller_name`, `seller_type`, `ingest.py`, `comparables()`, `scoring.py`.

Criterios de aceptación:

- Vista o columna materializada `seller_listing_count`: avisos activos de los últimos 30 días por (fuente, `seller_name` normalizado). Se recalcula en el nocturno junto con el rescore.
- Heurística documentada en `app_config.seller_classification`: un vendedor con `seller_listing_count ≥ dealer_min_listings` (propuesto 4) se clasifica `dealer_inferred` aunque la fuente diga particular o null. `seller_type` pasa a admitir `private | dealer | dealer_inferred | null`; `listings.attributes._seller` guarda la evidencia (conteo, regla).
- `price_ref` suma `dealer_median`, `dealer_n`, `private_median`, `private_n` calculados sobre el mismo pool de comparables. `diff_pct` no cambia (sigue contra la mediana general): ningún score ni alerta existente se mueve.
- Métrica en `/admin`: porcentaje de avisos con `seller_type` null por fuente antes y después.
- Tests: fixtures con un mismo vendedor en 5 avisos; verificar que la clasificación no toca el score ni los snapshots.

### F-03 · Agregados de mercado (`market_stats`)

No hay estadísticas agregadas: `first_seen_at`, `last_seen_at`, `last_full_seen_at` y `status = gone` existen pero nadie los resume. Solo las fuentes con lectura completa (`confirm_sources`: autocity, carone, deruedas, gruporandazzo, mardelusados, rosariogarage, mercadolibre) confirman que un aviso dejó de publicarse; Facebook, V6, Kavak y Autocosmos no, y la watchlist solo revisa guardados.

Reutilizar el loop nocturno (rescore y retención), `listing_snapshots`, `crawl_targets`, `search_profiles`.

Criterios de aceptación:

- Tabla `market_stats` (semana, make, model, year_band de 2 años, province, con fila agregada para «todas las zonas») con: `active_count`, `new_count`, `gone_count`, `median_price_usd`, `p25`, `p75`, `median_days_to_gone`, `p25_days_to_gone`, `drop_share` (fracción de avisos con al menos una baja), `median_total_drop_pct` (entre los que bajaron), `demand_count` (búsquedas activas de la plataforma que matchean modelo y zona), `n_days_sample`.
- `median_days_to_gone` se calcula solo con avisos de `confirm_sources` cuyo `gone` fue confirmado por lectura completa; el resto se excluye y la fila dice `days_source = confirm_sources`. «Dejó de publicarse» no se presenta como «se vendió».
- `demand_count` siempre agregado: nunca se expone por debajo de `market_stats.min_demand_n` (propuesto 3); tampoco se exponen identificadores de usuarios.
- Mínimos de muestra en `app_config.market_stats` (`min_n` propuesto 8 para precios, 5 para días); por debajo, los campos quedan null y la UI dice «sin datos suficientes».
- Job idempotente (`python -m tools.market_stats --week 2026-W43 --dry-run`), con fila en `collector_runs` o tabla propia de corridas y errores en `pipeline_errors`.
- Retención: 26 semanas; se poda con `retention.py`.

### F-04 · Canal push

`notifications.channel` ya admite `push` como valor del enum, pero no hay manifest, service worker ni suscripciones. El email tiene minutos de latencia y las agencias miran el celular.

Reutilizar `worker/notifications/{engine,service,dispatch}.py`, `channels/`, `search_profiles.channels`, `/app/settings`, `web/proxy.ts`.

Criterios de aceptación:

- PWA instalable (manifest, iconos, service worker en `web/public/`), Web Push con VAPID; tabla `push_subscriptions` (user_id, endpoint, keys, user_agent, created_at, last_success_at, failures) con RLS.
- Canal `push` en `worker/notifications/channels/push.py`; el engine respeta el mismo dedupe, tope diario y umbral; `dispatch` marca `failed` y da de baja la suscripción tras `push.max_failures` (propuesto 3). El email se mantiene como respaldo configurable por usuario (`channels` puede ser `{email}`, `{push}` o ambos).
- El payload del push lleva título, precio, «X% debajo de publicaciones comparables» y el link firmado a la ficha (`notifications/links.py`); el clic registra `alert_clicked` como hoy.
- Ajustes muestra el estado del dispositivo y permite quitar la suscripción. Nunca se pide permiso de notificaciones sin un gesto del usuario.
- Gating: `plan_feature('push')`, por defecto Pro; evaluable para Particular después.
- Playwright: instalación y suscripción simuladas en desktop y 375 px; test del worker con un endpoint falso (sin llamadas reales).

## Particular

### PAR-01 · Costo total estimado

Dolor: el precio publicado no es lo que paga. Transferencia, patente según jurisdicción y dólar cambian el orden entre dos autos parecidos.

Qué existe: `price_usd` con el blue congelado del día (`fx_rates`), la ficha muestra «≈ USD X al dólar del día», `web/components/app/dealer-fees-notice.tsx` dice «Trámites y gestoría: 8–10% adicional estimado» solo para avisos de agencia. No hay cálculo de transferencia ni patente.

Reutilizar `dealer-fees-notice.tsx`, `normalization/geo.py` (provincia del aviso), `search_profiles.origin_lat/lon` y `location_label` (jurisdicción del comprador), `email_html.py`, `templates.py`.

Criterios de aceptación:

- `app_config.cost_estimator` con parámetros por jurisdicción (CABA, Buenos Aires, resto): porcentaje y topes de arancel de transferencia, sellado, gastos fijos (formularios, verificación), gestoría opcional, y alícuota anual de patente con su base. **Code no inventa valores:** la migración los deja en null con un comentario, Juan los carga en `/admin/config` con fecha y fuente, y la UI muestra «parámetros al dd/mm».
- La jurisdicción de la patente es la del comprador (zona de la búsqueda); la de la transferencia, la del registro donde se radica (por defecto la del comprador). Si falta cualquiera, se muestra solo lo calculable y se dice qué falta.
- En ficha y tarjeta: «Costo total estimado: USD X / ARS Y», desplegable con el detalle. En el email de oportunidad: una línea. Siempre con la palabra «estimado»; prohibido «precio real» y derivados.
- Orden opcional «por costo total» en la pantalla de resultados (`search_results` recibe el criterio; la función SQL calcula con los parámetros vigentes o la web lo calcula sobre la página actual, decidir en el diseño por costo de consulta).
- Eventos: `total_cost_expanded`, `results_sorted_total_cost`.
- Tests: valores de ejemplo en la base `_test`; snapshot del email con y sin parámetros cargados.

### PAR-02 · Señales de riesgo y checklist antes de señar

Dolor: seña por transferencia, fotos robadas, «particular» que es revendedor, vendedor que no es el titular.

Qué existe: `red_flags.py` ya cubre precio demasiado bajo (`much_cheaper` ≥25%, guardas 50/65% y anticipos), inconsistencias descripción/ficha, repost dentro de la misma fuente (`probable_repost_of` exige mismo vendedor y ubicación). No hay hashes de fotos (solo URLs), no hay conteo de avisos por vendedor, no hay dedupe entre fuentes. Política vigente: Ese Auto no contacta vendedores y no promete «detección certificada de deuda» ([BACKLOG_COMERCIAL](BACKLOG_COMERCIAL.md)).

Reutilizar `red_flags.py`, `copy.py`, `pipeline/enrich.py`, `pipeline/news.py`, `listings.images`, F-02.

Criterios de aceptación:

- Hash perceptual (pHash) de las primeras `risk.photo_hash_count` fotos (propuesto 3) durante el enrichment, guardado en `listings.attributes._photo_hashes`; descarga con tope diario en `app_config.risk` y sin reintentos infinitos. Dos avisos de distinta fuente o zona con un hash igual (distancia ≤ `risk.phash_max_distance`) y mismo modelo generan la señal `duplicate_photos` en ambos.
- Señal `private_many_listings`: vendedor que se presenta como particular con `seller_listing_count ≥ dealer_min_listings` (F-02). Copy: «El vendedor tiene N publicaciones activas: conviene preguntar si es titular».
- Señal `cross_source_duplicate`: mismo modelo, año, km ±3%, precio ±5% y hash de foto coincidente en otra fuente; no modifica el score, solo informa y enlaza el otro aviso.
- `much_cheaper` con ≥35% pasa a decir explícitamente que un precio muy por debajo es motivo de verificación antes de señar, no una oportunidad; el nivel ya está topeado por `price_check.py`, no se cambia.
- Checklist «Antes de señar» en la ficha (bloque estático con copia): informe de dominio e informe histórico (DNRPA), deuda de patentes e infracciones por jurisdicción, prenda, VTV, cédula y DNI del titular, formulario 08 ante escribano o registro, nunca seña por transferencia sin ver el auto y los papeles. Links a las páginas oficiales en `app_config.risk.links` (los carga Juan). Copy «conviene verificar», sin afirmar que Ese Auto verificó nada.
- Email de oportunidad: sigue mostrando hasta 2 red flags; las nuevas entran en el mismo orden de severidad definido en `app_config.red_flags`.
- Eventos: `risk_checklist_viewed`, `risk_checklist_copied`, `duplicate_link_clicked`.
- Tests: fixtures con fotos iguales en dos fuentes; vendedor con 6 avisos; snapshot de ficha y email; lint de copy.

### PAR-03 · Días publicado, bajas y comportamiento del modelo

Dolor: no sabe cuánto ofertar ni si conviene esperar.

Qué existe: `listing_snapshots` y `PriceHistory` en la ficha, evento `price_drop` (≥3%) y alertas de baja, «Lleva X días publicada» solo en `/app/saved`, evento `listing_stale` sin notificación, «Publicado/Detectado hace…» en tarjetas y emails. No hay estadísticas del modelo. Un «precio de cierre» no se puede calcular con datos publicados y choca con la regla de copy: no se hace.

Reutilizar `listing_snapshots`, `match_cards`, `search_results`, `email_html.py`, `digest.py`, F-03.

Criterios de aceptación:

- Por aviso, en tarjeta, ficha y email de oportunidad: días publicado (desde `published_at` o `first_seen_at`, distinguiendo «publicado» de «detectado»), cantidad de bajas y baja acumulada en % y USD desde el primer snapshot.
- Por aviso, cuando F-03 tiene muestra: «Los avisos de este modelo en esta zona que bajaron de precio bajaron en promedio X% antes de dejar de publicarse» y «Suelen dejar de publicarse en ~N días». Copy exacto validado con el lint; sin «precio de cierre», «vale» ni «ofertá X».
- Por búsqueda, en la pantalla de resultados: mini gráfico (recharts, ya en el stack) de la mediana semanal de `price_usd` de los últimos 90 días y el conteo de avisos activos, con «sin datos suficientes» bajo `min_n`.
- Hasta que F-03 exista, la primera entrega incluye solo lo calculable por aviso (días y bajas); el bloque del modelo se activa con `plan_feature('model_stats')` cuando `market_stats` tenga 4 semanas de datos.
- Eventos: `price_history_expanded`, `model_stats_viewed`.
- Tests: snapshots de email con 0, 1 y 3 bajas; pgTAP de la consulta de tendencia.

### PAR-04 · Guías por modelo y preguntas específicas

Dolor: compra a ciegas, no sabe qué revisar de ese modelo y esa generación.

Qué existe: `seller_questions.py` genera preguntas determinísticas por red flags, datos faltantes, antigüedad y descripción; la única pieza por modelo es la distribución (`vehicle_catalog.timing_belt`, [DISTRIBUCION](DISTRIBUCION.md); la migración `20261107130000_timing_chain_catalog.sql` está marcada NOT APPLIED hasta que Juan revise la tabla). `polish_questions` (LLM) existe sin conectar. El sitemap solo tiene `/`, `/planes`, `/login`, `/privacidad` y `/terminos`. El PRD §51 menciona contenido SEO como canal.

Reutilizar `vehicle_catalog`, `llm/` (proveedor y `prompts/*.md`), `llm_jobs`, `seller_questions.py`, `/admin`, `web/app/sitemap`.

Criterios de aceptación:

- Tabla `model_guides` (make, model, generation_label, year_from, year_to, body jsonb con secciones fijas: fallas conocidas, qué revisar en la visita, versiones y equipamiento, mantenimiento y costos típicos, generaciones; `questions` jsonb; `sources` jsonb; `status` draft | published; `reviewed_by`, `reviewed_at`, `llm_version`).
- Generación por job `model_guide` en `llm_jobs`, con prompt en `llm/prompts/model_guide.md`, tope diario propio en `app_config.llm_limits` y cache por (modelo, generación, versión del prompt). Cada afirmación se guarda como afirmación de la guía, no como verificación; la UI dice «Guía orientativa».
- Revisión en `/admin/guides`: Juan edita y publica; nada sale a la web en `draft`. Primera tanda: los 30 modelos con más búsquedas activas (consulta sobre `search_profiles`).
- Páginas públicas `/guias/<marca>/<modelo>` con ISR, metadata, FAQ (JSON-LD) y CTA «Crear mi búsqueda» prellenada; sitemap actualizado. Sin precios de avisos ni datos de usuarios en el HTML público.
- `seller_questions.py` suma las `questions` de la guía del modelo y la generación del aviso (hasta 3), antes de las genéricas, y las marca con origen para el inspector de `/admin`.
- Eventos: `guide_viewed` (público, sin usuario), `guide_cta_clicked`, `guide_questions_copied`; GA4 `view_item` con `item_category = guide`.
- Tests: contrato JSON del job con respuestas grabadas (`fixtures/llm`), render de página con guía inexistente (404), e2e del CTA.

### PAR-05 · «¿A cuánto publicarlo?»

Dolor: tiene que vender el suyo para comprar y no sabe a cuánto publicarlo ni cuánto va a tardar.

Qué existe: nada; solo visión en el PRD (§4, §39, §56). `owned_vehicles` es otra cosa (compras registradas para un futuro Garage, hoy sin uso). El motor de comparables sirve tal cual con F-01.

Reutilizar F-01, F-03, `vehicle_catalog`, el formulario estructurado de `/app/searches/new`, `email_only_signup`, `lifecycle.py`.

Criterios de aceptación:

- Página pública `/vender` (nombre a validar; prohibido «tasación» y «cuánto vale») con formulario marca, modelo, versión, año, km, zona; resultado: rango p25–mediana–p75 de publicaciones comparables, n, nivel de la cascada usado y, con F-03, «suelen dejar de publicarse en ~N días». Siempre «referencia de precios publicados», nunca una cifra única presentada como precio del auto.
- Captación: email opcional para recibir la referencia actualizada semanalmente (reutiliza el alta solo con email) y un segundo consentimiento, separado y explícito, «Quiero que agencias interesadas me contacten» que crea una fila en `seller_leads` (user_id o email, spec del vehículo, zona, precio esperado opcional, `consent_contact_at`, `status`). Sin ese consentimiento no se crea el lead ni se comparte nada.
- Si hay búsquedas Pro activas que matchean el vehículo y la zona, la página muestra «N agencias de tu zona siguen este modelo» solo cuando N ≥ `market_stats.min_demand_n`.
- Términos y privacidad actualizados antes de publicar la página (tarea de preparación para Juan, no conclusión jurídica).
- Eventos: `sell_reference_requested`, `sell_reference_email_opt_in`, `seller_lead_created`; Meta `Lead` solo con consentimiento vigente.
- Tests: pgTAP de `seller_leads` (RLS: el particular ve solo lo suyo), e2e del formulario en 375 px, lint de copy.

## Pro

### PRO-01 · Solo particulares, push y mensaje listo

Dolor: pierde el auto por minutos y encima le llegan avisos de otras agencias.

Qué existe: `preferences.seller_type` es blanda (suma al score). Kavak, Autocity, Car One y Randazzo son siempre dealer; ML, Facebook, V6, deRuedas, RosarioGarage y Usados Santa Fe lo resuelven por señales; Mardel e Instagram quedan null. No se guardan teléfonos ni WhatsApp (los collectors los descartan a propósito) y la política es que Ese Auto no contacta vendedores: el contacto siempre lo hace la agencia desde la publicación original (`/app/listings/[id]/out`). Hoy la ficha tiene «copiar preguntas».

Reutilizar `matching.py` (hard filters con `ok | fail | unknown`), `search_profiles.filters`, `/app/searches/new` y `edit`, `seller_questions.py`, F-02, F-04.

Criterios de aceptación:

- Filtro duro `filters.seller_types` (`private`, `dealer`, `dealer_inferred`) en el formulario estructurado y el asistido, con `plan_feature('seller_filter')` (Pro). `null` cuenta como `unknown`: pasa y baja el score, como el resto de los hard filters; la UI lo explica.
- Rematch al editar el filtro (ya existe `rematch_requested_at`); los avisos que dejan de cumplir no se re-notifican.
- Con F-04: el Pro puede elegir push, email o ambos por búsqueda; el push llega dentro del mismo tick de detección que el email.
- «Mensaje listo para pegar» en ficha y en el email: texto con las preguntas del aviso, en un botón de copiar y en un link `mailto:`/portapapeles; nunca un envío automático ni un link a un número que Ese Auto no tiene. Plantilla editable por el usuario en Ajustes (`profiles.contact_template`, con lint de copy al guardar).
- Eventos: `seller_filter_set`, `contact_message_copied`.
- Tests: matching con `seller_types` y `seller_type` null; snapshot de email con el bloque de mensaje.

### PRO-02 · Margen estimado y rotación

Dolor: la agencia no piensa en «8% debajo de comparables», piensa en cuánto le queda y en cuánto tarda en salir.

Qué existe: `price_ref` con mediana general, `diff_pct`, umbral `opportunity_threshold_pct` (5–45%, `plan_feature('threshold_alerts')`), `first_seen_at`/`gone`. No hay margen ni rotación, y [BACKLOG_COMERCIAL](BACKLOG_COMERCIAL.md) prohíbe prometer rentabilidad: todo se presenta como estimación orientativa con su base.

Reutilizar `scoring.py` (no cambia), `price_ref` (F-02), `engine.py` (umbral), `email_html.py`, `match_cards`, PAR-01 (parámetros de transferencia), F-03 (rotación).

Criterios de aceptación:

- `app_config.dealer_margin`: costo de acondicionamiento (porcentaje y mínimo en USD) y si se descuenta transferencia (toma `cost_estimator`). Valores los carga Juan; mientras estén en null, el margen se muestra sin costos y lo dice.
- Por match, columna `margin_ref` jsonb: `dealer_median`, `dealer_n`, `asking_usd`, `est_costs_usd`, `gross_margin_usd`, `gross_margin_pct`, `level_used`. Se calcula en el rescore junto con `price_ref`; nulo si `dealer_n < comparables.min_n`.
- Tarjeta, ficha y email Pro: «Margen bruto estimado: USD X (contra la mediana de USD Y a la que publican las agencias este modelo, n = Z, sin acondicionamiento ni impuestos)». Con F-03: «Este modelo suele dejar de publicarse en ~N días en esta zona».
- Umbral por margen: `search_profiles.opportunity_threshold_usd` (alternativo o adicional al %); el engine aplica la misma regla que el umbral actual (inmediato, sin tope, no cuenta para el tope). Slider con mínimo en `plan_limits.pro.min_threshold_usd`.
- Orden «por margen estimado» en resultados para Pro.
- Eventos: `margin_threshold_set`, `results_sorted_margin`.
- Tests: pool con 6 agencias y 4 particulares; margen nulo con n insuficiente; snapshot de email Pro; lint de copy (sin «ganancia garantizada», «rentabilidad»).

### PRO-03 · Monitor de mi stock

Dolor: capital clavado en autos que no rotan y precios de publicación puestos a ojo.

Qué existe: nada para el usuario. `owned_vehicles` no sirve (son compras de particulares). Base reutilizable: el motor de matching y los targets de inventario completo de autocity, carone y gruporandazzo.

Reutilizar `search_profiles` (con un `kind`), `matching.py`, `engine.py`, `digest.py`, F-01, F-03.

Criterios de aceptación:

- Tabla `dealer_stock` (user_id, spec del vehículo, precio y moneda, `published_at`, `source_url` opcional, `status` active | sold | withdrawn, `sold_at`). Carga manual y por CSV en `/app/stock`; importación desde la tienda de ML queda para una segunda versión (collector de vendedor).
- Cada unidad activa crea un `search_profile` del sistema con `kind = 'stock_watch'` (misma marca, modelo, año exacto, km ±25%, `price_max = precio propio × stock.cheaper_pct`, zona del Pro), que no cuenta para `plan_limits` ni para el tope diario y usa el engine existente para avisar «Apareció un {modelo} más barato que el tuyo: USD X vs tu USD Y». Pausar o vender la unidad pausa el perfil.
- Por unidad, con F-01: posición contra comparables (percentil y diferencia contra la mediana) y, con F-03, días publicado contra `median_days_to_gone`; sugerencia expresada como «la mediana de publicaciones comparables es USD X», nunca como precio correcto.
- Resumen semanal «Tu stock contra el mercado» por email (nueva `kind` en `notifications`, respeta la baja de emails).
- Límite `plan_limits.pro.max_stock_items` (propuesto 30); gating `plan_feature('stock_monitor')`.
- Eventos: `stock_item_added`, `stock_item_sold`, `stock_alert_clicked`.
- Tests: pgTAP de RLS y de que el perfil del sistema no consume capacidad; test del engine con un `stock_watch`.

### PRO-04 · Radar de mercado por zona

Dolor: decide qué comprar por intuición; no sabe qué rota rápido ni dónde está más barato.

Qué existe: solo interno (`/admin/searches`, `/admin/catalog-misses`, métricas); `crawl_targets` agrupa la demanda por modelo. No se expone nada a usuarios.

Reutilizar F-03, `/admin/metrics` (patrón de vistas), recharts.

Criterios de aceptación:

- `/app/mercado` para Pro (`plan_feature('market_radar')`): tabla por modelo y banda de año filtrable por provincia con oferta activa, nuevos por semana, mediana y rango de precios publicados, días hasta dejar de publicarse, `demand_count` (búsquedas activas de particulares en la plataforma, siempre ≥ `min_demand_n`) y spread de mediana contra «todas las zonas».
- Lectura solo de `market_stats`, nunca de `listings` o `search_profiles` en vivo; ninguna fila con `n < min_n`.
- Resumen mensual por email «Qué se mueve en tu zona» (top 10 por rotación y por spread), con el mismo gating.
- Eventos: `market_radar_viewed`, `market_radar_filtered`.
- Tests: pgTAP de que la función expuesta solo devuelve agregados; e2e en 375 px.

### PRO-05 · Vendedores particulares antes de que publiquen

Dolor: comprarle directo a un particular es el mejor negocio, pero en los portales compite con veinte revendedores por el mismo aviso.

Qué existe: nada; depende de PAR-05 (`seller_leads` con consentimiento).

Reutilizar `seller_leads`, `matching.py`, `engine.py`, F-04.

Criterios de aceptación:

- Match de cada lead contra las búsquedas Pro activas (modelo, años, km, presupuesto, radio) sin revelar el contacto: la agencia recibe «Un particular quiere vender {modelo} {año}, {km}, en {zona}» por push o email y puede marcar «Me interesa».
- Doble consentimiento: el particular recibe las agencias interesadas (nombre comercial y mensaje corto) y elige a cuáles compartir su contacto; solo entonces la agencia ve el email o teléfono. Tope `seller_leads.max_agencies_per_lead` (propuesto 3). Estados `new | offered | shared | closed`.
- Incluido en Pro en la primera versión para medir; cobro por lead o Pro+ queda en reserva hasta tener datos.
- Privacidad y términos actualizados con el flujo exacto; borrado del lead a pedido del particular y vencimiento automático a los `seller_leads.ttl_days` (propuesto 45).
- Eventos: `seller_lead_offered`, `seller_lead_interest`, `seller_lead_shared`, `seller_lead_closed`.
- Tests: pgTAP de que la agencia no ve contacto sin `shared`; snapshot de los emails de las dos puntas.

## Extras y hallazgos

### X-01 · Seguimiento en la UI

`user_listing_interactions.status` ya tiene `new | seen | interested | discarded | contacted | visit_scheduled | purchased`, `rejection_reason` y `note`; la UI solo ofrece Guardar y Descartar, y el selector de estado se retiró. Las agencias llevan esto en WhatsApp y una planilla. Para Pro: devolver el selector con `contacted`, `visit_scheduled`, `purchased`, campo de nota y filtro por estado en resultados y guardados. `listing_status_changed` ya existe como evento. Tamaño S. Exportación CSV **no**: Juan la retiró el 15/10 (`20261027120000_remove_csv_export.sql`) y sigue en reserva hasta que un Pro la pida.

### H-01 · El email no trae las preguntas

La landing promete «por email, con el precio comparado y las preguntas para hacerle al vendedor»; el email de oportunidad solo lleva a la ficha. Sumar las 3 primeras preguntas de `matches.seller_questions` al email (`email_html.py`, `templates.py`, snapshot nuevo) o corregir la landing. Tamaño S; conviene resolverlo antes de PAR-04 y PRO-01, que amplían ese bloque.

### Restricciones a tener en cuenta

- El tope de 50 lecturas LLM por día de `description_facts` ya se agota (2.696 avisos sin leer al 26/10, [PLAN_GEOCODIFICADO](PLAN_GEOCODIFICADO.md)). PAR-02 y PAR-04 suman consumo: cada uno define su propio tope en `app_config.llm_limits` y no comparte el presupuesto de descripciones.
- Facebook sigue siendo frágil y contra sus términos; ninguna función nueva puede depender de una fuente sola.
- Las búsquedas sin modelo (por carrocería) existen desde octubre: todo lo que agrupe «por modelo» tiene que contemplar `body_type` como agrupador alternativo.

## Secuencia propuesta

1. **Ciclo 1 (P0, con datos ya guardados):** H-01 → F-02 → PRO-01 (filtro y mensaje, sin push) → PAR-03 (por aviso) → PRO-02 (margen v1 y umbral en USD).
2. **Ciclo 2 (P1):** F-04 push → PRO-01 push → PAR-01 → PAR-02 → X-01.
3. **Ciclo 3 (P1/P2):** F-03 → PAR-03 (bloque del modelo) → PRO-02 (rotación) → PAR-04.
4. **Ciclo 4 (P2, con validación comercial):** F-01 → PAR-05 → PRO-05 → PRO-03 → PRO-04.

Orden de magnitud: ciclo 1 ≈ 8–10 días efectivos; ciclos 2 y 3 ≈ 10–14 cada uno; ciclo 4 ≈ 15–20. No es una fecha de entrega.

## Reserva

| Idea | Condición para priorizarla |
|---|---|
| Importar stock desde la tienda de ML (PRO-03 v2) | 3 Pro con stock cargado a mano piden la importación |
| Cobro por lead o Pro+ (PRO-05) | Leads compartidos y contactos efectivos medidos durante 2 meses |
| Equipos (Ruta C de BACKLOG_COMERCIAL) | Una agencia con más de una persona usando la misma cuenta lo pide |
| Exportación CSV | Un Pro concreto paga por ese flujo (decisión del 15/10) |
| Push para Particular | Métricas de PRO-01 muestran mejor clic que el email |
| WhatsApp | Sigue como en BACKLOG_COMERCIAL: pedido de clientes pagos y margen que cubra el costo |

## Registro de decisión

- [ ] Juan revisa los dolores y el orden de los ciclos.
- [ ] Juan define la primera tanda del ciclo 1 y abre el diseño (`docs/superpowers/specs/`) del primer ID.
- [ ] Juan carga los parámetros de `cost_estimator` y `dealer_margin` antes de que PAR-01 y PRO-02 salgan a producción.
- [ ] Términos y privacidad revisados antes de PAR-05 y PRO-05.

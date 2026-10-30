# PAR-01: Costo total estimado

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Track the steps below during implementation.

**Goal:** reemplazar el aviso fijo «8–10 %» por un costo total estimado en rango (precio, arancel DNRPA, sellos, formularios y patente anual), con cada número tomado de `app_config.cost_estimator` con su fuente y fecha. Se muestra en la ficha (con detalle), en la tarjeta y en el email de oportunidad, solo para el plan Particular. Diseño: [2026-10-30-par01-costo-total-design.md](../specs/2026-10-30-par01-costo-total-design.md). Parámetros aprobados: [2026-10-30-par01-parametros-costo-total.md](../specs/2026-10-30-par01-parametros-costo-total.md). Ítem PAR-01 del [backlog](../../BACKLOG_PRODUCTO_2026-10.md); Fase 2, fila 4, del [plan por fases](../../PLAN_FASES_BACKLOG_PRODUCTO_2026-10.md).

**Architecture:** una migración que solo siembra config (`cost_estimator` y `plan_limits.pass.total_cost`). Una calculadora pura por lado (`worker/intelligence/cost_estimator.py`, `web/lib/cost-estimator.ts`) y un resolvedor de jurisdicción del comprador por cercanía, ambos validados con el mismo JSON de vectores dorados. La web calcula en el servidor (ficha y tarjetas, con una consulta extra por página). El worker calcula en `on_matches` y guarda `payload['total_cost']`. Sin cambios en `match_cards`, `search_results` ni scores.

**Tech Stack:** Postgres/Supabase (pgTAP), Python 3.12 (pytest, `pythonpath = .` en `worker/`), Next 16 + vitest + Playwright.

**Dependencias:**
- Mergear `claude/f02-vendedor` (PR #58) en esta rama antes de la Task 2.
- Si el paso 2 de F-02 (`effective_seller`, `effectiveSeller`, `dealer_inferred`) todavía no está, usar la variante «solo `seller_type`» del diseño (decisión 4) y cambiar al helper cuando llegue.
- `templates.py` y los snapshots van después de PRO-02 (plan §4).

**Pendiente de Juan:** las cuatro preguntas del diseño (Free, aviso de agencia para Free/Pro, mínimo y Subte en pick-ups de CABA, informe de dominio con 4 MRPA).

**Tareas de Juan (no las hago):** OK para la migración en producción; OK para reiniciar el worker (`wait_idle`) y para Vercel; revisar los valores en `/admin/config` después de aplicar.

## Comandos

Desde `/home/user/par01`; nunca contra el piloto ni producción:

- pgTAP: `npx --yes supabase@2.119.0 test db`
- Base de tests del worker: `cd worker && python -m tools.test_db`
- Worker offline: `cd worker && python -m pytest -q -p no:cacheprovider`
- Worker con base: `cd worker && TEST_DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:54322/automotive_test python -m pytest -q -p no:cacheprovider -m db`
- Snapshots: `cd worker && UPDATE_SNAPSHOTS=1 python -m pytest -q tests/test_notifications_templates.py`, solo para los casos nuevos.
- Web: `cd web && npx vitest run`, `npm run typecheck`, `npx eslint <archivos>`
- e2e: `cd web && CI=1 npx playwright test <spec>`

Antes de empezar se anota la línea base de pgTAP y de `-m db`. Criterio: nada nuevo en rojo.

## Task 0: preparación

- [ ] Leer `web/CLAUDE.md` → `AGENTS.md` y la doc de Next 16 en `web/node_modules/next/dist/docs/`.
- [ ] Mergear la rama de F-02 y anotar si el paso 2 está (`grep -rn effectiveSeller web/lib`).
- [ ] Correr y anotar la línea base.
- [ ] En `automotive_test`, contar los avisos en ARS cuyo `fx_rate` no coincide con ninguna fila de `fx_rates` de su día (posible fallback de 1100). Si hay casos, consultar a Juan antes de la Task 6.
- [ ] Confirmar que `web/lib/data/argentina-locations.json` y `worker/normalization/data/ar_localities.json` son iguales.

## Task 1: pgTAP y migración

Files: `supabase/tests/par01_cost_estimator_test.sql`, `supabase/migrations/20261124120000_par01_cost_estimator.sql`, `supabase/seed.sql`.

- [ ] Releer `max(version)`. Usar `20261124120000` si sigue por encima de lo que sumaron F-02, PRO-01 y PRO-02; si no, renombrar.
- [ ] Escribir primero el test que falle (formato de `par02_risk_config_test.sql`):
  - existe la fila `cost_estimator`, con `as_of` = `2026-10-30` y `status` = `aprobado`;
  - cada bloque de la lista del diseño tiene `source` no vacío y `as_of` con formato de fecha;
  - valores de control: `dnrpa.min_mrpa` = 32, `patente.caba.brackets[2].fixed` = 507150, `patente.ba.ipc_factor.max` = 1.25, `stamp_tax_pct.rest.private.max` = 3.0, `domain_report.in_total` = false, `gestoria.official_value` null;
  - el insert es idempotente: un valor editado no se pisa al re-aplicarlo;
  - `plan_limits.pass.total_cost` = true y el resto de `plan_limits` queda intacto; con la clave en false, re-aplicar no la cambia;
  - `plan_feature` da true para un usuario `pass`, false para `free` y `pro`, y true para un admin;
  - `anon` y `authenticated` no tienen acceso a `app_config`.
- [ ] Escribir la migración (JSON exacto del diseño) y el mismo bloque en `seed.sql`. Aplicar en local, correr `python -m tools.test_db` y pgTAP verde respecto de la línea base.

## Task 2: vectores dorados

Files: `worker/tests/fixtures/cost_estimator/golden.json`.

- [ ] Formato: `{"config": <JSON del diseño>, "cases": [{name, input: {listing, jurisdiction, seller, fx_latest, today, config_patch?}, expect: {total_ars, total_usd, terms, extras, missing, line}}], "jurisdiction_cases": [{lat, lon, label, expect}]}`. Los valores esperados se calculan a mano en el JSON, no con el código.
- [ ] Casos (precio ARS 20.000.000, `R` = 1.300, `today` 2026-10-30, salvo que se diga otra cosa):
  1. CABA, particular, 2017 → crudo 21.188.950 – 21.517.532,5; línea «USD 16.290 – 16.560 (ARS 21.188.000 – 21.518.000)».
  2. Buenos Aires → 20.948.000 – 21.158.840.
  3. Resto → 20.527.000 – 21.278.840.
  4. AMBA (unión) → 20.948.000 – 21.517.532,5.
  5. Agencia en Buenos Aires → arancel 0,9–1 % y sellos 1–3 %.
  6. Vendedor null en Buenos Aires → unión de particular y agencia.
  7. Aviso en USD 15.000 con `fx_latest` 1.300 → `P` = 19.500.000.
  8. Aviso en USD sin `fx_latest` → `None`, falta `fx`.
  9. Aviso en ARS sin `fx_rate` → solo ARS, `total_usd` null, falta `fx`.
  10. Pick-up en CABA → 2,30 % plano, sin tope.
  11. CABA modelo 2001 → mínimo de patente 0; modelo 2002 → escala.
  12. Buenos Aires 1985 → falta `patente` (`pre_min_year`).
  13. Resto modelo 2016 → mínimo 0; 2017 → 0,85 %.
  14. ARS 2.000.000 → arancel en el mínimo de 32 MRPA (32.320 – 34.880).
  15. CABA, VF de 100.000.000 → tope de 6 %.
  16. CABA, VF de 500.000 → mínimo de 13.300.
  17. Resto con VF.max en 70 M y en 100 M → bandas de 2,5 % y 3 %.
  18. Jurisdicción null → faltan `stamp` y `patente`; el total suma arancel y formularios.
  19. Año null → falta `patente`.
  20. Precio parcial → `None`.
  21. `config_patch` con escalas de Buenos Aires desordenadas → falta `patente` («faltan parámetros»).
  22. `form_12` sin `source` → falta `forms`.
  23. Sin `as_of` en la raíz → `None`.
  24. Redondeo: un caso con `min == max` tras redondear muestra un solo número.
- [ ] Casos de jurisdicción (`jurisdiction_cases`):
  - «AMBA» con el centro de CABA → `amba`;
  - «CABA» y «Ciudad de Buenos Aires, CABA» → `caba`;
  - Zona Norte → `ba` (San Isidro); La Plata → `ba`; Rosario → `rest`;
  - el punto -34.535,-58.47 → `caba`, como da hoy `nearest_locality`;
  - lat null → null.

## Task 3: calculadora del worker (tests primero)

Files: `worker/intelligence/cost_estimator.py`, `worker/intelligence/copy.py`, `worker/tests/test_cost_estimator.py`.

- [ ] Tests que fallen:
  - todos los `cases` y `jurisdiction_cases` del JSON dorado;
  - `parse_config`: cada regla del validador deja su bloque en `None` (rango invertido, k > 1, `from` no creciente, banda final no null, `as_of` inválido, `source` vacío), sin tirar excepción y sin defaults numéricos;
  - `review_status(cfg, today)`: `stale` a los 121 días, nada a los 120, `due` en diciembre y enero, `missing` sin `review`;
  - formato: miles con punto y redondeo hacia afuera.
- [ ] Implementar:
  - `parse_config`, `buyer_jurisdiction(lat, lon, label)` (con `zone.nearest_locality`; sin `derive_zone`), `estimate(...)`, `format_line(estimate)` (códigos más números; el texto sale de `copy.TOTAL_COST`) y `review_status`;
  - solo `math.floor`/`math.ceil`; `base * pct / 100`.
- [ ] Copy `TOTAL_COST` en `intelligence/copy.py`. Lint por funcionalidad (formato de `test_notifications_price_track.py:66-75`) con «precio final», «costo real», «costo exacto» y «total real», además de `FORBIDDEN_TERMS`.

## Task 4: calculadora web (tests primero)

Files: `web/lib/cost-estimator.ts`, `web/lib/cost-estimator.test.ts`, `web/lib/buyer-jurisdiction.ts`, `web/lib/buyer-jurisdiction.test.ts`, `web/lib/format.ts`, `web/lib/format.test.ts`, `web/lib/copy.ts`, `web/lib/copy.test.ts`.

- [ ] Tests que fallen:
  - el mismo JSON dorado, leído con `readFileSync(path.resolve(__dirname, "../../worker/tests/fixtures/cost_estimator/golden.json"))`;
  - los mismos casos de parser, `costEstimatorReview` y formato que en Python;
  - el lint de `copy.test.ts` escanea también `lib/cost-estimator.ts`;
  - un test explícito de los valores de `COST_ESTIMATE` (como el de `TRACKING`).
- [ ] Implementar:
  - `CostEstimatorInput` (zod estricto, que reusa el validador), `parseCostEstimator` (tolerante), `estimateCost`, `costEstimatorReview`;
  - `formatArsRange`/`formatUsdRange` en `format.ts`, con miles a mano y sin `Intl`;
  - `buyerJurisdiction` en `buyer-jurisdiction.ts` con `import "server-only"`: el mismo algoritmo de `nearest_locality` (preselección por distancia plana con el mismo número de candidatos y haversine), con caché por `(lat, lon)`;
  - `COST_ESTIMATE` en `copy.ts`.
- [ ] vitest, typecheck y eslint de los archivos tocados.

## Task 5: config y admin web

Files: `web/lib/config.ts`, `web/lib/config.test.ts`, `web/lib/admin-config.ts`, `web/lib/admin-config.test.ts`, `web/components/admin/config-forms.tsx`, `web/app/admin/config/page.tsx`, `web/lib/admin-dashboard-data.ts`, `web/lib/admin-dashboard.ts`, `web/components/admin/dashboard-ui.tsx`, tests de admin-dashboard.

- [ ] Tests que fallen:
  - `webConfig().costEstimator`: `null` sin fila, `null` si la fila es inválida, y bloques parciales tal cual;
  - `validateConfigChange("cost_estimator", …)`: acepta el JSON del diseño y rechaza cada regla con su mensaje (`cost_estimator.<ruta>: …`);
  - `plan_limits` acepta `total_cost` booleano y rechaza un string;
  - `DashboardAttention`: muestra el ítem con `as_of` de hace 121 días y en diciembre o enero, y no lo muestra a los 120 días en octubre.
- [ ] Implementar:
  - `WebConfig.costEstimator`, con la clave en el `.in()` (`config.ts:66`);
  - la rama del validador, con `total_cost` en el schema de `plan_limits` (`admin-config.ts:19,130`) y su toggle en `config-forms.tsx`;
  - `NAMES` y `HINTS` del diseño;
  - el aviso en el dashboard y en la tarjeta de la clave.

## Task 6: datos y email del worker (tests primero)

Files: `worker/db/repos/notifications.py`, `worker/db/repos/fx.py`, `worker/notifications/service.py`, `worker/notifications/templates.py`, `worker/tests/test_notifications_total_cost.py`, `worker/tests/notification_fixtures.py`, `worker/tests/snapshots/notifications/*.txt`, `worker/tests/test_notifications_postgres.py` (o el archivo `-m db` vigente de audiencias).

- [ ] Offline, tests que fallen:
  - `total_cost_line(None)` da `None`; con payload da la línea exacta; con `missing` dice «(sin patente)»;
  - `on_matches` con audiencia sin flag no agrega la clave; con flag la agrega solo a oportunidades (no a `new_match`), con la jurisdicción de esa búsqueda;
  - un aviso en USD sin cotización guardada no lleva la clave (nunca el fallback);
  - lint de copy sobre los casos nuevos.
- [ ] Snapshots:
  - casos nuevos `opportunity_total_cost` (CABA, completo) y `opportunity_total_cost_missing` (sin jurisdicción);
  - los snapshots existentes (`opportunity*.txt` y el resto) quedan idénticos byte a byte; se verifica con `git diff --exit-code` sobre ellos;
  - `PRDCopyTests` sin cambios.
- [ ] `-m db`, tests que fallen:
  - `profile_audiences` devuelve `total_cost` (true para `pass`, false para `free`), `origin_lat`, `origin_lon` y `location_label`;
  - `fx.latest_stored(cx)` devuelve la última fila (blue primero), o `None` sin filas, sin llamar a la red.
- [ ] Implementar:
  - columnas de audiencia: `public.plan_feature(sp.user_id, 'total_cost')` como `_THRESHOLD`, `sp.origin_lat`, `sp.origin_lon` y `sp.filters->>'location_label'`;
  - `latest_stored`;
  - en `on_matches`, una lectura de config y de cotización por lote, y `effective_seller(row)` desde la fila de `rows_for_scoring`;
  - `payload['total_cost']` y la línea después de `price_track_line`.

## Task 7: ficha

Files: `web/components/app/cost-estimate.tsx`, `web/components/app/cost-estimate.test.tsx`, `web/lib/cost-estimate-data.ts`, `web/app/app/listings/[id]/page.tsx`, `web/app/app/listings/actions.ts`, `web/lib/listing-actions.test.ts`, `web/components/app/dealer-fees-notice.tsx` (se borra).

- [ ] Tests que fallen (`renderToStaticMarkup`):
  - línea completa;
  - variantes «sin patente», AMBA, resto, «posible agencia», vendedor sin informar y «sin dólar del día»;
  - informe de dominio y gestoría fuera del total;
  - «parámetros al 30/10» y la fuente por término;
  - sin estimación no se renderiza nada;
  - ningún texto contiene «8–10» ni «precio real».
- [ ] Test de la acción: `trackTotalCostExpanded` valida con zod y llama a `track` con `total_cost_expanded` y `{listing_id, jurisdiction, missing}`.
- [ ] Implementar `cost-estimate-data.ts` (`server-only`):
  - `my_plan_feature('total_cost')`, `webConfig`, `latestFx()` (cliente admin, `cache()`) y el origen de la búsqueda `best` (o `profiles.default_origin_*`);
  - el componente, con `<details>` y un hijo cliente para el evento;
  - el reemplazo en `page.tsx:180` y el borrado de `DealerFeesNotice`.

## Task 8: tarjeta

Files: `web/components/app/listing-card.tsx`, `web/lib/listing-card.test.ts`, `web/app/app/searches/[id]/page.tsx`, `web/app/app/page.tsx`, `web/app/app/saved/page.tsx`, `web/lib/cost-estimate-data.ts`.

- [ ] Tests que fallen:
  - la tarjeta con prop `costLine` muestra `cost-estimate-line`; sin la prop, el markup actual queda igual;
  - `costLinesFor(cards)`: una sola consulta a `listings` por página y orígenes por `search_profile_id` distinto; sin el flag, cero consultas.
- [ ] Implementar `costLinesFor` y pasar `costLine` desde las tres páginas.

## Task 9: e2e

Files: `web/e2e/support/db.ts`, `web/e2e/total-cost.spec.ts`.

- [ ] Ampliar `Seed`:
  - `cost_estimator` (el JSON del diseño), `plan_limits.pass.total_cost` y el plan del usuario;
  - un aviso en ARS de 20.000.000 con `fx_rate` 1300, modelo 2017, particular;
  - búsqueda con origen «Palermo, CABA».
- [ ] Spec a 375 px:
  - la ficha muestra «Costo total estimado: USD 16.290 – 16.560 (ARS 21.188.000 – 21.518.000)»;
  - «Ver detalle» abre el desglose y deja una fila `total_cost_expanded` en `events`;
  - la tarjeta de resultados muestra la línea;
  - `document.documentElement.scrollWidth <= 375` en la ficha y en resultados;
  - con un usuario `free` (flag apagado) no hay línea ni texto «8–10»;
  - un aviso de agencia ya no muestra `dealer-fees-notice`.
- [ ] `acceptance.spec.ts`, `seller.spec.ts` (si F-02 está) y `comparables.spec.ts` sin regresiones.

## Task 10: verificación y cierre

- [ ] Todos los comandos verdes respecto de la línea base; typecheck y eslint de los archivos tocados.
- [ ] Revisión de copy: «estimado» siempre presente; ningún término prohibido; las fuentes de la ficha coinciden con la config.
- [ ] Actualizar `docs/BACKLOG_PRODUCTO_2026-10.md`: PAR-01 con valores sembrados en lugar de null (decisión de Juan del 30/10), orden por costo total fuera de v1 y `results_sorted_total_cost` reservado.
- [ ] Commit (sin push desde esta sesión).
- [ ] **Parar:** Juan aplica la migración (releyendo `max(version)`), reinicia el worker con `wait_idle`, despliega la web y revisa `/admin/config`.

## Rollback

- Rápido: `plan_limits.pass.total_cost = false` en `/admin/config` apaga ficha, tarjeta y email sin deploy. El worker lo toma en el próximo lote (es por fila de audiencia, sin caché de config).
- Código: revert de web y worker; `DealerFeesNotice` vuelve con el revert.
- Base: la fila `cost_estimator` y la clave `total_cost` quedan sin uso. Se pueden borrar con `delete from app_config where key = 'cost_estimator'` y `value #- '{pass,total_cost}'` en `plan_limits`, con OK de Juan.
- Sin bump ni rescore: no hay nada que deshacer en scores ni en alertas enviadas.

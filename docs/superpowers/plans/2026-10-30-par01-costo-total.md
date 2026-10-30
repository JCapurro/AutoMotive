# PAR-01: Costo total estimado

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Track the steps below during implementation.

**Goal:** reemplazar el aviso fijo «8–10 %» por un costo total estimado en rango (precio, arancel DNRPA, sellos, formularios y patente anual), con cada número tomado de `app_config.cost_estimator` con su fuente y fecha. Se muestra en la ficha (con detalle), en la tarjeta y en el email de oportunidad, solo con el flag `total_cost` (Particular; Free durante el piloto). Diseño: [2026-10-30-par01-costo-total-design.md](../specs/2026-10-30-par01-costo-total-design.md). Parámetros aprobados: [2026-10-30-par01-parametros-costo-total.md](../specs/2026-10-30-par01-parametros-costo-total.md). Ítem PAR-01 del [backlog](../../BACKLOG_PRODUCTO_2026-10.md); Fase 2, fila 4, del [plan por fases](../../PLAN_FASES_BACKLOG_PRODUCTO_2026-10.md).

**Architecture:** una migración que solo siembra config (`cost_estimator`, `plan_limits.pass.total_cost` y `plan_limits.free.total_cost`). Una calculadora pura por lado (`worker/intelligence/cost_estimator.py`, `web/lib/cost-estimator.ts`) un resolvedor de jurisdicción del comprador por cercanía (unión de las zonas de la búsqueda, con corte por distancia) y un armador de la entrada desde la fila del aviso. Los tres se validan con el mismo JSON de vectores dorados. La web calcula en el servidor (ficha y tarjetas, con una consulta extra por página). El worker calcula en `on_matches` y guarda `payload['total_cost']`. Sin cambios en `match_cards`, `search_results` ni scores.

**Tech Stack:** Postgres/Supabase (pgTAP), Python 3.12 (pytest, `pythonpath = .` en `worker/`), Next 16 + vitest + Playwright.

**Dependencias:**
- Mergear `claude/f02-vendedor` (PR #58) en esta rama antes de la Task 2.
- Si el paso 2 de F-02 (`effective_seller`, `effectiveSeller`, `dealer_inferred`) todavía no está, usar la variante «solo `seller_type`» del diseño (decisión 4) y cambiar al helper cuando llegue.
- `templates.py` y los snapshots van después de PRO-02 (plan §4).

**Respondido por Juan (30/10, «sí a todo»):** Free prendido durante el piloto, aviso de agencia borrado para todos, mínimo y Subte también en pick-ups de CABA, informe de dominio con 4 MRPA.

**Pendiente de Juan:** la pregunta 1 del diseño, `buyer_zone.max_locality_km` (recomendado 80) y `fx.max_age_days` (recomendado 3). Bloquea solo la Task 1; las demás tareas leen los valores de la config.

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

- [x] Leer `web/CLAUDE.md` → `AGENTS.md` y la doc de Next 16 en `web/node_modules/next/dist/docs/`.
- [x] Mergear la rama de F-02 y anotar si el paso 2 está (`grep -rn effectiveSeller web/lib`).
- [x] Correr y anotar la línea base.
- [x] En `automotive_test`, contar los avisos en ARS cuyo `fx_rate` no coincide con ninguna fila de `fx_rates` de su día (posible fallback de 1100). Si hay casos, consultar a Juan antes de la Task 6.
- [x] Confirmar que `web/lib/data/argentina-locations.json` y `worker/normalization/data/ar_localities.json` son iguales.
- [x] Confirmar que `rows_for_scoring` (`SELECT l.*`, `worker/db/repos/listings.py:307`) trae `price_partial`, `description_facts`, `body_type` y `dealer_inferred` (este último, después de F-02).

## Task 1: pgTAP y migración

Files: `supabase/tests/par01_cost_estimator_test.sql`, `supabase/migrations/20261126120000_par01_cost_estimator.sql`, `supabase/seed.sql`.

- [x] Releer `max(version)`. Usar `20261126120000` (F-02 ocupó 20261123–25) si sigue por encima de lo que sumaron F-02, PRO-01 y PRO-02; si no, renombrar.
- [x] Escribir primero el test que falle (formato de `par02_risk_config_test.sql`):
  - existe la fila `cost_estimator`, con `as_of` = `2026-10-30` y `status` = `aprobado`;
  - cada bloque de la lista del diseño tiene `source` no vacío y `as_of` con formato de fecha;
  - valores de control: `dnrpa.min_mrpa` = 32, `patente.caba.brackets[2].fixed` = 507150, `patente.ba.ipc_factor.max` = 1.25, `stamp_tax_pct.rest.private.max` = 3.0, `domain_report.in_total` = false, `gestoria.official_value` null;
  - el insert es idempotente: un valor editado no se pisa al re-aplicarlo;
  - `plan_limits.pass.total_cost` y `plan_limits.free.total_cost` = true y el resto de `plan_limits` queda intacto; con la clave en false, re-aplicar no la cambia;
  - `plan_feature` da true para un usuario `pass` y uno `free`, false para `pro`, y true para un admin;
  - `fx.max_age_days` y `buyer_zone.max_locality_km` con los valores que confirme Juan;
  - `anon` y `authenticated` no tienen acceso a `app_config`.
- [x] Escribir la migración (JSON exacto del diseño). En `seed.sql`, editar a mano el literal de `plan_limits` (`seed.sql:41-46`): `"total_cost": true` dentro de `pass` y de `free`, porque se inserta con `on conflict do nothing` y ninguna migración lo actualiza. Sumar también la fila `cost_estimator`. Un test pgTAP corre sobre la base sembrada y verifica las dos cosas. Aplicar en local, correr `python -m tools.test_db` y pgTAP verde respecto de la línea base.

## Task 2: vectores dorados

Files: `worker/tests/fixtures/cost_estimator/golden.json`.

- [x] Formato: `{"config": <JSON del diseño>, "cases": [{name, input: {listing, jurisdiction, seller, fx_latest, config_patch?}, expect: {total_ars, total_usd, terms, extras, missing, line}}], "jurisdiction_cases": [{zones, expect}], "input_cases": [{row, zones, fx_latest, expect: {listing, jurisdiction, seller} | null}]}`. Los valores esperados se calculan a mano en el JSON, no con el código. `line` es el string exacto del encabezado, con el sufijo de faltantes.
- [x] Casos (precio ARS 20.000.000, carrocería `sedan`, `R` = 1.300, salvo que se diga otra cosa):
  1. CABA, particular, 2017 → crudo 21.188.950 – 21.517.532,5; línea «USD 16.290 – 16.560 (ARS 21.188.000 – 21.518.000)».
  2. Buenos Aires → 20.948.000 – 21.158.840.
  3. Resto → 20.527.000 – 21.278.840.
  4. AMBA (`{caba, ba}`) → 20.948.000 – 21.517.532,5.
  5. Agencia en Buenos Aires → arancel 0,9–1 % y sellos 1–3 %.
  6. Vendedor null en Buenos Aires → unión de particular y agencia.
  7. Aviso en USD 15.000 con `fx_latest` `{rate: 1300, kind: blue, date: 2026-10-29}` → `P` = 19.500.000; el detalle dice «dólar blue del 29/10».
  8. Aviso en USD sin `fx_latest` → estimación vacía: `p_ars`, `terms` y totales null, `missing` = `[fx]`; línea «Costo total estimado: sin dólar del día, no se puede estimar».
  9. Aviso en ARS sin `fx_rate` → solo ARS, `total_usd` null, falta `fx`; línea «… ARS 21.188.000 – 21.518.000 (sin dólar del día)».
  10. Pick-up en CABA → 2,30 % plano, sin tope. Patente con VF.min = 14.000.000: crudo `321999.99999999994` en los dos lenguajes, detalle «ARS 322.000 – 506.000» (sin el margen saldría 321.900 – 506.100). Total 21.130.000 – 21.324.900; línea «USD 16.250 – 16.410 (ARS 21.130.000 – 21.325.000)».
  11. CABA modelo 2001 → mínimo de patente 0; modelo 2002 → escala (con `values_year` 2026).
  12. Buenos Aires 1985 → falta `patente` (`pre_min_year`).
  13. Resto modelo 2016 → mínimo 0; 2017 → 0,85 %.
  14. ARS 2.000.000 → arancel en el mínimo de 32 MRPA (32.320 – 34.880).
  15. CABA, VF de 100.000.000 → tope de 6 %.
  16. CABA, VF de 500.000 → mínimo de 13.300.
  17. Resto con VF.max en 70 M y en 100 M → bandas de 2,5 % y 3 %.
  18. Jurisdicción null → faltan `sellos` y `patente`; total 20.208.000 – 20.218.900; línea «Costo total estimado (sin sellos ni patente): USD 15.540 – 15.560 (ARS 20.208.000 – 20.219.000)».
  19. CABA, año null → falta `patente`; línea «Costo total estimado (sin patente): USD 16.000 – 16.020 (ARS 20.808.000 – 20.819.000)».
  20. (Precio parcial: pasa a `input_cases`.)
  21. `config_patch` con escalas de Buenos Aires desordenadas → falta `patente` («faltan parámetros»).
  22. `form_12` sin `source` → falta `formularios`; línea con «(sin formularios)».
  23. Sin `as_of` en la raíz → `None`.
  24. Redondeo: un caso con `min == max` tras redondear muestra un solo número.
  25. Sufijos: jurisdicción null + `form_12` inválido → «(sin sellos, formularios ni patente)»; `dnrpa` ausente → «(sin arancel)»; jurisdicción null + `dnrpa` ausente + año null → «(sin arancel, sellos ni patente)».
  26. CABA con `body_type` null → unión de los incisos a) y b): patente «ARS 322.000 – 698.700», total 21.130.000 – 21.517.592,5, línea «USD 16.250 – 16.560 (ARS 21.130.000 – 21.518.000)».
  27. Enero: `config_patch` sin cambios y la misma fila del caso 11 → el mismo resultado. Con `values_year` 2027 en el patch, el modelo 2002 pasa a mínimo 0. Así se prueba que el corte sale de `values_year` y no del reloj.
  28. Varias jurisdicciones `{caba, rest}` → sellos 1–3 % (unión de CABA y resto) y patente con el mínimo de resto y el máximo de CABA.
  29. `patente.values_year` ausente → falta `patente`.
- [x] Casos de jurisdicción (`jurisdiction_cases`, con `zones` = `[{lat, lon, label}]`):
  - «AMBA» con el centro de CABA → `{caba, ba}`;
  - «CABA» y «Ciudad de Buenos Aires, CABA» → `{caba}`;
  - Zona Norte → `{ba}` (San Isidro); La Plata → `{ba}`; Rosario → `{rest}`;
  - el punto -34.535,-58.47 → `{caba}`, como da hoy `nearest_locality`;
  - lat null → null; `[]` → null;
  - Montevideo (-34.9011, -56.1645, a 106,8 km) → null con el corte de 80; Punta del Este → null;
  - Palermo + Córdoba → `{caba, rest}`; Palermo + Montevideo → null (una zona sin dato anula todo);
  - rótulo «Rosario (zona aproximada)» → `{rest}`, y el texto lo cita tal cual.
- [x] Casos de armado (`input_cases`), los mismos para `build_input` (Python) y `buildCostInput` (TS):
  - `price_partial` true → null;
  - `description_facts.price_check.published_partial` true y `price_partial` false → null;
  - `published_kind` `installment` → null; `cash` → entrada con `cash` true;
  - `seller_type` `private` con `dealer_inferred` true → vendedor `dealer`; `seller_type` null → null;
  - aviso en USD con `fx_latest` → `P` = `price × rate`; aviso en ARS → `R` = `fx_rate` aunque haya `fx_latest`;
  - búsqueda con `extra_locations` → la unión de zonas;
  - precio 0 o null → null.
## Task 3: calculadora del worker (tests primero)

Files: `worker/intelligence/cost_estimator.py`, `worker/intelligence/copy.py`, `worker/tests/test_cost_estimator.py`.

- [x] Tests que fallen:
  - todos los `cases`, `jurisdiction_cases` e `input_cases` del JSON dorado;
  - `parse_config`: cada regla del validador deja su bloque en `None` (rango invertido, k > 1, `from` no creciente, banda final no null, `as_of` inválido, `source` vacío), sin tirar excepción y sin defaults numéricos;
  - `review_status(cfg, today)`: `stale` a los 121 días, nada a los 120, `missing` sin `review`. `due` con `as_of` 2026-10-30 el 2026-12-20; nada con `as_of` 2026-12-05 el 2026-12-20 ni el 2027-01-15; `due` con `as_of` 2026-11-30 el 2027-01-02;
  - formato: miles con punto, redondeo hacia afuera con el margen (`floor_to(321999.99999999994, 100)` = 322000 y `ceil_to(506000.00000000006, 100)` = 506000);
  - `missing_suffix` para cada combinación de códigos.
- [x] Implementar:
  - `parse_config`, `buyer_jurisdiction(zones, cfg)` (con `zone.nearest_locality` más la distancia; sin `derive_zone`), `build_input(row, zones, fx_latest, cfg)` (con `pipeline.ingest.published_partial` e `effective_seller`), `estimate(...)`, `missing_suffix(codes)`, `format_line(estimate)` (códigos más números; el texto sale de `copy.TOTAL_COST`) y `review_status`;
  - redondeo solo con `floor_to`/`ceil_to` (margen 0,01); `base * pct / 100`.
- [x] Copy `TOTAL_COST` en `intelligence/copy.py`. Lint por funcionalidad (formato de `test_notifications_price_track.py:66-75`) con «precio final», «costo real», «costo exacto» y «total real», además de `FORBIDDEN_TERMS`.

## Task 4: calculadora web (tests primero)

Files: `web/lib/cost-estimator.ts`, `web/lib/cost-estimator.test.ts`, `web/lib/buyer-jurisdiction.ts`, `web/lib/buyer-jurisdiction.test.ts`, `web/lib/format.ts`, `web/lib/format.test.ts`, `web/lib/copy.ts`, `web/lib/copy.test.ts`.

- [x] Tests que fallen:
  - el mismo JSON dorado (las tres listas), leído con `readFileSync(path.resolve(__dirname, "../../worker/tests/fixtures/cost_estimator/golden.json"))`;
  - los mismos casos de parser, `costEstimatorReview` y formato que en Python;
  - el lint de `copy.test.ts` escanea también `lib/cost-estimator.ts`;
  - un test explícito de los valores de `COST_ESTIMATE` (como el de `TRACKING`).
- [x] Implementar:
  - `CostEstimatorInput` (zod estricto, que reusa el validador), `parseCostEstimator` (tolerante), `buildCostInput` (con `publishedIsPartial`, `isCashPrice` y `effectiveSeller`), `estimateCost`, `missingSuffix`, `costEstimatorReview`;
  - `formatArsRange`/`formatUsdRange` en `format.ts`, con miles a mano, sin `Intl` y con `floorTo`/`ceilTo` (margen 0,01);
  - `buyerJurisdiction(zones, cfg)` en `buyer-jurisdiction.ts` con `import "server-only"`: el mismo algoritmo de `nearest_locality` (preselección por distancia plana con el mismo número de candidatos y haversine), que devuelve también la distancia, con caché por `(lat, lon)`, el corte `buyer_zone.max_locality_km` y la unión de zonas;
  - `COST_ESTIMATE` en `copy.ts`.
- [x] vitest, typecheck y eslint de los archivos tocados.

## Task 5: config y admin web

Files: `web/lib/config.ts`, `web/lib/config.test.ts`, `web/lib/admin-config.ts`, `web/lib/admin-config.test.ts`, `web/components/admin/config-forms.tsx`, `web/app/admin/config/page.tsx`, `web/lib/admin-dashboard-data.ts`, `web/lib/admin-dashboard.ts`, `web/components/admin/dashboard-ui.tsx`, tests de admin-dashboard.

- [ ] Tests que fallen:
  - `webConfig().costEstimator`: `null` sin fila, `null` si la fila es inválida, y bloques parciales tal cual;
  - `validateConfigChange("cost_estimator", …)`: acepta el JSON del diseño y rechaza cada regla con su mensaje (`cost_estimator.<ruta>: …`);
  - `plan_limits` acepta `total_cost` booleano y rechaza un string;
  - `DashboardAttention`: muestra el ítem con `as_of` de hace 121 días y en diciembre con `as_of` de octubre; no lo muestra a los 120 días en octubre ni con `as_of` 2026-12-05 el 2026-12-20.
- [ ] Implementar:
  - `WebConfig.costEstimator`, con la clave en el `.in()` (`config.ts:66`);
  - la rama del validador, con `total_cost` en el schema de `plan_limits` (`admin-config.ts:19,130`) y su toggle en `config-forms.tsx`;
  - `NAMES` y `HINTS` del diseño;
  - el aviso en el dashboard y en la tarjeta de la clave.

## Task 6: datos y email del worker (tests primero)

Files: `worker/db/repos/notifications.py`, `worker/db/repos/fx.py`, `worker/notifications/service.py`, `worker/notifications/templates.py`, `worker/tests/test_notifications_total_cost.py`, `worker/tests/notification_fixtures.py`, `worker/tests/snapshots/notifications/*.txt`, `worker/tests/test_notifications_postgres.py` (o el archivo `-m db` vigente de audiencias).

- [ ] Offline, tests que fallen:
  - `total_cost_line(None)` da `None`; con payload da la línea exacta; con `missing` usa `missing_suffix`: `[patente]` → «(sin patente)», `[sellos, patente]` (sin jurisdicción) → «(sin sellos ni patente)», `[formularios]` → «(sin formularios)»; `[fx]` en un aviso en ARS → «(sin dólar del día)» al final; `[fx]` en un aviso en USD → «sin dólar del día, no se puede estimar»;
  - `on_matches` con audiencia sin flag no agrega la clave; con flag la agrega solo a oportunidades (no a `new_match`), con la jurisdicción de esa búsqueda (origen más `extra_locations`);
  - `on_matches` con `cost_estimator` ausente, y con `cost_estimator` sin `as_of` válido, no agrega la clave aunque la audiencia tenga el flag, y el email sale sin la línea (el caso «sin parámetros cargados» del backlog);
  - `on_matches` con un aviso parcial (`price_partial` o `price_check.published_partial`) no agrega la clave;
  - un aviso en USD con la última cotización guardada más vieja que `fx.max_age_days` guarda `missing: [fx]` y totales null (nunca el fallback);
  - lint de copy sobre los casos nuevos.
- [ ] Snapshots:
  - casos nuevos `opportunity_total_cost` (CABA, completo, «con parámetros»), `opportunity_total_cost_missing` (sin jurisdicción, «(sin sellos ni patente)») y `opportunity_total_cost_no_config` (flag prendido y sin `cost_estimator`: idéntico a `opportunity.txt`);
  - los snapshots existentes (`opportunity*.txt` y el resto) quedan idénticos byte a byte; se verifica con `git diff --exit-code` sobre ellos;
  - `PRDCopyTests` sin cambios.
- [ ] `-m db`, tests que fallen:
  - `profile_audiences` devuelve `total_cost` (true para `pass`, false para `free`), `origin_lat`, `origin_lon` y `location_label`;
  - `fx.latest_stored(cx)` devuelve la fila blue más reciente aunque haya una oficial más nueva, la oficial más reciente si no hay blue, o `None` sin filas, sin llamar a la red. Devuelve `{rate, kind, date}`; el filtro por `fx.max_age_days` lo aplica `build_input`.
- [ ] Implementar:
  - columnas de audiencia: `public.plan_feature(sp.user_id, 'total_cost')` como `_THRESHOLD`, `sp.origin_lat`, `sp.origin_lon`, `sp.filters->>'location_label'` y `sp.filters->'extra_locations'`;
  - `latest_stored`;
  - en `on_matches`, una lectura de config y de cotización por lote, y `build_input(row, zones, fx_latest, cfg)` sobre la fila de `rows_for_scoring` (la misma regla de parcial que la ingesta y el mismo vendedor efectivo);
  - `payload['total_cost']` y la línea después de `price_track_line`.

## Task 7: ficha

Files: `web/components/app/cost-estimate.tsx`, `web/components/app/cost-estimate.test.tsx`, `web/lib/cost-estimate-data.ts`, `web/app/app/listings/[id]/page.tsx`, `web/app/app/listings/actions.ts`, `web/lib/listing-actions.test.ts`, `web/components/app/dealer-fees-notice.tsx` (se borra).

- [ ] Tests que fallen (`renderToStaticMarkup`):
  - línea completa;
  - variantes «(sin patente)», «(sin sellos ni patente)», AMBA, resto, varias zonas, «posible agencia», vendedor sin informar, «sin dólar del día» (ARS) y «no se puede estimar» (USD);
  - rótulo «Precio de contado» o «Precio publicado» según `isCashPrice`, como la ficha; aviso en USD con «USD 15.000 = ARS 19.500.000» y «dólar blue del 29/10»;
  - la nota «Montos redondeados hacia afuera»;
  - informe de dominio y gestoría fuera del total;
  - «parámetros al 30/10» y la fuente por término;
  - sin estimación no se renderiza nada;
  - ningún texto contiene «8–10» ni «precio real».
- [ ] Test de la acción: `trackTotalCostExpanded` valida con zod y llama a `track` con `total_cost_expanded` y `{listing_id, jurisdiction, missing}`.
- [ ] Implementar `cost-estimate-data.ts` (`server-only`):
  - `my_plan_feature('total_cost')`, `webConfig`, `latestFx()` (cliente admin, `cache()`, blue más reciente y si no la oficial), las zonas de la búsqueda `best` (origen más `extra_locations`) o `profiles.default_origin_*`, y `buildCostInput` sobre la fila que ya lee la página;
  - el componente, con `<details>` y un hijo cliente para el evento;
  - el reemplazo en `page.tsx:180` y el borrado de `DealerFeesNotice`.

## Task 8: tarjeta

Files: `web/components/app/listing-card.tsx`, `web/lib/listing-card.test.ts`, `web/app/app/searches/[id]/page.tsx`, `web/app/app/page.tsx`, `web/app/app/saved/page.tsx`, `web/lib/cost-estimate-data.ts`.

- [ ] Tests que fallen:
  - la tarjeta con prop `costLine` muestra `cost-estimate-line`; sin la prop, el markup actual queda igual;
  - `costLinesFor(cards)`: una sola consulta a `listings` por página con `price, currency, price_usd, fx_rate, price_partial, description_facts, seller_type, dealer_inferred, year, body_type`, y zonas por `search_profile_id` distinto; sin el flag, cero consultas;
  - una tarjeta de un aviso parcial (`price_partial` o `price_check.published_partial`) no tiene línea, igual que la ficha;
  - una tarjeta sin `search_profile_id` (inicio o guardados) usa `profiles.default_origin_*`; sin origen, la línea dice «(sin sellos ni patente)».
- [ ] Implementar `costLinesFor` (sobre `buildCostInput`, sin reimplementar la regla de parcial ni el vendedor) y pasar `costLine` desde las tres páginas.

## Task 9: e2e

Files: `web/e2e/support/db.ts`, `web/e2e/total-cost.spec.ts`.

- [ ] Ampliar `Seed`:
  - `cost_estimator` (el JSON del diseño), `plan_limits.pass.total_cost` y el plan del usuario;
  - un aviso en ARS de 20.000.000 con `fx_rate` 1300, modelo 2017, carrocería `sedan`, particular;
  - búsqueda con origen «Palermo, CABA».
- [ ] Spec a 375 px:
  - la ficha muestra «Costo total estimado: USD 16.290 – 16.560 (ARS 21.188.000 – 21.518.000)»;
  - «Ver detalle» abre el desglose y deja una fila `total_cost_expanded` en `events`;
  - la tarjeta de resultados muestra la línea;
  - `document.documentElement.scrollWidth <= 375` en la ficha y en resultados;
  - con un usuario `pro` (sin el flag) no hay línea ni texto «8–10»; con uno `free` sí hay línea (piloto);
  - un aviso de agencia ya no muestra `dealer-fees-notice`.
- [ ] `acceptance.spec.ts`, `seller.spec.ts` (si F-02 está) y `comparables.spec.ts` sin regresiones.

## Task 10: verificación y cierre

- [ ] Todos los comandos verdes respecto de la línea base; typecheck y eslint de los archivos tocados.
- [ ] Revisión de copy: «estimado» siempre presente; ningún término prohibido; las fuentes de la ficha coinciden con la config.
- [ ] Actualizar `docs/BACKLOG_PRODUCTO_2026-10.md`: PAR-01 con valores sembrados en lugar de null (decisión de Juan del 30/10), orden por costo total fuera de v1 y `results_sorted_total_cost` reservado.
- [ ] Commit (sin push desde esta sesión).
- [ ] **Parar:** Juan aplica la migración (releyendo `max(version)`), reinicia el worker con `wait_idle`, despliega la web y revisa `/admin/config`.

## Rollback

- Rápido: `plan_limits.pass.total_cost = false` (y `free.total_cost = false`) en `/admin/config` apaga ficha, tarjeta y email sin deploy. El worker lo toma en el próximo lote (es por fila de audiencia, sin caché de config).
- Código: revert de web y worker; `DealerFeesNotice` vuelve con el revert.
- Base: la fila `cost_estimator` y la clave `total_cost` quedan sin uso. Se pueden borrar con `delete from app_config where key = 'cost_estimator'` y `value #- '{pass,total_cost}' #- '{free,total_cost}'` en `plan_limits`, con OK de Juan.
- Sin bump ni rescore: no hay nada que deshacer en scores ni en alertas enviadas.

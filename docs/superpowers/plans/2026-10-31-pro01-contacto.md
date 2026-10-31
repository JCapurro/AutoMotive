# PRO-01: Solo particulares y mensaje listo (sin push)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Track the steps below during implementation.

**Goal:** filtro estricto de tipo de vendedor solo para Pro (`filters.seller_types`, `plan_feature('seller_filter')`, `effective_seller`, «sin dato» pasa con menos puntaje) y mensaje listo para mandar al vendedor (plantilla en Ajustes con lint, copiar y `mailto:` en la ficha, bloque en el email de oportunidad Pro). Diseño: [2026-10-31-pro01-contacto-design.md](../specs/2026-10-31-pro01-contacto-design.md). Ítem PRO-01 del [backlog](../../BACKLOG_PRODUCTO_2026-10.md); Fase 2, fila 2, del [plan por fases](../../PLAN_FASES_BACKLOG_PRODUCTO_2026-10.md).

**Architecture:** hard check `seller` en `matching.evaluate()`, activo solo si el dict del perfil trae `seller_filter` (`CASE WHEN sp.filters ? 'seller_types' THEN plan_feature(...)` en `_SELECT` y en la SQL de `low_results`, para no pagar `plan_limits_for` por fila); sin el flag, `seller_types[0]` actúa como preferencia blanda. La web solo deja **poner** el filtro a Pro; quitarlo, en cualquier plan. `search_filters_problem` valida la forma; `preview_search` filtra igual. Mensaje: función pura gemela (Python/TS) con reemplazo literal (nunca `str.format`), lint compartido y JSON dorados compartidos; relint al leer con fallback a la plantilla por defecto; preguntas específicas en `matches.contact_questions`; plantilla en `profiles.contact_template`; bloque de email por `payload.contact_message` con `plan_feature('contact_email')`.

**Tech Stack:** Postgres/Supabase (pgTAP), Python 3.12 (pytest), Next 16 + vitest + Playwright.

**Dependencias:** `main` en `28e439d` (F-02 y PAR-01). Sin bump de `SCORING_VERSION`; si una tarea parece necesitarlo, **parar y avisar** (el único bump, `f2-v5-seller-margin`, ya está desplegado y lo reutiliza PRO-02).

**Estado:** implementado (ver Notas de implementación del diseño); las preguntas del diseño se tomaron con su recomendación, asumido, a confirmar por Juan.

**Tareas de Juan (no las hago):** responder las preguntas del diseño; pasar `seller_unknown_pct` por fuente de `/admin/sources` antes de desplegar el paso 1; OK para cada migración en producción, para reiniciar el worker (`wait_idle`) y para Vercel.

## Comandos

Desde `/home/user/pro01`; nunca contra el piloto ni producción. Supabase local ya corriendo (no `start/stop/db reset`; si se cae, parar y avisar). Un proceso de e2e/base por vez; no dejar servidores corriendo.

- Aplicar migración: `psql postgresql://postgres:postgres@127.0.0.1:54322/postgres -v ON_ERROR_STOP=1 -1 -f <archivo>` + insertar su versión en `supabase_migrations.schema_migrations`
- pgTAP: `npx --yes supabase@2.119.0 test db`
- Base de tests del worker: `cd worker && python -m tools.test_db`
- Worker offline: `cd worker && python -m pytest -q -p no:cacheprovider`
- Worker con base: `cd worker && TEST_DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:54322/automotive_test python -m pytest -q -m db -p no:cacheprovider`
- Web: `cd web && npx vitest run`, `npm run typecheck`, `npx eslint . --ignore-pattern "playwright-report/**" --ignore-pattern "test-results/**"`
- e2e: `cd web && set -a && . ./.env.local && set +a && CI=1 npx playwright test pro01-contact.spec.ts acceptance.spec.ts seller.spec.ts total-cost.spec.ts` (desktop y mobile)

Criterio: «nada nuevo en rojo» respecto de la línea base.

## Task 0: preparación

- [ ] Leer `web/AGENTS.md` y la doc de Next 16 en `web/node_modules/next/dist/docs/`.
- [ ] Confirmar `max(version)` local = `20261127120000` y que Supabase responde en 54321/54322.
- [ ] Correr y anotar la línea base de los cinco comandos.
- [ ] Pedirle a Juan los números de `seller_unknown_pct` por fuente (`/admin/sources`, vista `admin_seller_coverage`; solo lectura, no lo corro yo contra producción) y anotarlos en el diseño (Riesgos, pregunta 4). Bloquea el **despliegue** del paso 1, no la implementación.

## Paso 1: filtro estricto de vendedor (Pro)

### Task 1: pgTAP y migración

- [ ] pgTAP primero (`supabase/tests/pro01_seller_filter_test.sql`): `plan_feature` con `seller_filter` y `contact_email` true para Pro y admin, false para Free/Pass; `search_filters_problem` acepta `["private"]`, `["dealer"]`, ausente y JSON `null`; rechaza `[]`, `["dealer_inferred"]`, `["private","dealer"]`, string, objeto; sigue `immutable` (`pg_proc.provolatile = 'i'`); grant y CHECK de `profiles.contact_template` (acepta null y 500 caracteres; rechaza 501, `''` y `'   '`); `matches.contact_questions` existe.
- [ ] `supabase/migrations/20261128120000_pro01_seller_filter_contact.sql`: claves `pro.seller_filter` y `pro.contact_email` (si faltan), `profiles.contact_template` + CHECK `contact_template is null or (char_length(contact_template) <= 500 and btrim(contact_template) <> '')` + grant de columna, `matches.contact_questions text[]`, `create or replace search_filters_problem` copiando `20261030120000:165-176` + regla nueva (conserva grants). Editar `supabase/seed.sql:45` (las dos claves en `pro`; no tocar la falta previa de `threshold_alerts`/`csv_export`).
- [ ] Aplicar, insertar versión, `tools.test_db`, pgTAP en verde. Regenerar `web/types/database.ts`.

### Task 2: matching (fijar primero, después tests nuevos)

- [ ] **Fijar antes de cambiar:** en `worker/tests/test_intelligence.py`, test que fija score, `level`, componentes y `match_reasons` (valores numéricos literales) de `fiesta_listing`/`fiesta_profile` con `preferences.seller_type` = private y dealer, y sin él, × listing private/dealer/`dealer_inferred`/null. Correr contra el código **sin cambios** y commitear el test aparte (`Pin seller preference scores before PRO-01`). No se edita después.
- [ ] Tests nuevos: hard `seller` × {private, dealer, `dealer_inferred`, null} × {flag on/off}; null → `unknown` y match menor en `unknown_penalty`; con hard activo no hay razón blanda `seller_type`; con flag off y `seller_types: ["private"]` el resultado es idéntico al de `preferences.seller_type = "private"` (contra los valores fijados).
- [ ] `worker/intelligence/matching.py`: `_seller(listing, profile)` con `effective_seller`; entrada `seller` en `evaluate()`; `_preferences` según la decisión 4 del diseño.
- [ ] `worker/intelligence/copy.py`: `FILTER_NAMES["seller"] = "vendedor"` y textos `REASON` del hard (ok/otro; «posible agencia» vía `seller_kind`).
- [ ] Si algún test fijado cambia, **parar y avisar** (sería un cambio de score que pide bump).

### Task 3: perfiles en el worker

- [ ] Tests `-m db` (`worker/tests/test_pro01_postgres.py`):
  - `_SELECT` trae `seller_filter` por plan, y false sin la clave aunque sea Pro;
  - un Particular con `seller_types` escrito por SQL sigue recibiendo agencias en crawl, rematch y rescore, con la razón blanda `seller_type`;
  - `low_results.candidates` + `_profile` llevan el flag hasta `evaluate()`;
  - no re-notificar: Pro con «solo particulares» → crawl notifica un aviso particular → `dealer_inferred = true` y rescore borra el match → `dealer_inferred = false` (y, en otra variante, `pro.seller_filter = false`) → crawl recrea el match → una sola fila en `notifications` para `match:<listing_id>`.
- [ ] Tests offline `intelligence/low_results`: `FILTERS`/`LABEL` con `seller`; `main_blocker == "seller"` cuando solo el vendedor descarta; `fingerprint` de un perfil sin `seller_types` igual a un valor literal fijado **antes** del cambio, y distinto con el flag on/off cuando tiene la clave.
- [ ] `worker/db/repos/profiles.py` (`_SELECT` con el `CASE`, `_to_alert`), `worker/db/repos/low_results.py` (mismo `CASE`), `worker/pipeline/low_results.py` (`_profile` copia `seller_filter`), `worker/intelligence/low_results.py` (`FILTERS`, `LABEL`, `fingerprint`), `worker/tools/explain_match.py`. `update_alert` no se toca (sin llamadores de producción; ver diseño, decisión 10).
- [ ] **Medición del camino caliente:** en `automotive_test`, 2.000 búsquedas (200 Pro estrictas) y `EXPLAIN (ANALYZE, BUFFERS)` + tiempo de `alerts_for_target`, `pending_rematch` y `profiles_by_ids` antes y después del cambio; anotar en las notas del diseño. Si empeora más de un 20 %, pasar al CTE `MATERIALIZED` por usuario (plan B del diseño) y volver a medir.

### Task 4: `preview_search`

- [ ] pgTAP: con feature, `["private"]` excluye `dealer` y `dealer_inferred` y deja el null; sin feature, ignora la clave.
- [ ] `supabase/migrations/20261128120100_pro01_preview_seller.sql` desde `20261115120000_multi_location.sql:25-121`, sola; `plan_feature(auth.uid(), ...)` una vez por consulta (CTE), no por fila. Aplicar y correr pgTAP.

### Task 5: web

- [ ] Tests vitest:
  - `search-form`: `toFilters` escribe `seller_types` y omite `preferences.seller_type` con el check; `fromProfile` lee `prefs.seller_type ?? f.seller_types?.[0]`; downgrade: el select muestra el valor guardado y «Quitar filtro estricto» lo vacía;
  - `search-relax.test.ts`: con `seller_strict` aparece `{ key: "seller", label: "Cualquier vendedor", change: { seller_strict: false } }`; sin él, no;
  - `draftToValues` con `sellerFilter`; «no-Pro nunca ve el checkbox» (patrón `search-form-layout.test.ts`); resumen de la búsqueda (Pro y downgrade);
  - `lib/search-actions.test.ts`: no-Pro con `seller_types` nuevo → no se guarda (queda lo guardado); no-Pro con `seller_types: []` → se quita; Pro con `["dealer_inferred"]`, dos valores o un string → error, nada escrito; `seller_filter_set` solo cuando cambia.
- [ ] `web/lib/types.ts` (`Filters.seller_types`), `web/lib/search-form.ts` (schema, `toFilters`, `toPreferences`, `fromProfile`, `seller_strict` en `SearchValues`), `web/lib/search-relax.ts` (`RelaxKey`, `RelaxChange`, variante), `web/app/app/searches/form-data.ts` (`sellerFilter`), `new/page.tsx`, `[id]/edit/page.tsx`, `components/app/assisted-search.tsx`, `lib/assisted.ts`.
- [ ] `components/app/search-form.tsx`: `Draft`/`draftFrom`/`toInput` con `seller_strict`; checkbox «Solo este tipo de vendedor» bajo el select para Pro; pista sin repetir «Incluye posibles agencias.»; aviso «solo Pro» con «Quitar filtro estricto» en downgrade.
- [ ] `app/app/searches/actions.ts`: `my_plan_feature('seller_filter')` en el `Promise.all`; reglas de la decisión 8 (poner solo Pro, quitar siempre); `seller_filter_set` en alta y edición.
- [ ] `components/app/search-criteria-summary.tsx`, `lib/copy.ts` (`REASON_OK`/`REASON_NAME`/`REASON_ORDER` con `seller`, textos nuevos).
- [ ] Clave `seller_filter` (y `contact_email`) en `lib/pro.ts`, `lib/admin-config.ts`, `app/admin/config/page.tsx`, `components/admin/config-forms.tsx`.
- [ ] `npx vitest run`, typecheck, eslint.

### Task 6: cierre del paso 1

- [ ] e2e en `pro01-contact.spec.ts`: Pro crea «solo particulares», ve la explicación, edita y el resumen cambia; no-Pro con `seller_types` sembrado por SQL ve el aviso «solo Pro», lo quita y el resumen pasa a «Vendedor: …» sin «solo Pro».
- [ ] Los cinco comandos en verde (e2e: `seller.spec.ts` intacto).
- [ ] Commit por paths: `Add Pro-only strict seller filter`.

## Paso 2: mensaje listo para mandar

### Task 7: funciones gemelas, lint y preguntas

- [ ] `worker/tests/fixtures/contact_message/golden.json`: por defecto con 0, 1 y 3 específicas; sin `catalog_model` («auto»); `catalog_model` que no cumple el patrón («auto»); un `title` con URL y `{preguntas}` en la entrada que **no** aparece en la salida; plantilla propia con y sin marcadores; plantilla null; plantillas hostiles (`{`, `}{`, `{x}`, `{auto.__class__}`, `{0}`, `{{auto}}`, `%s`) → plantilla por defecto.
- [ ] `worker/tests/fixtures/contact_message/lint.json`: la lista de términos (cada lado testea que coincide con su `FORBIDDEN_TERMS`) y casos con su error esperado: null/`""`/`"  \n "` → null; 501 caracteres; 7 líneas; marcador desconocido y llave suelta; «vale», «Valor real», «tasación», «TASACION» (y «vale la pena» permitido); `https://x.com`, `www.x`, `wa.me/54911…`, `autos.com.ar`, `yo@mail.com`, `@usuario`; `11 5555-5555`, `+54 9 11 5555 5555`, `11.5555.5555`, `1155555555`; y negativos que pasan («¿Tiene los services al día?», «Lo veo el 15 o el 16»).
- [ ] `worker/intelligence/contact_message.py`: `lint_contact_template`, `render` con reemplazo literal en una pasada (`re.sub(r"\{(auto|preguntas)\}", fn, tpl)`), relint + `try`/fallback a la plantilla por defecto (`log.warning`), `{auto}` solo desde `catalog_model` + año. Textos en `copy.py` (lint automático). Tests contra los dos JSON. `seller_questions()` y `question_texts()` sin cambios.
- [ ] `engine.py`/`matches.py`: `contact_questions` (`question_texts(limit=3)`) en `Evaluation.row()` y `upsert_scored`; test `-m db` de la columna.
- [ ] `web/lib/contact-message.ts` (+ `lintContactTemplate` en `web/lib/copy.ts`) y `contact-message.test.ts` contra los mismos JSON; `mailtoHref(subject, body)` con `encodeURIComponent` por campo y `\r\n`, test del href exacto con una plantilla multilínea que tiene `&`, `?`, `#` y `%` (espera `%26`, `%3F`, `%23`, `%25`, `%20` y `%0D%0A`, nunca `+`).

### Task 8: Ajustes

- [ ] Tests: `copy.test.ts` pasa a usar el helper para sus chequeos de términos (mismo resultado que hoy); acción `saveContactTemplate` devuelve `{error}` con el mensaje de cada regla y guarda null para vacío.
- [ ] `web/lib/copy.ts` (plantilla por defecto + textos), `app/app/settings/page.tsx` (select + card), `app/app/settings/actions.ts` (`saveContactTemplate`: zod, lint, `{error}`; sin evento propio), `components/app/settings-forms.tsx` (`ContactTemplateForm` con vista previa y «Volver al mensaje sugerido»).

### Task 9: ficha

- [ ] `app/app/listings/[id]/page.tsx`: select de `contact_questions`, `profiles.contact_template` y `vehicle_catalog.model` (`catalog_model`, mismo join que `rows_for_scoring`); armar el mensaje con relint + fallback (una plantilla escrita por API nunca llega a la pantalla).
- [ ] `components/app/seller-questions.tsx`: bloque «Mensaje listo para mandar», «Copiar», «Abrir en tu correo» (`mailtoHref`, sin destinatario), link a la publicación con `outboundHref`; la lista completa sigue igual.
- [ ] `app/app/listings/actions.ts`: `trackContactMessage(listingId, via, custom)` con zod → `contact_message_copied`.

### Task 10: email Pro

- [ ] Tests primero: `PayloadTests` (Pro con oportunidad → `contact_message`; Pro con `new_match`, Particular y Free → sin clave; Pro con `contact_template` inválida escrita por SQL → texto por defecto, sin excepción, el resto del lote se envía), fixture `opportunity_contact_message` con snapshot nuevo, Telegram e inbox sin cambios, los 11 snapshots existentes byte-idénticos, lint.
- [ ] `worker/db/repos/notifications.py` (`contact_email`, `p.contact_template`, `catalog_model`), `notifications/service.py`, `templates.py` (`Content.contact_message`, texto), `email_html.py` (bloque escapado, sin `QUESTIONS_FOOTER` cuando hay bloque), `copy.py` (título y nota).

### Task 11: métricas

- [ ] pgTAP en `admin_decision_metrics_test.sql`: `contact_message_copied` cuenta como actividad; `seller_filter_set` solo no suma un usuario activo nuevo (siempre llega con `search_profile_*`).
- [ ] `supabase/migrations/20261128120200_pro01_decision_metrics.sql` desde `20261122120100`, sola. Aplicar, correr pgTAP y regenerar `web/types/database.ts` si cambia.

### Task 12: e2e y cierre

- [ ] `web/e2e/pro01-contact.spec.ts` (helper de plan como `seedTotalCost` en `e2e/support/db.ts`) suma: Ajustes guarda una plantilla y rechaza otra con término prohibido y otra con teléfono; la ficha copia el mensaje y el `mailto:` no tiene destinatario y usa `%0D%0A`; sin scroll horizontal en 375 px.
- [ ] Los cinco comandos en verde, e2e con `acceptance`, `seller` y `total-cost`.
- [ ] Commit por paths: `Add ready-to-send seller message and template`.
- [ ] Notas de implementación al final del diseño: medición del camino caliente, `seller_unknown_pct`, y lo que haya cambiado.

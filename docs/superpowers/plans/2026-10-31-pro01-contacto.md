# PRO-01: Solo particulares y mensaje listo (sin push)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Track the steps below during implementation.

**Goal:** filtro estricto de tipo de vendedor solo para Pro (`filters.seller_types`, `plan_feature('seller_filter')`, `effective_seller`, «sin dato» pasa con menos puntaje) y mensaje listo para mandar al vendedor (plantilla en Ajustes con lint, copiar y `mailto:` en la ficha, bloque en el email de oportunidad Pro). Diseño: [2026-10-31-pro01-contacto-design.md](../specs/2026-10-31-pro01-contacto-design.md). Ítem PRO-01 del [backlog](../../BACKLOG_PRODUCTO_2026-10.md); Fase 2, fila 2, del [plan por fases](../../PLAN_FASES_BACKLOG_PRODUCTO_2026-10.md).

**Architecture:** hard check `seller` en `matching.evaluate()`, activo solo si el dict del perfil trae `seller_filter` (columna `plan_feature` en `_SELECT` y en la SQL de `low_results`); la web descarta el valor para no-Pro y conserva el guardado. `search_filters_problem` valida la forma; `preview_search` filtra igual. Mensaje: función pura gemela (Python/TS) con JSON dorado compartido; preguntas específicas en `matches.contact_questions`; plantilla en `profiles.contact_template`; bloque de email por `payload.contact_message` con `plan_feature('contact_email')`.

**Tech Stack:** Postgres/Supabase (pgTAP), Python 3.12 (pytest), Next 16 + vitest + Playwright.

**Dependencias:** `main` en `28e439d` (F-02 y PAR-01). Sin bump de `SCORING_VERSION`; si una tarea parece necesitarlo, **parar y avisar** (el único bump, `f2-v5-seller-margin`, ya está desplegado y lo reutiliza PRO-02).

**Tareas de Juan (no las hago):** responder las preguntas del diseño; OK para cada migración en producción, para reiniciar el worker (`wait_idle`) y para Vercel.

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

## Paso 1: filtro estricto de vendedor (Pro)

### Task 1: pgTAP y migración

- [ ] pgTAP primero (`supabase/tests/pro01_seller_filter_test.sql`): `plan_feature` con `seller_filter` y `contact_email` true para Pro y admin, false para Free/Pass; `search_filters_problem` acepta `["private"]`, `["dealer"]`, ausente; rechaza `[]`, `["dealer_inferred"]`, `["private","dealer"]`, no-array; grant y CHECK de `profiles.contact_template`; `matches.contact_questions` existe.
- [ ] `supabase/migrations/20261128120000_pro01_seller_filter_contact.sql`: claves `pro.seller_filter` y `pro.contact_email` (si faltan), `profiles.contact_template` + CHECK `<= 500` + grant de columna, `matches.contact_questions text[]`, `create or replace search_filters_problem` copiando `20261030120000:165-176` + regla nueva. Editar `supabase/seed.sql:45` (las dos claves en `pro`).
- [ ] Aplicar, insertar versión, `tools.test_db`, pgTAP en verde.

### Task 2: matching (tests primero)

- [ ] `worker/tests/test_intelligence.py`: hard `seller` × {private, dealer, `dealer_inferred`, null} × {flag on/off}; null → `unknown` y score menor en `unknown_penalty`; con hard activo no hay razón blanda `seller_type`; perfil sin `seller_types` puntúa igual que antes (mismo `Evaluation`).
- [ ] `worker/intelligence/matching.py`: `_seller(listing, profile)` con `effective_seller`; entrada `seller` en `evaluate()`; `_preferences` salta `seller_type` si el hard aplica.
- [ ] `worker/intelligence/copy.py`: `FILTER_NAMES["seller"] = "vendedor"` y textos `REASON` del hard (ok/otro; «posible agencia» vía `seller_kind`).

### Task 3: perfiles en el worker

- [ ] Tests `-m db` (`worker/tests/test_pro01_postgres.py`): `_SELECT` trae `seller_filter` por plan; un Particular con `seller_types` escrito por SQL sigue recibiendo agencias en crawl, rematch y rescore; `low_results` respeta el flag; `update_alert` (Telegram) conserva `filters.seller_types`.
- [ ] `worker/db/repos/profiles.py` (`_SELECT`, `_to_alert`, `update_alert`), `worker/db/repos/low_results.py`, `worker/tools/explain_match.py`.

### Task 4: `preview_search`

- [ ] pgTAP: con feature, `["private"]` excluye `dealer` y `dealer_inferred` y deja el null; sin feature, ignora la clave.
- [ ] `supabase/migrations/20261128120100_pro01_preview_seller.sql` desde `20261115120000_multi_location.sql:25-121`, sola. Aplicar y correr pgTAP.

### Task 5: web

- [ ] Tests vitest: `search-form` (`toFilters` escribe `seller_types` y omite `preferences.seller_type` con el check; `fromProfile` lo lee; con `sellerFilter=false` el valor guardado se conserva), `draftToValues` con `sellerFilter`, «no-Pro nunca ve el checkbox» (patrón `search-form-layout.test.ts`), resumen de la búsqueda.
- [ ] `web/lib/types.ts` (`Filters.seller_types`), `web/lib/search-form.ts` (schema, `toFilters`, `toPreferences`, `fromProfile`), `web/app/app/searches/form-data.ts` (`sellerFilter`), `new/page.tsx`, `[id]/edit/page.tsx`, `components/app/assisted-search.tsx`, `lib/assisted.ts`.
- [ ] `components/app/search-form.tsx`: `Draft`/`draftFrom`/`toInput` con `seller_strict`; checkbox «Solo este tipo de vendedor» bajo el select para Pro, pistas del diseño (decisión 6); aviso «solo Pro» en downgrade.
- [ ] `app/app/searches/actions.ts`: `my_plan_feature('seller_filter')` en el `Promise.all`; descartar/conservar; `seller_filter_set` en alta y edición.
- [ ] `components/app/search-criteria-summary.tsx`, `lib/copy.ts` (`REASON_OK`/`REASON_NAME`/`REASON_ORDER` con `seller`, textos nuevos).
- [ ] Clave `seller_filter` (y `contact_email`) en `lib/pro.ts`, `lib/admin-config.ts`, `app/admin/config/page.tsx`, `components/admin/config-forms.tsx`.
- [ ] `npx vitest run`, typecheck, eslint.

### Task 6: cierre del paso 1

- [ ] Los cinco comandos en verde (e2e: `seller.spec.ts` intacto).
- [ ] Commit por paths: `Add Pro-only strict seller filter`.

## Paso 2: mensaje listo para mandar

### Task 7: función gemela y preguntas

- [ ] `worker/tests/fixtures/contact_message_cases.json`: por defecto con 0, 1 y 3 específicas; sin modelo («auto»); plantilla propia con y sin marcadores; plantilla null.
- [ ] `worker/intelligence/contact_message.py` (+ textos en `copy.py`, lint automático) y test contra el JSON; `seller_questions()` y `question_texts()` sin cambios.
- [ ] `engine.py`/`matches.py`: `contact_questions` (`question_texts(limit=3)`) en `Evaluation.row()` y `upsert_scored`; test `-m db` de la columna.
- [ ] `web/lib/contact-message.ts` y `contact-message.test.ts` contra el mismo JSON.

### Task 8: Ajustes

- [ ] Tests: `lintContactTemplate` (largo, líneas, marcadores desconocidos, término prohibido, URL, número de 7+ dígitos, vacío → null); `copy.test.ts` pasa a usar el helper.
- [ ] `web/lib/copy.ts` (helper + plantilla por defecto + textos), `web/types/database.ts`, `app/app/settings/page.tsx` (select + card), `app/app/settings/actions.ts` (`saveContactTemplate`: zod, lint, `{error}`, `contact_template_saved`), `components/app/settings-forms.tsx` (`ContactTemplateForm` con vista previa y «Volver al mensaje sugerido»).

### Task 9: ficha

- [ ] `app/app/listings/[id]/page.tsx`: select de `contact_questions` y `profiles.contact_template`; armar el mensaje con `vehicle` corto.
- [ ] `components/app/seller-questions.tsx`: bloque «Mensaje listo para mandar», «Copiar», «Abrir en tu correo» (`mailto:?subject=&body=` sin destinatario), link a la publicación con `outboundHref`; la lista completa sigue igual.
- [ ] `app/app/listings/actions.ts`: `trackContactMessage(listingId, via, custom)` con zod → `contact_message_copied`.

### Task 10: email Pro

- [ ] Tests primero: `PayloadTests` (Pro con oportunidad → `contact_message`; Pro con `new_match`, Particular y Free → sin clave), fixture `opportunity_contact_message` con snapshot nuevo, Telegram e inbox sin cambios, los 11 snapshots existentes byte-idénticos, lint.
- [ ] `worker/db/repos/notifications.py` (`contact_email`, `p.contact_template`), `notifications/service.py`, `templates.py` (`Content.contact_message`, texto), `email_html.py` (bloque escapado, sin `QUESTIONS_FOOTER` cuando hay bloque), `copy.py` (título y nota).

### Task 11: métricas

- [ ] pgTAP en `admin_decision_metrics_test.sql`: los dos eventos cuentan como actividad.
- [ ] `supabase/migrations/20261128120200_pro01_decision_metrics.sql` desde `20261122120100`, sola. Aplicar y correr pgTAP.

### Task 12: e2e y cierre

- [ ] `web/e2e/pro01-contact.spec.ts` (helper de plan como `seedTotalCost` en `e2e/support/db.ts`): Pro crea «solo particulares», ve la explicación, edita y el resumen cambia; Ajustes guarda una plantilla y rechaza otra con término prohibido; la ficha copia el mensaje y el `mailto:` no tiene destinatario; sin scroll horizontal en 375 px.
- [ ] Los cinco comandos en verde, e2e con `acceptance`, `seller` y `total-cost`.
- [ ] Commit por paths: `Add ready-to-send seller message and template`.
- [ ] Notas de implementación al final del diseño si algo cambió.

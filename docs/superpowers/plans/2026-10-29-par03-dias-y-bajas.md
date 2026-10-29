# PAR-03 (por aviso): días publicado y bajas de precio

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Track the steps below during implementation.

**Goal:** Que la tarjeta, la ficha, el email de oportunidad y el digest digan cuántas veces bajó un aviso y cuánto acumula desde que lo vimos, y que el digest muestre la edad del aviso (publicado vs. detectado). Diseño aprobado: [2026-10-29-par03-dias-y-bajas-design.md](../specs/2026-10-29-par03-dias-y-bajas-design.md). Ítem PAR-03 del [backlog de producto](../../BACKLOG_PRODUCTO_2026-10.md). Fuera de alcance (espera a F-03): bloque «comportamiento del modelo», tendencia semanal, `model_stats_viewed`, `plan_feature('model_stats')`. No se calcula ni se dice nada parecido a un «precio de cierre».

**Architecture:** una función SQL `public.listing_price_tracks(bigint[])` (`stable`, `security invoker`, `set search_path = ''`) es la única definición de «baja»: la llama la web por RPC con los ids de la página y el worker desde `db/repos/notifications.py`. **No se tocan `match_cards`, `search_results` ni `comparables`.** El email de oportunidad guarda `price_track` (opcional) en el payload; el digest lo recalcula al armarse (`run_digest`). La web suma una prop opcional `track` a `ListingCard`, un resumen y un `<details>` en la ficha, y el evento `price_history_expanded` por server action. Sin tablas nuevas, sin RLS nueva, sin cambio de `SCORING_VERSION`.

**Tech Stack:** Postgres/Supabase (pgTAP), Python 3.12 (pytest, `pythonpath = worker`), Next 16 + vitest (solo `lib/**/*.test.ts`) + Playwright.

## Alcance y decisiones aprobadas

Juan aprobó todas las propuestas de «Decisiones que necesita de Juan» del diseño, tal cual:

1. Copy de la decisión 5 del diseño tal cual (se transcribe abajo).
2. `app_config.price_track.min_drop_pct = 1` para contar una baja (distinto de `price_drop_min_pct = 3`, que decide si se alerta).
3. Avisos en pesos: «-$ X, unos USD Y».
4. Solo se muestran bajas con neto de baja (`cum_pct > 0`); neto suba o sin cambio, tarjeta y email no dicen nada de bajas (la ficha conserva su «Subió X»).
5. Edad en el digest sí; en `new_match` no.
6. La ficha pasa el histórico a `<details>` cerrado (permite medir `price_history_expanded`).
7. Sin bloque del modelo ni tendencia hasta tener 4 semanas de `market_stats` (F-03).

Copy aprobado (singular y plural correctos; nunca «precio de cierre», «vale», «ofertá X»; ojo: `vale` es subcadena y también falla «equivale», «equivalente», «valer»):

- USD: `Bajó {n} vez desde que la vimos: -USD {monto} (-{p}%).` / `Bajó {n} veces desde que la vimos: -USD {monto} (-{p}%).`
- Pesos: `Bajó {n} veces desde que la vimos: -$ {monto_ars} (-{p}%), unos USD {monto_usd}.` (con n = 1, «Bajó 1 vez»).
- Edad, sin cambios: `Publicado hace {N} días.` / `Detectado hace {N} días.`
- Ficha, «Detectado»: `No sabemos cuándo se publicó; contamos desde que la detectamos.`
- Ficha, publicado antes de que lo viéramos: `Seguimos este aviso desde el {dd/mm}; no vemos los cambios anteriores.`
- Resumen de ficha: `{n} baja(s) · -USD {monto} (-{p}%) desde el {dd/mm}`.

Reglas de cálculo (diseño, decisión 2): se recorren los snapshots con precio, se colapsan repetidos (mismo criterio que `priceHistory()` de la ficha); por par consecutivo, misma moneda → baja si cae el precio propio, moneda distinta → baja si cae `price_usd`; cuenta solo si la caída es `>= price_track.min_drop_pct`. `cum_pct` = primer vs último precio en la moneda propia (USD si hubo cambio de moneda). `cum_usd`: USD directo; ARS = diferencia en pesos / `fx_rate` del último snapshot (`fx_rate` = ARS por USD, ver `insert_snapshot`, `worker/db/repos/listings.py:84`); monedas mezcladas = diferencia de `price_usd`.

**Tareas de Juan (no las hago ni invento su contenido):**

- OK explícito para aplicar la migración en producción (transacción + inserción de la versión exacta; releer `max(version)` antes). Hasta entonces solo base local/`_test`.
- OK para reiniciar el worker (con `wait_idle` antes) y para el deploy de la web en Vercel.
- Este plan no toca textos legales, links oficiales ni Privacidad/Términos: no hay cambios ahí. Si Juan quiere mencionar el seguimiento de precios en Privacidad/Términos, es un pedido aparte y el texto lo provee él.
- Revisar con avisos reales de contado (precio efectivo vs. publicado) que «-USD X» sea coherente antes de publicar (riesgo de contenido del diseño).

**Rama:** `claude/par03-dias-y-bajas`, partiendo de `main` con H-01 (PR #50, rama `claude/email-seller-questions`, hoy sin mergear) y X-01 ya mergeados. No empezar sin ambos en `main`.

**Orden de edición con el resto** (comparten `worker/notifications/email_html.py`, `worker/notifications/templates.py`, `worker/tests/snapshots/notifications/` y, en SQL, `match_cards`/`search_results`): **H-01 → X-01 → PAR-03 → PAR-02 tramo 1**; F-03 es independiente.

- H-01 primero: rebasar sobre H-01 mergeado y regenerar `opportunity.txt` desde su última versión (no resolver conflictos de snapshot a mano).
- X-01 antes: redefine `match_cards`/`search_results` y toca `listing-card.tsx`; PAR-03 parte de lo que deje X-01 en la tarjeta (pie/`footer`, píldoras de seguimiento) y **no redefine esas vistas**, así que no choca en SQL.
- PAR-02 tramo 1 después: rebasa sobre esto (mismos archivos de email y snapshots).

**Comandos de prueba** (desde la raíz salvo indicación):

- Python offline: `python -m pytest worker/tests/test_notifications_templates.py worker/tests/test_notifications_engine.py worker/tests/test_notifications_email_media.py worker/tests/test_intelligence_copy.py -q`
- Python con Postgres: `cd worker; python -m tools.test_db; cd ..` y luego `$env:TEST_DATABASE_URL = "postgresql://postgres:postgres@127.0.0.1:54322/automotive_test"; python -m pytest -m db -q` (solo base `*_test`; vacían tablas).
- pgTAP (README, sección Tests): `npx supabase test db`.
- Web (en `web/`): `npm test` (vitest, solo `lib/**/*.test.ts`), `npm run e2e` (Playwright desktop + 375 px), `npm run gen:types`, `npm run lint`.
- Después de cambiar código: `graphify update .`.

## Task 0: preparación y lectura obligatoria

- [ ] Confirmar que H-01 y X-01 están en `main` (`git log main --oneline | head`); crear `claude/par03-dias-y-bajas` desde `main`. Si falta alguno, parar y avisar a Juan.
- [ ] Leer `web/CLAUDE.md` → `AGENTS.md` y `node_modules/next/dist/docs/` (Next 16) antes de escribir código en `web/` (tareas 7 a 10).
- [ ] Releer la definición vigente de `ListingCard`/`LISTING_ROWS` (`web/components/app/listing-card.tsx`) tal como la dejó X-01, y `email_html.py`/`templates.py` tal como los dejó H-01 (aparece el bloque `questions`).
- [ ] Releer `max(version)` de producción (solo lectura, `supabase_migrations.schema_migrations`; última conocida `20261118130000`) y la migración de X-01 (provisoria `20261119120000_x01_tracking.sql`). Elegir el nombre de la migración de PAR-03 por encima de ambas: provisorio `supabase/migrations/20261121120000_par03_price_tracks.sql`.

## Task 1: EXPLAIN en base `_test` (antes de aprobar el diseño técnico)

Files: ninguno commiteado (script de siembra y salida van al scratchpad).

- [ ] `npx supabase start` si no está arriba y `cd worker; python -m tools.test_db; cd ..`. Conectar solo a `automotive_test` (puerto 54322); nunca a la base del piloto ni a producción.
- [ ] Sembrar volumen realista en `automotive_test`: 50.000 `listings` y ~200.000 `listing_snapshots` (un `new` más 0 a 6 cambios por aviso; mezcla de USD y ARS, algunos con cambio de moneda, `fx_rate` en los ARS), con la misma distribución de `observed_at` que producción (aprox.). Hacerlo con SQL `generate_series` en un archivo del scratchpad.
- [ ] Escribir la consulta candidata (el cuerpo de la futura función, con `min_drop_pct = 1` literal) y correr `EXPLAIN (ANALYZE, BUFFERS)` con 50 ids de una página y con 200 ids (tanda del worker). Esperado: range scan por `(listing_id, observed_at desc)` por aviso, sin seq scan de `listing_snapshots`.
- [ ] Criterio de paso: 50 ids en un orden de decenas de ms. Si hay seq scan o el tiempo es alto, ajustar la consulta (por ejemplo `unnest` + `lateral`) antes de la Task 2. Si no se logra sin tocar índices, **parar y consultar a Juan** (un índice nuevo es una decisión aparte). Pegar el plan y los tiempos en la descripción del PR.

## Task 2: pgTAP primero y migración

Files: `supabase/tests/price_tracks_test.sql` (nuevo), `supabase/migrations/20261121120000_par03_price_tracks.sql` (nuevo; nombre final según Task 0).

- [ ] Escribir `supabase/tests/price_tracks_test.sql` (formato de `supabase/tests/email_only_test.sql`: `begin; create extension if not exists pgtap with schema extensions; select plan(N); ... rollback;`) y verlo fallar. Casos del diseño: 0 bajas; 1 baja; 3 bajas; baja y suba posterior (neto suba → `cum_pct <= 0`, sin baja neta); precio repetido colapsa; ARS con el dólar moviéndose y precio propio estable (0 bajas); cambio de moneda ARS→USD (mide en `price_usd`); caída menor a `min_drop_pct` no cuenta (y cambia al editar `app_config.price_track`); aviso sin snapshots; aviso con un solo punto; array vacío; `cum_usd` de un aviso en ARS usa el `fx_rate` del último snapshot; un usuario `authenticated` recibe solo lo que ya lee (misma visibilidad que `listing_snapshots`) y `anon` no puede ejecutar la función.
- [ ] Migración con encabezado `--` que cite `docs/superpowers/specs/2026-10-29-par03-dias-y-bajas-design.md` y PAR-03: `insert into public.app_config (key, value) values ('price_track', '{"min_drop_pct": 1}') on conflict do nothing`; `create or replace function public.listing_price_tracks(p_listing_ids bigint[])` con las columnas `listing_id, drops, rises, first_at, first_price, first_currency, last_price, last_currency, cum_pct, cum_usd, last_drop_at`, `language sql stable security invoker set search_path = ''` (calificar todo con `public.`), `revoke all ... from public, anon`, `grant execute ... to authenticated, service_role`. Cuerpo según la Task 1. Sin tablas, sin RLS, sin columnas en `listings`. No editar migraciones viejas.
- [ ] Aplicar **solo en local**: `npx supabase migration up --local` (o `npx supabase db reset` si el stack local es descartable; no verifiqué cuál prefiere el repo), después `cd worker; python -m tools.test_db; cd ..`. **No aplicar en producción**: es paso de Juan.
- [ ] `npx supabase test db` verde (incluidos los tests existentes `f4_web_test.sql` y `free_result_quota_test.sql`, que no deberían verse afectados). `cd web; npm run gen:types` y revisar que el diff de `web/types/database.ts` solo agrega la función.

## Task 3: copy y helper de formato del worker

Files: `worker/intelligence/copy.py`, `worker/tests/test_intelligence_copy.py`, `worker/tests/test_notifications_templates.py`.

- [ ] Tests que fallen: función pura `price_track_line(track)` (ubicar junto a `age_line` en `worker/notifications/templates.py`) devuelve las frases aprobadas: 1 baja en USD («Bajó 1 vez…»), 3 bajas en USD, caso ARS con «unos USD», `None` si `track` es `None`, `drops == 0` o `cum_pct <= 0`; montos con `copy.money`/`copy.number` y porcentaje con `pct()` (coma decimal).
- [ ] Agregar las plantillas a `worker/intelligence/copy.py` (constantes, no literales en `templates.py`); `test_intelligence_copy.py` las cubre con `FORBIDDEN_TERMS` normalizando con `normalize_text`, igual que H-01. Agregar también un test que confirme que ningún texto nuevo contiene «precio de cierre», «ofertá», «equivale» ni «tasación».
- [ ] Implementar `price_track_line()` y correr los tests offline.

## Task 4: datos del worker (consulta y payload de oportunidad)

Files: `worker/db/repos/notifications.py` (nueva `price_tracks(listing_ids)`), `worker/notifications/service.py` (`on_matches`, `payload()`), `worker/tests/test_notifications_engine.py`, `worker/tests/test_notifications_postgres.py`.

- [ ] Tests que fallen (engine, con el repo parcheado): `on_matches` con un candidato de nivel oportunidad y una baja neta guarda `payload["price_track"] == {drops, cum_pct, cum_usd, currency, first_at}`; sin baja neta o `drops == 0` la clave no está; `new_match` no la lleva; una sola consulta por tanda (`price_tracks` se llama una vez con todos los `listing_id`). Test `db` en `test_notifications_postgres.py` (usa `PostgresTestCase`, base `*_test` con la migración aplicada): inserta snapshots reales y verifica que `repo.price_tracks([...])` devuelve lo que calcula la función.
- [ ] `price_tracks(ids)` en el repo: `SELECT * FROM public.listing_price_tracks(%s::bigint[])` con `connection()`, devuelve `dict[int, dict]`; `[]` → `{}` sin consultar.
- [ ] En `on_matches`, tras `states = await repo.interactions(pairs)`, `tracks = await repo.price_tracks(ids)`; pasar `price_track=` (solo si hay baja neta) a `payload()` como extra opcional (los `None` ya se descartan). No tocar `on_listing_events`.

## Task 5: render del email de oportunidad

Files: `worker/notifications/templates.py` (`content()`, línea ~206), `worker/notifications/email_html.py` (solo si hace falta), `worker/tests/test_notifications_templates.py`, `worker/tests/test_notifications_email_media.py`.

- [ ] Tests que fallen: con `price_track` en el payload, `content()` de `opportunity` agrega la línea **después de** `age_line` (mismo mecanismo `Content.lines`, así sale en email de texto, HTML, Telegram e inbox); sin la clave (payload viejo) el render es idéntico al actual, byte a byte; `new_match` y `price_drop` no cambian; el HTML pasa `FORBIDDEN_TERMS`.
- [ ] Implementar en `content()`: `if line := price_track_line(p.get("price_track")): c.lines.append(line)` tras `age_line`. Si Telegram no debe llevar la línea, no hace falta nada: el diseño dice que Telegram no cambia para `new_match`/`price_drop`; para `opportunity` comparte `Content.lines` (decisión: lo lleva, es la misma lista).
- [ ] Rebasar sobre H-01 antes de este paso (el bloque `questions` queda después de las líneas; verificar el orden en el snapshot).

## Task 6: digest con edad y baja recalculada

Files: `worker/notifications/digest.py` (`run_digest`, `build_items`), `worker/notifications/templates.py` (`_digest`, `item()`), `worker/tests/test_notifications_engine.py` o un archivo de digest existente, `worker/tests/test_notifications_templates.py`.

- [ ] Tests que fallen: (a) en la sección de coincidencias cada aviso suma a `DigestItem.details` la línea de edad (`age_line`) con «Publicado» si hay `published_at` y «Detectado» si no; (b) `run_digest` recalcula con `repo.price_tracks` **una vez** para todos los ids de la tanda y el item lleva `price_track` nuevo aunque el payload viejo guardado tenga otro valor; (c) secciones `price_drops` y `gone` sin cambios; (d) item sin baja neta no suma la línea.
- [ ] En `run_digest`, tras `items = build_items(pending, top, top_n)`: un llamado `price_tracks` con los `listing_id` de la sección `matches` y asignar `item["price_track"]`. En `_digest.item()`, para `section == "matches"` agregar `age_line` y `price_track_line` a `details`. Las líneas llevan punto final; verificar que el `details` del digest actual (km, ubicación) no duplique puntuación en el HTML (`_digest_card` en `email_html.py`).
- [ ] `new_match` no recibe edad (decisión 5).

## Task 7: fixtures y snapshots de notificaciones

Files: `worker/tests/notification_fixtures.py`, `worker/tests/snapshots/notifications/opportunity.txt`, `digest.txt` (más archivos nuevos si se agregan casos a `CASES`).

- [ ] Agregar casos: `OPPORTUNITY` con 1 baja (USD), `OPPORTUNITY_3_DROPS`, `OPPORTUNITY_ARS` y el actual sin la clave (payload viejo). Digest con 0, 1 y 3 bajas y con «Publicado»/«Detectado».
- [ ] Regenerar con `UPDATE_SNAPSHOTS=1 python -m pytest worker/tests/test_notifications_templates.py -q` **partiendo de la última versión de `opportunity.txt` de `main` (con H-01)**, revisar el diff (solo líneas nuevas; `new_match`, `price_drop`, `telegram buttons` y `email subject` sin cambios) y correr sin `UPDATE_SNAPSHOTS` para confirmar verde.

## Task 8: lib de la web (formato, copy y tests primero)

Files: `web/lib/price-track.ts` (nuevo), `web/lib/price-track.test.ts` (nuevo), `web/lib/copy.ts`, `web/lib/copy.test.ts`, `web/lib/format.ts` (solo si falta un helper), `web/app/admin/config/page.tsx`.

- [ ] Recordatorio: vitest solo incluye `lib/**/*.test.ts` (`web/vitest.config.ts`), por eso la lógica de las líneas vive en `lib/`, no en componentes.
- [ ] Tests que fallen en `web/lib/price-track.test.ts`: `trackLine(track)` con 1 baja USD («Bajó 1 vez…»), 3 bajas, caso ARS («-$ X (-p%), unos USD Y»), `null` si `drops == 0` o neto no es baja; `summaryLine(track)` («{n} baja(s) · -USD … desde el {dd/mm}»); `trackingNote(listing, firstAt)`: «Detectado» → nota de «No sabemos cuándo se publicó…»; publicado mucho antes del primer snapshot → «Seguimos este aviso desde el {dd/mm}…» (definir umbral, propuesto 2 días de diferencia; confirmarlo en el test); usa `money`, `pct`, `dayMonth` de `lib/format.ts`.
- [ ] Agregar los textos a `web/lib/copy.ts` y confirmar que `lib/copy.test.ts` (que escanea `app/`, `components/` y `lib/copy.ts`) sigue verde y no deja pasar los términos prohibidos. Agregar test que verifique que ningún texto nuevo contiene «precio de cierre» ni «ofertá».
- [ ] En `web/app/admin/config/page.tsx`, sumar `price_track` a `HINTS` (la página lista todas las filas de `app_config` aunque la clave no esté; el `HINTS` solo agrega la descripción y la prioriza): «Bajas de precio por aviso (PAR-03). min_drop_pct: baja mínima en % para contarla en tarjeta, ficha y emails (distinta de price_drop_min_pct, que decide si se avisa).» Verificar que el editor de config (`web/lib/admin-config.ts`) acepta un objeto JSON para esa clave (hay tests `admin-config*.test.ts`; correrlos) y, si valida claves conocidas, agregar la validación de `min_drop_pct` (número >= 0) con su test.

## Task 9: tarjeta de resultados

Files: `web/components/app/listing-card.tsx`, `web/app/app/searches/[id]/page.tsx`, `web/e2e/` (spec nuevo `price-tracks.spec.ts`), `web/e2e/support/db.ts` si hace falta sembrar bajas.

- [ ] Test Playwright primero (desktop y 375 px): una búsqueda sembrada con un aviso con 2 bajas muestra «Bajó 2 veces desde que la vimos: …» en la tarjeta, sin desbordar a 375 px; un aviso sin bajas o con neto suba no muestra nada. El helper `seedListing` (`e2e/support/db.ts`, ~línea 120) ya inserta `prices` históricos como snapshots; reusarlo.
- [ ] En `searches/[id]/page.tsx`, tras `search_results`, un segundo `supabase.rpc("listing_price_tracks", { p_listing_ids: ids })` con los ids de la página (no de todos los resultados), indexado por `listing_id`; pasar `track` a `<ListingCard>`. Solo en esa pantalla: `app/page.tsx` y `saved/page.tsx` ya tienen su propio cálculo o no tienen los ids chicos; no agregar llamadas extra ahí.
- [ ] En `ListingCard` agregar la prop opcional `track` y la línea junto a `ageLine(card)`; partir de lo que dejó X-01 en la tarjeta y no tocar su pie/`footer`.

## Task 10: ficha, `<details>` y evento

Files: `web/app/app/listings/[id]/page.tsx` (secciones de histórico, ~línea 261), `web/components/app/price-history.tsx`, `web/app/app/listings/actions.ts`, `web/e2e/price-tracks.spec.ts`.

- [ ] Test Playwright primero: la ficha con 2+ puntos muestra el resumen arriba, el histórico cerrado dentro de `<details>`, y al abrirlo se inserta un evento `price_history_expanded` con `{listing_id, drops, days}` en `events` (una sola vez por vista aunque se abra y cierre varias veces); con menos de 2 puntos la sección no aparece; con «Detectado» aparece la nota de que no sabemos cuándo se publicó.
- [ ] Server action `trackPriceHistoryExpanded(listingId, drops, days)` en `listings/actions.ts`, igual a `trackSellerQuestions` (`requireUser()` + `track()`). Componente cliente mínimo para el `<details>` (`onToggle` con un `ref` para disparar una sola vez), y resumen con `summaryLine`/`trackingNote`. La ficha llama `listing_price_tracks([listingId])` (o reusa `priceHistory(snapshots)` para la lista y la RPC solo para el resumen, para que haya una sola definición de «baja»).
- [ ] La sección sigue apareciendo solo con 2 o más puntos; `PriceHistory` mantiene «Bajó/Subió X desde que la vimos por primera vez» solo si no se duplica con el resumen (resolver en el mismo cambio).
- [ ] `/app/saved` queda con su cálculo propio (`watchEvents`); no se unifica en este ítem (anotarlo en el PR).

## Task 11: verificación y cierre

- [ ] `python -m pytest worker/tests -q -m "not db"` verde; con `TEST_DATABASE_URL` sobre `automotive_test`, `python -m pytest -m db -q` verde.
- [ ] `npx supabase test db` verde; en `web/`: `npm test`, `npm run lint`, `npm run e2e` (desktop y 375 px) verdes.
- [ ] Revisar que el HTML de los emails generados no contenga términos de `FORBIDDEN_TERMS`, «precio de cierre» ni «ofertá».
- [ ] `graphify update .` desde la raíz.
- [ ] Abrir PR de `claude/par03-dias-y-bajas` a `main` con el resultado del EXPLAIN y capturas de la tarjeta a 375 px. En la descripción: **la migración está lista pero sin aplicar en producción**; orden de despliegue: migración primero (Juan), después worker (con `wait_idle`, OK de Juan) y web (Vercel). La web nueva contra la base vieja haría fallar la RPC: la tarjeta y la ficha deben degradar sin línea de baja y sin romper si la RPC devuelve error (cubrirlo en un test).
- [ ] Marcar PAR-03 (parte por aviso) como entregado en `docs/BACKLOG_PRODUCTO_2026-10.md` y en el plan por fases al mergear; avisar a PAR-02 tramo 1 que puede rebasar.

## Rollback

Sacar `price_track` del payload en `on_matches` y `run_digest`, y la prop `track` de la tarjeta y el resumen de la ficha: los emails y pantallas vuelven al formato anterior y los payloads ya guardados no se tocan (la clave es opcional). La función SQL queda inerte sin dañar nada; si se quiere sacar, `drop function public.listing_price_tracks(bigint[])` y `delete from app_config where key = 'price_track'` en otra migración con timestamp mayor (nunca editar la aplicada).

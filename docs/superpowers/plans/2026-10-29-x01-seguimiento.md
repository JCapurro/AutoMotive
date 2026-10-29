# X-01: seguimiento en la UI (estados y notas)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Track the steps below during implementation.

**Goal:** Devolver a la web el selector de estado de una publicación (`contacted`, `visit_scheduled`, `purchased`, además de guardada y descartada), una nota por publicación y un filtro por estado en Guardados y en los resultados de una búsqueda. Diseño aprobado: [2026-10-29-x01-seguimiento-design.md](../specs/2026-10-29-x01-seguimiento-design.md). Ítem X-01 de [BACKLOG_PRODUCTO_2026-10](../../BACKLOG_PRODUCTO_2026-10.md).

**Architecture:** Las reglas de estado y de nota viven en funciones puras (`web/lib/listing-tracking.ts`) usadas por las server actions de `web/app/app/listings/actions.ts` (`setStatus` endurecido, `setNote` nueva, `recordPurchase` reactivada). Un componente cliente nuevo (bloque «Seguimiento») se monta debajo de `ListingActions` en la ficha. Guardados filtra por `?e=` sobre `user_listing_interactions` (sin SQL nuevo). Los resultados necesitan SQL: una migración agrega `note` al final de `match_cards`, tres valores de `p_filter` en `search_results` y la función `search_follow_counts`; `search_result_counts` no se toca. No cambian el score, los comparables, los avisos ni el worker.

**Tech Stack:** Next 16.3 / React 19 (web), Supabase Postgres + pgTAP, vitest (`environment: node`, solo `lib/**/*.test.ts`), Playwright (proyectos `desktop` y `mobile` a 375 px), pytest para confirmar que el worker no se rompe.

## Alcance y decisiones aprobadas

Juan aprobó tal cual las ocho propuestas de «Decisiones que necesita de Juan» del diseño:

1. «Comprado» se reactiva desde el selector con `recordPurchase`; el diálogo pide precio, moneda y fecha, todos opcionales.
2. El criterio 5 de `v_validation_criteria` pasa a contar solo `visit_scheduled` y `purchased` desde el despliegue; `contacted` queda como métrica propia en `/admin`. Va en una migración separada (Bloque C), con su pgTAP.
3. Largo de la nota: 500 caracteres, en `app_config.listing_tracking.note_max_chars`. El CHECK de 2000 en la base es solo un tope técnico anti-abuso.
4. Select de estado compacto dentro de cada tarjeta de Guardados, además de la ficha.
5. Las tres píldoras nuevas de resultados (`contacted`, `visit_scheduled`, `purchased`) siempre visibles, con su conteo.
6. «Comprado» es terminal en la UI en v1: el select queda deshabilitado con aclaración y no se construye «deshacer».
7. Microcopy del bloque de nota según el punto 10 del diseño: «Seguimiento», «Estado», «Tu nota» (placeholder «Qué hablaste, cuándo es la visita, qué falta revisar»), «Guardar nota», y «La nota es privada: no se la mostramos al vendedor ni a otros usuarios.». No decir «solo la ves vos».
8. Lectura de solo lectura de los seis criterios de `v_validation_criteria` en producción antes de desplegar (a), como línea de base.

Se mantienen del diseño: disponible para todos los planes, sin gating y sin clave en `plan_feature()`; nada de CSV; `new` no se elige; `contacted` y `visit_scheduled` no tocan `saved`; Guardar nunca baja un estado de seguimiento; la pregunta «¿Ese Auto influyó?» (`answerInfluence`) queda fuera; evento nuevo `listing_note_saved` con `{listing_id, length}` y nunca el contenido.

**Lo que Juan NO aprobó ni aportó (tareas suyas, no se inventan):**

- Texto legal de Privacidad y Términos sobre las notas (`web/app/privacidad/page.tsx:40` hoy menciona estados pero no notas). Este plan no toca esas páginas.
- Cualquier OK para aplicar migraciones en producción o desplegar (web o base). Las migraciones de este plan se aplican SOLO en una base local o `*_test`; aplicar a producción es un paso de Juan.
- Lectura en producción de: filas con `note` no nula y su largo máximo (el `validate constraint` puede fallar si hay alguna de más de 2000), valor vivo de `validation_criteria.outcome_min_users` y usuarios que hoy cuentan en el criterio 5.

**Rama:** `claude/x01-seguimiento`, creada desde la rama que contenga el diseño (verificar con `git log -- docs/superpowers/specs/2026-10-29-x01-seguimiento-design.md`; hoy está en `claude/disenos-fase0-1`, commit 82d0bfa). Un PR por bloque si Juan lo prefiere; si no, un PR con puntos de parada.

**Orden de edición con el resto del backlog (serializar):**

1. H-01 (PR #50 sin mergear, rama `claude/email-seller-questions`) toca `email_html.py`, `templates.py` y snapshots de notificaciones. X-01 no toca esos archivos, así que no choca en código; el orden de merge es H-01 → X-01 → PAR-03 → PAR-02 tramo 1.
2. La migración de `match_cards`/`search_results` es el punto de choque real: X-01 va primero y PAR-03 parte de la definición de X-01 (no de 20261030/20261013). Si PAR-03 o PAR-02 ya aterrizaron algo sobre esas piezas cuando llegue el Bloque B, copiar la última definición vigente, no la de este plan.
3. El timestamp provisorio `20261119120000` debe ser mayor que `max(version)` conocido (`20261118130000`) y que cualquier migración de F-03 ya mergeada; rever con `ls supabase/migrations | tail` al momento de crearla. F-03 es independiente.

**Comandos de prueba** (desde la raíz salvo que diga otra cosa):

- Web: `cd web && npm test` (vitest), `cd web && npm run typecheck`, `cd web && npm run lint`, `cd web && npx playwright test e2e/tracking.spec.ts --project=desktop --project=mobile` (el e2e usa el puerto 3100; el 3000 es la web legacy de producción).
- pgTAP: `npx supabase test db` (todo) o `npx supabase test db supabase/tests/x01_tracking_test.sql` (un archivo). Necesita el stack local (`npx supabase start`); Docker Desktop en la PC de Juan tiene un problema conocido de arranque: si no levanta, avisar a Juan y no tocar su configuración.
- Python: `pytest` desde la raíz; para los tests contra Postgres, `cd worker; python -m tools.test_db` y `$env:TEST_DATABASE_URL = "postgresql://postgres:postgres@127.0.0.1:54322/automotive_test"; pytest`. Nunca sobre la base del piloto.

## Diferencias con el diseño detectadas al armar el plan

- `web/vitest.config.ts` incluye solo `lib/**/*.test.ts` con `environment: node`: no hay tests de componente con DOM. Los tests «de componente» del diseño se hacen con `renderToStaticMarkup` en `web/lib/*.test.ts` (como `lib/listing-card.test.ts`) para el markup, y las interacciones (diálogos, cambiar de estado) se cubren en Playwright.
- `ListingActions` hoy decide «Guardada» con `status === 'interested' && saved`; cambia a leer `saved` (Task 6).
- La ficha ya trae `search_profile_id` por cada match (`listings/[id]/page.tsx:63`) y el `best` del match de mayor score; sirve para `recordPurchase`. La consulta de `user_listing_interactions` de la línea 67 hay que ampliarla con `note`.
- La clave `listing_tracking` no existe en `app_config` hasta la migración (Bloque B). En el Bloque A `webConfig()` usa 500 por defecto cuando falta, y recién después de aplicar la migración es editable en `/admin/config`.

---

# Bloque 0: preparación

## Task 1: leer las guías de la web antes de tocar `web/`

- [x] Leer `web/CLAUDE.md` (que importa `web/AGENTS.md`: «This is NOT the Next.js you know»).
- [x] Leer en `web/node_modules/next/dist/docs/` (`01-app/`, `index.md`) lo que corresponde a este trabajo: server actions y `'use server'`, `refresh()` de `next/cache` (la app lo usa en `actions.ts`), `searchParams` como promesa en `page.tsx`, componentes cliente. Anotar en el PR qué guías se leyeron.
- [x] Revisar avisos de deprecación que afecten a lo que se usa (`refresh`, `searchParams`, `useTransition` con acciones).

## Task 2: rama y línea base

- [x] `git switch -c claude/x01-seguimiento` desde la rama con el diseño; confirmar que `git status` no arrastra cambios ajenos (los `graphify-out/` modificados y los `docs/*.json` sin seguimiento de la sesión anterior no se incluyen en los commits de X-01).
- [x] Línea base verde antes de cambiar nada: `cd web && npm test && npm run typecheck && npm run lint` y `pytest` en la raíz. Registrar los fallos preexistentes, si hay.

---

# Bloque A: entrega (a), solo web, sin migración

Funciona con el esquema de hoy (la columna `note` y los siete estados ya existen). Se puede publicar sola.

## Task 3: reglas puras de seguimiento

Files: `web/lib/listing-tracking.ts` (nuevo), `web/lib/listing-tracking.test.ts` (nuevo).

- [x] Tests primero (vitest), que fallen:
  - `selectableStatuses()` devuelve, en este orden: `seen`, `interested`, `contacted`, `visit_scheduled`, `purchased`, `discarded`; nunca `new`. Los rótulos salen de `STATUS` en `web/lib/copy.ts` (Visto, Guardada, Contactado, Visita agendada, Comprado, Descartado).
  - `statusOnSave(current)`: con `contacted` o `visit_scheduled` devuelve `{ kind: "setSaved" }`; con cualquier otro devuelve `{ kind: "setStatus", status: "interested" }`.
  - `canChangeStatus(from, to)`: falso cuando `from === "purchased"` (terminal en v1), falso cuando `to === "purchased"` (va por `recordPurchase`) y cuando `to === "new"`; verdadero en el resto.
  - `normalizeNote(raw, max)`: `trim`; vacío o solo espacios → `null`; más de `max` → `{ error }` (no se corta en silencio); caracteres de control y saltos de línea se conservan salvo `\u0000`.
- [x] Implementar `web/lib/listing-tracking.ts` con esas funciones y la constante `NOTE_MAX_DEFAULT = 500`.
- [x] `cd web && npx vitest run lib/listing-tracking.test.ts` en verde.

## Task 4: acciones del servidor (`setStatus` endurecido, `setNote`)

Files: `web/app/app/listings/actions.ts`, `web/lib/listing-interactions.test.ts` (ampliar; ya mockea `requireUser`, `next/cache`, `@/lib/events` y `@/lib/supabase/server`).

- [x] Tests primero, que fallen:
  - `setStatus` lanza si el estado actual es `purchased` (lectura con `currentStatus`), sin llamar a `upsert`.
  - `setStatus(…, "contacted")` y `("visit_scheduled")` hacen upsert sin tocar `saved` y emiten `listing_status_changed` con `{listing_id, status, from, via:"web"}`.
  - `setNote`: recorta, vacío guarda `null`, más del tope falla sin escribir, upsert solo de `note` con `onConflict: "user_id,listing_id"`, emite `listing_note_saved` con `{listing_id, length}` y el evento **no contiene el texto**; si el upsert devuelve error, lanza y no llama a `refresh`.
  - El tope sale de `webConfig()` (mockear `@/lib/config`), no de una constante dentro de la acción.
- [x] Implementar en `actions.ts`: rechazo de cambios desde `purchased` en `setStatus` (conservar el rechazo existente de `status === "purchased"`), y `export async function setNote(listingId: number, note: string)` usando `normalizeNote` y `webConfig().listingTracking.noteMaxChars`.
- [x] `cd web && npx vitest run lib/listing-interactions.test.ts` en verde y los tests existentes del archivo sin cambios.

## Task 5: parámetro `listing_tracking` en `webConfig()`

Files: `web/lib/config.ts` (lista de claves en la línea ~60 y objeto devuelto), `web/lib/config.test.ts` o el test de config existente (buscarlo con `Grep webConfig web/lib/*.test.ts`), `web/app/admin/config/page.tsx` (mapa de descripciones, junto a `comparables`).

- [x] Test primero: sin la clave, `listingTracking.noteMaxChars === 500`; con `{"note_max_chars": 300}`, 300; valores no numéricos o ≤ 0 caen al default.
- [x] Agregar `"listing_tracking"` a la lista `.in("key", [...])` y exponer `listingTracking: { noteMaxChars }` en `WebConfig`.
- [x] Agregar la descripción en `/admin/config`: «Seguimiento de publicaciones (X-01). note_max_chars: largo máximo de la nota por publicación (500).». Revisar `web/lib/admin-config*.test.ts` por si exigen que toda clave tenga esquema o descripción.
- [x] Nota: hasta que se aplique la migración del Bloque B la fila no existe y aplica el default; no hay que crearla a mano.

## Task 6: Guardar nunca baja un estado de seguimiento

Files: `web/components/app/listing-actions.tsx`, `web/lib/listing-tracking.ts` (ya con `statusOnSave`), test en `web/lib/listing-tracking.test.ts` y markup en un test nuevo `web/lib/listing-actions.test.ts` (patrón `renderToStaticMarkup`).

- [x] Test primero: con `status="contacted"` y `saved=true` el botón se ve «Guardada» con `aria-pressed="true"`; con `status="contacted"` y `saved=false` se ve «Guardar» y no «Guardada»; con `status="interested"` y `saved=true` igual que hoy.
- [x] Cambiar `const interested = status === "interested" && saved` por `saved` y el `onClick` para usar `statusOnSave`: en `contacted`/`visit_scheduled` llamar `setSaved(listingId, true)` (ya existe en `actions.ts:85`, hoy sin uso en pantallas); en el resto `setStatus(listingId, "interested")`. Mantener el `pixel("AddToWishlist")` y `analyticsEvent` solo cuando `!saved`.
- [x] Verificar si `setSaved` emite `listing_saved`; si no lo hace, agregarlo con su test (el evento ya existe en `setStatus`) para que la métrica de guardados no se pierda en este camino.

## Task 7: bloque «Seguimiento» en la ficha, con diálogo de compra

Files: `web/components/app/listing-tracking.tsx` (nuevo, `"use client"`), `web/app/app/listings/[id]/page.tsx` (montarlo debajo de `ListingActions`, ~línea 198, y ampliar la consulta de la línea 67 con `note`), `web/lib/listing-tracking-ui.test.ts` (nuevo).

- [ ] Tests primero (`renderToStaticMarkup`, en `web/lib/listing-tracking-ui.test.ts`):
  - El bloque se llama «Seguimiento» y tiene un select con label «Estado» y exactamente las seis opciones de `selectableStatuses()`.
  - Con `status="purchased"` el select está deshabilitado y aparece una aclaración de que la compra no se puede deshacer desde acá.
  - Textarea con label «Tu nota», placeholder «Qué hablaste, cuándo es la visita, qué falta revisar», botón «Guardar nota» y la frase «La nota es privada: no se la mostramos al vendedor ni a otros usuarios.»; `maxLength` igual al tope recibido por props.
  - La nota existente se muestra con `whitespace-pre-line` y como texto (un `<script>` en la nota sale escapado).
  - El bloque aparece también cuando la publicación ya no está disponible (`listing_status` distinto de `active`).
- [ ] Implementar con `NativeSelect` (el que ya usa la app; confirmar el componente con `Grep NativeSelect web/components`). «Descartado» abre el `DiscardDialog` existente (extraerlo de `listing-actions.tsx` a un export reutilizable en vez de duplicarlo); «Comprado» abre un diálogo nuevo (precio, moneda `USD|ARS`, fecha; todo opcional; texto de confirmación de que es definitivo) que llama a `recordPurchase({ listingId, profileId: best?.search_profile_id, … })` con el esquema `Purchase` de `actions.ts`; si devuelve `error`, `toast.error` y el estado no cambia.
- [ ] Cambios de estado: `canChangeStatus` antes de llamar a `setStatus`; usar `useTransition` y `toast` como `ListingActions`. La nota: `setNote`, con contador de caracteres.
- [ ] Pasar por props el tope (`webConfig().listingTracking.noteMaxChars`, ya cargado en la página) y la `note` actual.
- [ ] `cd web && npx vitest run lib/listing-tracking-ui.test.ts` en verde.

## Task 8: Guardados con filtro, estado, nota y select

Files: `web/app/app/saved/page.tsx`, `web/components/app/listing-card.tsx` (solo si hace falta una prop para la nota; el `footer` ya existe), `web/components/app/listing-status-select.tsx` (nuevo, select compacto reutilizable por la Task 7), `web/lib/saved-page.test.ts` (nuevo; modelarlo con `lib/free-result-limit-page.test.ts`, que ya mockea Supabase para una `page.tsx`).

- [ ] Tests primero:
  - Sin `?e=`: la consulta de `user_listing_interactions` trae `saved = true` o estado en `interested, contacted, visit_scheduled, purchased` (se suma `purchased` solo en la web; `FOLLOWED` del worker no cambia) y selecciona también `note`.
  - Con `?e=contacted`, `?e=visit_scheduled`, `?e=purchased`: la consulta filtra por ese `status`; un valor desconocido de `e` cae a «Todos».
  - Se dibujan las píldoras Todos, Contactados, Visita agendada, Comprados con el estado activo marcado, y cada tarjeta muestra `StatusBadge` y la nota recortada a una línea.
  - Filtro vacío: mensaje propio («No marcaste publicaciones como contactadas.», etc.), sin romper la pantalla de «Todavía no guardaste publicaciones».
- [ ] Implementar. El select compacto va en el `footer` de `ListingCard` con `relative z-10`: la tarjeta tiene el link estirado (`after:absolute after:inset-0`) y sin eso el click abre la ficha. Elegir «Comprado» o «Descartado» desde la tarjeta abre los mismos diálogos de la Task 7; para «Comprado» sin `profileId` conocido, pasar el del mejor match (la página ya consulta `matches`, línea ~59).
- [ ] Verificar a 375 px en la Task 10 (queda como riesgo hasta ver Playwright).

## Task 9: lint de copy

Files: `web/lib/copy.test.ts`.

- [ ] Agregar los textos nuevos («Seguimiento», «Estado», «Tu nota», placeholder, «Guardar nota», frase de privacidad de la nota, aclaración de «Comprado» terminal, mensajes de filtro vacío) al chequeo existente de términos prohibidos de `web/lib/copy.ts` (prohibidos «vale», «valor real», «precio real», «tasación», «tasado»). Si los textos viven en el componente y no en `copy.ts`, moverlos a `copy.ts` para que el lint los cubra.
- [ ] `cd web && npx vitest run lib/copy.test.ts` en verde.

## Task 10: e2e de la entrega (a)

Files: `web/e2e/acceptance.spec.ts` (paso 5, líneas ~186-188), `web/e2e/tracking.spec.ts` (nuevo), `web/e2e/seed.ts`, `web/e2e/support/db.ts` (solo si falta un helper).

- [ ] Cambiar el paso 5 de `acceptance.spec.ts`: hoy afirma `toHaveCount(0)` para el label «Estado» y el botón «Compré este vehículo»; pasar a afirmar que el label «Estado» existe una vez, que el flujo de Guardar sigue dejando `{status:"interested", saved:true}` y que «Ver el puntaje en números» sigue sin existir. Verificar con `Grep "Compré este vehículo" web` que no queda otra aserción de ese retiro.
- [ ] Sembrar en `seed.ts` los avisos necesarios para el spec nuevo (uno activo y uno `gone`, ambos con match del usuario e2e; el prefijo `e2e` obligatorio).
- [ ] Escribir primero `web/e2e/tracking.spec.ts` (debe fallar antes de las Tasks 6-8 si se corre desde la rama base): cambiar a «Contactado» en la ficha y leer la fila en la base; Guardar después de «Contactado» deja el estado en `contacted` con `saved=true`; guardar una nota y verla en Guardados; filtrar por estado en Guardados; cambiar el estado desde el select de la tarjeta sin abrir la ficha; «Comprado» desde el diálogo crea la fila en `owned_vehicles` y deja el select deshabilitado; `expectNoHorizontalScroll` en ficha y Guardados.
- [ ] `cd web && npx playwright test e2e/tracking.spec.ts e2e/acceptance.spec.ts --project=desktop --project=mobile` en verde. Mirar capturas a 375 px del select dentro de `ListingCard`.

## Task 11: verificación de (a), PR y punto de parada

- [ ] `cd web && npm test && npm run typecheck && npm run lint` y `pytest` en la raíz: todo verde sin tocar worker ni SQL.
- [ ] `graphify update .` desde la raíz.
- [ ] Abrir el PR de (a) a `main` (rama `claude/x01-seguimiento`) con: qué guías de Next se leyeron, capturas desktop y 375 px, y la nota de que no hay migración.
- [ ] Marcar «X-01 (a)» en `docs/BACKLOG_PRODUCTO_2026-10.md` y en `docs/PLAN_FASES_BACKLOG_PRODUCTO_2026-10.md` al mergear.

**PUNTO DE PARADA 1.** Acá termina la entrega (a). No se sigue con el Bloque B sin que Juan lo pida, y desplegar (a) a producción es decisión de Juan. Antes de desplegar (a), con OK de Juan: (i) lectura de solo lectura de los seis criterios de `v_validation_criteria` como línea de base (decisión 8) y, ya que se está leyendo, `validation_criteria.outcome_min_users` y cuántos usuarios cuentan hoy en el criterio 5; (ii) decidir si la migración del criterio 5 (Bloque C) se aplica junto con el despliegue de (a), porque marcar «Contactado» cuesta un click y el criterio 5 se infla sin ella.

---

# Bloque B: entrega (b), migración y filtros

Requiere el PUNTO DE PARADA 1 resuelto. **Orden de despliegue: base primero, web después**; la web nueva contra la base vieja haría que los filtros nuevos caigan en el `else` de `search_results` y muestren «Todos» sin avisar. La base nueva con la web vieja es inocua. Aplicar la migración a producción y desplegar son pasos de Juan (ver «Tareas de Juan»).

## Task 12: pgTAP primero

Files: `supabase/tests/x01_tracking_test.sql` (nuevo; modelarlo con `supabase/tests/free_result_quota_test.sql` y `f4_web_test.sql`, que ya siembran usuarios, avisos y matches).

- [ ] Escribir el test completo antes de la migración, para que falle en rojo con el esquema actual:
  - RLS: A no ve ni modifica filas de `user_listing_interactions` de B, y no puede insertar con el `user_id` de B (SQLSTATE 42501).
  - CHECK: una nota de 2001 caracteres es rechazada (23514); una de 2000 pasa.
  - `match_cards.note` trae solo la nota propia.
  - `search_results(p_profile_id, 'contacted' | 'visit_scheduled' | 'purchased', …)` devuelve solo ese estado, y una publicación con `listing_status = 'gone'` contactada **sí** aparece (los filtros nuevos no exigen `active`).
  - `search_follow_counts(p_profile_id)` coincide con la cantidad devuelta por cada filtro.
  - Con un usuario `free` con el cupo enforced, los tres filtros respetan el tope de 50 (ver `free_result_quota_test.sql`).
  - `app_config.listing_tracking` existe con `note_max_chars = 500`.
  - `search_follow_counts` no es ejecutable por `anon` y sí por `authenticated`.
  - Los asserts de `f4_web_test.sql:85-87` y de `free_result_quota_test.sql:25` siguen verdes sin cambios (no editarlos).
- [ ] `npx supabase test db supabase/tests/x01_tracking_test.sql` falla por las razones esperadas (columna/función inexistentes).

## Task 13: migración `20261119120000_x01_tracking.sql`

Files: `supabase/migrations/20261119120000_x01_tracking.sql` (nombre provisorio; ver «Orden de edición»).

- [ ] Encabezado `--` que cite `docs/BACKLOG_PRODUCTO_2026-10.md` y el ID **X-01** y el diseño `docs/superpowers/specs/2026-10-29-x01-seguimiento-design.md`. No editar migraciones viejas.
- [ ] `create or replace view match_cards` copiando exacto la definición de `20261030120000_body_type.sql` (línea ~80) y agregando `i.note` **al final** de la lista de columnas (solo se agregan columnas al final). Mantener `security_invoker`.
- [ ] `create or replace function search_results` con la misma firma, copiando exacto `20261013120000_available_opportunities_keep_history.sql` y cambiando solo el `case` de `p_filter`: tres ramas nuevas `contacted`, `visit_scheduled`, `purchased` con `c.status = '<estado>'` y **sin** `listing_status = 'active'`. Los demás filtros y el orden no cambian. Releer ambos archivos antes de copiar; si PAR-03/PAR-02 ya aterrizaron algo, copiar la última definición.
- [ ] `search_follow_counts(p_profile_id)` → `(contacted_count, visit_scheduled_count, purchased_count)`, `security invoker`, `set search_path = ''`, con `revoke all … from public, anon` y `grant execute … to authenticated` explícitos (no confiar en los default privileges). **No tocar `search_result_counts`** (cambiar sus columnas obliga a `drop function` y rompe `worker/tests/test_availability_postgres.py:62`, que compara `SELECT *` contra un dict de exactamente 5 claves).
- [ ] `alter table user_listing_interactions add constraint … check (note is null or char_length(note) <= 2000) not valid;` y después `validate constraint` (si hay filas de más en producción, `validate` falla: por eso se mide antes, tarea de Juan).
- [ ] `insert into app_config … 'listing_tracking' '{"note_max_chars": 500}' on conflict do nothing`.
- [ ] Sin cambios de RLS, de `record_purchase` ni de `v_validation_criteria` (eso es el Bloque C).

## Task 14: aplicar en local y correr todo

- [ ] Aplicar SOLO en el stack local: `npx supabase db reset` (o `npx supabase migration up`) y `cd worker; python -m tools.test_db` para refrescar `automotive_test`. No hay paso contra producción en esta tarea.
- [ ] `npx supabase test db` completo en verde (el nuevo `x01_tracking_test.sql` y todos los previos, en particular `f4_web_test.sql`, `free_result_quota_test.sql`, `f6_metrics_test.sql`, `rls_test.sql`).
- [ ] `$env:TEST_DATABASE_URL = "postgresql://postgres:postgres@127.0.0.1:54322/automotive_test"; pytest` en verde, sobre todo `worker/tests/test_availability_postgres.py` y los de `watchlist_queue`: confirma que el worker no cambió.

## Task 15: tipos

Files: `web/types/database.ts`.

- [ ] `cd web && npm run gen:types` (corre contra el stack local) y revisar que el diff solo agregue `note` a `match_cards`, `search_follow_counts` y nada más. `npm run typecheck`.

## Task 16: resultados con píldoras, conteos y nota

Files: `web/app/app/searches/[id]/page.tsx` (`Filter`, `COUNT_KEY`, `EMPTY`, `FILTERS`, `loadCounts`, líneas ~37-100 y ~148), `web/components/app/listing-card.tsx` (nota recortada a una línea), `web/lib/search-preparation.test.ts` y `web/lib/free-result-limit-page.test.ts` (mocks), `web/lib/follow-filters.test.ts` (nuevo).

- [ ] Tests primero:
  - `Filter` acepta `contacted`, `visit_scheduled`, `purchased`; `?f=` desconocido sigue cayendo en `all`.
  - Las tres píldoras se dibujan siempre, con su conteo, aunque sea 0 (decisión 5).
  - `loadCounts` llama también a `search_follow_counts` y tolera `null`/error: los mocks de `search-preparation.test.ts` y `free-result-limit-page.test.ts` devuelven `null` para RPCs que no conocen, y la página no debe romper ni mostrar `NaN`.
  - Textos vacíos propios por filtro («No marcaste publicaciones como contactadas.», etc.).
  - `ListingCard` muestra la nota recortada a una línea y escapada cuando `card.note` existe; sin nota no cambia el markup actual (`lib/listing-card.test.ts` sigue verde).
- [ ] Implementar; el `nav` de píldoras ya hace scroll horizontal (quedan 8 a 375 px).
- [ ] `cd web && npm test && npm run typecheck && npm run lint`.

## Task 17: e2e de (b)

Files: `web/e2e/tracking.spec.ts` (ampliar), `web/e2e/seed.ts`.

- [ ] Primero los casos nuevos (rojo): en los resultados de una búsqueda, filtrar por Contactadas / Visita agendada / Compradas y ver la publicación `gone` contactada con su cartel «Ya no está disponible»; ver la nota en la tarjeta; los conteos de las píldoras coinciden con las filas; `expectNoHorizontalScroll` en resultados con las 8 píldoras a 375 px.
- [ ] `cd web && npx playwright test e2e/tracking.spec.ts --project=desktop --project=mobile` en verde contra la base local ya migrada.

## Task 18: verificación de (b), PR y punto de parada

- [ ] Todo verde: `npx supabase test db`, `pytest` (con y sin `TEST_DATABASE_URL`), `cd web && npm test && npm run typecheck && npm run lint && npx playwright test --project=desktop --project=mobile` (la suite completa, para no romper otros specs).
- [ ] `graphify update .`.
- [ ] PR de (b) a `main`. Descripción con el orden de despliegue (base primero, web después), el rollback y la nota de que la migración **no está aplicada en producción**.
- [ ] Marcar «X-01 (b)» en el backlog y el plan por fases al mergear.

**PUNTO DE PARADA 2.** Fin de (b). Aplicar la migración a producción y desplegar la web son pasos de Juan.

---

# Bloque C: criterio 5 sin `contacted` (decisión 2), migración separada

Va aparte para separar el cambio de producto del cambio de la regla con la que Juan mide la validación. Se puede mergear antes o después del Bloque B, pero conviene aplicarla en producción junto con (a). Serializar con cualquier otra migración que toque `v_validation_criteria` o `metric_alert_rows`.

## Task 19: criterio 5 cuenta solo `visit_scheduled` y `purchased`; `contacted` como métrica propia

Files: `supabase/tests/f6_metrics_test.sql` (actualizar: fija los valores de los seis criterios), `supabase/migrations/<timestamp mayor que el del Bloque B>_x01_outcome_metric.sql` (nuevo), `web/` solo si la métrica de `contacted` se muestra en `/admin` (ver más abajo).

- [ ] Leer la definición vigente de `v_validation_criteria` (`20261003120000_f6_backoffice_metrics.sql:536`, única definición al 29/10) y de `metric_alert_rows` (línea ~346) y `git log -- supabase/migrations | grep -i metric` por si hubo redefiniciones posteriores. Confirmar si `metric_alert_rows.saved` (criterio 3) también cuenta `contacted | visit_scheduled | purchased`.
- [ ] pgTAP primero: en `f6_metrics_test.sql` agregar casos donde un usuario con solo `contacted` **no** suma al criterio 5 y uno con `visit_scheduled` o `purchased` sí; actualizar los valores esperados que cambien; ver el test en rojo.
- [ ] Migración: `create or replace` de `v_validation_criteria` copiando exacta la vigente y cambiando solo la condición del criterio 5 (cuenta `visit_scheduled | purchased` en `user_listing_interactions`, `owned_vehicles` y los eventos `listing_status_changed` equivalentes). Encabezado que cite el backlog, el ID X-01 y la decisión 2. Sin tocar `outcome_min_users`.
- [ ] `contacted` como métrica propia en `/admin`: definir la fuente mínima (conteo de usuarios con algún `contacted` y de eventos `listing_status_changed` con `status = 'contacted'`) en la misma migración, y mostrarla donde viven hoy las métricas de validación (buscar con `Grep v_validation_criteria web`). **No verificado:** qué pantalla y qué componente la mostrarían; resolverlo leyendo `web/lib/admin-dashboard*.ts` antes de escribir la UI y, si implica más de una tarjeta, acordarlo con Juan.
- [ ] Aplicar solo en local, `npx supabase test db` completo, `npm test` si se tocó `web/`.
- [ ] PR propio. No aplicar en producción.

---

# Cierre

## Task 20: cierre y rollback documentado

- [ ] Actualizar en el backlog y en el plan por fases el estado de X-01 (a), (b) y el criterio 5, con los commits.
- [ ] `graphify update .` al final de cada bloque ya hecho; verificar que el último esté al día.
- [ ] Confirmar que ninguna tarea tocó `worker/`, `web/app/privacidad`, `web/app/terminos` ni `app_config` de producción.

## Tareas de Juan (no las hace Code)

- [ ] Texto de Privacidad y Términos sobre las notas (y, si corresponde, sobre «Comprado»): lo redacta Juan o quien corresponda.
- [ ] Antes de desplegar (a): lectura de solo lectura en producción de los seis criterios, `outcome_min_users` y usuarios del criterio 5 (línea de base, decisión 8); Code puede hacerla únicamente con su OK en el momento.
- [ ] Antes de aplicar el Bloque B en producción: releer `max(version)` (conocida: `20261118130000`), medir filas con `note` no nula y su largo máximo (solo lectura), y dar el OK. Aplicación en transacción, con la versión exacta insertada en el historial de migraciones; recién después desplegar la web.
- [ ] OK para aplicar el Bloque C en producción y decidir si va junto con el despliegue de (a).
- [ ] OK de cada despliegue de web (Vercel). No hay cambio de worker: sin reinicio ni `wait_idle`.

## Rollback

- **(a):** revertir el PR de la web; los estados y notas ya guardados quedan en `user_listing_interactions` sin efecto y los avisos del worker (que ya tratan `contacted`/`visit_scheduled` como seguidos) no cambian.
- **(b):** revertir la web primero; en SQL, `create or replace` de vuelta a las definiciones de `20261013120000` (`search_results`) y `20261030120000` (`match_cards`, sin `note`), `drop function search_follow_counts(bigint)` (confirmar el tipo del parámetro en la migración), `alter table user_listing_interactions drop constraint` del CHECK de nota y borrar la fila `app_config.listing_tracking`. Las notas guardadas quedan inertes.
- **C:** `create or replace` de `v_validation_criteria` con la definición previa.

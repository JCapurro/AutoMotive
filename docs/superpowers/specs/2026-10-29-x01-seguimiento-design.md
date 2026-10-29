# X-01 · Seguimiento en la UI (estados y notas)

Ítem del [backlog de producto](../../BACKLOG_PRODUCTO_2026-10.md) (X-01) y Fase 1 del [plan por fases](../../PLAN_FASES_BACKLOG_PRODUCTO_2026-10.md). Estado: **borrador para que Juan lo apruebe**; nada implementado, ninguna migración escrita ni aplicada. Fecha: 29/10/2026 (HEAD 8abd17b).

Alcance: devolver a la web el selector de estado de una publicación (`contacted`, `visit_scheduled`, `purchased`, además de guardada y descartada), una nota por publicación, y un filtro por estado en los resultados y en Guardados. Es para llevar la gestión de autos que hoy se hace en WhatsApp y una planilla. **Decisión de Juan: disponible para todos los planes, sin gating.** No cambia el score, los comparables, los avisos ni el worker. Sin exportación CSV (sigue en reserva, la retiró Juan el 15/10).

## Qué existe hoy (verificado en el repo)

- **Tabla.** `user_listing_interactions` (`20260927120000_core_schema.sql:256`): `status` (enum con los 7 valores), `saved`, `rejection_reason`, `note text` sin límite, `updated_at` con trigger. PK `(user_id, listing_id)`: el estado y la nota son por usuario y aviso, no por búsqueda.
- **`setStatus()`** (`web/app/app/listings/actions.ts:43`) ya acepta `contacted` y `visit_scheduled`; solo rechaza `purchased` (línea 45). Hace upsert, emite `listing_status_changed` con `{listing_id, status, from, via:'web'}` y, para `interested`/`discarded`, toca `saved`. No existe acción para la nota. `setSaved()` existe pero ninguna pantalla la usa.
- **UI.** `components/app/listing-actions.tsx` solo tiene Guardar, Descartar (con diálogo de motivo) y «Ver publicación». El selector se retiró en el commit `2cdb2782` («Simplify MVP actions»). Lo confirma `web/e2e/acceptance.spec.ts:186-188`: el paso 5 **afirma** que no existe el label «Estado» ni el botón «Compré este vehículo». Ese test tiene que cambiar.
- **`recordPurchase()`** (`actions.ts:105`) y la RPC `record_purchase` (última definición `20261030120000_body_type.sql:471`) existen, pero **ninguna pantalla las llama** (grep en `web/app`, `web/components`). La RPC crea la fila de `owned_vehicles`, pone `purchased` y emite `listing_status_changed` + `vehicle_purchased`. `answerInfluence()` (§38) tampoco tiene UI.
- **Guardados** (`web/app/app/saved/page.tsx:15`): lista `saved = true` o estado en `interested, contacted, visit_scheduled`. No incluye `purchased`, no tiene filtro ni nota.
- **Resultados** (`web/app/app/searches/[id]/page.tsx`): píldoras `new | opportunities | all | saved | discarded` con conteos de `search_result_counts`. `StatusBadge` (`components/app/badges.tsx`) ya sabe dibujar `contacted`, `visit_scheduled` y `purchased`.
- **SQL.** `match_cards` es una vista; su última definición es `20261030120000_body_type.sql:80` y no expone `note`. `search_results` y `search_result_counts` se redefinieron por última vez en **`20261013120000_available_opportunities_keep_history.sql`**, no en 20261030 (esa migración solo agregó `body_type` a la vista). `search_results` devuelve `setof match_cards`.
- **Cupo de la prueba** (`20261118120000_free_results_cap_50.sql`): **no redefine** `match_cards` ni `search_results`; agrega una policy restrictiva sobre `matches`. Como la vista es `security_invoker`, los filtros nuevos heredan el tope de 50 sin tocar nada.
- **RLS.** Policy `"user_listing_interactions: own rows"` `for all` con `user_id = auth.uid()` en `using` y `with check` (`20260927120100_rls.sql:63`). **No hay pgTAP dedicado** (grep en `supabase/tests/rls_test.sql` y `f4_web_test.sql`: solo siembran filas). Como la policy permite escribir cualquier valor, un usuario puede dejar `purchased` o una nota gigante por PostgREST saltándose la server action.
- **Worker.** `FOLLOWED_STATUSES` (`notifications/engine.py:45`), `watchlist_queue` (`db/repos/listings.py:423`) y `notification_access_active` (`20261118120000`, líneas 99-100) tratan `interested, contacted, visit_scheduled` como «seguidas»: se siguen revisando y siguen avisando aunque la búsqueda se pause. `apply_telegram_action` nunca baja un estado avanzado. Telegram ya no es canal activo.
- **Métrica.** `v_validation_criteria` se definió una sola vez (`20261003120000_f6_backoffice_metrics.sql:536`). El criterio 5 (Outcome) cuenta usuarios con algún `contacted | visit_scheduled | purchased`, en `user_listing_interactions`, en `owned_vehicles` o en eventos `listing_status_changed`; umbral `outcome_min_users` (default 3; **el valor vivo en producción no lo verifiqué**). `metric_alert_rows.saved` (línea 346) también cuenta esos estados, así que mueve además el criterio 3 (Engagement).
- **Privacidad.** `web/app/privacidad/page.tsx:40` ya dice «estados como "contacté" o "compré"»; no menciona notas.

### Correcciones al backlog y al plan

1. «`search_results` hoy 20261030 + free cap»: la última definición de `search_results`/`search_result_counts` es 20261013; 20261030 solo cambió la vista y el free cap no toca ninguna de las tres. La base para copiar es 20261013 (funciones) + 20261030 (vista).
2. «Para Pro»: queda sin efecto por la decisión de Juan. Tampoco se agrega clave de `plan_feature()` (regla 8 del backlog): no hay función que gatear.
3. «`listing_status_changed` ya existe como evento»: cierto, pero hoy solo lo disparan `setStatus` y `record_purchase`; no hay evento para la nota.
4. «Tamaño S»: es M. Hay migración (vista + función + CHECK), una acción nueva, UI en tres pantallas y tests en tres capas.
5. El plan dice que el efecto en la métrica es solo `v_validation_criteria`. Son dos criterios (3 y 5) y hoy ninguno se puede mover desde la UI web, porque el selector no existe.

## Decisión de diseño

1. **Sin gating.** Lo ven y lo usan todos los planes, incluida la prueba. Lo único que limita a la prueba es el cupo de 50 resultados, que ya filtra `matches` por RLS.
2. **Selector de estado en la ficha.** Bloque «Seguimiento» debajo de `ListingActions` (`listings/[id]/page.tsx` ~línea 198), también visible en publicaciones que ya no están. Un `NativeSelect` con label «Estado» y opciones: **Visto** (`seen`, sin seguimiento), **Guardada** (`interested`), **Contactado**, **Visita agendada**, **Comprado**, **Descartado**. `new` no se elige. Los nombres salen de `STATUS` en `web/lib/copy.ts`. «Descartado» abre el diálogo de motivo que ya existe; «Comprado», el diálogo del punto 5.
3. **Reglas de estado** (en `actions.ts`, con vitest):
   - Guardar nunca baja un estado de seguimiento. Hoy el botón usa `status === 'interested' && saved`; pasa a leer `saved`, y si el estado es `contacted` o `visit_scheduled` llama a `setSaved(true)` en vez de `setStatus('interested')`.
   - `setStatus` sigue rechazando `purchased` (va por `recordPurchase`) y además rechaza cualquier cambio desde `purchased` en v1: «Comprado» es terminal en la UI (el select queda deshabilitado con aclaración). No hay RPC para deshacer una compra; no se agrega en este ítem.
   - `contacted` y `visit_scheduled` no tocan `saved` (el worker y Guardados ya los tratan como seguidos).
4. **Nota.** Texto plano, una por (usuario, aviso). Acción nueva `setNote(listingId, note)`: `trim`, vacío → `null`, tope `app_config.listing_tracking.note_max_chars` (propuesto 500), upsert solo de `note`, evento nuevo `listing_note_saved` con `{listing_id, length}` (**nunca el contenido**). Textarea en la ficha con botón «Guardar nota». Se muestra como texto (React la escapa; `whitespace-pre-line`). En la base, un CHECK de respaldo `char_length(note) <= 2000` es un tope técnico anti-abuso, no un parámetro de producto.
5. **«Comprado».** Reactivar el camino que hoy no tiene UI: el diálogo pide precio, moneda y fecha (todos opcionales) y llama a `recordPurchase` con el `search_profile_id` del mejor match. Así `owned_vehicles`, `vehicle_purchased` y el panel «Outcomes (§38)» de `web/app/admin/metrics/diagnostic/page.tsx:217` siguen alimentándose por un solo camino. Fuera de alcance: la pregunta «¿Ese Auto influyó?» (`answerInfluence`), que queda como seguimiento aparte. Si Juan prefiere no reactivar la compra, se omiten «Comprado» y su filtro y el resto no cambia.
6. **Guardados.** (i) Píldoras de filtro por estado con `?e=` (Todos, Contactados, Visita agendada, Comprados), filtrando la consulta a `user_listing_interactions` (sin SQL nuevo). (ii) `FOLLOWED` suma `purchased` solo en la web: la compra queda a la vista; el worker no cambia. (iii) Cada tarjeta muestra el estado con `StatusBadge` y la nota recortada a una línea, y un select compacto en el `footer` para cambiar el estado sin abrir la ficha, que es lo que reemplaza la planilla. Ojo: `ListingCard` tiene el link estirado con `after:absolute after:inset-0`; el select necesita `relative z-10`.
7. **Resultados (SQL).** Una sola migración nueva:
   - `create or replace view match_cards` copiando la definición de 20261030 y **agregando `note` al final** (`i.note`). Solo se agregan columnas al final; `search_results` y `recent_opportunities` la heredan, como pasó con `body_type`.
   - `create or replace function search_results` (misma firma, copiando 20261013) con tres valores nuevos de `p_filter`: `contacted`, `visit_scheduled`, `purchased` (`c.status = '<estado>'`). A diferencia de `new`/`all`, **no exigen `listing_status = 'active'`**: una publicación contactada que se cayó tiene que seguir apareciendo, con su cartel «Ya no está disponible». Los demás filtros y el orden no cambian.
   - Función nueva `search_follow_counts(p_profile_id)` → `(contacted_count, visit_scheduled_count, purchased_count)`, `security invoker`. **No se modifica `search_result_counts`**: cambiar sus columnas obliga a `drop function` y rompe `worker/tests/test_availability_postgres.py:62`, que compara `SELECT *` contra un dict de exactamente 5 claves.
   - `check (note is null or char_length(note) <= 2000)` en `user_listing_interactions`, `not valid` y luego `validate constraint` (ver riesgo de datos más abajo).
   - `insert into app_config ... on conflict do nothing` con `listing_tracking`.
   - `revoke ... from public, anon; grant execute ... to authenticated` explícito para la función nueva (regla 3). Sin cambios de RLS, de `record_purchase` ni de `v_validation_criteria`.
8. **Resultados (web).** `Filter` suma tres claves con sus textos vacíos («No marcaste publicaciones como contactadas.», etc.); el `nav` de píldoras ya hace scroll horizontal, así que a 375 px quedan 8 píldoras en una fila deslizable. Las tarjetas muestran la nota recortada. `loadCounts` llama también a `search_follow_counts` y tolera `null` (los mocks de `search-preparation.test.ts` y `free-result-limit-page.test.ts` devuelven `null` para RPCs que no conocen).
9. **Config (regla 4).** `app_config.listing_tracking = {"note_max_chars": 500}`, leído por `webConfig()` (`web/lib/config.ts`, lista de claves en la línea 60) y editable en `/admin/config` (esquema en `web/lib/admin-config.ts`, descripción en `web/app/admin/config/page.tsx`). Los estados y sus textos no son parámetros.
10. **Copy.** Pasa el lint de `web/lib/copy.ts`. Textos propuestos: «Seguimiento», «Estado», «Tu nota» (placeholder «Qué hablaste, cuándo es la visita, qué falta revisar»), «Guardar nota». No decir «solo la ves vos»: un admin con service role puede leer la base. Propuesta: «La nota es privada: no se la mostramos al vendedor ni a otros usuarios.»

## Entrega en dos partes

- **(a) Solo web, sin migración.** Selector y nota en la ficha, reglas de estado, diálogo de compra, Guardados con filtro, nota y select. Funciona con el esquema de hoy (la columna `note` y los estados ya existen). Se puede publicar sola.
- **(b) SQL.** Migración (vista con `note`, filtros nuevos, `search_follow_counts`, CHECK, `app_config`), después `npm run gen:types`, y recién entonces las píldoras y la nota en las tarjetas de resultados. **Orden de despliegue: base primero, web después.** La web nueva contra la base vieja haría que los filtros nuevos caigan en el `else` de `search_results` y muestren «Todos» sin avisar; la base nueva con la web vieja es inocua.

## Efecto en `v_validation_criteria`

Hoy la UI web no puede llegar a esos estados, así que los criterios 3 y 5 solo se mueven con datos históricos. Al habilitar el selector para todos, **marcar «Contactado» cuesta un click**: el criterio 5 (umbral 3 usuarios) se va a cumplir sin que signifique intención real de compra, y el 3 sube marginalmente (`saved` incluye esos estados).

- El diseño **no toca la vista** en este ítem: separar el cambio de producto del cambio de la regla con la que Juan mide la validación.
- Antes de desplegar (a), con OK de Juan, guardar una captura de solo lectura de los valores de los seis criterios, para tener la línea de base.
- Propuesta a decidir (abajo): desde el despliegue, el criterio 5 cuenta solo `visit_scheduled` y `purchased`, y `contacted` pasa a ser una métrica propia en `/admin`. Es otra migración, con su pgTAP (`f6_metrics_test.sql` fija los valores de los seis criterios y habría que actualizarlo).

## Validación y operación

- **pgTAP** (`supabase/tests/x01_tracking_test.sql`, se corre con `npx supabase test db`): A no ve ni modifica las filas de B, y no puede insertar con el `user_id` de B (42501); nota de más de 2000 caracteres rechazada (23514); `match_cards.note` solo trae la nota propia; `search_results` con los tres filtros nuevos, incluida una publicación `gone`; `search_follow_counts` coincide con los filtros; con un usuario `free` enforced, los filtros nuevos respetan el tope de 50 (ver `free_result_quota_test.sql`). Los asserts actuales de `f4_web_test.sql:85-87` y de `free_result_quota_test.sql:25` deben seguir verdes sin cambios.
- **vitest** (`npm test`): ampliar `web/lib/listing-interactions.test.ts` (no baja desde `purchased`; Guardar no baja `contacted`; `setNote`: trim, vacío a null, tope desde config, evento sin contenido, fallo de escritura sin refresh); tests de componente del bloque Seguimiento (opciones, diálogo de descarte, diálogo de compra llama a `recordPurchase`); Guardados con `?e=`; página de resultados con y sin `search_follow_counts`; `copy.test.ts`.
- **Playwright**, proyectos `desktop` y `mobile` (375 px): cambiar el paso 5 de `acceptance.spec.ts` (hoy afirma que el selector y «Compré este vehículo» no existen) y un spec nuevo `web/e2e/tracking.spec.ts`: cambiar a Contactado en la ficha y leer la fila en la base, guardar una nota, ver la nota en Guardados, filtrar por estado en Guardados y en resultados, `expectNoHorizontalScroll` en las tres pantallas. Hace falta sembrar avisos en `web/e2e/seed.ts`.
- **Python:** correr `python -m tools.test_db` para confirmar que nada del worker (`watchlist_queue`, `test_availability_postgres.py`) cambió.
- **Antes de tocar `web/`:** leer `web/CLAUDE.md` → `AGENTS.md` y la guía correspondiente en `node_modules/next/dist/docs/` (Next 16). Para escribir este diseño no hizo falta y **no lo hice**: es la primera tarea del plan.
- **Operación.** Sin cambios de worker: no hay reinicio ni `wait_idle`. La migración a producción solo con OK de Juan, en transacción, con la versión exacta, releyendo antes `max(version)` (la última conocida es `20261118130000`; la nueva va por encima, p. ej. `20261119120000_x01_tracking.sql`, nombre provisorio). `graphify update .` al terminar. Rollback: revertir la web; en SQL, `create or replace` de vuelta a las definiciones de 20261013/20261030, `drop function search_follow_counts` y `drop constraint` del CHECK. Las notas guardadas quedan inertes.

## No verificado

- Datos de producción: cuántas filas tienen `note` no nula y su largo máximo (el `validate constraint` puede fallar si hay alguna de más de 2000; chequear antes, solo lectura, con OK); valor vivo de `validation_criteria.outcome_min_users`; cuántos usuarios hoy cuentan en el criterio 5.
- Que `default privileges` de Supabase den execute a `authenticated` en funciones nuevas (por eso el `grant` explícito).
- Si algún conector o job usa el evento `vehicle_purchased` (en `web/lib` y `worker/` no lo encontré; no revisé el resto).
- Cómo queda el layout del select dentro de `ListingCard` a 375 px: se ve recién en Playwright.
- Texto de Privacidad y Términos sobre las notas: no lo redacto, depende de Juan (ver abajo).

## Riesgos

- **Métrica de validación inflada** por el click barato de «Contactado» (arriba).
- **`record_purchase` sin deshacer**: un click equivocado en «Comprado» queda. Lo mitiga el diálogo de confirmación y que sea explícito que es terminal.
- **`search_results` ya se redefinió 3 veces**: copiar exactamente 20261013 y cambiar solo el `case`; PAR-03 y PRO-02 tocan esas mismas piezas después (el plan serializa X-01 → PAR-03 → PRO-02).
- **Escritura directa por PostgREST** de cualquier estado o nota. Es dato propio y no cambia nada para otros usuarios; endurecerlo (trigger que exija `record_purchase` para `purchased`) queda fuera.
- **Fricción de despliegue** web/base (ver orden en «Entrega»).

## Decisiones que necesita de Juan

1. ¿Reactivar «Comprado» con `recordPurchase` desde el selector? Propuesto: sí, con precio y fecha opcionales. Hoy un test afirma que ese botón no existe (retiro del MVP), así que necesito tu confirmación explícita.
2. ¿Criterio 5 de `v_validation_criteria` sin `contacted` desde el despliegue (solo `visit_scheduled` y `purchased`), con `contacted` como métrica aparte? Propuesto: sí, en una migración separada. Alternativa: dejarlo igual y medir con la línea de base.
3. Largo de la nota: propuesto 500 caracteres (`listing_tracking.note_max_chars`).
4. ¿Select de estado dentro de cada tarjeta de Guardados (propuesto) o solo en la ficha?
5. ¿Las tres píldoras nuevas en resultados siempre visibles con su conteo (propuesto, para que se descubra la función) o solo cuando hay alguna publicación en ese estado?
6. ¿«Comprado» terminal en la UI en v1 (propuesto) o hay que construir ya un «deshacer»?
7. Texto del bloque de nota y de Privacidad/Términos sobre las notas: los redactás vos o con quien corresponda; no invento texto legal. Propuesta de microcopy en el punto 10 del diseño.
8. Línea de base de la métrica: ¿OK para una lectura de solo lectura en producción antes de desplegar (a)?

## Siguiente paso

Con tu aprobación escribo el plan en `docs/superpowers/plans/2026-10-29-x01-seguimiento.md` (tareas `- [ ]` con los comandos de prueba exactos; primera tarea: leer `AGENTS.md` de la web) y abro la rama `claude/x01-seguimiento`. Se entrega primero (a) y, con tu OK para aplicar la migración, (b).

# PRO-01 · Solo particulares y mensaje listo (sin push)

Ítem PRO-01 del [backlog de producto](../../BACKLOG_PRODUCTO_2026-10.md) y Fase 2, fila 2, del [plan por fases](../../PLAN_FASES_BACKLOG_PRODUCTO_2026-10.md) (secciones 4, 5 y 8). Estado: borrador para Juan; nada implementado. Plan de ejecución: [2026-10-31-pro01-contacto.md](../plans/2026-10-31-pro01-contacto.md). Rama `claude/pro01-contacto`, sale de `main` en `28e439d` (con F-02 y PAR-01).

## Alcance

Dos pasos, se pueden desplegar juntos o por separado:

1. **Filtro estricto de vendedor (solo Pro).** `filters.seller_types` en el formulario estructurado, el asistido y la edición; lo aplica `matching.py` como hard filter con `effective_seller`; el vendedor sin dato es `unknown` (pasa y baja el score). El plan Particular conserva la preferencia blanda de hoy.
2. **Mensaje listo para mandar.** Mensaje de 3–4 líneas armado con una plantilla (por defecto o la del usuario en Ajustes, `profiles.contact_template`, con lint al guardar) y las preguntas del aviso. En la ficha: botón «Copiar» y link `mailto:` sin destinatario. En el email de oportunidad Pro: bloque con el texto.

**Fuera de alcance:** push (requiere F-04). Nunca hay envío automático ni link a un teléfono, WhatsApp o email del vendedor: Ese Auto no los tiene.

## Estado actual (verificado en el repo, `28e439d`)

- **Hard filters.** Resultado `ok | fail | unknown`. `match()` descarta solo con `fail`; `unknown` nunca descarta (`worker/intelligence/matching.py:1-8, 27-72, 395-399`). `evaluate()` arma el dict de checks (`matching.py:373-392`); `_source` (`285-291`) es el modelo más cercano.
- **Preferencia blanda.** `preferences.seller_type` (`private | dealer`) con `effective_seller`; clave de razón `seller_type`; soft `unknown` si no hay dato (`matching.py:349-355`). `effective_seller` cuenta `dealer_inferred` como `dealer` (`worker/intelligence/seller.py:19-35`; gemelo web `effectiveSeller`, `web/lib/seller.ts:8-33`).
- **Score.** `match_component` resta `unknown_penalty` (0,15) por cada hard `unknown` (`scoring.py:89-101`, `config.py:33`). `FILTER_NAMES` no tiene vendedor (`copy.py:107-109`).
- **Perfiles en el worker.** Todos los caminos (crawl, rematch, rescore, sin modelo, listado) leen un solo `_SELECT` (`worker/db/repos/profiles.py:26-74`). `low_results` tiene su propia SQL (`worker/db/repos/low_results.py:23-37`); `preview_search` (última versión `20261115120000_multi_location.sql:25-121`) no conoce el vendedor.
- **Plan.** `plan_feature(user, key)`: true para admin o si `plan_limits_for(user)->'limits'->>key = 'true'`; ignora `plan_limits.enforced` (`20261025120000_pro_threshold_export.sql:27-36`). Modelo a seguir: `threshold_alerts`, que la web descarta para no-Pro y el worker vuelve a filtrar al leer (`notifications.py:18-21`). `total_cost` no sirve como «es Pro»: está prendido en `pass` y `free` (`20261127120000`).
- **Bypass.** `authenticated` tiene UPDATE sobre `search_profiles.filters` (`20261007120000_ese_auto_commercial.sql:131-134`). Un control solo en la web no alcanza.
- **Rematch al editar.** `matchingChanged` compara filters/preferences/origen → `rematch_requested_at`; el rematch usa `backfill=True` (no notifica) y el rescore borra los matches que dejan de cumplir (`actions.ts:208-222`, `pipeline/rematch.py`, `pipeline/rescore.py:48-83`). **Ya cumple** «los que dejan de cumplir no se re-notifican».
- **Formulario.** Un select «Vendedor» con la pista «Preferido» y `SELLER_FORM_HINT` (`search-form.tsx:704-720`, `lib/copy.ts:116-120`); `seller.spec.ts:54-66` lo fija. Las features de plan llegan por `loadFormData` (`form-data.ts:10-31`). El asistido solo produce `seller_type` (`worker/llm/schemas.py:26`, `web/lib/assisted.ts:248`) y autoguarda un borrador único sin revisión (`assisted-search.tsx:200-241`).
- **Preguntas.** `seller_questions()` arma el texto completo y queda en `matches.seller_questions` (`seller_questions.py:78-81`, `engine.py:57`); `question_texts()` devuelve solo las específicas (sin saludo/disponible/titular), máx. 3 (`seller_questions.py:84-94`), y es lo que usa el email H-01. El saludo no nombra el auto. Tests fijan el formato actual (`test_intelligence.py:361-372`, `test_intelligence_postgres.py:427`, `acceptance.spec.ts:171`).
- **Ficha.** `<SellerQuestions>` con «Copiar mensaje» y la nota «Ese Auto no contacta al vendedor…» (`components/app/seller-questions.tsx:11-49`); fallback `BASE_SELLER_QUESTIONS`. `listings` no tiene teléfono ni email.
- **Ajustes.** `profiles` con UPDATE por columna (`20260927120100_rls.sql:36-43`, `20261001120000_f4_web.sql:27`). `useSave()` convierte un error lanzado en un toast genérico (`settings-forms.tsx:15-27`).
- **Copy lint.** Web: solo un test de vitest (`lib/copy.test.ts:10-36`); no hay función de runtime. Worker: AST sobre `worker/intelligence/*.py` (`test_intelligence_copy.py`) y casos renderizados (`test_notifications_templates.py:134-145`).
- **Eventos.** `track()` sin lista cerrada (`lib/events.ts`). La única lista es `human_events` en `admin_decision_metrics`, última definición `20261122120100`.
- **Email.** El gating por plan es por columna `plan_feature(...)` en `profile_audiences` (`notifications.py:20-42`). El bloque H-01 va después de `c.lines` y antes del botón (`email_html.py:190-193`, `templates.py:399-400`); Telegram y bandeja no leen `c.questions`. 8 de 11 snapshots heredan `OPPORTUNITY.payload` (`notification_fixtures.py:95-99`).

## Decisiones de Juan (sección 8 del plan)

- El filtro estricto es **solo Pro** (`plan_feature('seller_filter')`, clave nueva en `plan_limits`). Particular conserva la preferencia blanda.
- Por F-02, `dealer_inferred` **cuenta como agencia**: el filtro ofrece «Particulares» y «Agencias (incluye posibles agencias)» y lee `effective_seller`.
- Vendedor sin dato = `unknown`: pasa, baja el score y la UI lo explica.
- Mensaje corto, de vos, cordial y directo, 3–4 líneas con las preguntas del aviso. Plantilla editable en Ajustes con lint. Solo copiar y `mailto:`. Bloque en el email de oportunidad Pro.
- Eventos `seller_filter_set` y `contact_message_copied`. Sin bump de `SCORING_VERSION` (el único, `f2-v5-seller-margin`, ya está desplegado y lo reutiliza PRO-02).

## Decisiones de diseño

1. **Forma.** `filters.seller_types: ["private"] | ["dealer"]`. Se guarda como array por compatibilidad con el backlog, pero la UI elige uno solo (ambos = sin filtro, no se guarda). No se guarda `dealer_inferred`: `["dealer"]` lo incluye vía `effective_seller`. Una tercera opción que nadie elige solo agrega estado.
2. **Hard check `seller`** (clave distinta de la blanda `seller_type`, para no chocar en `match_reasons`). `None` → `UNKNOWN`; `effective_seller ∈ seller_types` → `OK`; si no → `FAIL`. Solo corre si `profile["seller_filter"]` es true; si no, devuelve `None` (filtro ausente).
3. **Gating en lectura, siempre.** `_SELECT` y la SQL de `low_results` suman `public.plan_feature(sp.user_id,'seller_filter') AS seller_filter`, que `_to_alert` pasa al dict del perfil. Cubre el bypass por PostgREST y el downgrade con filtro guardado. Sigue la semántica de `threshold_alerts`: Pro-only también durante el piloto (no mira `enforced`). **No** se agrega rechazo por plan en `enforce_plan_features`.
4. **Sin doble conteo.** Si el hard `seller` aplica, `_preferences` omite la blanda `seller_type`. Perfiles sin `seller_types` (todos los de hoy) puntúan igual: el `unknown_penalty` ya existe por hard filter y la fórmula no cambia. **Sin bump, sin rescore masivo.**
5. **Validación de forma en la base.** `search_filters_problem` (redefinida desde `20261030120000:165-176`) suma: `seller_types`, si está, es un array de 1 elemento en `('private','dealer')`. Rechaza basura escrita por API.
6. **Formulario (Pro).** El campo «Vendedor» sigue siendo el mismo select (label y opciones intactas: no rompe `seller.spec.ts`). Debajo, solo con `sellerFilter`, un checkbox «Solo este tipo de vendedor». Con el check: se guarda `filters.seller_types = [valor]` y no `preferences.seller_type`; la pista cambia a «Descartamos los otros. Si la publicación no dice quién vende, el aviso pasa con menos puntaje.» y para agencias se suma «Incluye posibles agencias.». En el resumen de la búsqueda, fila «Vendedor: Solo particulares» / «Solo agencias (incluye posibles agencias)». Las opciones del select para Pro se rotulan «Particulares» y «Agencias (incluye posibles agencias)»; para Particular quedan como hoy. Envuelve en 375 px (texto en bloque, sin Segmented).
7. **Formulario (no Pro).** Sin control nuevo ni upsell en el formulario (patrón del umbral, `search-form.tsx:936-943`). Si la búsqueda ya tiene `seller_types` (bajó de plan), el resumen y el formulario muestran «Filtro estricto: solo Pro. No se aplica en tu plan.» y la acción **conserva** el valor guardado (no lo borra ni lo cambia): no hay rematch espurio y vuelve a valer si recupera Pro.
8. **Acción del servidor.** `my_plan_feature('seller_filter')` en el `Promise.all` de `save()`. Sin la feature, `seller_types` del input se ignora y se copia el guardado. Con la feature, se valida con zod. `seller_filter_set {profile_id, seller_types, mode}` se registra en el alta con valor y en la edición cuando cambia (incluye pasar a vacío). El rematch ya lo dispara `matchingChanged`.
9. **Asistido.** Para Pro, `draftToValues(..., sellerFilter)` convierte `seller_type` del LLM en filtro estricto y el borrador muestra la nota «Solo particulares (filtro estricto). Podés cambiarlo editando la búsqueda.». El worker (schema, prompt, `drafts.py`) no cambia. Ver pregunta 2.
10. **Otros caminos.** `preview_search` (redefinida desde `20261115120000`, migración sola) aplica `seller_types` solo si `plan_feature(auth.uid(),'seller_filter')`, con la misma regla de `effective_seller` (`seller_type='dealer' or dealer_inferred`) y dejando pasar el null. `update_alert` de Telegram preserva `filters.seller_types` al rearmar filters. `tools/explain_match.py` lee el flag igual que `_SELECT`.
11. **Cambio de plan.** No se fuerza rematch. Al bajar, el filtro deja de excluir avisos nuevos; los excluidos antes no aparecen. Al subir, el rescore nocturno borra los que no cumplen y los nuevos ya filtran. Ver pregunta 3.
12. **Mensaje: forma.** Una función pura por lado, gemelas (`worker/intelligence/contact_message.py`, `web/lib/contact-message.ts`), con un JSON dorado compartido (`worker/tests/fixtures/contact_message_cases.json`, lo leen pytest y vitest), como en PAR-01. Entrada: plantilla (o null), listing (`model`, `year`, `title`) y preguntas específicas.
13. **Plantilla.** Marcadores `{auto}` y `{preguntas}`; uno por línea. Por defecto:
    ```
    Hola, vi tu {auto} publicado.
    {preguntas}
    ¿Cuándo se puede ver?
    ```
    `{auto}` = `«{modelo} {año}»` (p. ej. «Fiesta 2017»); sin modelo, «auto». `{preguntas}` = «¿Lo seguís teniendo?» + la primera pregunta específica (`question_texts(limit=1)`), o «¿Sos titular?» si no hay ninguna: siempre dos líneas, así el mensaje por defecto queda en 4. Ejemplo: «Hola, vi tu Fiesta 2017 publicado. / ¿Lo seguís teniendo? / ¿Tenés historial de services? / ¿Cuándo se puede ver?». Se reutilizan los textos de `QUESTION` sin reescribirlos; `seller_questions()` y `question_texts()` no cambian (tests y `matches.seller_questions` intactos).
14. **Preguntas en la ficha.** Columna nueva `matches.contact_questions text[]` (las específicas, `question_texts(limit=3)`), que escribe `upsert_scored` junto a `seller_questions`. Evita parsear el texto armado o portar `question_keys` a TS. Filas viejas: null → `{preguntas}` cae en «¿Lo seguís teniendo? ¿Sos titular?» hasta el próximo rescore. La ficha usa el `best` de hoy; sin match, el mismo fallback.
15. **Lint de la plantilla al guardar.** `lintContactTemplate()` en `web/lib/copy.ts`, que reusa `FORBIDDEN_TERMS` y la regex de `copy.test.ts` (el test pasa a usar el helper, para que CI y runtime coincidan). Reglas: máx. 500 caracteres y 6 líneas; solo `{auto}` y `{preguntas}` como marcadores; sin términos prohibidos; sin URLs ni números de 7+ dígitos (no se insertan contactos). Vacía = volver a la plantilla por defecto (se guarda null). Error devuelto como `{error}` con mensaje específico, no lanzado. CHECK en la base: `char_length(contact_template) <= 500`. El worker no relintea: renderiza lo guardado escapado.
16. **Ajustes.** Card nueva «Mensaje para vendedores» en `/app/settings`: textarea con la plantilla (o la por defecto como placeholder), vista previa con un auto de ejemplo, «Guardar» y «Volver al mensaje sugerido». Todos los planes (ver pregunta 1). Evento `contact_template_saved {custom}`.
17. **Ficha.** `SellerQuestions` suma arriba «Mensaje listo para mandar» con el texto, «Copiar» (portapapeles) y «Abrir en tu correo» (`mailto:?subject=<auto>&body=<mensaje>`, sin destinatario). Se mantiene la nota «Ese Auto no contacta al vendedor: vos decidís si mandarlo.» y se suma «Mandalo desde la publicación» con el link existente (`outboundHref`). El bloque «¿Qué le pregunto al vendedor?» con la lista completa sigue igual (`acceptance.spec.ts:171`). Evento `contact_message_copied {listing_id, via: 'clipboard'|'mailto', custom_template}` por acción de servidor con zod.
18. **Email Pro.** Clave nueva `plan_limits.pro.contact_email` (dedicada; ni `total_cost` ni `seller_filter` sirven de proxy). `profile_audiences` suma `plan_feature(sp.user_id,'contact_email') AS contact_email` y `p.contact_template`. `on_matches` arma `payload.contact_message` (texto ya renderizado) solo si `_opportunity(c)` y `a.contact_email`. `Content.contact_message` (no en `c.lines`: Telegram y bandeja no cambian). Texto y HTML: después de las preguntas H-01 y antes del botón, título «Mensaje listo para mandar», el texto escapado línea por línea y la nota «Copialo y mandalo desde la publicación. Ese Auto no contacta al vendedor.». Con el bloque, se omite `QUESTIONS_FOOTER` (sería redundante). Sin `mailto` en el email. Payloads viejos y planes sin la clave: byte-idénticos. Las oportunidades Pro que caen en el digest (por umbral) no llevan bloque, igual que hoy con las preguntas.
19. **Métricas.** `admin_decision_metrics` (redefinida desde `20261122120100`, migración sola) suma `contact_message_copied` y `seller_filter_set` a `human_events`.

## Migraciones (todas > `20261127120000`)

- `20261128120000_pro01_seller_filter_contact.sql`: `plan_limits.pro.seller_filter = true` y `plan_limits.pro.contact_email = true` (solo si faltan; `jsonb_set` como `20261025120000:14-16`); `profiles.contact_template text` con CHECK de largo y `grant update (contact_template) on public.profiles to authenticated`; `matches.contact_questions text[]`; `create or replace search_filters_problem` con la regla de `seller_types`. `supabase/seed.sql` se edita a mano (las dos claves en `pro`).
- `20261128120100_pro01_preview_seller.sql`: `preview_search` desde `20261115120000`, con el filtro.
- `20261128120200_pro01_decision_metrics.sql`: `admin_decision_metrics` desde `20261122120100`, con los dos eventos.

## Riesgos

- **Bypass o downgrade:** cubiertos por el gating en lectura; un test `-m db` lo fija (Particular con `seller_types` guardado sigue recibiendo agencias).
- **Caminos que arman perfiles por fuera de `_SELECT`** (`low_results`, `preview_search`, `explain_match`): si falta uno, conteos y diagnósticos no coinciden con el matching real. Hay un test por cada uno.
- **Telegram** rearma filters y perdería `seller_types`: test de `update_alert`.
- **Índice único de búsquedas activas** compara filters: dos búsquedas iguales salvo `seller_types` pasan a ser distintas. Es lo buscado; `sameActiveSearch` lo respeta.
- **Copy lint:** cualquier literal nuevo en `app/`, `components/` o `worker/intelligence/` pasa por el lint; los textos de este diseño no usan términos prohibidos.
- **Snapshots:** el bloque depende de una clave nueva del payload; solo se agrega `opportunity_contact_message`. Los 11 existentes no cambian.
- **Plantilla libre:** se escapa en HTML y se codifica en el `mailto:`; el lint impide URLs y teléfonos.

## Qué NO cambia

`SCORING_VERSION`, la fórmula de score, `seller_questions()`/`question_texts()` y `matches.seller_questions`, el prompt y schema del LLM, `enforce_plan_features`, Telegram y la bandeja web, el email de Particular y Free, `/app/listings/[id]/out`.

## Operación y rollback

- Orden: migraciones (con OK de Juan, cada una en una transacción con su versión) → worker (`wait_idle`) → web.
- Rollback rápido sin deploy: `plan_limits.pro.seller_filter = false` apaga el filtro en el worker al instante (los matches excluidos vuelven con el próximo rescore o edición); `pro.contact_email = false` apaga el bloque del email.
- Rollback de código: revert de web y worker; las columnas nuevas quedan sin uso.

## Tests

- Worker: `matching` con `seller_types` × {private, dealer, `dealer_inferred`, null} × {flag on, off}; preferencia blanda omitida con hard activo; score igual para perfiles sin la clave; `FILTER_NAMES`. Gemelo del mensaje contra el JSON dorado. `-m db`: `plan_feature('seller_filter')` y `contact_email` por plan (modelo `test_commercial_postgres.py:306-320`), `_SELECT`/`low_results`/`update_alert`, `contact_questions` escrito por `upsert_scored`. Notificaciones: payload Pro/no-Pro (patrón `PayloadTests`), snapshot nuevo, Telegram e inbox sin cambios, lint.
- pgTAP: claves de plan, `search_filters_problem`, grant y CHECK de `contact_template`, `preview_search` con y sin feature, `admin_decision_metrics`.
- Web: `search-form` (`toFilters`/`fromProfile`/conservar en downgrade), `draftToValues`, `lintContactTemplate`, `contact-message` contra el JSON dorado, «no-Pro nunca ve el checkbox».
- e2e nuevo `pro01-contact.spec.ts` (desktop y mobile): Pro crea «solo particulares», ve la explicación, edita y el resumen cambia; Ajustes guarda una plantilla, rechaza una con término prohibido y la ficha copia el mensaje y arma el `mailto:` sin destinatario; sin scroll horizontal. Más `acceptance`, `seller` y `total-cost` en verde.

## Preguntas para Juan

1. **¿El mensaje listo en la ficha y la plantilla en Ajustes son para todos los planes o solo Pro?** Tu decisión dice «bloque en el email de oportunidad Pro», pero no aclara la ficha. Recomiendo **todos los planes en la ficha y Ajustes** (hoy todos copian preguntas y es lo que acerca el contacto) y **el bloque del email solo Pro** (`plan_limits.pro.contact_email`, apagable desde `/admin/config`).
2. **En el asistido, un Pro que escribe «particular» o «sin agencia»: ¿filtro estricto o preferencia?** Recomiendo **estricto**, con la nota visible en el borrador («Solo particulares (filtro estricto). Podés cambiarlo editando la búsqueda.»): es el dolor de PRO-01. El autoguardado no tiene revisión, por eso la nota.
3. **Cambio de plan con filtro guardado.** Recomiendo **no forzar rematch**: al subir a Pro, el filtro se aplica a los avisos nuevos y el nocturno limpia los existentes; al bajar, deja de excluir lo nuevo y el valor queda guardado (inactivo, con aviso «solo Pro») por si vuelve. La alternativa (marcar `rematch_requested_at` en cada cambio de plan) toca webhook de pagos, admin y vencimientos, que hoy no saben de búsquedas.

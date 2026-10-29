# H-01 · Preguntas para el vendedor en el email de oportunidad

Ítem del [backlog de producto](../../BACKLOG_PRODUCTO_2026-10.md) (H-01) y Fase 1 del [plan por fases](../../PLAN_FASES_BACKLOG_PRODUCTO_2026-10.md). Estado: **borrador para que Juan lo apruebe**; nada implementado.

Alcance: la landing (`web/app/page.tsx:34`) promete «por email, con el precio comparado y las preguntas para hacerle al vendedor», pero el email de oportunidad solo lleva a la ficha. Se agrega al email un bloque corto con las preguntas más útiles de ese aviso. No cambia el score, los comparables ni quién recibe qué; Ese Auto sigue sin contactar vendedores.

## Qué existe hoy (verificado en el repo)

- `matches.seller_questions` es un solo texto listo para pegar («Hola, ¿cómo estás? ¿Lo seguís teniendo? ¿Sos titular? …»), armado por `seller_questions()` en `worker/intelligence/seller_questions.py` a partir de claves (`question_keys()`) y del diccionario `QUESTION` de `intelligence/copy.py`. No se puede cortar «las 3 primeras» desde el texto guardado.
- `notifications/service.payload()` solo guarda `listing`, `match` (score, level, `diff_pct`), `red_flags` y `profile_name`. Las queries de `db/repos/notifications.py` no seleccionan `seller_questions`.
- `templates.content()` arma `Content` (líneas y notas); `email_html.render()` solo dibuja `lines`, `notes`, imágenes y botón. Telegram y el inbox web usan el mismo `Content`.
- Snapshots en `worker/tests/snapshots/notifications/` (`opportunity.txt`, `new_match.txt`).

## Decisión de diseño

1. **Qué preguntas.** Las preguntas **específicas** del aviso, sin el saludo: se excluyen `greeting`, `available` y `holder` (son comunes a todos los avisos y no aportan en un resumen). Máximo 3, en el orden en que ya genera `question_keys()` (red flags y datos faltantes primero). Si el aviso no tiene ninguna específica, el bloque no aparece. El mensaje completo para pegar sigue viviendo solo en la ficha.
2. **De dónde salen.** Función nueva `question_texts(listing, flags, *, timing_belt, now, limit=3)` en `seller_questions.py`, que reutiliza `question_keys()` (misma lógica, sin duplicarla) y devuelve los textos de `QUESTION`. Se llama al armar el payload, no se agrega columna ni migración, y los avisos viejos funcionan igual. El `SCORING_VERSION` no cambia.
3. **Payload.** Clave nueva opcional `questions: list[str]` en el payload de `new_match` y `opportunity`. Los payloads ya guardados no la tienen: `templates.content()` la trata como lista vacía y no rompe.
4. **Render.** `Content` suma `questions: list[str]`; el email (HTML y texto) lo muestra como bloque «Preguntas para hacerle al vendedor» entre las líneas de precio y las notas. **Telegram, el inbox web y el digest no cambian** (la promesa de la landing es por email; el digest agrupa muchos avisos).
5. **Plan y canal.** Sin gating: lo reciben todos los planes, porque es lo que ya promete la landing.
6. **Copy.** Todas las preguntas ya pasan el lint de `copy.py`; el encabezado y la línea de cierre del bloque se agregan a `copy.py` para que el lint también los cubra.

## Datos que necesita y riesgo conocido

`question_keys()` lee del aviso: `description_facts`, `description`, `year`, `mileage_km`, `transmission`, `trim`, `price_partial`. `listing_payload()` ya usa `description_facts`, pero las queries de notificaciones podrían no traer `description`, `transmission` o `price_partial`. **Primera tarea del plan:** confirmar qué columnas trae la fila de `listing` en cada punto donde se llama `payload()` (`service.py` líneas ~166 y ~204) y, si faltan, sumarlas a la query en vez de recalcular preguntas con datos incompletos (generaría preguntas de más, como «¿Qué transmisión es?» cuando sí la tiene).

Alternativa descartada: partir el texto guardado de `matches.seller_questions` buscando cada frase de `QUESTION`; es frágil si el texto se pule con el LLM (`polish_questions`) y no distingue específicas de genéricas por sí sola.

## Validación y operación

- Tests de `question_texts`: sin específicas (lista vacía), 1, 3 y más de 3 (corta en 3); orden estable; no incluye saludo, disponibilidad ni titular; mismo conjunto de claves que `question_keys()`.
- Snapshots nuevos y actualizados: `opportunity.txt` y `new_match.txt` con y sin preguntas; un caso con payload viejo (sin la clave) que debe renderizar idéntico al snapshot anterior.
- Lint de copy sobre el encabezado y el cierre; chequeo de que ningún texto contiene los términos prohibidos.
- Sin migración, sin cambio de `SCORING_VERSION`, sin llamadas LLM. Se despliega con el worker (`wait_idle` antes de reiniciar, con OK de Juan).
- Rollback: quitar `questions` del payload; los emails vuelven al formato actual sin tocar datos.

## Decisiones que necesita de Juan

1. ¿Sumar las preguntas al email (este diseño) o corregir la landing y dejar el email como está? El diseño asume lo primero.
2. ¿Cuántas preguntas? Propuesto 3.
3. ¿Se omite el saludo y las genéricas (propuesto) o se incluyen «¿Lo seguís teniendo?» y «¿Sos titular?»?
4. Texto del encabezado: propuesto «Preguntas para hacerle al vendedor» y cierre «Podés copiar el mensaje completo desde la ficha del auto.».
5. ¿Telegram queda sin el bloque (propuesto)?

## Siguiente paso

Con tu aprobación escribo el plan en `docs/superpowers/plans/2026-10-29-email-seller-questions.md` (tareas `- [ ]` con los comandos de prueba exactos) y abro la rama `claude/email-seller-questions`.

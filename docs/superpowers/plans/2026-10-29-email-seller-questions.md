# H-01: preguntas para el vendedor en el email

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Track the steps below during implementation.

**Goal:** Que el email de nuevo match y de oportunidad lleve hasta 3 preguntas específicas del aviso, como promete la landing. Diseño aprobado: [2026-10-29-email-seller-questions-design.md](../specs/2026-10-29-email-seller-questions-design.md).

**Architecture:** `seller_questions.py` expone `question_texts()` sobre la misma lógica de `question_keys()`. `NotificationService.on_matches` la llama al armar el payload y guarda `questions` (opcional). `templates.content()` lo copia a `Content.questions`; solo el email (texto y HTML) lo dibuja. Telegram, inbox web y digest no cambian. Sin migración y sin cambio de `SCORING_VERSION`.

**Tech Stack:** Python 3.12, unittest/pytest (`pytest` desde la raíz; `pythonpath = worker`).

## Alcance y decisiones aprobadas

- Máximo 3 preguntas, solo las específicas: se excluyen `greeting`, `available` y `holder`. Sin específicas, no hay bloque.
- Solo kinds `new_match` y `opportunity` (ambos salen de `on_matches`). `price_drop` y `listing_gone` no llevan preguntas.
- Encabezado «Preguntas para hacerle al vendedor»; cierre «Podés copiar el mensaje completo desde la ficha del auto.».
- Verificado en el repo: la fila `listing` que recibe `on_matches` viene de `rows_for_scoring` (`SELECT l.*, vc.timing_belt`), así que ya trae `description`, `transmission`, `price_partial`, `trim` y `timing_belt`. No hace falta tocar queries. Las `red_flags` de la evaluación son dicts `{id, text, severity}` (`RedFlag.to_json`).
- Payloads viejos sin `questions` deben renderizar igual que hoy.
- No aplicar nada a producción ni reiniciar el worker sin OK de Juan (`wait_idle` antes).

Rama: `claude/email-seller-questions`. Comandos de prueba (desde la raíz del repo): `python -m pytest worker/tests/test_intelligence.py -k SellerQuestion -q` y `python -m pytest worker/tests/test_notifications_templates.py worker/tests/test_notifications_engine.py worker/tests/test_notifications_email_media.py -q`.

## Task 1: `question_texts()`

Files: `worker/intelligence/seller_questions.py`, `worker/tests/test_intelligence.py` (clase `SellerQuestionTests`).

- [ ] Escribir tests que fallen: sin específicas devuelve `[]` (auto de 2025, con descripción larga, con km, transmisión y versión); un caso con 1 específica; un caso con más de 3 que corta en 3 y conserva el orden de `question_keys()`; nunca incluye los textos de `greeting`, `available` ni `holder`; acepta flags como `RedFlag` y como dicts `{id,text,severity}`.
- [ ] Implementar `question_texts(listing, flags, *, timing_belt, now, limit=3) -> list[str]`: normaliza flags (si es dict, `RedFlag(**d)`), llama `question_keys()`, filtra las tres claves genéricas, mapea con `QUESTION`, corta en `limit`. No duplicar la lógica de selección.
- [ ] Correr `python -m pytest worker/tests/test_intelligence.py -k SellerQuestion -q` y confirmar que pasa, junto con los tests existentes de la clase.

## Task 2: copy del bloque

Files: `worker/intelligence/copy.py` o `worker/notifications/templates.py` (donde viven las constantes de email, junto a `FINANCEABLE`), `worker/tests/test_notifications_templates.py`.

- [ ] Agregar `QUESTIONS_TITLE = "Preguntas para hacerle al vendedor"` y `QUESTIONS_FOOTER = "Podés copiar el mensaje completo desde la ficha del auto."`.
- [ ] Test: ambas constantes pasan el chequeo de `FORBIDDEN_TERMS` (normalizando con `normalize_text`, igual que el test de copy existente) y no contienen «tasación» ni derivados.

## Task 3: payload

Files: `worker/notifications/service.py`, `worker/tests/test_notifications_engine.py`.

- [ ] Test que falle: `on_matches` con un candidato cuyo `evaluation["red_flags"]` incluye `no_owners` produce un evento cuyo `payload["questions"]` es una lista no vacía de a lo sumo 3 textos; con un aviso sin específicas el payload no tiene la clave `questions`.
- [ ] En `on_matches`, calcular `questions = question_texts(listing, [RedFlag(**f) for f in ev.get("red_flags") or []], timing_belt=listing.get("timing_belt"), now=now or datetime.now(timezone.utc))` y pasarla como `questions=questions or None` a `payload()` (los extras `None` ya se descartan).
- [ ] No tocar `on_listing_events` ni `digest.py`.

## Task 4: render del email

Files: `worker/notifications/templates.py` (`Content`, `content()`, `email()`), `worker/notifications/email_html.py`, `worker/tests/test_notifications_templates.py`, `worker/tests/test_notifications_email_media.py`.

- [ ] Tests que fallen: con `questions` en el payload, el email de texto trae el título y las preguntas, en ese orden, antes de la línea «Ver auto en Ese Auto»; el HTML trae un bloque con título, una línea por pregunta y el cierre, antes del botón; Telegram y `inbox` (la función que arma título, `lines` y `notes`) quedan idénticos a hoy; sin `questions` la salida es idéntica a la actual.
- [ ] Agregar `questions: list[str]` a `Content`; en `content()` asignarlo desde `p.get("questions") or []` solo para `new_match` y `opportunity`.
- [ ] En `email()`: tras `text += c.lines` insertar, si hay preguntas, `["", QUESTIONS_TITLE] + [f"- {q}" ...] + [QUESTIONS_FOOTER]`. En `email_html.render()`: tras el bucle de `c.lines` y antes del botón, un bloque con título en negrita, un `<p>` por pregunta y el cierre en tono atenuado, con los mismos estilos de `MUTED`/`INK` y `_p()`. Escapar con las funciones existentes.
- [ ] Correr los tests de plantillas y de email_media; confirmar que `telegram`/`inbox` no cambiaron.

## Task 5: fixtures y snapshots

Files: `worker/tests/notification_fixtures.py`, `worker/tests/snapshots/notifications/opportunity.txt`, `new_match.txt`.

- [ ] Agregar `questions` a `OPPORTUNITY` (2 preguntas reales de `QUESTION`, por ejemplo `owners` y `vtv`) y dejar `NEW_MATCH` sin la clave para cubrir el payload viejo; sumar un caso `NEW_MATCH_WITH_QUESTIONS` con 3 preguntas a `CASES` solo si se quiere snapshot propio.
- [ ] Regenerar con `UPDATE_SNAPSHOTS=1 python -m pytest worker/tests/test_notifications_templates.py -q`, revisar el diff: solo cambian las secciones «email text» y «email html» de `opportunity`; `telegram`, `telegram buttons`, `email subject` y `new_match` (sin clave) quedan idénticos.
- [ ] Correr el set completo de notificaciones sin `UPDATE_SNAPSHOTS` y confirmar verde.

## Task 6: verificación y cierre

- [ ] `python -m pytest worker/tests -q -m "not db"` verde (los tests `db` requieren una base `*_test` con `python -m tools.test_db`; correrlos solo ahí).
- [ ] Revisar que no aparezcan los términos de `FORBIDDEN_TERMS` en el HTML generado.
- [ ] `graphify update .` desde la raíz.
- [ ] Abrir PR de `claude/email-seller-questions` a `main` con el resumen del cambio. Sin migración, sin deploy: desplegar el worker solo con OK de Juan y `wait_idle` previo.
- [ ] Marcar H-01 como entregado en `docs/BACKLOG_PRODUCTO_2026-10.md` y en el plan por fases al mergear.

## Rollback

Quitar `questions=` de la llamada en `on_matches`; los emails vuelven al formato actual y los payloads ya guardados no se tocan.

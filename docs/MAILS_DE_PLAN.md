# Mails del plan

Son los mails de la fase 2 de [planes](PLANES_2026-10.md), los que llevan a pagar. Los manda el worker por Resend, con su propio registro de envíos. Reemplazan al recordatorio de fin de prueba del 9/10, que pasó a ser el mail 2.2.

| Mail | Cuándo | Estado |
| --- | --- | --- |
| 2.1 Prueba sin coincidencias | 24 h después de activar la prueba, sin ninguna coincidencia nueva desde la activación | Listo |
| 2.2 Fin de la prueba | Al terminar las 72 h, si la cuenta nunca compró | Listo |
| 2.3 Vencimiento de Particular | 5 días antes y el día que vence el pase | Pendiente: su botón «Extender 30 días» necesita 2.4 |
| 2.5 Conteo después de vencer | 7, 14 y 21 días después del vencimiento | Pendiente: falta decidir si se siguen rastreando las búsquedas vencidas |

## Reglas para todos

- **Una sola vez por evento.** `lifecycle_emails` tiene una fila por cuenta, tipo de mail y evento (`unique (user_id, kind, event_key)`). Aunque el worker corra de nuevo o se reinicie, el mismo evento no se vuelve a mandar. Resend también recibe `Idempotency-Key: lifecycle-<id>`.
- **Baja.** Todos llevan el enlace de baja (`/baja?t=…`) y el encabezado `List-Unsubscribe` de un clic. La baja quita `email` de los canales, y sin ese canal ningún tipo se reserva ni se manda. Sin `WEB_BASE_URL` no hay enlace de baja, así que no sale ninguno.
- **Texto.** Tono de la marca, de vos. Nunca «en tiempo real», «todos los portales» ni «el más barato»: un test lo controla. Si un número da 0, la frase que lo menciona no aparece.
- **Por debajo de comparables.** Son las coincidencias que el sistema ya marca como oportunidad (nivel `high`).
- **Horario.** Solo entre `send_from` y `send_until`, hora argentina. Lo que se vuelve pendiente de noche sale a la mañana siguiente.
- **Re-chequeo.** Se revisa quién corresponde dos veces: al reservar y otra vez justo antes de mandar. Si en el medio pagó, se dio de baja o (en 2.1) apareció una coincidencia, la fila queda `skipped` y no sale nada.

## 2.1 Prueba sin coincidencias

- **A quién.** Cuentas en prueba vigente, con una búsqueda activa, a las 24 h de activar la prueba y sin ninguna coincidencia nueva desde entonces. Las coincidencias de los últimos 30 días que se guardan al crear la búsqueda (`is_backfill`) no cuentan como nuevas.
- **Asunto.** «Tu búsqueda de {modelo} todavía no tuvo coincidencias nuevas».
- **Cuerpo.** «En las primeras 24 horas no apareció ningún auto nuevo con tus filtros. Si ampliás años, kilómetros o zona, vas a ver más opciones en lo que queda de la prueba.»
- **Botón.** «Ajustar filtros», a `/app/searches/<id>/edit`.

## 2.2 Fin de la prueba

- **A quién.** Cuentas cuya prueba de 72 h terminó y que nunca compraron (un pago devuelto también cuenta como compra). Tampoco va a quien tiene un checkout en curso o si el checkout está cerrado (`commercial_pilot.enabled = false`). Las condiciones son las del recordatorio anterior.
- **Asunto.** «Terminó tu prueba: encontramos {X} autos para tu búsqueda». Si X da 0, el asunto queda en «Terminó tu prueba».
- **Cuerpo.** «En 3 días encontramos {X} autos para tu búsqueda de {modelo}, y {Y} estaban por debajo de publicaciones comparables. Para seguir recibiendo avisos, Particular sale $15.000 por 30 días, con 3 búsquedas y pago único. Tu historial y tus favoritos quedan guardados.»
  - X son las coincidencias de la búsqueda de la prueba hasta el fin de la prueba; Y, las de nivel `high`.
  - El precio sale de `app_config.pro_offer` y las búsquedas de `plan_limits.pass`. Si la oferta no sirve, la frase nombra Particular sin precio: nunca un precio equivocado.
- **Botón.** «Seguir con Particular», a `/app/pro?plan=pass_30`: la pantalla de planes con Particular elegido, a un clic de Mercado Pago.

## Clics y eventos

- **Clics.** El botón pasa por `/m/<id>` ([ruta](../web/app/m/[emailId]/route.ts)). Esa ruta registra `lifecycle_email_clicked` (con `kind`) y redirige al destino guardado en la fila, que siempre es una ruta del sitio. Las vistas previas de enlaces y los HEAD no cuentan.
- **`lifecycle_email_sent`.** Se registra cuando Resend acepta el mail, con `kind` y `email_id`.
- **`trial_ended`.** Uno por cuenta cuando terminan las 72 h, compre o no. Datos: `results`, `opportunities`, `immediate_alerts_sent`, `converted` y `ended_at`. Las pruebas que terminaron antes de este cambio reciben el suyo en la primera pasada, con su fecha real en `ended_at`.

## Configuración: `app_config.lifecycle_emails`

Se edita desde `/admin/config`. Un valor inválido se reemplaza por su valor por defecto.

| Campo | Por defecto | Qué hace |
| --- | --- | --- |
| `enabled` | `true` | `false` apaga todos los tipos. |
| `kinds` | 2.1 y 2.2 prendidos | Prende o apaga cada tipo. |
| `send_from` / `send_until` | `"09:00"` / `"21:00"` | Horario de envío, hora argentina. |
| `window_hours` | `48` | Plazo para mandar una fila reservada. Pasado ese plazo queda `skipped` (`outside_window`). Tiene que superar la noche sin envíos. |
| `max_per_day` | `30` | Mails reservados por día calendario argentino, entre todos los tipos. Resend gratis permite 100 por día entre alertas y estos mails. |

El worker revisa cada `TRIAL_REMINDER_TICK_SECONDS` (900 s). El nombre se conserva por compatibilidad con el `.env` del VPS.

## Código

- **Migración.** [`20261020120000_lifecycle_emails.sql`](../supabase/migrations/20261020120000_lifecycle_emails.sql): crea el registro, mueve las filas de `trial_reminders` y borra esa tabla.
- **Worker.** [`notifications/lifecycle.py`](../worker/notifications/lifecycle.py) decide cuándo correr y manda; [`db/repos/lifecycle_emails.py`](../worker/db/repos/lifecycle_emails.py) maneja el registro; los textos están en [`notifications/templates.py`](../worker/notifications/templates.py).
- **Tests.** `test_lifecycle_emails_postgres.py` y `test_lifecycle_templates.py`, con snapshots en `tests/snapshots/notifications/lifecycle_*.txt`.

## Verificar en producción

1. Configuración: `select value from app_config where key = 'lifecycle_emails';`.
2. Envíos por tipo: `select kind, status, count(*) from lifecycle_emails group by 1, 2 order by 1, 2;`.
3. Errores: `select * from pipeline_errors where stage = 'lifecycle_email' order by created_at desc;`.
4. Log del worker: líneas `plan emails: N <kind> claimed` y `N sent`, o `plan emails off: …` si falta el canal o `WEB_BASE_URL`.
5. Eventos: `select name, count(*) from events where name in ('trial_ended', 'lifecycle_email_sent', 'lifecycle_email_clicked') group by 1;`.

## Límites conocidos

- **Caídas largas.** Si el worker está caído más de `window_hours`, los eventos de ese lapso se quedan sin mail.
- **Tope diario.** Cuenta reservas, incluidas las que terminan `skipped` o `failed`, y no ve el volumen de alertas que comparte la cuota de Resend.
- **Qué significa `sent`.** Que Resend aceptó el mail; rebotes y quejas no se registran.
- **Duración de la prueba.** Las reservas usan las 72 h de `plan_limits_for`. Si cambia esa duración, hay que revisar `claim_lifecycle_emails`.

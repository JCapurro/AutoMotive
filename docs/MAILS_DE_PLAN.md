# Mails del plan

Son los mails de la fase 2 de [planes](PLANES_2026-10.md), los que llevan a pagar. Los manda el worker por Resend, con su propio registro de envíos. Reemplazan al recordatorio de fin de prueba del 9/10, que pasó a ser el mail 2.2.

| Mail | Cuándo | Estado |
| --- | --- | --- |
| 2.1 Prueba sin coincidencias | 24 h después de activar la prueba, sin ninguna coincidencia nueva desde la activación | Listo |
| 2.2 Fin de la prueba | Al terminar las 72 h, si la cuenta nunca compró | Listo |
| 2.3 Vencimiento de Particular | 5 días antes y el día que vence el pase | Listo |
| 2.5 Conteo después de vencer | 7, 14 y 21 días después del vencimiento, si apareció algo | Listo |

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

## 2.3 Vencimiento de Particular

- **A quién.** Cuentas con Particular vigente y el checkout abierto.
- **Cuándo.**
  - «Te quedan 5 días de Ese Auto»: cuando faltan entre 5 y 4 días.
  - «Hoy vence tu acceso a Ese Auto»: el día calendario argentino del vencimiento.
- **Una vez por vencimiento.** La clave del evento es la fecha de fin del pase. Si se extiende, el fin nuevo tiene sus dos mails y el viejo no manda ninguno: si ya estaba reservado, queda `skipped`.
- **Cuerpo.** «Desde que activaste Particular encontramos {X} autos, {Y} por debajo de comparables. Si todavía no lo encontraste, extendé 30 días más: se suman a tu vencimiento.» El del último día agrega: «Desde mañana dejamos de buscar y de avisarte. Tu historial y tus favoritos quedan guardados.»
  - X cuenta desde el inicio de la cadena de pases (una extensión empieza donde termina el anterior).
  - Si X o Y dan 0, su frase no aparece.
- **Pase que venció de madrugada.** El mail del último día igual sale a las 9, pero sin «Desde mañana dejamos de buscar» ni «se suman a tu vencimiento»: comprar después de vencer cuenta 30 días desde el pago.
- **Botón.** «Extender 30 días», a `/app/pro?plan=pass_30`.

## 2.5 Conteo después de vencer

- **A quién.** Pruebas que terminaron sin compra (un pago devuelto cuenta como compra, igual que en 2.2) y pases Particular vencidos y no renovados. Agencia no está incluida. No sale si la persona compró, se dio de baja o tiene un checkout en curso.
- **Qué se cuenta.** Publicaciones que coinciden con alguna búsqueda pausada por el vencimiento y que cumplen dos condiciones:
  - se vieron por primera vez después del vencimiento;
  - son recientes según la regla de los avisos (`recommended_max_age_days`).

  El worker las evalúa con el mismo motor que las coincidencias, pero las guarda en `expired_search_matches`: no se muestran en la web ni generan avisos. «Por debajo de comparables» corresponde al nivel `high`. La primera pasada de un portal nuevo se toma como historial y no se cuenta.
- **Cuándo.** Los días 7, 14 y 21 después del vencimiento, cada uno durante 24 horas. Son 3 mails como máximo. Si N da 0, ese día no sale nada; si aparece algo más tarde ese mismo día, el mail sale en ese momento.
- **Qué búsqueda.** Si había varias, la que más encontró.
- **Asunto.** «Aparecieron {N} autos nuevos para tu búsqueda de {modelo}». Con uno solo: «Apareció 1 auto nuevo para tu búsqueda de {modelo}».
- **Cuerpo.** «Desde que venció tu acceso aparecieron {N} autos nuevos que coinciden con tu búsqueda, y {M} están por debajo de comparables. Reactivá para verlos.» Si M da 0, la frase termina en «tu búsqueda». No se muestran los autos.
- **Botón.** «Reactivar por $15.000», a `/app/pro?plan=pass_30`. El precio sale de `pro_offer`; si no sirve, el botón dice «Reactivar».
- **Una vez por etapa.** La clave del evento es `<vencimiento>:<día>`. Un vencimiento nuevo, después de otro pase, arranca su propio ciclo.
- **Al reactivar.** Comprar Particular reactiva las búsquedas (2.4). En el siguiente rastreo aparecen las publicaciones que siguen activas.

### El rastreo de esas 3 semanas

Juan aprobó el 14/10/2026 rastrear una vez por día, durante esas 3 semanas, los modelos de las búsquedas vencidas.

- **Modelo que ya rastrea otra búsqueda activa** en ese portal: se cuenta con lo que ya se recolecta, sin cambiar la consulta ni la frecuencia de esa búsqueda.
- **Modelo que no rastrea nadie más:** queda un objetivo `count_only` que corre una vez por día; si falla, reintenta a las 6 horas, no a los 15 minutos de un objetivo activo. Si una búsqueda activa vuelve a pedir ese modelo, el objetivo recupera la frecuencia del portal y corre en el momento.
- **Duración.** 22 días desde el vencimiento: las 3 semanas más el día del último mail.
- **Apagado.** Con `kinds.count_after_expiry = false` se corta también este rastreo.
- **Costo.** No suma plata: el worker corre en el mismo VPS y los portales no cobran. Cada modelo que solo piden búsquedas vencidas agrega una consulta por día y por portal; una búsqueda activa hace decenas por día (Mercado Libre, cada 10 minutos).

## Clics y eventos

- **Clics.** El botón pasa por `/m/<id>` ([ruta](../web/app/m/[emailId]/route.ts)). Esa ruta registra `lifecycle_email_clicked` (con `kind`) y redirige al destino guardado en la fila, que siempre es una ruta del sitio. Las vistas previas de enlaces y los HEAD no cuentan.
- **`lifecycle_email_sent`.** Se registra cuando Resend acepta el mail, con `kind` y `email_id`.
- **`trial_ended`.** Uno por cuenta cuando terminan las 72 h, compre o no. Datos: `results`, `opportunities`, `immediate_alerts_sent`, `converted` y `ended_at`. Las pruebas que terminaron antes de este cambio reciben el suyo en la primera pasada, con su fecha real en `ended_at`.
- **`reactivated_from_count_email`.** Se registra cuando alguien compra Particular sin acceso vigente y su último mail de conteo (2.5) salió en los 30 días anteriores. Datos: `email_id`, `stage` (7, 14 o 21), `clicked` y `days_after_email`. Cada mail cuenta para una sola compra, y una extensión posterior no se vuelve a contar.

## Configuración: `app_config.lifecycle_emails`

Se edita desde `/admin/config`. Un valor inválido se reemplaza por su valor por defecto.

| Campo | Por defecto | Qué hace |
| --- | --- | --- |
| `enabled` | `true` | `false` apaga todos los tipos. |
| `kinds` | Todos prendidos: 2.1, 2.2, 2.3 y 2.5 | Prende o apaga cada tipo. Apagar `count_after_expiry` también corta su rastreo. |
| `send_from` / `send_until` | `"09:00"` / `"21:00"` | Horario de envío, hora argentina. |
| `window_hours` | `48` | Plazo para mandar una fila reservada. Pasado ese plazo queda `skipped` (`outside_window`). Tiene que superar la noche sin envíos. |
| `max_per_day` | `30` | Mails reservados por día calendario argentino, entre todos los tipos. Resend gratis permite 100 por día entre alertas y estos mails. |

El worker revisa cada `TRIAL_REMINDER_TICK_SECONDS` (900 s). El nombre se conserva por compatibilidad con el `.env` del VPS.

## Código

- **Migración.** [`20261020120000_lifecycle_emails.sql`](../supabase/migrations/20261020120000_lifecycle_emails.sql): crea el registro, mueve las filas de `trial_reminders` y borra esa tabla.
- **2.5.**
  - [`20261024120000_count_after_expiry.sql`](../supabase/migrations/20261024120000_count_after_expiry.sql): el conteo, quién se cuenta (`count_after_expiry_searches`), el reclamo del mail y el evento.
  - En el worker: los objetivos `count_only` están en `pipeline/crawl.py` y `db/repos/targets.py`; el conteo de cada tanda, en `count_after_expiry` de `pipeline/scheduler.py`, que guarda con `db/repos/expired_matches.py`.
- **Worker.** [`notifications/lifecycle.py`](../worker/notifications/lifecycle.py) decide cuándo correr y manda; [`db/repos/lifecycle_emails.py`](../worker/db/repos/lifecycle_emails.py) maneja el registro; los textos están en [`notifications/templates.py`](../worker/notifications/templates.py).
- **Tests.** `test_lifecycle_emails_postgres.py` y `test_lifecycle_templates.py`, con snapshots en `tests/snapshots/notifications/lifecycle_*.txt`. El rastreo de 2.5 se prueba en `test_ingest_postgres.py` (`CountAfterExpiryCrawlTests`).

## Verificar en producción

1. Configuración: `select value from app_config where key = 'lifecycle_emails';`.
2. Envíos por tipo: `select kind, status, count(*) from lifecycle_emails group by 1, 2 order by 1, 2;`.
3. Errores: `select * from pipeline_errors where stage = 'lifecycle_email' order by created_at desc;`.
4. Log del worker: líneas `plan emails: N <kind> claimed` y `N sent`, o `plan emails off: …` si falta el canal o `WEB_BASE_URL`.
5. Eventos: `select name, count(*) from events where name in ('trial_ended', 'lifecycle_email_sent', 'lifecycle_email_clicked', 'reactivated_from_count_email') group by 1;`.
6. 2.5, búsquedas que se cuentan ahora: `select * from count_after_expiry_searches();`.
7. 2.5, objetivos diarios: `select source, make, model, query->'count_profile_ids', next_run_at from crawl_targets where active and query->>'count_only' = 'true';`.
8. 2.5, lo contado: `select search_profile_id, access_ended_at, count(*), count(*) filter (where level = 'high') from expired_search_matches group by 1, 2;`.

## Límites conocidos

- **Caídas largas.** Si el worker está caído más de `window_hours`, los eventos de ese lapso se quedan sin mail.
- **Tope diario.** Cuenta reservas, incluidas las que terminan `skipped` o `failed`, y no ve el volumen de alertas que comparte la cuota de Resend.
- **Qué significa `sent`.** Que Resend aceptó el mail; rebotes y quejas no se registran.
- **Duración de la prueba.** Las reservas usan las 72 h de `plan_limits_for`. Si cambia esa duración, hay que revisar `claim_lifecycle_emails` y `count_after_expiry_end`.
- **El conteo de 2.5 es un piso.** Cuando otra búsqueda activa rastrea el mismo modelo con filtros más estrechos (por ejemplo, desde 2018, si la vencida pedía desde 2012), la vencida solo ve lo que trae esa consulta.
- **Publicaciones que ya no están.** N incluye las publicaciones que aparecieron aunque ya no estén publicadas; al reactivar solo se ven las que siguen activas.

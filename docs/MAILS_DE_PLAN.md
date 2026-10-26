# Mails del plan

Son los mails de la fase 2 de [planes](PLANES_2026-10.md), los que llevan a pagar. Los manda el worker por Resend, con su propio registro de envíos. Reemplazan al recordatorio de fin de prueba del 9/10, que pasó a ser el mail 2.2.

| Mail | Cuándo | Estado |
| --- | --- | --- |
| 2.1 Prueba sin coincidencias | 24 h después de activar la prueba, sin ninguna coincidencia nueva desde la activación | Listo |
| 2.2 Fin de la prueba | Al terminar las 72 h, si la cuenta nunca compró | Listo |
| 2.3 Vencimiento de Particular | 5 días antes y el día que vence el pase | Listo |
| 2.5 Conteo después de vencer | El primero de los días 7, 14 o 21 después del vencimiento en que haya algo; una sola vez por cuenta | Listo |
| Bienvenida | 45 minutos después de la primera búsqueda de la cuenta | Listo |
| Remarketing 1A o 1B | Cuentas sin búsqueda: 24 h después de pedirla o de registrarse; una sola vez por cuenta, sin seguimiento | Listo, apagado |
| Prueba extra de 7 días | Oferta 7 días después de la prueba de 72 h; aviso al día 5 y al terminar | Listo, apagado |

## Reglas para todos

- **Remarketing, una sola vez por cuenta.** Desde el 26/10/2026 (decisión de Juan), para no insistir: una cuenta recibe como máximo un mail 2.5 en toda su vida y un solo mail de remarketing sin búsqueda (1A o 1B). Cuenta lo que salió (`sent`); uno fallido o salteado no bloquea. La regla está en `count_after_expiry_eligible` y `no_search_eligible` ([`20261114120000_remarketing_once.sql`](../supabase/migrations/20261114120000_remarketing_once.sql)), así que vale al reservar y al re-chequear.
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

  El worker las evalúa con el mismo motor que las coincidencias, pero las guarda en `expired_search_matches` (con nivel, puntaje y `diff_pct`): no se muestran en la web ni generan avisos. «Por debajo de comparables» corresponde al nivel `high`. La primera pasada de un portal nuevo se toma como historial y no se cuenta, tampoco cuando las corridas siguientes la vuelven a encontrar: no cuenta nada visto por primera vez antes de que terminara la primera corrida exitosa del objetivo (`collector_runs`).
- **Cuándo.** Los días 7, 14 y 21 después del vencimiento, cada uno durante 24 horas. Sale el primero de esos días en que haya algo para contar, y después ninguno más: es un solo mail por cuenta, también si vuelve a vencer. Si N da 0, ese día no sale nada; si aparece algo más tarde ese mismo día, el mail sale en ese momento.
- **Qué búsqueda.** Si había varias, la que más encontró.
- **La oportunidad que se perdió.** Desde el 26/10/2026 (decisión de Juan) el mail muestra el mejor auto que apareció desde el vencimiento, con la plantilla de marca de las alertas: foto, modelo, precio publicado y el % por debajo de comparables resaltado en amarillo. Lo elige `missed_car` al reservar el mail y queda en `payload.car`: primero las de nivel `high`, después la mayor diferencia contra comparables (`diff_pct`), el mejor puntaje y la más nueva. Nunca una con precio parcial. Si la búsqueda tiene radio, el auto tiene que tener coordenadas dentro de ese radio: los que pasan el filtro de ubicación como «desconocido» se cuentan, pero no se muestran.
  - **Asunto.** «Te perdiste este {auto}, {D}% debajo de comparables». Si sigue publicado: «Apareció este {auto} y tu búsqueda estaba pausada, …». Sin D, el asunto termina en el auto.
  - **Título.** «La oportunidad que te perdiste». Si sigue publicado no se habla de pérdida: «Esto apareció mientras tu búsqueda estaba pausada».
  - **Líneas.** «{D}% debajo de publicaciones comparables.» (o «Por debajo de publicaciones comparables.» sin porcentaje), kilómetros y zona, «Estuvo publicado {días} días y ya no está.» (o «Todavía está publicado: reactivá tu búsqueda para verlo.»), «Con tu búsqueda activa, te hubiéramos avisado apenas apareció.» y, si N es mayor que 1, «Y no fue el único: desde que venció tu acceso aparecieron {N} autos nuevos para tu búsqueda, {M} por debajo de comparables.». Las frases con un número en 0 no aparecen.
  - **Días publicado.** Desde la publicación (o la primera vez que se vio) hasta la última vez que se vio; solo cuando ya no está.
  - La foto lleva al mismo destino que el botón.
- **Sin auto para mostrar.** Si ninguno tiene precio completo, el mail sale con el conteo: asunto «Aparecieron {N} autos nuevos para tu búsqueda de {modelo}» (con uno solo, «Apareció 1 auto nuevo…») y el cuerpo «Desde que venció tu acceso aparecieron {N} autos nuevos que coinciden con tu búsqueda, y {M} están por debajo de comparables. Reactivá para verlos.» Si M da 0, la frase termina en «tu búsqueda».
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

## Bienvenida

No lleva a pagar: es el primer mail que recibe la cuenta y existe para que los que siguen lleguen a Principal. Desde el 15/10/2026 salieron 66 mails a usuarios reales sin un solo clic.

- **A quién.** Una vez por cuenta (`event_key = 'first'`), 45 minutos después de su primera búsqueda, si esa cuenta recibe emails y tiene una búsqueda activa. Los 45 minutos dejan que el primer rastreo cuente coincidencias. Si la búsqueda se pausó antes del envío, la fila queda `skipped`.
- **Asunto.** «Tu búsqueda de {modelo} ya está activa».
- **Cuerpo.** «Ya encontramos {X} autos que coinciden con tu búsqueda de {modelo}, y {Y} están por debajo de publicaciones comparables. Te avisamos de los nuevos apenas aparezcan.» Con X en 0: «Ya estamos revisando las publicaciones para tu búsqueda de {modelo}. Todavía no apareció ninguno que coincida: te avisamos apenas aparezca.» Después: «Para que nuestras alertas no terminen en Spam o Promociones, agregá este remitente a tus contactos o mové este email a Principal.»
- **Botón.** «Ver mis resultados», a `/app/searches/<id>` (la búsqueda activa que más encontró).
- **Código.** [`20261109130000_search_activated_email.sql`](../supabase/migrations/20261109130000_search_activated_email.sql): las funciones de reserva y re-chequeo de los demás tipos quedan como `*_base` y las nuevas las llaman.

## Remarketing: cuentas sin búsqueda

No lleva a pagar: busca que la cuenta arme su primera búsqueda o que cuente por qué no. Al 25/10/2026 eran 12 de 36 cuentas: 9 habían escrito qué auto buscaban en el modo asistido sin activarlo y 3 nunca escribieron nada.

- **Diseño.** La plantilla de marca de los demás mails de plan, con el remitente de siempre: título, una sola línea y un botón a la plataforma. Nada más, porque el objetivo es que entren (decisión de Juan, 26/10/2026). Con `remarketing.reply_to` las respuestas van a esa casilla.
- **1A, búsqueda sin activar (`search_abandoned`).** 24 horas después del último pedido asistido (`llm_jobs` `parse_search` terminado) de una cuenta que no tiene ninguna búsqueda, ni pausada.
  - **Asunto y título.** «Tu búsqueda de {modelo} está lista».
  - **Línea.** «La armamos con lo que nos escribiste. Activala y te avisamos cuando aparezca.»
  - **Botón.** «Activar mi búsqueda», a `/app/searches/new?prompt=<texto>`: el modo asistido con lo que había escrito.
- **1B, nunca escribió (`search_not_started`).** 24 horas después del registro, sin pedido asistido ni búsqueda. Asunto «¿Qué auto estás buscando?», la línea «Contanos con tus palabras y revisamos las publicaciones por vos.» y el botón «Empezar mi búsqueda» a `/app/searches/new`.
- **Seguimiento (`search_feedback`).** No sale desde el 26/10/2026: la cuenta ya recibió 1A o 1B y la regla de una sola vez lo bloquea. Lo que sigue describe cómo era. 4 días después de que salió 1A o 1B, si todavía no tiene búsqueda y no contestó ningún motivo. Asunto «Tu {modelo} te está esperando» (sin modelo, «Tu próximo auto te está esperando»), la línea «Activá tu búsqueda en un minuto y dejá que busquemos por vos.», el botón del primer mail y, debajo, un link chico «¿Algo te frenó? Contanos». Después de este, nada más.
- **Motivos.** El link del seguimiento es `/f/<id>?s=<firma>` ([página](../web/app/f/[emailId]/page.tsx)): abrirlo no registra nada, porque los antivirus del correo abren todos los links. La página ofrece «Solo estaba mirando», «No encontré mi modelo o versión», «La búsqueda que armaron no era lo que pedí» (solo después de un pedido asistido), «No entendí qué hace Ese Auto», «Ya compré un auto» y «Otro motivo», un campo opcional para comentar y el botón «Enviar» (con `?r=<motivo>`, ese motivo viene marcado). La firma es la del botón del mismo mail. Se guarda en `email_feedback`, uno por mail (un segundo envío lo reemplaza), con el evento `email_feedback`. Se ven en `/admin/metrics`, «Por qué no armaron su búsqueda».
- **Cuentas que ya estaban.** `remarketing.backfill_since` (por defecto 1/10/2026): al prender 1A o 1B, las cuentas cuyo evento es posterior a esa fecha reciben el suyo aunque sea más viejo que `window_hours`. Es una vez por cuenta, como todos. Con `null`, solo cuenta la ventana. El seguimiento no usa esa fecha: se mide desde que salió el primero.
- **Apagados.** Los tres tipos nacen en `false` en `lifecycle_emails.kinds`.
- **Código.** [`20261110120000_remarketing_no_search.sql`](../supabase/migrations/20261110120000_remarketing_no_search.sql): las funciones de reserva y re-chequeo anteriores quedan como `*_welcome` y las nuevas las llaman. Los textos, en `remarketing_email` de `notifications/templates.py`.

## Prueba extra de 7 días

Para las pruebas de 72 h que terminaron sin compra: una vez por cuenta, 7 días más con su búsqueda. Al 25/10/2026 eran 14, y varias habían encontrado cientos de autos sin abrir un email.

- **Oferta (`bonus_trial_offer`).** 7 días después de que terminó la prueba de 72 h, si nunca pagó (un pago devuelto cuenta como compra), no tiene un checkout en curso, nunca tuvo la prueba extra y su búsqueda encontró algo. Ese día **reemplaza al conteo del 2.5**: un conteo reservado mientras hay una oferta de menos de 5 días queda `skipped`. Los conteos de los días 14 y 21 siguen si no la aceptó.
  - **Asunto.** «Te damos 7 días más para tu búsqueda de {modelo}».
  - **Línea.** «Desde que pausamos tu búsqueda aparecieron {N} autos nuevos. Reactivala gratis 7 días, sin tarjeta.» Sin nuevos: «En tu prueba encontramos {X} autos. …». Los autos los ve en la plataforma: el registro guarda hasta 3 en `payload.cars`, pero el mail no los muestra.
  - **Botón.** «Activar mis 7 días», a `/app/bonus` ([página](../web/app/app/bonus/page.tsx)). Abrirla no cambia nada: la prueba arranca con el botón de la página (`start_my_bonus_trial`). Reactivar sin que lo pidan mandaría alertas a quien no las quiere.
- **Cómo funciona.** `profiles.bonus_trial_started_at` marca el inicio. `plan_limits_for` responde `trial` durante 7 días (`free_trial_end`), así que búsquedas, alertas y límites son los del plan gratis, como en la primera prueba. Al activarla vuelven las búsquedas que pausó el vencimiento, hasta el cupo del plan gratis. Se registra `bonus_trial_started`.
- **Día 5 (`bonus_trial_ending`).** «Te quedan 2 días gratis para tu búsqueda de {modelo}», con la línea «Ya encontramos {N} autos. El {día} tu búsqueda se pausa.» y el botón «Ver mis resultados».
- **Al terminar (`bonus_trial_ended`).** «Terminaron tus 7 días: encontramos {X} para tu búsqueda», con la línea «Encontramos {X} para tu búsqueda de {modelo}.» y el botón «Seguir con Particular». El evento `bonus_trial_ended` guarda `results`, `opportunities`, `alerts_sent`, `alerts_clicked` y `converted`.
- **Después.** El 2.5 cuenta desde el fin de la prueba extra (`count_after_expiry_end`): un ciclo más de 7, 14 y 21 días.
- **Pruebas que ya terminaron.** `bonus_trial.backfill_since` (por defecto 1/10/2026): al prender la oferta, las pruebas cuyo día 7 cae después de esa fecha la reciben aunque sea más viejo que `window_hours`.
- **Apagados.** Los tres tipos nacen en `false` en `lifecycle_emails.kinds`.
- **Código.** [`20261111120000_bonus_trial.sql`](../supabase/migrations/20261111120000_bonus_trial.sql): las funciones anteriores quedan como `*_remarketing` y las nuevas las llaman.

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
| `kinds` | Prendidos: 2.1, 2.2, 2.3, 2.5 y `search_activated` (bienvenida). Apagados: `search_abandoned`, `search_not_started` y `search_feedback` (remarketing) | Prende o apaga cada tipo. Apagar `count_after_expiry` también corta su rastreo. |
| `send_from` / `send_until` | `"09:00"` / `"21:00"` | Horario de envío, hora argentina. |
| `window_hours` | `48` | Plazo para mandar una fila reservada. Pasado ese plazo queda `skipped` (`outside_window`). Tiene que superar la noche sin envíos. |
| `max_per_day` | `30` | Mails reservados por día calendario argentino, entre todos los tipos. Resend gratis permite 100 por día entre alertas y estos mails. |

El worker revisa cada `TRIAL_REMINDER_TICK_SECONDS` (900 s). El nombre se conserva por compatibilidad con el `.env` del VPS.

## Código

- **Migración.** [`20261020120000_lifecycle_emails.sql`](../supabase/migrations/20261020120000_lifecycle_emails.sql): crea el registro, mueve las filas de `trial_reminders` y borra esa tabla.
- **2.5.**
  - [`20261024120000_count_after_expiry.sql`](../supabase/migrations/20261024120000_count_after_expiry.sql): el conteo, quién se cuenta (`count_after_expiry_searches`), el reclamo del mail y el evento.
  - [`20261112120000_count_missed_car.sql`](../supabase/migrations/20261112120000_count_missed_car.sql): puntaje y `diff_pct` en el conteo, `missed_car` y el auto en el payload. `claim_lifecycle_emails` anterior queda como `claim_lifecycle_emails_bonus`.
  - [`20261113120000_missed_car_location.sql`](../supabase/migrations/20261113120000_missed_car_location.sql): el auto mostrado, siempre dentro del radio de la búsqueda.
  - Vista previa: [`design/email-alerts/oportunidad-perdida.html`](../design/email-alerts/oportunidad-perdida.html).
  - En el worker: los objetivos `count_only` están en `pipeline/crawl.py` y `db/repos/targets.py`; el conteo de cada tanda, en `count_after_expiry` de `pipeline/scheduler.py`, que guarda con `db/repos/expired_matches.py`.
- **Worker.** [`notifications/lifecycle.py`](../worker/notifications/lifecycle.py) decide cuándo correr y manda; [`db/repos/lifecycle_emails.py`](../worker/db/repos/lifecycle_emails.py) maneja el registro; los textos están en [`notifications/templates.py`](../worker/notifications/templates.py).
- **Tests.** `test_lifecycle_emails_postgres.py` y `test_lifecycle_templates.py`, con snapshots en `tests/snapshots/notifications/lifecycle_*.txt`. El rastreo de 2.5 se prueba en `test_ingest_postgres.py` (`CountAfterExpiryCrawlTests`).

## Verificar en producción

1. Configuración: `select value from app_config where key = 'lifecycle_emails';`.
2. Envíos por tipo: `select kind, status, count(*) from lifecycle_emails group by 1, 2 order by 1, 2;`.
3. Errores: `select * from pipeline_errors where stage = 'lifecycle_email' order by created_at desc;`.
4. Log del worker: líneas `plan emails: N <kind> claimed` y `N sent`, o `plan emails off: …` si falta el canal o `WEB_BASE_URL`.
5. Eventos: `select name, count(*) from events where name in ('trial_ended', 'lifecycle_email_sent', 'lifecycle_email_clicked', 'reactivated_from_count_email', 'email_feedback', 'bonus_trial_started', 'bonus_trial_ended') group by 1;`.
6. 2.5, búsquedas que se cuentan ahora: `select * from count_after_expiry_searches();`.
7. 2.5, objetivos diarios: `select source, make, model, query->'count_profile_ids', next_run_at from crawl_targets where active and query->>'count_only' = 'true';`.
8. 2.5, lo contado: `select search_profile_id, access_ended_at, count(*), count(*) filter (where level = 'high') from expired_search_matches group by 1, 2;`.

## Límites conocidos

- **Caídas largas.** Si el worker está caído más de `window_hours`, los eventos de ese lapso se quedan sin mail.
- **Tope diario.** Cuenta reservas, incluidas las que terminan `skipped` o `failed`, y no ve el volumen de alertas que comparte la cuota de Resend.
- **Qué significa `sent`.** Que Resend aceptó el mail; rebotes y quejas no se registran.
- **Duración de la prueba.** Las reservas usan las 72 h de la prueba y los 7 días de la prueba extra (`free_trial_end`). Si cambia alguna duración, hay que revisar `claim_lifecycle_emails` y `count_after_expiry_end`.
- **El conteo de 2.5 es un piso.** Cuando otra búsqueda activa rastrea el mismo modelo con filtros más estrechos (por ejemplo, desde 2018, si la vencida pedía desde 2012), la vencida solo ve lo que trae esa consulta.
- **Reinicio de bootstrap.** Si un cambio de `POLICY_VERSION` repite la carga inicial de Mercado Libre o Facebook, lo que esa carga trae por primera vez puede contarse en las corridas siguientes: el historial se mide desde la primera corrida exitosa del objetivo, no desde la última carga inicial.
- **Publicaciones que ya no están.** N incluye las publicaciones que aparecieron aunque ya no estén publicadas; al reactivar solo se ven las que siguen activas.

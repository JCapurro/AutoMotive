# Prueba gratis «40 + N»

Juan lo decidió y aprobó el plan el 20/11/2026. Todo sale apagado: lo prende él desde `/admin/config` cuando la migración esté aplicada y el worker desplegado.

## Por qué

Con la reserva prendida desde el 14/11 (`docs/PRUEBA_HONESTA.md`), la prueba muestra hasta 30 autos ya publicados (los más nuevos) y deja el resto del cupo de 50 para autos nuevos. Dos problemas:

- **Cuándo pagar.** El cartel de los 50 (`FreeResultLimit`) abre cuando la cuenta usó su cupo, pero casi nadie está en la app en ese momento: hoy, 1 de las 32 cuentas que llegaron a 50 lo vio. La oferta del primer rato (`docs/OFERTA_PRUEBA.md`) abre sola antes de que la prueba haya mostrado su valor.
- **Cuánto tarda.** Medido en producción: con 5 autos nuevos, el 41 % de las pruebas se completa dentro de las 72 h (mediana: 22 h). Con lo que queda del cupo de 50 casi ninguna lo completa.

La prueba pasa a ser: 40 autos ya publicados, elegidos al azar entre lo que encuentra la primera revisión, y después los próximos 5 autos nuevos de cualquier nivel. Con el 5.º sale un único aviso de pago: un mail y un cartel. Antes de eso no se abre nada solo.

## Reglas

- **El interruptor es `app_config.trial_reserve`.** La migración no lo toca. Con la fila como está hoy (`{"enabled": true, "backfill_max": 30}`) la base, los mails y la web hacen exactamente lo de hoy.
- **Modo nuevo** = reserva prendida y un `new_max` válido.
- **Los números no están en el código.** 40 y 5 salen de `backfill_max` y `new_max`.
- **Un valor roto es apagado**, como los campos de antes: un `new_max` que no es un número de 0 o más es sin tope; un `random_stock` que no es `true` es apagado; un `notice_since` que no se puede leer es sin mail.
- **Nunca quita** un resultado ya admitido.
- **El tope total** (`plan_limits.free.max_total_results`, 50) sigue valiendo, y las 72 h también.

## Los tres campos nuevos de `trial_reserve`

| Campo | Qué es | Qué hace |
| --- | --- | --- |
| `new_max` | Entero de 0 o más | Tope de resultados nuevos por cuenta. Al llegar, la prueba está completa. |
| `random_stock` | `true` | Los ya publicados de la primera revisión (y de cada re-revisión) se eligen al azar, no los más nuevos. |
| `notice_since` | Fecha y hora ISO | El mail `trial_complete` va solo a pruebas empezadas desde ese momento. Sin este campo, no va a nadie. |

## Qué hace cada modo

### Modo de hoy (sin `new_max`)

Sin cambios: los ya publicados entran por orden de llegada hasta `backfill_max`, los nuevos llenan el resto hasta 50, el cartel de la oferta se abre solo una vez por búsqueda (con 5 ocultos o más) y `FreeResultLimit` se abre a los 50. `FreeResultLimit` y estos caminos quedan como vuelta atrás; se borran cuando el modo nuevo esté confirmado.

### Modo nuevo

**Base de datos** (`20270109120000_trial_complete.sql`):

- **Tope de nuevos.** `admit_free_result` no admite un resultado nuevo si la cuenta ya tiene `new_max` con `is_backfill = false`. Lo ya publicado sigue con su tope `backfill_max`.
- **Ya publicados al azar** (con `random_stock`). Mientras una búsqueda espera su primera revisión o una re-revisión (`bootstrapped_at` vacío o `rematch_requested_at` puesto), lo ya publicado espera. Al terminar la revisión (`mark_bootstrapped`), el trigger `search_profiles_admit_free_stock_sample` admite de una vez una muestra al azar de lo ya publicado de esa búsqueda, con la publicación activa y todavía sin admitir, hasta el lugar que queda: `least(backfill_max - ya publicados admitidos, tope total - admitidos)`. Lo ya publicado que llega después, con la búsqueda lista, entra por orden de llegada. Un auto nuevo nunca espera. «Ya publicado» es la misma regla de siempre, ahora en una sola función (`trial_is_stock`). El worker no cambia para esto.
- **Lo que lee la web.** `my_plan_limits()` suma `free_new_used` y `free_new_max` (este último vacío sin tope o sin cupo de prueba).
- **Cuándo se completó.** `trial_completed_at(cuenta)`: cuándo entró el resultado nuevo número `new_max`. Vacío sin tope, con tope 0 o si todavía no llegó.

**Mails** (docs/MAILS_DE_PLAN.md):

- **`trial_complete` (nuevo).** Una vez por cuenta, 60 minutos después de completar, solo con `lifecycle_emails.kinds.trial_complete` en `true` (apagado en la migración, en el worker y en `/admin/config`), solo a pruebas empezadas desde `notice_since`, mientras la cuenta tenga cupo de prueba y la prueba siga corriendo (una cuenta que pagó o una prueba terminada no lo reciben; para el final está `trial_ended`).
- **Bienvenida.** Lo que le queda a la prueba son autos nuevos: «Tu prueba te va a mostrar los próximos {N} autos nuevos que coincidan.»

**Página de resultados**:

- **Antes de completar:** el cartel de la oferta ya no se abre solo. La franja, su botón «Ver todos» (que lo abre) y la tarjeta del final quedan como están.
- **Al completar:** no aparece `FreeResultLimit`. El mismo cartel se abre en su variante «completa», una vez por pestaña y búsqueda (`sessionStorage`, clave `ea_trial_complete_opened:<id>`), y la franja lo vuelve a abrir. Aparece aunque la búsqueda no oculte nada. Tiene el camino «Enviar feedback» del cartel viejo.
- **Otros textos** de la página que decían «50 resultados» dicen lo que pasó: «Tu prueba ya te mostró sus {N} autos nuevos».
- **Qué {N}.** Los autos nuevos que la cuenta recibió de verdad (`free_new_used`), no el tope: en una prueba que ya corría al prender el modo pueden ser más (hasta 20). El mail usa el tope porque solo va a pruebas empezadas desde `notice_since`, donde son iguales.
- **Completa es solo por el tope.** Una cuenta que llenó sus 50 sin llegar al tope de nuevos (por ejemplo, antes de prender el modo) sigue el camino de hoy en los dos modos: `FreeResultLimit` y «Tu prueba ya usó sus 50 resultados».
- **La tarjeta del final** con `random_stock` ya no dice «los primeros {N} que encontramos» sino «Tu prueba muestra {N} de los {T}.».
- **Planes y Términos** dicen los dos números.

## Textos

Con `new_max` 5, 45 mostrados y 23 ocultos.

### Mail `trial_complete`

| Parte | Texto |
| --- | --- |
| Encabezado | TU PRUEBA GRATIS |
| Asunto y título | Ya encontramos 5 autos nuevos para tu búsqueda (con 1: «Ya encontramos 1 auto nuevo para tu búsqueda») |
| Primera línea | Aparecieron desde que se activó tu búsqueda de Ford Focus y ya están en tu lista. (sin modelo: «…tu búsqueda y ya están en tu lista.»; con 1: «Apareció desde que se activó tu búsqueda de Ford Focus y ya está en tu lista.») |
| Con ocultos | Hay 23 más que coinciden y tu prueba no muestra. (con 1: «Hay 1 más que coincide y tu prueba no muestra.»; con 0, no va) |
| Oferta | Para seguir recibiendo los que aparezcan, Particular sale $5.000 por 7 días o $15.000 por 30, pago único. (precios y días de `pro_offer.pass_7` y `pro_offer.pass_30`; sin un pase de 7 días válido, la línea de 2.2: «…Particular sale $15.000 por 30 días, con 3 búsquedas y pago único.») |
| Botón | Seguir recibiendo autos nuevos |
| Pie | El de `trial_ended`. |

Payload: `model`, `new` (el tope), `shown` (lo que la prueba muestra de esa búsqueda) y `hidden` (las coincidencias activas que oculta, como las cuenta `my_search_hidden_results`). La búsqueda es la que más muestra, como en `trial_ended`. Va a `/app/searches/<id>` (a `/app` si la cuenta no tiene búsquedas).

### Bienvenida en modo nuevo

En lugar de cuántos resultados le quedan a la prueba:

- con lugar: «Tu prueba te va a mostrar los próximos 5 autos nuevos que coincidan.» (con 1: «Tu prueba te va a mostrar el próximo auto nuevo que coincida.»);
- sin lugar: «Tu prueba ya te mostró sus 5 autos nuevos, así que no vamos a avisarte de otros. Con Particular los ves todos y seguimos avisándote.» (con 1: «…ya te mostró su auto nuevo…»).

El payload lleva `trial_new` (el tope) y `trial_left` cuenta autos nuevos.

### Cartel «completo»

| Lugar | Texto |
| --- | --- |
| Etiqueta | Prueba gratis completa |
| Título | Ya te encontramos 5 autos nuevos. (con 1: «Ya te encontramos 1 auto nuevo.») |
| Bajada con ocultos | Seguí recibiendo los que aparezcan y mirá los **23** más que coinciden. (con 1: «Seguí recibiendo los que aparezcan y mirá el otro que coincide.») |
| Bajada sin ocultos | Seguí recibiendo los que aparezcan. |
| Botón de pago con ocultos | Ver los 68 · 7 días por $ 5.000 |
| Botón de pago sin ocultos | Seguir recibiendo · 7 días por $ 5.000 |
| Salida | Seguir con mis 45 |
| Feedback | Enviar feedback |
| Franja | Ya te encontramos **5** autos nuevos. Hay **23** más que coinciden. · botón «Seguir recibiendo» (con 1 nuevo: «Ya te encontramos 1 auto nuevo.»; con 1 oculto: «Hay 1 más que coincide.»; sin ocultos, solo la primera frase) |

### Otros textos de la página

- Cartel de preparación: «Desde ahora: tu prueba ya te mostró sus 5 autos nuevos, así que no vamos a avisarte de otros.»
- Formularios de búsqueda nueva (estructurado y asistido), con la prueba completa: «Tu prueba ya te mostró sus 5 autos nuevos, así que no vamos a avisarte de otros.» en lugar de «Desde entonces te avisamos de las nuevas.» / «Te avisamos por email cuando aparezca una publicación que coincida.»; tiene prioridad sobre «ya usó sus 50 resultados».
- Lista vacía: «Todavía no hay publicaciones que coincidan. Tu prueba ya te mostró sus 5 autos nuevos: con Particular te avisamos de las nuevas.»
- Tarjeta del final con `random_stock`: «Tu prueba muestra 45 de los 68. Con Particular los ves todos y te avisamos de los nuevos.» (con 0 mostrados, el texto de siempre)

### Planes y Términos

- Planes: «Hasta 40 autos ya publicados y los próximos 5 autos nuevos que aparezcan durante la prueba» (con 1: «…y el próximo auto nuevo que aparezca…»).
- Términos dice como total lo que la prueba puede mostrar de verdad, `min(max_total_results, min(backfill_max, max_total_results) + new_max)`: «hasta 45 resultados en total durante la prueba» con 40 y 5. Después: «De ese cupo, como máximo 40 son publicaciones que ya estaban al activar la búsqueda, elegidas al azar entre las que encuentra la primera revisión, y después se suman las próximas 5 publicaciones nuevas que coincidan; con eso la prueba queda completa.» (sin `random_stock`, sin «elegidas al azar…»).

## Eventos

Los de la oferta (`trial_offer_viewed`, `trial_offer_dismissed`, `trial_offer_plan_selected`), con `complete: true` en `props` para la variante completa. Las vistas de la variante completa se cuentan aparte (`sessionStorage` `ea_trial_offer_viewed:<superficie>:<id>:complete`). El mail registra `lifecycle_email_sent` y `lifecycle_email_clicked` como los demás.

## Qué queda afuera

- El largo de la prueba, los precios, los límites de los planes y los niveles de alerta.
- `plan_limits.free.immediate_alerts_per_day`: se sube por configuración al prender, no en el código.
- Planes pagos, admins y el piloto sin límites: sin cambios.
- **Prueba extra de 7 días:** una cuenta que completó la prueba no recibe autos nuevos en la semana extra, igual que hoy una cuenta con el cupo lleno. No se cambia.
- **Tope 0:** con `new_max` 0 la prueba muestra solo lo ya publicado y nunca queda «completa» (ni cartel ni mail: no hay «0 autos nuevos» que contar).
- `FreeResultLimit` y los caminos del modo de hoy quedan como vuelta atrás. Se borran cuando el modo nuevo esté confirmado.

## Despliegue

1. **Migración** `20270109120000_trial_complete.sql`, a mano con el OK de Juan: transacción más el insert de la versión exacta; antes, ver `max(version)` en prod (hoy `20270108120000`). Agrega un trigger en `search_profiles` y cambia `admit_free_result` (el trigger de `matches`): con el worker andando puede esperar locks; `lock_timeout` es de 5 s, si falla se reintenta.
2. **Merge:** Vercel publica la web.
3. **Worker en el VPS:** el tipo `trial_complete` y la bienvenida nueva.

Sin la migración la web anda igual (sin `free_new_max` no hay modo nuevo). Sin el worker, el mail no sale y la bienvenida usa el texto de hoy.

## Encender

En `/admin/config`, en este orden:

1. `plan_limits.free.immediate_alerts_per_day`: de 3 al tope (5), para que los 5 nuevos puedan llegar en el momento.
2. `lifecycle_emails.kinds.trial_complete`: `true` («Prueba completa»).
3. `trial_reserve`: `{"enabled": true, "backfill_max": 40, "new_max": 5, "random_stock": true, "notice_since": "<hora de encendido, ej. 2026-11-21T15:00:00Z>"}`.

Cada cambio queda en el historial de `/admin/config`.

## Volver atrás

En `trial_reserve`, sacar `new_max`, `random_stock` y `notice_since` (y volver `backfill_max` a 30 si se quiere lo de antes). Lo admitido queda; desde ese momento la prueba vuelve a las reglas de hoy y `FreeResultLimit` vuelve a abrir a los 50. Apagar `kinds.trial_complete` corta el mail.

## Qué medir

Comparar las pruebas empezadas desde `notice_since` con las de las dos semanas anteriores:

- **Cuántas completan y cuándo:** `trial_completed_at(user_id)` menos `free_trial_started_at`, por cuenta; cuántas dentro de las 72 h.
- **Cartel:** `trial_offer_viewed` con `props->>'complete' = 'true'` y `surface = 'sheet'`; cerrados (`trial_offer_dismissed`) y pases elegidos (`trial_offer_plan_selected`).
- **Mail:** `lifecycle_emails` con `kind = 'trial_complete'` por estado (`sent`, `skipped`), aperturas y `lifecycle_email_clicked`.
- **Pagos:** `checkout_started` y `commercial_payments` de esas cuentas, y cuántos llegan dentro de las 24 h del mail.
- **Lo ya publicado:** `free_trial_results.is_backfill` por cuenta (debería quedar en 40 o menos).

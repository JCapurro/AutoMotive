# Prueba gratis de 50 publicaciones

Juan aprobó el plan el 20/11/2026 («40 + N») y lo cambió el 21/11/2026 por esta regla: «45 no es un número, debería aparecer 50». Todo sale apagado. Juan lo prende desde `/admin/config` cuando las dos migraciones estén aplicadas y el worker desplegado.

## Por qué

La reserva está prendida desde el 14/11 (`docs/PRUEBA_HONESTA.md`). Con ella, la prueba muestra hasta 30 autos ya publicados (los más nuevos) y deja el resto del cupo de 50 para autos nuevos. Eso trae dos problemas.

- **Cuándo pagar.** El cartel de los 50 (`FreeResultLimit`) abre cuando la cuenta usó su cupo, pero casi nadie está en la app en ese momento. Hasta hoy, 1 de las 32 cuentas que llegaron a 50 lo vio. Y la oferta del primer rato (`docs/OFERTA_PRUEBA.md`) abre sola antes de que la prueba haya mostrado su valor.
- **Cuánto tarda.** Con lo que queda del cupo para autos nuevos, casi ninguna prueba llega a 50 dentro de las 72 h.

## La regla

- **La prueba se cuenta como «50 publicaciones».** Termina en una de dos formas:
  - Llega a 50 resultados (`plan_limits.free.max_total_results`).
  - Pasan los 3 días.
- **Sin tope de nuevos.** Lo ya publicado entra hasta `backfill_max` (45 al prender), elegido al azar entre lo que encuentra la primera revisión. Los autos nuevos llenan el resto hasta 50.
- **Completa = cupo lleno** (usados ≥ límite). Recién ahí aparecen el cartel y el mail `trial_complete`. Antes no se abre nada solo.
- **Las pruebas que no llegan a 50** completan los 3 días de prueba gratis y siguen el camino de hoy (`trial_ended`).
- **Qué no dice ningún texto al usuario:**
  - el tope de lo ya publicado;
  - cuántos autos nuevos hubo;
  - cómo se arman los 50.

  Términos es la excepción: dice el tope de lo ya publicado, como hoy.

## Reglas del interruptor

- **El interruptor es `app_config.trial_reserve`.** Las migraciones no lo tocan. Con la fila de producción (`{"enabled": true, "backfill_max": 30}`), la base, los mails y la web hacen exactamente lo de hoy (ver «Cómo se comprobó que no cambia nada»).
- **Modo aviso** = reserva prendida y un `notice_since` que se puede leer. En la base es `trial_reserve_notice_since()`; en la web, `trialNoticeMode()`.
- **Los números no están en el código.** 45 sale de `backfill_max` y 50 de `max_total_results`.
- **Un valor roto es apagado,** como los campos de antes:
  - un `random_stock` que no es `true` es apagado;
  - un `notice_since` que no se puede leer es modo de hoy.
- **Nunca se quita** un resultado ya admitido.

## Los dos campos nuevos de `trial_reserve`

| Campo | Qué es | Qué hace |
| --- | --- | --- |
| `random_stock` | `true` | Lo ya publicado de la primera revisión (y de cada re-revisión) se elige al azar, no por más nuevo. |
| `notice_since` | Fecha y hora ISO | Prende el modo aviso. El mail `trial_complete` va solo a pruebas empezadas desde ese momento. |

## Base de datos

Son dos migraciones.

- **`20270109120000_trial_complete.sql`** está en producción desde el 21/11 a las 15:12 UTC y no se toca.
- **`20270110120000_trial_fifty.sql`** la lleva a esta regla:
  - Borra `trial_reserve_new_max()`.
  - Saca de `admit_free_result` el tope de nuevos.
  - Vuelve `my_plan_limits()` a la forma de 20261207, sin `free_new_used` ni `free_new_max`.
- **Lo ya publicado al azar** (con `random_stock`) queda como estaba en 0109:
  - Mientras una búsqueda espera su primera revisión o una re-revisión, lo ya publicado espera.
  - Al terminar la revisión, el trigger `search_profiles_admit_free_stock_sample` admite de una vez una muestra al azar, hasta el lugar que queda.
  - Un auto nuevo nunca espera.
- **Cuándo se completó.** `trial_completed_at(cuenta)` es cuándo entró el resultado número `límite`, ordenado por `admitted_at` y `listing_id`. Vacío sin límite o si el cupo todavía no se llenó.

## Mails (docs/MAILS_DE_PLAN.md)

- **`trial_complete`.** Se manda una vez por cuenta, 60 minutos después de llenar el cupo, solo si se cumplen todas estas condiciones:
  - `lifecycle_emails.kinds.trial_complete` está en `true` (viene apagado en la migración, en el worker y en `/admin/config`);
  - la prueba empezó desde `notice_since`;
  - la cuenta sigue con cupo de prueba;
  - la prueba sigue corriendo.

  Una cuenta que pagó y una prueba terminada no lo reciben.
- **Bienvenida.** En modo aviso, el payload suma `"trial_notice": true` y el texto cuenta la prueba como sus 50 publicaciones.

## Página de resultados

- **Antes de llenar el cupo:**
  - El cartel de la oferta no se abre solo.
  - La franja, su botón «Ver todos» (que lo abre) y la tarjeta del final dicen cuántos coinciden, no cuántos muestra la prueba.
- **Con el cupo lleno:**
  - No aparece `FreeResultLimit`.
  - El cartel se abre en su variante «completa», una vez por pestaña y búsqueda (`sessionStorage`, clave `ea_trial_complete_opened:<id>`), y la franja lo vuelve a abrir.
  - Aparece aunque la búsqueda no oculte nada.
  - Tiene el camino «Enviar feedback» del cartel viejo.
- **Los avisos honestos** quedan como en main: el cartel de preparación, los dos formularios de búsqueda nueva y la lista vacía dicen «Tu prueba ya usó sus 50 resultados…».
- **Modo de hoy:** sin cambios. `FreeResultLimit` se abre a los 50, y la franja y el cartel son los de siempre. Con `random_stock`, la tarjeta del final usa la bajada corta.

## Textos

Los ejemplos son con 50 publicaciones, 45 mostradas en la búsqueda y 23 ocultas.

### Antes de llenar el cupo (modo aviso)

| Lugar | Texto |
| --- | --- |
| Franja | Encontramos **68** autos que coinciden. · botón «Ver todos» (con 1: «Encontramos 1 auto que coincide.») |
| Título del cartel | Encontramos 68 autos. (con 1: «Encontramos 1 auto.») |
| Bajada del cartel | Con Particular los ves todos y te avisamos de los nuevos. (con 1: «Con Particular lo ves…») |
| Botón de pago | El de siempre: «Ver los 68 · 7 días por $ 5.000» |
| Salida | Ahora no |
| Tarjeta del final | Título de siempre («Y 23 más que coinciden»). Bajada: «Con Particular los ves todos y te avisamos de los nuevos.» También con `random_stock` fuera del modo aviso. |

### Cartel «completo» (versión A)

| Lugar | Texto |
| --- | --- |
| Etiqueta | Prueba gratis completa |
| Título | Ya recibiste tus 50 publicaciones. |
| Bajada | ¿Querés seguir recibiendo? |
| Botón de pago | Seguir recibiendo · 7 días por $ 5.000 (siempre, con ocultos o sin) |
| Salida | Ahora no |
| Feedback | Enviar feedback |
| Franja | Ya recibiste tus **50** publicaciones. · botón «Seguir recibiendo» |

### Mail `trial_complete`

| Parte | Texto |
| --- | --- |
| Encabezado | TU PRUEBA GRATIS |
| Asunto y título | Ya recibiste las 50 publicaciones de tu prueba |
| Con ocultos | Hay 23 más que coinciden con tu búsqueda de Ford Focus. (con 1: «Hay 1 más que coincide…»; sin modelo: «…con tu búsqueda.»; con 0, no va) |
| Oferta | Para seguir recibiendo, Particular sale $5.000 por 7 días o $15.000 por 30, pago único. (precios y días de `pro_offer.pass_7` y `pass_30`; sin un pase de 7 días válido, la línea `particular_offer`) |
| Botón | Seguir recibiendo |
| Pie | El de `trial_ended`. |

El payload es `{model, total, shown, hidden}`:

- `total` es el límite.
- `shown` es lo que la prueba muestra de esa búsqueda.
- `hidden` son las coincidencias activas que oculta.

La búsqueda elegida es la que más muestra, como en `trial_ended`. El mail lleva a `/app/searches/<id>`, o a `/app` si la cuenta no tiene búsquedas. Un payload sin `total` no se manda: el worker lo rechaza.

### Bienvenida en modo aviso

- **Lo encontrado:** «Ya encontramos 68 autos que coinciden con tu búsqueda de Ford Focus.» Suma mostrados y ocultos, con la cola de «abajo del precio» de siempre y sin línea de ocultos. Sin nada encontrado, el texto de siempre.
- **Con cupo:** «Tu prueba incluye 50 publicaciones: de las nuevas que coincidan te avisamos por email.»
- **Con el cupo lleno:** «Ya recibiste las 50 publicaciones de tu prueba. Con Particular las ves todas y seguimos avisándote.»

`trial_left` se calcula como siempre.

### Planes y Términos

- **Planes,** en modo aviso: «Hasta 50 publicaciones durante la prueba».
- **Términos:** la frase de siempre, con total = el límite: «hasta 50 resultados en total durante la prueba. De ese cupo, como máximo 45 son publicaciones que ya estaban al activar la búsqueda».
  - Con `random_stock` se le suma: «, elegidas al azar entre las que encuentra la primera revisión».

## Eventos

- **Cartel:** los de la oferta (`trial_offer_viewed`, `trial_offer_dismissed`, `trial_offer_plan_selected`), con `complete: true` en `props` para la variante completa.
  - Las vistas de la variante completa se cuentan aparte (`sessionStorage` `ea_trial_offer_viewed:<superficie>:<id>:complete`).
- **Mail:** registra `lifecycle_email_sent` y `lifecycle_email_clicked`, como los demás.

## Qué queda afuera

- El largo de la prueba, los precios, los límites de los planes y los niveles de alerta.
- `plan_limits.free.immediate_alerts_per_day`: se sube por configuración al prender, no en el código.
- Planes pagos, admins y el piloto sin límites: sin cambios.
- **Prueba extra de 7 días:** una cuenta con el cupo lleno no recibe autos nuevos en la semana extra, como hoy. No se cambia.
- **El modo de hoy** queda como vuelta atrás: `FreeResultLimit` y sus caminos. Se borran cuando el modo aviso esté confirmado.

## Cómo se comprobó que no cambia nada

En un clon anterior a las dos migraciones (en 20270108) se corrió un escenario con `trial_reserve` `{"enabled": true, "backfill_max": 3}`, límite 8 y tres cuentas:

- una con lo ya publicado esperando la revisión;
- una con una re-revisión;
- una solo con autos nuevos, con una publicación dada de baja.

De cada una se guardó lo admitido, `my_plan_limits()` y el payload de la bienvenida. Después se aplicaron 0109 y 0110 en el mismo clon y se repitió el escenario. Lo único distinto fueron las horas de la transacción (`expires_at`, `trial_started_at`).

## Despliegue

1. **Migración `20270110120000_trial_fifty.sql`.** Se aplica a mano con el OK de Juan: una transacción más el insert de la versión exacta.
   - Antes, ver `max(version)` en prod: tiene que ser `20270109120000`.
   - Cambia `admit_free_result` (el trigger de `matches`), así que con el worker andando puede esperar locks. `lock_timeout` es de 5 s; si falla, se reintenta.
2. **Merge.** Vercel publica la web.
3. **Worker en el VPS:** el mail `trial_complete` nuevo y la bienvenida en modo aviso.

Las dos migraciones (0109 y 0110) tienen que estar en producción antes de prender.

## Encender

En `/admin/config`, en este orden:

1. `plan_limits.free.immediate_alerts_per_day`: de 3 a 5.
2. `lifecycle_emails.kinds.trial_complete`: `true` («Prueba completa»).
3. `trial_reserve`: `{"enabled": true, "backfill_max": 45, "random_stock": true, "notice_since": "<hora de encendido, ej. 2026-11-22T15:00:00Z>"}`.

Cada cambio queda en el historial de `/admin/config`.

## Volver atrás

1. Volver `trial_reserve` a `{"enabled": true, "backfill_max": 30}`.
   - Lo ya admitido queda.
   - Desde ese momento la prueba vuelve a las reglas de hoy y `FreeResultLimit` vuelve a abrir a los 50.
2. Para cortar el mail, apagar `kinds.trial_complete`.

## Qué medir

Comparar las pruebas empezadas desde `notice_since` con las de las dos semanas anteriores:

- **Cuántas completan y cuándo:** por cuenta, `trial_completed_at(user_id)` menos `free_trial_started_at`. Contar cuántas completan dentro de las 72 h.
- **Cartel:** `trial_offer_viewed` con `props->>'complete' = 'true'` y `surface = 'sheet'`. Además, los cerrados (`trial_offer_dismissed`) y los pases elegidos (`trial_offer_plan_selected`).
- **Mail:** `lifecycle_emails` con `kind = 'trial_complete'` por estado (`sent`, `skipped`), las aperturas y `lifecycle_email_clicked`.
- **Pagos:** `checkout_started` y `commercial_payments` de esas cuentas, y cuántos llegan dentro de las 24 h del mail.
- **Lo ya publicado:** `free_trial_results.is_backfill` por cuenta. Debería quedar en 45 o menos.

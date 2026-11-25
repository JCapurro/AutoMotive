# Oferta cuando la prueba oculta autos

Juan aprobó el diseño el 14/11/2026, sobre el prototipo `design/variants/oferta-prueba/`. Eligió la variante A: un cartel que se abre solo una vez, una franja arriba de la lista y una tarjeta al final, con el pase de 7 días primero.

> **Desde el 21/11 (`docs/PRUEBA_COMPLETA.md`):** en modo aviso (`trial_reserve.notice_since`, la prueba de 50 publicaciones) el cartel ya no se abre solo antes de que el cupo se llene. La franja dice «Encontramos {T} autos que coinciden.», el cartel «Encontramos {T} autos.» con «Con Particular los ves todos y te avisamos de los nuevos.» y la salida «Ahora no». Con el cupo lleno se abre su variante «completa» («Ya recibiste tus 50 publicaciones.» / «¿Querés seguir recibiendo?») en lugar de `FreeResultLimit`, una vez por pestaña y búsqueda. La tarjeta del final, en modo aviso o con `random_stock`, dice solo «Con Particular los ves todos y te avisamos de los nuevos.». Sin `notice_since`, todo lo de este documento sigue igual.

## Por qué

Desde que se prendió la reserva de la prueba (`docs/PRUEBA_HONESTA.md`), la prueba muestra como máximo 30 autos ya publicados. El resto queda oculto, y la página solo lo decía en un renglón gris al final de la lista.

- 0 de 16 búsquedas de prueba nuevas vieron una pantalla de pago. 6 de ellas ocultaban autos.
- En 14 días, 92 de 363 búsquedas de prueba tenían más de 30 autos publicados. La mediana era de 48 ocultos.
- El cartel de los 50 (`FreeResultLimit`) ya no aparece en el primer rato, porque la reserva frena el llenado. Era el único lugar donde se pagaba (análisis del 14/11: los 2 pagos llegaron en los primeros 20 minutos desde ese tope).

## Qué hace

En la página de resultados de una búsqueda (`/app/searches/[id]`), cuando la prueba oculta coincidencias que siguen publicadas:

### 1. Franja arriba de la lista (`TrialHiddenOffer`, `data-testid="trial-offer-strip"`)

«Tu prueba muestra **30** de los **78** autos que coinciden.» y un botón «Ver todos» que abre el cartel.

### 2. Cartel (`TrialHiddenOffer`, `data-testid="trial-offer-sheet"`)

- En el celular es una hoja que sube desde abajo. Desde `sm` es un diálogo centrado.
- Se abre solo **una vez por búsqueda y navegador**: la clave `ea_trial_offer_opened:<id>` de `localStorage`. Sin almacenamiento (modo privado), se abre una vez por visita a la página.
- Se abre solo si la búsqueda oculta al menos `TRIAL_OFFER_SHEET_MIN` (5) autos y el filtro es «Todos». La franja y la tarjeta aparecen con cualquier cantidad.
- El foco va al cartel, no al primer botón (si no, «7 días» parecería elegido dos veces).
- Contenido: título, bajada, el pase Particular con «7 días» elegido y «30 días» a un toque, la garantía, el botón de pago, «Seguir con mis 30» y los términos con un link a Pro.

### 3. Tarjeta al final de la lista (`TrialHiddenCard`, `data-testid="trial-hidden"`)

Reemplaza los dos renglones grises de antes («Y N más que coinciden y tu prueba no muestra.» y la lista vacía con «Hay N publicaciones…»). Muestra los dos pases como botones: el de 7 días relleno y primero, el de 30 con borde.

- Con resultados: al final de la lista, en el filtro «Todos» y en la última página.
- Con la lista vacía: en lugar del texto de lista vacía, en el filtro «Todos».

### Pago

Igual que `ExpiredMissed` (`web/components/app/expired-missed.tsx`):

- Con pagos automáticos: `startPayment` y directo a Mercado Pago, con `InitiateCheckout` (Meta) y `begin_checkout` (GA). Una cuenta que entró solo con el mail pasa antes por `/app/cuenta` y vuelve a `/app/pro?plan=…`.
- Sin pagos automáticos: a `/app/pro?plan=<pase>&from=results`.

## Reglas

- **Solo cantidades:** al navegador llegan `shown` (lo que la lista muestra, `count.all_count`) y `hidden` (`my_search_hidden_results`). Ningún dato de un auto oculto.
- **Cuándo aparece:** `hidden > 0`, la búsqueda ya está lista (`!needsPreparation`: mientras se prepara, los conteos se mueven) y la prueba **no** llegó al tope de 50. Con el tope, manda el cartel de los 50 (`FreeResultLimit`), que no cambia.
- **El pase de 7 días va primero** en el cartel y en la tarjeta.
- **Precios:** los de `app_config.pro_offer` (`webConfig().proOffer`). Este cambio no toca precios ni planes.
- **Textos:** viven en `web/lib/trial-offer.ts` para que los tres lugares digan lo mismo. Sin los términos de `FORBIDDEN_TERMS` (`web/lib/copy.ts`).

## Textos (con 30 mostrados y 48 ocultos)

| Lugar | Texto |
| --- | --- |
| Franja | Tu prueba muestra **30** de los **78** autos que coinciden. · botón «Ver todos» |
| Título del cartel | Encontramos 78 autos. Tu prueba muestra 30. |
| Bajada del cartel | Los otros **48** también coinciden con lo que pediste y siguen publicados. |
| Botón de pago | Ver los 78 · 7 días por $ 5.000 |
| Salida del cartel | Seguir con mis 30 |
| Título de la tarjeta | Y **48** más que coinciden |
| Bajada de la tarjeta | Tu prueba muestra los primeros 30 que encontramos. Con Particular ves los 78, ordenados por mejor oportunidad, y te avisamos de los que aparezcan. |
| Segundo botón de la tarjeta | 30 días por $ 15.000 |

Los singulares y el caso «la prueba no muestra ninguno» están en `trial-offer.ts` y probados en `web/lib/trial-offer.test.ts`. Por ejemplo, con 0 mostrados: «Encontramos 12 autos. Tu prueba no muestra ninguno.» y la salida «Ahora no».

## Eventos

`trackTrialOffer` (`web/app/app/pro/actions.ts`) escribe en `public.events`. Nunca tira error: un evento que falla no frena el pago.

| Evento | Cuándo | `props` |
| --- | --- | --- |
| `trial_offer_viewed` | Se vio una superficie. Una vez por pestaña, búsqueda y superficie (`sessionStorage`). La tarjeta cuenta cuando entra en pantalla. | `search_profile_id`, `surface`, `shown`, `hidden` |
| `trial_offer_dismissed` | Se cerró el cartel sin elegir un pase («Seguir con mis…», la X, Escape o tocar afuera). | ídem |
| `trial_offer_plan_selected` | Se tocó un pase en el cartel o en la tarjeta. | ídem + `plan` (`pass_7` o `pass_30`) |

`surface` es `sheet`, `strip` o `card`. En la variante «completa» de `docs/PRUEBA_COMPLETA.md` los tres eventos llevan además `complete: true`. La franja no tiene evento de clic propio: tocar «Ver todos» abre el cartel y suma un `trial_offer_viewed` con `surface = sheet` si es la primera vez en la pestaña.

Cada `trial_offer_viewed` (y cada `quota_popup_viewed` del aviso de límite) también va al píxel de Meta como evento personalizado `PaywallViewed`, con `content_name` = la superficie (`sheet`, `strip`, `card` o `quota_popup`) y eventID `paywall:<superficie>:<search_profile_id>`. Sirve para ver en Meta qué anuncios traen gente que llega a la pantalla de pago y para armar audiencias con quienes la vieron y no pagaron. No lleva datos de la persona. No va a X: X necesita un evento creado en su Events Manager.

Lo que sigue al pase elegido ya existía y no lleva `surface`:

- `checkout_started` (`props.offer`, `props.checkout_id`): se creó el checkout de Mercado Pago.
- `payment_confirmed` (`props.offer`, `props.amount`): el pago se acreditó.

Para atribuirlos a la oferta, unir por `user_id` con el `trial_offer_plan_selected` anterior del mismo plan (`props.plan = props.offer`) dentro de, por ejemplo, 30 minutos.

## Cómo medir

Cuentas que empiezan la prueba después del despliegue, por `surface`:

1. **Vistas:** búsquedas con `trial_offer_viewed`, por `surface`, y su `hidden` (mediana, y si cambia algo arriba o abajo de 48).
2. **Cierres:** `trial_offer_dismissed` sobre vistas del cartel.
3. **Pase elegido:** `trial_offer_plan_selected` por `surface` y `plan`. ¿Se elige el de 7 o el de 30?
4. **Checkout:** `checkout_started` atribuido (ver arriba) sobre pases elegidos.
5. **Pago:** `payment_confirmed` atribuido sobre `checkout_started`.

Comparar contra las búsquedas de prueba de los 14 días anteriores (0 pantallas de pago vistas en las 16 nuevas desde la reserva). Con pocos pagos por semana, leer los números absolutos antes que los porcentajes.

```sql
-- Embudo por superficie, desde el despliegue.
select props->>'surface' as surface,
       count(*) filter (where name = 'trial_offer_viewed')        as vistas,
       count(*) filter (where name = 'trial_offer_dismissed')     as cierres,
       count(*) filter (where name = 'trial_offer_plan_selected') as pases
from public.events
where name like 'trial_offer_%' and created_at >= :desde
group by 1 order by 1;
```

## Qué queda afuera

- **El cartel de los 50** (`FreeResultLimit`): no cambia. Con el tope alcanzado no aparecen la franja ni el cartel; la tarjeta sí, si hay ocultos.
- **El camino al pago** de las cuentas que entraron solo con el mail (`/app/cuenta`, `account-steps`, `email-only`): es la parte B, en otra rama.
- **Otros filtros** («Nuevos», «Favoritos», etc.): la franja aparece, pero el cartel no se abre solo y la tarjeta no se muestra.
- **Mails:** siguen como en `docs/PRUEBA_HONESTA.md` §3.
- **Pro:** solo un link en el cartel. La oferta es para Particular.

## Archivos

- `web/lib/trial-offer.ts`: conteos y textos.
- `web/components/app/trial-hidden-offer.tsx`: franja, cartel, elección del pase y tarjeta.
- `web/app/app/searches/[id]/page.tsx`: dónde y cuándo aparecen.
- `web/app/app/pro/actions.ts`: `trackTrialOffer`.
- `web/lib/admin-event-labels.ts`: nombres de los eventos en el admin.
- Pruebas: `web/lib/trial-offer.test.ts`, `web/lib/trial-hidden-offer.test.ts`, `web/lib/trial-offer-events.test.ts`, `web/lib/free-result-limit-page.test.ts`.

## Despliegue

Solo web: sin migración ni cambios en el worker. `my_search_hidden_results` ya está en producción. Merge y Vercel publica.

# Camino al pago con código

Desde noviembre de 2026 (propuesta aprobada por Juan sobre `design/variants/oferta-prueba/pago.html`).

## Qué cambia

Una cuenta que entró solo con su email (el 93 %) llega a Mercado Pago escribiendo **un código**. Ya no elige contraseña ni vuelve a pasar por la página de Planes.

Antes eran siete pasos: el botón del plan, «Mandarme el código», ir al email, escribir el código, la contraseña dos veces, la página de Planes otra vez y «Continuar en Mercado Pago». El 14/11/2026, 2 de las 3 personas que eligieron un plan en el cartel de pago no llegaron a Mercado Pago.

Ahora:

1. El botón del plan lleva a `/app/cuenta?next=/app/pro?plan=<oferta>`, como antes.
2. El código **se manda solo** al llegar (una vez por pestaña y minuto: recargar no lo vuelve a mandar).
3. La persona escribe el código y toca «Confirmar y pagar $ 5.000». Al confirmar acepta los Términos.
4. La página sigue sola a Mercado Pago (`?pagar=1`).

Lo que no cambia: **nadie paga sin haber probado que el email es suyo**. La base sigue rechazando un checkout de una cuenta `email_only` (trigger `guard_billing_account`). La cuenta se completa con las mismas guardas que la contraseña:

- prueba fresca de esta sesión (`hasFreshProof`, menos de 1 hora);
- las demás sesiones se cierran antes (`signOut({ scope: 'others' })` y, en la misma transacción, `complete_email_only_account`);
- `safeNext` en todo `next`.

La contraseña queda opcional. Después se entra con un código por email; quien quiera una la elige en «Mis datos» (`/auth/reset-password`).

## Estados de `/app/cuenta`

«Pagando» = `next` empieza con `/app/pro` y los pagos automáticos están prendidos (`webConfig().automaticPayments`). El plan sale de `payPlan(next)` ([web/lib/pro.ts](../web/lib/pro.ts)): `/app/pro?plan=<oferta>` sin `fundador`.

| Cuenta | Pagando | Qué muestra |
|---|---|---|
| Solo-email sin prueba | sí | «Escribí el código que te mandamos». Código enviado solo; botón «Confirmar y pagar $ X» (o «Confirmar y seguir» con el link fundador). Si el envío falla por límite, queda el error y «Mandarme otro código». |
| Solo-email con prueba, o cuenta completa con plan | sí | «Seguí en Mercado Pago» ([ContinueToPayment](../web/components/app/continue-to-payment.tsx)). Con `?pagar=1` (escribió el código en esta pestaña) arranca solo, una vez por pestaña (`sessionStorage`), para que «Atrás» desde Mercado Pago no abra otro checkout. Sin `pagar=1` (abrió el link del email) muestra «Continuar en Mercado Pago · $ X». |
| Solo-email sin prueba | no | «Confirmá tu email», como antes. |
| Solo-email con prueba | no | «Elegí una contraseña», como antes. |
| Cuenta completa sin plan | — | `redirect(next)`, como antes. |

Resultados de `continueToPayment(next, version, amount)` ([web/app/app/cuenta/actions.ts](../web/app/app/cuenta/actions.ts)):

- `url`: dispara `InitiateCheckout` (Meta) y `begin_checkout` (GA4) y abre Mercado Pago.
- `href`: no hay oferta para cobrar acá (link fundador, `/app/pro` solo o pagos apagados); sigue a esa página.
- `password`: la base todavía no tiene la migración; aparece el formulario de contraseña de antes.
- `expired`: la prueba venció; la página vuelve al paso del código (y el código se manda solo).
- `error`: se muestra, con el botón para reintentar.

La cuenta completa que llega con un plan no se redirige: cuando una acción toca cookies, Next vuelve a renderizar la página en la misma respuesta, y para entonces la cuenta ya no es solo-email.

## Entrar después sin contraseña

Las cuentas solo-email tienen identidad `email` y un `encrypted_password` al azar. Al completarse sin contraseña, `/login` les pediría una clave que nunca eligieron. Por eso:

- `complete_email_only_account(..., 'code')` pone `auth.users.raw_app_meta_data.passwordless = true`.
- `hasPassword` ([web/lib/email-only.ts](../web/lib/email-only.ts)) devuelve false con esa marca, y `/login` manda el código.
- `updatePassword` ([web/app/auth/reset-password/actions.ts](../web/app/auth/reset-password/actions.ts)) la pone en false con el cliente admin cuando la persona elige una contraseña.
- «Mis datos» dice «Todavía no elegiste una» y ofrece «Elegir contraseña».

## Migración y despliegue

[20261223120000_account_code_method.sql](../supabase/migrations/20261223120000_account_code_method.sql) redefine `complete_email_only_account`: es la de `20261029120000` más el método `'code'` y la marca. Prueba: [supabase/tests/account_code_method_test.sql](../supabase/tests/account_code_method_test.sql).

**El orden da igual; las dos versiones funcionan:**

- **Migración primero:** la web vieja nunca manda `'code'`.
- **Web primero:** la base vieja contesta `invalid_method` y la web muestra la contraseña, como hoy. El código se manda solo y la página arranca sola igual: solo falta saltear la contraseña.

Aplicarla con el procedimiento de siempre y con el OK de Juan. Antes, mirar `max(version)` en producción (el 15/11 era 20261222120000).

## Cómo medir

Embudo por cuenta, en `public.events`:

1. `quota_plan_selected` o `trial_offer_plan_selected` (eligió un plan en el cartel);
2. `account_completed` con `props.method = 'code'` (escribió el código; con `'password'` es el camino viejo o una base sin la migración);
3. `checkout_started`;
4. `payment_confirmed`.

Comparar el paso 1→3 con lo de antes (el 14/11: 1 de 3 llegó a Mercado Pago). En GA4, `begin_checkout`.

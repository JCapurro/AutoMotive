# Agencias: cómo cobrar el canal (propuesta)

Fecha: 19/11/2026. Fase 3 de [PLAN_AGENCIAS_STOCK_Y_CANAL.md](PLAN_AGENCIAS_STOCK_Y_CANAL.md).
**Es solo una propuesta.** No cambia precios, planes, `plan_limits`, `plan_feature()` ni nada de Mercado Pago, y no
agrega ningún límite que le corte el servicio a una agencia. Decide Juan.

## 1. Qué hay hoy

- **Planes** ([PLANES_2026-10.md](PLANES_2026-10.md)): Pro a $100.000 por mes (`pro_offer.pro_monthly`), precio
  fundador de $50.000 por 3 meses solo por link (`/fundador/<code>`). Los límites y funciones viven en
  `app_config.plan_limits`; `plan_feature(usuario, función)` los lee igual en la base, el worker y la web.
- **Cobro** ([MERCADO_PAGO.md](MERCADO_PAGO.md)): Pro es una suscripción de Mercado Pago (preapproval sin plan, con
  el monto guardado en `billing_checkouts.amount`); los pases son pagos únicos de Checkout Pro.
  `apply_mercadopago_payment` rechaza cualquier monto distinto del guardado (`payment_mismatch`): **un monto
  variable por mes no entra en la suscripción actual**.
- **Agencias**: una agencia es una fila de `dealers` con sus miembros (`dealer_members`, en el piloto uno por
  usuario). Plan y pago son **por usuario**, no por agencia: cualquier opción paga lee el plan del dueño.
- **Lo que se puede contar ya** (todo apagado por defecto):
  - consultas de compradores: `dealer_leads` (con estado: nueva, contactado, señado, vendido, perdido) y el evento
    `dealer_lead_created`;
  - pedidos a vendedores: `dealer_seller_requests` y los eventos `dealer_seller_requested` / `dealer_seller_answered`;
  - stock cargado y visible: `dealer_stock_items` y `dealer_listing_hidden()`;
  - alertas enviadas con autos de agencia: `notifications` unidas a `listings.dealer_id`.

Regla fija para las tres opciones: **neutralidad**. Pagar nunca cambia el puntaje, el orden ni el cupo de un auto.
Lo que se cobra es el acceso al canal (que sus autos `directo` lleguen a compradores) y las consultas, nunca una
posición.

## 2. Las tres opciones

### A · Incluido en Pro

La agencia paga Pro como cualquier usuario y con eso tiene el canal y «Qué comprar»/«Vendedores».

Qué habría que construir:
- Una función nueva en `plan_limits.pro`, por ejemplo `"dealer_channel": true` (se edita en /admin/config).
- En la compuerta de envío: una agencia sin la función queda como «sin aprobar» para los autos `directo`. Lo más
  simple es exigir `plan_feature(dueño, 'dealer_channel')` además de `approved_at` en `dealer_listing_hidden()` y
  `dealer_public_name()`, con su gemelo en el worker (`intelligence/dealer.py`).
- En el panel: un aviso «Con Pro tus autos llegan a compradores» y el botón al checkout de Pro que ya existe.
- Nada nuevo en Mercado Pago.

Pros: cero código de cobro nuevo; precio fácil de explicar; reusa el precio fundador por link.
Contras: $100.000 por mes antes de que la agencia vea consultas es una venta difícil; las funciones de comprador de
Pro no le sirven; no escala con lo que le damos (una agencia con 40 consultas paga lo mismo que una con 0).

### B · Por consulta entregada

La agencia paga por cada consulta de un comprador (`dealer_leads` nuevo) y por cada vendedor que acepta su pedido
(`dealer_seller_requests` aceptado).

Qué habría que construir:
- Un libro de movimientos por agencia (`dealer_ledger`: consulta entregada, crédito comprado, devolución), con la
  regla de qué cuenta: lead único por comprador y auto (ya lo garantiza `unique (buyer_user_id, listing_id)`), con
  teléfono válido, y sin cobrar los que la agencia marque como inválidos dentro de N días.
- Cómo pagar: **créditos prepagos** con Checkout Pro (como un pase: «20 consultas por $X»), porque una suscripción
  de monto variable choca con `payment_mismatch`. Habría que agregar una oferta nueva a `begin_billing_checkout` y a
  `apply_mercadopago_payment` (toca cobros: OK de Juan).
- Qué pasa sin crédito: hoy está prohibido cortar el servicio. Con esta opción, en algún momento habría que decidir
  si una agencia sin crédito deja de recibir consultas (eso sí es un corte) o si se le acumula deuda.
- Panel: saldo, consumo y factura del mes.

Pros: alinea el precio con el valor; la agencia chica entra barato.
Contras: es la opción con más código y más riesgo de cobros; incentiva discutir cada consulta («ese no compraba»);
y nos da un incentivo raro a mandar consultas flojas. Pide mucha confianza en la calidad del lead.

### C · Pro con N consultas incluidas

Pro incluye el canal y hasta N consultas por mes; arriba de N, créditos (como B) o un plan mayor.

Qué habría que construir:
- Lo de A, más un número en `plan_limits.pro` (por ejemplo `"dealer_leads_month": 20`) y su conteo por agencia y mes.
- Arriba de N: lo de B (créditos) o un segundo nivel de suscripción («Pro Agencia») con otra oferta en
  `pro_offer`. El segundo nivel es más simple: reusa la suscripción, sin montos variables.
- Mientras no se decida el excedente, N puede ser «sin tope»: con eso C arranca igual que A y solo se mide.

Pros: precio fijo y entendible, con protección si una agencia concentra muchas consultas; se puede empezar como A sin
código de excedente.
Contras: hay que elegir N con datos que todavía no tenemos; dos lugares donde se cobra si se hace el excedente.

## 3. Datos del embudo para decidir

Por agencia y por mes (todo sale de tablas que ya existen; falta una consulta de admin que lo junte):

| Dato | De dónde | Para qué |
|---|---|---|
| Autos cargados y visibles | `dealer_stock_items`, `dealer_listing_hidden()` | si la agencia mantiene el stock (si no, no hay nada que cobrar) |
| Alertas enviadas con sus autos | `notifications` × `listings.dealer_id` | alcance real |
| Visitas a la ficha de sus autos | eventos `listing_detail_viewed` | interés |
| Consultas (leads) y su estado | `dealer_leads` | **el número central**: consultas por agencia y mes, y su dispersión |
| Ventas declaradas | `dealer_leads.status = 'sold'` | cuánto vale una consulta para la agencia |
| Pedidos a vendedores y % aceptado | `dealer_seller_requests` | si «Vendedores» tiene valor propio |
| Vuelta al panel | eventos de vista de `/agencia/*` (**falta registrarlos**) | retención antes de pagar |
| Disposición a pagar | charla con las 3–5 agencias del piloto | el precio |

Umbrales orientativos para decidir al cierre del piloto:
- Si la mediana de consultas por agencia y mes es **menos de 3**: todavía no se cobra; el problema es la demanda.
- Si está **entre 3 y 15** y poco dispersa: **A** (o C con N sin tope).
- Si hay agencias con **más de 3 veces la mediana**: **C** con N cerca del percentil 75.
- B solo si las agencias piden explícitamente pagar por consulta y la tasa de consultas inválidas que marcan es baja.

## 4. Riesgos

- **Neutralidad.** Cualquier opción debe cobrar acceso, nunca orden. Revisar que el cobro no se cuele en
  `Scorer`, en el cupo ni en la etiqueta.
- **Privacidad.** Cobrar por consulta empuja a «exprimir» datos del comprador. El consentimiento por agencia y el
  mínimo de 3 personas en los conteos no se negocian por un plan.
- **Cobros.** B y el excedente de C tocan `begin_billing_checkout` y `apply_mercadopago_payment`. Cualquier cambio
  pide OK de Juan y el ensayo aislado de Mercado Pago.
- **Corte de servicio.** Hoy no hay ningún límite que corte a una agencia. Si una opción lo necesita (B sin crédito),
  es una decisión aparte, con aviso previo a la agencia.
- **Plan por usuario.** Si una agencia tiene más de un miembro (hoy no se puede), hay que decidir qué plan manda.
- **Pocos datos.** Con 3–5 agencias en el piloto, cualquier número de N es una estimación.

## 5. Recomendación

1. **Piloto gratis 60 a 90 días** con las agencias aprobadas, como ya se inclina Juan. Antes de empezar, agregar el
   registro de vistas del panel y una consulta de admin con la tabla de §3.
2. Al cierre, si la mediana de consultas supera 3 por mes: **opción C arrancando como A**. El canal entra en Pro
   (precio fundador por link para las agencias del piloto) con N «sin tope» al principio. Así no hay código de cobro
   nuevo: solo la función en `plan_limits` y la compuerta.
3. Con 2 o 3 meses de datos pagos, poner N en el percentil 75 y decidir el excedente con un segundo nivel de
   suscripción, no con créditos.
4. Dejar **B** como alternativa solo si las agencias lo piden.

Nada de esto se implementa sin el OK de Juan.

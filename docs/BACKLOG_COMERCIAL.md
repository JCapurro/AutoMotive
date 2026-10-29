# Ese Auto · backlog comercial

Actualizado: 29/10/2026 (versión anterior: 2/10/2026). Objetivo: ingreso complementario rentable. Referencias: [propuesta comercial](PROPUESTA_COMERCIAL.md), [planes de octubre](PLANES_2026-10.md), [mails de plan](MAILS_DE_PLAN.md), [Mercado Pago](MERCADO_PAGO.md), [estrategia de lanzamiento](marketing/ESTRATEGIA_LANZAMIENTO_2026-10-03.md).

**Resumen en una línea:** el producto, el cobro y los límites están en producción desde mediados de octubre; lo que falta es comercial. Hay 72 cuentas y 58 pruebas en un mes, y **cero pagos reales**. El trabajo de las próximas semanas es averiguar por qué y vender, no construir más.

## 1. Qué está en producción (29/10/2026)

| Frente | Estado en producción | Desde |
|---|---|---|
| Oferta | Prueba gratis (1 búsqueda, 72 h, 3 zonas), **Particular $15.000 / 30 días** (3 búsquedas, 10 avisos/día, carrocería sin modelo), **Pro $100.000 / mes** (20 búsquedas, 50 avisos/día, umbral de oportunidad, carrocería sin modelo), **Custom** a convenir por WhatsApp | Pro reemplazó a Agencia ($75.000) el 14/10 |
| Cobro | Mercado Pago integrado: checkout identificado, firma de notificaciones, períodos idempotentes, baja, devolución, conciliación. Extensión de Particular (+30 días sobre el vencimiento). Pagos a mano desde /admin | 7/10; extensión 14/10 |
| Límites | `app_config.plan_limits` aplicado por base, worker y web. Prueba única de 72 h desde la primera búsqueda; al vencer se pausan búsquedas y cesan alertas (`search_paused_by_plan`) | 14/10 |
| Mails de ciclo de vida | Bienvenida a los 45 min de la primera búsqueda, prueba sin coincidencias (2.1), fin de prueba (2.2), vencimiento de Particular (2.3), conteo 22 días después de vencer con "el auto que te perdiste" (2.5), búsqueda abandonada / no iniciada, remarketing a cuentas sin búsqueda (una vez), **prueba extra de 7 días** con la propia búsqueda. Registro de aperturas y clics | 14/10 a 26/10 |
| Entrada por público | Dos mensajes de entrada ("busco mi auto" / "busco habitualmente"); formulario con catálogo completo (422 modelos, versiones), varias zonas por búsqueda, carrocería | 16/10 a 26/10 |
| Producto que se puede prometer | Carriles por fuente, cola con lease, breaker, salud de plataforma, bot de reparación cada 5 min; noticias falsas filtradas en fuentes sin fecha; comparables confirmados (fases 1 y 2) | 21/10 a 24/10 |
| Administración | /admin/billing, /admin/config (límites y precios sin deploy), dashboards de decisiones (`admin_decision_metrics`) | 27/10 |
| Marca y canales | eseauto.com.ar, @eseauto.ar (IG), @eseautoar (X), contacto@eseauto.com.ar, Meta verificado, GA4 + Vercel Analytics con consentimiento por defecto | 16/10 |

**Publicado el 29/10/2026 (V-02):** tope de **50 resultados en total** durante la prueba (`20261118120000_free_results_cap_50`; al aplicarla, 50 cuentas gratis quedaron con su cupo histórico y 15 ya estaban en 50) y **formulario de feedback** en el pop-up del tope, con mail a Juan (`20261118130000_product_feedback_leads`, [PRODUCT_FEEDBACK.md](PRODUCT_FEEDBACK.md)). Web en Vercel y worker en el VPS en `660ba13`.

### Qué pasó con el backlog del 2/10

| ID | Resultado |
|---|---|
| COM-02, COM-03, COM-04, COM-05, COM-06, B-01, B-02, PIL-01 | **Cerrados.** Están en producción con las fases 1–3 de planes |
| COM-07 producto prometible | **Cerrado en lo técnico** (carriles, salud, noticias, comparables). Falta la parte comercial: publicar cobertura medida por fuente/zona |
| COM-08 medir rentabilidad | **Parcial.** Hay eventos y dashboards; falta registrar costos reales (VPS, Resend, Vercel, LLM) y horas |
| COM-10 salida controlada | **Hecho** el recorrido con cuentas propias (3 checkouts pendientes son pruebas de Juan). **Nunca lo completó un externo** |
| COM-01 validar la oferta con candidatos | **No se hizo.** 0 entrevistas, 0 demos a profesionales, prospectos de X sin contactar |
| COM-09 operación comercial | **Parcial.** Términos actualizados; falta presupuesto de costos, comprobante/impuestos y horario de soporte publicado |
| COM-11 aviso de fin de prueba | Cerrado (2.2) |
| A-01/A-02, C-01..C-03 | Siguen en reserva |

## 2. Lo que dicen los datos (prod, 29/10/2026)

| Métrica | Valor |
|---|---|
| Cuentas | 72, todas creadas en los últimos 30 días; **50 en los últimos 7 días** |
| Pruebas iniciadas | 58 (65 búsquedas creadas por 50 cuentas; 27 búsquedas activas, 40 pausadas) |
| Pruebas vencidas | 32; 33 búsquedas pausadas por plan |
| Cuentas por coincidencias | 7 con 0, 16 con 1–9, 19 con 10–49, 16 con 50+ |
| Uso | 356 avisos enviados, 28 clics en avisos, 161 fichas vistas, 39 salidas al portal, 4 favoritos |
| Señal de pago | 25 `plan_limit_hit`, 9 vieron el CTA de planes, 4 lo clickearon, **3 checkouts (todos de Juan), 0 pagos** |
| Mails de ciclo de vida | 101 enviados, 7 clics (36 bienvenida → 4 clics; 16 fin de prueba → 0; 16 sin coincidencias → 0; 10 conteo post-vencimiento → 0; 9 prueba extra → 2) |
| Modelos más buscados | Focus 5, Argo 5, Gol Trend 4, Corolla 4, Fiesta 4, Golf 3, Polo 3, Etios 3, Ka 3, A3 3 |

Lecturas:

- **La adquisición funciona mejor de lo que decía la proyección** (50 cuentas en una semana, sin pauta). El cuello de botella es prueba → pago.
- **El 40 % de las cuentas vio menos de 10 coincidencias.** Para ellas, vencer la prueba no duele: no hay nada que perder. Esto es cobertura o filtros, no precio.
- **Los mails de "fin de prueba" y "conteo" no convierten** (26 enviados, 0 clics). El de bienvenida y la prueba extra sí mueven.
- **Nadie llegó al checkout.** No se sabe si el precio asusta, si no se entiende qué se compra o si ni siquiera lo ven: 9 de 32 cuentas vencidas vieron el CTA.
- **Nadie entró por el canal profesional.** Las 72 cuentas son particulares (o no se midió el mensaje de entrada elegido: verificar en `search_created.mode`).

## 3. Backlog vigente

P0: necesario para el primer pago real. P1: para decidir precios y canales con datos. P2: condicional. Tamaño: S hasta 1 día, M 2–3, L 4–6.

| ID | Prio | Trabajo y resultado | Tamaño |
|---|---|---|---|
| V-01 | P0 | **Hablar con 10 cuentas vencidas** (de las 32): por qué no pagaron, qué buscaban, si encontraron auto. Preguntas por mail con respuesta a Juan, o llamada si dejan teléfono. Registrar en una planilla | Comercial, 1 semana |
| V-02 | P0 | ~~Publicar el tope de 50 + feedback~~ **Hecho el 29/10.** Es la primera fuente de objeciones en el producto: revisar los leads de `product_feedback` cada semana | S |
| V-03 | P0 | **Un pago real externo.** Pedirle a 2–3 conocidos que compren Particular con su tarjeta (se les devuelve si quieren). Confirma el checkout, el mail de confirmación, la activación y la factura | S + operación |
| V-04 | P0 | **Checkout visible al vencer.** Hoy 9 de 32 vencidos vieron el CTA. El mail 2.2 y la pantalla de vencido tienen que llevar directo al checkout con el precio y lo que recupera ("tus 2 búsquedas se reactivan") | S |
| V-05 | P0 | **Diagnóstico de las pruebas con < 10 coincidencias** (23 cuentas): modelo, zona, filtros, fuentes que cubrieron. Si es cobertura, ampliar fuentes/zonas; si son filtros, que el formulario avise antes (ya hay sugerencias con 0 resultados) | M |
| V-06 | P1 | **Costos reales y horas** en /admin: VPS, Resend, Vercel, LLM por mes, horas de Juan por semana. Cierra COM-08 | S |
| V-07 | P1 | **5 demos a profesionales** con una búsqueda de su trabajo. Arrancar con los [prospectos de X](marketing/PROSPECTOS_AGENCIAS_X_2026-10-07.md). Cierra COM-01 para Pro | Comercial, 2 semanas |
| V-08 | P1 | **Cobertura publicada por fuente y zona** (COM-07 comercial): "en AMBA leemos ML, FB, Kavak, Autocosmos y 7 agencias cada N minutos", con datos de `collector_runs` | S |
| V-09 | P1 | **Comprobante y condiciones** (COM-09): decidir monotributo/factura, actualizar términos, publicar horario de soporte | Operación |
| V-10 | P2 | Experimentos de precio/duración (ver §4), solo con la decisión explícita de Juan y después de V-01 | S cada uno |

## 4. Ideas por canal de venta

Son hipótesis para probar en orden, no decisiones. Cualquier cambio de precio, duración o cobro necesita el OK de Juan y queda registrado en §6.

### 4.1 Particular (B2C): comprador que busca su auto

**Qué sabemos:** llega solo, prueba, y el 60 % ve coincidencias reales. No paga. Cuando compra el auto, se va.

**Para convertir la prueba (orden sugerido):**

1. **Preguntar antes de cambiar.** V-01. Diez conversaciones valen más que cualquier experimento.
2. **Mostrar lo que pierde, no lo que gana.** Al vencer: "Desde que venció tu prueba aparecieron 14 Focus nuevos en tu zona, 3 por debajo del precio de referencia. Reactivá por $15.000". El 2.5 ya cuenta; hace falta que lo diga la pantalla y el mail 2.2, no un mail 22 días después.
3. **Checkout de un paso desde el mail.** Enlace firmado → checkout de Mercado Pago, sin pasar por /planes. Hoy hay 3 clics entre el mail y pagar.
4. **Particular más corto y más barato como entrada**, p. ej. 7 días por $5.000 o 15 días por $9.000 (**precio a definir por Juan**). El comprador no sabe si va a tardar un mes; 30 días es un compromiso. Medir si sube la conversión y si después extienden (la extensión ya existe).
5. **Pago asistido por WhatsApp.** Para quien no quiere cargar tarjeta: transferencia + activación desde /admin (ya existe). Ofrecerlo en el mail 2.2 como alternativa.
6. **Prueba extra a cambio de feedback.** Ya existe la de 7 días; condicionarla a responder 3 preguntas (V-02 trae el formulario).
7. **Garantía simple:** "si en 30 días no te avisamos de ningún auto por debajo de referencia, te devolvemos el pago". Las devoluciones ya están implementadas. Revisar términos antes.

**Para traer más compradores (cuando convierta algo):**

8. **Páginas por modelo con precio de referencia** ("¿Cuánto sale un Ford Focus usado en octubre 2026?"), generadas de `comparable_pool` para los 30 modelos más buscados. Es el único canal orgánico con intención de compra y los datos ya existen. SEO lento pero acumulativo. M.
9. **Grupos de Facebook de modelos** (Focus, Argo, Gol Trend): responder "¿está bien de precio?" con el dato de Ese Auto y el enlace. Manual, 30 min por día.
10. **Meta Ads tramo 1** del plan de lanzamiento: solo cuando haya 2–3 pagos orgánicos; antes no hay qué optimizar.
11. **Referido simple:** "compartile Ese Auto a quien te manda avisos" (P13). Sin cupón hasta que haya pagos.
12. **Mensaje de entrada medido:** confirmar que `search_created.mode` registra "busco mi auto" vs "habitualmente" y mirar la proporción.

**Qué no hacer todavía:** app nativa, WhatsApp automático, cupones, anual, pase de 90 días.

### 4.2 Pro (B2B): revendedor, agencia chica, comprador por encargo

**Qué sabemos:** nada de clientes. Cero demos, cero contactos, cero cuentas con el mensaje "busco habitualmente" verificadas. Pro vale $100.000/mes y tiene las funciones que un profesional pediría (20 búsquedas, umbral de oportunidad, carrocería sin modelo). Un profesional vale 6,7 Particulares.

**El argumento de venta es el umbral:** "cuando un Corolla 2020 aparece un 12 % abajo de los 40 publicados, te llega al instante". Eso es lo que un revendedor hace a mano todo el día en ML y FB. No vender "búsquedas"; vender "oportunidades antes que los demás".

**Para conseguir los primeros 5 (orden sugerido):**

1. **Prospección en X e Instagram** con la rutina de PROSPECTOS_AGENCIAS_X: 5 perfiles por día, 1 mensaje por negocio, empezar por HF Garage y Renato. Meta: 5 demos en 2 semanas (V-07).
2. **Demo con su búsqueda, no con la nuestra.** 15 minutos: armar un Pro de prueba desde /admin con sus modelos y zona, dejarlo 7 días, mostrarle el lunes qué oportunidades detectó. La prueba Pro no existe como producto; se hace a mano con `plan` y `plan_expires_at` desde /admin.
3. **Primeros 5 a precio piloto** (p. ej. $50.000/mes los primeros 3 meses, **a definir por Juan**) a cambio de una llamada semanal de 15 min. Se cobra por checkout normal; el monto de cada suscripción es propio. Reabrir `agency_founders.slots` si se quiere marcar.
4. **Reporte semanal de oportunidades por mail** para Pro: "esta semana detectamos 23 avisos bajo referencia en tus 8 búsquedas; 4 siguen publicados". Es un digest que ya casi existe (2.5 lo hace para vencidos). Da valor visible para renovar.
5. **WhatsApp para Pro, manual primero.** Antes de la Cloud API ([WHATSAPP_ALERTAS.md](WHATSAPP_ALERTAS.md)), Juan reenvía a mano las oportunidades de umbral a los 5 primeros por WhatsApp Business. Si lo piden, se automatiza.
6. **Canal indirecto: inspectores y gestores** (tipo Dynaco). No compran; recomiendan. Un Particular referido por ellos con comisión o un mes gratis para el que refiere.
7. **Vertical concreta para empezar:** revendedores de un segmento (p. ej. autos de $10–20 M en GBA oeste) en vez de "agencias" en general. La cobertura de fuentes en AMBA es la mejor.
8. **Landing /pro** separada de /planes, con el umbral explicado y un botón "Pedir demo" (WhatsApp, como Custom). Hoy Pro vive en la misma tabla que Particular y habla a dos públicos a la vez. S.

**Qué no hacer todavía:** equipos y permisos (ruta C), API, marca blanca, exportación (se sacó el 15/10), WhatsApp automático antes de 5 clientes que lo pidan.

### 4.3 Ideas de producto por dolor (de [BACKLOG_PRODUCTO_2026-10](BACKLOG_PRODUCTO_2026-10.md))

El backlog de producto del 26/10 parte de los dolores de cada público y detalla criterios de aceptación por ítem. Acá va solo el mapa contra los dos canales y cómo se cruza con §4.1 y §4.2; el detalle, los tamaños y las dependencias están en ese documento.

| ID | Canal | Idea en una línea | Cruce con este backlog |
|---|---|---|---|
| H-01 | ambos | Las 3 preguntas al vendedor en el mail de oportunidad (la landing lo promete) | S, va primero: cumple la promesa antes de pedir plata |
| PAR-03 | Particular | Días publicado, bajas acumuladas y comportamiento del modelo en tarjeta, ficha y mail | Refuerza 4.1.2: "lo que perdés" con datos del aviso |
| PAR-01 | Particular | Costo total estimado (transferencia, patente, gestoría) por aviso | Diferenciador de Particular frente a mirar el portal |
| PAR-02 | Particular | Señales de riesgo (fotos repetidas, "particular" con muchos avisos) y checklist antes de señar | Confianza; argumento para pagar 30 días |
| PAR-04 | Particular | Guías por modelo como páginas públicas indexables | Es 4.1.8 con contenido además de precios: un solo proyecto SEO |
| PAR-05 | Particular | "¿A cuánto publicarlo?" + captación de vendedores con consentimiento | P2; abre el canal del que vende para comprar |
| PRO-01 | Pro | Filtro duro "solo particulares", push y mensaje listo para pegar | Es el argumento de demo de 4.2.2: lo que el revendedor hace a mano |
| PRO-02 | Pro | Margen bruto estimado y umbral de alerta en USD | Completa 4.2: "oportunidades" en la unidad que usa la agencia |
| X-01 | Pro | Estados de seguimiento (contactado, visita, comprado) y notas | S; reemplaza la planilla de WhatsApp |
| PRO-03 / PRO-04 / PRO-05 | Pro | Monitor de stock, radar de mercado por zona, vendedores antes de publicar | P2, después de 5 Pro pagos; necesitan F-01/F-03 |
| F-02 / F-03 / F-04 | base | Vendedor v2, agregados de mercado, canal push | Fundaciones; F-02 es P0 porque PRO-01 y PRO-02 dependen de ella |

**Orden sugerido respecto de la venta:** H-01 y X-01 (chicos, mejoran la demo Pro) → F-02 → PRO-01 sin push → PAR-03 por aviso → PRO-02 margen v1. Nada de esto reemplaza V-01 a V-05: primero saber por qué no pagan; el ciclo 1 de producto corre en paralelo con las conversaciones, no antes.

### 4.4 Decisiones que piden los dos canales

- **Fuentes y zonas que se pueden prometer** (V-08). Vender AMBA primero; el interior se promete cuando las fuentes regionales tengan 30 días de lectura estable.
- **Un solo embudo de medición**: pruebas → coincidencias útiles → CTA visto → checkout → pago → renovación, separado por mensaje de entrada. Los dashboards de decisiones ya tienen la mayoría.
- **Presupuesto y horas**: cuántas horas por semana tiene Juan para hablar con gente. Sin eso, V-01 y V-07 no pasan.

## 5. Reserva: implementar solo con demanda demostrada

| Idea | Condición para priorizarla |
|---|---|
| Pase de 7/15 días (4.1.4) | V-01 dice que 30 días es la objeción |
| WhatsApp automático | 5 clientes Pro lo piden y pagan |
| Páginas SEO por modelo (4.1.8) | 2–3 pagos orgánicos confirman que el comprador paga |
| Prueba Pro autoservicio | Más de 5 demos manuales por mes |
| Equipos (ruta C) | Una agencia paga y pide un segundo usuario |
| Pase 90 días, anual, cupones, app nativa, API | Retención demostrada durante varios ciclos |

No incluir comisión por compraventa, mensajes automáticos a vendedores ni promesas de rentabilidad.

## 6. Registro de decisión

- [x] Objetivo: ingreso complementario rentable (1/10).
- [x] Ruta B; Particular $15.000 / 30 días; Agencia $75.000 → **Pro $100.000 / mes** desde el 14/10. Fundadoras cerradas sin ninguna.
- [x] Cobro automático con Mercado Pago autorizado (2/10) y en producción (7/10).
- [x] Prueba: 1 búsqueda, 72 h, 3 zonas; tope de 50 resultados en total aprobado el 28/10, **sin publicar**.
- [x] Exportación CSV quitada el 15/10.
- [ ] Presupuesto de costos y horas semanales de Juan para venta.
- [ ] Comprobante / tratamiento impositivo.
- [ ] Precio piloto Pro y pase corto Particular (§4): **pendientes de decisión de Juan**, no implementar sin OK.
- [ ] Primer pago real de un externo.

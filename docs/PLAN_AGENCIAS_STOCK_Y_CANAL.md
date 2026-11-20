# Ese Auto para agencias: stock, precios y canal de venta

Fecha: 18/11/2026. Estado: **borrador para discutir con Juan**. Todavía no se construye nada, no hay migraciones ni cambios de precio.

Origen: charla con un agenciero (TT) cuyo problema principal es **conseguir canales para vender sus autos**. Juan ya le había adelantado la herramienta de stock e insights de precio. Este plan suma lo que pidió: aprovechar la demanda que ya tenemos (las búsquedas de los compradores) como canal de venta.

## 1. La idea en una frase

La agencia carga su stock una sola vez. A cambio sabe a qué precio está cada auto contra el mercado, cuánta gente lo está buscando ahora mismo y, si lo autoriza, el auto les llega a esos compradores dentro de sus alertas.

## 2. Lo que ya tenemos (no se construye de cero)

| Pieza | Dónde está | Para qué sirve acá |
|---|---|---|
| Comparables y nivel de precio | `comparables()`, `market_stats`, confirm_sources | Semáforo de precio de cada auto de la agencia |
| Catálogo de 422 modelos con versiones | `vehicle_catalog` | Normalizar lo que carga la agencia |
| Agrupado de avisos por vendedor | `seller_listing_count`, `listings.dealer_inferred` | Importar el stock de una agencia desde su perfil de Mercado Libre o Facebook, sin que cargue nada |
| Búsquedas guardadas con modelo, años, precio y zona | `search_profiles` | La demanda: cuánta gente busca cada auto |
| Matching, puntaje, alertas por email, web, Telegram y WhatsApp | worker | El canal: el auto de la agencia llega a quien lo busca |
| Duplicados entre fuentes | `listing_duplicates` | Que el mismo auto en ML y cargado directo se muestre una sola vez |
| Gente que quiere vender su auto y acepta que la contacten agencias | `sell_intent.agencies_contact_ok` | Canal de **compra** de stock para la agencia (fase 3) |
| Filtro «solo particulares» de Pro | `search_profiles.filters.seller_types` | Se respeta: quien no quiere agencias no las ve |
| Prospección de agencias por WhatsApp | worker/prospector, `/admin/prospeccion` | Ya tiene los datos de stock de cada agencia contactada; el informe del punto 4 se vuelve el gancho |
| Plan Pro y precio fundador | `plan_limits.pro`, `/fundador/<code>` | Ya existe dónde cobrar |

## 3. Cómo lo vive cada uno

### La agencia

1. **Alta en 2 minutos.** Tres formas de cargar, de menor a mayor esfuerzo:
   - Pega el link de su perfil de Mercado Libre, de Facebook o de su web. Nosotros leemos y mantenemos el stock sincronizado. Es la forma recomendada porque no le pide trabajo y se actualiza sola.
   - Sube una planilla, una foto de la lista o un PDF. Un LLM lo pasa a filas, lo cruza con el catálogo y la agencia confirma lo que dudamos.
   - Carga manual, auto por auto, con el formulario de búsqueda (marca, modelo, versión, año, km, precio, color, fotos).
2. **Panel de stock.** Una fila por auto con:
   - Precio contra el mercado: «12 % arriba de autos parecidos, 23 comparables».
   - Días en stock, contra cuánto tarda ese modelo en desaparecer de los portales (lo medimos con lo que ya leemos).
   - Demanda: «7 búsquedas activas lo quieren; 4 entran en tu precio».
   - Precio sugerido para vender en unos 30 días, explicado.
   - Margen, si cargó lo que pagó por el auto (dato privado, opcional).
3. **Avisos para la agencia.** «Bajó el mercado del Corolla 2019», «apareció uno igual 8 % más barato a 10 km», «este auto lleva 60 días», «entraron 3 búsquedas nuevas para tu Amarok».
4. **Qué comprar.** «En tu zona se buscan Etios 2018–2020 hasta $X y casi no hay oferta». Sale de las búsquedas sin resultados que ya medimos.
5. **Consultas.** Una bandeja con cada comprador que pidió que lo contacten, de qué auto y desde qué alerta. La agencia marca el estado: contactado, señado, vendido.

### El comprador

- Le llega el auto de agencia **igual que cualquier otro**: mismo puntaje, misma explicación de precio, con la etiqueta «Agencia · stock confirmado».
- Botón **«Quiero que me contacten»**. Recién ahí la agencia recibe su nombre y teléfono. Sin ese toque, la agencia solo ve números agregados.
- Si eligió «solo particulares», no ve autos de agencia.

### Nosotros

- Medimos el embudo completo: autos cargados → coincidencias → alertas enviadas → consultas → ventas declaradas.
- Es el argumento comercial más fuerte que podemos tener: «este mes te mandamos 11 consultas por 6 autos».

## 4. Fase 0: el cruce manual del TT (esta semana, sin código)

Con la lista de stock que está pasando:

1. Normalizar cada auto contra el catálogo (marca, modelo, versión, año, km, precio).
2. Para cada uno:
   - Comparables y nivel de precio.
   - Búsquedas activas que coinciden: cuántas, y cuántas entran en su precio y su zona.
   - Días que tarda ese modelo en salir del mercado.
3. Un informe de una página para él: los autos con demanda, los caros, los que no busca nadie y 2 o 3 modelos que convendría que compre.

Si salen coincidencias concretas, es la demo y la validación al mismo tiempo. Si salen pocas, ya sabemos que primero va el panel (fase 1) y el canal espera a que crezca la demanda.

**Ojo:** en el informe solo van números agregados. No se muestra ningún dato de un comprador, y una coincidencia con menos de 3 búsquedas se informa como «pocas» (no «1 persona en Ramos Mejía»).

## 5. Fases

| Fase | Qué entra | Para quién | Cómo sabemos que funcionó |
|---|---|---|---|
| **0 · Cruce manual** | Informe a mano del stock del TT | El TT | Le sirve y quiere seguir |
| **1 · Panel de stock** | Alta por link, planilla o a mano; panel con precio, días, demanda; avisos a la agencia | TT y 3–5 agencias de la prospección, gratis | Vuelven al panel cada semana; corrigen precios por nuestra sugerencia |
| **2 · Canal de venta** | Autos de agencia en las alertas, etiqueta, botón de contacto, bandeja de consultas | Las mismas agencias | Consultas por auto por mes; % que termina en venta declarada |
| **3 · Compra y cobro** | «Qué comprar»; vendedores particulares con `agencies_contact_ok`; cobro | Agencias que pagan | Agencias pagas que renuevan |

La fase 1 no toca nada del lado del comprador. Se puede lanzar y medir sin riesgo para la confianza de quien busca.

## 6. Decisión técnica clave: el stock como avisos de una fuente nueva

Recomendación: cada auto cargado por una agencia es un **`listing` de una fuente propia** (por ejemplo `directo`), ligado a la agencia. Así el puntaje, los comparables, las alertas, la ficha, la deduplicación y el filtro de vendedor funcionan sin reescribirlos.

Si la agencia entra por su link de Mercado Libre, sus avisos ya existen en `listings`. Solo los marcamos como suyos (`dealer_id`) y no se duplican.

Tablas nuevas, aproximadas:

- `dealers`: la agencia, su zona y sus links de origen.
- `dealer_members`: qué usuarios la administran (al principio, uno).
- `listings.dealer_id` y `listings.dealer_status`: disponible, reservado o vendido; `confirmed_at`.
- `dealer_vehicle_private`: costo de compra y notas, solo visibles para la agencia.
- `dealer_leads`: comprador, auto, alerta de origen, consentimiento, estado.

Recordatorios de la operación: una tabla con FK a `listings` necesita el worker parado al aplicarla, y reiniciarlo después de agregar columnas a `listings`.

## 7. Reglas que no se negocian

1. **Neutralidad.** El auto de agencia compite con el mismo puntaje. No hay posiciones pagas por delante de un auto mejor o más barato. Si el comprador deja de confiar en las alertas, perdemos la demanda, que es justo lo que le vendemos a la agencia.
2. **Privacidad.** La agencia nunca ve datos de un comprador sin su «quiero que me contacten». Los conteos de demanda van con un mínimo de 3.
3. **Stock vivo.** Un auto cargado a mano que no se confirma en 7 días deja de enviarse en alertas hasta que la agencia lo confirme. Los sincronizados por link se confirman solos con cada lectura. Avisar un auto ya vendido quema al comprador y a nosotros.
4. **Etiqueta visible.** Siempre se ve que es de agencia.

## 8. Decisiones para Juan

1. **Cobro del canal:** incluido en Pro ($100.000; $50.000 fundador), por consulta entregada, o mezcla (Pro con N consultas incluidas). Recomendación: piloto gratis hasta tener números de consultas por auto, después decidir con datos.
2. **Contacto:** WhatsApp directo a la agencia (más simple, medimos menos) o formulario nuestro que se reenvía (medimos todo y podemos preguntar después si compró). Recomendación: formulario nuestro y, enseguida, botón a WhatsApp con mensaje armado.
3. **Quién ve autos de agencia:** todos los planes, incluido Free (es más oferta para el comprador). Recomendación: sí, todos.
4. **Ventanita para la agencia:** página pública por auto y por agencia en eseauto (SEO, para compartir). Recomendación: después de la fase 2.

## 9. Riesgos

- **Poca demanda todavía** (~140 búsquedas por semana): en la fase 2 una agencia puede recibir pocas consultas. Por eso la fase 1 vende precio y demanda, no volumen de consultas.
- **Carga y actualización:** si la agencia tiene que mantener el stock a mano, deja de hacerlo. Por eso el link sincronizado va primero.
- **Conflicto con los compradores Pro** que usan Ese Auto para negociar contra agencias. El filtro de vendedor y la neutralidad lo cubren, pero conviene mirarlo en las primeras semanas.
- **Carga del worker:** sincronizar perfiles de vendedor suma lecturas al carril de ML y FB, que es el cuello de botella real (ver escalabilidad). Con pocas agencias no pesa.

# Ese Auto · propuesta comercial y proyección

Fecha: 1 de octubre de 2026. Objetivo confirmado: generar un ingreso complementario rentable durante los primeros seis meses.

Estado: **ruta B seleccionada por el usuario**, con foco en ingreso recurrente. Precios de lanzamiento definidos por el usuario: **Particular ARS 15.000 por 30 días y Agencia ARS 75.000 por mes**. La aceptación comercial y los costos siguen por validar. Este documento no cambia precios, planes ni cobros en producción. El [backlog comercial](BACKLOG_COMERCIAL.md) prioriza los comunes y el módulo B; A y C se conservan como alternativas.

## 1. Qué vender

**Encontrar publicaciones relevantes de autos usados, compararlas y recibir avisos cuando aparecen o cambia su precio, sin revisar varios portales todos los días.**

La diferenciación a validar es la combinación de varias fuentes, filtros útiles, explicación del precio observado y alertas con poco ruido. No vender ahorro garantizado, ganancias por reventa, inspección mecánica ni una tasación: los comparables son precios publicados, no operaciones cerradas. La velocidad se mide desde la detección y depende de cada fuente.

Mercado inicial propuesto: Argentina, empezando por AMBA y un conjunto acotado de modelos con buena cobertura. Esa cobertura debe verificarse en el piloto.

| Público | Necesidad por la que podría pagar | Duración del uso | Canal inicial a probar | Principal dificultad |
|---|---|---|---|---|
| Particular que compra en 1–3 meses | Ahorrar tiempo, comparar opciones, detectar avisos relevantes | Temporal | Comunidades de modelos, contenido con búsquedas reales, referidos | Cuando compra, deja de necesitar el servicio |
| Entusiasta que sigue el mercado | Monitorear varios modelos y cambios de precio | Intermitente | Comunidades y contenido especializado | Puede usar mucho y pagar poco |
| Revendedor independiente / comprador profesional | Encontrar vehículos para evaluar y contactar regularmente | Recurrente | Demostraciones individuales y referidos del rubro | Exige cobertura, relevancia y continuidad |
| Agencia pequeña | Coordinar compras entre varias personas | Recurrente | Venta directa con demostración | Equipos, permisos, soporte y proceso de venta más largo |

La ocupación orienta el mensaje; el acceso se cobra por capacidad. Un particular puede contratar Agencia y un revendedor puede comprar Particular si le alcanza. En la ruta B, Agencia es el nuevo nombre comercial de Pro: mantiene una cuenta y 10 búsquedas. Equipos compartidos siguen en reserva como ruta C; el cambio de nombre/precio no agrega integrantes.

## 2. Qué ya existe y qué falta

Ampliación autorizada el 2/10/2026: cobro y acceso automático por la API de Mercado Pago preparados. Agencia pasa a renovación mensual automática al habilitar la integración; Particular mantiene pago único. Aplicación al entorno destino y validación con el proveedor pendientes. Ver [configuración y pruebas](MERCADO_PAGO.md).

**Actualización 2/10/2026:** marca y piloto asistido implementados en el checkout local. Particular ARS 15.000 y Agencia ARS 75.000, capacidades y prueba única de 72 horas, registro de pagos externos y renovación manual. No publicado ni habilitado en producción. El inventario siguiente describe la inspección inicial anterior a esta implementación; no son los precios nuevos. Ver [implementación y habilitación](IMPLEMENTACION_COMERCIAL.md).

Inspección del código local en `7721e16`, sin consultar métricas ni configuración de producción:

- Ya existen búsquedas, comparables, score explicado, historial de precios, favoritos, alertas web/Telegram/email, modo asistido y administración.
- Existen `free`, `pro`, `pass`, vencimiento, límites configurables, lista de espera y eventos de intención de pago.
- Los valores predeterminados son Pro USD 15/mes, pase 30 días USD 12 y pase 90 días USD 25. Son hipótesis de lista de espera: no prueban disposición a pagar. La configuración desplegada podría diferir.
- No hay un cobro integrado en el flujo de planes inspeccionado. Los límites vienen desactivados en el seed del piloto.
- El PRD original prioriza particulares. Elegir B cambia la prioridad comercial; elegir C también requiere capacidad de equipos que no forma parte del producto actual.

Evidencia: [PRD](PRD.md), [plan técnico](TECHNICAL_PLAN.md), [planes](../web/lib/pro.ts), [acción de lista de espera](../web/app/app/pro/actions.ts), [configuración inicial](../supabase/seed.sql).

## 3. Referencias de mercado

Precios públicos consultados el 1/10/2026. Las características son las publicadas por cada proveedor; no se probaron sus servicios ni su volumen de ventas.

| Referencia | Precio publicado | Cómo usarla en esta decisión |
|---|---|---|
| Autoprecios, Argentina | Pack promocional de 100 tokens por ARS 5.000; Empresa muestra ARS 130.000/mes | Hay oferta local de búsquedas y alertas cobradas por consumo. El pack es una promoción y no equivale a un mes ilimitado |
| CarBuy, Uruguay | Beta Personal USD 39/mes, Revendedor USD 99/mes, Empresa MAX USD 199/mes | Referencia regional de segmentación por comprador y profesional; no trasladar esos precios automáticamente a Argentina |

Fuentes: [Autoprecios](https://autoprecios.com.ar/planes) y [CarBuy](https://car-buy.app/register). Esto fundamenta qué alternativas probar, no demuestra que Ese Auto pueda vender a esos precios.

## 4. Alternativas iniciales conservadas como referencia

**Archivo de la comparación inicial en USD. Los precios de esta sección quedaron sustituidos, para la ruta B, por los importes en ARS de la sección 5. A y C no son ofertas activas.** La opción C se denomina Agencia Equipos para distinguirla del plan Agencia individual seleccionado en B.

| Ruta | Oferta base propuesta | Ventaja | Costo comercial y de producto | Encaje con el objetivo |
|---|---|---|---|---|
| **A · Comprador particular** | Free + Compra mensual USD 15; como alternativa de compra, pases USD 19/30 días o USD 39/90 días | Se parece al MVP actual y es fácil de explicar | Mucha reposición de clientes después de cada compra; adquisición sensible al precio | Útil si ya tenés llegada a comunidades de compradores |
| **B · Mixta, seleccionada** | Hipótesis inicial: Compra 30 días USD 19 + Pro USD 49/mes; sustituida por Particular ARS 15.000 + Agencia ARS 75.000/mes | El particular paga por su búsqueda; el profesional aporta recurrencia | Dos mensajes comerciales, pero cuentas individuales y gran parte del producto compartida | Mejor balance entre ingreso recurrente y mantenimiento |
| **C · Agencia Equipos** | Prueba guiada + Agencia Equipos USD 129/mes, 3 integrantes y 30 búsquedas compartidas | Mayor ingreso por cliente | Organizaciones, permisos, colaboración y más acompañamiento | Conveniente si ya tenés agencias interesadas y tiempo para atenderlas |

En A, mensual y pases tienen capacidad comparable de 3 búsquedas. El mes recurrente cuesta menos que 30 días sin renovación; el pase de 90 días ofrece descuento por compromiso. En B, el pase tiene 3 búsquedas y Pro 10: no vender un pase barato con exactamente la misma capacidad que Pro.

La opción C puede empezar validando con cuentas individuales durante una demostración, pero no debe anunciar equipos compartidos hasta implementarlos. Si exige atención constante, deja de servir como ingreso complementario.

### Exploración inicial de precios, archivada

USD de referencia usados en la comparación inicial. No son precios publicados ni una conversión a pesos. La oferta seleccionada ya tiene precios en ARS en la sección 5; esta tabla conserva las hipótesis anteriores, no experimentos activos.

| Producto | Entrada | Precio base propuesto | Precio alto a validar | Capacidad propuesta |
|---|---:|---:|---:|---|
| Compra mensual, solo A | 9/mes | 15/mes | 19/mes | 3 búsquedas activas, 1 persona |
| Compra 30 días, A o B | 12 | 19 | 29 | 3 búsquedas activas, pago único |
| Compra 90 días, A; opcional después en B | 25 | 39 | 59 | 3 búsquedas activas, pago único |
| Pro, B | 29/mes | 49/mes | 69/mes | 10 búsquedas activas, 1 persona |
| Agencia, C | 79/mes | 129/mes | 199/mes | 30 búsquedas compartidas, 3 personas |

Estos fueron puntos de precio para comparar, no planes simultáneos. Ahora se parte de los precios elegidos en pesos; cualquier experimento posterior requiere una nueva decisión y una oferta comparable.

## 5. Oferta seleccionada en pesos: B

Los importes de lanzamiento son nominales en pesos argentinos, no una conversión diaria del dólar. Mantenerlos durante el período comprado; cualquier revisión posterior debe tener fecha, condiciones y comunicación previa. Definir el tratamiento impositivo/comprobante antes de publicar el precio final de checkout.

| Prestación | Free · prueba de 3 días | Particular | Agencia |
|---|---|---|---|
| Precio de lanzamiento | ARS 0 | **ARS 15.000 por 30 días, pago único** | **ARS 75.000/mes, renovación explícita** |
| Duración | 72 horas desde la primera activación de búsqueda gratuita | 30 días desde la confirmación del pago | Cada período mensual pagado |
| Búsquedas activas | 1 | 3 | 10 |
| Nuevas coincidencias | Resumen diario | Aviso cuando se detectan | Aviso cuando se detectan |
| Resultados de cada búsqueda | Vista de hasta 50 resultados | Todos los disponibles, paginados | Todos los disponibles, paginados |
| Comparables, score explicado y advertencias | En las fichas disponibles | Incluidos | Incluidos |
| Historial y favoritos | Capacidades actuales | Incluidos | Incluidos |
| Canales | Web y canales existentes configurados | Web, Telegram y email configurados | Web, Telegram y email configurados |
| Uso compartido | No | No | No |
| Al vencer | Se pausa la búsqueda y cesan las actualizaciones y alertas | Sin acceso activo, salvo tiempo restante de una prueba ya iniciada | Al final del período pagado si se cancela; misma regla de prueba restante |

**Free permite una búsqueda durante 3 días, una sola prueba por cuenta.** Regla operativa propuesta: contar 72 horas corridas desde la primera activación de una búsqueda gratuita, no desde el registro. Editar, pausar, borrar o reemplazar la búsqueda no reinicia ni detiene ese plazo. Al vencer, se conservan historial y favoritos para consulta; para recibir nuevos resultados, actualizaciones o alertas hay que contratar Particular o Agencia. La prueba no genera ningún cobro automático.

Contratar un plan pago no pausa el reloj de Free; cancelar o vencer un plan pago tampoco inicia ni renueva la prueba. Solo puede quedar acceso gratuito por el tiempo aún vigente de una prueba ya iniciada. Los detalles operativos del plazo se documentan como supuestos de implementación para hacer concreta la duración elegida.

Una búsqueda es un perfil de vehículo/filtros; tres modelos guardados por el asistente cuentan como tres. Pausar libera capacidad activa; no borra favoritos ni historial. Esta definición requiere ajustar el conteo actual, que cuenta perfiles creados.

Para lanzar, mantener el tope actual de 10 avisos inmediatos de nuevas coincidencias por persona y día; el resto va al resumen. Las bajas de precio de favoritos mantienen la excepción actual de aviso inmediato mientras haya prueba Free o plan pago vigente. Al vencer todo acceso, también cesan esas alertas y los resúmenes pendientes. Comunicar ambas reglas; no prometer alertas ilimitadas. Revisar el tope con uso real antes de crear otra diferencia por plan.

El límite de 50 es una vista de resultados, no información secreta ni un muro que impida encontrar la publicación en su portal original. Los datos de usuarios sí deben seguir protegidos. Mantener visible la calidad del análisis ayuda a demostrar valor sin construir nuevos bloqueos.

No prometer rastreo más frecuente exclusivo: los targets se comparten y `crawl_priority` no tiene un consumidor encontrado en el código inspeccionado. La diferencia inicial es volumen de búsquedas y modalidad de notificación.

## 6. Proyección a seis meses

**Simulación de viabilidad, no pronóstico de ventas.** No tenemos tráfico, conversión, costos operativos ni retención reales auditados. Mes 1 es el primer mes con cobro habilitado; el desarrollo y la validación previos quedan fuera de estos seis meses. La proyección vigente de B se expresa en ARS, con precios nominales constantes de ARS 15.000 y ARS 75.000. No supone aumentos por inflación ni una evolución del dólar.

Separamos MRR (suscripciones mensuales Agencia), ventas de Particular y excedente operativo. Particular es un pase y no suma MRR. Las cifras no incluyen impuestos del negocio, remuneración efectiva del dueño ni inversión inicial de desarrollo. Se mantiene el presupuesto anterior de costos en USD, convertido con **ARS 1.500/USD como supuesto de planificación, no cotización actual**. La columna que valora horas descuenta ARS 22.500/h (USD 15 × 1.500), también supuesto editable, no tarifa de mercado.

### Supuestos de B

- Agencia ARS 75.000/mes; Particular ARS 15.000 por 30 días. Se parte de cero clientes pagos; se conservan las hipótesis de altas, bajas y volumen para aislar el efecto del cambio de precios, sin afirmar que la demanda será idéntica.
- Suscriptores del mes = suscriptores previos × (1 − bajas mensuales) + altas nuevas. Bajas significa cancelación o pérdida de acceso pago.
- Se supone que las altas pagan al comienzo del mes. Por eso la simulación simplifica cobros y prorrateos. Los decimales representan valores esperados, no personas fraccionadas.
- Reserva del 8% de ventas para cobro y devoluciones. **No es una comisión oficial de Mercado Pago**; sustituir por costos efectivos de la cuenta y su tratamiento fiscal.
- Reserva variable mensual al tipo de cambio supuesto: ARS 4.500 por Agencia, ARS 750 por Particular vendido y ARS 225 por persona que usa la prueba Free durante el mes (USD 3, 0,50 y 0,15 respectivamente). Son asignaciones para dimensionar margen, no costos marginales medidos. La ingesta depende especialmente de modelos/fuentes/cadencia, no solo de usuarios. Se conserva esta reserva por prueba sin prorratearla automáticamente a 3/30; todavía no hay evidencia para recalcular costos o conversión por la nueva duración.
- Infraestructura base: ARS 150.000/mes (USD 100 al cambio supuesto): web 30.000, base de datos 37.500, operación del worker 52.500 y otros servicios/reserva 30.000. No se contrataron servicios.
- Como referencias, Vercel publica Pro desde USD 20/mes y Supabase Pro desde USD 25/mes, sujetos a consumo e impuestos. Vercel Hobby restringe su uso a proyectos personales no comerciales; contemplar hosting apto antes de lanzar cobros. [Vercel precios](https://vercel.com/pricing), [Vercel Hobby](https://vercel.com/docs/plans/hobby), [Supabase precios](https://supabase.com/pricing).

| Supuesto mensual / al mes 6 | Prudente | Base | Favorable |
|---|---:|---:|---:|
| Prospectos profesionales calificados por mes | 10 | 20 | 32 |
| Conversión de prospecto a Agencia pago | 20% | 25% | 25% |
| Nuevas cuentas Agencia por mes | 2 | 5 | 8 |
| Bajas Agencia por mes | 12% | 8% | 5% |
| Particular vendidos en mes 6 | 4 | 12 | 25 |
| Personas que usan Free durante mes 6, costo de prueba separado del pago | 100 | 250 | 500 |
| Infraestructura mensual, ARS | 150.000 | 150.000 | 225.000 |
| Captación en efectivo mensual, ARS | 45.000 | 112.500 | 225.000 |
| Horas del dueño por mes, operación y captación | 20 | 20 | 32 |

Los prospectos calificados son personas del segmento que ya aceptaron evaluar el producto; no son visitas web ni mensajes enviados. En el base, los pases crecen 2, 4, 6, 8, 10 y 12 por mes y las personas que usan Free durante cada mes son 50, 80, 120, 160, 200 y 250. Son usuarios únicos con prueba vigente en algún momento del mes, no 250 búsquedas gratuitas simultáneas o permanentes. Si luego pagan, se contabiliza además el costo de su acceso pago, sin sumar Free al MRR. Para llegar a 12 pases con 5% de conversión de nuevos compradores activados se necesitarían 240 activaciones de compradores ese mes; validar ese flujo y la conversión de la prueba de 3 días antes de asumirlos como resultados reales.

### Resultado mensual en mes 6, ruta B · ARS

| Concepto | Prudente | Base | Favorable |
|---|---:|---:|---:|
| Cuentas Agencia activas esperadas | 8,9 | 24,6 | 42,4 |
| MRR | 669.495 | 1.845.211 | 3.178.897 |
| Ventas de Particular | 60.000 | 180.000 | 375.000 |
| Ventas totales del mes | 729.495 | 2.025.211 | 3.553.897 |
| Costos y reservas, con captación | 319.029 | 600.480 | 1.056.296 |
| **Excedente antes de impuestos y horas** | **410.466** | **1.424.731** | **2.497.602** |
| **Restando el valor de las horas del dueño** | **−39.534** | **974.731** | **1.777.602** |

El escenario prudente no alcanza a remunerar el tiempo al valor supuesto. El base puede servir como ingreso complementario si la operación cabe en unas 20 horas mensuales. Ambos dependen de conseguir clientes, sostener la cobertura y de los costos en pesos efectivos.

### Evolución del escenario base B · ARS

| Mes | Agencia esperados | MRR | Particular, ventas | Ventas totales | Costos/reservas | Excedente antes de impuestos y horas |
|---|---:|---:|---:|---:|---:|---:|
| 1 | 5,0 | 375.000 | 30.000 | 405.000 | 330.150 | 74.850 |
| 2 | 9,6 | 720.000 | 60.000 | 780.000 | 389.100 | 390.900 |
| 3 | 13,8 | 1.037.400 | 90.000 | 1.127.400 | 446.436 | 680.964 |
| 4 | 17,7 | 1.329.408 | 120.000 | 1.449.408 | 500.217 | 949.191 |
| 5 | 21,3 | 1.598.055 | 150.000 | 1.748.055 | 550.728 | 1.197.328 |
| 6 | 24,6 | 1.845.211 | 180.000 | 2.025.211 | 600.480 | 1.424.731 |

Totales de seis meses sin redondear cada fila: ventas ARS 7.535.074; excedente antes de impuestos/horas ARS 4.717.964; después de valorar 120 horas a ARS 22.500, ARS 2.017.964. No recuperan automáticamente el desarrollo inicial: su costo se resta aparte.

Fórmula para reproducir B en ARS: `excedente = (75.000 × Agencia + 15.000 × Particular) × 0,92 − TC × (3 × Agencia + 0,50 × Particular + 0,15 × Free + infraestructura_USD + captación_USD)`, con `TC = 1.500` en las tablas. Los precios de venta en ARS no dependen de TC.

### Comparación inicial A/B/C en USD · archivada, no vigente

La siguiente comparación conserva el análisis previo al cambio de precios. Sus importes y resultados de B quedaron sustituidos por las tablas en ARS anteriores; no usarla para presupuestar la oferta seleccionada. A y C siguen siendo alternativas sin precio en pesos aprobado.

No es una competencia con condiciones idénticas: cada ruta necesita un embudo distinto. Estos supuestos permiten apreciar escala y carga; no prueban cuál va a vender mejor.

| Ruta, escenario ilustrativo al mes 6 | A: particulares | B: mixta | C: agencias |
|---|---:|---:|---:|
| Precio recurrente | 15 | 49 | 129 por equipo |
| Altas nuevas por mes / bajas mensuales | 20 / 30% | 5 / 8% | 2 / 5% |
| Embudo requerido por mes | 200 compradores activados × 10% | 20 prospectos calificados × 25% | 10 agencias calificadas × 20% |
| Clientes recurrentes esperados | 58,8 | 24,6 | 10,6 |
| MRR | 882 | 1.206 | 1.367 |
| Pases adicionales vendidos en mes 6 | No incluidos | 12 × 19 = 228 | No incluidos |
| Excedente antes de impuestos y horas | 428 | 1.027 | 849 |
| Horas mensuales valoradas a USD 15 | 20 | 20 | 40 |
| Excedente después de valorar esas horas | 128 | 727 | 249 |

Costos históricos de A: fijos 100, captación 150, 500 Free × 0,15, variable USD 1 por suscriptor y reserva de cobro 8%. Costos históricos de C: fijos 200, captación 100, 20 cuentas de demostración × 0,15, variable USD 10 por equipo y reserva de cobro 8%. B en esta tabla usa los antiguos precios USD 49/19 y costos base USD 100 de infraestructura, 75 de captación, 3 por Pro, 0,50 por pase, 0,15 por Free y reserva de cobro 8%. A podría obtener ventas de pases, pero se excluyeron para no contar al mismo comprador también como suscriptor.

### Cuántas cuentas Agencia hacen falta para un ingreso objetivo · ARS

Con ARS 150.000 fijos + 112.500 de captación + 56.250 para 250 personas que usan la prueba Free durante el mes al cambio supuesto, sin depender de vender Particular. Cada Agencia aporta ARS 64.500 después de la reserva del 8% y ARS 4.500 de costo variable:

| Precio Agencia | Cuentas para ARS 750.000/mes de excedente | Cuentas para ARS 1.500.000/mes de excedente |
|---|---:|---:|
| **ARS 75.000/mes** | **17** | **29** |

Son metas ilustrativas, antes de impuestos y de valorar tus horas. Con Agencia a ARS 75.000, cubrir los costos de este modelo requiere 5 cuentas; obtener ARS 1.500.000 además de valorar 20 horas a ARS 22.500 requiere 36 cuentas. No asumir igual conversión al cambiar el precio.

### Sensibilidad al costo en dólares, base mes 6

Los siguientes tipos de cambio son escenarios elegidos para calcular, no cotizaciones verificadas. Mantienen precios de venta y clientes constantes; solo cambia la conversión del presupuesto de costos y horas.

| TC supuesto, ARS/USD | Costos/reservas, ARS | Excedente antes de impuestos y horas, ARS | Restando el valor de horas, ARS |
|---|---:|---:|---:|
| 1.200 | 512.787 | 1.512.424 | 1.152.424 |
| 1.500 | 600.480 | 1.424.731 | 974.731 |
| 1.800 | 688.172 | 1.337.039 | 797.039 |

Al TC supuesto de 1.500, diez horas extra de soporte reducen ARS 225.000 el resultado valorado; USD 100 adicionales de infraestructura reducen el excedente en ARS 150.000. ARS 112.500 de captación / 5 altas Agencia da ARS 22.500 de costo en efectivo por alta solo si se atribuye todo ese gasto a Agencia; no incluye horas comerciales y no es todavía un CAC medido.

## 7. Validación y salida comercial

1. **Semanas 1–2, antes de programar cobros:** 10 entrevistas con profesionales y 5 con compradores; mostrar búsquedas reales y el precio base. Registrar modelos buscados, horas invertidas, utilidad, objeción y aceptación de una oferta concreta. No confundir una lista de espera con una venta.
2. **Piloto pago asistido, al terminar los bloqueantes mínimos:** habilitar hasta 5 Agencia a ARS 75.000 y 5 Particular a ARS 15.000 con enlaces de pago y activación administrativa trazable. En este piloto, Agencia se vende por 30 días con renovación manual explícita; no anunciar renovación automática todavía. Comprobar pago, vencimiento, cobertura y condiciones antes de conceder acceso. Medir pagos confirmados, uso, casos de valor, soporte y renovaciones. Vender solo cobertura comprobada; las personas se incorporan voluntariamente, sin mensajes automáticos a vendedores.
3. **Primeras dos renovaciones:** automatizar el cobro y ampliar si se sostiene la utilidad. Objetivos internos provisionales: al menos 4 de las primeras 5 cuentas Agencia renuevan una vez; al menos 3 relatan un contacto o una visita útil; soporte repetitivo debajo de 20 minutos por pago/mes, más mantenimiento compartido. Con cinco personas son señales cualitativas, no tasas estadísticamente sólidas. La renovación manual mide recompra deliberada; al pasar a automática, medir esa cohorte por separado.
4. **Meses 3–6 desde el lanzamiento pago:** medir altas, bajas por motivo, costo por cliente, costo por fuente/modelo y horas con los precios elegidos. Buscar 17–29 cuentas Agencia activas para el rango ilustrativo ARS 750.000–1.500.000 anterior, sin depender de Particular. Revisar precios con datos y una nueva decisión explícita; no hay un segundo precio autorizado por esta planificación.

Canales iniciales: red propia, demostraciones individuales y contenido con ejemplos verificables. Referidos manuales antes de desarrollar un programa. La publicidad de pago queda como experimento acotado cuando haya conversión observada; los presupuestos de la simulación no autorizan gastos.

Si compran Particular pero no renuevan Agencia, favorecer A. Si varias agencias solicitan equipos y aceptan pagar más, evaluar C. Si hay uso pero nadie paga, revisar el valor y la oferta antes de sumar funcionalidades.

## 8. Decisión a registrar

- Objetivo: ingreso complementario rentable, confirmado.
- Ruta: **B · Mixta, seleccionada por el usuario**.
- Oferta y precios definidos por el usuario: **Free por 3 días + Particular ARS 15.000/30 días + Agencia ARS 75.000/mes**, con 1, 3 y 10 búsquedas respectivamente y una cuenta por plan.
- Particular conserva pago único de 30 días; Agencia conserva renovación mensual. Equipos compartidos siguen en reserva.
- Presupuesto real de operación, tratamiento impositivo/comprobante, política de revisión de precios y meta personal de ingreso: pendientes antes del lanzamiento. El TC de las proyecciones es un supuesto, no un precio de venta ni una cotización de mercado.
- Ejecución: [backlog comercial](BACKLOG_COMERCIAL.md). La planificación está escrita; ninguna tarea figura como implementada por este trabajo.

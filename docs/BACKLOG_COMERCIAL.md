# Ese Auto · backlog comercial

Fecha: 1/10/2026. Objetivo: ingreso complementario rentable. Referencia: [propuesta comercial y proyecciones](PROPUESTA_COMERCIAL.md).

Estado de selección: **B · Mixta, elegida por el usuario**, con foco en ingreso recurrente. PIL-01, COM-01 a COM-10 y B-01/B-02 integran el backlog seleccionado. A y C quedan en reserva. Marca **Ese Auto** y etapa **PIL-01 implementadas localmente** el 2/10/2026. No se activaron cobros ni límites en producción. El estado detallado de cada frente figura debajo; autoservicio sigue condicionado a pagos y recompra.

Precios definidos por el usuario: **Particular ARS 15.000 por 30 días, pago único; Agencia ARS 75.000/mes**. **Free permite una búsqueda por 3 días.** Como regla operativa propuesta, la prueba es única por cuenta y dura 72 horas corridas desde la primera activación de una búsqueda gratuita. Particular corresponde a `pass` con 3 búsquedas activas y Agencia a `pro` con 10 y una cuenta; Agencia Equipos (ruta C) sigue fuera del alcance. En las referencias técnicas siguientes, Pro designa ese mismo acceso Agencia, no un tercer plan pago.

## Estado de implementación al 2/10/2026

| Frente | Estado | Pendiente concreto |
|---|---|---|
| Marca | Implementada: Ese Auto, logo/textos/metadata/email/bot | Dominio, remitente y nombre/usuario del bot externos, revisar disponibilidad de marca antes de lanzar |
| COM-02 / B-01 / B-02 | Implementados: ARS, 1/3/10 búsquedas, tres días, planes y entradas por público | Publicar oferta en el entorno destino |
| COM-03 | Implementado en SQL y worker; prueba única, acceso, capacidad atómica y cola de avisos | Aplicar migración antes de actualizar worker; habilitar límites desde Cobros tras revisar/comunicar cuentas existentes |
| PIL-01 | Implementado: solicitud, pagos verificados, períodos, referencia única y responsable | Configurar enlaces del proveedor fuera de la plataforma, verificar cada operación y conciliar diariamente |
| COM-05 / COM-06 | Etapa asistida: renovación manual, no renovación, devolución ya verificada, acceso e historial en Ajustes | Suscripciones automáticas, impagos y conciliación automática si el piloto valida demanda |
| COM-08 | Registro y tablero básicos: ingresos, Particular, mensualidades Agencia vigentes y devoluciones | Registrar costos/horas y adquisición en planilla; métricas completas de cohortes y bajas por motivo |
| COM-10 | Pruebas locales de permisos, período, capacidad, pagos y alertas; web compilada y vista en móvil/escritorio | Prueba con proveedor real/sandbox y login, publicar y habilitar cohorte limitada |
| COM-01 / COM-07 / COM-09 | Operación externa pendiente | Validar oferta con candidatos, observar cobertura 7 días, presupuesto/hosting, contacto, comprobantes y condiciones |
| COM-04 autoservicio | Condicionado, fuera de PIL-01 | Checkout alojado, eventos verificados y renovación automática después de pagos/recompra |

La mensualidad Agencia vigente es una medida de períodos pagados; no es MRR de suscripciones con débito automático. Las devoluciones del piloto se registran después de verificarlas en el proveedor, por el importe total, empezando por el período más nuevo si existen renovaciones adelantadas. La configuración no modifica el importe histórico de una compra.

[Guía de habilitación y pruebas](IMPLEMENTACION_COMERCIAL.md).

## Regla de alcance

Reutilizar `profiles.plan`, `plan_expires_at`, `app_config`, el motor de notificaciones, las métricas, la pantalla de planes y el backoffice. Agregar el inicio persistente de la prueba Free por cuenta, independiente del vencimiento pago, y la persistencia de cobros necesaria para distinguir transacciones, suscripciones y eventos del proveedor. No crear otro motor genérico de planes ni una plataforma de facturación propia.

P0: necesario antes del primer cobro autoservicio. P1: necesario para evaluar rentabilidad y renovar con confianza. P2: condicional. Esfuerzo orientativo de desarrollo: S = hasta 1 día, M = 2–3 días, L = 4–6 días efectivos. No incluye espera por validación comercial, habilitación del proveedor ni operación del piloto.

## Comunes a cualquier ruta

| ID | Prioridad | Trabajo y resultado | Dependencia | Tamaño / tipo |
|---|---|---|---|---|
| COM-01 | P0 | Validar con candidatos la oferta elegida: Particular ARS 15.000/30 días y Agencia ARS 75.000/mes | Ruta y precios definidos | Comercial, 1–2 semanas de calendario |
| COM-02 | P0 | Unificar pantalla de planes, landing y condiciones: moneda, precio final, renovación, límites y cobertura real | COM-01 | M |
| COM-03 | P0 | Resolver límites efectivos en base de datos y worker, incluida prueba Free de 72 horas, vencimientos pagos y búsquedas activas | COM-01 | L |
| COM-04 | P0 | Registrar compras/suscripciones y conectar checkout alojado del proveedor; confirmar pagos de manera verificable | COM-01, COM-03 | L |
| COM-05 | P0 | Resolver renovación, impago, cancelación, devolución y conciliación, sin perder historial del usuario | COM-04 | M |
| COM-06 | P0 | Cuenta: mostrar acceso vigente, importe/próxima renovación y cancelar; ayuda para cobro fallido | COM-04, COM-05 | M |
| COM-07 | P0 | Verificar cobertura y continuidad con telemetría real; mostrar última actualización y fallas relevantes | COM-01 | M, más observación |
| COM-08 | P0/P1 | Registrar pagos reales antes de cobrar; completar luego el tablero de embudo, renovación, excedente y horas | COM-01; pagos dependen de COM-04 | M |
| COM-09 | P0 | Preparar operación comercial: hosting apto, costos máximos, condiciones, comprobantes y canal de soporte | COM-01, COM-07 | Operación + S en producto |
| COM-10 | P0 | Validar recorrido completo con cobro de prueba, vencimiento y cancelación; habilitar cohorte limitada | COM-02 a COM-09 y módulo seleccionado | M |

### COM-02 · Una oferta coherente

Reutilizar `web/lib/pro.ts`, `web/components/app/pro-plans.tsx`, `web/app/app/pro/page.tsx`, `web/app/app/pro/actions.ts`, `web/app/page.tsx` y `app_config.pro_offer`. Antes de tocar `web`, leer sus instrucciones `AGENTS.md`.

Criterios de aceptación:

- Publicar nombres Particular/Agencia y montos 15.000/75.000 en ARS. Adaptar `pro_offer`, tipos y formato que hoy usan `price_usd`/«USD»; persistir moneda e importe explícitos, no cambiar solo el símbolo. No activar el pase 90 días sin precio elegido.
- La misma oferta/versionado de precio llega a marketing, checkout, confirmación y cuenta. Registrar importe, moneda y duración comprados; cambios futuros no reescriben compras anteriores.
- La lista de espera conserva su significado mientras no hay cobro; después el CTA explica la compra real.
- Reemplazar la promesa actual «Búsqueda cada pocos minutos» por un texto sustentado en cobertura y mediciones. Diferenciar publicación, detección y envío.
- Definir cada búsqueda y qué pasa al pausar, vencer o cancelar. Mostrar el tope de avisos y las excepciones de favoritos.
- Mostrar «Prueba gratis por 3 días», inicio, fecha/hora de vencimiento y estado final. Al vencer, explicar que se conservaron historial/favoritos y ofrecer Particular o Agencia; no iniciar cobros automáticamente.
- Un solo precio base visible por producto; los precios alternativos son experimentos por cohorte, no nuevas tarjetas simultáneas.

### COM-03 · Límites que siguen vigentes al vencer

Reutilizar funciones de la migración `supabase/migrations/20261003120000_f6_backoffice_metrics.sql`; cualquier cambio se agrega con una nueva migración. Revisar `worker/db/repos/notifications.py`, `worker/notifications/service.py`, `worker/notifications/engine.py`, `worker/notifications/dispatch.py`, `worker/pipeline/crawl.py`, `web/lib/pro.ts` y las consultas de resultados.

Hallazgos que justifican el trabajo:

- `plan_limits_for()` reconoce vencimientos, pero el trigger de frecuencia actúa al insertar/cambiar la búsqueda. Los lectores de audiencias del worker inspeccionados usan la frecuencia almacenada, sin consultar el plan efectivo.
- El límite de cantidad cuenta perfiles creados, incluidos pausados. La oferta propuesta cobra por búsquedas activas.
- La vista web corta resultados; `search_results()` acepta límite/desplazamiento sin aplicar el plan. No presentar el corte visual como protección de datos.
- `crawl_priority` aparece en configuración/documentación, sin aplicación encontrada en la ingesta. No ofrecer cadencias exclusivas como prestación lista.

Criterios de aceptación:

- Crear y reactivar búsquedas aplica el límite activo de forma atómica, incluso ante dos solicitudes simultáneas. Múltiples modelos del asistente consumen la capacidad correcta y muestran qué se pudo guardar.
- Registrar una sola vez y desde el servidor el inicio de Free (por ejemplo `free_trial_started_at` en `profiles`) al activar la primera búsqueda gratuita; una creación fallida no consume la prueba. Derivar el vencimiento a las 72 horas con tiempo del servidor, independiente de `plan_expires_at`. Pausar, editar, borrar, reemplazar o reactivar búsquedas no reinicia ni detiene el reloj; el cliente no puede modificarlo.
- El plan efectivo se aplica al preparar y despachar alertas, incluida la cola pendiente; una búsqueda antigua no conserva beneficios por tener un valor guardado antes del vencimiento.
- Al vencer Free sin plan pago vigente, el servidor deja de permitir búsquedas activas o nuevos resultados/actualizaciones. Pausar su demanda en crawl, rematch y seguimiento de favoritos, y detener alertas/resúmenes pendientes antes del envío. El cese no depende de que el usuario vuelva a abrir la web ni debe detener targets compartidos que usan otras cuentas habilitadas.
- Al vencer/cancelar un plan pago no se inicia ni reinicia Free. Si una prueba ya iniciada aún tiene tiempo, puede conservarse una búsqueda elegida por el usuario (la más antigua si no elige); si no, todas se pausan. Las excedentes nunca se borran. El reloj de Free tampoco se pausa al contratar un plan.
- Favoritos e historial ya guardados sobreviven para consulta. La excepción de avisos de baja de favoritos solo se aplica con prueba Free o plan pago vigente; no puede mantener monitoreo gratis después de las 72 horas.
- El servidor aplica la vista de resultados contratada en los caminos normales de consulta. Si se pretende convertirla en un muro de acceso, primero revisar también vistas/tablas accesibles por Supabase; no basta modificar la pantalla.
- Prueba integrada mínima de límites: antes de 72 horas la búsqueda Free funciona; exactamente al vencer cesa el acceso activo, incluidos favoritos y notificaciones en cola. Editar/pausar/borrar/recrear no renueva el plazo. Pagar restaura la capacidad contratada; vencer el pago no regala otra prueba. Verificar también una prueba con tiempo restante y conservar historial en todos los casos.

### COM-04 y COM-05 · Cobro y ciclo de vida

Candidato para Argentina: Mercado Pago, con pago único para pases y suscripción para mensualidades. La documentación describe cobros recurrentes y checkout por enlace; la cuenta, medios habilitados y costos deben verificarse durante la integración. [Documentación oficial de suscripciones](https://www.mercadopago.com.ar/developers/es/docs/subscriptions/overview).

Trabajo propuesto en `web/app/api/` y nuevas migraciones; son ubicaciones futuras, no componentes que ya existan.

- Persistir usuario propietario, oferta/precio comprado, identificadores únicos del proveedor, importe, moneda, estado y período pagado. Guardar solo datos necesarios; el checkout del proveedor captura los datos de tarjeta.
- Checkout debe cobrar `currency = ARS` e importe 15.000 para Particular o 75.000 para Agencia, validado del lado del servidor. El tipo de cambio de las proyecciones solo estima costos; no interviene en el importe cobrado.
- El cliente no fija precio ni concede Pro. Un redirect exitoso no es evidencia de cobro: verificar el estado con el proveedor.
- Validar la autenticidad de notificaciones según la integración elegida, aplicar eventos idempotentemente y consultar el estado vigente para resolver eventos fuera de orden. Un webhook repetido no duplica acceso ni extiende un pase dos veces.
- Separar «suscripción autorizada» de «período pagado». Pases duran 30 días desde la confirmación; en la primera versión, no permitir superponer compras incompatibles ni recomprar un pase vigente sin una regla explícita.
- Cancelación detiene futuras renovaciones y mantiene acceso hasta el fin ya pagado. Vencido/impago aplica el estado de acceso de COM-03: solo queda Free si una prueba ya iniciada sigue vigente, sin conceder otra. Inicialmente sin prorrateos ni período de gracia oculto. Una devolución total revoca el período asociado según las condiciones publicadas.
- Conciliación periódica recupera un webhook perdido. Registrar errores y dar un camino de revisión administrativa con trazabilidad.
- Prueba mínima de dinero: pago válido/pendiente/rechazado; evento repetido/fuera de orden; usuario ajeno; cancelación y devolución. Usar sandbox del proveedor y base de pruebas, nunca vaciar datos del piloto.

### COM-06 · Autogestión

Extender `web/app/app/settings/` y la pantalla de planes. El usuario ve plan efectivo, fecha de fin o próxima renovación, precio/moneda y estado del cobro. Puede cancelar con confirmación clara y comprobación posterior del estado; la baja de emails y la baja de suscripción son acciones distintas. Mantener acceso y mensajes útiles mientras un pago está pendiente.

### COM-07 · Producto que se puede prometer

Reutilizar `collector_runs`, `worker_heartbeat`, alertas operativas, administración y los scripts de `ops/`. No reescribir el supervisor ni agregar infraestructura antes de medir.

- Observar al menos 7 días consecutivos: fuentes operativas por modelo/zona, retraso de ingesta, tiempo detección→envío, fallas, recuperaciones y ruido. La ventana es un criterio interno propuesto.
- Publicar cobertura respaldada por esa observación. Definir metas por fuente antes de ofrecer velocidad; no confundir `first_seen_at` con fecha de publicación.
- Mostrar degradación/frescura y evitar cobrar por una promesa de cobertura que se sabe incumplida. Definir el procedimiento de soporte en una interrupción prolongada.
- Medir costo por target y por usuario, trabajos asistidos y errores de IA. Mantener formulario manual como alternativa; el asistente no puede ser un bloqueo del producto pago.
- Verificar que el proveedor de IA y su modalidad de uso son adecuados para producción; presupuestar la API o alternativa elegida. No asumir que una suscripción personal implica costo comercial cero o capacidad ilimitada.

### COM-08 · Medir rentabilidad, no solo intención

Extender `web/app/admin/metrics/page.tsx`, `web/lib/events.ts` y las vistas existentes. Capturar segmento opcional, origen de adquisición y oferta vista. Separar `waitlist_joined` de pago confirmado y de renovación.

Tablero mínimo: inicio de prueba Free → primer resultado útil → vencimiento/conversión → oferta → checkout → pago confirmado; MRR solo de suscripciones vigentes; ventas de pases por separado; bajas por motivo; devoluciones; renovaciones elegibles y completadas; costos y horas del dueño. Medir conversión por cohorte de prueba y personas que usaron Free durante el mes, sin contarlas como búsquedas permanentes. Excluir admins, cuentas de prueba técnicas y reintentos duplicados. Distinguir bajas por «ya compré» de abandono por falta de valor.

Prueba mínima: la misma transacción recibida dos veces cuenta una vez; un pase no suma MRR; un suscriptor vencido deja de contarlo. Un registro manual semanal de costos/horas alcanza inicialmente.

### COM-09 · Operación comercial

- Comparar el hosting actual con los requisitos de uso comercial y fijar un presupuesto. No contratar planes ni mover el worker por este documento.
- Revisar cobertura permitida y continuidad de las fuentes: el README ya señala limitaciones de sesión y condiciones de Facebook; no tratar todos los portales como fuentes garantizadas.
- Definir moneda, impuestos/comprobante, cancelaciones, devoluciones y revisión de precios con asesoramiento adecuado al negocio. Actualizar `web/app/terminos/` y, si cambia el tratamiento de datos, privacidad. Esto es una tarea de preparación, no una conclusión jurídica.
- Verificar login, emails de acceso y canal de soporte. Definir horario razonable; no vender soporte 24/7.

### COM-10 · Salida controlada

Recorrido: registrarse → activar búsqueda y prueba de 72 horas → encontrar valor → vencer Free → contratar Particular/Agencia → obtener capacidad → recibir aviso → cancelar/vencer → quedar sin acceso activo, salvo prueba iniciada aún vigente. Verificar también compra antes de vencer Free, acceso desde móvil y fallas de pago. Reutilizar las herramientas y pruebas ya instaladas; las pruebas de base/worker usan la base aislada `_test`.

Activar límites gradualmente con tratamiento explícito de usuarios existentes del piloto. Definir y comunicar cómo empieza la prueba de las cuentas actuales antes de habilitar su vencimiento; no inferir retroactivamente un inicio desde la fecha de registro. Revisar cuentas que exceden el límite antes de cambiar `enforced`; no cortar búsquedas silenciosamente. Medir soporte de la primera cohorte antes de abrir adquisición general.

## Módulos según la elección

| ID | Ruta | Agregar / adaptar | Criterio de cierre | Tamaño |
|---|---|---|---|---|
| A-01 | A | Compra mensual y pases 30/90, todos con capacidad de particular; adaptar mensajes y duraciones | El checkout y el vencimiento distinguen renovación mensual de pago único; 90 días no suma MRR | M |
| A-02 | A | Registrar «ya compré» al pausar/cancelar y medir resultado de la búsqueda | Separar éxito de compra de abandono; no obliga a seguir suscripto | S |
| B-01 | B | Configurar Free 1 por 3 días, Particular 3 y Agencia 10 búsquedas activas; ARS 15.000/30 días y ARS 75.000/mes | Oferta, SQL, worker y checkout coinciden; Free no se renueva al recrear búsquedas; `pass` no concede capacidad `pro`; Agencia mantiene una cuenta | S después de COM-03/04 |
| B-02 | B | Dos mensajes de entrada: «busco mi auto» y «busco vehículos habitualmente» | Recomienda Particular o Agencia, conserva elección libre y permite medir ambos públicos | S |
| C-01 | C | Organizaciones, invitaciones, integrantes y permisos; acceso aislado por agencia | Una persona no ve datos de otra agencia; revocar invitación/acceso funciona | L |
| C-02 | C | Búsquedas y favoritos compartidos, asignación simple de contacto y capacidad por equipo | 30 búsquedas y 3 integrantes por agencia; evitar trabajo duplicado dentro del equipo | L |
| C-03 | C | Suscripción propiedad de la agencia y administrador de facturación | Salida de un integrante no cancela ni transfiere el cobro; renovación/cancelación correctas | M |

C modifica la unidad de cobro y acceso de persona a organización. Si se elige C, cerrar ese modelo antes de implementar COM-03/04 para evitar construir dos sistemas consecutivos.

## Secuencia de ejecución seleccionada: B

1. COM-01 + B-02 → oferta local concreta para compradores y profesionales; primeras señales de disposición a pagar.
2. COM-02 y COM-07/09 → promesa verificable y operación posible.
3. COM-03 + B-01 → PIL-01; Free 1 por 3 días, Particular 3 y Agencia 10 búsquedas activas, con registro básico de pagos/horas en ARS y verificación de vencimientos.
4. Si hay pagos y recompra: COM-04 → COM-05/06 → COM-08 → COM-10, cobro autoservicio y ampliación.

**PIL-01 · Piloto asistido antes de automatizar facturación.** Hasta 5 Agencia a ARS 75.000 y 5 Particular a ARS 15.000, con enlaces de pago del proveedor, verificación manual de pago y activación administrativa auditada de plan/vencimiento. Crear únicamente la operación administrativa mínima si no existe; un usuario común nunca puede cambiar su plan. Mantener un registro de transacción, usuario, importe, moneda y período, y conciliar diariamente. Agencia se ofrece como 30 días con renovación manual en esta etapa: no es todavía una suscripción automática. Publicar procedimiento de baja/devolución y ejecutar una prueba de vencimiento. Dependencias: COM-01/02/03/07/09, B-01/B-02 y registro básico de COM-08. Tamaño específico de activación/registro: S–M, además de esas dependencias. No contratar servicios ni emitir enlaces reales como parte de esta planificación.

Orden de magnitud para completar A/B con autoservicio: aproximadamente 25–35 días efectivos de desarrollo y verificación, sujeto a lo que falle en el piloto y al proveedor de cobros. El piloto asistido evita hacer COM-04/05/06 completos antes de comprobar pagos; no elimina sus requisitos para automatizar. La validación comercial y los siete días de observación suman calendario; algunas tareas se pueden solapar. No es una fecha de entrega. A tiempo parcial, dividir las horas estimadas por las horas semanales disponibles; los seis meses de la proyección comienzan al habilitar cobros y no incluyen esta preparación. C agrega aproximadamente 10–15 días efectivos y mayor operación comercial.

## Reserva: implementar solo con demanda demostrada

| Idea | Condición para priorizarla |
|---|---|
| Pase 90 días en B | Usuarios del pase piden más duración y hay suficiente retención |
| WhatsApp | Clientes pagos lo piden y el margen cubre costo por mensajes e integración |
| Más avisos inmediatos / prioridad de rastreo por plan | Mediciones prueban pérdida de valor por el tope o cadencia actual y existe capacidad operativa |
| Exportaciones o informes | Profesionales concretos pagan por ese flujo |
| Suscripción anual | Retención y cobertura demostradas durante varios ciclos |
| Referidos automáticos / cupones | Referidos manuales aportan altas pagas repetidas |
| App nativa, CRM completo, API y marca blanca | Demanda suficiente para recuperar desarrollo y soporte |

No incluir inicialmente comisión por compraventa: la operación cierra fuera de Ese Auto y falta atribución verificable. No incluir mensajes automáticos a vendedores, detección certificada de deuda ni promesas de rentabilidad.

## Registro de decisión

- [x] Objetivo confirmado: ingreso complementario rentable.
- [x] Ruta B elegida; PIL-01, COM-01 a COM-10 y B-01/B-02 seleccionados, A/C en reserva.
- [x] Precios definidos: Particular ARS 15.000/30 días y Agencia ARS 75.000/mes; capacidades de B conservadas (3 y 10 búsquedas, una cuenta).
- [x] Duración Free definida por el usuario: una búsqueda por 3 días; reglas operativas de inicio, no reinicio y vencimiento documentadas en COM-03 para implementar.
- [ ] Presupuesto y condiciones de lanzamiento definidos.
- [x] Implementación autorizada y realizada para marca y PIL-01; publicación y operación comercial pendientes.

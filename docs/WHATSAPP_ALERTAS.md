# Alertas de Ese Auto por WhatsApp

Investigación: 6 de octubre de 2026. Propuesta de integración; el canal todavía no está implementado ni activado.

## Recomendación

Usar WhatsApp Business Platform mediante la Cloud API de Meta y empezar con un grupo pequeño de usuarios que lo soliciten. Como configuración inicial, ofrecer un resumen diario; los avisos inmediatos deben ser opcionales y tener un límite propio. Mantener email como canal de respaldo.

La API directa evita el cargo adicional de un intermediario, aunque requiere operar la conexión, las credenciales y los webhooks. Twilio es una alternativa si se prioriza simplificar el alta y tener soporte del proveedor. La app WhatsApp Business por sí sola no agrega un canal al worker.

| Opción | Ventaja | Costo y límite |
|---|---|---|
| Meta Cloud API directa | Integración con el motor existente, sin cargo de Twilio | Tarifas de Meta por mensajes; operar webhooks y conexión |
| Twilio WhatsApp | Herramientas de alta, pruebas y soporte | Tarifas de Meta + USD 0,005 por mensaje entrante o saliente |
| App WhatsApp Business / enlaces `wa.me` | Útil para atención manual y vinculación | No resuelve alertas automáticas personalizadas desde el worker |

El producto oficial es [WhatsApp Business Platform](https://business.whatsapp.com/products/business-platform). El recargo está publicado en [precios de Twilio](https://www.twilio.com/en-us/whatsapp/pricing).

## Requisitos del producto

Meta exige que el destinatario haya proporcionado su contacto y aceptado recibir mensajes. Las conversaciones iniciadas por la empresa requieren plantillas aprobadas; fuera de las 24 horas posteriores al último mensaje del usuario tampoco se puede usar texto libre. Debe atenderse la baja del canal. Fuente: [política oficial de WhatsApp](https://business.whatsapp.com/policy).

En Ese Auto, el flujo propuesto es:

1. En Configuración, el usuario elige “Recibir novedades por WhatsApp” y la frecuencia. La opción empieza desmarcada y muestra qué recibirá.
2. “Vincular WhatsApp” abre una conversación con Ese Auto y un código de uso único, con vencimiento. El mensaje entrante permite comprobar que controla el número y vincularlo con su cuenta. Esto es una decisión de implementación; no es un requisito específico de Meta.
3. Guardar número normalizado, identificador del destinatario del proveedor, fecha de vinculación y consentimiento, versión del texto aceptado y fecha de baja. No heredar el consentimiento de email.
4. Mostrar estado “Vinculado”, frecuencia y “Desactivar WhatsApp”. También procesar “BAJA”, “STOP” y el botón de baja en los mensajes.
5. Enviar avisos con un enlace a Ese Auto y acceso al aviso, evitando una conversación por cada auto si puede agruparse en el resumen.

Para móviles argentinos, probar explícitamente el formato que devuelve el proveedor y evitar concatenar `+54` sin normalización. No modificar un número personal existente hasta verificar con Meta o el proveedor si puede convivir con la app Business o debe migrarse.

## Plantillas iniciales

Estos borradores deben presentarse y aprobarse; su categoría final la determina Meta. Las oportunidades y recomendaciones de autos pueden entrar en **marketing**. No presupuestar como utilidad solo porque el usuario creó una búsqueda. [Criterios de categorías y aprobación de Twilio](https://www.twilio.com/docs/whatsapp/tutorial/message-template-approvals-statuses).

**`eseauto_resumen_diario` — idioma español:**

> Tu resumen de Ese Auto está listo. Encontramos {{1}} novedades en tus búsquedas: {{2}} publicaciones nuevas y {{3}} cambios de precio. Revisá los detalles en Ese Auto. Podés dejar de recibir estos mensajes cuando quieras.

Botones: “Ver mis búsquedas” con enlace HTTPS a la aplicación, y “Dejar de recibir” como respuesta rápida.

**`eseauto_nueva_coincidencia`:**

> Hay una nueva publicación para tu búsqueda {{1}} en Ese Auto: {{2}}. Precio publicado: {{3}}. Kilometraje informado: {{4}}. Consultá la publicación y la información a verificar en Ese Auto.

Botones: “Ver en Ese Auto” y “Dejar de recibir”. Suprimir el dato ausente mediante una variante aprobada o expresar “no informado”; no completar datos del auto por inferencia. La plantilla y sus variables deben corresponder al evento real.

## Presupuesto de referencia

Meta cobra según país del destinatario y categoría, y publica sus [tarifas oficiales](https://business.whatsapp.com/products/platform-pricing). Twilio publica para Argentina una **referencia de marketing de USD 0,0618** por mensaje en su [tabla de conceptos](https://www.twilio.com/docs/whatsapp/key-concepts#bidding-reference-cheat-sheet); esa tabla indica que se basa en tarifas de julio de 2026.

No fue posible corroborar la tabla vigente de octubre en la documentación de desarrolladores de Meta durante esta investigación. Por eso, estos valores sirven para dimensionar, **no como cotización vigente confirmada**. Revalidar tarifa, categoría, moneda de facturación y posibles cargos del proveedor antes de habilitar envíos. No asumir que la ventana de atención vuelve gratuitas las alertas de marketing.

| Escenario ilustrativo | Mensajes al mes | Meta a USD 0,0618 | Meta + Twilio a USD 0,0668 |
|---|---:|---:|---:|
| 1.000 mensajes | 1.000 | USD 61,80 | USD 66,80 |
| 20 usuarios, 1 resumen/día durante 30 días | 600 | USD 37,08 | USD 40,08 |
| 100 usuarios, 1 resumen/día durante 30 días | 3.000 | USD 185,40 | USD 200,40 |
| 100 usuarios, 5 avisos/día durante 30 días | 15.000 | USD 927,00 | USD 1.002,00 |

Son cálculos a tarifa plana, sin descuentos, impuestos, cambio de moneda, cargos por número o mensajes entrantes adicionales. Solo se envía resumen cuando hay novedades. Establecer un presupuesto mensual y un máximo por usuario; al alcanzarlo, informar la pausa y continuar por email si está habilitado. Evaluar el margen del plan antes de ofrecerlo sin límites.

## Cambios necesarios en este repositorio

El motor ya separa decisión y transporte con `Channel.send(Notification) → SendResult`, pero **no alcanza con agregar un adaptador**:

- Migraciones: agregar `whatsapp` a `public.notification_channel` y a las restricciones de canales en perfiles/búsquedas; crear persistencia de vinculación y consentimiento con acceso restringido. El MVP actual usa email.
- Worker: agregar `notifications/channels/whatsapp.py`, datos de contacto a `Notification` y a las consultas de `db/repos/notifications.py`, y verificar vinculación/consentimiento en `deliverable()` y nuevamente antes del envío. Registrar el adaptador en `main.build_notifier()`.
- Preferencias web: habilitar canal y frecuencia por usuario/búsqueda con validación en servidor, además de los controles visuales. Regenerar los tipos de Supabase después de las migraciones.
- Plantillas: mapear eventos y variables aprobadas. Reutilizar las reglas de coincidencias, bajas de precio, deduplicación y resumen; agregar un cupo de WhatsApp independiente del tope de avisos inmediatos.
- Webhook HTTPS: verificación inicial del proveedor, firma de las peticiones, mensajes de vinculación/baja y estados `sent`, `delivered`, `read`, `failed`, tratados de forma idempotente. Con Meta directo, verificar la firma antes de aceptar el contenido.
- Entrega: almacenar el identificador del proveedor y separar aceptación por la API de entrega al usuario. Un timeout después de un POST puede haber enviado el mensaje: no reintentar a ciegas ni asumir que la idempotencia de Resend existe en WhatsApp. Reintentar errores transitorios comprobables; poner resultados ambiguos en revisión/reconciliación.
- Operación: configuración desactivada por defecto, secretos solo en servidor/worker y presupuesto. No reenviar avisos históricos al activar el canal ni desactivar email si WhatsApp falla.

## Orden para un piloto

1. Resolver número emisor, acceso al Business Portfolio/WABA y proveedor. Confirmar costos antes de contratar o activar facturación.
2. Probar con destinatarios internos y entorno de pruebas del proveedor. El [sandbox de Twilio](https://www.twilio.com/docs/whatsapp/sandbox) admite solo usuarios que se vinculan y no permite plantillas personalizadas: no sustituye la aprobación de nuestras plantillas.
3. Implementar vinculación, consentimiento/baja, preferencias, adaptador y webhook, manteniendo el canal desactivado para los demás usuarios.
4. Aprobar las plantillas y verificar un ciclo real con un destinatario que lo solicite: vinculación → envío → entrega confirmada por webhook → baja → ausencia de nuevos envíos. Ejercitar también el envío fuera de la ventana de 24 horas y un timeout ambiguo.
5. Abrir a un grupo acotado con resumen diario y cupo de gasto. Medir entrega, bajas, clics y costo por usuario antes de ampliar las alertas inmediatas.

No se crearon cuentas, números, plantillas externas ni envíos reales como parte de esta investigación.

# Feedback de la prueba gratis

El pop-up de los 50 resultados incluye **Enviar feedback**. Abre un formulario dentro de la página, sin pedir otra vez el email. Al guardar, `submit_product_feedback` obtiene la identidad y el email de la cuenta autenticada y verifica que la búsqueda le pertenezca.

Cada comentario queda como lead en `product_feedback`, con su búsqueda de origen y el estado del envío. Los usuarios comunes no pueden leer estos registros ni escribirlos directamente; los administradores pueden consultarlos. Se permiten hasta tres comentarios por cuenta en 24 horas. Un identificador de solicitud evita duplicados al reintentar.

El worker revisa la cola cada `NOTIFY_TICK_SECONDS` (60 segundos por defecto) y usa el canal Resend ya configurado. `app_config.feedback_delivery` controla el envío y el destinatario, fijado para esta implementación en **juan.capurro12@gmail.com**. La dirección de avisos de plataforma no cambia. El email permite responder al email de la cuenta que dejó el comentario.

Los reintentos conservan la misma clave de idempotencia de Resend. Un error temporal se reintenta con espera creciente hasta cinco intentos. Un error permanente o el agotamiento de intentos deja el lead en `failed`, con el error, para revisión. Sin canal o destinatario configurado, los leads permanecen pendientes. La confirmación en la página significa que el comentario se guardó; no afirma que el email ya fue entregado.

Para publicar: aplicar la migración `20261118130000_product_feedback_leads.sql`, desplegar la web y actualizar el worker. No habilitar el nuevo loop en un worker cuya base todavía no tenga la tabla.

Verificación local: pruebas de acción/formulario, permisos y límites en SQL, reintentos y exclusión entre workers. El envío real de prueba se ejecutó desde una base local aislada; se verificó su recepción en el Gmail elegido.

# Emails de alerta de Ese Auto

Las alertas inmediatas y el resumen diario usan el logo S Auto, el azul y el
amarillo del sitio, fotos de la publicación y botones que abren la ficha del
auto en Ese Auto. En la ficha se puede consultar el análisis, guardar el auto
y acceder al aviso original.

## Comportamiento

- La alerta individual muestra una foto principal, precio publicado, datos,
  comparación cuando corresponde y el botón. Hasta dos fotos adicionales van
  después del botón para no demorar la acción principal.
- El resumen muestra una foto por tarjeta y un máximo de cinco tarjetas en el
  orden actual de las secciones. Cuando hay más, informa cuántas se muestran y
  enlaza a las búsquedas. La alternativa de texto conserva todos los elementos.
- Los enlaces de fotos, títulos y botones de autos pasan por `/r/<id>?to=detail`;
  los del resumen agregan `&l=<listing_id>`. Conservan el registro de clics
  existente y llegan a `/app/listings/<id>?n=<notification_id>`.
- `listings.images` llega al payload como hasta tres URLs HTTP(S), únicas y
  válidas. Se admiten strings y objetos `{url}`. No se descargan imágenes de
  terceros durante el envío.
- Sin fotos o con payloads anteriores se muestra “Foto no disponible”. Si el
  cliente bloquea imágenes, siguen disponibles el texto, el precio y los enlaces.
  Las imágenes remotas dependen de la disponibilidad del sitio de origen.
- El logo se envía como un PNG inline con Content-ID. El archivo está incluido
  en `worker/notifications/assets/ese-auto-logo.png`: no requiere un nuevo
  despliegue web, un bucket ni una URL pública.
- Se conserva la baja de emails y la baja con un clic, los reintentos,
  la idempotencia, las preferencias y los límites de envío. No se agregan
  píxeles de apertura. Telegram y la bandeja web conservan su comportamiento.
- Sin `WEB_BASE_URL`, los enlaces de autos conservan el destino externo y el
  resumen no oculta resultados: no hay web configurada donde consultar el resto.

## Activación

El cambio es del worker; no requiere migraciones ni nuevas dependencias.
Después de incorporar la rama a `main`, actualizar el checkout del VPS y
reiniciar el servicio existente:

```bash
cd /opt/automotive
git pull --ff-only
systemctl restart automotive-worker.service
systemctl status automotive-worker.service --no-pager
```

`WEB_BASE_URL` debe apuntar a `https://www.eseauto.com.ar`. No ejecutar un
reenvío masivo de notificaciones anteriores: los nuevos envíos usan el nuevo
renderer. Los payloads que ya estaban encolados pueden no tener fotos.

Antes de un envío de prueba real, elegir explícitamente el destinatario. La
validación de esta rama usa Resend simulado: no envía mensajes a usuarios.

## Vista previa y validación

Ejemplos autocontenidos: `design/email-alerts/oportunidad.html` y
`design/email-alerts/resumen-diario.html`. Los valores, precios, fechas y
puntajes son ilustrativos; las fotos provienen de las páginas archivadas en
los fixtures de los parsers. No son ofertas actuales. Los enlaces de muestra
usan `eseauto.example`, para no abrir notificaciones de usuarios reales.

Para regenerar HTML y capturas de 390 y 800 px, desde la raíz y con los
requisitos del worker y Chromium de Playwright instalados:

```bash
python design/email-alerts/render_previews.py
cd worker
pytest tests/test_notifications_templates.py tests/test_notifications_channels.py \
  tests/test_notifications_engine.py tests/test_notifications_email_media.py -q
```

La fuente del logo está en `design/email-alerts/logo.html`, usando Archivo y
el CSS de la marca existente. El PNG es una captura del elemento `#logo` a
escala 3; se muestra a 132 × 38 px en los emails.

Se verifican fotos desde el payload hasta ambos tipos de correo, destinos por
auto, escape HTML, ausencia de fotos, URLs inválidas, límite del resumen,
alternativa de texto, logo inline y cabeceras de baja. La revisión visual de
Chromium no sustituye una prueba en Gmail, Outlook y Apple Mail.

Referencia del proveedor para la imagen inline:
https://resend.com/changelog/embed-images-using-cid

# MVP del 6 de octubre de 2026

El lanzamiento ofrece una búsqueda gratuita durante 72 horas desde su primera
activación, hasta 50 resultados, alertas en la web y un resumen diario por email.
Particular y Agencia continúan en lista de espera; los cobros automáticos siguen
deshabilitados hasta completar las pruebas de Mercado Pago.

## Configuración

- Worker: `WEB_BASE_URL=https://www.eseauto.com.ar`,
  `EMAIL_FROM=Ese Auto <contacto@eseauto.com.ar>` y `RESEND_API_KEY` válida.
  La clave se guarda en el `.env` ignorado y nunca en el repositorio.
- Web/Vercel: `NEXT_PUBLIC_CONTACT_EMAIL=contact@eseauto.com.ar`.
- `TELEGRAM_ENABLED=false` es el valor predeterminado del MVP. El worker puede
  arrancar sin token de Telegram. Ajustes, dashboard y landing ofrecen web/email.

## Prueba gratuita

La migración `20261010120000_mvp_email_free_trial.sql` cambia los canales
predeterminados a email/web, sustituye la antigua preferencia de Telegram y
conserva las preferencias explícitas de recibir solamente en la web.

`enable_free_trial()` habilita exclusivamente los límites gratuitos. Requiere
un administrador autenticado o el servicio de confianza con `service_role`.
No cambia `commercial_pilot.enabled` ni inicia cobros. Es idempotente.

Las cuentas existentes con búsquedas activas y sin prueba iniciada reciben 72
horas desde la habilitación. Se conserva activa la búsqueda más antigua; las
excedentes quedan pausadas y conservan su historial. Las cuentas nuevas inician
su prueba al activar su primera búsqueda. Editar, pausar o reemplazar no reinicia
el plazo.

## MercadoLibre

La fuente está bloqueada por login/verificación del proveedor. Para preparar
una sesión, desde el checkout operativo:

```powershell
cd C:\Users\Juan\Desktop\AutoMotive\worker
python -m collectors.mercadolibre
```

El propietario completa el ingreso/verificación en el navegador. Cuando puede
ver el sitio normalmente, vuelve a la consola y presiona Enter para guardar
`ml_state.json`. Después hay que comprobar una corrida del scraper con esa
sesión. Un login exitoso no demuestra que el acceso automatizado esté habilitado.
Si el proveedor mantiene el bloqueo, la fuente continúa degradada.

## Verificación

Las pruebas de límites usan exclusivamente la base local `mvp_launch_test`.
El caso de habilitación verifica acceso de 72 horas, pausa de excedentes,
permisos, repetición sin reiniciar y conservación de la lista de espera paga.
El arranque del worker verifica que no se invoque Telegram en el MVP.

Antes de anunciar, completar con una cuenta externa el registro, la confirmación,
la recuperación de contraseña, una búsqueda y la recepción de su resumen.
Un correo de prueba del remitente verifica entrega, pero no sustituye ese
recorrido completo.

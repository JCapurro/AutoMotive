# Ingreso con Google

La web ofrece **Continuar con Google** en ingreso y registro, junto a email y
contraseña. Usa Supabase Auth con PKCE: el servidor guarda el verificador en
cookies, Google autoriza la identidad y `/auth/callback` intercambia el código
por una sesión. Conserva el destino interno `next` y vuelve al login si falla
o se cancela la autorización.

## Activación en Supabase Cloud

El 5/10/2026, después de configurar el proveedor, se verificó
`/auth/v1/settings` del proyecto `dnqyravczgcpuowijbja`: `external.google=true`.
La prueba real desde la versión local completó la autorización de Google,
intercambió el código y abrió `/app/settings`; la sesión persistió al recargar.
La web de producción todavía no incluye el botón y necesita un nuevo despliegue.
Agregar el botón no habilita automáticamente el proveedor: si se deshabilita,
el formulario informa que Google no está disponible y permite usar contraseña.

1. En [Google Auth Platform](https://console.cloud.google.com/auth/clients),
   reutilizá un cliente OAuth de Ese Auto si existe; de lo contrario, creá uno
   de tipo **Web application**. Configurá la marca, audiencia y los scopes básicos
   `openid`, `email` y `profile`. Si la audiencia está en modo de prueba, agregá
   las cuentas de prueba; para usuarios generales debe estar publicada.
2. Configurá el origen web `https://www.eseauto.com.ar` y, para desarrollo,
   `http://127.0.0.1:3000`. Agregá como **Authorized redirect URI** de Google:
   `https://dnqyravczgcpuowijbja.supabase.co/auth/v1/callback`.
3. En [Supabase → Authentication → Providers → Google](https://supabase.com/dashboard/project/dnqyravczgcpuowijbja/auth/providers?provider=Google),
   activá Google y guardá su **Client ID** y **Client Secret**. El secreto queda
   en Supabase; no se agrega a la web, a Git ni a una variable `NEXT_PUBLIC_*`.
4. En [Supabase → URL Configuration](https://supabase.com/dashboard/project/dnqyravczgcpuowijbja/auth/url-configuration),
   usá `https://www.eseauto.com.ar` como Site URL y permití:
   - `https://www.eseauto.com.ar/auth/callback**`
   - `http://127.0.0.1:3000/auth/callback**` para desarrollo con Supabase Cloud.
   El sufijo contempla `next` y `provider` de la URL de retorno.
5. En producción, `SITE_URL=https://www.eseauto.com.ar`. En desarrollo,
   `SITE_URL=http://127.0.0.1:3000`; debe coincidir con el host del navegador para
   conservar la cookie PKCE. No hacen falta nuevas variables en Vercel.
   Se verificó que Vercel Production ya tiene el `SITE_URL` con `www` y la URL
   de Supabase correcta. El dominio sin `www` redirige a `www`.

Google redirige a **Supabase**; Supabase redirige a **la web**. Son dos callbacks
distintos. Confirmá que la URL del proveedor del dashboard coincide con la de
Google antes de guardar.

## Supabase local (opcional)

Si también querés probar con Auth local, configurá `[auth.external.google]` en
`supabase/config.toml` con `enabled=true`, el Client ID y
`secret="env(SUPABASE_AUTH_EXTERNAL_GOOGLE_CLIENT_SECRET)"`. Mantené
`skip_nonce_check=false`. Guardá el secreto en el entorno local y agregá
`http://127.0.0.1:54321/auth/v1/callback` al cliente OAuth de desarrollo.

## Verificación de aceptación

- Desde `/login?next=/app/settings`, continuá con Google sin llenar email ni
  contraseña. Tras autorizar, debe abrir `/app/settings` con sesión vigente.
- Probá un usuario nuevo y uno existente; comprobá que conserva sus búsquedas.
  La aplicación delega la vinculación de identidades a Supabase y no asocia
  usuarios manualmente por un email ingresado en el formulario.
- Cancelá la autorización: debe volver al login con un mensaje de Google y
  conservar `next`, sin mostrar un error de confirmación por email.
- Confirmá que email/contraseña, confirmación y recuperación siguen funcionando.
- El primer ingreso confirmado con Google registra `signup_completed` con
  `method=google`; los accesos siguientes no repiten el evento de alta.

Las pruebas unitarias cubren inicio, errores, callback y redirecciones. El flujo
real necesita un proveedor habilitado y autorización de una cuenta de Google.

Referencia: [documentación oficial de Supabase](https://supabase.com/docs/guides/auth/social-login/auth-google).

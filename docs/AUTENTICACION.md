# Registro y acceso con Supabase Auth

La web usa email + contraseña. Las cuentas existentes conservan su usuario, búsquedas y plan: quienes antes entraban con un link deben usar **Olvidé mi contraseña** para definirla.

- `/login`: `signInWithPassword`.
- `/login?mode=signup`: `signUp`, confirmación por email y reenvío con `resend`.
- `/login?mode=recover`: `resetPasswordForEmail`; respuesta genérica exista o no la cuenta.
- `/auth/confirm`: `verifyOtp` para enlaces con token hash (también funciona desde otro navegador).
- `/auth/callback`: soporta token hash y el intercambio PKCE `exchangeCodeForSession`.
- `/auth/reset-password`: valida la sesión en página y acción, cambia la contraseña con `updateUser` y cierra las sesiones con `signOut`.

Las contraseñas se envían directamente desde la acción al proveedor; no se guardan en tablas, eventos ni estado devuelto a la interfaz. La recuperación no genera `signup_completed`.

## Configuración del proyecto alojado antes de publicar

`supabase/config.toml` configura la instancia local; editarlo no cambia el proyecto alojado.

1. En Supabase Dashboard → Authentication → Sign In / Providers → Email: habilitar email y **Confirm email**. Exigir un mínimo de 8 caracteres. Conservar el SMTP existente.
2. En URL Configuration: Site URL debe coincidir con el `SITE_URL` de Vercel (host canónico). Agregar los destinos `/auth/callback` y `/auth/callback?next=...` a la lista permitida; puede usarse `https://<host-canónico>/auth/callback**` para los destinos internos. Agregar los hosts de desarrollo solo en su entorno.
3. En Email Templates → Confirm signup: copiar `supabase/templates/confirmation.html`, asunto **Confirmá tu cuenta en Ese Auto**. La aplicación envía un RedirectTo con query `next`; la plantilla agrega el token hash y el tipo. No reemplazarlo por un enlace que solo lleve al inicio.
4. En Email Templates → Reset password: copiar `supabase/templates/recovery.html`, asunto **Recuperá tu contraseña de Ese Auto**. El tipo recovery lleva siempre al formulario de nueva contraseña.
5. Publicar la web y verificar con una cuenta de prueba: registro → bloqueo antes de confirmar → email → confirmación → ingreso con contraseña → recuperación → nueva contraseña → rechazo de la anterior. Abrir un email en otro navegador y probar un enlace ya usado.

No es necesario modificar usuarios existentes ni aplicar migraciones SQL. No usar `supabase config push` para copiar toda la configuración local al proyecto alojado.

## Desarrollo

Reiniciar la instancia Auth local para aplicar `config.toml` y las plantillas. Mailpit captura los emails locales. Las pruebas del flujo completo requieren confirmación habilitada y que la web apunte a esa instancia local. Los tests unitarios simulan las respuestas de Supabase; no prueban entrega SMTP real.

Referencia: https://supabase.com/docs/guides/auth/passwords

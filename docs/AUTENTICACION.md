# Registro y acceso con Supabase Auth

La web tiene dos tipos de cuenta:

- **Cuenta completa**: email confirmado + contraseña (o Google). Hace falta para contratar un plan. Las cuentas anteriores conservan su usuario, búsquedas y plan: quienes antes entraban con un link usan **No tengo contraseña: mandame un link para entrar** (o **Olvidé mi contraseña**) y, si quieren, definen una.
- **Cuenta solo-email** (desde el 15/10/2026): la búsqueda gratis pide solo el email, sin contraseña, código ni confirmación. Ver [Búsqueda gratis solo con email](#búsqueda-gratis-solo-con-email).

Rutas:

- `/` (portada): `startFreeSearch` ([web/app/actions.ts](../web/app/actions.ts)) crea la búsqueda gratis con el email.
- `/login`: `signInWithPassword`. Debajo de la contraseña, **No tengo contraseña: mandame un link para entrar** lleva al modo link. Si las credenciales no sirven y el email es de una cuenta solo-email, manda el link para entrar.
- `/login?mode=signup`: `signUp`, confirmación por email y reenvío con `resend`. El link «Crear cuenta» solo aparece para contratar (`next` en `/app/pro`); la portada también cae acá si el alta solo con email está apagada o llegó a su tope. Si el email ya es de una cuenta solo-email, manda el link para entrar en vez de registrar.
- `/login?mode=recover` («Entrá con un link»): `resetPasswordForEmail`; respuesta genérica exista o no la cuenta.
- `/auth/confirm`: `verifyOtp` para links con token hash (también funciona desde otro navegador). Para `type=recovery` solo acepta `next=/auth/reset-password?next=<ruta interna>`.
- `/auth/callback`: soporta token hash y el intercambio PKCE `exchangeCodeForSession`.
- `/auth/reset-password`: valida la sesión en página y acción, cambia la contraseña con `updateUser` y cierra las sesiones con `signOut`. Una sesión solo-email va a `/app/cuenta`.
- `/app/cuenta`: la cuenta solo-email confirma su email y elige contraseña; pasa a cuenta completa.

Las contraseñas se envían directamente desde la acción al proveedor; no se guardan en tablas, eventos ni estado devuelto a la interfaz. La recuperación no genera `signup_completed`.

## Búsqueda gratis solo con email

Migración [20261029120000_email_only_accounts.sql](../supabase/migrations/20261029120000_email_only_accounts.sql); lógica del servidor en [web/lib/email-only.ts](../web/lib/email-only.ts) y [web/lib/account-proof.ts](../web/lib/account-proof.ts).

**Alta (portada).** El visitante escribe qué auto busca (un cuadro de tamaño fijo) y toca «Crear mi búsqueda». Recién ahí se abre un pop-up que pide solo el email: el alta nunca abre la página de login, que queda para «Ingresar» y para contratar un plan. `startFreeSearch` normaliza el email, pasa por los limitadores y busca la cuenta con `auth_account_for_email`:

- **Email nuevo**: el servidor crea la cuenta solo-email con `admin.createUser({ email, email_confirm: true })`, sin contraseña (GoTrue guarda igual un hash bcrypt al azar que nadie conoce). Enseguida `mark_email_only_account(uid)` pone `profiles.email_only = true`; si devuelve false, `admin.deleteUser` y no hay sesión. Después `generateLink({ type: 'magiclink' })` + `verifyOtp` en el cliente con cookies dan la **sesión sin email**: no se manda ningún email y se comprueba que la sesión sea del usuario recién creado. `afterSignIn(..., 'email_only')` registra `signup_completed { method: 'email_only' }` y la web sigue a `/app/searches/new?prompt=…`.
- **Email de una cuenta solo-email**: no hay sesión. Le mandamos el link para entrar a ese email.
- **Email de una cuenta completa** (contraseña o Google, confirmada): no hay sesión sin prueba. El mismo pop-up pide la contraseña (`enterForFreeSearch`, con freno por IP) o manda el link para entrar (`linkForFreeSearch`), y sigue a la búsqueda.

La sesión se emite solo para un email que no existía, en el mismo pedido en que `createUser` funcionó. Nunca para un email existente: eso sería entrar a la cuenta de otro escribiendo su dirección.

**Link para volver = email de recuperación.** Para entrar desde otro dispositivo o navegador (el de Instagram no comparte cookies con Chrome ni Gmail), la app llama `resetPasswordForEmail(email, { redirectTo: /auth/callback?next=/auth/reset-password?next=<destino> })`. La plantilla Reset password es neutra («Entrá a Ese Auto»). Al usar el link, `/auth/confirm` (POST) verifica el token y:

- cuenta solo-email: cierra las demás sesiones con `signOut({ scope: 'others' })` (las de quien haya escrito ese email), borra lo que esa persona pudo dejar con `secure_email_only_account` (factores MFA y el vínculo de Telegram), guarda la prueba de la casilla en `account_proofs` (el `session_id` del JWT, `method = 'email_link'`) y lleva a `/app/cuenta?next=<destino>`;
- cuenta completa: `/auth/reset-password?next=<destino>`, como siempre.

GoTrue guarda un solo token de recuperación por usuario: solo funciona el último link (también `generateLink` lo reemplaza) y vence a la hora (`otp_expiry`). Un segundo pedido dentro del intervalo mínimo devuelve 429 `over_email_send_rate_limit` (también justo después del alta, porque `generateLink` cuenta como envío); la web contesta que espere un minuto, sin afirmar que salió un link. El cupo por cuenta es por hora (`links_per_user_hour`), para que nadie pueda dejar a otro sin poder entrar por un día pidiendo links a su email. Si los limitadores no responden, el link sale igual (queda el límite por email de GoTrue).

Una cuenta con contraseña nunca confirmada (un registro abandonado) también recibe el link desde la portada: el link confirma el email y lleva a elegir una contraseña nueva, que reemplaza la que hubiera puesto otra persona en ese registro.

**`/app/cuenta`.** Con una prueba de menos de 1 hora para la sesión actual: «Elegí una contraseña». La acción usa `getUser()` (comprueba que la sesión siga viva), cierra las demás sesiones, llama `complete_email_only_account(user, session, method)` (que en la misma transacción borra cualquier otra sesión de la cuenta) y recién después `updateUser({ password })`. Con una sesión ya revocada, la página pide cerrar sesión y volver a entrar. Sin prueba: «Confirmá tu email» y el botón que manda el link. Si `next` empieza con `/app/pro`, la contraseña es obligatoria; si no, se puede seguir sin ella.

**Comprar exige cuenta.** `/app/pro` muestra los precios a todos. `startPayment` devuelve `needsAccount` para una cuenta solo-email y `ProPlans` lleva a `/app/cuenta?next=/app/pro?plan=<plan>`. Respaldo en la base: el trigger `billing_checkouts_guard_account` (BEFORE INSERT OR UPDATE OF user_id) rechaza con `account_required`. La lista de espera no cambia.

**Google.** En el callback de Google, si la cuenta es solo-email y una identidad `google` tiene el mismo email verificado, primero se cierran las demás sesiones (si eso falla, la cuenta queda solo-email), se limpian las huellas, se guarda la prueba (`method = 'google'`) y se completa la cuenta. Depende de que Supabase vincule Google automáticamente a la cuenta existente: verificarlo en el proyecto alojado (abajo). En los navegadores dentro de apps (Instagram, Facebook) Google no deja entrar: la web oculta el botón y sugiere abrir la página en el navegador.

Piezas en la base (todas las funciones y tablas nuevas son solo para `service_role`: por defecto Supabase les da EXECUTE a `anon` y `authenticated`, y con eso una sesión solo-email podría completarse sola o la clave anónima enumeraría emails):

- `profiles.email_only`: la única fuente de verdad. Los usuarios no pueden escribirla (el UPDATE de `profiles` se otorga por columna). No usar `app_metadata` (no está al hacer el INSERT y viaja desactualizado en el JWT) ni `encrypted_password` (siempre tiene un hash).
- `account_proofs(session_id, user_id, method, created_at)`: la prueba de la casilla (o de Google) por sesión. El `amr` del JWT no sirve: GoTrue emite `otp` para todo `verifyOtp` con token hash, sea recovery o magic link.
- Trigger `auth_users_guard_email_only` en `auth.users` (BEFORE UPDATE OF encrypted_password, email, email_change): mientras la cuenta sea solo-email, GoTrue no puede ponerle contraseña ni cambiarle el email (`account_required`). Una sesión solo-email puede llamar `updateUser` directo contra GoTrue sin reautenticarse; sin esto, quien escribió un email ajeno dejaría una contraseña que sobrevive a la prueba del dueño.
- `auth_throttle` + `claim_auth_throttle(kind, key, limit, window)`: limitadores por IP y por cuenta. La IP se guarda como HMAC-SHA256 (con `SUPABASE_SERVICE_ROLE_KEY`; IPv6 por /64) y las filas se borran a los 2 días.
- `app_config.email_only_signup` es el interruptor: con `enabled: false` el pop-up dice que por ahora no se pueden crear búsquedas nuevas (no manda al registro). `per_ip_hour` y `per_day` limitan las cuentas nuevas (pasado el tope, el mismo aviso); `links_per_user_hour`, `links_per_ip_hour` y `lookups_per_ip_hour` limitan los links y las búsquedas de cuenta. Se edita desde `/admin/config`. `app_config.llm_limits.email_only_per_user_hour` (5) limita el modo asistido de estas cuentas.
- `admin_users.email_only`: la pastilla «Solo email» en `/admin/users`.

Otros detalles:

- `signOut({ scope: 'others' })` corta los refresh tokens, pero los access tokens ya emitidos siguen valiendo hasta que vencen (JWT ES256, verificados localmente por `getClaims`): hasta 1 hora. Los pasos sensibles (`/app/cuenta`, `startPayment`) usan `getUser()`, y `delete_my_account` exige que el `session_id` del JWT siga existiendo en `auth.sessions`: quien escribió el email no puede borrar la cuenta que el dueño acaba de recuperar.
- No hay doble opt-in: el pie de las alertas dice «¿No fuiste vos? Dejá de recibirlos» ([templates.py](../worker/notifications/templates.py)) y `/baja` funciona sin entrar.
- Un clic en «Ver auto en Ese Auto» (`/r/<id>?to=detail`) sin sesión, de una cuenta solo-email, va a la publicación original en vez de al login.
- Eventos: `signup_completed { method: 'email_only' }` en el alta y `account_completed { method: 'password' | 'google' }` al pasar a cuenta completa (en `/app/cuenta` o con Google). Desde el 15/10/2026 los «registrados» de `v_activation` incluyen las cuentas solo-email.
- Fuera de v1: links firmados en `/r` y `/m` que inicien sesión, cambiar el email de una cuenta solo-email, email de bienvenida y manejo de rebotes.

## Configuración del proyecto alojado antes de publicar

`supabase/config.toml` configura la instancia local; editarlo no cambia el proyecto alojado. No usar `supabase config push` para copiar toda la configuración local al proyecto alojado.

1. En Supabase Dashboard → Authentication → Sign In / Providers → Email: habilitar email y **Confirm email** (lo usan los registros con contraseña). Exigir un mínimo de 8 caracteres. Conservar el SMTP existente.
2. En URL Configuration: Site URL debe coincidir con el `SITE_URL` de Vercel (host canónico). La lista permitida tiene que ser exacta: `https://www.eseauto.com.ar/auth/callback**` (cubre el `next` anidado). Nada de comodines de host: las plantillas mandan el token hash a `{{ .RedirectTo }}`. Agregar los hosts de desarrollo solo en su entorno.
3. En Email Templates → Confirm signup: copiar `supabase/templates/confirmation.html`, asunto **Confirmá tu cuenta en Ese Auto**. La aplicación envía un RedirectTo con query `next`; la plantilla agrega el token hash y el tipo. No reemplazarlo por un enlace que solo lleve al inicio.
4. En Email Templates → Reset password: copiar `supabase/templates/recovery.html`, asunto **Tu link para entrar a Ese Auto**. Igual que la de confirmación, el link es `{{ .RedirectTo }}&token_hash=…&type=recovery`. Si GoTrue rechaza el `redirectTo` lo cambia sin avisar por el Site URL, que no tiene `?`, y el link queda roto: por eso la lista permitida del paso 2. Tampoco mandar recuperaciones desde el Dashboard («Send password recovery» no lleva `redirectTo`): usar `/login` → «Entrá con un link».
5. Publicar la web y verificar con una cuenta de prueba: registro → bloqueo antes de confirmar → email → confirmación → ingreso con contraseña → link para entrar → nueva contraseña → rechazo de la anterior. Abrir un email en otro navegador y probar un link ya usado.

### Checklist de la búsqueda solo con email

1. **Migración `20261029120000_email_only_accounts.sql`, con el OK de Juan.** Antes, mirar `select max(version) from supabase_migrations.schema_migrations` en producción: tiene que ser menor que `20261029120000`. Aplicarla a mano, en una transacción, junto con el insert de la versión exacta en `supabase_migrations.schema_migrations (version, name, statements)`. Nunca `apply_migration` del MCP, `supabase db push` ni `ops/update.ps1`. Es compatible hacia atrás (columna con default, funciones que la web vieja no llama, triggers que solo afectan cuentas solo-email), así que va antes del deploy de la web. Después verificar: `has_function_privilege('anon', 'public.auth_account_for_email(text)', 'execute')` y lo mismo para `authenticated` y cada función nueva dan false; `select reloptions from pg_class where relname = 'admin_users'` da `{security_invoker=true}`; existe la fila `email_only_signup` en `app_config`.
2. **Dashboard → Authentication → Email Templates → Reset password**: pegar el `recovery.html` nuevo y el asunto **Tu link para entrar a Ese Auto**. Se puede hacer en cualquier momento: la web nueva funciona con la plantilla vieja (lleva a `/auth/confirm` sin `next`) y la web vieja con la nueva (`/auth/callback` con token hash pasa a `/auth/confirm`, que para recovery fuerza `/auth/reset-password`). Hacerlo junto con el deploy, porque el texto viejo («Recuperá tu contraseña») confunde a quien nunca eligió una.
3. **URL Configuration**: confirmar que la lista permitida sigue exacta (`https://www.eseauto.com.ar/auth/callback**`).
4. **Rate Limits**: subir «token verifications». El `verifyOtp` del alta y el de `/auth/confirm` corren en el servidor, con las IP de Vercel, y comparten ese balde por IP. Revisar también el límite de emails enviados: es de todo el proyecto y comparte la cuota de Resend (100 por día en el plan gratis) con las alertas.
5. **Allow manual linking: apagado.** La mejora con Google confía en la vinculación automática por email verificado; con la vinculación manual cualquier cuenta de Google podría completar una cuenta solo-email.
6. **JWT expiry: bajarlo a 10 minutos** (muy recomendado). Una sesión cerrada con `signOut({ scope: 'others' })` sigue leyendo y editando por PostgREST hasta que vence su access token; `delete_my_account` ya lo controla, el resto no.
6b. **MFA → TOTP: apagar el enrolamiento** si no se usa (local está apagado). Una sesión solo-email podría inscribir un factor; `secure_email_only_account` lo borra en la primera prueba, pero mejor no permitirlo.
7. Confirmar que **Email OTP Expiration** es 3600 s: los textos dicen que el link vence en 1 hora.
8. **Verificar la vinculación automática de Google en el proyecto alojado** antes de contar con ella: crear una búsqueda solo con un Gmail de prueba y después «Continuar con Google» con esa misma cuenta. Tiene que quedar el mismo usuario (con su búsqueda), `profiles.email_only = false` y un evento `account_completed { method: 'google' }`. Si crea otro usuario o da error, ocultar Google para las cuentas solo-email hasta resolverlo.
9. Anotar acá cómo está la confirmación por teléfono/SMS del proyecto alojado: con autoconfirmación, `signUp` sobre un email confirmado devuelve 422 `user_already_exists`; sin ella, un usuario ofuscado (200 sin identidades). El login contempla las dos.
10. Vercel: `SUPABASE_SERVICE_ROLE_KEY` en Production (también firma el hash de la IP). Después, deploy de la web.
11. VPS: desplegar el worker (cambió el pie de los emails). El repair bot no despliega si hay commits de `main` sin desplegar que tocan `worker/` o `supabase/` ([COLLECTOR_REPAIR.md](COLLECTOR_REPAIR.md)).
12. Prueba en producción con una casilla de Juan: portada → email → búsqueda creada sin abrir ningún email; el mismo email otra vez → link; link → `/app/cuenta` → contraseña; `/app/pro` → «Continuar en Mercado Pago» con una cuenta solo-email pide la cuenta. Al final, borrar esa cuenta desde Ajustes.
13. Las primeras semanas, mirar en Resend los rebotes. La cuota la vigila el monitor: avisa por email al 80% de la diaria o la mensual (`docs/PLATFORM_HEALTH.md`).

## Desarrollo

Reiniciar la instancia Auth local para aplicar `config.toml` y las plantillas; el stack local compartido no se reinicia: para probar la plantilla nueva usar un stack scratch (otro `project_id` y otros puertos). El helper `magicLink` de los e2e acepta la plantilla vieja y la nueva. Mailpit captura los emails locales. Las pruebas del flujo completo requieren confirmación habilitada y que la web apunte a esa instancia local: `startFreeSearch` crea usuarios con la service role, así que nunca probar la portada con el `.env.local` de producción (`playwright.config.ts` se niega a correr contra un Supabase que no sea local). GoTrue local no aplica límites por IP (no recibe `Sb-Forwarded-For`): el comportamiento con IPs compartidas solo se ve en el proyecto alojado. Los tests unitarios simulan las respuestas de Supabase; no prueban entrega SMTP real.

Referencia: https://supabase.com/docs/guides/auth/passwords

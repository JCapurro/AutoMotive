# Confirmación consumida por una vista previa

Diagnóstico del 5 de octubre de 2026. Horas de Argentina (UTC-3).

## Evidencia de producción

El deployment `dpl_5XUte6B1BAkdXqYUMBTejsA8CTCi`, commit `0f348a8`, registró:

| Hora | Vercel | Supabase Auth |
| --- | --- | --- |
| 23:03:19–20 | `HEAD /auth/callback` | `/verify` 200, cuenta confirmada |
| 23:03:22 | `GET /auth/callback` | `/verify` 403, `otp_expired`, `One-time token not found` |
| 23:03:35 | `GET /auth/callback` | Mismo error |
| 23:03:43 y 23:04:06 | Reenvíos desde la aplicación | `/resend` 200 |

La cuenta de esa secuencia conserva `email_confirmed_at` y `last_sign_in_at` de las 23:03:20. Los reenvíos son posteriores a la confirmación. No hace falta volver a registrar esa cuenta: puede ingresar con email y contraseña.

El callback y la ruta de confirmación consumían el token en `GET`. Sin un handler `HEAD` explícito, Next.js también ejecutaba ese handler durante una comprobación `HEAD`. Los logs identifican la petición previa; no identifican qué aplicación la originó.

## Corrección

- `HEAD` en ambos endpoints responde sin verificar tokens.
- `GET` con token hash abre una pantalla de confirmación y conserva el destino seguro.
- La confirmación ocurre mediante un formulario `POST` con verificación de origen. El redirect usa 303 para evitar reenviar el formulario al destino.
- Los enlaces usados vuelven a ingreso; la pantalla explica cómo ingresar si ya se confirmó la cuenta y permite solicitar otra confirmación con email editable.
- El ingreso de una cuenta pendiente ofrece el mismo reenvío, sin repetir el registro.
- La recuperación de contraseña usa la misma pantalla previa, manteniendo el destino de recuperación.
- La pantalla con token no carga GA4 ni Meta Pixel y aplica `strict-origin`: el referrer incluye solo el origen, sin ruta ni token. Conserva el header Origin necesario para validar el formulario.
- Los enlaces hash actuales de las plantillas siguen funcionando. La publicación de este cambio no necesita una migración ni cambios de plantilla.

Supabase documenta el consumo de enlaces por verificaciones previas y la confirmación mediante una pantalla intermedia: https://supabase.com/docs/guides/auth/auth-email-templates#email-prefetching

## Validación y alcance

Las tres regresiones de apertura automática y reenvío fallaron antes de la corrección. Después pasaron 115 pruebas unitarias, typecheck y lint.

Pasaron además las dos pruebas aisladas de navegador, escritorio y móvil: HEAD seguido de GET conserva el token, confirmación manual desde otro contexto, enlace usado, resultado del reenvío, ingreso con contraseña y recuperación con cambio de contraseña. La repetición final de las 25 pruebas específicas de Auth y privacidad también pasó.

El Supabase local compartido tiene autoconfirmación habilitada. La suite completa de registro por correo se detuvo ante esa configuración, como exige la aplicación. La prueba aislada de tokens usa cuentas y enlaces generados por la API administrativa local, sin modificar la configuración ni resetear fixtures compartidos; elimina exclusivamente sus propias cuentas. No demuestra entrega SMTP en producción.

Comando de la prueba aislada: `npm exec playwright -- test --config playwright.auth.config.ts` desde `web/`, con variables de Supabase local en `.env.local`.

Publicación: integrar el cambio en `main` y comprobar el commit del deployment nuevo, `HEAD`, la pantalla previa y el acceso. El diagnóstico de producción de este documento corresponde al commit anterior; las pruebas locales no sustituyen esa verificación del deployment.

Graphify se actualizó con AST local. Reporta cuatro fixtures JSON sin nodos (`argentina-locations.json`, `parse_search_golden.json`, `parse_search_output.json`, `parse_search_recorded.json`); no se usaron para este diagnóstico.

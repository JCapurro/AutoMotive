# Automotive — web

Next.js (App Router, TypeScript) + Supabase (`@supabase/ssr`), Tailwind y
shadcn/ui. Es la capa *Client* del §41: la web nunca habla con el worker, se
comunican por tablas (plan técnico, sección 2).

## Rutas (plan técnico, sección 9)

| Ruta | Qué hay |
|---|---|
| `/` | Landing del §50 |
| `/login` | Email + contraseña; creación de cuenta y recuperación por email |
| `/auth/callback`, `/auth/confirm` | Confirmación / recuperación (PKCE o token hash); recuperación en `/auth/reset-password` |
| `/app` | Dashboard del §28: búsquedas con "N nuevos esta semana · M oportunidades" y oportunidades recientes |
| `/app/searches/new`, `/app/searches/[id]/edit` | Alta y edición estructurada, con preview "N publicaciones actuales coinciden" (`preview_search`) |
| `/app/searches/[id]` | Resultados del §29: filtros, orden, pausar, frecuencia. Mientras el worker hace el backfill, la página se refresca sola |
| `/app/listings/[id]` | Detalle del §23: ¿por qué apareció?, análisis de precio, Opportunity Score, histórico, conviene verificar, preguntas al vendedor, estados, descarte con motivo, guardar y "Compré este vehículo" |
| `/app/listings/[id]/out` | "Ver publicación" con `listing_outbound_clicked` |
| `/app/saved` | Watchlist del §30 |
| `/app/inbox` | Inbox web; el badge se actualiza por Supabase Realtime |
| `/app/settings` | Vincular Telegram (`t.me/<bot>?start=<código>`), canales, frecuencia, ubicación por defecto y «Borrar mi cuenta» (`delete_my_account`) |
| `/app/pro` | «Probar Automotive Pro» (§52): Pro mensual vs Search Pass 30/90 días y la lista de espera. Sin cobro |
| `/r/[notificationId]` | Redirect con tracking de las alertas (sección 7.3) |
| `/privacidad`, `/terminos` | Política de privacidad (Ley 25.326) y términos de uso del piloto, enlazados desde la landing y el login |
| `/baja?t=<token>`, `POST /api/baja?t=<token>` | Baja del email desde el pie de cada alerta, sin login: la página pide confirmar (abrir el link no cambia nada); el POST es el *one-click* de `List-Unsubscribe` (RFC 8058) |
| `/admin/**` | Backoffice (sección 10), solo `profiles.role = 'admin'`: Resumen con los criterios del §53, Métricas, Notificaciones con el inspector «¿por qué se envió?» (`/admin/notifications/[id]`, `/admin/matches/[id]`), Matches, Usuarios, Búsquedas, Listings, Fuentes, Errores y Config |

Las lecturas agregadas son funciones SQL `security invoker`
(`dashboard_summary`, `recent_opportunities`, `search_results`,
`search_result_counts`) sobre la vista `match_cards`; las mutaciones son Server
Actions con el cliente del usuario (RLS). La service role solo se usa del lado
del servidor para `/r/`, para leer `app_config` y en `/admin` (después de
chequear el rol en el proxy y en cada página y acción).

## Correrla

```powershell
cd ..                    # raíz del repo
npx supabase start       # Postgres, Auth, Realtime y Mailpit (http://127.0.0.1:54324)
cd web
copy .env.example .env.local   # completar las keys de `npx supabase status`
npm install
npm run dev -- --hostname 127.0.0.1
```

Usá `127.0.0.1:3000` (no `localhost`): es el `site_url` de Auth local y la
cookie de sesión es por host. Los emails locales de confirmación y recuperación llegan a Mailpit. Configuración alojada: [AUTENTICACION.md](../docs/AUTENTICACION.md).

Para ver resultados sin scrapear: `npm run e2e:seed` carga un mercado de Ford
Fiesta de prueba; después de crear una búsqueda, `python -m tools.rematch`
(desde `worker/`) hace el backfill y `python -m tools.simulate_alert <listing_id>`
simula la llegada de una publicación (solo al inbox web).

## Tests

```powershell
npm run typecheck
npm run lint
npm test          # vitest: helpers y lint del copy prohibido (§19)
npm run e2e       # Playwright: build + start, proyectos desktop y mobile (375 px)
```

El e2e necesita el stack local de Supabase y el entorno Python del worker
(`pip install -r ../worker/requirements.txt`): el backfill y la alerta simulada
corren el código real del worker. Cubre la aceptación de F4: registro,
creación de búsqueda, backfill, alerta simulada que llega por Realtime, clic
(trackeado por `/r/`), "Me interesa" y compra con la pregunta del §38.
`e2e/admin.spec.ts` cubre la de F6: el inspector en un clic desde
Notificaciones, los 6 criterios del §53 en el Resumen, `/admin` cerrado a
quien no es admin y el CTA Pro → planes → lista de espera con sus eventos.
`e2e/f7-account.spec.ts` cubre F7: las páginas legales, la baja del email
(página y *one-click*) y el borrado de la cuenta.

Antes del e2e pará el worker (`python main.py` o la tarea *Worker*): si no, toma
los pedidos del modo asistido que el test simula. Y liberá el puerto 3000: con
`next dev` el overlay de desarrollo tapa la barra de navegación del celular.

El e2e escribe en la base del stack local (la misma que usa la web), pero solo
datos con el prefijo `e2e` (usuarios `@e2e.automotive.test`, publicaciones
`e2e-…`), que el setup borra antes de cada corrida.

Tipos de la base: `npm run gen:types` (regenera `types/database.ts` desde el
stack local).

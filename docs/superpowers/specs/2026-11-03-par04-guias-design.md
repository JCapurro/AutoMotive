# PAR-04 · Guías por modelo y preguntas específicas

Ítem PAR-04 del [backlog de producto](../../BACKLOG_PRODUCTO_2026-10.md) y Fase 3, fila 5, del [plan por fases](../../PLAN_FASES_BACKLOG_PRODUCTO_2026-10.md) (nota 5 de la sección 1 y «Pendiente» de la sección 3). Fecha: 2026-11-03. Rama `claude/par04-guias`, creada desde `origin/main` en `187096f`. Estado: **implementado en la rama, esperando que Juan lo apruebe**. Hay código (migraciones `20261205120000` a `20261205120400`, worker y web; ver «Archivos»), nada se pusheó y nada se aplicó en producción. Al publicar la primera guía cambian `matches.seller_questions` y `contact_questions` de los avisos de ese modelo.

Decisión de Juan del 03/11: el push (F-04) queda **pospuesto**; se arranca PAR-04. PAR-04 no depende de F-04.

Antes de tocar `web/`: leer `web/AGENTS.md` y, en `web/node_modules/next/dist/docs/`, las guías de ISR (`01-app/02-guides/incremental-static-regeneration.md`), JSON-LD (`01-app/02-guides/json-ld.md`), `generateStaticParams`, `generateMetadata`, `revalidatePath` y `sitemap`. En esta web no está activado `cacheComponents` (`next.config.ts` solo tiene `reactCompiler`), así que vale la guía de ISR **sin** Cache Components.

## Alcance

1. Tabla `model_guides`: una guía por (marca, modelo, generación), con cinco secciones fijas, preguntas, fuentes, `status draft | published` y quién la revisó.
2. Generación de un **borrador** con un job `model_guide` en `llm_jobs`: prompt en `worker/llm/prompts/model_guide.md`, validación estricta, cache por (modelo, generación, versión del prompt) y topes propios en `app_config.llm_limits.model_guide`. **La generación queda apagada** (`enabled: false`) hasta que Juan apruebe el proveedor y el tope.
3. `/admin/guides`: los 30 modelos con más búsquedas activas, generar borrador (si está prendido), crear y editar a mano, publicar y despublicar.
4. Páginas públicas `/guias` (índice) y `/guias/<marca>/<modelo>`, con ISR, metadata, FAQ en JSON-LD y CTA «Crear mi búsqueda» con el texto prellenado; sitemap actualizado.
5. `seller_questions.py` suma hasta 3 preguntas de la guía **publicada** del modelo y la generación del aviso, con su origen guardado para el inspector de `/admin`.
6. Eventos `guide_viewed`, `guide_cta_clicked`, `guide_questions_copied` y GA4 `view_item` con `item_category = guide`.

Fuera de alcance: guías por versión o motor, imágenes, comentarios de usuarios, traducción, precios de avisos o cualquier dato de la plataforma en la página pública, `polish_questions` (sigue sin conectar), cambios en `vehicle_catalog.timing_belt`.

Reglas de producto que el diseño hace cumplir:

- **Nada sale a la web sin que Juan lo revise y lo publique** desde `/admin/guides`. RLS: `anon` y `authenticated` solo leen filas `published`. La IA escribe solo borradores.
- La página pública dice **«Guía orientativa»** y avisa que no reemplaza la revisión de un mecánico. Cada afirmación es de la guía, no una verificación de Ese Auto ni de un auto en particular.
- Sin precios de avisos, sin datos de usuarios y sin cifras de demanda en el HTML público.
- El copy sigue [BACKLOG_COMERCIAL](../../BACKLOG_COMERCIAL.md) y el lint de `worker/intelligence/copy.py` y `web/lib/copy.ts`: nada de promesas («garantizado», «certificado», «verificado por Ese Auto»), ni «vale», «valor real», «precio real», «tasación».

## Qué existe hoy (verificado en `187096f`)

- **Capa LLM.** `worker/llm/provider.py` define `LLMProvider` (`parse_search`, `extract_listing_facts`, `polish_questions`, `explain_low_results`) con cuatro implementaciones: `openai` (por defecto, `OPENAI_MODEL = gpt-6-luna`), `anthropic`, `claude_cli` y `local` (stub). `LLM_PROVIDER` se elige por entorno (`worker/config.py:155`). Los prompts son `worker/llm/prompts/*.md` y los esquemas están en `worker/llm/schemas.py` (pydantic). El modo asistido usa `openai`.
- **`llm_jobs`.** `supabase/migrations/20260927120000_core_schema.sql:327`: `user_id uuid not null default auth.uid()` con `on delete cascade`; `kind` con CHECK `parse_search | extract_listing_facts | polish_questions`. RLS (`20260927120100_rls.sql:88`): el usuario lee lo suyo y puede insertar `(user_id, kind, input)` propios en `queued`. Trigger `enforce_llm_rate_limit` (última versión en `20261029120000_email_only_accounts.sql`): `llm_limits.per_user_hour` (30) y `email_only_per_user_hour` (5) **cuentan todos los kinds**. Está en la publicación `supabase_realtime`. `llm_job_stats` agrupa por proveedor, kind y día.
- **Loop del worker.** `worker/pipeline/llm_jobs.py`: `KINDS = ["parse_search"]`; `claim` con `FOR UPDATE SKIP LOCKED`; `expire` falla los `queued` de más de **75 s** (la web cae al formulario) y los `running` de más de `LLM_TIMEOUT_SECONDS + 60`. Los consumidores comparten la cola (`LLM_CONCURRENCY`).
- **Precedente de llamada «de sistema».** El bot de pocos resultados (`20261126120000_low_results_bot.sql`, `pipeline/low_results.py`) llama al proveedor **sin pasar por `llm_jobs`** y guarda `provider` en su propia tabla. Por eso en `llm_jobs` no hay ningún job sin usuario.
- **Respuestas grabadas.** `worker/llm/replay.py` reproduce sobres de `claude -p` guardados en `worker/tests/fixtures/llm/parse_search_recorded.json`; `tools/record_llm.py` los graba (con el CLI real); `tests/test_llm_contract.py` corre el contrato con replay, y con `LLM_SMOKE=1` contra el proveedor real.
- **Preguntas al vendedor.** `worker/intelligence/seller_questions.py` (95 líneas, puro): `question_keys` → `seller_questions` (mensaje completo, `matches.seller_questions`) y `question_texts` (las específicas, hasta 3, sin las genéricas `greeting|available|holder`: email H-01 y `matches.contact_questions` de PRO-01). Los textos están en `copy.QUESTION`. `intelligence/engine.assess` las arma; `pipeline/scoring.Scorer` carga filas con `rows_for_scoring` (`SELECT l.*, vc.timing_belt, vc.model AS catalog_model`); `notifications/service.py:261` recalcula `question_texts` para el email. El inspector de `/admin/matches/[id]` no muestra preguntas todavía.
- **Rescore.** `pipeline/rescore.py` re-evalúa cada `rescore.every_hours` los matches de avisos activos vistos en 14 días y no notifica. `SCORING_VERSION = "f2-v5-seller-margin"`.
- **Catálogo.** `vehicle_catalog (make, model, trim, aliases, year_from, year_to, transmissions, fuels, body_types, timing_belt)`; la fila del modelo tiene `trim is null`. La migración `20261107130000_timing_chain_catalog.sql` sigue **NOT APPLIED** en producción (Juan revisa la tabla de [DISTRIBUCION](../../DISTRIBUCION.md)). Está en `supabase/migrations/`, así que la base local y la de tests sí la tienen.
- **Búsquedas.** `search_profiles.filters ->> 'make' / 'model'`, `enabled`; `search_access_active(id)` dice si la búsqueda está vigente para el plan. En la base local hay 54 búsquedas activas.
- **Web pública.** `web/app/sitemap.ts` (estático: `/`, `/planes`, `/login`, `/privacidad`, `/terminos`), `web/app/robots.ts` (bloquea `/app`, `/admin`, `/r/`, `/m/`, `/api/`, `/auth/`, `/baja`), `web/app/layout.tsx` (metadata base, `es_AR`, GA4, Clarity, Meta Pixel y Vercel Analytics). `SiteHeader` recibe `signedIn` y `page: "home" | "planes"`. La landing (`app/page.tsx`) es dinámica (lee el usuario) y usa `LandingSearch` (alta solo con email, `startFreeSearch`). `searchStartHref` y `?prompt=` llevan el texto a `/app/searches/new` (modo asistido).
- **Clientes Supabase.** `lib/supabase/server.ts` usa cookies (vuelve dinámica la página); `lib/supabase/admin.ts` es service role. No hay un cliente anónimo sin cookies.
- **Eventos.** `events.user_id` admite null, pero la única política es «insert own» (`track()` en `lib/events.ts` exige usuario). No hay forma de registrar un evento anónimo.
- **GA4.** `analyticsEvent()` en `lib/google-analytics.ts` respeta el consentimiento; la ficha ya manda `view_item` (`components/app/view-tracker.tsx`).
- **Admin.** `requireAdmin()` + service role; las escrituras van por RPCs `security definer` con `p_actor_id` concedidas solo a `service_role` (molde: `admin_update_setting`). Navegación en `components/admin/admin-nav.tsx`. `/admin/config` valida claves conocidas en `lib/admin-config.ts`.
- **Proxy.** `web/proxy.ts` refresca la sesión en cada navegación y protege `/app` y `/admin`.

## Decisiones de diseño

### 1. Una guía por modelo y generación; una página por modelo

- La fila es (marca, modelo, generación). `generation_label` puede ser null: «todo el modelo en los años del catálogo». En la primera tanda cada modelo tiene **una** fila con `generation_label` null y la sección «Generaciones» explica los cambios; se pueden sumar filas por generación después sin cambiar nada.
- La URL es por modelo: `/guias/<marca>/<modelo>` muestra todas las filas **publicadas** de ese modelo, ordenadas por `year_from`, con un ancla por generación. Si no hay ninguna publicada: 404.
- Slugs: minúsculas, sin acentos, espacios y signos a `-` (`Volkswagen Gol Trend` → `volkswagen/gol-trend`). Se calculan al guardar (`web/lib/guides.ts`, con su test) y se guardan en `slug_make` y `slug_model`, únicos junto con la generación. No se derivan en SQL (unaccent no es immutable).
- Marca y modelo se eligen del catálogo (`vehicle_catalog`, fila `trim is null`), igual que el formulario de búsqueda; así las preguntas cruzan con `listings.catalog_model`.

### 2. Tabla `model_guides`

```sql
create table public.model_guides (
  id               bigint generated always as identity primary key,
  make             text not null,
  model            text not null,
  generation_label text check (generation_label is null or char_length(generation_label) between 1 and 80),
  year_from        integer check (year_from between 1950 and 2100),
  year_to          integer check (year_to between 1950 and 2100),
  slug_make        text not null check (slug_make ~ '^[a-z0-9]+(-[a-z0-9]+)*$'),
  slug_model       text not null check (slug_model ~ '^[a-z0-9]+(-[a-z0-9]+)*$'),
  body             jsonb not null default '{}' check (jsonb_typeof(body) = 'object'),
  questions        jsonb not null default '[]' check (jsonb_typeof(questions) = 'array'),
  sources          jsonb not null default '[]' check (jsonb_typeof(sources) = 'array'),
  status           text not null default 'draft' check (status in ('draft', 'published')),
  origin           text not null default 'manual' check (origin in ('manual', 'llm')),
  llm_job_id       bigint references public.llm_jobs (id) on delete set null,
  llm_version      text,          -- "<proveedor>|<versión del prompt>", p. ej. "openai:gpt-6-luna|model_guide-v1"
  generated_at     timestamptz,
  reviewed_by      uuid references public.profiles (id) on delete set null,
  reviewed_at      timestamptz,
  published_at     timestamptz,
  created_at       timestamptz not null default now(),
  updated_at       timestamptz not null default now(),
  constraint model_guides_years check (year_to is null or year_from is null or year_to >= year_from),
  constraint model_guides_unique unique nulls not distinct (make, model, generation_label),
  constraint model_guides_slug_unique unique nulls not distinct (slug_make, slug_model, generation_label),
  constraint model_guides_published_reviewed check (status = 'draft' or (reviewed_by is not null and reviewed_at is not null))
);
```

Forma de `body` (claves fijas; cada sección es una lista de afirmaciones de la guía):

```json
{
  "known_issues":       [{"text": "…", "applies_to": "motor 1.6 16v, 2014–2016"}],
  "visit_checklist":    [{"text": "…"}],
  "versions_equipment": [{"text": "…", "applies_to": "XEi"}],
  "maintenance_costs":  [{"text": "…"}],
  "generations":        [{"label": "E170", "year_from": 2014, "year_to": 2019, "text": "…"}]
}
```

`questions`: `[{"text": "¿…?", "why": "…"}]`, de 3 a 8, cada una de 10 a 200 caracteres y terminada en «?». `sources`: `[{"title": "…", "url": "https://…", "kind": "ficha técnica | manual | prensa | foro | otra", "verified": false}]`.

Las secciones se llaman en la página «Fallas conocidas», «Qué revisar en la visita», «Versiones y equipamiento», «Mantenimiento y costos típicos» y «Generaciones». El esquema de `body` lo validan el worker (pydantic, `schemas.ModelGuideDraft`) y la web al guardar (zod, `lib/guides.ts`); en la base solo hay chequeos de tipo, como en el resto de los jsonb.

RLS y grants:

- `anon` y `authenticated`: `select` **solo de columnas públicas** (`id, make, model, generation_label, year_from, year_to, slug_make, slug_model, body, questions, sources, published_at, updated_at, content_updated_at`) y política `using (status = 'published')`. No ven `reviewed_by`, `llm_job_id`, `llm_version`, `origin` ni los borradores.
- Nadie más que `service_role` escribe. La web admin escribe con RPCs `security definer set search_path = ''` concedidas solo a `service_role`, con `p_actor_id` y chequeo de `profiles.role = 'admin'`:
  - `admin_save_model_guide(p_id, p_values jsonb, p_expected_updated_at, p_actor_id)`: crea o edita; con `updated_at` esperado para no pisar otra edición (como `admin_update_setting`).
  - `admin_set_model_guide_status(p_id, p_status, p_actor_id, p_expected_updated_at)`: publicar pone `reviewed_by = actor`, `reviewed_at = now()` y `published_at`; despublicar vuelve a `draft` y deja la revisión anterior. **Publicar exige el `updated_at` de la página que Juan tiene abierta** (`guide_changed` si la guía cambió desde entonces, por ejemplo un borrador que el worker escribió después de «Regenerar»); despublicar no lo pide. **No publica sin al menos una fuente** (`guide_sources_missing`) **ni si hay alguna con `verified = false`** (las fuentes que sugiere la IA pueden ser inventadas: Juan las verifica o las borra), ni si faltan las cinco secciones o las preguntas (`guide_incomplete`).
- Trigger `set_updated_at` como en el resto.

### 3. El problema de `llm_jobs.user_id` NOT NULL

El plan (sección 1, nota 5) dice que un job de sistema no encaja. Propuesta: **no es un job de sistema**. Lo pide un admin desde `/admin/guides`, así que `user_id` es el admin que pidió el borrador (Juan). Cambios en `llm_jobs`:

- CHECK de `kind`: suma `model_guide`.
- La política «enqueue own» pasa a exigir `kind <> 'model_guide'`: **un usuario común no puede encolar guías** insertando directo (hoy cualquier `authenticated` puede insertar cualquier kind del CHECK). Las guías solo entran por `admin_request_model_guide`.
- CHECK de forma del input para `model_guide`: `make` y `model` string, `guide_id` número.
- `enforce_llm_rate_limit` ignora `model_guide`: tiene sus propios topes (decisión 4). Si no, una tanda de 30 se comería el `per_user_hour` de Juan y le cortaría el modo asistido.
- `expire` usa otro vencimiento para `model_guide` (`llm_limits.model_guide.queued_ttl_minutes`, propuesto 60): los 75 s de hoy existen porque la web cae al formulario, y eso no aplica a un borrador.

Alternativas descartadas: `user_id` nullable (cambia la semántica de la política «read own», de Realtime, del rate limit y de las consultas de remarketing que agrupan por usuario) y una tabla de jobs propia (duplica claim, expire, latencia y `llm_job_stats`). Si se borra el perfil del admin, sus jobs se borran por cascada; la guía conserva `llm_version` y `generated_at` (`llm_job_id` queda null).

### 4. Topes, apagado y proveedor (`app_config.llm_limits.model_guide`)

La migración agrega la sub-clave sin pisar lo que ya haya:

```json
"model_guide": {
  "enabled": false,
  "per_day": 30,
  "per_month": 60,
  "queued_ttl_minutes": 60,
  "timeout_seconds": 180,
  "max_questions_in_listing": 3
}
```

- `enabled: false` hasta que Juan apruebe proveedor y tope. Apagado, `/admin/guides` muestra «La generación con IA está apagada» y el botón no aparece; crear y editar a mano funciona igual. El worker vuelve a mirar `enabled` al tomar el job: un job encolado antes de apagarlo falla con «generación apagada» y no llama al proveedor.
- `per_day` (día de Argentina) y `per_month` cuentan los jobs `model_guide` que **llamaron al proveedor**; los aciertos de cache no cuentan. Los revisa `admin_request_model_guide` con un lock advisory (no hay carrera entre dos pedidos). Pasado el tope: `guide_daily_cap` / `guide_monthly_cap`, con el número en el mensaje.
- Piloto: Juan prende con `per_day: 5`, revisa las 5 guías piloto y, si le sirven, sube a 30 para la primera tanda. Todo desde `/admin/config`, sin deploy.
- `max_questions_in_listing` (3) es cuántas preguntas de la guía suma un aviso (decisión 8). `/admin/config` valida la sub-clave con zod (`lib/admin-config.ts`).
- Proveedor: el mismo `LLM_PROVIDER` del worker que usa el modo asistido (`openai`, `gpt-6-luna`). No se agrega un proveedor nuevo. `llm_version` guarda proveedor y modelo, así que si Juan después elige otro modelo para guías se sabe qué borrador salió de cuál.

### 5. El job `model_guide`

Pedido (web → base):

- `admin_request_model_guide(p_guide_id, p_force boolean, p_actor_id)` (solo `service_role`): chequea admin, `enabled`, topes y que la guía esté en `draft` (**nunca se regenera una guía publicada**: hay que despublicarla). Inserta en `llm_jobs` `kind = 'model_guide'`, `user_id = p_actor_id`, `input = {guide_id, make, model, generation_label, year_from, year_to, force}`. Devuelve el id del job.
- «Generar los que faltan» en `/admin/guides` crea los borradores vacíos que falten de la lista de candidatos y pide un job por cada uno, hasta el tope del día; dice cuántos quedaron sin pedir.

Proceso (worker):

- `pipeline/llm_jobs.py`: un consumidor **aparte** para `model_guide` (uno solo, sin concurrencia), para que una guía de dos minutos nunca demore una búsqueda asistida. Los consumidores de siempre siguen con `["parse_search"]`.
- Cache: el worker, que es el que conoce la versión del prompt, arma `cache_key = make|model|generation_label|MODEL_GUIDE_PROMPT_VERSION` (en minúsculas) y busca un job `model_guide` `done` con la misma clave en `output.cache_key`. Si existe y `force` es falso, copia esa salida, marca el job `done` con `provider = 'cache'` y `output.cached = true`, y **no llama al proveedor**. `force` (botón «Regenerar») la saltea. Índice parcial sobre `(output ->> 'cache_key') where kind = 'model_guide' and status = 'done'`.
- `MODEL_GUIDE_PROMPT_VERSION = "model_guide-v1"` vive en `worker/llm/prompts/__init__.py`. Un test compara el hash del `.md` con el registrado junto a la versión: si alguien edita el prompt sin subir la versión, el test falla.
- `LLMProvider.model_guide(context) -> ModelGuideDraft` en las cuatro implementaciones (en `local`, `LLMError` como hoy), con `timeout_seconds` propio.
- Validación después del proveedor (`intelligence/guides.py`, puro): esquema estricto; lint de copy (`FORBIDDEN_TERMS` y `RISK_FORBIDDEN`); **ninguna cifra de dinero** en ninguna sección (regex de `$`, `USD`, `ARS`, `pesos`, `dólares` seguidos o precedidos de números); de 3 a 8 preguntas; todas las fuentes con `verified = false`. Si algo falla, el job queda `failed` con el motivo y la guía no cambia.
- Escritura: si la guía sigue en `draft`, el worker reemplaza `body`, `questions` y `sources`, y pone `origin = 'llm'`, `llm_job_id`, `llm_version` y `generated_at`. Las ediciones a mano se miden con `content_updated_at`, que un trigger mueve solo cuando cambia el contenido (publicar y despublicar mueven `updated_at`, pero no son ediciones). Si la guía tiene ediciones a mano posteriores a la última generación (`content_updated_at > generated_at`), el pedido exige `force` (la UI pide confirmación: «Vas a reemplazar tus cambios»). Si la guía se publicó mientras el job corría, no se toca: la salida queda en `llm_jobs.output`.
- `tools/llm_jobs --replay` también procesa `model_guide` con respuestas grabadas (para el e2e y para probar a mano).

Prompt (`worker/llm/prompts/model_guide.md`), en castellano rioplatense: rol de redactor de una guía orientativa para comprar usado en Argentina; solo información general del modelo, sin inventar números de serie, recalls o fechas que no conozca; «si no estás seguro, no lo pongas»; sin cifras de dinero; sin marcas de talleres; cada afirmación corta y concreta; `applies_to` cuando depende del motor o los años; preguntas para hacerle al vendedor, no a un mecánico; fuentes sugeridas que el redactor humano va a verificar. El contexto que se le pasa: marca, modelo, generación, años y versiones del catálogo. **No** se le pasan avisos, precios, búsquedas ni datos de usuarios, ni `timing_belt` (decisión 10).

### 6. `/admin/guides`

- Nueva entrada «Guías» en `admin-nav.tsx`. Página `force-dynamic` como el resto del admin.
- **Lista de candidatos**: `admin_guide_candidates(p_limit int default 30)` (solo `service_role`): búsquedas `enabled` con `search_access_active(id)`, agrupadas por la fila del catálogo (`lower(filters->>'make')`, `lower(filters->>'model')` contra `vehicle_catalog` con `trim is null`), ordenadas por cantidad, con años del catálogo y el estado de la guía (sin guía, borrador, publicada). Devuelve solo conteos agregados, nunca usuarios. Las búsquedas sin modelo quedan afuera.
- Por fila: «Crear borrador» (vacío), «Generar borrador» (solo con la generación prendida), «Editar», «Publicar» / «Despublicar», «Ver página» (si está publicada), y la marca «Piloto» en las primeras 5 que Juan elija (es una etiqueta de la lista: `app_config.model_guides.pilot` con los ids; propuesta abajo).
- **Editor**: un formulario por sección con renglones agregables (texto y «aplica a»), preguntas (texto y «por qué»), fuentes (título, URL, tipo y la casilla «La revisé»), años y generación. Antes de guardar corre el lint de copy y la regla de cifras; el error dice qué renglón falla. Muestra el origen («Borrador de IA del 05/11, openai:gpt-6-luna, model_guide-v1» o «Escrita a mano»), el estado del último job (en cola, generando, falló y por qué) y una vista previa con el mismo componente de la página pública.
- Publicar, despublicar o guardar una guía publicada llama a `revalidatePath('/guias/<marca>/<modelo>')`, `revalidatePath('/guias')` y `revalidatePath('/sitemap.xml')` desde la Server Action.

### 7. Páginas públicas

`web/app/guias/page.tsx` (índice) y `web/app/guias/[marca]/[modelo]/page.tsx`:

- **ISR**: `export const revalidate = 3600`; `generateStaticParams` devuelve `[]` (nada se arma en el build: así un problema de la base no rompe el deploy, como pasó con el admin) y cada página se genera en la primera visita y queda cacheada; `dynamicParams` queda en `true`. La publicación invalida al instante (decisión 6).
- La página **no usa cookies**: lee con un cliente anónimo nuevo sin sesión (`lib/supabase/public.ts`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`), así RLS es la que garantiza que solo se lean guías publicadas. `SiteHeader` se renderiza como deslogueado; el estado de sesión del CTA se resuelve en el cliente.
- 404 (`notFound()`) si el slug no existe, si solo hay borradores o si la tabla no existe (base vieja). Slugs fuera del patrón: 404 sin consultar.
- **Metadata** (`generateMetadata`): título «Toyota Corolla usado: guía orientativa para revisarlo», descripción fija armada con marca, modelo y años, `alternates.canonical`, Open Graph del layout. Los borradores no tienen metadata porque no tienen página.
- **Contenido**: H1, aviso destacado arriba de todo — «Guía orientativa. Resume información general del modelo; no verifica ningún auto en particular ni reemplaza la revisión de un mecánico de confianza.» —, las cinco secciones, «Preguntas para hacerle al vendedor» con botón «Copiar preguntas», fuentes (todas verificadas, por la regla de publicación) y «Última actualización: <fecha>» (la del contenido, `content_updated_at`: publicar o despublicar no la cambia). No muestra quién la revisó, si la escribió la IA ni ningún dato de la plataforma.
- **FAQ en JSON-LD** (`FAQPage`), armado de forma determinística desde las secciones: «¿Qué fallas conocidas tiene el Toyota Corolla?» → los renglones de «Fallas conocidas»; «¿Qué revisar al ver un Toyota Corolla usado?» → «Qué revisar en la visita»; «¿Qué preguntarle al vendedor de un Toyota Corolla?» → las preguntas. Se escapa `<` como `<` (guía de Next). Nota: Google muestra resultados enriquecidos de FAQ solo en algunos sitios; el JSON-LD sirve igual para describir la página.
- **CTA «Crear mi búsqueda»**: reutiliza `LandingSearch` con dos props nuevas, `initialText` («Busco un Toyota Corolla 2014 a 2019», años de la guía o del catálogo) y la detección de sesión en el cliente. Deslogueado abre el mismo diálogo de alta solo con email; logueado va a `/app/searches/new?prompt=…`. Desde ahí el texto pasa al modo asistido como cualquier búsqueda.
- **Índice `/guias`**: guías publicadas agrupadas por marca, con link a cada página. Sin guías: «Todavía no hay guías publicadas» y un link a la landing (no es 404, para que el link del sitemap nunca rompa).
- `robots.ts` no cambia (`/guias` ya queda permitido). Hoy el matcher de `proxy.ts` incluye `/guias`. Se verifica que no agregue `Set-Cookie` en `/guias` (para que la respuesta se cachee); si lo hace, se excluye `/guias` del matcher.

### 8. Preguntas de la guía en el aviso (`seller_questions.py`)

- `pipeline/scoring.Scorer.create` carga una vez por lote las guías **publicadas** (`db/repos/guides.published_questions`): `{(lower(make), lower(model)): [(guide_id, year_from, year_to, questions)]}`. Si `to_regclass('public.model_guides')` es null (base vieja) devuelve `{}` y el worker sigue como hoy.
- Cruce: la marca y `catalog_model` del aviso; el año dentro de `[year_from, year_to]` (null = sin límite). Si cruzan varias generaciones, gana la de rango más chico. Sin año en el aviso, solo cruza la fila con `generation_label` null.
- Orden en el mensaje: saludo, «¿lo seguís teniendo?» y titular (como hoy) → **las preguntas del aviso** (las que salen de red flags y de lo que dice la descripción) → **hasta 3 de la guía** (`max_questions_in_listing`) → las genéricas por antigüedad o dato faltante (VTV, choques, services sin descripción, transmisión, versión). Es la lectura de «antes de las genéricas» del backlog: la guía no le gana a una señal del propio aviso.
- `question_texts` (email H-01 y mensaje listo de PRO-01, tope 3) sigue el mismo orden, así que las preguntas de la guía entran en el email solo si el aviso no tiene tres propias.
- Se saltean las preguntas de la guía que repiten una del template o son casi iguales (`guides.same_question`: iguales normalizadas, o con las palabras que importan, sin artículos, preposiciones ni verbos genéricos como «hizo» o «cambió», que se solapan al menos un 80 %).
- **Origen**: `question_keys` pasa a devolver `(key, text, origin)`; las de la guía tienen `key = "guide:<guide_id>:<n>"` y `origin = "guide"`. Columna nueva `matches.question_origins jsonb` (`[{"key": "timing_belt", "origin": "template", "text": "…"}, {"key": "guide:12:0", "origin": "guide", "guide_id": 12, "text": "…"}]`, cada entrada con su texto y en el orden de `seller_questions`), escrita junto con `seller_questions`. El worker la escribe solo si la columna existe (mismo chequeo `to_regclass`/catálogo una vez por proceso). El inspector `/admin/matches/[id]` muestra las preguntas con su origen y el link a la guía.
- Sin bump de `SCORING_VERSION`: no cambia ningún score ni nivel. Los matches toman las preguntas de una guía recién publicada en el próximo rescore periódico (avisos activos vistos en 14 días); re-puntuar no notifica. **Despublicar las saca al instante** de todos los matches que las tienen, también de avisos que ya no están activos y de búsquedas sin acceso (`model_guide_withdraw_questions`, migraciones `20261205120300` y `20261205120400`): saca de `question_origins` las entradas de esa guía y solo esos textos, como preguntas enteras: rearma `seller_questions` con las entradas que quedan y saca esos textos de `contact_questions` (nunca una pregunta del template con el mismo texto ni un pedazo de otra pregunta). Un rescore que cargó la guía antes de despublicarla no la vuelve a escribir: `upsert_scored` relee con `FOR SHARE` qué guías siguen publicadas y saca las otras (`seller_questions.without_guides`). Guardar una guía publicada saca las preguntas que ya no tiene. `guard_match_access` deja pasar un update que solo cambia esas tres columnas. Los emails ya enviados no se pueden retirar.
- `max_questions_in_listing` se acota a 0..3 en el worker y `/admin/config` rechaza más de 3 (el backlog dice «hasta 3»).

### 9. Eventos y GA4

- RPC `log_guide_event(p_name text, p_slug_make text, p_slug_model text)`, `security definer`, concedida a `anon` y `authenticated`: acepta solo `guide_viewed`, `guide_cta_clicked` y `guide_questions_copied`, solo para una guía publicada, y graba `events (user_id = auth.uid(), name, props = {guide_id, make, model})`. `user_id` queda null para un visitante (el backlog pide `guide_viewed` sin usuario). No guarda IP, user agent ni referrer.
- Como la página está cacheada, `guide_viewed` sale del navegador (un componente cliente, una vez por carga). `guide_cta_clicked` al tocar «Crear mi búsqueda»; `guide_questions_copied` al copiar.
- GA4 (con el mismo consentimiento de hoy): `view_item` con `items: [{item_id: "guide:toyota/corolla", item_name: "Toyota Corolla", item_category: "guide"}]`; el CTA reutiliza los eventos que ya manda `LandingSearch`.
- `/admin/guides` muestra vistas, clics del CTA y copias de los últimos 30 días por guía (conteos de `events`).

### 10. `timing_chain_catalog` sigue NOT APPLIED

PAR-04 **no aplica** `20261107130000_timing_chain_catalog.sql` ni depende de ella: el prompt no recibe `vehicle_catalog.timing_belt`, la página no lo muestra y las preguntas de la guía no lo consultan. Si la guía dice «distribución por correa», es una afirmación de la guía que Juan revisa como cualquier otra. La pregunta `timing_belt` del template sigue dependiendo de la columna como hoy. Riesgo: una guía y el catálogo pueden decir cosas distintas sobre la distribución; ver «Riesgos». La base local y la de tests sí tienen esa migración (está en la carpeta); los tests de PAR-04 no usan `timing_belt`.

### 11. Base vieja (la web de `main` sin las migraciones)

- `/guias/<marca>/<modelo>`: el error de tabla inexistente (`PGRST205` / `42P01`) se trata como «no existe» → 404.
- `/guias`: «Todavía no hay guías publicadas».
- `sitemap.ts`: pasa a ser `async` con `revalidate = 3600`; si la consulta falla, devuelve las entradas estáticas de siempre.
- `/admin/guides`: «Falta aplicar la migración `20261205120000_par04_model_guides`» y nada más.
- `log_guide_event` inexistente: el componente cliente ignora el error.
- La ficha y el inspector no leen `question_origins` si no existe (el select se arma sin la columna y el inspector muestra las preguntas sin origen).
- Worker: decisión 8.

## Migraciones

Todas con versión ≥ `20261205120000` (producción está en `20261204120000`), aplicables desde una base vacía (después de toda la cadena) y con inserts idempotentes. Encabezado `--` que cita el backlog y PAR-04. **No se aplican en producción** sin el OK de Juan.

1. `20261205120000_par04_model_guides.sql`: `model_guides` con RLS, grants por columna y trigger; `admin_save_model_guide`, `admin_set_model_guide_status`, `admin_guide_candidates`; CHECK de `llm_jobs.kind` con `model_guide`, CHECK de input, política «enqueue own» con `kind <> 'model_guide'`, `enforce_llm_rate_limit` que ignora `model_guide`, `admin_request_model_guide`, índice de cache; `llm_limits.model_guide` (merge sin pisar) y `app_config.model_guides` (`{"pilot": []}`).
2. `20261205120100_par04_guide_events.sql`: `log_guide_event` y los tres eventos en `admin_decision_metrics.human_events` (partiendo de su última definición, `20261203120100_par02_decision_metrics_duplicate.sql`).
3. `20261205120200_par04_question_origins.sql`: `matches.question_origins jsonb`.
4. `20261205120300_par04_guide_review_fixes.sql` (arreglos de la revisión): `model_guides.content_updated_at` con su trigger; `model_guide_withdraw_questions` y su uso al despublicar y al guardar una guía publicada; `guard_match_access` que deja pasar el retiro; `log_guide_event` con tope por guía (`app_config.model_guides.events`).
5. `20261205120400_par04_guide_publish_guards.sql` (segunda tanda): `model_guide_problem` exige al menos una fuente; `admin_set_model_guide_status` con `p_expected_updated_at` (la firma de tres argumentos se borra); `match_questions_without` y `model_guide_withdraw_questions` que saca solo lo que la guía escribió, como preguntas enteras; `select (content_updated_at)` para `anon` y `authenticated` («Última actualización» y `lastModified` del sitemap son la fecha del contenido).

Después: `web/types/database.ts` a mano (tabla, RPCs y columna), sin `gen:types`.

## Archivos

Worker: `llm/prompts/model_guide.md`, `llm/prompts/__init__.py` (versión y armado del mensaje), `llm/schemas.py` (`ModelGuideDraft`), `llm/provider.py` y las cuatro implementaciones, `llm/replay.py` (replay por kind), `intelligence/guides.py` (validación y cruce de preguntas), `intelligence/seller_questions.py`, `intelligence/engine.py` (`question_origins`), `pipeline/scoring.py`, `pipeline/llm_jobs.py` (handler, consumidor aparte, cache), `db/repos/llm_jobs.py` (vencimiento por kind), `db/repos/guides.py` (nuevo), `db/repos/matches.py` (`_EVALUATED` condicional), `tools/record_llm.py` (`--kind model_guide`, no se corre en esta etapa), `tools/llm_jobs.py`.

Web: `app/guias/page.tsx`, `app/guias/[marca]/[modelo]/page.tsx`, `components/guides/*` (secciones, aviso, copiar preguntas, tracker, JSON-LD), `components/landing-search.tsx` (`initialText` y sesión en cliente), `lib/guides.ts` (slugs, zod, FAQ, lint), `lib/supabase/public.ts`, `app/sitemap.ts`, `app/admin/guides/{page,actions,[id]/page}.tsx`, `components/admin/admin-nav.tsx`, `lib/admin-config.ts` y `config-forms.tsx` (`llm_limits.model_guide`), `components/admin/inspector.tsx` (preguntas con su origen en `/admin/matches/[id]`), `types/database.ts`. Además: `lib/guides-data.ts` (lectura anónima, 404 con base vieja), `lib/admin-guides.ts` (datos de `/admin/guides`), `components/admin/guide-editor.tsx` y `guide-buttons.tsx`, `e2e/par04-guides.spec.ts`.

Base: las tres migraciones, `supabase/tests/model_guides_test.sql` (pgTAP), `supabase/seed.sql` sin guías (los tests y el e2e siembran las suyas).

Docs: este spec, el plan `docs/superpowers/plans/2026-11-03-par04-guias.md` (después de la aprobación), backlog y plan por fases.

## Tests

Ninguna prueba llama a un proveedor real. Las respuestas de `worker/tests/fixtures/llm/model_guide_recorded.json` se escriben **a mano** con el formato de los sobres grabados y dicen en el archivo que son sintéticas; se vuelven a grabar con `tools.record_llm --kind model_guide` recién cuando Juan apruebe el proveedor.

- **Contrato del job (pytest, offline)**: con el replay, una respuesta válida produce un `ModelGuideDraft` con las cinco secciones, 3–8 preguntas y fuentes no verificadas; respuestas inválidas grabadas (sección faltante, cifra en dólares, «garantizado», 12 preguntas, JSON roto) dejan el job `failed` con motivo y la guía sin cambios. Test del hash del prompt contra `MODEL_GUIDE_PROMPT_VERSION`.
- **Postgres (pytest contra `automotive_test`)**: `admin_request_model_guide` con la generación apagada (error), sin ser admin (error), con guía publicada (error), en el tope diario y mensual (error); un `authenticated` no puede insertar `model_guide` directo; el rate limit por hora no cuenta `model_guide`; cache: el segundo pedido no llama al proveedor, no cuenta para el tope y `force` sí llama; vencimiento por kind; el worker no pisa una guía publicada; con `enabled` apagado después de encolar, el job falla sin llamar.
- **Preguntas**: unitarios de `seller_questions` (orden aviso → guía → genéricas, tope 3, años, generación más chica, sin año, duplicadas, guía en borrador ignorada, origen); snapshot del email de oportunidad con preguntas de guía en `worker/tests/snapshots/notifications/`; base sin `model_guides` → igual que hoy.
- **pgTAP (`model_guides_test.sql`)**: `anon` y `authenticated` leen solo `published` y no pueden leer `reviewed_by` ni `llm_version`; nadie salvo `service_role` escribe; publicar sin revisión o con fuentes sin verificar falla; `log_guide_event` rechaza nombres desconocidos y guías en borrador y graba `user_id` null para `anon`.
- **Vitest**: slugs; zod de `body`; FAQ JSON-LD (forma y escape de `<`); lint de copy sobre una guía de ejemplo, el copy fijo de las páginas y el del admin (`FORBIDDEN_TERMS` y la lista de riesgo); la página llama a `notFound()` con slug inexistente, con solo borradores y con la tabla inexistente; el HTML renderizado no tiene `USD`, `$` ni campos internos; sitemap con y sin tabla.
- **Playwright** (`e2e/par04-guides.spec.ts`, `CI=1 npx playwright test`, desktop y 375 px): una guía publicada sembrada en la base local se ve con el aviso «Guía orientativa»; el CTA abre el alta con el texto prellenado (deslogueado) y lleva a `/app/searches/new?prompt=…` (logueado); un borrador da 404; `/guias` lista la publicada; `/admin/guides` crea, edita y publica a mano con la generación apagada.
- Nota de ISR: una guía sembrada por SQL llega a `/guias` y al sitemap recién en la siguiente invalidación (publicar desde `/admin/guides` la hace). En el build, un error de la base deja el índice vacío en vez de romper el deploy; en ejecución, ISR sigue sirviendo la página anterior.

## Riesgos

- **Afirmaciones falsas de la IA.** Es la razón de que todo sea borrador y de que la página diga «Guía orientativa». Mitigación: prompt prudente, sin cifras de dinero, fuentes obligatoriamente verificadas por Juan antes de publicar, piloto de 5. El riesgo residual es la revisión humana de 30 guías largas.
- **Distribución contradictoria.** Una guía puede decir «cadena» donde `vehicle_catalog` (con o sin `timing_chain_catalog` aplicada) dice correa, y el aviso mostrar las dos cosas. Mitigación: el editor muestra al lado el valor de `timing_belt` del catálogo como referencia para Juan; no se sincronizan.
- **Contenido escaso para SEO.** Páginas cortas o parecidas entre sí pueden no posicionar; es contenido orientativo, no una promesa de tráfico.
- **Eventos anónimos inflables.** `log_guide_event` es público. Tiene un tope por guía (todos los eventos juntos): 30 por minuto y 300 por hora (`app_config.model_guides.events`); pasado el tope no graba nada y no da error. Así la clave anónima no puede llenar `events`, pero alguien todavía puede inflar las vistas hasta el tope: son una métrica orientativa.
- **Caché de Vercel y proxy.** Si `proxy.ts` agrega cookies a la respuesta, la página puede no cachearse; se verifica en el plan (encabezados `x-nextjs-cache` y `cache-control`) y, si hace falta, se excluye `/guias` del matcher.
- **Preguntas que cambian sin aviso.** Publicar una guía cambia el texto de `seller_questions` y `contact_questions` de muchos matches en el siguiente rescore; no notifica, pero el email de oportunidad de un aviso nuevo ya la incluye.
- **Costo.** Con el tope de 30 por día y 60 por mes y un solo consumidor, el gasto máximo queda acotado por config; el monto depende del proveedor que elija Juan.
- **Admin borrado.** Los jobs de un admin borrado desaparecen por cascada; la guía conserva la versión del LLM.

## Preguntas para Juan

Todo es configurable; entre paréntesis, el valor por defecto que propongo.

1. **Proveedor LLM**: ¿el mismo del modo asistido (`openai`, `gpt-6-luna`), o uno más grande solo para guías? (El mismo; `llm_version` guarda cuál se usó).
2. **Tope de gasto**: ¿`per_day` y `per_month`? (30 por día y 60 por mes; para el piloto, 5 por día). ¿Querés además un tope en dinero? Hoy no hay medición de costo por job.
3. **Encendido**: la generación queda apagada (`llm_limits.model_guide.enabled = false`). ¿La prendo yo cuando apruebes 1 y 2, o la prendés vos desde `/admin/config`? (Vos).
4. **Tono y aviso**: «Guía orientativa. Resume información general del modelo; no verifica ningún auto en particular ni reemplaza la revisión de un mecánico de confianza.» ¿Ok así? (Sí).
5. **Piloto**: revisás las primeras 5 guías antes de publicar y después la tanda de 30. ¿Las 5 son las 5 con más búsquedas activas o las elegís vos? (Las 5 con más búsquedas).
6. **Costos típicos**: ¿la sección «Mantenimiento y costos típicos» puede tener montos? (No en la v1: frecuencias y qué piezas suelen ser caras, sin cifras; si querés montos, los cargás vos con fuente y fecha, y la regla de cifras se relaja solo para esa sección).
7. **Orden de las preguntas**: aviso → guía (hasta 3) → genéricas. ¿O la guía va primero? (Aviso primero).
8. **Una guía por modelo** con la sección «Generaciones» en la primera tanda, y filas por generación solo cuando haga falta. ¿Ok? (Sí).
9. **Fuentes**: no se puede publicar con fuentes sin la casilla «La revisé». ¿Preferís que la página no muestre fuentes en absoluto? (Mostrar solo las revisadas).
10. **Nombre y URL**: `/guias/<marca>/<modelo>` y el título «<Marca> <Modelo> usado: guía orientativa para revisarlo». ¿Ok? (Sí).
11. **`timing_chain_catalog`**: PAR-04 no la necesita. ¿La seguís revisando aparte? (Sí, aparte; no bloquea PAR-04).

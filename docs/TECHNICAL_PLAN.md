# Automotive — Plan técnico del MVP

- **Basado en:** [PRD v1.0](PRD.md). Convención: **§N** siempre es una sección del PRD; las secciones de este documento se citan como "sección N" (y en la columna *Plan* de la trazabilidad, solo el número).
- **Estado:** F0–F6 implementadas (worker sobre Supabase Postgres, ingesta por crawl targets, matching con razones, Opportunity Score, motor de notificaciones, web MVP en `web/`, modo asistido con `claude -p`, backoffice `/admin` con el inspector, vistas de métricas y CTA Pro con lista de espera). Sigue F7 (puesta en producción para el piloto, §51); mientras tanto corre en local. Planificada: F8 (barrido por recencia: la captura deja de depender de los modelos buscados).
- **Decisiones tomadas:**
  - Web con **Next.js + Supabase**.
  - Base de datos: **Postgres (Supabase)**, que reemplaza a SQLite.
  - Lenguaje natural con **`claude -p`** durante el piloto, detrás de una interfaz que permita pasar a un **LLM local** en el lanzamiento.

---

## 1. Punto de partida y gaps

Hoy AutoMotive es un bot de Telegram en Python que resuelve el caso "alerta por filtros" de punta a punta:

| Capacidad del PRD | Qué existe hoy | Gap |
|---|---|---|
| Collectors (§41, capa 1) | `scrapers/mercadolibre.py`, `facebook.py`, `v6.py`, `kavak.py` (Playwright). `autocosmos.py` existe pero no está en `REGISTRY` | Se scrapea **por alerta** (`scheduler._run_alert` + `_expand_filters`): el costo crece con la cantidad de usuarios. Las cards no traen descripción, versión, tipo de vendedor ni imágenes completas. |
| Normalización (§41, capa 2) | `normalize.py`, `price_check.py`, `scrapers/_dates.py`, `geo.py`, `fx.py` | `normalize_model` se queda con las 2 primeras palabras, así que mezcla modelo y versión ("fiesta kinetic"). ML completa marca y modelo **desde el filtro** y no desde el aviso. No hay catálogo de versiones. |
| Persistencia de listings (§14) | `listings_cache` en SQLite (`db.upsert_listings`) | No hay `first_seen_at` global ni historial: el upsert pisa precio y km. No guarda descripción, imágenes ni estado. |
| Detección de nuevo (§15) | `seen_listings` **por alerta** + bootstrap silencioso | No distingue "actualizada" ni "re-publicada". No hay bajas de precio. |
| Matching (§16) | `BaseScraper.matches_filters` | Es booleano y no deja razones. Rechaza avisos en otra moneda en vez de convertirlos (`mon != item.moneda`). No hay soft preferences. |
| Opportunity Score (§17–20) | `opportunity.evaluate`: match binario por % bajo la mediana (`db.comparables`) | No hay score 0–100, ni componentes, ni niveles, ni explicación. |
| Notificaciones (§21–22, §32) | `scheduler._format_notification` + `bot.send_message` | Está acoplado a Telegram dentro del scheduler. Tiene un solo tipo de alerta, no hay digest, tope ni log de envíos. |
| Usuarios, web, estados, métricas (§26–39) | Wizard de Telegram (`bot/handlers.py`) | No hay usuarios, web, estados, favoritos, OwnedVehicle, tracking ni backoffice. |
| Observabilidad (§46) | Logs a stdout | No hay registro de corridas ni errores consultables. |

Lo que **se reutiliza tal cual o con cambios chicos**:

- los parsers de cada scraper y `_browser.py`;
- `annotate_partial_price`, `keyword_partial`, `statistical_partial` e `is_suspicious_discount`;
- `geo.filter_listings_by_radius`, `haversine_km`, la tabla local de ciudades y el geocode cache;
- `fx.usd_ars_rate`;
- `parse_relative_date`;
- la lógica de recencia (`scheduler._is_recent`);
- `tools/scraper_cli.py`;
- los tests existentes.

---

## 2. Arquitectura objetivo

Son las cinco capas del §41, repartidas en dos runtimes que comparten Postgres:

```
┌──────────────────────────┐        ┌──────────────────────────────────────────┐
│ Web — Next.js (Vercel)   │◀──────▶│ Supabase                                 │
│ landing, app, admin      │ RLS    │  Postgres · Auth (magic link) · Realtime │
└──────────────────────────┘        └──────────────────────────────────────────┘
                                                   ▲ psycopg (rol de servicio)
┌──────────────────────────────────────────────────┴───────────────────────────┐
│ Worker Python (host siempre prendido: Playwright + sesiones FB/ML)           │
│                                                                              │
│  crawl loop ─▶ collectors ─▶ normalization ─▶ upsert + snapshots             │
│                                                     │                        │
│                                                     ▼                        │
│                               intelligence (matching · comparables · score · │
│                                             red flags)                       │
│                                                     │                        │
│                                                     ▼                        │
│                                notification engine ─▶ Telegram / email / web │
│                                                                              │
│  llm_jobs loop ─▶ LLMProvider (claude -p hoy · LLM local mañana)             │
│  telegram bot   ─▶ vinculación de cuenta + acciones inline                   │
└──────────────────────────────────────────────────────────────────────────────┘
```

Principios:

1. **El worker solo hace conexiones salientes**: Postgres, fuentes, APIs de Telegram y email. La web nunca le habla directo: se comunican por tablas (`llm_jobs`, `search_profiles.rematch_requested_at`, `notifications`). Así el worker puede correr en la PC actual o en un VPS sin exponer puertos.
2. **Los datos tienen un único dueño por capa**:
   - collectors y normalización escriben `listings` y `listing_snapshots`;
   - intelligence escribe `matches`;
   - el notification engine escribe `notifications`;
   - la web escribe `search_profiles`, `user_listing_interactions`, `owned_vehicles` y `events`.
3. **Todo lo del §44 es determinístico**: el LLM solo propone y el usuario confirma.
4. **La app mobile futura (§55) usa el mismo Supabase**: Auth, RLS y Realtime. Cambiar de cliente no toca el worker.
5. **Región de Supabase:** `sa-east-1` (São Paulo), por latencia desde Argentina.

---

## 3. Estructura del repo

Monorepo. El Python actual se mueve a `worker/` con `git mv` para no perder el historial.

```
worker/
  collectors/        ← scrapers/*.py (+ _browser.py, _dates.py); Listing ampliado; fetch_detail() por fuente
  normalization/     ← normalize.py, price_check.py, geo.py, fx.py; vehicle.py (make/model/trim vía catálogo); transmission.py
  intelligence/      matching.py, comparables.py, scoring.py, levels.py, red_flags.py, seller_questions.py
  notifications/     engine.py, digest.py, templates.py, channels/{base,telegram,email,web}.py
  llm/               provider.py (interfaz), claude_cli.py, local.py (futuro), schemas.py, prompts/
  bot/               telegram.py (/start <code>, callbacks inline); el wizard se retira en F4
  db/                pool.py (psycopg), repos/{listings,profiles,matches,notifications,runs,config}.py
  pipeline/          crawl.py (targets + cadencia), ingest.py (upsert/snapshots/dedupe), enrich.py, rematch.py, watchlist.py
  tools/             scraper_cli.py, migrate_sqlite.py, explain_match.py
  tests/
  main.py            orquesta los loops asyncio
  pyproject.toml
supabase/
  config.toml
  migrations/        SQL versionado (supabase CLI)
  seed.sql           sources, app_config, vehicle_catalog inicial
  tests/             tests de RLS/SQL (pgTAP)
web/
  app/               rutas (ver sección 9)
  lib/supabase/      clientes server/browser/admin
  components/
  types/database.ts  generado con `supabase gen types typescript`
docs/
  PRD.md, TECHNICAL_PLAN.md
```

**Mapa de migración de módulos:**

| Hoy | Mañana | Cambio |
|---|---|---|
| `db.py` (SQLite) | `worker/db/` | psycopg 3 con `AsyncConnectionPool`. Las funciones mantienen su nombre donde tiene sentido (`comparables`, `upsert_listings`). |
| `scheduler.py` | `worker/pipeline/crawl.py` + `worker/notifications/engine.py` | `_expand_filters` pasa a derivar **crawl targets**. `_format_notification` pasa a `templates.py`. `_is_recent` se mantiene. |
| `opportunity.py` | `worker/intelligence/{comparables,scoring}.py` | El match binario pasa a ser el score 0–100. El gate anti-anticipo se conserva. |
| `bot/handlers.py`, `bot/catalog.py` | `worker/bot/telegram.py` | El wizard sigue hasta F4. Después el bot solo vincula la cuenta y resuelve acciones inline. `catalog.py` pasa a ser el seed de `vehicle_catalog`. |
| `config.py` + `.env` | `worker/config.py` (infra) + tabla `app_config` (reglas de negocio) | Ver el Apéndice A. |

---

## 4. Modelo de datos (Postgres / Supabase)

Mapea el §40.

- Todas las fechas son `timestamptz` en UTC y se muestran en `America/Argentina/Buenos_Aires`.
- Los IDs de dominio son `bigint identity`. Los usuarios usan el `uuid` de `auth.users`.

### 4.1 Tablas

| Tabla | Propósito | Campos clave |
|---|---|---|
| `profiles` | User (§40), 1:1 con `auth.users` | email, phone, `telegram_chat_id`, `telegram_link_code`, `plan` (free/pro/pass), `plan_expires_at` (Search Pass §34), `role` (user/admin), default_origin (lat/lon/label), created_at |
| `sources` | Fuentes y su cadencia (§42) | id (`mercadolibre`…), enabled, `crawl_interval_seconds`, priority, last_ok_at, consecutive_failures |
| `vehicle_catalog` | VehicleDefinition (§40) | make, model, trim, aliases[], year_from/year_to, transmissions[], fuels[] |
| `search_profiles` | SearchProfile (§13) | user_id, name, `filters` (hard), `preferences` (soft), `raw_query`, origin + `radius_km`, `notification_frequency`, `notify_min_level`, channels[], enabled, `bootstrapped_at`, `rematch_requested_at` |
| `crawl_targets` | Agrupación de profiles por (source, make, model) | query jsonb (rango más amplio), last_run_at, next_run_at, active, first_run_done |
| `listings` | Listing canónico (§14) | `UNIQUE(source, external_id)` y el resto de la sección 4.2 |
| `listing_snapshots` | ListingSnapshot / histórico (§31) | Una fila **solo cuando cambia algo**: price, price_usd, fx_rate, mileage_km, attrs_hash, `change_kind` |
| `matches` | Match (§40) | `UNIQUE(search_profile_id, listing_id)`, score, level, `score_breakdown`, `match_reasons`, `price_ref`, red_flags, is_backfill, scoring_version |
| `user_listing_interactions` | Estados (§26), descarte (§27), watchlist (§30) | PK (user_id, listing_id), `status`, `saved`, `rejection_reason`, note |
| `owned_vehicles` | OwnedVehicle (§39) | user_id, listing_id, search_profile_id, snapshot del vehículo, purchase_price/currency/date, `automotive_influence` |
| `notifications` | Log de alertas (§21–22) | user_id, match_id, listing_id, `kind`, channel, status, dedupe_key, payload, sent_at, opened_at, clicked_at |
| `events` | Tracking (§35–38) | user_id, name, props, created_at |
| `llm_jobs` | Cola de trabajos del LLM (§43) | user_id, kind, input, output, status, error, provider, latency_ms |
| `collector_runs` | Observabilidad (§46) | source, target_id, started/finished, status, found/new/updated, error |
| `pipeline_errors` | Errores de normalización y notificación (§46) | stage, ref, error, created_at |
| `app_config` | Pesos, umbrales y límites configurables (§18, §20, §33) | key, value jsonb, updated_at |
| `geocode_cache`, `fx_rates` | Soporte | Igual que hoy / cotización diaria (blue y oficial) |

### 4.2 DDL de las tablas centrales (boceto)

```sql
create type listing_status     as enum ('active','gone');
create type match_level        as enum ('high','good','match','low');
create type notify_frequency   as enum ('immediate','daily');
create type interaction_status as enum ('new','seen','interested','discarded',
                                        'contacted','visit_scheduled','purchased');
create type rejection_reason   as enum ('too_expensive','too_many_km','wrong_trim','location',
                                        'automatic','seller','apparent_condition',
                                        'documentation','other');

create table listings (
  id                   bigint generated always as identity primary key,
  source               text not null references sources(id),
  external_id          text not null,
  url                  text not null,
  title                text not null,
  description          text,
  make text, model text, trim text, year int,
  price                numeric, currency text check (currency in ('USD','ARS')),
  price_usd            numeric,
  mileage_km           int,
  transmission         text,              -- 'manual' | 'automatic' | null
  fuel                 text,
  location_text        text, lat double precision, lon double precision,
  seller_name          text, seller_type text,   -- 'private' | 'dealer' | null
  images               jsonb not null default '[]',
  attributes           jsonb not null default '{}',
  published_at         timestamptz,
  first_seen_at        timestamptz not null default now(),
  last_seen_at         timestamptz not null default now(),
  status               listing_status not null default 'active',
  price_partial        boolean not null default false,
  price_partial_reason text,
  normalization_confidence real,
  fingerprint          text,
  probable_repost_of   bigint references listings(id),
  enriched_at          timestamptz,
  unique (source, external_id)
);
create index on listings (make, model, year);
create index on listings (fingerprint);
create index on listings (first_seen_at desc);

create table listing_snapshots (
  id          bigint generated always as identity primary key,
  listing_id  bigint not null references listings(id) on delete cascade,
  observed_at timestamptz not null default now(),
  price numeric, currency text, price_usd numeric, fx_rate numeric,
  mileage_km  int,
  attrs_hash  text not null,
  change_kind text not null   -- new | price | mileage | description | images | attrs
);
create index on listing_snapshots (listing_id, observed_at desc);

create table search_profiles (
  id                     bigint generated always as identity primary key,
  user_id                uuid not null references profiles(id) on delete cascade,
  name                   text not null,
  filters                jsonb not null,
  preferences            jsonb not null default '{}',
  raw_query              text,
  origin_lat double precision, origin_lon double precision, radius_km real,
  notification_frequency notify_frequency not null default 'immediate',
  notify_min_level       match_level not null default 'good',
  channels               text[] not null default '{telegram,web}',
  enabled                boolean not null default true,
  bootstrapped_at        timestamptz,
  rematch_requested_at   timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table matches (
  id                bigint generated always as identity primary key,
  search_profile_id bigint not null references search_profiles(id) on delete cascade,
  listing_id        bigint not null references listings(id) on delete cascade,
  score             smallint not null check (score between 0 and 100),
  level             match_level not null,
  score_breakdown   jsonb not null,
  match_reasons     jsonb not null,
  price_ref         jsonb,
  red_flags         jsonb not null default '[]',
  is_backfill       boolean not null default false,
  scoring_version   text not null,
  generated_at      timestamptz not null default now(),
  updated_at        timestamptz not null default now(),
  unique (search_profile_id, listing_id)
);
create index on matches (search_profile_id, score desc, generated_at desc);

create table user_listing_interactions (
  user_id          uuid not null references profiles(id) on delete cascade,
  listing_id       bigint not null references listings(id) on delete cascade,
  status           interaction_status not null default 'new',
  saved            boolean not null default false,
  rejection_reason rejection_reason,
  note             text,
  updated_at       timestamptz not null default now(),
  primary key (user_id, listing_id)
);
```

### 4.3 Forma de `filters` y `preferences`

Hay **un vehículo por Search Profile**, siguiendo el §13 ("múltiples búsquedas" antes que una sola compleja). Si el usuario escribe "Fiesta Titanium… también Polo Highline", el modo asistido propone **dos profiles**.

```jsonc
// filters: hard filters (§16). Si alguno da "fail", no hay match.
{
  "make": "Ford", "model": "Fiesta",
  "trims": ["Titanium"], "trim_strict": false,  // con trim_strict=false, la versión es soft
  "year_min": 2016, "year_max": 2018,
  "price_max": 11500, "currency": "USD",         // se compara convirtiendo con fx, no descartando
  "km_max": 150000,
  "transmission": "manual",
  "fuel": null,
  "sources": ["mercadolibre", "facebook", "v6", "kavak"]
}
// preferences: soft (§16). Alimentan el score.
{
  "km_target": 120000, "price_target": 10500,
  "preferred_trims": ["Titanium"], "seller_type": "private",
  "colors": [], "max_distance_km": 30
}
```

La ubicación va en columnas propias (`origin_*`, `radius_km`) porque la usa `geo.py`. "AMBA" es un preset: centro en CABA y 60 km.

### 4.4 RLS y seguridad

- `search_profiles`, `user_listing_interactions`, `owned_vehicles`, `notifications`, `events` y `llm_jobs`: el usuario accede solo a sus propias filas (`user_id = auth.uid()`).
- `matches`: el usuario los lee a través de sus profiles (`exists (select 1 from search_profiles sp where sp.id = search_profile_id and sp.user_id = auth.uid())`). Solo el worker los escribe.
- `listings` y `listing_snapshots`: cualquier usuario autenticado los lee. Solo el worker los escribe.
- `app_config`, `collector_runs`, `pipeline_errors` y `crawl_targets`: sin acceso desde el cliente. El admin los lee del lado del servidor con la service role, después de chequear `profiles.role = 'admin'`.
- Límites del plan (§33): un trigger `before insert` en `search_profiles` lee `app_config.plan_limits` y solo actúa si `plan_limits.enforced = true`. Durante el piloto queda apagado, pero se registra el evento `plan_limit_hit` para medir.

### 4.5 Migración desde SQLite (`worker/tools/migrate_sqlite.py`)

1. `listings_cache` → `listings`, más un snapshot `new` por cada fila. `first_seen_at` sale de `scraped_at`, que es lo mejor que tenemos.
2. `alerts` → `search_profiles`: una fila por combinación (marca, modelo) que exista en el catálogo. Se toma un mapeo `telegram_user_id → email` por argumento y se crean los usuarios con la Admin API de Supabase.
3. `seen_listings` → `matches` con `is_backfill = true`, así no se vuelve a notificar lo ya visto.
4. `geocode_cache` se copia tal cual.

El script es idempotente y tiene modo `--dry-run`.

---

## 5. Pipeline de ingesta (§14, §15, §42)

### 5.1 Crawl targets

- **Derivación:** `crawl_targets` se recalcula en cada tick a partir de los `search_profiles` habilitados. Agrupa por `(source, make, model)` y toma el rango más amplio: año mínimo y máximo, `km_max` más alto (o ninguno) y **sin filtro de precio en origen**, porque los precios se convierten de moneda después.
- **Por qué:** el costo pasa a depender de cuántos modelos se buscan y no de cuántos usuarios hay. Esto también habilita al revendedor del §9, que busca muchos modelos.
- **Cadencia:** `next_run_at = last_run_at + sources.crawl_interval_seconds`. Valores iniciales:

  | Fuente | Intervalo |
  |---|---|
  | MercadoLibre | 5–10 min |
  | V6 y Kavak | 30 min |
  | Facebook | 45–60 min (anti-bot) |

  Más adelante, el plan Pro puede bajar el intervalo de los targets de sus usuarios (§52).
- **Concurrencia:** fuentes distintas corren en paralelo, como hoy con `asyncio.gather`. Dentro de una misma fuente, los targets van en serie y con jitter.

### 5.2 Normalización

Por cada `Listing` que devuelve un collector:

1. **make, model y trim**: se sacan del título y los atributos, con match contra `vehicle_catalog` (aliases + `rapidfuzz`, que ya está en `requirements.txt`). Si no se puede resolver, se usa el make/model del target, pero con `normalization_confidence` más baja. Así se corrige el problema actual de ML, que copia el filtro.
2. **transmisión y combustible**: por regex sobre el título y los atributos ("manual", "MT", "6MT", "AT", "CVT", "automática", "Tiptronic"…).
3. **precio**: `keyword_partial` como hoy, más `price_usd` con `fx.usd_ars_rate()`. La cotización del día se guarda en `fx_rates`.
4. **ubicación**: `geo.geocode_location` con cache, igual que hoy.
5. **published_at**: los parsers actuales (`parse_relative_date`).

### 5.3 Upsert, snapshots y detección de cambios

```
upsert (source, external_id):
  insert  → first_seen_at = last_seen_at = now(); snapshot change_kind='new'; evento listing_new
  update  → last_seen_at = now(); status = 'active'
            if price o mileage o hash(description) o hash(images) o hash(attrs clave) cambió:
                snapshot con change_kind; evento listing_updated
                if price_usd bajó ≥ app_config.price_drop_min_pct: evento price_drop
```

- Todo se hace en una transacción por batch.
- Los eventos (`listing_new`, `listing_updated`, `price_drop`) son una cola en memoria dentro del mismo ciclo del worker. Alimentan matching y notificaciones sin polling adicional.

### 5.4 Re-publicaciones (§15, heurística imperfecta aceptada)

- `fingerprint = hash(make, model, year, round(km, -3), seller_name normalizado, location normalizada)`.
- Cuando entra un listing nuevo: si existe otro con el mismo fingerprint en los últimos 60 días y su precio difiere menos de 10%, se completa `probable_repost_of`.
- El match se genera igual, pero la alerta dice "re-publicado" y **no** cuenta como oportunidad nueva.
- Se excluye de los comparables para no contar dos veces el mismo auto.

### 5.5 Enrichment de la ficha

- **Solo** para listings que generan al menos un match y no tienen `enriched_at`.
- Cada collector implementa `fetch_detail(url)` para traer descripción, versión, transmisión, tipo de vendedor, imágenes y atributos.
- Tiene una cola propia con rate limit por fuente.
- Al terminar se **re-evalúa el match**, porque la transmisión o la versión pueden pasar de `unknown` a un valor concreto, y se recalculan los red flags.

### 5.6 Watchlist refresher (§30)

Que un aviso no aparezca en el listado **no prueba** que se haya ido: solo se leen las primeras 96 publicaciones, ordenadas por más nuevas. Por eso hay un loop diario que:

1. recorre los listings con `saved = true` o con estado `interested`, `contacted` o `visit_scheduled`;
2. llama a `fetch_detail`;
3. si la publicación dio 404, está pausada o vendida, marca `status = 'gone'` y emite `listing_gone`;
4. si no, compara contra el último snapshot, con la misma lógica de la sección 5.3.

Además, cuando la publicación lleva X días publicada (`app_config.watchlist_stale_days`), emite un evento informativo.

### 5.7 Bootstrap (evita el diluvio inicial; se conserva la idea actual)

- **Profile nuevo o editado:** la web marca `rematch_requested_at`. El worker corre el matching contra `listings` activos de los últimos 30 días y crea `matches` con `is_backfill = true`, que **no se notifican**. El usuario ve resultados en la web enseguida ("first value", §36).
- **Target nuevo:** la primera corrida (`first_run_done = false`) no notifica. Los matches de esa corrida también quedan como backfill.
- **Recencia:** se mantiene `RECOMMENDED_MAX_AGE_DAYS` cuando la fuente expone `published_at` (`_is_recent`).

---

## 6. Intelligence (§16–20, §24, §25, §44)

Todo este módulo es determinístico, puro y testeable. El LLM no participa.

### 6.1 Matching

`match(listing, profile) → MatchResult | None`. Por cada hard filter se genera una razón:

```jsonc
"match_reasons": {
  "model":        {"result": "ok",      "detail": "Ford Fiesta"},
  "year":         {"result": "ok",      "detail": "2017 ∈ 2016–2018"},
  "transmission": {"result": "unknown", "detail": "la publicación no lo informa"},
  "price":        {"result": "ok",      "detail": "USD 10.300 ≤ 11.500"},
  "km":           {"result": "ok",      "detail": "112.000 ≤ 150.000"},
  "location":     {"result": "ok",      "detail": "Vicente López · 18 km"},
  "trim":         {"result": "ok",      "detail": "Titanium (preferida)"}
}
```

- Un `fail` descarta el listing. Un `unknown` lo deja pasar, igual que hoy `matches_filters`, pero penaliza el score y en la UI se muestra "❔ no informado".
- **Moneda:** el precio se compara convirtiendo con fx. Se elimina el descarte actual por moneda distinta.
- La base del código es `BaseScraper.matches_filters`, ampliada para devolver razones en vez de un booleano.
- **Cuándo corre:**
  - en `listing_new`;
  - en `listing_updated` (re-score);
  - después del enrichment;
  - en el rematch de un profile;
  - en un **re-score nocturno** de los matches activos de los últimos 14 días, porque la mediana se mueve.
  - Si cambia `scoring_version`, se re-scorea todo.

### 6.2 Comparables y Price Intelligence (§19)

Una función SQL `comparables(listing_id)` que usa `percentile_cont`:

- misma marca y modelo;
- año ±1;
- km ±25%;
- `last_seen_at` dentro de los últimos 30 días;
- sin `price_partial`, sin `probable_repost_of` y sin el propio listing;
- todo en `price_usd`.

**Cascada de especificidad**: se usa el primer nivel que llega a `n ≥ app_config.comparables.min_n` (hoy 5):

1. misma versión y misma transmisión;
2. misma transmisión;
3. solo el modelo.

Devuelve `{median, p25, p75, n, diff_pct, level_used}`, y eso se guarda en `matches.price_ref`.

**Copy obligatorio:**
- "X% debajo del mercado observado", "publicaciones comparables (n=…)", "precio publicado".
- Prohibidos (hay un test de lint sobre los templates): "vale", "precio real", "tasación".

### 6.3 Opportunity Score 0–100 (§17–18)

```
score = round(100 · Σ wᵢ·cᵢ / Σ wᵢ)      cᵢ ∈ [0,1], wᵢ desde app_config.score_weights
```

| Componente | Peso inicial | Curva inicial (`clamp` a [0,1]) | Explicación que se guarda |
|---|---|---|---|
| Precio | 35 | `0.5 + d/20`, con d = % bajo la mediana. Si `n < min_n`: c = 0.5 | "8% debajo de 23 comparables" / "sin comparables suficientes" |
| Match | 25 | Fracción de soft preferences cumplidas (1 si no hay) − 0.15 por cada hard filter `unknown` | "cumple 3/3 preferencias; transmisión no informada" |
| Kilometraje | 15 | `0.5 + 1.25·(1 − km / mediana_km_comparables)`; 0.5 si no hay datos | "10% menos km que comparables" |
| Versión | 10 | Preferida = 1 · desconocida = 0.5 · otra = 0.2 | "versión Titanium (preferida)" |
| Recencia | 10 | `0.5^(horas/24)`, con la edad desde `published_at` o, si falta, `first_seen_at` | "publicado hace 4 min" / "detectado hace 4 min" |
| Completitud | 5 | Fracción de campos clave presentes: año, km, precio, transmisión, versión, ubicación, descripción de 150+ caracteres, 3+ imágenes, tipo de vendedor, fecha | "6/10 datos informados" |

**Guardas que vienen de `price_check`:**
- con d ≥ 65%, no hay match "oportunidad": el listing se trata como precio parcial (`statistical_partial`);
- con 50% ≤ d < 65%, el nivel queda como máximo en `good` y se agrega el red flag correspondiente (`is_suspicious_discount`);
- con `price_partial = true`, el listing se excluye.

**Calibración con el ejemplo del PRD** (§10, §22). Supuestos: Fiesta Titanium 2017, 112.000 km, USD 10.300; mediana USD 11.200 y mediana de km 125.000; publicado hace 4 min; 6/10 datos.

| Componente | cᵢ | wᵢ·cᵢ |
|---|---|---|
| Precio (d = 8,0%) | 0,90 | 31,6 |
| Match | 1,00 | 25,0 |
| Km (112k/125k) | 0,63 | 9,5 |
| Versión | 1,00 | 10,0 |
| Recencia | 1,00 | 10,0 |
| Completitud | 0,60 | 3,0 |
| **Score** | | **89 → 🔥 Alta oportunidad** |

Este caso se convierte en un **fixture dorado**: tiene que quedar entre 85 y 90. Los pesos y las curvas se ajustan con datos reales del piloto, porque son configurables sin deploy.

`score_breakdown` guarda, por cada componente, `{c, w, contribution, explanation}` más `scoring_version`. Es lo que muestran el detalle y el inspector del admin.

### 6.4 Niveles (§20)

Se leen de `app_config.level_thresholds = {high: 85, good: 70, match: 50}`:

| Nivel | Umbral |
|---|---|
| 🔥 high | ≥ 85 |
| 🟢 good | ≥ 70 |
| 🟡 match | ≥ 50 |
| ⚪ low | < 50 |

### 6.5 Red flags (§24)

Son reglas determinísticas sobre la descripción y los números. Cada una tiene id, texto y severidad, y **todas se redactan como "conviene verificar"**:

| id | Regla |
|---|---|
| `no_owners` | La descripción no menciona dueño, titular o "único dueño" |
| `no_service` | No menciona service ni "services oficiales" |
| `no_timing_belt` | No menciona distribución ni correa (solo en modelos con correa, según el catálogo) |
| `much_cheaper` | d ≥ 25% bajo comparables (y d ≥ 50%: "verificar que no sea anticipo") |
| `short_description` | La descripción tiene menos de 150 caracteres o no existe |
| `low_km_for_age` | km / antigüedad menor a 5.000 km por año |
| `partial_price_suspect` | Viene de `price_check` |
| `repost` | Tiene `probable_repost_of` |

Si todavía no hay descripción (antes del enrichment), las reglas que la necesitan quedan pendientes: no se disparan.

### 6.6 Preguntas al vendedor (§25)

- Son **templates determinísticos** que se arman a partir de los red flags y los datos faltantes. Siempre incluyen: saludo, "¿lo seguís teniendo?", "¿sos titular?". Según el caso agregan distribución, services, VTV, choques o reparaciones, y km.
- Opcionalmente, `llm.polish_questions` mejora la redacción (F5).
- La web solo **copia** el texto. Nunca se contacta al vendedor (§6).

---

## 7. Motor de notificaciones (§21, §22, §32, §47)

### 7.1 Decisión

`engine.decide(event)` → cero o más `notifications` en estado `queued` o `digest`:

| Evento | Condición | `kind` |
|---|---|---|
| Match nuevo (no backfill) | level = high y high ≥ `notify_min_level` | `opportunity` |
| Match nuevo (no backfill) | level ≥ `notify_min_level` | `new_match` |
| Match nuevo | level < `notify_min_level` | Ninguno: se ve solo en la web y el digest |
| Match nuevo con `probable_repost_of` | Según nivel | `new_match` con la etiqueta "re-publicado" |
| `price_drop` | Listing guardado, o con match de nivel ≥ match; baja ≥ `price_drop_min_pct` (3%) | `price_drop`, con el score nuevo |
| `listing_gone` | Listing guardado o en seguimiento | `listing_gone` (va al digest) |

Reglas:

- **Frecuencia**: con `immediate` se encola y se envía; con `daily` va al digest. Los `price_drop` de publicaciones guardadas son siempre inmediatos.
- **Tope diario**: `app_config.alerts_max_per_user_day` (default 10) sobre los envíos inmediatos. Lo que se pasa del tope se degrada a digest y queda registrado. El KPI `alerts/user/day` del §47 está en el admin.
- **Dedupe**: hay un `UNIQUE(user_id, dedupe_key)`, con `dedupe_key = kind:listing_id[:snapshot_id]`. No se re-alerta nunca la misma publicación por el mismo motivo (§15).
- **Multi-profile**: si un listing matchea varios profiles del mismo usuario, sale una sola notificación, con el nivel más alto.

### 7.2 Canales

Hay una interfaz `Channel.send(notification) → result`, y cada adapter vive en `channels/`:

| Canal | Uso | Notas |
|---|---|---|
| Telegram | Canal existente, prioridad alta en el §21 | `_format_notification` pasa a `templates.py` (HTML, igual que hoy). Suma los botones inline ⭐ Me interesa · ✖ Descartar · 🔎 Ver en Automotive |
| Email (Resend) | Obligatorio en el §21; digest diario e inmediato opcional | Templates HTML + texto. Remitente de un dominio verificado |
| Web inbox | Obligatorio en el §21 | La fila en `notifications` + Supabase Realtime pintan un badge y el feed |
| Push mobile | Futuro (§21) | Otro adapter más; el engine no cambia |

- **Digest diario:** un loop a la hora configurada (`app_config.digest_hour`, default 20:00 ART) arma, por usuario, el top N por score del día más las bajas de precio y los avisos de "desapareció".
- **Plantillas de los tres tipos del §22:**
  - `new_match`: 🚗 Nuevo vehículo encontrado.
  - `opportunity`: 🔥 Nueva oportunidad, con score, "% debajo de publicaciones comparables" y "publicado hace X".
  - `price_drop`: 📉 Bajó de precio, con antes, ahora y %.

  Si no hay `published_at`, se dice "detectado hace X" y no "publicado hace X" (§11, principio 5: no fingir certeza).

### 7.3 Tracking de aperturas y clics

- Todo link sale como `https://<web>/r/<notification_id>?to=detail|listing`. Es un route handler de Next.js que actualiza `clicked_at` (y `opened_at` si estaba vacío), inserta el evento `alert_clicked` y redirige.
- **Definición operativa de "apertura" (§37):** Telegram no expone lecturas, así que *apertura = primer clic en cualquier link de la alerta*. En el web inbox, además, se marca `opened_at` al verla. No se usan pixels de tracking en email.

---

## 8. Capa LLM (§43, §44)

### 8.1 Interfaz

```python
class LLMProvider(Protocol):
    async def parse_search(self, text: str) -> list[SearchDraft]: ...          # modo asistido (§12)
    async def extract_listing_facts(self, title: str, description: str) -> ListingFacts: ...  # opcional
    async def polish_questions(self, questions: list[str], context: dict) -> str: ...          # opcional
```

`SearchDraft` y `ListingFacts` son modelos Pydantic. Su JSON Schema se usa **a la vez** como `--json-schema` del CLI y para validar la respuesta.

### 8.2 `ClaudeCliProvider` (piloto)

```
claude -p \
  --output-format json \
  --json-schema '<schema de SearchDrafts>' \
  --system-prompt "<instrucciones + catálogo de marcas/modelos/versiones relevante>" \
  --tools "" \
  --no-session-persistence \
  --strict-mcp-config --setting-sources "" \
  --model haiku  < "<pedido>texto del usuario</pedido>"
```

- Se lanza con `asyncio.create_subprocess_exec`, sin shell. El texto del usuario va por **stdin**, dentro del mensaje (`<pedido>…</pedido>`), nunca en la línea de comandos: así no puede leerse como un flag. Sin tools, sin sesión guardada, sin MCP ni settings, y con el directorio temporal como cwd (no aplica ningún CLAUDE.md del repo). Tiene un presupuesto configurable por job (`LLM_TIMEOUT_SECONDS`, 60 s) con un reintento adentro: una falla rápida se reintenta con el tiempo que queda; un timeout no.
- De la salida se toma `structured_output` del envelope JSON (o `result`, parseado) y se valida con Pydantic. Si no valida, el job queda `failed` y la web cae al formulario estructurado.
- Requisitos del host del worker: Claude Code instalado y logueado. La ruta se configura con `CLAUDE_CLI_PATH`.
- Se registran `provider`, `latency_ms` y el error en `llm_jobs`, para comparar después con el LLM local.

### 8.3 `LocalProvider` (lanzamiento)

- Un endpoint compatible con OpenAI (Ollama o llama.cpp server), con JSON mode o gramática, usando el mismo schema.
- Se elige con `LLM_PROVIDER=claude_cli|local`, más `LOCAL_LLM_BASE_URL` y `LOCAL_LLM_MODEL`.
- Hay tests de contrato comunes a los dos providers: los mismos inputs dorados tienen que producir drafts válidos.

### 8.4 Flujo del modo asistido en la web

1. El usuario escribe "Busco Fiesta Titanium manual 2016 a 2018 hasta USD 11.500…".
2. La web inserta `llm_jobs(kind='parse_search', input={text})` con RLS.
3. El worker toma el job (`FOR UPDATE SKIP LOCKED`) y ejecuta el provider.
4. Después **normaliza los drafts contra `vehicle_catalog`**, que es un paso determinístico, y escribe `output`.
5. La web recibe el resultado por Realtime (o polling cada 2 s como fallback). Muestra **uno o más formularios pre-completados y editables**, uno por vehículo, y el usuario confirma o corrige antes de guardar (§12).
6. Si hay error o timeout (60 s), se muestra el mensaje "No pude interpretarlo, completá los filtros" y el formulario estructurado vacío.

**Guardarraíles del §44:** el LLM nunca calcula precio, score, dedupe ni timestamps, y nunca aplica filtros sin la confirmación del usuario. Lo que el usuario guarda son siempre filtros estructurados.

---

## 9. Web (Next.js + Supabase)

**Stack:**
- Next.js (App Router, TypeScript), `@supabase/ssr` y Tailwind + shadcn/ui;
- Recharts para el histórico de precios;
- tipos generados desde la base.

**Auth:** Supabase magic link / OTP por email. Local se prueba con Inbucket (`supabase start`).

**Patrón de datos:**
- Server Components leen con la sesión del usuario (RLS).
- Las mutaciones van por Server Actions.
- Los agregados del dashboard salen de funciones SQL `security invoker` (`dashboard_summary()`, `search_results(profile_id, filter, sort)`).

| Ruta | Contenido (PRD) |
|---|---|
| `/` | Landing del §50: hero, card de ejemplo, 4 beneficios, CTA "Crear mi búsqueda" |
| `/login` | Email → magic link |
| `/app` | Dashboard del §28: cards por búsqueda ("14 nuevos esta semana · 2 oportunidades · Ver resultados") y feed "Oportunidades recientes" ordenado por score y fecha de detección |
| `/app/searches/new` | Pestañas **Asistido** (sección 8.4) y **Estructurado** (marca, modelo, versión, años, km máx., precio máx. + moneda, transmisión, combustible, ubicación + radio o preset AMBA). Autocompletado desde `vehicle_catalog`. Frecuencia y nivel mínimo de alerta. Preview "N publicaciones actuales coinciden" |
| `/app/searches/[id]` | Resultados del §29. Filtros: nuevos · oportunidades · todos · favoritos · descartados. Orden: recientes · mejor oportunidad · menor precio · menor km. Editar, pausar y frecuencia |
| `/app/listings/[id]` | Detalle del §23: vehículo, precio, km, ubicación, "publicado/detectado hace X", score + nivel + desglose, **¿Por qué apareció?** (checklist ✅/❔ de `match_reasons`), **Análisis de precio** (precio, mediana, n, diferencia), **Histórico de precios** (§31, si hay 2 o más snapshots de precio), **Conviene verificar** (red flags), **¿Qué le pregunto al vendedor?** (texto + copiar), selector de estado (§26), motivo de descarte (§27), ⭐ guardar, **Compré este vehículo** (crea `owned_vehicles` y pregunta por la influencia del §38) y "Ver publicación" vía `/r/` |
| `/app/saved` | Watchlist del §30, con eventos: bajó de precio, desapareció, cambió, "lleva X días" |
| `/app/settings` | Canales: vincular Telegram con el deep link `t.me/<bot>?start=<telegram_link_code>` y el email. Ubicación por defecto y frecuencia |
| `/r/[notificationId]` | Redirect con tracking (sección 7.3) |
| `/admin/**` | Backoffice (sección 10) |

- **Vincular Telegram:** el bot recibe `/start <code>`, busca `profiles.telegram_link_code`, guarda el `telegram_chat_id` y rota el código.
- **Acciones inline:** callbacks del tipo `act:<listing_id>:interested|discarded` que el worker escribe en `user_listing_interactions` más el evento correspondiente.
- **Monetización (§52):** cuando el usuario tiene actividad real (por ejemplo 3 o más alertas clickeadas), aparece el banner "¿Querés enterarte antes?" con el CTA **Probar Automotive Pro**. Lleva a una pantalla de planes (Pro mensual vs Search Pass 30/90 días, §33–34) con "Sumarme a la lista de espera" y registra `pro_cta_viewed`, `pro_cta_clicked` y `waitlist_joined` con el plan elegido. Todavía no hay cobro.

---

## 10. Backoffice y observabilidad (§45, §46)

Rutas `/admin`, protegidas por el chequeo de `role = 'admin'` en middleware y en el servidor. Leen con el cliente de service role, que solo existe del lado del servidor.

| Vista | Contenido |
|---|---|
| Resumen | Métricas de la sección 11 + estado de las fuentes |
| Usuarios | Plan, profiles, alertas por día, última actividad |
| Búsquedas | Filtros, cantidad de matches y alertas, `bootstrapped_at` |
| Listings | Búsqueda por fuente, id o modelo. Snapshots, matches y red flags |
| Fuentes / collectors | `collector_runs`: estado, encontrados/nuevos/actualizados, duración, error. Fallas consecutivas. Editar `crawl_interval_seconds` |
| Matches y scores | Distribución de scores por nivel y por fuente |
| Notificaciones | Enviadas, fallidas, degradadas a digest; clics |
| Errores | `pipeline_errors` por etapa |
| **Inspector "¿por qué se envió?"** | Para una notificación o match: listing ↔ search, `match_reasons` campo por campo, `score_breakdown`, `price_ref` (con el nivel de cascada usado) y red flags. Exactamente el formato del §45 |
| Config | Edición de `app_config`: pesos, umbrales, topes y límites de plan |

Mientras no existe la web, hay un inspector por CLI: `python -m tools.explain_match <match_id>` (desde F2).

**Alertas operativas:** si una fuente acumula N fallas consecutivas (`app_config.collector_failure_alert_after`, default 3), se manda un mensaje al `TELEGRAM_ADMIN_CHAT_ID`. Los logs siguen yendo a stdout. No se necesita infraestructura extra (§46).

---

## 11. Métricas y eventos (§35–38, §53)

**Catálogo de eventos** (`events.name`):

- **Cuenta:** `signup_completed`.
- **Búsquedas:** `search_profile_created` (`mode: assisted|structured`), `search_profile_updated`, `search_profile_paused`.
- **Alertas:** `alert_sent`, `alert_clicked`.
- **Publicaciones:** `listing_detail_viewed`, `listing_outbound_clicked`, `listing_status_changed`, `listing_saved`, `listing_discarded` (`reason`).
- **Preguntas al vendedor:** `seller_questions_generated`, `seller_questions_copied`.
- **Compra:** `vehicle_purchased`, `purchase_influence_answered`.
- **Monetización:** `pro_cta_viewed`, `pro_cta_clicked`, `waitlist_joined`, `plan_limit_hit`.

**Vistas SQL** (el admin las lee):

| Vista | Definición |
|---|---|
| `v_north_star_weekly` | Publicaciones **relevantes** abiertas desde una alerta, por usuario activo y por semana. *Relevante* = clickeada desde una alerta y no descartada con un motivo que indique que no era match (`automatic`, `wrong_trim`, `location`) |
| `v_activation` | Registrados → con 1 o más profiles (objetivo 70%, §36) |
| `v_first_value` | Tiempo desde la creación del profile hasta el primer match de nivel ≥ good (incluye backfill) |
| `v_alert_funnel` | Por nivel y canal: enviadas → clickeadas → guardadas → descartadas |
| `v_high_score_engagement` | Engagement con high contra match/good (§37). Si no hay diferencia, el score no aporta |
| `v_alerts_per_user_day` | KPI de ruido (§47) |
| `v_outcomes` | Compras, influencia y tiempo usando Automotive (§38) |
| `v_validation_criteria` | Los 6 criterios del §53 contra su umbral: ≥30 usuarios con búsquedas activas, ≥30% de alertas abiertas, ≥15% de click o guardado, retención semanal, contactos o visitas, ≥10% de intención de pago |

**Definiciones operativas (F6).** Todas las vistas excluyen a los admins. Una *alerta* es una fila `(user_id, dedupe_key)` entregada (envío inmediato o dentro de un digest enviado), cualquiera sea la cantidad de canales; se abre o clickea si pasó en cualquiera de ellos. *Usuario activo* de una semana: recibió una alerta o generó cualquier evento que no sea `alert_sent`. En `v_validation_criteria`:

- **Engagement:** publicaciones alertadas (por usuario) con clic en la alerta, clic a la fuente (`listing_outbound_clicked`) o guardadas / «Me interesa».
- **Retención:** de los usuarios cuya primera búsqueda tiene ≥ `retention_weeks` semanas (3), los que estuvieron activos en los últimos 7 días; umbral 40%. El PRD no da número: es una decisión del piloto.
- **Outcome:** usuarios que contactaron, agendaron visita o compraron; umbral 3 («algunos»), también una decisión del piloto.
- **Monetización:** usuarios con búsqueda activa que se sumaron a la lista de espera o tienen un plan pago vigente.

Los umbrales viven en `app_config.validation_criteria` y se editan desde `/admin/config`.

---

## 12. Freemium (§33, §34)

- **`profiles.plan`** puede ser `free`, `pro` o `pass`, con `plan_expires_at` para el Search Pass.
- **`app_config.plan_limits`:**

  ```json
  {
    "enforced": false,
    "free": {"max_profiles": 1, "max_visible_results": 50, "immediate_alerts": false},
    "pro":  {"max_profiles": 10, "immediate_alerts": true, "crawl_priority": "high"},
    "pass": {"max_profiles": 10, "immediate_alerts": true, "crawl_priority": "high"}
  }
  ```

- **Mientras `enforced = false` (el piloto):** todo está habilitado, pero cada vez que un usuario free supera un límite se registra `plan_limit_hit` y se ofrece el CTA de Pro. Así se mide la intención de pago sin frenar la validación.
- **Dónde se mide cada límite:** `max_profiles` y `immediate_alerts` con triggers en `search_profiles` (con `enforced = true`, la búsqueda de más se rechaza y la inmediata pasa a diaria); `max_visible_results` lo reporta la web a `record_plan_limit_hit()`, que deduplica por búsqueda y día (con `enforced = true`, la web corta los resultados). Un Pro o Search Pass vencido cuenta como free (`plan_limits_for()`).
- **CTA (§52):** `pro_cta_state()` lo muestra a usuarios free que no están en la lista de espera después de `pro_cta.min_alert_clicks` alertas clickeadas (3) o de pasar un límite a propósito (`pro_cta.on_limits`, por defecto `max_profiles`). Los límites pasivos (alertas inmediatas, resultados) solo se miden, para no mostrarle el CTA a todo usuario nuevo.
- **Cobro real:** queda fuera de este plan. Se decide con los datos de `waitlist_joined`.

---

## 13. Roadmap por fases

Las fases van en orden. Cada una deja el sistema funcionando: el bot de Telegram sigue alertando durante toda la transición. Tamaños relativos: S, M, L.

### F0 · Fundaciones (M)

- **Alcance:**
  - proyecto Supabase (`sa-east-1`) + `supabase/` con las migraciones de la sección 4 y el seed (`sources`, `app_config`, `vehicle_catalog` inicial con los modelos más buscados);
  - reorganización a `worker/`;
  - `worker/db` con psycopg (el pooler en modo sesión o la conexión directa; con el transaction pooler, `prepare_threshold=None`);
  - `migrate_sqlite.py`.
- **Aceptación:**
  - el bot actual funciona igual que hoy leyendo y escribiendo en Postgres;
  - `pytest` pasa (los tests existentes se mueven);
  - `supabase db reset` aplica las migraciones desde cero;
  - la migración de una copia de `automotive.db` es idempotente.
- **Tests:** pytest y pgTAP para RLS básica.

### F1 · Ingesta centrada en la publicación (L)

- **Alcance:**
  - crawl targets y cadencia por fuente;
  - normalización v2 (catálogo, transmisión, `price_usd`);
  - upsert canónico, snapshots y detección de cambios;
  - fingerprint y re-publicaciones;
  - `fetch_detail` y enrichment de publicaciones con match;
  - watchlist refresher;
  - `collector_runs` y `pipeline_errors`;
  - registrar `autocosmos` en `REGISTRY` si sus selectores siguen vivos.
- **Aceptación:**
  - dos corridas seguidas no duplican publicaciones;
  - un cambio de precio simulado genera un snapshot `price` y un evento `price_drop`;
  - `first_seen_at` no cambia en los updates;
  - el costo de scraping no crece al agregar un profile repetido.
- **Tests:** parsers con HTML guardado como fixture; ingesta contra Postgres local.

### F2 · Intelligence (M)

- **Alcance:**
  - matching con razones;
  - comparables v2 con cascada;
  - score 0–100 con breakdown y niveles;
  - red flags y preguntas al vendedor con templates;
  - `app_config` de pesos y umbrales;
  - re-score nocturno;
  - `tools/explain_match.py`.
- **Aceptación:**
  - el fixture dorado de la sección 6.3 da entre 85 y 90;
  - un `unknown` nunca descarta un listing, pero baja el score;
  - los avisos en ARS se comparan bien contra un tope en USD;
  - el test de lint del copy prohibido (§19) pasa.
- **Tests:** pytest puro, sin red ni base, con fixtures dorados.

### F3 · Motor de notificaciones (M)

- **Alcance:**
  - `engine.decide` con la tabla de la sección 7.1;
  - canales Telegram (migrado, con botones inline), email (Resend) y web;
  - digest diario, tope diario y dedupe;
  - `notifications` como log;
  - redirect con tracking (se puede servir con un endpoint mínimo hasta que exista la web).
- **Aceptación:**
  - la misma publicación nunca genera dos alertas del mismo tipo;
  - con el tope en 2, la tercera alerta del día va al digest;
  - los tres tipos del §22 llegan por Telegram y por email con el copy correcto.
- **Tests:** fakes de los canales; tests de la tabla de decisión; snapshot de los templates.

### F4 · Web MVP (L)

- **Alcance:**
  - auth, landing, dashboard;
  - alta y edición estructurada de búsquedas con preview de backfill;
  - resultados con filtros y orden;
  - detalle completo del §23;
  - estados, descarte con motivo, watchlist;
  - "Compré este vehículo" → `owned_vehicles` + encuesta;
  - settings y vinculación de Telegram;
  - web inbox con Realtime.
  - Se retira el wizard de Telegram, que redirige a la web.
- **Aceptación:** un e2e completo:
  1. registro;
  2. creación de búsqueda;
  3. ver el backfill;
  4. llega una alerta simulada;
  5. clic en la alerta;
  6. marcar "Me interesa";
  7. marcar como comprado.
  Además, la navegación funciona en mobile (viewport de 375 px).
- **Tests:** Playwright e2e contra Supabase local y seed.

### F5 · Modo asistido con LLM (S–M)

- **Alcance:**
  - `llm_jobs` y su loop;
  - `ClaudeCliProvider`;
  - normalización de drafts contra el catálogo;
  - UI de revisión multi-vehículo;
  - `polish_questions` opcional;
  - `extract_listing_facts` opcional para enriquecer los red flags.
- **Aceptación:**
  - 20 frases de ejemplo (fixture) producen drafts válidos y editables;
  - si el LLM falla, se cae al formulario sin romper el flujo;
  - la latencia p95 queda registrada.
- **Tests:** contrato del provider con respuestas grabadas; smoke test real con `claude -p` detrás de un flag.

### F6 · Backoffice, métricas y monetización (M)

- **Alcance:**
  - `/admin` completo con el inspector;
  - vistas SQL de la sección 11;
  - CTA Pro y lista de espera;
  - límites de plan configurables;
  - alerta de collector caído al admin.
- **Aceptación:**
  - desde el admin se puede responder "¿por qué se envió esta alerta?" en 1 clic;
  - `v_validation_criteria` muestra los 6 criterios del §53 con datos del seed.
- **Tests:** vistas SQL con eventos del seed.

### F7 · Piloto: puesta en producción (M)

F0–F6 dejan el producto completo, pero todo corre en una sola PC con Supabase local: nadie de afuera puede registrarse ni recibir un magic link. F7 es lo mínimo para abrir el piloto del §51 sin perder datos ni métricas. Mientras tanto el sistema corre en local (web en `127.0.0.1:3000`, Supabase local, worker en la PC).

**Estado:** hosting decidido (opción *B*, web y worker en la PC con Cloudflare Tunnel). **Cambio del 29/09:** la base pasó a Supabase en la nube, en una organización Free (US$0; el costo de ~US$10/mes de la opción *A* era por crear el proyecto en una organización Pro): proyecto `dnqyravczgcpuowijbja`, `sa-east-1`, con migraciones y seed aplicados. El túnel solo publica la web; Auth, SMTP y claves se configuran en el dashboard y no en `config.toml`/`supabase/.env` (que quedan para el stack local de desarrollo y tests), y la tarea *Supabase* ya no existe. El backup hace `pg_dump` de la nube con Docker. El código de los 12 puntos está hecho; lo que falta son cuentas y configuración que solo puede hacer el dueño, paso a paso en [PILOT_SETUP.md](PILOT_SETUP.md):

- **1–3:** `supabase/config.toml` toma la URL pública, el SMTP de Resend y claves propias del stack de `supabase/.env` (`tools/supabase_keys.py` reemplaza las claves de demo de la CLI, que con la API pública dejarían entrar a cualquiera); falta crear el túnel, el dominio y la cuenta de Resend.
- **6:** `LLM_PROVIDER=anthropic` (`llm/anthropic_api.py`, API de Claude con structured outputs, mismo contrato); falta la API key.
- **8:** log a archivo UTF-8 con rotación, latido (`worker_heartbeat`, visible en `/admin/sources`), `tools/watchdog.py`, y `ops/` (supervisor con reinicio, tareas programadas, backup diario con restore probado, `update.ps1`); falta instalar las tareas.
- **9:** Kavak, V6 y Autocosmos OK el 28/09; faltan renovar las sesiones de MercadoLibre (bloqueado) y Facebook (0 resultados).
- **11:** Open Graph con imagen, `robots.txt` y `sitemap.xml`.

~~La API se publica solo en `/auth`, `/rest` y `/realtime`: en el mismo puerto están pgMeta (`/pg/*`) y Storage sin autenticación.~~ Ya no aplica: la API es la de Supabase en la nube.

- **Alcance:**
  1. **Hosting (decisión abierta, bloquea 2–4 y 8).** La web y la API de Supabase tienen que ser públicas, porque el navegador habla directo con Supabase (Auth, Realtime). Opciones:
     - *A.* Supabase hosteado (`sa-east-1`, ~US$10/mes) + web en Vercel + worker en la PC;
     - *B.* todo en la PC, expuesto con Cloudflare Tunnel (web `:3000` y API `:54321` en dos subdominios). Costo cero; la disponibilidad depende de la PC.
     Sea cual sea: `supabase/config.toml` (`site_url`, `additional_redirect_urls`), `SITE_URL` y `NEXT_PUBLIC_SUPABASE_URL` de la web, `WEB_BASE_URL` del worker y una sección de deploy en el README.
  2. **Dominio con https.** Lo necesitan el remitente verificado de Resend, el botón «Ver en Automotive» de Telegram (solo https) y el `site_url` de Auth.
  3. **Email de Auth real.** `[auth.email.smtp]` con Resend (hoy los magic links quedan en Inbucket). Subir `auth.rate_limit.email_sent` (hoy 2/hora) y revisar el template `magic_link.html` con el dominio final.
  4. **Base de tests separada.** Los tests de Postgres hacen `TRUNCATE` de las tablas de datos y hoy apuntan a la misma base que el piloto. Una base `automotive_test` en el mismo Postgres (o un stack aparte) y un guard en `worker/tests/pgcase.py` que se niegue a correr contra la base configurada en `DATABASE_URL`. Actualizar el README.
  5. **Configuración completa del worker.** `.env` alineado con `.env.example`: `WEB_BASE_URL` (sin esto no hay `/r/<id>` y se rompen «alertas abiertas» y engagement del §53), `RESEND_API_KEY` + `EMAIL_FROM` (email es canal obligatorio del §21), `TELEGRAM_ADMIN_CHAT_ID` y `CLAUDE_CLI_PATH`. Un chequeo al arrancar que loguee en `WARNING` cada canal o métrica que queda apagada.
  6. **Proveedor LLM para terceros.** Resolver la decisión de la sección 14 sobre `claude -p` con suscripción: agregar un `AnthropicApiProvider` (API key, Haiku, mismo schema y mismos tests de contrato) y/o implementar `LocalProvider` (sección 8.3). `LLM_PROVIDER` elige.
  7. **Legal y privacidad (Ley 25.326).** Páginas `/privacidad` y `/terminos` enlazadas desde la landing y el login; «Borrar mi cuenta» en `/app/settings` (borra `auth.users` en cascada y registra el evento antes); link de baja en los emails (`List-Unsubscribe` + ruta que saca `email` de los canales).
  8. **Operación del worker.** Correrlo como servicio que se reinicia solo y arranca con Windows (NSSM o Task Scheduler); logs a archivo con rotación, con el logger `httpx` en `WARNING` (en `INFO` escribe la URL de la API de Telegram, que incluye el token del bot); un *heartbeat* (`app_config` o tabla) que el admin muestre, y una alerta externa si el worker deja de latir (el aviso de fuentes caídas vive dentro del worker y muere con él). Backup diario de la base (`pg_dump`) si se sigue en local.
  9. **Smoke de fuentes reales.** Correr `tools.scraper_cli` contra las 5 fuentes, renovar `ml_state.json` / `fb_state.json`, y dejar una corrida completa en `collector_runs` sin errores antes de invitar usuarios.
  10. **Retención de datos** (sección 14): job diario que borra listings `gone` sin interacción de más de 180 días (y sus snapshots). Imprescindible si se elige el free tier hosteado (500 MB).
  11. **Lanzamiento (§51):** Open Graph + imagen, `robots` y `sitemap` en la landing.
  12. **Limpieza:** carpetas vacías de la raíz (`scrapers/`, `bot/`, `tests/`, `tools/`), `bot.log`, `ml_dom.html`; README al día (paso 6 de «Cómo funciona» y la nota «hasta que F3…»).
- **Opcional (no bloquea el piloto):** conectar `polish_questions` y `extract_listing_facts` (F5) al detalle y al enrichment; sumar «ya lo vi» a `rejection_reason` si aparece seguido.
- **Aceptación:**
  - una persona desde otra red se registra con un magic link real, crea una búsqueda y recibe una alerta por email y Telegram cuyo clic queda en `notifications.clicked_at`;
  - correr toda la suite de tests no toca los datos del piloto;
  - reiniciar la PC deja el worker corriendo sin intervención, y apagarlo dispara una alerta;
  - un usuario puede leer la política de privacidad, darse de baja del email y borrar su cuenta;
  - las 5 fuentes tienen una corrida `ok` en `collector_runs` en las últimas 24 h.
- **Tests:** guard de la base de tests (pytest), borrado de cuenta y baja de email (pgTAP + e2e), retención (Postgres), contrato del nuevo provider LLM.

**Después de F7:** piloto con 20–50 usuarios (§51). Se evalúa con `v_validation_criteria`.

### F8 · Barrido por recencia (M–L)

**Por qué:** hoy se scrapea por crawl target (fuente × marca × modelo). Ese esquema escala con los usuarios, pero no con los modelos: el costo es modelos distintos × fuentes × frecuencia. Además, los datos dependen de lo que alguien buscó. Un modelo nuevo arranca sin historia y sin mediana de comparables, y el Opportunity Score depende de esa mediana.

F8 separa la captura de la demanda. Por fuente, se recorre el catálogo de usados completo o «más nuevos primero». Así:

- el costo pasa a ser proporcional a los avisos nuevos o al tamaño del catálogo, no a los modelos buscados;
- la base tiene todo el mercado para comparables desde el día uno;
- un aviso que deja de aparecer en barridos completos se puede dar de baja sin pedir su ficha.

**Qué ofrece cada fuente** (relevado en vivo el 29/09/2026):

| Fuente | Catálogo de usados | Orden «más nuevos» | Barrido propuesto |
|---|---|---|---|
| V6 | ~170 avisos, 20 por página, render en el navegador | Sí: `sortOrder=publicadoMasNuevo`. **Hoy el colector usa `sort=recent`, que no ordena** | Incremental cada 30 min hasta llegar a un aviso conocido, y completo cada 24 h (unas 9 páginas) |
| Autocosmos | ~6.024 avisos, 48 por página, HTTP (~126 páginas) | No: solo relevancia, precio, cuota y anticipo. Las cards no traen fecha | Completo cada 6 h por HTTP, una página cada 3 s (unos 7 min). Los targets siguen para los modelos buscados, que necesitan avisos rápidos |
| Kavak | ~1.260 autos, 30 por página, 42 páginas, render en el navegador | Tiene «Más nuevo», pero no cambia la URL. Hay que verificar si ordena por ingreso o por año. Los ids son numéricos y crecientes | Completo cada 6 h. Incremental solo si «Más nuevo» es por ingreso |
| Facebook | Por ciudad, con scroll infinito y sesión | Sí: el feed `/marketplace/<ciudad>/vehicles?sortBy=creation_time_descend` (el colector ya lo arma sin query) | Incremental por ciudad de las búsquedas activas. No se puede recorrer el país entero |
| MercadoLibre | El más grande. El web corta en ~2.000 resultados por consulta | Hay que verificar si `_OrderId_BEGIN` es «más recientes» | **Bloqueado** (login wall, 146 corridas fallidas). Queda con targets hasta resolver la sesión o la API oficial (fuera de F8) |

**Alcance:**

0. **Relevamiento (1–2 días, antes de codificar):**
   - confirmar qué ordena «Más nuevo» en Kavak y cómo pedirlo (parámetro o API interna del front);
   - con la sesión de Facebook renovada: cuántos avisos da el feed por ciudad antes de repetirse, y qué radio cubre;
   - medir avisos nuevos por día por fuente, con un barrido manual con `scraper_cli sweep <fuente> --dry-run`, para fijar las cadencias con datos.
1. **Modelo:**
   - `crawl_targets.kind` (`model` | `sweep`): un barrido es un target con make/model null y `query` = `{mode: incremental|full, city?}`. Así reusa la cadencia, `collector_runs`, la salud de fuentes y las alertas al admin.
   - En `sources`: `ingest_mode` (`targets` | `sweep` | `both`), `sweep_incremental_seconds`, `sweep_full_seconds`, `sweep_page_interval_seconds` y `sweep_max_pages`. Se editan en la base, sin deploy.
   - `listings.last_full_sweep_at`: el último barrido completo que lo vio.
2. **Colectores:**
   - `BaseScraper.sweep(mode, known)` devuelve un iterador async de páginas de `Listing`. `known` es el conjunto de ids ya vistos: el incremental corta en la primera página sin avisos nuevos.
   - Implementar V6 (y corregir ya su `sortOrder` en los targets), Autocosmos y Kavak; Facebook por ciudad después.
   - Un `CollectorBlocked` corta el barrido y aplica el backoff de la fuente.
   - Tests con fixtures HTML de dos páginas.
3. **Pipeline:**
   - `crawl.py` corre los barridos como cualquier target, con una transacción de ingesta por página. Si se corta a mitad de camino, no se pierde lo ingestado.
   - El matching pasa a hacerse **por aviso**: `process_batch` agrupa los ids por (make, model) del aviso y busca los perfiles de cada grupo (`alerts_for_model`), en vez de los perfiles del target.
   - El primer barrido de una fuente es silencioso (backfill), igual que el primer run de un target.
   - Baja por ausencia: un aviso activo que no aparece en 2 barridos completos seguidos de su fuente pasa a `gone`, con el evento `listing_gone` y la razón «no aparece en la fuente». Solo aplica a fuentes con barrido completo y solo si el barrido terminó sin errores.
   - El enriquecimiento sigue según la demanda (matches y precios parciales). Barrer no implica pedir fichas.
4. **Comparables:** con el mercado completo, revisar `min_n` y la ventana de `comparables` (hoy 30 días) y el nivel `model` frente a `trim`. Tiene que medirse, no suponerse: `admin_score_histogram` antes y después.
5. **Backoffice y métricas:**
   - `/admin/sources` muestra por fuente el último barrido completo, las páginas, los nuevos por día, la cobertura (avisos vistos en el último completo frente a los activos) y las bajas por ausencia.
   - Una alerta al admin si un barrido completo trae menos del 50% de lo habitual: suele ser un cambio de layout.
6. **Rollout por fuente:**
   - Una semana con `ingest_mode=both` (targets y barrido en paralelo), comparando qué encontró cada uno.
   - Después, `sweep` donde el barrido cubre lo mismo o más con el mismo aviso rápido (V6; Kavak si tiene incremental).
   - Autocosmos y Facebook quedan en `both`; MercadoLibre en `targets`.

**Fuera de alcance:** una cola de trabajos con rate limit y varios workers, MercadoLibre por API oficial y hosting. Se retoman si el volumen lo pide.

**Aceptación:**
- con V6, Autocosmos y Kavak barridos, una búsqueda nueva de un modelo que nadie buscaba muestra resultados y una mediana de comparables al instante, sin esperar un crawl;
- un aviso nuevo de V6 aparece en menos de 30 min, y en Autocosmos y Kavak en menos de 6 h, además de los targets;
- un aviso borrado en la fuente pasa a `gone` en menos de 2 barridos completos, sin pedir su ficha;
- el costo en requests por día de cada fuente no cambia al sumar 50 modelos buscados nuevos;
- `/admin/sources` muestra la cobertura y ninguna fuente barrida tiene errores en 24 h.

**Tests:**
- barrido incremental que corta en un id conocido y barrido completo con baja por ausencia (Postgres);
- barrido cortado a la mitad: lo ingestado queda y no hay bajas;
- matching por aviso de otro modelo que el del target;
- primer barrido silencioso;
- colectores con fixtures de dos páginas.

**Costo:** US$0. Todo corre en la PC del piloto, y la base crece unos 15–20 MB por el catálogo de Autocosmos y Kavak.

**Correspondencia con la priorización del PRD (§48):**
- **P0** = F0–F4 (registro/login, profiles, collectors, normalización, nuevos, matching, dedupe, alertas, dashboard, resultados, link original, favoritos, descartados y tracking).
- **P1** = F2 (score, comparables, precio, "por qué apareció"), F3 (alertas de precio), F4 (estados, múltiples profiles) y F5 (lenguaje natural, preguntas).
- **P2** queda fuera del plan.

---

## 14. Riesgos y decisiones abiertas

| Riesgo / decisión | Mitigación / propuesta |
|---|---|
| Anti-bot y ToS de FB y ML (§47) | Collectors aislados; `collector_runs` con alerta de fallas; cadencia conservadora en FB; si una fuente se cae, el resto sigue |
| **Host del worker** (decisión abierta) | Necesita Playwright y las sesiones `fb_state.json`/`ml_state.json`. Piloto: la PC actual. Después: un VPS chico en Argentina o Brasil (conviene IP residencial para FB) |
| `claude -p` en el piloto | Límites de uso de la suscripción y latencia de 5–20 s: aceptables para la creación de búsquedas. Revisar que el uso automatizado desde un servicio sea compatible con los términos del plan de Claude Code. La salida prevista es el LLM local o una API key |
| Crecimiento de `listing_snapshots` y `listings` en el free tier de Supabase (500 MB) | Snapshots solo cuando hay cambios; retención de 180 días para listings `gone` sin interacción; índices justos |
| Tipo de cambio | `price_usd` se congela con la cotización del día de observación (blue, con fallback al oficial) y se guarda en `fx_rates` para reproducir cálculos |
| Precisión de la detección de re-publicaciones | Aceptada como imperfecta (§15). Se mide en el admin con los reposts marcados y los descartes con motivo "ya lo vi" (se puede sumar al enum si aparece seguido) |
| Datos incompletos en las cards | Enrichment de publicaciones con match + `normalization_confidence` + penalización de `unknown` en el score |
| Demasiadas alertas (§47) | `notify_min_level` por defecto en `good`, tope diario, digest, un solo aviso por listing por usuario |

---

## 15. Trazabilidad PRD → plan

| PRD | Tema | Plan | Fase |
|---|---|---|---|
| §1–3 | Resumen, problema, hipótesis | Contexto; métricas 11 | — |
| §4 | Visión | Arquitectura 2 (`owned_vehicles` habilita el Garage) | — |
| §5 | Objetivo del MVP | Métricas 11 (`v_validation_criteria`) | F6 |
| §6 | No objetivos | Guardarraíles: sin contacto automático (6.6), sin tasación (6.2) | — |
| §7–9 | ICP y personas | Múltiples profiles (4.3); ingesta por targets apta para revendedor (5.1) | F1, F4 |
| §10 | Propuesta de valor | Score + templates (6.3, 7.2) | F2, F3 |
| §11 | Principios | Tope y niveles (7.1), recencia (5.1), explicabilidad (6), control (4.3), copy prudente (6.2), backend reutilizable (2) | Todas |
| §12 | Flujo principal y modos | `/app/searches/new` (9) + LLM (8.4) | F4, F5 |
| §13 | Search Profile | `search_profiles` (4) | F0, F4 |
| §14 | Ingesta | 5.2–5.3, `listings` | F1 |
| §15 | Nuevo / actualizado / re-publicado | 5.3–5.4 | F1 |
| §16 | Matching hard/soft | 6.1 | F2 |
| §17–18 | Opportunity Score | 6.3 | F2 |
| §19 | Price Intelligence | 6.2 | F2 |
| §20 | Niveles | 6.4 | F2 |
| §21 | Canales | 7.2 (Telegram = canal existente; WhatsApp fuera de alcance) | F3 |
| §22 | Tipos de alerta | 7.1–7.2 | F3 |
| §23 | Página de resultado | `/app/listings/[id]` (9) | F4 |
| §24 | Red flags | 6.5 | F2 (UI en F4) |
| §25 | Asistente de contacto | 6.6 (+ `polish_questions` 8) | F2, F5 |
| §26 | Estados | `user_listing_interactions.status` | F4 |
| §27 | Razones de descarte | `rejection_reason` enum | F4 |
| §28 | Dashboard | `/app` | F4 |
| §29 | Search Results | `/app/searches/[id]` | F4 |
| §30 | Watchlist | 5.6 + `/app/saved` | F1, F4 |
| §31 | Histórico de precios | `listing_snapshots` + gráfico | F1, F4 |
| §32 | Frecuencia | `notification_frequency` + digest (7) | F3 |
| §33–34 | Freemium / Search Pass | 12 | F6 |
| §35–38 | Métricas | 11 + tracking (7.3) | F3 (eventos), F6 (vistas) |
| §39 | OwnedVehicle | `owned_vehicles` | F0 (tabla), F4 (UI) |
| §40 | Modelo de datos | 4 | F0 |
| §41 | Arquitectura en capas | 2–3 | F0 |
| §42 | Frecuencia de crawling | 5.1 (`sources.crawl_interval_seconds`) | F1 |
| §43 | Usos de IA | 8 | F5 |
| §44 | Qué no depende de un LLM | 6 y guardarraíles 8.4 | F2, F5 |
| §45 | Backoffice e inspector | 10 (CLI en F2, web en F6) | F2, F6 |
| §46 | Observabilidad | `collector_runs`, `pipeline_errors`, 10 | F1, F6 |
| §47 | Riesgos | 14 | — |
| §48 | Priorización | Correspondencia en 13 | — |
| §49 | MVP recomendado | F0–F5 | — |
| §50 | Landing | `/` | F4 |
| §51 | Lanzamiento | Piloto después de F6 | — |
| §52 | Experimento de monetización | CTA Pro + lista de espera (9, 12) | F6 |
| §53 | Criterio de validación | `v_validation_criteria` | F6 |
| §54–55 | App mobile | Fuera de alcance; habilitada por 2, principio 4 (mismo Supabase) | — |
| §56 | Roadmap conceptual | 1.0 Find = F0–F4; 1.5 Understand = F2 + F5 | — |
| §57–58 | Apuesta y definición | Contexto | — |

---

## Apéndice A — Configuración

**Worker (`.env`), infraestructura:**

| Variable | Uso |
|---|---|
| `DATABASE_URL` | Conexión Postgres de Supabase (service role / pooler) |
| `TELEGRAM_TOKEN`, `TELEGRAM_ADMIN_CHAT_ID` | Bot y alertas operativas |
| `RESEND_API_KEY`, `EMAIL_FROM` | Canal email |
| `WEB_BASE_URL` | Para armar `/r/<id>` y los links al detalle |
| `LLM_PROVIDER` (`claude_cli`/`local`), `CLAUDE_CLI_PATH`, `CLAUDE_CLI_MODEL`, `LLM_TIMEOUT_SECONDS`, `LOCAL_LLM_BASE_URL`, `LOCAL_LLM_MODEL` | Capa LLM |
| `TICK_INTERVAL_SECONDS` | Tick del loop (se mantiene) |
| `GEOCODING_ENABLED`, `GEOCODING_USER_AGENT`, `FB_STORAGE_STATE`, `ML_STORAGE_STATE` | Se mantienen |

**Web (`.env.local`):**
- `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY` (o la publishable key);
- `SUPABASE_SERVICE_ROLE_KEY` (solo del lado del servidor);
- `NEXT_PUBLIC_TELEGRAM_BOT_USERNAME`.

**Reglas de negocio (`app_config`), con los valores iniciales:**

| Clave | Valor inicial | Reemplaza a |
|---|---|---|
| `score_weights` | `{price:35, match:25, km:15, trim:10, recency:10, completeness:5}` | — |
| `level_thresholds` | `{high:85, good:70, match:50}` | `DEFAULT_DISCOUNT_PCT` (queda deprecado) |
| `comparables` | `{min_n:5, year_tol:1, km_tol_pct:25, max_age_days:30}` | `OPPORTUNITY_MIN_COMPARABLES` |
| `recommended_max_age_days` | `15` | `RECOMMENDED_MAX_AGE_DAYS` |
| `price_drop_min_pct` | `3` | — |
| `alerts_max_per_user_day` | `10` | — |
| `digest_hour` | `"20:00"` (ART) | — |
| `watchlist_stale_days` | `30` | — |
| `collector_failure_alert_after` | `3` | — |
| `plan_limits` | ver sección 12 | — |
| — (`sources.crawl_interval_seconds`) | ver sección 5.1 | `ALERT_RESCRAPE_INTERVAL_SECONDS` |

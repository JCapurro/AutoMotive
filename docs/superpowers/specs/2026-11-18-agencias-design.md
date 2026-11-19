# Agencias: panel de stock y canal de venta (diseño técnico)

Fecha: 18/11/2026. Rama `claude/agencias` (worktree `C:/tmp/wt-agencias`, desde `origin/main` 578e71f).
Plan aprobado: [docs/PLAN_AGENCIAS_STOCK_Y_CANAL.md](../../PLAN_AGENCIAS_STOCK_Y_CANAL.md). Cruce manual que se automatiza:
[docs/INFORME_STOCK_TT_2026-11-18.md](../../INFORME_STOCK_TT_2026-11-18.md).

Alcance: **fase 1** (panel de stock) y **fase 2** (canal de venta). Fuera: fase 3 (cobro, «qué comprar»,
`sell_intent`), avisos a la agencia («bajó el mercado…»), precio sugerido, subida de fotos, página pública de
agencia, LLM para leer planillas/fotos/PDF.

Este documento fija contratos para tres agentes que trabajan en paralelo sin hablarse:

| Agente | Toca solo | Entrega |
|---|---|---|
| **BASE** | `supabase/migrations/20261228120000_dealer_program.sql`, `supabase/tests/dealers_test.sql` | esquema, RLS, funciones SQL, cambios a vistas/funciones existentes |
| **WORKER** | `worker/**` (lista exacta en §8) | sincronización ítem → aviso, compuertas de envío, etiqueta en alertas, aviso de consulta a la agencia |
| **WEB** | `web/**` (lista exacta en §8) | `/agencia`, ficha, tarjetas, botón de contacto, `/admin/agencias` |

Ninguno espera al otro: los nombres, firmas, columnas, códigos de error y formas de JSON de este documento son el
contrato. Si un agente encuentra que algo del contrato no se puede implementar tal cual, lo implementa lo más
cerca posible y lo deja escrito en su reporte (no cambia el contrato de los otros).

---

## 0. Decisiones (por defecto; Juan las puede cambiar)

1. **Piloto gratis.** No se toca `plan_limits`, `plan_feature()`, Mercado Pago ni precios. Ninguna función nueva
   lee el plan. Todos los planes (Free incluido) ven autos de agencia.
2. **El auto de agencia es una fila de `listings`.** Dos casos:
   - **Directo** (cargado a mano o por planilla): fuente nueva `directo`; lo escribe **solo el worker**, con el
     mismo `ingest` que cualquier aviso (catálogo, `price_usd` al blue del día, snapshots, bajas de precio,
     duplicados, clasificación de vendedor).
   - **Sincronizado** (la agencia ya publica en ML/FB/…): el aviso ya existe; solo se marca con
     `listings.dealer_id`. Nunca se crea una copia.
3. **La agencia trabaja sobre `dealer_stock_items`**, una fila por auto de su stock (el «ítem»). Cada ítem apunta a
   lo sumo a un aviso (`listing_id`, único). El panel y las métricas salen de los ítems.
4. **La web nunca escribe `listings`.** La agencia escribe ítems a través de funciones RPC (`security definer`,
   con chequeo de pertenencia). El worker convierte ítems en avisos.
5. **Sincronización por link = avisos que ya leemos.** La agencia pega su link y cómo figura su nombre; Juan aprueba
   en `/admin/agencias` cuál `seller_key` de cada fuente es suya. No se suman lecturas nuevas de perfiles (cero
   carga extra en los carriles de ML/FB). Límite conocido: solo entran los autos de modelos que alguien busca.
6. **Contacto:** formulario nuestro que crea un lead con consentimiento explícito; recién después, botón a
   WhatsApp con mensaje armado si la agencia cargó un WhatsApp.
7. **Alta abierta, canal con aprobación.** Con `enabled=true` cualquier usuario logueado puede dar de alta una
   agencia y usar el panel de precios. La demanda (conteos de búsquedas) y el envío a compradores exigen
   `dealers.approved_at` (lo pone Juan).
8. **La planilla se lee en la web** (TypeScript puro, sin dependencias nuevas: CSV a mano, XLSX con
   `node:zlib` + lectura del ZIP). La agencia ve la vista previa, corrige columnas y confirma. Las patentes
   (`dominio`, `patente`) se descartan al leer y nunca se guardan.
9. **Los autos `directo` quedan fuera de toda referencia de mercado**: `comparable_listings()` (y por lo tanto
   `comparables()` y `comparable_pool()`), `market_stats` y la referencia del panel. El precio que pide una agencia
   no es mercado, y así un auto no se compara consigo mismo.

## 1. Interruptores

`app_config` clave `dealer_program`, sembrada por la migración con
`{"enabled": false, "channel_enabled": false, "manual_confirm_days": 7, "demand_min_count": 3}` (`on conflict do nothing`).

Lectura saneada, igual en los tres lados (gemelos; los tres tienen test de los mismos casos):

| Clave | Tipo | Rango | Si falta o es inválida |
|---|---|---|---|
| `enabled` | boolean | — | `false` |
| `channel_enabled` | boolean | — | `false` |
| `manual_confirm_days` | entero | 1 a 60 | `7` |
| `demand_min_count` | entero | **3** a 50 | `3` (nunca menos de 3: así nunca se muestra 1 ni 2) |

Canal efectivo = `enabled and channel_enabled`. En adelante «canal prendido» significa eso.

- SQL: `public.dealer_program() returns jsonb` (§3.4).
- Worker: `intelligence/config.py: dealer_program(raw) -> dict` y `DEFAULT_DEALER_PROGRAM`.
- Web: `web/lib/dealer-program.ts: parseDealerProgram(raw: unknown): DealerProgram`.

Efectos:

| | `enabled=false` | `enabled=true`, canal apagado | canal prendido |
|---|---|---|---|
| `/agencia/*` | 404 | panel completo (sin envío) | panel + consultas |
| Avisos `directo` a compradores | nunca | nunca | si pasan la compuerta (§2) |
| Etiqueta «Agencia» | nunca | nunca | sí (directo y sincronizados) |
| «Quiero que me contacten» | nunca | nunca | sí |
| Worker, bucle de agencias | solo barrido (no-op sin filas) | sincroniza ítems, no hace matching de directo | todo |
| Reglas que protegen al comprador (§2: reservado/vendido; C4) | aplican a filas con `dealer_id` | ídem | ídem |

Con los defaults no hay ninguna fila de agencia, así que esas reglas no se disparan y nada cambia (C5).

## 2. Compuerta de envío (la regla central)

Un aviso «oculto» no se envía, no se muestra en resultados y no tiene filas en `matches`. Motivo, en este orden
(primer caso que aplica):

| # | Condición | Motivo |
|---|---|---|
| 1 | `dealer_id is null` y `source <> 'directo'` | `null` (aviso común, como hoy) |
| 2 | `source = 'directo'` y `dealer_id is null` | `no_dealer` |
| 3 | `source = 'directo'` y canal apagado | `channel_off` |
| 4 | `source = 'directo'` y la agencia sin `approved_at` o con `status <> 'active'` | `not_approved` |
| 5 | `source = 'directo'` y `dealer_status is distinct from 'available'` | `not_available` |
| 6 | `source = 'directo'` y (`dealer_confirmed_at is null` o `< now() - manual_confirm_days`) | `unconfirmed` |
| 7 | `source = 'directo'` | `null` (se envía) |
| 8 | sincronizado y `dealer_status in ('reserved','sold')` | `not_available` |
| 9 | sincronizado | `null` |

- SQL: `public.dealer_listing_hidden(p_source text, p_dealer_id bigint, p_dealer_status text, p_confirmed_at timestamptz) returns text`.
- Worker (gemelo puro): `intelligence/dealer.py: hidden_reason(listing, program, *, now) -> str | None`. Lee del
  `listing` las claves `source`, `dealer_id`, `dealer_status`, `dealer_confirmed_at`, `dealer_approved` (bool) y
  `dealer_active` (bool), que `rows_for_scoring` trae con un `LEFT JOIN dealers` (§4.3).
- El panel usa además `pending_sync` (ítem sin aviso todavía), que no es de esta función.

Cómo se garantiza «oculto ⇒ sin `matches`, sin `expired_search_matches` y sin pares de duplicado visibles» (todas
las superficies del comprador que leen `matches` — resultados, `search_results`, `recent_opportunities`,
`dashboard_summary`, `welcome_cars`, `landing_feed`, resumen diario, Telegram —, las que leen
`expired_search_matches` — `missed_car` (el auto del email 2.5), `missed_since_expiry` (el panel «lo que perdés») y
los conteos de `claim_lifecycle_emails` — y las banderas de duplicado de otros avisos quedan cubiertas):

1. **No se crean:** `pipeline/scoring.Scorer.evaluate` devuelve `None` si `hidden_reason(...)` no es `None` (crawl,
   rematch, rescore, color, near_zone **y `scheduler.count_after_expiry`**, que escribe `expired_search_matches`,
   pasan todos por ahí). El rescore nocturno ya borra el match que deja de pasar.
2. **Se borran al instante** cuando la agencia marca reservado/vendido/archivado: la RPC
   `dealer_set_item_status` llama a `dealer_hide_listing()` en la misma transacción, que borra los `matches` **y
   las filas de `expired_search_matches`** del aviso.
3. **Se barren** cada `DEALER_TICK_SECONDS` (120 s): `public.dealer_sweep()` borra los `matches` y las filas de
   `expired_search_matches`, y pasa a `skipped` las notificaciones `queued`/`digest` de todo aviso oculto (cubre el
   vencimiento de la confirmación, la agencia sin aprobar o pausada y el apagado del canal). Así los conteos de
   `claim_lifecycle_emails` (que no se tocan) tampoco cuentan un oculto, con a lo sumo 120 s de atraso. Si el aviso
   vuelve a ser visible, esa fila de conteo no se recupera (conservador: el email cuenta de menos, nunca de más).
4. **Defensa extra** en las lecturas directas: `match_cards` (vista), `preview_search`, `missed_car` y
   `missed_since_expiry` (las dos leen `expired_search_matches`), `recent_active` (worker), `top_matches` (resumen
   diario) y la unión de pares de duplicado `_DUPLICATES` (worker) filtran con la misma función, con la forma
   `(l.dealer_id is null and l.source <> 'directo') or public.dealer_listing_hidden(l.source, l.dealer_id, l.dealer_status, l.dealer_confirmed_at) is null`
   (el `or` corta antes de llamar a la función para los avisos comunes). En `missed_car`/`missed_since_expiry` el
   filtro va en la consulta misma, así un oculto no sale ni en la ventana entre dos barridos.
5. **Notificaciones:** `Notifier.on_matches` y `Notifier.on_listing_events` descartan el evento si
   `hidden_reason(row)` no es `None` (las filas ya están cargadas; sin consultas nuevas).
6. **Duplicados de riesgo (PAR-02):** un `directo` no entra nunca en los grupos de `db/repos/duplicates.py` (ni se
   le calculan hashes de fotos), así que no forma pares en `listing_duplicates`: la agencia suele reusar las fotos
   de sus avisos de portal y la regla `cross_source_photos` no excluye agencias, lo que pondría la URL del
   `directo` («Agencias») como bandera roja en avisos ajenos. El duplicado propio de la agencia lo resuelve §4.4
   paso 4.1/4.2. Para los sincronizados (avisos de portal comunes), los pares se siguen calculando como hoy, pero
   `rows_for_scoring` solo une un par cuyo otro aviso es común o visible (predicado del punto 4 sobre `o`): un
   sincronizado reservado o vendido deja de aparecer en las banderas de otros en el siguiente puntaje.

Cuando un aviso vuelve a pasar la compuerta (reconfirmado, vuelve a disponible, se prende el canal), el worker lo
vuelve a matchear (§4.4 paso 6). Las claves de deduplicación (`match:<listing_id>`) y `filter_unseen` impiden que
le llegue dos veces a la misma persona.

---

## 3. Base de datos (agente BASE)

Un solo archivo: `supabase/migrations/20261228120000_dealer_program.sql`. Comentario de cabecera obligatorio:

> Agrega FK a `listings` (`dealer_stock_items.listing_id`, `dealer_stock_items.duplicate_listing_id`,
> `dealer_leads.listing_id`): **parar el worker antes de aplicarla** y reiniciarlo después (agrega columnas a
> `listings`). Aplicar a mano según la memoria de migraciones de producción, con OK de Juan. Nada de esto se aplica
> en esta rama.

Convenciones: `set search_path = ''` en toda función, nombres calificados `public.`, `(select auth.uid())` en
políticas, `notify pgrst, 'reload schema'` al final. Errores con `raise exception '<código>' using errcode = 'P0001'`
(la web mapea el código, §6.6).

### 3.1 Fuente y columnas nuevas en `listings`

```sql
insert into public.sources (id, name, enabled, crawl_interval_seconds, priority, detail_interval_seconds)
values ('directo', 'Agencias', false, 86400, 900, 60) on conflict (id) do nothing;
```
`enabled=false`: no aparece en el formulario de búsqueda, no genera `crawl_targets`, enrich ni watchlist la
ignoran. Una búsqueda guardada sin `filters.sources` (todas) la acepta; una con un subconjunto de fuentes no.

```sql
alter table public.listings
  add column dealer_id bigint references public.dealers (id) on delete set null,
  add column dealer_status text check (dealer_status in ('available', 'reserved', 'sold')),
  add column dealer_confirmed_at timestamptz;
create index listings_dealer_id_idx on public.listings (dealer_id) where dealer_id is not null;
```
(Crear `dealers` antes de este `alter`.) Sin CHECK que ate `directo` a `dealer_id`: el worker inserta por `ingest`
y completa `dealer_id` enseguida; en el medio la compuerta lo oculta (`no_dealer`). La política de lectura de
`listings` no cambia.

### 3.2 Tablas

```sql
create table public.dealers (
  id             bigint generated always as identity primary key,
  name           text not null check (char_length(btrim(name)) between 2 and 80),
  contact_email  text check (contact_email is null or contact_email ~ '^[^@\s]+@[^@\s]+\.[^@\s]+$'),
  phone          text check (phone is null or phone ~ '^[0-9]{8,15}$'),
  whatsapp       text check (whatsapp is null or whatsapp ~ '^[0-9]{10,15}$'),   -- solo dígitos, con 54
  address_text   text check (address_text is null or char_length(address_text) <= 160),
  locality_label text not null check (char_length(locality_label) between 2 and 120),
  lat            double precision not null check (lat between -90 and 90),
  lon            double precision not null check (lon between -180 and 180),
  profile_links  jsonb not null default '[]' check (jsonb_typeof(profile_links) = 'array'),
  status         text not null default 'active' check (status in ('active', 'paused')),
  approved_at    timestamptz,
  approved_by    uuid references public.profiles (id) on delete set null,
  created_by     uuid references public.profiles (id) on delete set null,
  created_at     timestamptz not null default now(),
  updated_at     timestamptz not null default now()
);
-- profile_links: [{"kind": "mercadolibre"|"facebook"|"instagram"|"web", "url": "https://…"}], hasta 6.

create table public.dealer_members (
  dealer_id  bigint not null references public.dealers (id) on delete cascade,
  user_id    uuid not null references public.profiles (id) on delete cascade,
  role       text not null default 'owner' check (role in ('owner')),
  created_at timestamptz not null default now(),
  primary key (dealer_id, user_id),
  unique (user_id)                                   -- piloto: una agencia por usuario
);

create table public.dealer_sources (
  id               bigint generated always as identity primary key,
  dealer_id        bigint not null references public.dealers (id) on delete cascade,
  source           text not null references public.sources (id),
  profile_url      text check (profile_url is null or profile_url ~ '^https://'),
  seller_name_hint text check (seller_name_hint is null or char_length(seller_name_hint) <= 80),
  seller_key       text,                              -- lo elige Juan al aprobar
  status           text not null default 'pending' check (status in ('pending', 'approved', 'rejected')),
  approved_at      timestamptz,
  created_at       timestamptz not null default now(),
  check (status <> 'approved' or seller_key is not null)
);
create unique index dealer_sources_seller_once on public.dealer_sources (source, seller_key) where status = 'approved';

create table public.dealer_imports (
  id            bigint generated always as identity primary key,
  dealer_id     bigint not null references public.dealers (id) on delete cascade,
  filename      text check (char_length(filename) <= 200),
  kind          text not null check (kind in ('csv', 'xlsx')),
  rows_total    integer not null check (rows_total >= 0),
  rows_imported integer not null check (rows_imported >= 0),
  created_by    uuid references public.profiles (id) on delete set null,
  created_at    timestamptz not null default now()
);

create table public.dealer_stock_items (
  id                   bigint generated always as identity primary key,
  dealer_id            bigint not null references public.dealers (id) on delete cascade,
  origin               text not null check (origin in ('manual', 'sheet', 'sync')),
  import_id            bigint references public.dealer_imports (id) on delete set null,
  listing_id           bigint references public.listings (id) on delete set null,
  duplicate_listing_id bigint references public.listings (id) on delete set null,
  make text, model text, trim text,
  year                 integer check (year between 1950 and 2100),
  mileage_km           integer check (mileage_km between 0 and 2000000),
  price                numeric check (price > 0),
  currency             text check (currency in ('ARS', 'USD')),
  transmission         text check (transmission in ('manual', 'automatic')),
  fuel text, color text, body_type text,
  title                text check (title is null or char_length(title) <= 160),
  description          text check (description is null or char_length(description) <= 4000),
  images               jsonb not null default '[]' check (jsonb_typeof(images) = 'array'),  -- URLs https, hasta 10
  status               text not null default 'available'
                         check (status in ('available', 'reserved', 'sold', 'archived')),
  confirmed_at         timestamptz,
  in_stock_since       date,
  sync_state           text not null default 'pending'
                         check (sync_state in ('pending', 'synced', 'linked', 'review', 'error', 'gone')),
  sync_error           text,
  synced_at            timestamptz,
  matched_at           timestamptz,     -- última vez que el worker lo matcheó estando visible
  created_by           uuid references public.profiles (id) on delete set null,
  created_at           timestamptz not null default now(),
  updated_at           timestamptz not null default now(),
  check (origin = 'sync' or (make is not null and model is not null and year is not null
                             and price is not null and currency is not null))
);
create unique index dealer_stock_items_listing_once on public.dealer_stock_items (listing_id) where listing_id is not null;
create index dealer_stock_items_dealer_idx on public.dealer_stock_items (dealer_id, status);
create index dealer_stock_items_todo_idx on public.dealer_stock_items (id)
  where sync_state in ('pending', 'review') or matched_at is null;

create table public.dealer_item_private (
  item_id           bigint primary key references public.dealer_stock_items (id) on delete cascade,
  purchase_price    numeric check (purchase_price > 0),
  purchase_currency text check (purchase_currency in ('ARS', 'USD')),
  notes             text check (notes is null or char_length(notes) <= 1000),
  updated_at        timestamptz not null default now()
);

create table public.dealer_leads (
  id                 bigint generated always as identity primary key,
  dealer_id          bigint not null references public.dealers (id) on delete cascade,
  item_id            bigint references public.dealer_stock_items (id) on delete set null,
  listing_id         bigint references public.listings (id) on delete set null,
  buyer_user_id      uuid not null references public.profiles (id) on delete cascade,
  buyer_name         text not null check (char_length(btrim(buyer_name)) between 2 and 80),
  buyer_phone        text not null check (buyer_phone ~ '^[0-9]{8,15}$'),
  message            text check (message is null or char_length(message) <= 500),
  consent_text       text not null check (char_length(consent_text) between 20 and 300),
  consent_at         timestamptz not null default now(),
  notification_id    bigint references public.notifications (id) on delete set null,
  origin             text not null check (origin in ('ficha', 'email', 'telegram', 'web')),
  status             text not null default 'new'
                       check (status in ('new', 'contacted', 'reserved', 'sold', 'lost')),
  status_changed_at  timestamptz,
  dealer_notified_at timestamptz,
  created_at         timestamptz not null default now(),
  updated_at         timestamptz not null default now(),
  unique (buyer_user_id, listing_id)
);
create index dealer_leads_dealer_idx on public.dealer_leads (dealer_id, created_at desc);
create index dealer_leads_unnotified_idx on public.dealer_leads (id) where dealer_notified_at is null;
```
Triggers `set_updated_at` en `dealers`, `dealer_stock_items`, `dealer_item_private`, `dealer_leads`. Si el
comprador borra su cuenta, sus leads se van con él (cascade).

### 3.3 RLS y permisos

RLS habilitada en las siete tablas. `revoke all ... from public, anon, authenticated` en las siete y
`grant all ... to service_role`. Después, solo esto:

| Tabla | `authenticated` puede | Política |
|---|---|---|
| `dealers` | `select` | `public.is_dealer_member(id)` |
| `dealer_members` | `select` | `user_id = (select auth.uid())` |
| `dealer_sources` | `select` | `public.is_dealer_member(dealer_id)` |
| `dealer_imports` | `select` | `public.is_dealer_member(dealer_id)` |
| `dealer_stock_items` | `select` | `public.is_dealer_member(dealer_id)` |
| `dealer_item_private` | `select` | miembro de la agencia del ítem |
| `dealer_leads` | `select` de columnas `id, dealer_id, item_id, listing_id, buyer_name, buyer_phone, message, consent_at, origin, status, status_changed_at, created_at` (**no** `buyer_user_id`, `consent_text`, `notification_id`) | `buyer_user_id = (select auth.uid()) or public.is_dealer_member(dealer_id)` |

Ninguna escritura directa de clientes: todo pasa por las RPC de §3.5 (validan pertenencia, consentimiento y
valores). El worker y `/admin` usan service role.

### 3.4 Funciones de apoyo

Todas `stable`, `security definer`, `set search_path = ''`, salvo que se diga otra cosa.

| Firma | Devuelve | Grants |
|---|---|---|
| `dealer_program()` | jsonb saneado de §1 | anon, authenticated, service_role |
| `is_dealer_member(p_dealer_id bigint)` | boolean (`auth.uid()` es miembro) | authenticated, service_role |
| `dealer_listing_hidden(p_source text, p_dealer_id bigint, p_dealer_status text, p_confirmed_at timestamptz)` | text, motivo de §2 o null | anon, authenticated, service_role |
| `dealer_public_name(p_dealer_id bigint)` | text: `dealers.name` si canal prendido, aprobada y activa; si no, null | anon, authenticated, service_role |
| `dealer_market_ref(p_make text, p_model text, p_year int, p_price_usd numeric, p_exclude_listing bigint)` | jsonb (§3.6) | service_role |
| `dealer_demand(p_make text, p_model text, p_year int, p_price numeric, p_currency text, p_mileage_km int, p_lat float8, p_lon float8, p_exclude_users uuid[], p_source text)` | jsonb crudo (§3.7); `p_source` es la fuente del auto: una búsqueda con `filters.sources` que no la incluye no entra en `fits` | service_role |
| `dealer_blue_rate()` | numeric: `rate` del `fx_rates` `kind='blue'` más reciente (null si no hay) | service_role |

`dealer_program()` y `is_dealer_member()` son `security definer` porque `app_config` y `dealer_members` están
cerradas para el cliente y la vista `match_cards` corre como invocador.

### 3.5 RPC del panel, del comprador y del worker

Todas `volatile`, `security definer`. Las de la agencia exigen `dealer_program().enabled` (si no,
`dealer_program_off`), usuario logueado (`not_signed_in`) y ser miembro (`not_member`). Las de la agencia operan
sobre «mi agencia» (la de `dealer_members` del usuario).

| Firma | Qué hace | Errores |
|---|---|---|
| `my_dealer() returns jsonb` (stable) | `null` si no soy miembro; si no `{id, name, contact_email, phone, whatsapp, address_text, locality_label, lat, lon, profile_links, status, approved: bool, sources: [{id, source, profile_url, seller_name_hint, status}], counts: {available, reserved, sold, unconfirmed, review, leads_new}}`. No exige `enabled` (la web decide). | — |
| `create_dealer(p_name text, p_locality_label text, p_lat float8, p_lon float8, p_phone text default null, p_whatsapp text default null, p_contact_email text default null, p_address_text text default null, p_profile_links jsonb default '[]') returns bigint` | Crea la agencia y la membresía `owner`. | `dealer_program_off`, `not_signed_in`, `already_member`, `invalid_dealer:<campo>` |
| `update_my_dealer(` mismos parámetros `) returns void` | Actualiza los datos (no `status`). Si una agencia aprobada cambia nombre, lat o lon, `approved_at` vuelve a null y Juan la revisa de nuevo (impide sondear la zona de un comprador moviéndose, y que el comprador consienta a un nombre no revisado). | + `not_member` |
| `dealer_add_source(p_source text, p_profile_url text, p_seller_name_hint text) returns bigint` | Pide sincronizar una fuente (`pending`). `p_source` en (`mercadolibre`, `facebook`, `deruedas`, `kavak`, … cualquier `sources.id` con `enabled` y distinto de `directo`). | `invalid_source` |
| `dealer_upsert_item(p_item_id bigint, p_values jsonb) returns bigint` | `p_item_id null` crea un ítem `manual`; si no, edita uno mío no `sync`. Claves de `p_values`: `make, model, trim, year, mileage_km, price, currency, transmission, fuel, color, body_type, title, description, images, in_stock_since`. Pone `confirmed_at = now()`, `sync_state = 'pending'`, `matched_at = null`. | `invalid_item:<campo>`, `item_not_found` |
| `dealer_import_items(p_rows jsonb, p_filename text, p_kind text) returns jsonb` | Hasta 500 objetos con las mismas claves; crea `dealer_imports` e ítems `sheet` confirmados. Todo o nada. Devuelve `{import_id, imported}`. | `too_many_rows`, `invalid_item:<fila>:<campo>` |
| `dealer_set_item_status(p_item_id bigint, p_status text) returns void` | `available`/`reserved`/`sold`/`archived`. Copia a `listings.dealer_status` (`archived` → `sold` en el aviso; para `directo` el worker además lo da de baja). Si el aviso queda oculto: `dealer_hide_listing(listing_id)`. Si queda visible: `matched_at = null` (el worker lo vuelve a matchear). Un ítem `sync` admite `reserved`/`sold`/`available`. | `invalid_status`, `item_not_found` |
| `dealer_confirm_items(p_item_ids bigint[] default null) returns integer` | `confirmed_at = now()` en mis ítems `manual`/`sheet` disponibles (todos si `null`) y copia a `listings.dealer_confirmed_at`; los que estaban vencidos quedan con `matched_at = null`. Devuelve cuántos. | — |
| `dealer_resolve_duplicate(p_item_id bigint, p_mine boolean) returns void` | Ítem en `review`. `true`: crea un `dealer_sources` `pending` para `(source, seller_key)` del aviso duplicado y deja el ítem en `review` hasta que Juan apruebe; `false`: `duplicate_listing_id = null`, `sync_state = 'pending'` (se crea el directo). | `item_not_found` |
| `dealer_set_item_private(p_item_id bigint, p_purchase_price numeric, p_purchase_currency text, p_notes text) returns void` | Upsert en `dealer_item_private`. | `invalid_item:<campo>` |
| `dealer_stock_insights() returns table (…)` (stable) | §3.6. | `not_member` |
| `dealer_set_lead_status(p_lead_id bigint, p_status text) returns void` | Solo miembros de la agencia del lead. Pone `status_changed_at`. | `lead_not_found`, `invalid_status` |
| `request_dealer_contact(p_listing_id bigint, p_name text, p_phone text, p_message text, p_consent boolean, p_consent_text text, p_notification_id bigint default null) returns jsonb` | §3.8. | `dealer_program_off`, `not_signed_in`, `consent_required`, `contact_unavailable`, `invalid_contact:<campo>`, `rate_limited` |
| `listing_dealer_card(p_listing_id bigint) returns jsonb` (stable) | Para la ficha, §3.8. `null` si el aviso no es de agencia ni `directo`. | — |
| `dealer_badges(p_listing_ids bigint[]) returns table (listing_id bigint, dealer_name text, confirmed_at timestamptz)` (stable) | Solo filas con etiqueta (canal prendido, aprobada, activa, no oculto). Hasta 200 ids. | — |
| `dealer_hide_listing(p_listing_id bigint) returns void` (interna) | Borra `matches` y `expired_search_matches` del aviso, pasa a `skipped` (`error = 'dealer_hidden'`) sus notificaciones `queued`/`digest` y pone `matched_at = null` en su ítem. | — (sin grant a clientes) |
| `dealer_sweep() returns table (matches_deleted int, notifications_skipped int, expired_deleted int)` | `dealer_hide_listing` para todo aviso con `(dealer_id is not null or source = 'directo')` y motivo no nulo que todavía tenga `matches`, filas en `expired_search_matches` o notificaciones pendientes. | service_role |
| `admin_dealer_seller_candidates(p_source text, p_hint text) returns table (seller_key text, seller_name text, active int)` | Avisos activos de esa fuente con `seller_key ilike '%'||hint||'%'` o `seller_name ilike`, agrupados; hasta 30. | service_role |

Grants: las RPC del panel y del comprador a `authenticated` (y `service_role`); `revoke execute ... from public, anon`
en todas. `admin_*`, `dealer_sweep`, `dealer_market_ref`, `dealer_demand`, `dealer_blue_rate`, `dealer_hide_listing`:
solo `service_role`.

Validaciones de `p_values` (SQL, además de los CHECK): `year` entre 1950 y año actual + 1; `price > 0`; `currency`
en ARS/USD; `images` con URLs `https://` (hasta 10); `make`/`model` no vacíos. La web normaliza al catálogo antes de
llamar (§6.3); el worker vuelve a normalizar al crear el aviso.

### 3.6 `dealer_stock_insights()` y la referencia de mercado

Columnas, una fila por ítem de mi agencia con `status <> 'archived'`, ordenadas por `created_at`:

```
item_id bigint, listing_id bigint, origin text, status text, sync_state text,
make text, model text, trim text, year int, mileage_km int,         -- del aviso si existe, si no del ítem
price numeric, currency text, price_usd numeric,                    -- price_usd: USD tal cual; ARS / dealer_blue_rate()
confirmed_at timestamptz, confirm_due_at timestamptz,               -- confirm_due_at solo manual/sheet
hidden_reason text,                                                 -- §2, o 'pending_sync' sin aviso; null = se envía
market jsonb, days_in_stock int, model_days_to_sell jsonb, demand jsonb
```

`market` = `dealer_market_ref(make, model, year, price_usd, listing_id)`, **la metodología del informe**:

```sql
from public.listings o
where lower(o.make) = lower(p_make) and lower(o.model) = lower(p_model)
  and o.year between p_year - 1 and p_year + 1       -- año ±1
  and o.status = 'active'
  and o.last_seen_at >= now() - interval '30 days'   -- vistos en 30 días
  and o.price_usd > 0 and not o.price_partial         -- precio en USD congelado al blue del día de lectura
  and o.source <> 'directo'                           -- todas las fuentes salvo stock cargado por agencias
  and o.id is distinct from p_exclude_listing
  and not (o.attributes ? '_not_vehicle')
-- sin filtro de versión ni de km, como el informe
```
Devuelve `{"n": int, "median": num, "p25": num, "p75": num, "vs_market_pct": num|null, "enough": bool,
"year_tol": 1, "days": 30, "blue": num|null}`, con medianas y percentiles `percentile_cont` redondeados a 2
decimales, `vs_market_pct = round((p_price_usd / median - 1) * 100, 1)` (positivo = más caro que el mercado, como
el informe: «+17 %», «−66 %»), `enough = n >= app_config.comparables.min_n` (5 por defecto).

`days_in_stock` = días (hora de Argentina) desde `coalesce(in_stock_since, published_at del aviso, created_at del ítem)`.

`model_days_to_sell` = `{"median": int|null, "n": int}`: avisos `gone`, mismo modelo, año ±1, `source <> 'directo'`,
`last_seen_at` en los últimos 180 días; días entre `coalesce(published_at, first_seen_at)` y `last_seen_at`;
`median` null si `n < 5`.

`demand` (§3.7): si la agencia no está aprobada, `{"approved": false}`. Si no,
`{"approved": true, "window_days": 90, "min_count": <demand_min_count>, "levels": {"model": X, "fits": X, "zone": X, "active_zone": X}}`
donde cada `X` es:
- `0` si no hay ninguna búsqueda;
- el **número de búsquedas** si las **personas distintas** detrás son `>= demand_min_count`;
- el string `"few"` en otro caso (nunca 1 ni 2, y nunca un número cuando hay menos de 3 personas);
- `null` solo en `zone`/`active_zone` si la agencia no tiene ubicación (no pasa: es obligatoria).

El redondeo a «pocas» se hace **en SQL**, dentro de la función; los números crudos no salen nunca a un cliente.

### 3.7 `dealer_demand()` (crudo, solo service role)

Base: `search_profiles sp` con `sp.enabled or sp.created_at >= now() - interval '90 days'`, con modelo
(`nullif(btrim(filters->>'model'), '')` no nulo) igual a `lower(p_model)` y marca igual o vacía, excluyendo los
usuarios `p_exclude_users` (los miembros de la agencia) y los `profiles.role = 'admin'`. Niveles anidados:

| Nivel | Agrega a lo anterior |
|---|---|
| `model` | — |
| `fits` | año (`year_min`, `year_max`, `years` como `matching._year`); precio (`price_min`/`price_max`; moneda de `filters.currency`, si falta ARS cuando el monto es ≥ 1.000.000; auto pasado con `dealer_blue_rate()`); km (`km_min`/`km_max`; km desconocido pasa); vendedor (`filters.seller_types` no vacío y sin `'dealer'` queda afuera, C4) |
| `zone` | la ubicación de la agencia cae en alguna zona de la búsqueda (`origin_lat/lon` + `radius_km`, y `filters.extra_locations`), con `public.haversine_km`; una búsqueda sin zona acepta |
| `active_zone` | `sp.enabled` |

Devuelve `{"model": {"searches": n, "people": n}, "fits": {...}, "zone": {...}, "active_zone": {...}}`. Valores de
`filters` leídos con guardas de tipo (`jsonb_typeof = 'number'`), nunca un cast que pueda fallar.

### 3.8 Contacto del comprador

`request_dealer_contact`:
1. Canal prendido, si no `dealer_program_off`. `p_consent is true` y `p_consent_text` de 20 a 300 caracteres, si no
   `consent_required`.
2. El aviso tiene `dealer_id`, la agencia tiene etiqueta (`dealer_public_name` no nulo) y `dealer_listing_hidden`
   es null, si no `contact_unavailable`. El comprador no es miembro de esa agencia.
3. Nombre de 2 a 80; teléfono: se quitan los no dígitos y queda de 8 a 15 (`invalid_contact:name|phone|message`).
4. Si ya existe el lead `(buyer, listing)`, lo devuelve con `created: false` (no cuenta para el límite).
5. Máximo 5 leads nuevos por comprador en 24 h (`rate_limited`).
6. `origin`: el `channel` de `p_notification_id` si esa notificación es del comprador y del aviso (`email`,
   `telegram`, `web`); si no, `ficha`.
7. Inserta y registra `events (user_id = comprador, name = 'dealer_lead_created', props = {lead_id, dealer_id, listing_id, origin})`
   — sin nombre, teléfono ni mensaje.
8. Devuelve `{"lead_id", "created": bool, "dealer_name", "whatsapp": dígitos|null, "vehicle": "Ford Focus 2017", "created_at"}`.

`listing_dealer_card(p_listing_id)` devuelve:
```json
{"dealer_id": 1, "dealer_name": "TT Autos" | null, "badge": true, "is_directo": true,
 "hidden_reason": null, "confirmed_at": "…", "viewer_is_member": false,
 "can_request": true, "my_lead": {"id": 7, "created_at": "…", "status": "new"} | null,
 "whatsapp": "5491122334455" | null}
```
`dealer_name` solo con etiqueta; `whatsapp` solo si `my_lead` existe; `can_request` = etiqueta, no oculto, logueado,
no miembro y sin lead previo. Para un miembro, `hidden_reason` y `dealer_name` (aunque no haya etiqueta) sirven
para la vista previa.

### 3.9 Cambios a objetos existentes (copiar el cuerpo vigente y agregar solo lo indicado)

| Objeto (última definición) | Cambio |
|---|---|
| `comparable_listings` (`20261106120000_comparables_full_read.sql`) | `and o.source <> 'directo'` en el `where`. Cubre `comparables()` y `comparable_pool()`. Sin bump de `SCORING_VERSION` (sin filas `directo`, igual resultado). |
| vista `match_cards` (`20261214120000_listing_color.sql`) | Columnas nuevas **al final**: `dealer_id` (= `l.dealer_id` si `dealer_public_name` no es null, si no null), `dealer_name` (`case when l.dealer_id is not null then public.dealer_public_name(l.dealer_id) end`), `dealer_confirmed_at` (`l.dealer_confirmed_at` cuando hay `dealer_name`). `where` con el predicado de §2 (punto 4). Revisar que las funciones `returns setof public.match_cards` sigan compilando. |
| `preview_search` (`20261214120000_listing_color.sql`) | En los dos brazos de candidatos, el predicado de §2 (punto 4) y `and not (l.dealer_id is not null and <seller_types del filtro no vacío y sin 'dealer'>)`. |
| `landing_feed` (`20261219120000_landing_hero.sql`) | `and l.source <> 'directo'` (sin página pública de agencia; la home es anónima). |
| `welcome_cars` (`20261217120000_welcome_cars.sql`) | En el `jsonb_build_object`, `'dealer_name', case when l.dealer_id is not null then public.dealer_public_name(l.dealer_id) end` (el `jsonb_strip_nulls` lo saca si es null: sin cambio para avisos comunes). |
| `missed_car` (**`20261214120000_listing_color.sql:249-366`**, no la de `20261210120000_missed_car_fits_search.sql`, que no tiene el color) | Copiar ese cuerpo **completo**, incluida la regla estricta de color (`public.search_colors(sp.f) as colors` en `f`, l. 275, y `and (f.colors is null or c.color is null or c.color = any (f.colors))`, l. 355-356); sacarla cambiaría el auto del email 2.5 aun con el programa apagado (C5). Dos cambios: (a) en el `where` de `cand` (l. 308-309) agregar el predicado de §2 (punto 4): `and ((l.dealer_id is null and l.source <> 'directo') or public.dealer_listing_hidden(l.source, l.dealer_id, l.dealer_status, l.dealer_confirmed_at) is null)`; (b) en el `jsonb_build_object`, `'dealer_name'` igual que `welcome_cars`. |
| `missed_since_expiry` (`20261211120000_pass_7.sql:525-546`, única definición) | `create or replace` con el mismo cuerpo, `join public.listings l on l.id = m.listing_id` en el segundo `join` de `expired_search_matches` (l. 540) y el predicado de §2 (punto 4) en el `where`. El conteo de `ended` (l. 529-533) no cambia (fecha, no autos). Mantener `revoke ... from public, anon` y `grant ... to authenticated`. La llamada existente a `plan_limits_for` queda tal cual (no es un cambio de planes, C10). |

Rollback (en el comentario): volver a aplicar los cuerpos de esas migraciones, `drop` de las funciones y tablas
nuevas, `alter table listings drop column dealer_*`, `delete from sources where id = 'directo'` (solo sin avisos),
`delete from app_config where key = 'dealer_program'`.

---

## 4. Worker (agente WORKER)

### 4.1 `intelligence/config.py`
```python
DEFAULT_DEALER_PROGRAM = {"enabled": False, "channel_enabled": False, "manual_confirm_days": 7, "demand_min_count": 3}
def dealer_program(raw: Any) -> dict[str, Any]: ...   # §1; agrega "channel": enabled and channel_enabled
```

### 4.2 `intelligence/dealer.py` (nuevo, puro)
```python
DEALER_SOURCE = "directo"
HIDDEN_REASONS = ("no_dealer", "channel_off", "not_approved", "not_available", "unconfirmed")
def is_dealer_listing(listing: Mapping) -> bool            # dealer_id no nulo o source == "directo"
def hidden_reason(listing: Mapping, program: Mapping, *, now: datetime) -> str | None   # §2, gemelo exacto
def label(listing: Mapping, program: Mapping, *, now: datetime) -> dict | None
    # {"label": "Agencia", "name": dealer_name} si canal prendido, dealer_approved, dealer_active,
    # dealer_name y hidden_reason None; si no None.
def private_only(filters: Mapping) -> bool                 # seller_types válidos, no vacíos, sin "dealer"
```

### 4.3 Cambios en módulos existentes

| Archivo | Cambio |
|---|---|
| `intelligence/matching.py` | En `_seller`, **antes** de `strict_seller`: si `listing.get("dealer_id")` y `private_only(f)`, `Reason(FAIL, copy.REASON["seller_dealer_stock"].format(wanted=…))`. Cumple C4 para cualquier plan. Sin bump de `SCORING_VERSION` (no cambia ningún aviso sin `dealer_id`). Nada más cambia: mismo puntaje, sin bonus, sin excepción a cupo ni umbral. |
| `intelligence/copy.py` | `DEALER_LABEL = "Agencia"`; `REASON["seller_dealer_stock"] = "auto de agencia, se busca solo {wanted}"`. |
| `pipeline/scoring.py` | `Scorer` guarda `program = dealer_program(await db.get_config("dealer_program"))`; `evaluate` devuelve `None` si `hidden_reason(row, self.program, now=self.now)`. |
| `db/repos/listings.py` | `rows_for_scoring`: `LEFT JOIN dealers d ON d.id = l.dealer_id` con `d.name AS dealer_name, d.approved_at IS NOT NULL AS dealer_approved, coalesce(d.status = 'active', false) AS dealer_active`. `recent_active` (las dos ramas): predicado de §2 (punto 4). |
| `db/repos/notifications.py` | `top_matches`: predicado de §2 (punto 4). |
| `db/repos/listings.py` (`_DUPLICATES`, l. 330-343) | En el `JOIN listings o ON o.id = d.other_id AND o.status = 'active'` agregar `AND ((o.dealer_id IS NULL AND o.source <> 'directo') OR public.dealer_listing_hidden(o.source, o.dealer_id, o.dealer_status, o.dealer_confirmed_at) IS NULL)`: un par cuyo otro aviso está oculto no llega a `risk_duplicates` ni a `red_flags.duplicate_flags` (`intelligence/red_flags.py:175`). Sin filas de agencia, mismo resultado que hoy. |
| `db/repos/duplicates.py` | `'directo'` fuera de todo agrupamiento: `_GROUPS` y `group_rows` con `AND source <> 'directo'` (`l.source` en `group_rows`); `photo_hash_queue` suma siempre `'directo'` a `skip_sources` dentro de la función (`list({*skip_sources, "directo"})`), así no se gastan hashes en él. Los pares `directo` que existieran se borran solos en la siguiente corrida del grupo (el diff de `pipeline/risk_duplicates.py` los saca porque ya no salen de `detect`). `intelligence/duplicates.py` y `pipeline/risk_duplicates.py` no cambian. |
| `notifications/service.py` | `listing_payload`: si `label(...)` → `out["dealer"] = {"label": "Agencia", "name": …}` (el `Notifier` carga `program` una vez por lote). `on_matches` y `on_listing_events`: saltean filas con `hidden_reason`. |
| `notifications/templates.py` | Si `payload["listing"]["dealer"]`: línea «Agencia · {name}» en email, Telegram y cada ítem del resumen; en `_welcome_cars` y `_missed` si el auto trae `dealer_name`. Sin `dealer`, salida byte a byte igual (los snapshots existentes no cambian). |
| `pipeline/market_stats.py` | `_FETCH`: `AND l.source <> 'directo'`. |
| `config.py` | `DEALER_TICK_SECONDS = int(os.getenv("DEALER_TICK_SECONDS", "120"))`. |
| `main.py` | `_every("dealers", DEALER_TICK_SECONDS, lambda _stop: run_dealers(notifier, links), stop)`. |
| `tests/pgcase.py` | `_TRUNCATE` suma `dealers, dealer_members, dealer_sources, dealer_imports, dealer_stock_items, dealer_item_private, dealer_leads`. |

### 4.4 `pipeline/dealers.py` (nuevo) — el bucle

```python
@dataclass
class DealerTick:
    swept_matches: int = 0; skipped_notifications: int = 0; swept_expired: int = 0
    linked: int = 0; unlinked: int = 0; created: int = 0; updated: int = 0
    gone: int = 0; review: int = 0; matched: int = 0; lead_notices: int = 0

async def run_dealers(notifier: Notifier, links: Links, *, now: datetime | None = None) -> DealerTick
```
Pasos, cada uno con su `try` y `log_error("dealers", ...)`; nunca levanta:

1. **Barrido** (siempre): `repo.sweep()` → `SELECT * FROM public.dealer_sweep()` (`matches_deleted`, `notifications_skipped`, `expired_deleted`).
2. Si `not program["enabled"]`: termina.
3. **Fuentes aprobadas** (`sync_linked`): por cada `dealer_sources` `approved`, los avisos `active` de
   `(source, seller_key)` con `dealer_id is null or = agencia` → `dealer_id`, `dealer_status = coalesce(dealer_status, 'available')`,
   `dealer_confirmed_at = greatest(last_seen_at, last_full_seen_at)`; upsert de ítem `origin='sync'`,
   `sync_state='linked'`, `matched_at = now()` (ya los matchea el crawl). Un aviso con `dealer_id` de otra agencia:
   `log_error`, se saltea. Ítems `sync` cuyo aviso pasó a `gone` → `sync_state='gone'`, `status='archived'` (salvo
   `sold`). Avisos con `dealer_id` cuya fuente ya no está aprobada → `dealer_id/status/confirmed_at = null`, ítem
   `archived`. En cada tick se refresca `dealer_confirmed_at` de los sincronizados («se confirman con cada lectura», C3).
4. **Ítems manuales y de planilla** (`sync_manual`, hasta 200 por tick, `sync_state = 'pending'`, `status <> 'archived'`):
   1. Duplicado propio: un ítem `sync` de la misma agencia con misma marca/modelo/año, precio ±3 % (en USD) y km
      ±10 % (o km desconocido) → el ítem pasa a apuntar a ese aviso (`listing_id`, `sync_state='linked'`) y el ítem
      `sync` se borra (queda uno). Si tenía un `directo`, ese aviso → `mark_gone`.
   2. Duplicado ajeno: un aviso `active` de otra fuente, mismo modelo/año, km ±3 % (ambos conocidos) o precio ±2 %,
      a ≤ 30 km de la agencia, con vendedor agencia (`effective_seller == 'dealer'`) → `sync_state='review'`,
      `duplicate_listing_id`; no se crea el directo hasta `dealer_resolve_duplicate`.
   3. Si no: `collectors.base.Listing(source="directo", listing_id=str(item.id), titulo=title or "{make} {model} {trim} {year}",
      url=f"{WEB_BASE_URL}/app/listings/directo/{item.id}", precio, moneda, marca, modelo, version=trim, anio, km,
      ubicacion=dealer.locality_label, transmision, combustible, vendedor="dealer" (lo que `tx.seller_type` lea como
      dealer), vendedor_nombre=dealer.name, descripcion, imagenes, published_at=epoch de item.created_at)` →
      `pipeline.ingest.ingest([...], seen=True)`; después, en una transacción: `lat/lon` de la agencia,
      `dealer_id`, `dealer_status` (`available`/`reserved`; `sold` → `mark_gone`), `dealer_confirmed_at = item.confirmed_at`,
      `listing_id`, `sync_state='synced'`, `synced_at`. Error → `sync_state='error'`, `sync_error` corto (sin datos de personas).
   4. Ítems `archived`/`sold` con aviso `directo` activo → `mark_gone` (el evento `listing_gone` queda oculto por la compuerta).
5. **Toque diario**: `last_seen_at = now()` de avisos `directo` activos de ítems `available`/`reserved` con
   `last_seen_at < now() - 1 día` (que la retención no los borre).
6. **Matching** (solo con canal prendido): avisos de ítems con `matched_at is null` y `hidden_reason` nulo, más los
   creados o cambiados en el paso 4 (con sus `events`) → agrupados por `(source, make, model)`, `process_batch(notifier,
   {"id": None, "source": s, "make": mk, "model": md, "query": {}}, ids, first_run=False, events=evs)` (como
   `tools/simulate_alert.py`) → `matched_at = now()`. Mismo matching, puntaje, cupo diario y umbrales que cualquier
   aviso nuevo (C1).
7. **Aviso de consulta a la agencia** (solo con canal prendido): `notifications/dealer_leads.notify_new_leads(channel, links)`.

### 4.5 `db/repos/dealers.py` (nuevo)
Funciones async con SQL plano (service role): `sweep()`, `approved_sources()`, `link_source_listings(...)`,
`archive_gone_sync_items()`, `unlink_unapproved()`, `refresh_sync_confirmations()`, `pending_items(limit)`,
`dealer_rows(ids)`, `own_sync_duplicate(item)`, `foreign_duplicate(item, dealer)`, `attach_listing(item_id, listing_id, values)`,
`mark_item(item_id, **fields)`, `touch_directo()`, `to_match(limit)`, `set_matched(item_ids)`, `unnotified_leads(limit)`,
`mark_lead_notified(ids)`. Los nombres internos los ajusta WORKER; lo que importa es que ningún SQL de agencias
salga de este archivo, `pipeline/dealers.py` y los puntos de §4.3.

### 4.6 `notifications/dealer_leads.py` (nuevo)
`async def notify_new_leads(channel, links, *, limit=50) -> int`: por agencia, un email a `dealers.contact_email`
(o al email del dueño) con `channel.send_message(...)`: asunto «Tenés {n} consulta(s) nueva(s) en Ese Auto», cuerpo
«{n} persona(s) pidieron que las contactes por tu {vehículo}. Mirá los datos en tu panel.» y botón a
`{WEB_BASE_URL}/agencia/consultas`. **Sin nombre, teléfono ni mensaje del comprador** en el email ni en los logs
(se loguea solo `lead_id` y `dealer_id`). Marca `dealer_notified_at`.

---

## 5. Planilla

Lectura en `web/lib/dealer-sheet.ts` (puro, testeable):

```ts
export type SheetKind = "csv" | "xlsx";
export type SheetTable = { headers: string[]; rows: string[][] };
export function parseCsv(text: string): SheetTable;              // separador ; , o tab detectado; comillas; BOM
export function parseXlsx(bytes: Uint8Array): SheetTable;        // primera hoja; sharedStrings; fechas seriales a año
export type ColumnMap = Partial<Record<SheetField, number>>;     // índice de columna
export type SheetField = "make" | "model" | "trim" | "year" | "mileage_km" | "price" | "currency"
  | "transmission" | "fuel" | "color" | "in_stock_since" | "title" | "description";
export function guessColumns(headers: string[], rows: string[][]): ColumnMap;
export type SheetRow = { line: number; values: ItemValues; issues: SheetIssue[] };
export type SheetIssue = "no_make" | "no_model" | "not_in_catalog" | "no_year" | "no_price"
  | "price_far_from_market" | "price_looks_like_cost" | "duplicate_in_sheet";
export function toRows(table: SheetTable, map: ColumnMap, catalog: Catalog): SheetRow[];
export const PLATE_HEADERS: RegExp;   // dominio|patente|placa: esas columnas se descartan siempre
```
- Límites: 1 MB, 500 filas. Encabezados en español con o sin tildes («Marca», «Modelo», «Versión», «Año», «Km»,
  «Precio», «Venta», «Moneda», «Color», «Ingreso»…). Precio: `$ 12.500.000`, `12,5 M`, `USD 14.000`, `u$s`.
  Moneda: explícita, o ARS si ≥ 1.000.000, si no USD (la regla de `matching.filter_currency`).
- Una columna de precio vacía (el caso «VENTA» del informe) no se adivina: `guessColumns` toma la primera columna
  numérica de montos y la vista previa pide confirmar «¿Esta columna es el precio de venta?».
- Vehículos que no son autos (camiones) o modelos fuera del catálogo → `not_in_catalog`: la fila se puede corregir
  con los selectores del catálogo o sacar.
- La vista previa no escribe nada. «Cargar N autos» llama a `dealer_import_items` con las filas aceptadas.

`price_far_from_market`/`price_looks_like_cost` se calculan después de cargar, con los insights (no en la vista
previa): el panel muestra «Revisá este precio» cuando `vs_market_pct <= -20` o `>= 50`.

---

## 6. Web (agente WEB)

### 6.1 Rutas

| Ruta | Qué muestra |
|---|---|
| `/agencia` (`layout.tsx`) | Exige sesión (proxy) y `dealer_program.enabled` (si no `notFound()`). Navegación: Stock · Cargar · Consultas · Datos. |
| `/agencia` (`page.tsx`) | Sin agencia: alta. Con agencia: resumen (`my_dealer().counts`), aviso «Falta que aprobemos tu agencia» si no está aprobada, «Confirmá tu stock» si hay vencidos. |
| `/agencia/stock` | Tabla de `dealer_stock_insights()`: auto, precio, precio vs mercado, comparables, demanda, días, estado (select), envío (motivo de §2 en palabras). Botón «Confirmar stock». Filtros: disponibles / reservados / vendidos. |
| `/agencia/stock/nuevo` | Alta manual (marca, modelo, versión del catálogo; año, km, precio, moneda, caja, combustible, color, fecha de ingreso, descripción, fotos por URL). |
| `/agencia/stock/[itemId]` | Editar; detalle de mercado (n, p25, mediana, p75) y demanda por nivel; «Lo que pagaste (solo lo ves vos)» y notas (`dealer_set_item_private`); «¿Es este aviso tuyo?» si `sync_state='review'`. |
| `/agencia/stock/planilla` | Subir CSV/XLSX → vista previa con problemas por fila y selector de columnas → confirmar. |
| `/agencia/consultas` | Bandeja de `dealer_leads` (RLS): auto, nombre, teléfono (link `tel:` y WhatsApp), mensaje, fecha, origen, estado (select). Con canal apagado: «El canal de venta todavía no está activo». |
| `/agencia/datos` | Datos de la agencia y fuentes para sincronizar (link + cómo figura el nombre) con su estado. |
| `/app/listings/directo/[itemId]` (`route.ts`) | Busca `listings` `source='directo'`, `external_id=itemId` y redirige a `/app/listings/<id>`; 404 si no existe. |
| `/admin/agencias` | Agencias (alta, aprobada, estado, ítems por estado, consultas por estado — solo conteos), aprobar/pausar, fuentes pendientes con `admin_dealer_seller_candidates` y aprobar/rechazar eligiendo el `seller_key`. |

### 6.2 Server actions
- `web/app/agencia/actions.ts`: `createDealer`, `updateDealer`, `addDealerSource`, `saveItem`, `previewSheet`
  (FormData → `SheetRow[]`, sin escribir), `importSheet`, `setItemStatus`, `confirmStock`, `resolveDuplicate`,
  `saveItemPrivate`, `setLeadStatus`. Todas con `createClient()` (sesión del usuario), validación zod y
  `revalidatePath`. Ninguna usa service role.
- `web/app/app/listings/dealer-actions.ts`: `requestDealerContact(listingId, form)` → RPC; devuelve el JSON de §3.8.
- `web/app/admin/agencias/actions.ts`: `approveDealer`, `pauseDealer`, `approveSource`, `rejectSource` (admin
  client, chequeo de admin como el resto de `/admin`).

### 6.3 Librerías (puras, con vitest)
- `lib/dealer-program.ts`: `DealerProgram`, `parseDealerProgram`, `channelOn(p)`.
- `lib/dealer-sheet.ts`: §5.
- `lib/dealer-insights.ts`: `priceVsMarketText(market)`, `demandTexts(demand)`, `hiddenReasonText(reason, days)`,
  `daysInStockText(n, modelDays)`, `priceCheck(market)`. Textos:
  - `«12 % arriba de autos parecidos · 23 comparables»`, `«En precio · 23 comparables»` (±10 %),
    `«8 % abajo de autos parecidos…»`, `«Pocos comparables (3)»` si `!enough`, `«Sin comparables»`.
  - Demanda: `«42 búsquedas del modelo · 17 entran en año y precio · 8 en tu zona · 2 activas en tu zona»`;
    `"few"` → «pocas»; `0` → «ninguna»; `approved:false` → «La demanda se ve cuando aprobemos tu agencia».
  - Motivos: `channel_off` «Todavía no se envía a compradores»; `not_approved` «Falta que aprobemos tu agencia»;
    `not_available` «Reservado o vendido: no se envía»; `unconfirmed` «Sin confirmar hace más de {d} días: confirmalo
    para que vuelva a enviarse»; `pending_sync` «Lo estamos cargando»; `null` «Se envía a quien lo busca».
- `lib/dealer-contact.ts`: `consentText(dealerName)` =
  «Acepto que Ese Auto le pase mi nombre, mi teléfono y mi mensaje a {agencia} para que me contacte por este auto.»;
  `normalizePhone`, `whatsappUrl(digits, text)`, `whatsappText(vehicle, name)` =
  «Hola, vi tu {vehículo} en Ese Auto y te pedí que me contactes. Soy {nombre}.»; `leadErrorText(code)`.
- `lib/dealer-server.ts` (`server-only`): `myDealer()`, `stockInsights()`, `dealerLeads()`, `dealerCard(listingId)`,
  `dealerBadges(ids)`.

### 6.4 Comprador
- `components/app/dealer-badge.tsx`: chip «Agencia» (con `title` = nombre). Se muestra solo si hay `dealer_name`.
- `components/app/listing-card.tsx`: prop opcional `dealerName`; los que pasan `MatchCard` la toman de
  `match_cards.dealer_name`; `/app/saved` usa `dealer_badges`.
- Ficha `app/app/listings/[id]/page.tsx`: si el aviso tiene `dealer_id` o es `directo`, llama a
  `listing_dealer_card` (si no, ninguna llamada nueva). `directo` oculto y visitante no miembro → `notFound()`.
  Miembro → banner «Así lo ven los compradores. {motivo}». Con etiqueta: chip «Agencia · {nombre}», «Stock
  confirmado hace {n} días» (directo), y `components/app/dealer-contact.tsx`. Para `directo` no se muestra «Ver
  publicación» (no hay otra página).
- `app/app/listings/[id]/out/route.ts`: si `source = 'directo'`, redirige a la ficha.
- **«Quiero que me contacten»** (`dealer-contact.tsx`, cliente): botón → formulario con Nombre, Teléfono (precargado
  de `profiles.phone`), Mensaje opcional (precargado «Hola, me interesa el {vehículo}. ¿Sigue disponible?»), casilla
  **sin marcar** con `consentText`, botón «Pedir contacto» deshabilitado hasta marcarla. Éxito: «Listo. {agencia} ya
  tiene tu pedido.» y, si hay WhatsApp, «Escribile por WhatsApp». Ya pedido: «Ya le pediste a {agencia} que te
  contacte el {fecha}.» + WhatsApp. `?n=<id>` de la URL (lo pone `/r/…`) va como `p_notification_id`.
- Analítica: `track(..., "dealer_contact_requested", {listing_id, dealer_id, origin})` y el mismo evento a GA sin
  parámetros personales. Nunca nombre, teléfono, mensaje ni email en eventos, logs o errores.
- `components/app/app-nav.tsx`: link «Mi agencia» solo con `enabled` y `my_dealer()` no nulo.
- `app/privacidad/page.tsx`: párrafo propuesto «Si tocás "Quiero que me contacten", le pasamos tu nombre, tu
  teléfono y tu mensaje a esa agencia, y a nadie más.» — **Juan lo aprueba antes de prender el canal** (dejarlo
  dicho en el reporte).

### 6.5 Config y admin
- `lib/config.ts`: `WebConfig.dealerProgram: DealerProgram` (con `parseDealerProgram`).
- `lib/admin-config.ts`: validación de la clave `dealer_program` (mismos rangos de §1) y etiquetas de los campos.
- `components/admin/admin-nav.tsx`: «Agencias» → `/admin/agencias` (y su test).
- `proxy.ts`: `/agencia` y `/agencia/**` exigen sesión como `/app`.
- `types/database.ts`: tablas, columnas nuevas de `listings` y `match_cards`, y las funciones de §3.4–3.5 a mano
  (no hay `gen:types` sin el stack local).

### 6.6 Errores de RPC → texto
`dealer_program_off` «Esto todavía no está disponible.» · `not_member` «No tenés acceso a esta agencia.» ·
`already_member` «Ya tenés una agencia.» · `invalid_dealer:*`/`invalid_item:*` «Revisá {campo}.» ·
`too_many_rows` «La planilla tiene más de 500 autos.» · `consent_required` «Marcá la casilla para que le pasemos
tus datos.» · `contact_unavailable` «Este auto ya no está disponible.» · `invalid_contact:phone` «Revisá el
teléfono.» · `rate_limited` «Ya pediste muchos contactos hoy. Probá mañana.» · cualquier otro «No pudimos guardar.
Probá de nuevo.»

---

## 7. Tests y cómo correrlos

### 7.1 BASE — `supabase/tests/dealers_test.sql` (pgTAP, todo en una transacción con `rollback`)
1. Defaults exactos de `app_config.dealer_program`; `dealer_program()` sanea (`demand_min_count` 1 → 3, 2 → 3, 51 → 3; tipos malos → defaults).
2. `create_dealer` con `enabled=false` → `dealer_program_off`; con `true` crea agencia y membresía; segunda vez `already_member`.
3. RLS: B no ve filas de A en las siete tablas; B no puede `dealer_upsert_item`/`dealer_set_item_status`/`dealer_set_lead_status` sobre A; `authenticated` sin `insert/update/delete` en las siete; `has_column_privilege('authenticated','public.dealer_leads','buyer_user_id','select')` falso.
4. Comprador: sin consentimiento → `consent_required`; con canal apagado → `dealer_program_off`; aviso oculto → `contact_unavailable`; OK → fila, `created:true`; repetido → `created:false`; 6.º en 24 h → `rate_limited`; el comprador ve solo su lead; el evento `dealer_lead_created` no tiene `buyer_name`/`buyer_phone`/`message` en `props`.
5. `dealer_listing_hidden`: los 9 casos de §2 (incluye 8 días sin confirmar con `manual_confirm_days=7`).
6. `match_cards`: oculto no aparece; visible trae `dealer_name`; con canal apagado `dealer_name` null; una fila común sale igual antes y después.
7. `comparable_listings` y `comparables()` ignoran `directo`; `landing_feed` no trae `directo`.
8. `preview_search`: no cuenta `directo` oculto; con `seller_types=['private']` no cuenta un aviso con `dealer_id`.
9. `dealer_sweep` borra `matches` y filas de `expired_search_matches`, y pasa a `skipped` notificaciones
   `queued`/`digest`, solo de avisos ocultos (un aviso común y un `directo` visible con filas en las dos tablas quedan
   intactos); devuelve los tres conteos.
10. `dealer_set_item_status('sold')` (y `'reserved'`) copia a `listings` y borra sus `matches` y sus
    `expired_search_matches` en el acto; `available` deja `matched_at` null.
11. `dealer_market_ref`: fixture con el mismo modelo en años −1/0/+1 (entran), +2 (no), visto hace 31 días (no), `gone` (no), `price_partial` (no), `directo` (no), otra fuente (entra) → `n`, `median`, `p25`, `p75` exactos y signo de `vs_market_pct` (caro positivo).
12. `dealer_demand` y `dealer_stock_insights`: niveles anidados; 2 personas con 4 búsquedas → `"few"`; 3 personas → número de búsquedas; 0 → 0; agencia sin aprobar → `{"approved": false}`; búsqueda `private` fuera de `fits`; búsqueda sin zona dentro de `zone`; miembros y admins excluidos; `not_member` para otro usuario.
13. `welcome_cars`/`missed_car`: sin `dealer_name` para avisos comunes; con él para uno con etiqueta.
14. `missed_car` conserva la regla estricta de color después de la migración: búsqueda con `filters.colors =
    ['rojo']` y en `expired_search_matches` un aviso común `color = 'azul'` con mejor `diff_pct` y otro `rojo` →
    devuelve el `rojo`; el `azul` con un candidato `rojo` de foto (`attributes._color.candidates`, prob ≥ 30) tampoco
    sale (estricto: solo el color propio); sin `colors`, sale el de mejor `diff_pct`. Los mismos casos que ya cubre
    `listing_color_test.sql`, que además se vuelve a correr entero sobre la base migrada.
15. `missed_car` y `missed_since_expiry` con un aviso oculto que **sigue** en `expired_search_matches` (contado
    cuando era visible, antes de cualquier barrido): un `directo` reservado, uno sin confirmar hace 8 días, uno de
    agencia sin aprobar, uno con canal apagado y un sincronizado vendido → `missed_car` no lo devuelve (devuelve el
    siguiente común, o null si no hay) y `missed_since_expiry` no lo cuenta en `found` ni en `below`; el mismo
    `directo` visible sí sale. Para `missed_since_expiry`, simular la sesión con `set local request.jwt.claims` del
    dueño de la búsqueda y un plan vencido, como en los tests existentes de pase.

Cómo correr (sin tocar la base local de la otra sesión ni producción):
```powershell
cd C:/tmp/wt-agencias/worker
python -m tools.test_db                       # clona automotive_test desde la base local (sin esta migración)
docker exec supabase_db_automotive psql -U postgres -d postgres -c "create database automotive_agencias_test template automotive_test owner postgres"
docker exec -i supabase_db_automotive psql -U postgres -d automotive_agencias_test -v ON_ERROR_STOP=1 -c "create extension if not exists pgtap with schema extensions" -c "insert into public.admin_metric_observation(singleton) values (true) on conflict do nothing"
Get-Content ../supabase/migrations/20261228120000_dealer_program.sql -Raw | docker exec -i supabase_db_automotive psql -U postgres -d automotive_agencias_test -v ON_ERROR_STOP=1 -1
Get-Content ../supabase/tests/dealers_test.sql -Raw | docker exec -i supabase_db_automotive psql -U postgres -d automotive_agencias_test -v ON_ERROR_STOP=1
```
Además, correr los pgTAP existentes que tocan lo cambiado (`rls_test.sql`, `pro01_seller_filter_test.sql`,
`par02_duplicates_test.sql`, **`listing_color_test.sql`** (cubre `missed_car` con color, `match_cards` y
`preview_search`) y los que usen `comparables`, `welcome_cars`, `landing_feed`) sobre la misma base. Si el stack local no está levantado: no arrancarlo a la fuerza ni tocar
Docker Desktop; escribir los tests igual y decir que no se corrieron.

### 7.2 WORKER (pytest)
- `tests/test_dealer_program.py`: `dealer_program()` (bordes de §1); `hidden_reason` (9 casos); `label`; `private_only`.
- `tests/test_dealer_matching.py`: C4 (Free y Pro con `['private']` → falla con `dealer_id`; sin `dealer_id` igual que
  hoy; `['dealer']` y `[]` pasan); C1: el mismo aviso con y sin `dealer_id` (compuerta abierta) da el mismo
  `score`, `level` y `score_breakdown`; `Scorer.evaluate` devuelve `None` con cada motivo.
- `tests/test_dealer_notifications.py`: `listing_payload` con/sin `dealer`; email y Telegram con «Agencia · X»;
  sin `dealer`, salida igual (snapshots existentes intactos); `on_listing_events` saltea ocultos;
  `notify_new_leads` no incluye nombre ni teléfono del comprador en asunto, cuerpo ni logs (`caplog`).
- `tests/test_dealers_postgres.py` (`pgcase`, requiere la base de §7.1 en `TEST_DATABASE_URL`): ítem manual → aviso
  `directo` con `price_usd = price / TEST_FX_RATE`, `dealer_*`, coordenadas de la agencia y `external_id`;
  duplicado propio enlaza sin crear copia (C8); duplicado ajeno → `review`; fuente aprobada enlaza y confirma con
  `last_seen_at`; reservado → sin `matches`; canal apagado → `run_dealers` no crea `matches` ni notificaciones;
  canal prendido → `process_batch` crea el match y la notificación para la búsqueda que lo acepta y nada para la
  `['private']`; gemelo: `hidden_reason` (Python) == `dealer_listing_hidden` (SQL) en la matriz; `market_stats` y
  `recent_active` ignoran lo oculto/`directo`; con `enabled=false` y sin filas, `run_dealers` no escribe nada;
  `count_after_expiry` no escribe en `expired_search_matches` un aviso oculto.
  **Duplicados de riesgo:** un `directo` visible (canal prendido, aprobado, confirmado) y un aviso común de ML del
  mismo modelo con el mismo hash de foto en `attributes._photo_hashes` (datos que coinciden, el caso
  `cross_source_photos`) → `risk_duplicates.detect_for([ambos])` no crea ninguna fila en `listing_duplicates` con el
  `directo`, `rows_for_scoring` del aviso de ML trae `risk_duplicates` vacío y su `red_flags` no tiene
  `cross_source_duplicate`; lo mismo con canal apagado y `enabled=true`; `photo_hash_queue` nunca devuelve el
  `directo`. Control: dos avisos comunes de ML y Kavak con la misma foto siguen formando el par como hoy. Y un
  sincronizado (ML con `dealer_id`) con par visible a un aviso de Kavak: con `dealer_status='sold'` el par deja de
  salir en `rows_for_scoring` del de Kavak; con `available` sale.
  Además, correr enteros `tests/test_risk_duplicates_postgres.py`, `tests/test_duplicates.py`,
  `tests/test_photo_hash.py` y `tests/test_ingest_postgres.py` (cubre `count_after_expiry`).
- Correr: `cd C:/tmp/wt-agencias/worker; python -m pytest -q` (sin base, los de Postgres se saltean) y con
  `$env:TEST_DATABASE_URL="postgresql://postgres:postgres@127.0.0.1:54322/automotive_agencias_test"` para los de DB.
  Los suites existentes deben seguir pasando.

### 7.3 WEB (vitest, tsc, eslint)
- `lib/dealer-program.test.ts`, `lib/dealer-sheet.test.ts` (CSV `;`/`,`, comillas, BOM, XLSX mínimo armado en el
  test con `node:zlib`, columnas de patente descartadas, precio «$ 12.500.000» y «12,5 M», columna de precio sin
  título, 501 filas), `lib/dealer-insights.test.ts` (textos y «pocas»; nunca imprime 1 o 2 aunque venga un número),
  `lib/dealer-contact.test.ts` (consentimiento, teléfono, URL de WhatsApp codificada).
- Actualizar `lib/admin-nav.test.ts`, `lib/admin-config.test.ts` y los tests de proxy si existen.
- Correr desde `C:/tmp/wt-agencias/web`: `npx vitest run`, `npx tsc --noEmit`, `npx eslint <archivos tocados>`.
  `next dev` solo con `--webpack` y **nunca** con `web/.env.local` (apunta a producción): no copiarlo ni leerlo.

---

## 8. Reparto exacto de archivos

**BASE:** `supabase/migrations/20261228120000_dealer_program.sql`, `supabase/tests/dealers_test.sql`.

**WORKER** — nuevos: `worker/intelligence/dealer.py`, `worker/db/repos/dealers.py`, `worker/pipeline/dealers.py`,
`worker/notifications/dealer_leads.py`, `worker/tests/test_dealer_program.py`, `worker/tests/test_dealer_matching.py`,
`worker/tests/test_dealer_notifications.py`, `worker/tests/test_dealers_postgres.py`. Modificados:
`worker/intelligence/config.py`, `worker/intelligence/matching.py`, `worker/intelligence/copy.py`,
`worker/pipeline/scoring.py`, `worker/pipeline/market_stats.py`, `worker/db/repos/listings.py` (incluye
`_DUPLICATES`), `worker/db/repos/duplicates.py`, `worker/db/repos/notifications.py`, `worker/notifications/service.py`, `worker/notifications/templates.py`,
`worker/config.py`, `worker/main.py`, `worker/tests/pgcase.py`.

**WEB** — nuevos: `web/lib/dealer-program.ts`, `web/lib/dealer-sheet.ts`, `web/lib/dealer-insights.ts`,
`web/lib/dealer-contact.ts`, `web/lib/dealer-server.ts` y sus `*.test.ts`; `web/app/agencia/layout.tsx`,
`web/app/agencia/page.tsx`, `web/app/agencia/actions.ts`, `web/app/agencia/stock/page.tsx`,
`web/app/agencia/stock/nuevo/page.tsx`, `web/app/agencia/stock/[itemId]/page.tsx`,
`web/app/agencia/stock/planilla/page.tsx`, `web/app/agencia/consultas/page.tsx`, `web/app/agencia/datos/page.tsx`,
`web/app/app/listings/directo/[itemId]/route.ts`, `web/app/app/listings/dealer-actions.ts`,
`web/app/admin/agencias/page.tsx`, `web/app/admin/agencias/actions.ts`, `web/components/agencia/*.tsx`
(`dealer-nav`, `dealer-signup-form`, `dealer-profile-form`, `stock-table`, `stock-item-form`, `sheet-import`,
`lead-inbox`), `web/components/app/dealer-badge.tsx`, `web/components/app/dealer-contact.tsx`. Modificados:
`web/proxy.ts`, `web/types/database.ts`, `web/lib/config.ts`, `web/lib/admin-config.ts` (+ test),
`web/components/admin/admin-nav.tsx` (+ `web/lib/admin-nav.test.ts`), `web/components/app/listing-card.tsx`,
`web/components/app/app-nav.tsx`, `web/components/app/expired-missed.tsx` (etiqueta del auto perdido),
`web/app/app/listings/[id]/page.tsx`, `web/app/app/listings/[id]/out/route.ts`, `web/app/app/saved/page.tsx`,
`web/app/privacidad/page.tsx`.

Nadie toca `docs/` (salvo el reporte que pida el orquestador), `ops/`, `graphify-out/` ni el checkout principal.
Nadie hace commit, push, deploy ni aplica migraciones fuera de la base de test clonada.

---

## 9. Cómo se cumple cada criterio

| | Cómo | Dónde (evidencia que tienen que dejar los agentes) |
|---|---|---|
| **C1** Neutralidad | El auto es una fila de `listings`; entra por `process_batch` como cualquier aviso nuevo; `Scorer.evaluate` solo **excluye** (compuerta), nunca suma; el stock de una agencia no cambia las banderas rojas ni el puntaje de avisos ajenos (un `directo` no forma pares de duplicado, §2 punto 6); `scoring.py` no se toca; cupo y umbrales del motor de notificaciones sin cambios. Etiqueta: `match_cards.dealer_name` → tarjetas; `listing_dealer_card` → ficha; `payload.listing.dealer` → email/Telegram/resumen; `welcome_cars`/`missed_car`. | `pipeline/scoring.py` (compuerta), `test_dealer_matching.py` (mismo puntaje con y sin `dealer_id`), `dealer-badge.tsx`, `templates.py`, pgTAP 6/13. |
| **C2** Privacidad | Leads solo por `request_dealer_contact` con `p_consent=true` y texto guardado; la agencia no ve `buyer_user_id`; demanda redondeada **en SQL** a `"few"` bajo `demand_min_count` (≥ 3, por personas); RLS por pertenencia en las 7 tablas; escrituras solo por RPC; worker con service role; eventos y emails sin datos del comprador. | Migración §3.3/§3.6/§3.8; pgTAP 3/4/12; `dealer_leads.py` + test con `caplog`; `dealer-insights.test.ts`. |
| **C3** Stock vivo | Compuerta motivos 5–6 y 8; vencimiento barrido cada 120 s; reservado/vendido borra `matches` y `expired_search_matches` en la misma transacción; `missed_car` y `missed_since_expiry` filtran ocultos en la consulta (un auto contado cuando era visible no sale en el email 2.5 ni en «lo que perdés»); un `directo` nunca forma pares de duplicado y un par con otro aviso oculto no se une, así no aparece en banderas rojas ajenas; sincronizados confirmados con `greatest(last_seen_at, last_full_seen_at)` en cada tick. | `dealer_listing_hidden`, `dealer_set_item_status`, `dealer_hide_listing`, `dealer_sweep`, `missed_car`, `missed_since_expiry`, `db/repos/listings.py` (`_DUPLICATES`), `db/repos/duplicates.py`, `pipeline/dealers.py` paso 3; pgTAP 5/9/10/15; `test_dealers_postgres.py` (duplicados de riesgo, `count_after_expiry`). |
| **C4** Filtro de vendedor | `matching._seller` falla todo aviso con `dealer_id` para `seller_types` sin `'dealer'`, sin depender del plan; `preview_search` y `dealer_demand` igual. | `matching.py`, `test_dealer_matching.py`, pgTAP 8/12. |
| **C5** Interruptores | Defaults apagados en la migración; sin filas de agencia nada cambia: predicados con `or` que cortan, `jsonb_strip_nulls`, `directo` deshabilitada; `missed_car` se copia de su definición vigente (`20261214120000_listing_color.sql`, con la regla estricta de color) y no de una anterior; `_DUPLICATES` y el agrupamiento de duplicados dan lo mismo sin filas de agencia; `/agencia` 404; la ficha no hace llamadas nuevas para avisos comunes; el bucle del worker solo barre (no-op). | pgTAP 1/6/7/14 y `listing_color_test.sql` entero; `test_dealers_postgres.py` (con `enabled=false` no escribe; control de duplicados entre avisos comunes); `test_risk_duplicates_postgres.py` intacto; snapshots de templates intactos. |
| **C6** Seguridad operativa | Migración solo en `automotive_agencias_test`; sin deploy, push, `.env.local` ni gastos; Docker se deja como está. | Reporte de cada agente. |
| **C7** Tests | §7 por parte; suites existentes; `tsc` y `eslint` en archivos tocados; lo no corrido, dicho. | Salida de cada suite en el reporte. |
| **C8** Reuso | `directo` por `ingest` (catálogo, fx, snapshots, duplicados, clasificación de vendedor, matching, alertas sin reescribir); sincronizados = avisos existentes con `dealer_id`; índice único `listing_id` en ítems; duplicado propio enlaza; ajeno pasa a revisión; `directo` fuera de comparables. | `pipeline/dealers.py` paso 4, pgTAP 7, `test_dealers_postgres.py`. |
| **C9** Producto | (a) alta `/agencia`; (b) planilla CSV/XLSX + manual + fuentes por link aprobadas; (c) `dealer_stock_insights` (mercado con la metodología del informe, n, demanda por modelo/año/precio/zona, días); (d) estados + «Confirmar stock»; (e) `/agencia/consultas`. Comprador: etiqueta y «Quiero que me contacten». Reproducir el informe: §10. | Rutas de §6.1; pgTAP 11/12; vitest de planilla. |
| **C10** Alcance | Ninguna función ni pantalla lee o escribe planes, precios, Mercado Pago, `plan_feature`, `sell_intent`. | `grep` de esos nombres en el diff: solo apariciones existentes. |

## 10. Cómo comparar con el informe del TT (después, con OK de Juan)

1. Base de test o, con OK de Juan, producción con la migración aplicada y `enabled=true` (canal apagado).
2. Dar de alta «TT» con centro en Quilmes, aprobarla en `/admin/agencias`.
3. Subir `autosusadostock.xlsx` por `/agencia/stock/planilla` (las patentes se descartan solas), confirmar la
   columna de precio.
4. `/agencia/stock` debe dar, por auto, la misma mediana y diferencia que la tabla 1 y 2 del informe (modelo, año
   ±1, 30 días, blue, todas las fuentes) salvo por los días transcurridos, y la demanda «Focus 2016–2018: 17 a 24 en
   año y precio, 8 a 12 en la zona, 2 activas en zona». Diferencias esperables: el informe contó a mano camiones y
   modelos raros (acá quedan en «sin comparables») y no excluyó cuentas admin.

## 11. Riesgos y pendientes

- **Datos agregados con sondeo:** una agencia aprobada podría mover el precio para ver cuándo una búsqueda cambia de
  «pocas» a un número. El mínimo de 3 personas lo acota; Juan aprueba quién ve demanda.
- **Cobertura de la sincronización:** solo avisos que ya leemos. Leer el perfil completo de un vendedor es otro
  trabajo (carriles de ML/FB).
- **Fotos:** solo por URL. Un directo sin fotos compite peor (mismo puntaje, peor tarjeta).
- **Cuentas solo-email** que abren un directo desde el email sin sesión llegan al login (no hay página externa).
- **Privacidad:** el párrafo de `/privacidad` lo aprueba Juan antes de prender `channel_enabled`.
- **Producción:** aplicar con el worker parado (FK a `listings`), reiniciarlo, y regenerar `web/types/database.ts`
  contra la base real cuando se pueda.

## 12. Embudo del canal (fase 2, migración `20261230120000_dealer_funnel.sql`)

Qué se registra además de lo de §3:

- `dealer_match_log`: la primera coincidencia de cada auto de agencia con cada búsqueda. Lo llena un trigger de
  sentencia sobre los `insert` en `matches` (solo filas cuyo aviso tiene `dealer_id`). Hace falta porque los
  `matches` de un auto oculto se borran (§2) y el rescore nocturno también borra. Sin FK a `listings` ni a
  `search_profiles`: la historia sobrevive a ambos.
- `dealer_leads.furthest_status`: el paso más lejano de la consulta (nueva < contactada < reservó < compró). Una
  consulta contactada que después «no avanzó» sigue contando como contactada.
- `dealer_sales`: la venta declarada. Al marcar una consulta «Compró» o un auto vendido, el panel pregunta con un
  clic «¿La venta vino por Ese Auto?» (`dealer_declare_sale`). Si se cierra sin responder, el inicio de `/agencia`
  vuelve a preguntar. Una respuesta por auto (o por consulta si ya no tiene auto); se puede cambiar.

Lecturas:

| Función | Para | Permiso |
|---|---|---|
| `dealer_funnel(p_start, p_end, p_dealer)` | crudo, una agencia o todas | service role |
| `admin_dealer_funnel(p_start, p_end)` | `/admin/agencias/embudo`: por agencia y total, 7/30/90 días completos de Argentina | service role (la página la lee con el cliente admin después de `requireAdmin`) |
| `my_dealer_reach()` | inicio de `/agencia`: «este mes tus autos llegaron a N personas y recibiste M consultas» | miembro de la agencia; personas en «pocas» bajo `demand_min_count` (nunca menos de 3), en SQL |

Definiciones: alerta de un auto de agencia = fila de `notifications` entregada (enviada, o dentro de un resumen
enviado) o auto listado en los `items` de un resumen enviado, posterior al alta del ítem; una por persona y auto.
Personas alcanzadas = usuarios distintos detrás de esas alertas. Se excluyen las cuentas admin y los miembros de la
propia agencia. Stock y visibles son una foto de hoy; lo demás, del período. Una venta declarada cuenta mientras su
auto (o su consulta) siga vendido.

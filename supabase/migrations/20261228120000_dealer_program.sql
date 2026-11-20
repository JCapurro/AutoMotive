-- Agencias: panel de stock y canal de venta, fases 1 y 2
-- (docs/PLAN_AGENCIAS_STOCK_Y_CANAL.md; contrato técnico en
-- docs/superpowers/specs/2026-11-18-agencias-design.md, §1-§3).
--
-- Agrega FK a `listings` (`dealer_stock_items.listing_id`,
-- `dealer_stock_items.duplicate_listing_id`, `dealer_leads.listing_id`): **parar el worker antes de
-- aplicarla** y reiniciarlo después (agrega columnas a `listings`). Aplicar a mano según la memoria de
-- migraciones de producción, con OK de Juan. Nada de esto se aplica en esta rama.
--
-- What it adds (all of it off by default, see app_config.dealer_program):
-- * source 'directo' (disabled: no crawl targets, not in the search form) and
--   listings.dealer_id / dealer_status / dealer_confirmed_at.
-- * dealers, dealer_members, dealer_sources, dealer_imports, dealer_stock_items,
--   dealer_item_private, dealer_leads. RLS by membership; clients only read,
--   every write goes through the security definer RPCs below. A dealer never
--   sees buyer_user_id, consent_text or notification_id of its leads.
-- * dealer_program() (the switch, sanitized), dealer_listing_hidden() (the
--   send gate, §2), dealer_public_name(), the agency's RPCs, the buyer's
--   contact RPCs, dealer_stock_insights() (market reference with the method of
--   docs/INFORME_STOCK_TT_2026-11-18.md and demand rounded to "few" under
--   demand_min_count people, in SQL), dealer_sweep() for the worker.
-- * Existing objects, copied from their current bodies with only the gate
--   added: comparable_listings (no 'directo'), match_cards (dealer columns
--   last, hidden rows out), preview_search (hidden out; seller_types without
--   'dealer' drops any listing with dealer_id, any plan), landing_feed (no
--   'directo'), welcome_cars and missed_car (dealer_name; missed_car keeps the
--   strict color rule of 20261214120000), missed_since_expiry (hidden out).
--   With the switches off and no dealer rows every one of them returns what it
--   returns today: the added predicates short-circuit on dealer_id is null and
--   source <> 'directo', and jsonb_strip_nulls drops a null dealer_name.
-- No plan, price, Mercado Pago or plan_feature() is read or written by
-- anything new (preview_search keeps its existing plan_feature call as it was).
--
-- Production notes: `create index listings_dealer_id_idx` is not concurrent
-- (partial, empty at creation: quick, but it scans listings under a write
-- lock), another reason to stop the worker first.
--
-- Rollback: re-apply the bodies of comparable_listings
-- (20261106120000_comparables_full_read.sql), match_cards, preview_search and
-- missed_car (20261214120000_listing_color.sql), landing_feed
-- (20261219120000_landing_hero.sql), welcome_cars
-- (20261217120000_welcome_cars.sql) and missed_since_expiry
-- (20261211120000_pass_7.sql); drop the new functions and the seven tables;
-- `alter table public.listings drop column dealer_id, drop column dealer_status,
-- drop column dealer_confirmed_at`; `delete from public.sources where id = 'directo'`
-- (only with no listings left); `delete from public.app_config where key = 'dealer_program'`.

set local lock_timeout = '5s';

-- ---------------------------------------------------------------------------
-- 1. Switch and source
-- ---------------------------------------------------------------------------

insert into public.app_config (key, value)
values ('dealer_program', '{"enabled": false, "channel_enabled": false, "manual_confirm_days": 7, "demand_min_count": 3}')
on conflict (key) do nothing;

insert into public.sources (id, name, enabled, crawl_interval_seconds, priority, detail_interval_seconds)
values ('directo', 'Agencias', false, 86400, 900, 60)
on conflict (id) do nothing;

-- ---------------------------------------------------------------------------
-- 2. Tables
-- ---------------------------------------------------------------------------

create table public.dealers (
  id             bigint generated always as identity primary key,
  name           text not null check (char_length(btrim(name)) between 2 and 80),
  contact_email  text check (contact_email is null or contact_email ~ '^[^@\s]+@[^@\s]+\.[^@\s]+$'),
  phone          text check (phone is null or phone ~ '^[0-9]{8,15}$'),
  whatsapp       text check (whatsapp is null or whatsapp ~ '^[0-9]{10,15}$'),   -- digits only, with 54
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
comment on table public.dealers is
  'Agencias (docs/PLAN_AGENCIAS_STOCK_Y_CANAL.md). profile_links: [{"kind": "mercadolibre"|"facebook"|"instagram"|"web", '
  '"url": "https://..."}], up to 6. approved_at (set by Juan in /admin/agencias) unlocks demand and the sales channel.';
create index dealers_approved_by_idx on public.dealers (approved_by) where approved_by is not null;
create index dealers_created_by_idx on public.dealers (created_by) where created_by is not null;
create trigger dealers_set_updated_at before update on public.dealers
  for each row execute function public.set_updated_at();

create table public.dealer_members (
  dealer_id  bigint not null references public.dealers (id) on delete cascade,
  user_id    uuid not null references public.profiles (id) on delete cascade,
  role       text not null default 'owner' check (role in ('owner')),
  created_at timestamptz not null default now(),
  primary key (dealer_id, user_id),
  unique (user_id)                                   -- pilot: one dealer per user
);

create table public.dealer_sources (
  id               bigint generated always as identity primary key,
  dealer_id        bigint not null references public.dealers (id) on delete cascade,
  source           text not null references public.sources (id),
  profile_url      text check (profile_url is null or profile_url ~ '^https://'),
  seller_name_hint text check (seller_name_hint is null or char_length(seller_name_hint) <= 80),
  seller_key       text,                              -- picked by Juan when approving
  status           text not null default 'pending' check (status in ('pending', 'approved', 'rejected')),
  approved_at      timestamptz,
  created_at       timestamptz not null default now(),
  check (status <> 'approved' or seller_key is not null)
);
create unique index dealer_sources_seller_once on public.dealer_sources (source, seller_key) where status = 'approved';
create index dealer_sources_dealer_idx on public.dealer_sources (dealer_id);

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
create index dealer_imports_dealer_idx on public.dealer_imports (dealer_id);
create index dealer_imports_created_by_idx on public.dealer_imports (created_by) where created_by is not null;

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
  images               jsonb not null default '[]' check (jsonb_typeof(images) = 'array'),  -- https URLs, up to 10
  status               text not null default 'available'
                         check (status in ('available', 'reserved', 'sold', 'archived')),
  confirmed_at         timestamptz,
  in_stock_since       date,
  sync_state           text not null default 'pending'
                         check (sync_state in ('pending', 'synced', 'linked', 'review', 'error', 'gone')),
  sync_error           text,
  synced_at            timestamptz,
  matched_at           timestamptz,     -- last time the worker matched it while visible
  created_by           uuid references public.profiles (id) on delete set null,
  created_at           timestamptz not null default now(),
  updated_at           timestamptz not null default now(),
  check (origin = 'sync' or (make is not null and model is not null and year is not null
                             and price is not null and currency is not null))
);
comment on table public.dealer_stock_items is
  'One row per car of a dealer''s stock. listing_id: its listing (a ''directo'' one the worker creates, or the '
  'portal listing it syncs from). duplicate_listing_id: a foreign listing that looks like the same car (sync_state '
  'review) until the dealer answers dealer_resolve_duplicate.';
create unique index dealer_stock_items_listing_once on public.dealer_stock_items (listing_id) where listing_id is not null;
create index dealer_stock_items_dealer_idx on public.dealer_stock_items (dealer_id, status);
create index dealer_stock_items_todo_idx on public.dealer_stock_items (id)
  where sync_state in ('pending', 'review') or matched_at is null;
create index dealer_stock_items_duplicate_idx on public.dealer_stock_items (duplicate_listing_id)
  where duplicate_listing_id is not null;
create index dealer_stock_items_import_idx on public.dealer_stock_items (import_id) where import_id is not null;
create index dealer_stock_items_created_by_idx on public.dealer_stock_items (created_by) where created_by is not null;
create trigger dealer_stock_items_set_updated_at before update on public.dealer_stock_items
  for each row execute function public.set_updated_at();

create table public.dealer_item_private (
  item_id           bigint primary key references public.dealer_stock_items (id) on delete cascade,
  purchase_price    numeric check (purchase_price > 0),
  purchase_currency text check (purchase_currency in ('ARS', 'USD')),
  notes             text check (notes is null or char_length(notes) <= 1000),
  updated_at        timestamptz not null default now()
);
create trigger dealer_item_private_set_updated_at before update on public.dealer_item_private
  for each row execute function public.set_updated_at();

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
comment on table public.dealer_leads is
  'A buyer asked a dealer to contact them, with explicit consent (consent_text as shown). Only through '
  'request_dealer_contact. The dealer reads name, phone and message; never buyer_user_id, consent_text or '
  'notification_id. Goes away with the buyer''s account (cascade).';
create index dealer_leads_dealer_idx on public.dealer_leads (dealer_id, created_at desc);
create index dealer_leads_unnotified_idx on public.dealer_leads (id) where dealer_notified_at is null;
create index dealer_leads_buyer_created_idx on public.dealer_leads (buyer_user_id, created_at desc);
create index dealer_leads_listing_idx on public.dealer_leads (listing_id) where listing_id is not null;
create index dealer_leads_item_idx on public.dealer_leads (item_id) where item_id is not null;
create index dealer_leads_notification_idx on public.dealer_leads (notification_id) where notification_id is not null;
create trigger dealer_leads_set_updated_at before update on public.dealer_leads
  for each row execute function public.set_updated_at();

-- listings: who sells it, as the dealer said. After dealers exists.
alter table public.listings
  add column dealer_id bigint references public.dealers (id) on delete set null,
  add column dealer_status text check (dealer_status in ('available', 'reserved', 'sold')),
  add column dealer_confirmed_at timestamptz;
create index listings_dealer_id_idx on public.listings (dealer_id) where dealer_id is not null;
comment on column public.listings.dealer_id is
  'The dealer this listing belongs to: a ''directo'' listing made from its stock, or a portal listing synced from an '
  'approved dealer_sources row. Null for everything else (the gate, dealer_listing_hidden, lets those through).';

-- ---------------------------------------------------------------------------
-- 3. RLS and privileges: clients read their own rows, write nothing
-- ---------------------------------------------------------------------------

alter table public.dealers             enable row level security;
alter table public.dealer_members      enable row level security;
alter table public.dealer_sources      enable row level security;
alter table public.dealer_imports      enable row level security;
alter table public.dealer_stock_items  enable row level security;
alter table public.dealer_item_private enable row level security;
alter table public.dealer_leads        enable row level security;

revoke all on public.dealers, public.dealer_members, public.dealer_sources, public.dealer_imports,
  public.dealer_stock_items, public.dealer_item_private, public.dealer_leads
  from public, anon, authenticated;
grant all on public.dealers, public.dealer_members, public.dealer_sources, public.dealer_imports,
  public.dealer_stock_items, public.dealer_item_private, public.dealer_leads
  to service_role;

grant select on public.dealers, public.dealer_members, public.dealer_sources, public.dealer_imports,
  public.dealer_stock_items, public.dealer_item_private
  to authenticated;
-- Column grant: buyer_user_id, consent_text and notification_id stay out.
grant select (id, dealer_id, item_id, listing_id, buyer_name, buyer_phone, message, consent_at, origin, status,
              status_changed_at, created_at)
  on public.dealer_leads to authenticated;

-- Whether the signed-in user belongs to the dealer. Security definer: the
-- policies and match_cards (security invoker) call it.
create function public.is_dealer_member(p_dealer_id bigint) returns boolean
language sql stable security definer set search_path = '' as $$
  select exists (select 1 from public.dealer_members m
                  where m.dealer_id = p_dealer_id and m.user_id = (select auth.uid()))
$$;

create policy "dealers: members read" on public.dealers
  for select to authenticated using (public.is_dealer_member(id));
create policy "dealer_members: own rows" on public.dealer_members
  for select to authenticated using (user_id = (select auth.uid()));
create policy "dealer_sources: members read" on public.dealer_sources
  for select to authenticated using (public.is_dealer_member(dealer_id));
create policy "dealer_imports: members read" on public.dealer_imports
  for select to authenticated using (public.is_dealer_member(dealer_id));
create policy "dealer_stock_items: members read" on public.dealer_stock_items
  for select to authenticated using (public.is_dealer_member(dealer_id));
create policy "dealer_item_private: members read" on public.dealer_item_private
  for select to authenticated using (exists (select 1 from public.dealer_stock_items i
                                              where i.id = item_id and public.is_dealer_member(i.dealer_id)));
create policy "dealer_leads: buyer or dealer read" on public.dealer_leads
  for select to authenticated using (buyer_user_id = (select auth.uid()) or public.is_dealer_member(dealer_id));

-- ---------------------------------------------------------------------------
-- 4. Helpers
-- ---------------------------------------------------------------------------
-- (The restrictive policy on listings for hidden 'directo' rows is at the end
-- of section 8, once dealer_listing_hidden exists.)

-- A JSON number (or a numeric string) as numeric; anything else is null. Never fails.
create function public.dealer_json_number(p jsonb) returns numeric
language sql immutable set search_path = '' as $$
  select case
           when jsonb_typeof(p) = 'number' then (p #>> '{}')::numeric
           when jsonb_typeof(p) = 'string' and (p #>> '{}') ~ '^\s*-?\d{1,15}(\.\d{1,6})?\s*$'
             then btrim(p #>> '{}')::numeric
         end
$$;

-- A whole JSON number as integer (int4 range); anything else is null. Never fails.
create function public.dealer_json_int(p jsonb) returns integer
language sql immutable set search_path = '' as $$
  select case when n is not null and n = trunc(n) and abs(n) < 2147483647 then n::integer end
    from (select public.dealer_json_number(p) as n) x
$$;

-- app_config.dealer_program, sanitized (§1): a missing or invalid key takes
-- its default; demand_min_count is never under 3.
create function public.dealer_program() returns jsonb
language sql stable security definer set search_path = '' as $$
  with raw as (
    select coalesce((select c.value from public.app_config c where c.key = 'dealer_program'), '{}'::jsonb) as v
  ), typed as (
    select case when jsonb_typeof(raw.v -> 'enabled') = 'boolean' then (raw.v ->> 'enabled')::boolean
                else false end as enabled,
           case when jsonb_typeof(raw.v -> 'channel_enabled') = 'boolean' then (raw.v ->> 'channel_enabled')::boolean
                else false end as channel_enabled,
           case when jsonb_typeof(raw.v -> 'manual_confirm_days') = 'number'
                then public.dealer_json_int(raw.v -> 'manual_confirm_days') end as days,
           case when jsonb_typeof(raw.v -> 'demand_min_count') = 'number'
                then public.dealer_json_int(raw.v -> 'demand_min_count') end as min_count
      from raw
  )
  select jsonb_build_object(
           'enabled', t.enabled,
           'channel_enabled', t.channel_enabled,
           'manual_confirm_days', case when t.days between 1 and 60 then t.days else 7 end,
           'demand_min_count', case when t.min_count between 3 and 50 then t.min_count else 3 end)
    from typed t
$$;

-- The latest blue quote, null without one.
create function public.dealer_blue_rate() returns numeric
language sql stable security definer set search_path = '' as $$
  select r.rate from public.fx_rates r where r.kind = 'blue' order by r.date desc limit 1
$$;

-- The send gate (§2): why a listing is hidden from buyers, or null.
create function public.dealer_listing_hidden(p_source text, p_dealer_id bigint, p_dealer_status text,
                                             p_confirmed_at timestamptz)
returns text
language plpgsql stable security definer set search_path = '' as $$
declare
  v_prog jsonb;
begin
  if p_dealer_id is null and p_source is distinct from 'directo' then
    return null;                                             -- 1: a listing like any other
  end if;
  if p_source is distinct from 'directo' then               -- synced portal listing
    if p_dealer_status in ('reserved', 'sold') then
      return 'not_available';                                -- 8
    end if;
    return null;                                             -- 9
  end if;
  if p_dealer_id is null then
    return 'no_dealer';                                      -- 2
  end if;
  v_prog := public.dealer_program();
  if not ((v_prog ->> 'enabled')::boolean and (v_prog ->> 'channel_enabled')::boolean) then
    return 'channel_off';                                    -- 3
  end if;
  if not exists (select 1 from public.dealers d
                  where d.id = p_dealer_id and d.approved_at is not null and d.status = 'active') then
    return 'not_approved';                                   -- 4
  end if;
  if p_dealer_status is distinct from 'available' then
    return 'not_available';                                  -- 5
  end if;
  if p_confirmed_at is null
     or p_confirmed_at < now() - make_interval(days => (v_prog ->> 'manual_confirm_days')::integer) then
    return 'unconfirmed';                                    -- 6
  end if;
  return null;                                               -- 7
end $$;

-- The dealer's name as buyers see it: only with the channel on and the dealer
-- approved and active.
create function public.dealer_public_name(p_dealer_id bigint) returns text
language sql stable security definer set search_path = '' as $$
  select d.name
    from public.dealers d
   where d.id = p_dealer_id
     and d.approved_at is not null
     and d.status = 'active'
     and (select (p ->> 'enabled')::boolean and (p ->> 'channel_enabled')::boolean
            from (select public.dealer_program() as p) x)
$$;

-- The signed-in user's dealer, for the agency RPCs: dealer_program_off,
-- not_signed_in, not_member.
create function public.dealer_require_member() returns bigint
language plpgsql stable security definer set search_path = '' as $$
declare
  v_uid uuid := (select auth.uid());
  v_id  bigint;
begin
  if not (public.dealer_program() ->> 'enabled')::boolean then
    raise exception 'dealer_program_off' using errcode = 'P0001';
  end if;
  if v_uid is null then
    raise exception 'not_signed_in' using errcode = 'P0001';
  end if;
  select m.dealer_id into v_id from public.dealer_members m where m.user_id = v_uid;
  if v_id is null then
    raise exception 'not_member' using errcode = 'P0001';
  end if;
  return v_id;
end $$;

-- The dealer's form, validated: the first wrong field, or null. Values come
-- normalized (phones as digits, trimmed text).
create function public.dealer_profile_problem(p_name text, p_locality_label text, p_lat double precision,
                                              p_lon double precision, p_phone text, p_whatsapp text,
                                              p_contact_email text, p_address_text text, p_profile_links jsonb)
returns text
language plpgsql immutable set search_path = '' as $$
declare
  e jsonb;
begin
  if p_name is null or char_length(p_name) not between 2 and 80 then return 'name'; end if;
  if p_locality_label is null or char_length(p_locality_label) not between 2 and 120 then return 'locality_label'; end if;
  if p_lat is null or p_lat not between -90 and 90 then return 'lat'; end if;
  if p_lon is null or p_lon not between -180 and 180 then return 'lon'; end if;
  if p_phone is not null and p_phone !~ '^[0-9]{8,15}$' then return 'phone'; end if;
  if p_whatsapp is not null and p_whatsapp !~ '^[0-9]{10,15}$' then return 'whatsapp'; end if;
  if p_contact_email is not null
     and (p_contact_email !~ '^[^@\s]+@[^@\s]+\.[^@\s]+$' or char_length(p_contact_email) > 200) then
    return 'contact_email';
  end if;
  if p_address_text is not null and char_length(p_address_text) > 160 then return 'address_text'; end if;
  if p_profile_links is null or jsonb_typeof(p_profile_links) <> 'array' then return 'profile_links'; end if;
  if jsonb_array_length(p_profile_links) > 6 then return 'profile_links'; end if;
  for e in select x from jsonb_array_elements(p_profile_links) x loop
    if jsonb_typeof(e) <> 'object' then return 'profile_links'; end if;
    if jsonb_typeof(e -> 'kind') is distinct from 'string'
       or (e ->> 'kind') not in ('mercadolibre', 'facebook', 'instagram', 'web') then
      return 'profile_links';
    end if;
    if jsonb_typeof(e -> 'url') is distinct from 'string'
       or (e ->> 'url') !~ '^https://[^\s]+$' or char_length(e ->> 'url') > 300 then
      return 'profile_links';
    end if;
  end loop;
  return null;
end $$;

-- A stock item's values (the keys of dealer_upsert_item), validated: the
-- first wrong field, or null. Unknown keys are ignored.
create function public.dealer_item_problem(p jsonb) returns text
language plpgsql stable set search_path = '' as $$
declare
  k      text;
  v      jsonb;
  n      numeric;
  d      date;
  v_year integer := extract(year from now() at time zone 'America/Argentina/Buenos_Aires')::integer;
begin
  if p is null or jsonb_typeof(p) <> 'object' then return 'values'; end if;
  foreach k in array array['make', 'model'] loop
    v := p -> k;
    if jsonb_typeof(v) is distinct from 'string' then return k; end if;
    if char_length(btrim(v #>> '{}')) not between 1 and 60 then return k; end if;
  end loop;
  foreach k in array array['trim', 'fuel', 'color', 'body_type'] loop
    v := p -> k;
    if v is not null and jsonb_typeof(v) <> 'null' then
      if jsonb_typeof(v) <> 'string' then return k; end if;
      if char_length(v #>> '{}') > 80 then return k; end if;
    end if;
  end loop;
  n := public.dealer_json_int(p -> 'year');
  if n is null or n < 1950 or n > v_year + 1 then return 'year'; end if;
  v := p -> 'mileage_km';
  if v is not null and jsonb_typeof(v) <> 'null' then
    n := public.dealer_json_int(v);
    if n is null or n < 0 or n > 2000000 then return 'mileage_km'; end if;
  end if;
  n := public.dealer_json_number(p -> 'price');
  if n is null or n <= 0 or n >= 1000000000000 then return 'price'; end if;
  v := p -> 'currency';
  if jsonb_typeof(v) is distinct from 'string' then return 'currency'; end if;
  if upper(btrim(v #>> '{}')) not in ('ARS', 'USD') then return 'currency'; end if;
  v := p -> 'transmission';
  if v is not null and jsonb_typeof(v) <> 'null' then
    if jsonb_typeof(v) <> 'string' then return 'transmission'; end if;
    if (v #>> '{}') not in ('manual', 'automatic') then return 'transmission'; end if;
  end if;
  v := p -> 'title';
  if v is not null and jsonb_typeof(v) <> 'null' then
    if jsonb_typeof(v) <> 'string' then return 'title'; end if;
    if char_length(v #>> '{}') > 160 then return 'title'; end if;
  end if;
  v := p -> 'description';
  if v is not null and jsonb_typeof(v) <> 'null' then
    if jsonb_typeof(v) <> 'string' then return 'description'; end if;
    if char_length(v #>> '{}') > 4000 then return 'description'; end if;
  end if;
  v := p -> 'images';
  if v is not null and jsonb_typeof(v) <> 'null' then
    if jsonb_typeof(v) <> 'array' then return 'images'; end if;
    if jsonb_array_length(v) > 10 then return 'images'; end if;
    if exists (select 1 from jsonb_array_elements(v) i
                where jsonb_typeof(i) <> 'string') then
      return 'images';
    end if;
    if exists (select 1 from jsonb_array_elements_text(v) i
                where i !~ '^(https://|http://(127\.0\.0\.1|localhost)[:/])[^\s]+$' or char_length(i) > 1000) then
      return 'images';
    end if;
  end if;
  v := p -> 'in_stock_since';
  if v is not null and jsonb_typeof(v) <> 'null' then
    if jsonb_typeof(v) <> 'string' then return 'in_stock_since'; end if;
    if (v #>> '{}') !~ '^\d{4}-\d{2}-\d{2}$' then return 'in_stock_since'; end if;
    begin
      d := (v #>> '{}')::date;
    exception when others then
      return 'in_stock_since';
    end;
    if d < date '1990-01-01' or d > (now() at time zone 'America/Argentina/Buenos_Aires')::date + 1 then
      return 'in_stock_since';
    end if;
  end if;
  return null;
end $$;

-- The columns of a validated item (dealer_item_problem returned null).
create function public.dealer_item_fields(p jsonb)
returns table (make text, model text, "trim" text, year integer, mileage_km integer, price numeric, currency text,
               transmission text, fuel text, color text, body_type text, title text, description text,
               images jsonb, in_stock_since date)
language sql stable set search_path = '' as $$
  select btrim(p ->> 'make'),
         btrim(p ->> 'model'),
         nullif(btrim(p ->> 'trim'), ''),
         public.dealer_json_int(p -> 'year'),
         public.dealer_json_int(p -> 'mileage_km'),
         public.dealer_json_number(p -> 'price'),
         upper(btrim(p ->> 'currency')),
         p ->> 'transmission',
         nullif(btrim(p ->> 'fuel'), ''),
         nullif(btrim(p ->> 'color'), ''),
         nullif(btrim(p ->> 'body_type'), ''),
         nullif(btrim(p ->> 'title'), ''),
         nullif(btrim(p ->> 'description'), ''),
         case when jsonb_typeof(p -> 'images') = 'array' then p -> 'images' else '[]'::jsonb end,
         (p ->> 'in_stock_since')::date
$$;

-- Hide one listing now: its matches, its 2.5 counts and its pending
-- notifications go; its item is matched again when it is visible again.
create function public.dealer_hide_listing(p_listing_id bigint) returns void
language plpgsql volatile security definer set search_path = '' as $$
begin
  delete from public.matches m where m.listing_id = p_listing_id;
  delete from public.expired_search_matches e where e.listing_id = p_listing_id;
  update public.notifications n
     set status = 'skipped', error = 'dealer_hidden'
   where n.listing_id = p_listing_id and n.status in ('queued', 'digest');
  update public.dealer_stock_items i set matched_at = null where i.listing_id = p_listing_id;
end $$;

-- ---------------------------------------------------------------------------
-- 5. The agency's RPCs
-- ---------------------------------------------------------------------------

-- My dealer, its sources and counts; null when I am not a member. Does not
-- require the switch (the web decides what to show).
create function public.my_dealer() returns jsonb
language sql stable security definer set search_path = '' as $$
  with me as (
    select m.dealer_id from public.dealer_members m where m.user_id = (select auth.uid())
  ), days as (
    select (public.dealer_program() ->> 'manual_confirm_days')::integer as n
  )
  select jsonb_build_object(
           'id', d.id, 'name', d.name, 'contact_email', d.contact_email, 'phone', d.phone,
           'whatsapp', d.whatsapp, 'address_text', d.address_text, 'locality_label', d.locality_label,
           'lat', d.lat, 'lon', d.lon, 'profile_links', d.profile_links, 'status', d.status,
           'approved', d.approved_at is not null,
           'sources', coalesce((
             select jsonb_agg(jsonb_build_object('id', s.id, 'source', s.source, 'profile_url', s.profile_url,
                                                 'seller_name_hint', s.seller_name_hint, 'status', s.status)
                              order by s.created_at, s.id)
               from public.dealer_sources s where s.dealer_id = d.id), '[]'::jsonb),
           'counts', (
             select jsonb_build_object(
                      'available', count(*) filter (where i.status = 'available'),
                      'reserved', count(*) filter (where i.status = 'reserved'),
                      'sold', count(*) filter (where i.status = 'sold'),
                      'unconfirmed', count(*) filter (where i.origin in ('manual', 'sheet') and i.status = 'available'
                                                        and (i.confirmed_at is null
                                                             or i.confirmed_at < now() - make_interval(days => days.n))),
                      'review', count(*) filter (where i.sync_state = 'review' and i.status <> 'archived'),
                      'leads_new', (select count(*) from public.dealer_leads ld
                                     where ld.dealer_id = d.id and ld.status = 'new'))
               from public.dealer_stock_items i
              where i.dealer_id = d.id))
    from me
    join public.dealers d on d.id = me.dealer_id
   cross join days
$$;

create function public.create_dealer(
  p_name text, p_locality_label text, p_lat double precision, p_lon double precision,
  p_phone text default null, p_whatsapp text default null, p_contact_email text default null,
  p_address_text text default null, p_profile_links jsonb default '[]'
) returns bigint
language plpgsql volatile security definer set search_path = '' as $$
declare
  v_uid      uuid := (select auth.uid());
  v_name     text := btrim(p_name);
  v_locality text := btrim(p_locality_label);
  v_phone    text := nullif(regexp_replace(coalesce(p_phone, ''), '\D', '', 'g'), '');
  v_whatsapp text := nullif(regexp_replace(coalesce(p_whatsapp, ''), '\D', '', 'g'), '');
  v_email    text := nullif(lower(btrim(p_contact_email)), '');
  v_address  text := nullif(btrim(p_address_text), '');
  v_links    jsonb := coalesce(p_profile_links, '[]'::jsonb);
  v_problem  text;
  v_id       bigint;
begin
  if not (public.dealer_program() ->> 'enabled')::boolean then
    raise exception 'dealer_program_off' using errcode = 'P0001';
  end if;
  if v_uid is null then
    raise exception 'not_signed_in' using errcode = 'P0001';
  end if;
  if exists (select 1 from public.dealer_members m where m.user_id = v_uid) then
    raise exception 'already_member' using errcode = 'P0001';
  end if;
  v_problem := public.dealer_profile_problem(v_name, v_locality, p_lat, p_lon, v_phone, v_whatsapp, v_email,
                                             v_address, v_links);
  if v_problem is not null then
    raise exception 'invalid_dealer:%', v_problem using errcode = 'P0001';
  end if;
  insert into public.dealers (name, locality_label, lat, lon, phone, whatsapp, contact_email, address_text,
                              profile_links, created_by)
  values (v_name, v_locality, p_lat, p_lon, v_phone, v_whatsapp, v_email, v_address, v_links, v_uid)
  returning id into v_id;
  begin
    insert into public.dealer_members (dealer_id, user_id, role) values (v_id, v_uid, 'owner');
  exception when unique_violation then
    raise exception 'already_member' using errcode = 'P0001';
  end;
  return v_id;
end $$;

create function public.update_my_dealer(
  p_name text, p_locality_label text, p_lat double precision, p_lon double precision,
  p_phone text default null, p_whatsapp text default null, p_contact_email text default null,
  p_address_text text default null, p_profile_links jsonb default '[]'
) returns void
language plpgsql volatile security definer set search_path = '' as $$
declare
  v_dealer   bigint := public.dealer_require_member();
  v_name     text := btrim(p_name);
  v_locality text := btrim(p_locality_label);
  v_phone    text := nullif(regexp_replace(coalesce(p_phone, ''), '\D', '', 'g'), '');
  v_whatsapp text := nullif(regexp_replace(coalesce(p_whatsapp, ''), '\D', '', 'g'), '');
  v_email    text := nullif(lower(btrim(p_contact_email)), '');
  v_address  text := nullif(btrim(p_address_text), '');
  v_links    jsonb := coalesce(p_profile_links, '[]'::jsonb);
  v_problem  text;
begin
  v_problem := public.dealer_profile_problem(v_name, v_locality, p_lat, p_lon, v_phone, v_whatsapp, v_email,
                                             v_address, v_links);
  if v_problem is not null then
    raise exception 'invalid_dealer:%', v_problem using errcode = 'P0001';
  end if;
  -- A new name or place after approval goes back to Juan: buyers consent to
  -- the name he checked, and a dealer that moves at will could locate a
  -- buyer's search by re-reading its demand by zone (agencias C2).
  update public.dealers d
     set name = v_name, locality_label = v_locality, lat = p_lat, lon = p_lon, phone = v_phone,
         whatsapp = v_whatsapp, contact_email = v_email, address_text = v_address, profile_links = v_links,
         approved_at = case when d.name is distinct from v_name or d.lat is distinct from p_lat
                                 or d.lon is distinct from p_lon then null else d.approved_at end,
         approved_by = case when d.name is distinct from v_name or d.lat is distinct from p_lat
                                 or d.lon is distinct from p_lon then null else d.approved_by end
   where d.id = v_dealer;
end $$;

-- Ask to sync a source where the dealer already publishes (Juan approves the
-- seller_key in /admin/agencias).
create function public.dealer_add_source(p_source text, p_profile_url text, p_seller_name_hint text)
returns bigint
language plpgsql volatile security definer set search_path = '' as $$
declare
  v_dealer bigint := public.dealer_require_member();
  v_url    text := nullif(btrim(p_profile_url), '');
  v_hint   text := nullif(btrim(p_seller_name_hint), '');
  v_id     bigint;
begin
  if p_source is null or p_source = 'directo'
     or not exists (select 1 from public.sources s where s.id = p_source and s.enabled) then
    raise exception 'invalid_source' using errcode = 'P0001';
  end if;
  if v_url is not null and (v_url !~ '^https://[^\s]+$' or char_length(v_url) > 300) then
    raise exception 'invalid_dealer:profile_url' using errcode = 'P0001';
  end if;
  if v_hint is not null and char_length(v_hint) > 80 then
    raise exception 'invalid_dealer:seller_name_hint' using errcode = 'P0001';
  end if;
  if v_url is null and v_hint is null then
    raise exception 'invalid_dealer:profile_url' using errcode = 'P0001';
  end if;
  insert into public.dealer_sources (dealer_id, source, profile_url, seller_name_hint)
  values (v_dealer, p_source, v_url, v_hint)
  returning id into v_id;
  return v_id;
end $$;

-- Create (p_item_id null: a manual item) or edit one of my items that is not
-- synced. On edit, a key present in p_values replaces the value (null clears
-- it); an absent key keeps it. Confirms the item and queues it for the worker.
create function public.dealer_upsert_item(p_item_id bigint, p_values jsonb) returns bigint
language plpgsql volatile security definer set search_path = '' as $$
declare
  v_dealer  bigint := public.dealer_require_member();
  v_keys    text[] := array['make', 'model', 'trim', 'year', 'mileage_km', 'price', 'currency', 'transmission',
                            'fuel', 'color', 'body_type', 'title', 'description', 'images', 'in_stock_since'];
  v_item    public.dealer_stock_items;
  v_values  jsonb;
  v_problem text;
  v_id      bigint;
begin
  if p_values is null or jsonb_typeof(p_values) <> 'object' then
    raise exception 'invalid_item:values' using errcode = 'P0001';
  end if;
  v_values := (select coalesce(jsonb_object_agg(e.key, e.value), '{}'::jsonb)
                 from jsonb_each(p_values) e where e.key = any (v_keys));
  if p_item_id is not null then
    select i.* into v_item from public.dealer_stock_items i
     where i.id = p_item_id and i.dealer_id = v_dealer and i.origin <> 'sync'
     for update;
    if not found then
      raise exception 'item_not_found' using errcode = 'P0001';
    end if;
    v_values := jsonb_build_object(
                  'make', v_item.make, 'model', v_item.model, 'trim', v_item.trim, 'year', v_item.year,
                  'mileage_km', v_item.mileage_km, 'price', v_item.price, 'currency', v_item.currency,
                  'transmission', v_item.transmission, 'fuel', v_item.fuel, 'color', v_item.color,
                  'body_type', v_item.body_type, 'title', v_item.title, 'description', v_item.description,
                  'images', v_item.images, 'in_stock_since', v_item.in_stock_since) || v_values;
  end if;
  v_problem := public.dealer_item_problem(v_values);
  if v_problem is not null then
    raise exception 'invalid_item:%', v_problem using errcode = 'P0001';
  end if;

  if p_item_id is null then
    insert into public.dealer_stock_items (dealer_id, origin, make, model, trim, year, mileage_km, price, currency,
                                           transmission, fuel, color, body_type, title, description, images,
                                           in_stock_since, confirmed_at, sync_state, matched_at, created_by)
    select v_dealer, 'manual', f.make, f.model, f.trim, f.year, f.mileage_km, f.price, f.currency,
           f.transmission, f.fuel, f.color, f.body_type, f.title, f.description, f.images,
           f.in_stock_since, now(), 'pending', null, (select auth.uid())
      from public.dealer_item_fields(v_values) f
    returning id into v_id;
    return v_id;
  end if;

  update public.dealer_stock_items i
     set make = f.make, model = f.model, trim = f.trim, year = f.year, mileage_km = f.mileage_km,
         price = f.price, currency = f.currency, transmission = f.transmission, fuel = f.fuel,
         color = f.color, body_type = f.body_type, title = f.title, description = f.description,
         images = f.images, in_stock_since = f.in_stock_since,
         confirmed_at = now(), sync_state = 'pending', sync_error = null, matched_at = null
    from public.dealer_item_fields(v_values) f
   where i.id = p_item_id;
  -- Its listing is confirmed in the same act (the worker rewrites the rest).
  update public.listings l set dealer_confirmed_at = now()
   where l.id = v_item.listing_id and l.source = 'directo' and l.dealer_id = v_dealer;
  return p_item_id;
end $$;

-- A spreadsheet's accepted rows, all or nothing.
create function public.dealer_import_items(p_rows jsonb, p_filename text, p_kind text) returns jsonb
language plpgsql volatile security definer set search_path = '' as $$
declare
  v_dealer  bigint := public.dealer_require_member();
  v_uid     uuid := (select auth.uid());
  v_row     jsonb;
  v_line    bigint;
  v_problem text;
  v_import  bigint;
  v_count   integer;
begin
  if p_rows is null or jsonb_typeof(p_rows) <> 'array' then
    raise exception 'invalid_item:rows' using errcode = 'P0001';
  end if;
  v_count := jsonb_array_length(p_rows);
  if v_count > 500 then
    raise exception 'too_many_rows' using errcode = 'P0001';
  end if;
  if p_kind is null or p_kind not in ('csv', 'xlsx') then
    raise exception 'invalid_item:kind' using errcode = 'P0001';
  end if;
  for v_row, v_line in select r.value, r.ord from jsonb_array_elements(p_rows) with ordinality r (value, ord) loop
    v_problem := public.dealer_item_problem(v_row);
    if v_problem is not null then
      raise exception 'invalid_item:%:%', v_line, v_problem using errcode = 'P0001';
    end if;
  end loop;

  insert into public.dealer_imports (dealer_id, filename, kind, rows_total, rows_imported, created_by)
  values (v_dealer, left(nullif(btrim(p_filename), ''), 200), p_kind, v_count, v_count, v_uid)
  returning id into v_import;

  insert into public.dealer_stock_items (dealer_id, origin, import_id, make, model, trim, year, mileage_km, price,
                                         currency, transmission, fuel, color, body_type, title, description, images,
                                         in_stock_since, confirmed_at, sync_state, created_by)
  select v_dealer, 'sheet', v_import, f.make, f.model, f.trim, f.year, f.mileage_km, f.price, f.currency,
         f.transmission, f.fuel, f.color, f.body_type, f.title, f.description, f.images, f.in_stock_since,
         now(), 'pending', v_uid
    from jsonb_array_elements(p_rows) with ordinality r (value, ord)
   cross join lateral public.dealer_item_fields(
           (select coalesce(jsonb_object_agg(e.key, e.value), '{}'::jsonb) from jsonb_each(r.value) e)) f
   order by r.ord;

  return jsonb_build_object('import_id', v_import, 'imported', v_count);
end $$;

-- available / reserved / sold / archived. A reserved, sold or archived car
-- leaves the buyers' screens in the same transaction.
create function public.dealer_set_item_status(p_item_id bigint, p_status text) returns void
language plpgsql volatile security definer set search_path = '' as $$
declare
  v_dealer bigint := public.dealer_require_member();
  v_item   public.dealer_stock_items;
  v_l      public.listings;
begin
  if p_status is null or p_status not in ('available', 'reserved', 'sold', 'archived') then
    raise exception 'invalid_status' using errcode = 'P0001';
  end if;
  select i.* into v_item from public.dealer_stock_items i
   where i.id = p_item_id and i.dealer_id = v_dealer
   for update;
  if not found then
    raise exception 'item_not_found' using errcode = 'P0001';
  end if;
  if v_item.origin = 'sync' and p_status = 'archived' then
    raise exception 'invalid_status' using errcode = 'P0001';
  end if;

  update public.dealer_stock_items i set status = p_status where i.id = v_item.id;

  if v_item.listing_id is null then
    return;
  end if;
  update public.listings l
     set dealer_status = case when p_status = 'archived' then 'sold' else p_status end
   where l.id = v_item.listing_id and l.dealer_id = v_dealer
  returning * into v_l;
  if v_l.id is null then
    return;
  end if;
  if public.dealer_listing_hidden(v_l.source, v_l.dealer_id, v_l.dealer_status, v_l.dealer_confirmed_at) is not null then
    perform public.dealer_hide_listing(v_l.id);
  else
    update public.dealer_stock_items i set matched_at = null where i.id = v_item.id;
  end if;
end $$;

-- «Confirmar stock»: my available manual and sheet items (all, or the given
-- ones) are confirmed now, and their listings with them.
create function public.dealer_confirm_items(p_item_ids bigint[] default null) returns integer
language plpgsql volatile security definer set search_path = '' as $$
declare
  v_dealer bigint := public.dealer_require_member();
  v_days   integer := (public.dealer_program() ->> 'manual_confirm_days')::integer;
  v_count  integer;
begin
  with target as (
    select i.id, i.listing_id,
           i.confirmed_at is null or i.confirmed_at < now() - make_interval(days => v_days) as expired
      from public.dealer_stock_items i
     where i.dealer_id = v_dealer
       and i.origin in ('manual', 'sheet')
       and i.status = 'available'
       and (p_item_ids is null or i.id = any (p_item_ids))
     for update
  ), items as (
    update public.dealer_stock_items i
       set confirmed_at = now(),
           matched_at = case when t.expired then null else i.matched_at end
      from target t
     where i.id = t.id
    returning i.id, i.listing_id
  ), listed as (
    update public.listings l set dealer_confirmed_at = now()
      from items
     where l.id = items.listing_id and l.source = 'directo' and l.dealer_id = v_dealer
    returning l.id
  )
  select count(*) into v_count from items;
  return v_count;
end $$;

-- An item in review: p_mine true asks Juan to approve the foreign listing's
-- seller as this dealer's (the item stays in review); false creates the
-- directo listing. sync_error keeps which listing was dismissed, so the worker
-- can tell it from a new duplicate.
create function public.dealer_resolve_duplicate(p_item_id bigint, p_mine boolean) returns void
language plpgsql volatile security definer set search_path = '' as $$
declare
  v_dealer bigint := public.dealer_require_member();
  v_item   public.dealer_stock_items;
  v_l      public.listings;
begin
  select i.* into v_item from public.dealer_stock_items i
   where i.id = p_item_id and i.dealer_id = v_dealer and i.sync_state = 'review'
   for update;
  if not found then
    raise exception 'item_not_found' using errcode = 'P0001';
  end if;
  if coalesce(p_mine, false) and v_item.duplicate_listing_id is not null then
    select l.* into v_l from public.listings l where l.id = v_item.duplicate_listing_id;
    if not exists (select 1 from public.dealer_sources s
                    where s.dealer_id = v_dealer and s.source = v_l.source and s.status <> 'rejected'
                      and s.seller_key is not distinct from v_l.seller_key) then
      insert into public.dealer_sources (dealer_id, source, profile_url, seller_name_hint, seller_key)
      values (v_dealer, v_l.source, case when v_l.url ~ '^https://' then left(v_l.url, 2000) end,
              left(v_l.seller_name, 80), v_l.seller_key);
    end if;
    return;
  end if;
  update public.dealer_stock_items i
     set sync_error = case when i.duplicate_listing_id is not null
                           then 'duplicate_dismissed:' || i.duplicate_listing_id end,
         duplicate_listing_id = null, sync_state = 'pending'
   where i.id = v_item.id;
end $$;

-- What the dealer paid and its notes: only the dealer sees them.
create function public.dealer_set_item_private(p_item_id bigint, p_purchase_price numeric,
                                               p_purchase_currency text, p_notes text) returns void
language plpgsql volatile security definer set search_path = '' as $$
declare
  v_dealer   bigint := public.dealer_require_member();
  v_currency text := nullif(upper(btrim(p_purchase_currency)), '');
  v_notes    text := nullif(btrim(p_notes), '');
begin
  if not exists (select 1 from public.dealer_stock_items i where i.id = p_item_id and i.dealer_id = v_dealer) then
    raise exception 'item_not_found' using errcode = 'P0001';
  end if;
  if p_purchase_price is not null and (p_purchase_price <= 0 or p_purchase_price >= 1000000000000) then
    raise exception 'invalid_item:purchase_price' using errcode = 'P0001';
  end if;
  if (v_currency is not null and v_currency not in ('ARS', 'USD'))
     or (p_purchase_price is not null and v_currency is null) then
    raise exception 'invalid_item:purchase_currency' using errcode = 'P0001';
  end if;
  if v_notes is not null and char_length(v_notes) > 1000 then
    raise exception 'invalid_item:notes' using errcode = 'P0001';
  end if;
  insert into public.dealer_item_private (item_id, purchase_price, purchase_currency, notes)
  values (p_item_id, p_purchase_price, v_currency, v_notes)
  on conflict (item_id) do update
     set purchase_price = excluded.purchase_price, purchase_currency = excluded.purchase_currency,
         notes = excluded.notes;
end $$;

create function public.dealer_set_lead_status(p_lead_id bigint, p_status text) returns void
language plpgsql volatile security definer set search_path = '' as $$
declare
  v_dealer bigint := public.dealer_require_member();
begin
  if p_status is null or p_status not in ('new', 'contacted', 'reserved', 'sold', 'lost') then
    raise exception 'invalid_status' using errcode = 'P0001';
  end if;
  update public.dealer_leads ld
     set status = p_status, status_changed_at = now()
   where ld.id = p_lead_id and ld.dealer_id = v_dealer;
  if not found then
    raise exception 'lead_not_found' using errcode = 'P0001';
  end if;
end $$;

-- ---------------------------------------------------------------------------
-- 6. Market reference and demand (§3.6, §3.7)
-- ---------------------------------------------------------------------------

-- The report's method: same model, year ±1, active, seen in 30 days, price in
-- USD frozen at the blue of the day it was read, every source but 'directo',
-- no trim or km filter.
create function public.dealer_market_ref(p_make text, p_model text, p_year integer, p_price_usd numeric,
                                         p_exclude_listing bigint)
returns jsonb
language sql stable security definer set search_path = '' as $$
  with cfg as (
    select coalesce(case when jsonb_typeof(c.value -> 'min_n') = 'number'
                         then public.dealer_json_int(c.value -> 'min_n') end, 5) as min_n
      from (select 1) one
      left join public.app_config c on c.key = 'comparables'
  ), pool as (
    select o.price_usd
      from public.listings o
     where lower(o.make) = lower(p_make) and lower(o.model) = lower(p_model)
       and o.year between p_year - 1 and p_year + 1
       and o.status = 'active'
       and o.last_seen_at >= now() - interval '30 days'
       and o.price_usd > 0 and not o.price_partial
       and o.source <> 'directo'
       and o.id is distinct from p_exclude_listing
       and not (o.attributes ? '_not_vehicle')
  ), stats as (
    select count(*)::integer as n,
           round(percentile_cont(0.5)  within group (order by p.price_usd)::numeric, 2) as median,
           round(percentile_cont(0.25) within group (order by p.price_usd)::numeric, 2) as p25,
           round(percentile_cont(0.75) within group (order by p.price_usd)::numeric, 2) as p75
      from pool p
  )
  select jsonb_build_object(
           'n', s.n, 'median', s.median, 'p25', s.p25, 'p75', s.p75,
           'vs_market_pct', case when s.median > 0 and p_price_usd > 0
                                 then round((p_price_usd / s.median - 1) * 100, 1) end,
           'enough', s.n >= cfg.min_n,
           'year_tol', 1, 'days', 30, 'blue', public.dealer_blue_rate())
    from stats s cross join cfg
$$;

-- How long the model takes to sell: gone listings of the model, year ±1, seen
-- in the last 180 days, from published (or first seen) to last seen.
create function public.dealer_model_days_to_sell(p_make text, p_model text, p_year integer) returns jsonb
language sql stable security definer set search_path = '' as $$
  with days as (
    select greatest(0, extract(epoch from g.last_seen_at - coalesce(g.published_at, g.first_seen_at)) / 86400) as d
      from public.listings g
     where lower(g.make) = lower(p_make) and lower(g.model) = lower(p_model)
       and g.year between p_year - 1 and p_year + 1
       and g.status = 'gone'
       and g.source <> 'directo'
       and g.last_seen_at >= now() - interval '180 days'
  )
  select jsonb_build_object(
           'median', case when count(*) >= 5
                          then round(percentile_cont(0.5) within group (order by d.d)::numeric)::integer end,
           'n', count(*)::integer)
    from days d
$$;

-- Raw demand: saved searches of the model (active, or created in 90 days),
-- in nested levels. Service role only: the counts leave the database only
-- rounded, through dealer_stock_insights.
create function public.dealer_demand(p_make text, p_model text, p_year integer, p_price numeric, p_currency text,
                                     p_mileage_km integer, p_lat double precision, p_lon double precision,
                                     p_exclude_users uuid[], p_source text)
returns jsonb
language sql stable security definer set search_path = '' as $$
  with blue as (
    select public.dealer_blue_rate() as rate
  ), base as (
    select sp.id, sp.user_id, sp.enabled, sp.filters as f, sp.origin_lat, sp.origin_lon, sp.radius_km
      from public.search_profiles sp
      join public.profiles pr on pr.id = sp.user_id
     where (sp.enabled or sp.created_at >= now() - interval '90 days')
       and jsonb_typeof(sp.filters -> 'model') = 'string'
       and btrim(sp.filters ->> 'model') <> ''
       and lower(btrim(sp.filters ->> 'model')) = lower(btrim(p_model))
       and (jsonb_typeof(sp.filters -> 'make') is distinct from 'string'
            or btrim(sp.filters ->> 'make') = ''
            or lower(btrim(sp.filters ->> 'make')) = lower(btrim(p_make)))
       and pr.role <> 'admin'
       and not (sp.user_id = any (coalesce(p_exclude_users, '{}'::uuid[])))
  ), parsed as (
    select b.*,
           public.dealer_json_number(b.f -> 'year_min') as year_min,
           public.dealer_json_number(b.f -> 'year_max') as year_max,
           case when jsonb_typeof(b.f -> 'years') = 'array'
                then array(select public.dealer_json_int(y) from jsonb_array_elements(b.f -> 'years') y
                            where public.dealer_json_int(y) is not null) end as years,
           public.dealer_json_number(b.f -> 'price_min') as price_min,
           public.dealer_json_number(b.f -> 'price_max') as price_max,
           public.dealer_json_number(b.f -> 'km_min') as km_min,
           public.dealer_json_number(b.f -> 'km_max') as km_max,
           case when jsonb_typeof(b.f -> 'currency') = 'string' and upper(b.f ->> 'currency') in ('ARS', 'USD')
                then upper(b.f ->> 'currency') end as currency,
           -- matching._source: a non-empty filters.sources without the car's
           -- source never receives it ('directo' is never in the form).
           case when jsonb_typeof(b.f -> 'sources') = 'array' and jsonb_array_length(b.f -> 'sources') > 0
                then not (b.f -> 'sources' ? coalesce(p_source, 'directo'))
                else false end as other_sources,
           -- Twin of intelligence.dealer.private_only: only the valid types
           -- ('private', 'dealer') count, so ['foo'] is no filter at all.
           case when jsonb_typeof(b.f -> 'seller_types') = 'array'
                then (b.f -> 'seller_types' ? 'private') and not (b.f -> 'seller_types' ? 'dealer')
                else false end as private_only
      from base b
  ), bounds as (
    select p.*,
           coalesce(p.year_min, (select min(y) from unnest(p.years) y)) as year_lo,
           coalesce(p.year_max, (select max(y) from unnest(p.years) y)) as year_hi,
           coalesce(p.currency, case when coalesce(p.price_max, p.price_min) >= 1000000 then 'ARS' else 'USD' end)
             as filter_currency
      from parsed p
  ), priced as (
    select b.*,
           case
             when p_price is null or p_price <= 0 then null
             when coalesce(upper(p_currency), b.filter_currency) = b.filter_currency then p_price
             when b.filter_currency = 'USD' then p_price / nullif(blue.rate, 0)
             else p_price * blue.rate
           end as car_price
      from bounds b cross join blue
  ), judged as (
    select p.user_id, p.enabled,
           ((p_year is null
             or ((p.year_lo is null or p_year >= p.year_lo)
                 and (p.year_hi is null or p_year <= p.year_hi)
                 and (p.years is null or cardinality(p.years) = 0 or p_year = any (p.years))))
            and ((p.price_min is null and p.price_max is null) or p.car_price is null
                 or ((p.price_min is null or p.car_price >= p.price_min)
                     and (p.price_max is null or p.car_price <= p.price_max)))
            and (p_mileage_km is null
                 or ((p.km_min is null or p_mileage_km >= p.km_min)
                     and (p.km_max is null or p_mileage_km <= p.km_max)))
            and not p.private_only
            and not p.other_sources) as fits,
           case when p_lat is null or p_lon is null then null
                else z.zones = 0 or z.hits > 0 end as in_zone
      from priced p
     cross join lateral (
       select count(*) as zones,
              count(*) filter (where public.haversine_km(zz.lat, zz.lon, p_lat, p_lon) <= zz.radius) as hits
         from (select p.origin_lat as lat, p.origin_lon as lon, p.radius_km::double precision as radius
                where p.radius_km > 0 and p.origin_lat is not null and p.origin_lon is not null
               union all
               select public.dealer_json_number(e -> 'lat')::double precision,
                      public.dealer_json_number(e -> 'lon')::double precision,
                      public.dealer_json_number(e -> 'radius_km')::double precision
                 from jsonb_array_elements(case when jsonb_typeof(p.f -> 'extra_locations') = 'array'
                                                then p.f -> 'extra_locations' else '[]'::jsonb end) e
                where public.dealer_json_number(e -> 'lat') is not null
                  and public.dealer_json_number(e -> 'lon') is not null
                  and public.dealer_json_number(e -> 'radius_km') > 0) zz
     ) z
  )
  select jsonb_build_object(
           'model', jsonb_build_object('searches', count(*), 'people', count(distinct j.user_id)),
           'fits', jsonb_build_object('searches', count(*) filter (where j.fits),
                                      'people', count(distinct j.user_id) filter (where j.fits)),
           'zone', case when p_lat is not null and p_lon is not null then
                     jsonb_build_object('searches', count(*) filter (where j.fits and j.in_zone),
                                        'people', count(distinct j.user_id) filter (where j.fits and j.in_zone)) end,
           'active_zone', case when p_lat is not null and p_lon is not null then
                     jsonb_build_object('searches', count(*) filter (where j.fits and j.in_zone and j.enabled),
                                        'people', count(distinct j.user_id)
                                                    filter (where j.fits and j.in_zone and j.enabled)) end)
    from judged j
$$;

-- One level as a dealer may see it: 0, the number of searches when at least
-- p_min people are behind them, otherwise "few". Never 1 or 2.
create function public.dealer_demand_level(p_level jsonb, p_min integer) returns jsonb
language sql immutable set search_path = '' as $$
  select case
           when p_level is null or jsonb_typeof(p_level) <> 'object' then 'null'::jsonb
           when coalesce(public.dealer_json_int(p_level -> 'searches'), 0) = 0 then '0'::jsonb
           when coalesce(public.dealer_json_int(p_level -> 'people'), 0) >= greatest(coalesce(p_min, 3), 3)
             then to_jsonb(public.dealer_json_int(p_level -> 'searches'))
           else '"few"'::jsonb
         end
$$;

-- The stock page: one row per item of my dealer that is not archived.
create function public.dealer_stock_insights()
returns table (item_id bigint, listing_id bigint, origin text, status text, sync_state text,
               make text, model text, "trim" text, year integer, mileage_km integer,
               price numeric, currency text, price_usd numeric,
               confirmed_at timestamptz, confirm_due_at timestamptz,
               hidden_reason text,
               market jsonb, days_in_stock integer, model_days_to_sell jsonb, demand jsonb)
language plpgsql stable security definer set search_path = '' as $$
#variable_conflict use_column
declare
  v_dealer   bigint := public.dealer_require_member();
  v_prog     jsonb := public.dealer_program();
  v_days     integer := (v_prog ->> 'manual_confirm_days')::integer;
  v_min      integer := (v_prog ->> 'demand_min_count')::integer;
  v_blue     numeric := public.dealer_blue_rate();
  v_d        public.dealers;
  v_members  uuid[];
begin
  select d.* into v_d from public.dealers d where d.id = v_dealer;
  select coalesce(array_agg(m.user_id), '{}'::uuid[]) into v_members
    from public.dealer_members m where m.dealer_id = v_dealer;

  return query
  with base as (
    select i.id as b_item_id, l.id as b_listing_id, i.origin as b_origin, i.status as b_status,
           i.sync_state as b_sync_state, i.created_at as b_created_at,
           case when l.id is not null then l.make else i.make end as b_make,
           case when l.id is not null then l.model else i.model end as b_model,
           case when l.id is not null then l.trim else i.trim end as b_trim,
           case when l.id is not null then l.year else i.year end as b_year,
           case when l.id is not null then l.mileage_km else i.mileage_km end as b_km,
           case when l.id is not null then l.price else i.price end as b_price,
           case when l.id is not null then l.currency else i.currency end as b_currency,
           case when i.origin = 'sync' then l.dealer_confirmed_at else i.confirmed_at end as b_confirmed_at,
           -- No listing yet, or its listing ended (the worker makes it again):
           -- not sent, whatever the gate would say of the ended row.
           case when l.id is null or l.status <> 'active' then 'pending_sync'
                else public.dealer_listing_hidden(l.source, l.dealer_id, l.dealer_status, l.dealer_confirmed_at)
           end as b_hidden,
           coalesce(l.source, 'directo') as b_source,
           coalesce(i.in_stock_since,
                    (l.published_at at time zone 'America/Argentina/Buenos_Aires')::date,
                    (i.created_at at time zone 'America/Argentina/Buenos_Aires')::date) as b_since
      from public.dealer_stock_items i
      left join public.listings l on l.id = i.listing_id
     where i.dealer_id = v_dealer and i.status <> 'archived'
  ), priced as (
    select b.*,
           case when b.b_price is null or b.b_price <= 0 then null
                when b.b_currency = 'USD' then b.b_price
                when b.b_currency = 'ARS' then round(b.b_price / nullif(v_blue, 0), 2)
           end as b_price_usd
      from base b
  )
  select p.b_item_id, p.b_listing_id, p.b_origin, p.b_status, p.b_sync_state,
         p.b_make, p.b_model, p.b_trim, p.b_year, p.b_km,
         p.b_price, p.b_currency, p.b_price_usd,
         p.b_confirmed_at,
         case when p.b_origin in ('manual', 'sheet') and p.b_confirmed_at is not null
              then p.b_confirmed_at + make_interval(days => v_days) end,
         p.b_hidden,
         public.dealer_market_ref(p.b_make, p.b_model, p.b_year, p.b_price_usd, p.b_listing_id),
         ((now() at time zone 'America/Argentina/Buenos_Aires')::date - p.b_since)::integer,
         public.dealer_model_days_to_sell(p.b_make, p.b_model, p.b_year),
         case when v_d.approved_at is null then '{"approved": false}'::jsonb
              else (select jsonb_build_object(
                             'approved', true, 'window_days', 90, 'min_count', v_min,
                             'levels', jsonb_build_object(
                                         'model', public.dealer_demand_level(r.raw -> 'model', v_min),
                                         'fits', public.dealer_demand_level(r.raw -> 'fits', v_min),
                                         'zone', public.dealer_demand_level(r.raw -> 'zone', v_min),
                                         'active_zone', public.dealer_demand_level(r.raw -> 'active_zone', v_min)))
                      from (select public.dealer_demand(p.b_make, p.b_model, p.b_year, p.b_price, p.b_currency,
                                                        p.b_km, v_d.lat, v_d.lon, v_members, p.b_source) as raw) r)
         end
    from priced p
   order by p.b_created_at, p.b_item_id;
end $$;

-- The market page of one car («Ver el mercado»): the very listings behind
-- dealer_market_ref for that item (same model, year ±1, active, seen in the
-- last 30 days, priced, never 'directo'), cheapest first. Twin of
-- dealer_market_ref's pool: change both together. Public listings only, and
-- only for a member of the item's dealer.
create function public.dealer_market_listings(p_item_id bigint)
returns table (listing_id bigint, source text, url text, title text, "trim" text, year integer,
               mileage_km integer, price numeric, currency text, price_usd numeric,
               location_text text, seller_type text, first_seen_at timestamptz)
language plpgsql stable security definer set search_path = '' as $$
#variable_conflict use_column
declare
  v_dealer bigint := public.dealer_require_member();
  v_make text; v_model text; v_year integer; v_listing bigint;
begin
  select case when l.id is not null then l.make else i.make end,
         case when l.id is not null then l.model else i.model end,
         case when l.id is not null then l.year else i.year end,
         l.id
    into v_make, v_model, v_year, v_listing
    from public.dealer_stock_items i
    left join public.listings l on l.id = i.listing_id
   where i.id = p_item_id and i.dealer_id = v_dealer;
  if not found then
    raise exception 'not_found' using errcode = 'P0001';
  end if;

  return query
  select o.id, o.source, o.url, o.title, o.trim, o.year, o.mileage_km, o.price, o.currency, o.price_usd,
         o.location_text, o.seller_type, o.first_seen_at
    from public.listings o
   where lower(o.make) = lower(v_make) and lower(o.model) = lower(v_model)
     and o.year between v_year - 1 and v_year + 1
     and o.status = 'active'
     and o.last_seen_at >= now() - interval '30 days'
     and o.price_usd > 0 and not o.price_partial
     and o.source <> 'directo'
     and o.id is distinct from v_listing
     and not (o.attributes ? '_not_vehicle')
   order by o.price_usd, o.id
   limit 500;
end $$;

-- ---------------------------------------------------------------------------
-- 7. The buyer's side (§3.8)
-- ---------------------------------------------------------------------------

create function public.request_dealer_contact(p_listing_id bigint, p_name text, p_phone text, p_message text,
                                              p_consent boolean, p_consent_text text,
                                              p_notification_id bigint default null)
returns jsonb
language plpgsql volatile security definer set search_path = '' as $$
declare
  v_uid     uuid := (select auth.uid());
  v_prog    jsonb := public.dealer_program();
  v_l       public.listings;
  v_dealer  public.dealers;
  v_name    text := btrim(p_name);
  v_phone   text := regexp_replace(coalesce(p_phone, ''), '\D', '', 'g');
  v_message text := nullif(btrim(p_message), '');
  v_consent text := btrim(p_consent_text);
  v_lead    public.dealer_leads;
  v_origin  text := 'ficha';
  v_vehicle text;
begin
  if not ((v_prog ->> 'enabled')::boolean and (v_prog ->> 'channel_enabled')::boolean) then
    raise exception 'dealer_program_off' using errcode = 'P0001';
  end if;
  if v_uid is null then
    raise exception 'not_signed_in' using errcode = 'P0001';
  end if;
  if p_consent is not true or v_consent is null or char_length(v_consent) not between 20 and 300 then
    raise exception 'consent_required' using errcode = 'P0001';
  end if;

  select l.* into v_l from public.listings l where l.id = p_listing_id;
  if v_l.id is null or v_l.dealer_id is null
     or public.dealer_public_name(v_l.dealer_id) is null
     or public.dealer_listing_hidden(v_l.source, v_l.dealer_id, v_l.dealer_status, v_l.dealer_confirmed_at) is not null
     or exists (select 1 from public.dealer_members m where m.dealer_id = v_l.dealer_id and m.user_id = v_uid) then
    raise exception 'contact_unavailable' using errcode = 'P0001';
  end if;
  select d.* into v_dealer from public.dealers d where d.id = v_l.dealer_id;
  v_vehicle := coalesce(nullif(concat_ws(' ', v_l.make, v_l.model, v_l.year::text), ''), v_l.title);

  if v_name is null or char_length(v_name) not between 2 and 80 then
    raise exception 'invalid_contact:name' using errcode = 'P0001';
  end if;
  if v_phone !~ '^[0-9]{8,15}$' then
    raise exception 'invalid_contact:phone' using errcode = 'P0001';
  end if;
  if v_message is not null and char_length(v_message) > 500 then
    raise exception 'invalid_contact:message' using errcode = 'P0001';
  end if;

  -- One buyer at a time: the 24 h cap can't be raced.
  perform pg_advisory_xact_lock(hashtext('public.request_dealer_contact'), hashtext(v_uid::text));

  select ld.* into v_lead from public.dealer_leads ld
   where ld.buyer_user_id = v_uid and ld.listing_id = p_listing_id;
  if v_lead.id is not null then
    return jsonb_build_object('lead_id', v_lead.id, 'created', false, 'dealer_name', v_dealer.name,
                              'whatsapp', v_dealer.whatsapp, 'vehicle', v_vehicle, 'created_at', v_lead.created_at);
  end if;

  if (select count(*) from public.dealer_leads ld
       where ld.buyer_user_id = v_uid and ld.created_at > now() - interval '24 hours') >= 5 then
    raise exception 'rate_limited' using errcode = 'P0001';
  end if;

  if p_notification_id is not null then
    select n.channel::text into v_origin
      from public.notifications n
     where n.id = p_notification_id and n.user_id = v_uid and n.listing_id = p_listing_id;
    if v_origin is null or v_origin not in ('email', 'telegram', 'web') then
      v_origin := 'ficha';
    end if;
  end if;

  insert into public.dealer_leads (dealer_id, item_id, listing_id, buyer_user_id, buyer_name, buyer_phone, message,
                                   consent_text, notification_id, origin)
  values (v_l.dealer_id,
          (select i.id from public.dealer_stock_items i where i.listing_id = p_listing_id),
          p_listing_id, v_uid, v_name, v_phone, v_message, v_consent,
          case when v_origin <> 'ficha' then p_notification_id end, v_origin)
  returning * into v_lead;

  -- No name, phone or message in the event.
  insert into public.events (user_id, name, props)
  values (v_uid, 'dealer_lead_created',
          jsonb_build_object('lead_id', v_lead.id, 'dealer_id', v_lead.dealer_id, 'listing_id', p_listing_id,
                             'origin', v_origin));

  return jsonb_build_object('lead_id', v_lead.id, 'created', true, 'dealer_name', v_dealer.name,
                            'whatsapp', v_dealer.whatsapp, 'vehicle', v_vehicle, 'created_at', v_lead.created_at);
end $$;

-- For the listing page; null unless the listing is a dealer's or 'directo'.
create function public.listing_dealer_card(p_listing_id bigint) returns jsonb
language sql stable security definer set search_path = '' as $$
  with l as (
    select l.id, l.source, l.dealer_id, l.dealer_status, l.dealer_confirmed_at
      from public.listings l
     where l.id = p_listing_id and (l.dealer_id is not null or l.source = 'directo')
  ), x as (
    select l.*,
           (select auth.uid()) as uid,
           public.dealer_public_name(l.dealer_id) as pub,
           public.dealer_listing_hidden(l.source, l.dealer_id, l.dealer_status, l.dealer_confirmed_at) as hidden,
           l.dealer_id is not null and public.is_dealer_member(l.dealer_id) as member
      from l
  ), y as (
    select x.*,
           x.pub is not null and x.hidden is null as badge,
           (select jsonb_build_object('id', ld.id, 'created_at', ld.created_at, 'status', ld.status)
              from public.dealer_leads ld
             where ld.buyer_user_id = x.uid and ld.listing_id = x.id) as my_lead
      from x
  )
  select jsonb_build_object(
           -- Nothing of an unlabeled listing to a non-member: not whose it is
           -- nor its internal state (agencias C2).
           'dealer_id', case when y.badge or y.member then y.dealer_id end,
           'dealer_name', case when y.badge then y.pub
                               when y.member then (select d.name from public.dealers d where d.id = y.dealer_id) end,
           'badge', y.badge,
           'is_directo', y.source = 'directo',
           'hidden_reason', case when y.member then y.hidden end,
           'confirmed_at', case when y.badge or y.member then y.dealer_confirmed_at end,
           'viewer_is_member', y.member,
           'can_request', y.badge and y.uid is not null and not y.member and y.my_lead is null,
           'my_lead', y.my_lead,
           'whatsapp', case when y.my_lead is not null
                            then (select d.whatsapp from public.dealers d where d.id = y.dealer_id) end)
    from y
$$;

-- The labels for a list of listings (up to 200): only those a buyer sees
-- with the «Agencia» chip.
create function public.dealer_badges(p_listing_ids bigint[])
returns table (listing_id bigint, dealer_name text, confirmed_at timestamptz)
language sql stable security definer set search_path = '' as $$
  select l.id, public.dealer_public_name(l.dealer_id), l.dealer_confirmed_at
    from public.listings l
   where l.id in (select distinct u.id from unnest((coalesce(p_listing_ids, '{}'::bigint[]))[1:200]) u (id))
     and l.dealer_id is not null
     and public.dealer_public_name(l.dealer_id) is not null
     and public.dealer_listing_hidden(l.source, l.dealer_id, l.dealer_status, l.dealer_confirmed_at) is null
$$;

-- ---------------------------------------------------------------------------
-- 8. Worker and admin
-- ---------------------------------------------------------------------------

-- Every DEALER_TICK_SECONDS: hide what stopped passing the gate (confirmation
-- expired, dealer unapproved or paused, channel off).
create function public.dealer_sweep()
returns table (matches_deleted integer, notifications_skipped integer, expired_deleted integer)
language plpgsql volatile security definer set search_path = '' as $$
declare
  v_ids bigint[];
  v_m   integer := 0;
  v_n   integer := 0;
  v_e   integer := 0;
begin
  select coalesce(array_agg(l.id), '{}'::bigint[]) into v_ids
    from public.listings l
   where (l.dealer_id is not null or l.source = 'directo')
     and public.dealer_listing_hidden(l.source, l.dealer_id, l.dealer_status, l.dealer_confirmed_at) is not null
     and (exists (select 1 from public.matches m where m.listing_id = l.id)
          or exists (select 1 from public.expired_search_matches e where e.listing_id = l.id)
          or exists (select 1 from public.notifications n
                      where n.listing_id = l.id and n.status in ('queued', 'digest')));
  if cardinality(v_ids) > 0 then
    delete from public.matches m where m.listing_id = any (v_ids);
    get diagnostics v_m = row_count;
    delete from public.expired_search_matches e where e.listing_id = any (v_ids);
    get diagnostics v_e = row_count;
    update public.notifications n
       set status = 'skipped', error = 'dealer_hidden'
     where n.listing_id = any (v_ids) and n.status in ('queued', 'digest');
    get diagnostics v_n = row_count;
    update public.dealer_stock_items i set matched_at = null
     where i.listing_id = any (v_ids) and i.matched_at is not null;
  end if;
  return query select v_m, v_n, v_e;
end $$;

-- /admin/agencias: the sellers of a source that look like the dealer's hint.
create function public.admin_dealer_seller_candidates(p_source text, p_hint text)
returns table (seller_key text, seller_name text, active integer)
language sql stable security definer set search_path = '' as $$
  with pat as (
    select '%' || replace(replace(replace(btrim(p_hint), '\', '\\'), '%', '\%'), '_', '\_') || '%' as p
     where char_length(btrim(coalesce(p_hint, ''))) >= 2
  )
  select l.seller_key, max(l.seller_name), count(*)::integer
    from public.listings l
   cross join pat
   where l.source = p_source
     and l.status = 'active'
     and l.seller_key is not null
     and (l.seller_key ilike pat.p or l.seller_name ilike pat.p)
   group by l.seller_key
   order by 3 desc, 1
   limit 30
$$;

-- listings: a 'directo' listing the gate hides (unconfirmed, reserved, sold,
-- dealer unapproved, channel off) is the dealer's business until it is sent:
-- only its members read it. Restrictive, so it narrows the existing
-- "listings: authenticated read" (using true). Every other listing passes on
-- the first, cheap term. The service role (worker, admin) bypasses RLS.
-- Known and accepted: listings.dealer_id / dealer_status / dealer_confirmed_at
-- of synced portal listings stay readable like every other column of a
-- portal listing (no buyer data in them).
create policy "listings: hidden dealer stock" on public.listings
  as restrictive for select to authenticated
  using (source <> 'directo'
         or public.dealer_listing_hidden(source, dealer_id, dealer_status, dealer_confirmed_at) is null
         or public.is_dealer_member(dealer_id));

-- ---------------------------------------------------------------------------
-- 9. Existing objects: current bodies plus the gate
-- ---------------------------------------------------------------------------

-- comparable_listings: 20261106120000's, without 'directo' (covers
-- comparables() and comparable_pool()). No SET, as before, so it inlines.
create or replace function public.comparable_listings(
  p_listing_id   bigint,
  p_year_tol     integer default null,
  p_km_tol_pct   numeric default null,
  p_max_age_days integer default null
) returns setof public.listings
language sql
stable
as $$
  -- Materialized: read once per call, not once per comparable.
  with cfg as materialized (
    select coalesce(p_year_tol,     (c.value->>'year_tol')::integer,     1)  as year_tol,
           coalesce(p_km_tol_pct,   (c.value->>'km_tol_pct')::numeric,   25) as km_tol_pct,
           coalesce(p_max_age_days, (c.value->>'max_age_days')::integer, 30) as max_age_days,
           (c.value->>'gone_max_age_days')::integer                        as gone_days,
           coalesce(c.value->'confirm_sources', '[]'::jsonb)                 as confirm_sources,
           coalesce((c.value->>'confirm_grace_hours')::numeric, 36) * interval '1 hour' as grace
      from (select 1) as one
      left join public.app_config c on c.key = 'comparables'
  )
  select o.*
    from public.listings t
   cross join cfg
    join public.listings o
      on lower(o.make) = lower(t.make) and lower(o.model) = lower(t.model)
   where t.id = p_listing_id and t.make is not null and t.model is not null
     and o.id <> t.id
     -- A dealer's asking price is not market (agencias, §0.9).
     and o.source <> 'directo'
     and o.price_usd > 0
     and not o.price_partial
     and o.last_seen_at >= now() - make_interval(days => cfg.max_age_days)
     and (t.year is null or o.year between t.year - cfg.year_tol and t.year + cfg.year_tol)
     and (t.mileage_km is null or o.mileage_km is null
          or o.mileage_km between t.mileage_km * (1 - cfg.km_tol_pct / 100)
                              and t.mileage_km * (1 + cfg.km_tol_pct / 100))
     and (o.status = 'active' or cfg.gone_days is null
          or o.last_seen_at >= now() - make_interval(days => cfg.gone_days))
     -- The source test first, and not a bare NOT EXISTS: the planner would turn
     -- that into an anti join that reads crawl_targets for every comparable
     -- (3x slower in prod on 22/10/2026); this way only confirm_sources pay.
     and not (cfg.confirm_sources ? o.source
              and exists (select 1 from public.listing_unconfirmed(
                            o.source, o.make, o.model, o.year, o.mileage_km,
                            greatest(o.last_seen_at, o.last_full_seen_at), cfg.confirm_sources, cfg.grace)))
     and o.probable_repost_of is distinct from t.id
     -- A repost (find_repost_of points at the root) is the same car as its
     -- original: it counts only while the original does not.
     and (o.probable_repost_of is null or not exists (
           select 1
             from public.listings x
            where x.id = o.probable_repost_of
              and x.price_usd > 0
              and not x.price_partial
              and x.last_seen_at >= now() - make_interval(days => cfg.max_age_days)
              and (x.status = 'active' or cfg.gone_days is null
                   or x.last_seen_at >= now() - make_interval(days => cfg.gone_days))
              and not (cfg.confirm_sources ? x.source
                       and exists (select 1 from public.listing_unconfirmed(
                                     x.source, x.make, x.model, x.year, x.mileage_km,
                                     greatest(x.last_seen_at, x.last_full_seen_at),
                                     cfg.confirm_sources, cfg.grace)))))
$$;

-- match_cards: 20261214120000's, plus dealer_id, dealer_name and
-- dealer_confirmed_at last (only with the label) and hidden listings out.
create or replace view public.match_cards with (security_invoker = true) as
select m.id                              as match_id,
       m.search_profile_id,
       sp.name                           as profile_name,
       sp.user_id,
       m.listing_id,
       m.score,
       m.level,
       m.is_backfill,
       m.generated_at,
       m.price_ref,
       m.red_flags,
       l.title,
       l.make,
       l.model,
       l.trim,
       l.year,
       l.price,
       l.currency,
       l.price_usd,
       l.mileage_km,
       l.transmission,
       l.fuel,
       l.location_text,
       l.source,
       l.images,
       l.published_at,
       l.first_seen_at,
       l.status                          as listing_status,
       l.probable_repost_of,
       coalesce(i.status, 'new')         as status,
       coalesce(i.saved, false)          as saved,
       i.rejection_reason,
       l.price_published,
       l.price_published_currency,
       l.price_source,
       l.description_facts -> 'price_check' ->> 'effective_kind' as price_kind,
       coalesce((l.description_facts -> 'financing' ->> 'offered')::boolean, false) as financing_offered,
       l.body_type,
       i.note,
       -- Only while the search has the strict filter: a seller type and the
       -- owner's seller_filter as last synced. Short-circuits for the rest.
       case when m.match_reasons -> 'seller' ->> 'result' = 'unknown'
                 and m.match_reasons -> 'seller' ->> 'kind' = 'hard'
                 and jsonb_typeof(sp.filters -> 'seller_types') = 'array'
                 and sp.filters -> 'seller_types' <> '[]'::jsonb
            then coalesce((select p.seller_filter_access from public.profiles p where p.id = sp.user_id), false)
            else false end               as seller_unknown,
       l.color,
       l.attributes -> '_color' ->> 'method' as color_method,
       case when l.dealer_id is not null and public.dealer_public_name(l.dealer_id) is not null
            then l.dealer_id end         as dealer_id,
       case when l.dealer_id is not null then public.dealer_public_name(l.dealer_id) end as dealer_name,
       case when l.dealer_id is not null and public.dealer_public_name(l.dealer_id) is not null
            then l.dealer_confirmed_at end as dealer_confirmed_at
  from public.matches m
  join public.search_profiles sp on sp.id = m.search_profile_id
  join public.listings l on l.id = m.listing_id
  left join public.user_listing_interactions i
    on i.user_id = sp.user_id and i.listing_id = m.listing_id
 where (l.dealer_id is null and l.source <> 'directo')
    or public.dealer_listing_hidden(l.source, l.dealer_id, l.dealer_status, l.dealer_confirmed_at) is null;

-- preview_search: 20261214120000's, plus the gate and the dealer-stock rule
-- of the seller filter (any plan, as matching._seller) in both branches.
create or replace function public.preview_search(
  p_filters    jsonb,
  p_origin_lat double precision default null,
  p_origin_lon double precision default null,
  p_radius_km  double precision default null
) returns jsonb
language sql
stable
security definer
set search_path = ''
as $$
  with f as (
    select nullif(btrim(p_filters->>'make'), '')           as make,
           nullif(btrim(p_filters->>'model'), '')          as model,
           public.search_is_model_less(p_filters)          as model_less,
           public.search_body_types(p_filters)             as body_types,
           public.search_colors(p_filters)                 as colors,
           (p_filters->>'year_min')::integer               as year_min,
           (p_filters->>'year_max')::integer               as year_max,
           (p_filters->>'price_min')::numeric              as price_min,
           (p_filters->>'price_max')::numeric              as price_max,
           upper(coalesce(nullif(p_filters->>'currency', ''),
                          case when coalesce((p_filters->>'price_max')::numeric,
                                             (p_filters->>'price_min')::numeric, 0) >= 1000000
                               then 'ARS' else 'USD' end)) as currency,
           (p_filters->>'km_min')::integer                 as km_min,
           (p_filters->>'km_max')::integer                 as km_max,
           nullif(p_filters->>'transmission', '')          as transmission,
           nullif(p_filters->>'fuel', '')                  as fuel,
           case when jsonb_typeof(p_filters->'sources') = 'array'
                     and jsonb_array_length(p_filters->'sources') > 0
                then array(select jsonb_array_elements_text(p_filters->'sources')) end as sources,
           case when coalesce((p_filters->>'trim_strict')::boolean, false)
                     and jsonb_typeof(p_filters->'trims') = 'array'
                     and jsonb_array_length(p_filters->'trims') > 0
                then array(select lower(jsonb_array_elements_text(p_filters->'trims'))) end as strict_trims,
           case when jsonb_typeof(p_filters->'seller_types') = 'array'
                     and jsonb_array_length(p_filters->'seller_types') > 0
                     and public.plan_feature((select auth.uid()), 'seller_filter')
                then array(select jsonb_array_elements_text(p_filters->'seller_types')) end as seller_types,
           -- Dealer stock: a seller filter without 'dealer' leaves out every
           -- listing with dealer_id, whatever the plan (agencias C4).
           -- Twin of intelligence.dealer.private_only: only the valid types
           -- ('private', 'dealer') count, so ['foo'] is no filter at all.
           case when jsonb_typeof(p_filters->'seller_types') = 'array'
                then (p_filters->'seller_types' ? 'private')
                     and not (p_filters->'seller_types' ? 'dealer')
                else false end                     as private_only
  ),
  fx as (
    select rate from public.fx_rates order by date desc, (kind = 'blue') desc limit 1
  ),
  -- The places the search adds, read as numbers. A value that isn't one is
  -- null, so its place is skipped as matching skips it (the case keeps the
  -- cast from ever seeing the text).
  extra as (
    select case when e->>'lat' ~ '^\s*[-+]?\d+(\.\d+)?\s*$' then (e->>'lat')::double precision end as lat,
           case when e->>'lon' ~ '^\s*[-+]?\d+(\.\d+)?\s*$' then (e->>'lon')::double precision end as lon,
           case when e->>'radius_km' ~ '^\s*[-+]?\d+(\.\d+)?\s*$'
                then (e->>'radius_km')::double precision end as radius
      from jsonb_array_elements(case when jsonb_typeof(p_filters->'extra_locations') = 'array'
                                     then p_filters->'extra_locations' else '[]'::jsonb end) e
  ),
  -- The search's own place and the ones it adds, as matching's search_zones.
  zones as (
    select p_origin_lat as lat, p_origin_lon as lon, p_radius_km as radius
     where p_radius_km > 0 and p_origin_lat is not null and p_origin_lon is not null
    union all
    select x.lat, x.lon, x.radius
      from extra x
     where x.lat is not null and x.lon is not null and x.radius > 0
  ),
  -- One branch per shape, each with its own index: (lower(make), lower(model),
  -- year) or listings_body_type_active_idx.
  candidates as (
    select l.*
      from f
      join public.listings l on lower(l.make) = lower(f.make)
     where f.make is not null
       and (f.model is null or lower(l.model) = lower(f.model))
       and l.status = 'active'
       and l.last_seen_at >= now() - interval '30 days'
       and not l.price_partial
       and ((l.dealer_id is null and l.source <> 'directo')
            or public.dealer_listing_hidden(l.source, l.dealer_id, l.dealer_status, l.dealer_confirmed_at) is null)
       and not (l.dealer_id is not null and f.private_only)
    union all
    select l.*
      from f
      join public.listings l on l.body_type = any (f.body_types)
     where f.model_less
       and f.body_types is not null
       and l.status = 'active'
       and l.body_type is not null
       and l.last_seen_at >= now() - interval '30 days'
       and not l.price_partial
       and ((l.dealer_id is null and l.source <> 'directo')
            or public.dealer_listing_hidden(l.source, l.dealer_id, l.dealer_status, l.dealer_confirmed_at) is null)
       and not (l.dealer_id is not null and f.private_only)
  ),
  priced as (
    select l.*,
           case
             when l.price is null or l.price <= 0 then null
             when upper(coalesce(l.currency, f.currency)) = f.currency then l.price
             when f.currency = 'USD' then coalesce(l.price_usd, l.price / nullif(fx.rate, 0))
             else l.price * fx.rate
           end as price_in_filter
      from candidates l
     cross join f
      left join fx on true
  ),
  hits as (
    select p.*
      from priced p
     cross join f
     where (p.year is null or f.year_min is null or p.year >= f.year_min)
       and (p.year is null or f.year_max is null or p.year <= f.year_max)
       and (p.mileage_km is null or f.km_min is null or p.mileage_km >= f.km_min)
       and (p.mileage_km is null or f.km_max is null or p.mileage_km <= f.km_max)
       and (p.price_in_filter is null or f.price_min is null or p.price_in_filter >= f.price_min)
       and (p.price_in_filter is null or f.price_max is null or p.price_in_filter <= f.price_max)
       and (f.transmission is null or p.transmission is null or p.transmission = f.transmission)
       and (f.fuel is null or p.fuel is null or position(lower(f.fuel) in lower(p.fuel)) > 0)
       and (f.body_types is null or p.body_type = any (f.body_types)
            or (p.body_type is null and not f.model_less))
       and public.listing_color_fits(p.color, p.attributes, f.colors)
       and (f.sources is null or p.source = any (f.sources))
       and (f.seller_types is null
            or (case when p.seller_type = 'dealer' or p.dealer_inferred then 'dealer' else p.seller_type end) is null
            or (case when p.seller_type = 'dealer' or p.dealer_inferred then 'dealer' else p.seller_type end)
               = any (f.seller_types))
       and (f.strict_trims is null or p.trim is null
            or exists (select 1 from unnest(f.strict_trims) t where position(t in lower(p.trim)) > 0))
       and (not exists (select 1 from zones)
            or (p.lat is not null and p.lon is not null
                and exists (select 1 from zones z where public.haversine_km(z.lat, z.lon, p.lat, p.lon) <= z.radius)))
  ),
  sample as (
    select h.id, h.title, h.make, h.model, h.trim, h.year, h.price, h.currency, h.mileage_km,
           h.location_text, h.source, h.first_seen_at, h.body_type, h.color,
           case when h.dealer_id is not null then public.dealer_public_name(h.dealer_id) end as dealer_name
      from hits h
     order by h.first_seen_at desc
     limit 3
  )
  -- dealer_name only when there is one: an ordinary sample row stays as today.
  select jsonb_build_object(
           'count',  (select count(*) from hits),
           'sample', coalesce((select jsonb_agg(case when s.dealer_name is null then to_jsonb(s) - 'dealer_name'
                                                     else to_jsonb(s) end
                                                order by s.first_seen_at desc) from sample s),
                              '[]'::jsonb))
$$;

-- landing_feed: 20261219120000's, without 'directo' (no public dealer page;
-- the home is anonymous).
create or replace function public.landing_feed()
returns jsonb
language sql stable security definer set search_path = '' as $$
  with flagged as (
    select distinct on (l.id)
           l.id, l.make, l.model, l.trim, l.year, l.mileage_km, l.price_usd, l.price_partial,
           l.source, l.location_text, l.first_seen_at, m.price_ref, m.red_flags
      from public.listings l
      join public.matches m on m.listing_id = l.id
     where l.first_seen_at > now() - interval '24 hours'
       and l.status = 'active'
       and l.source <> 'directo'
       and m.level = 'high'
     order by l.id, m.score desc
  ), solid as (
    select distinct on (f.make, f.model) f.*
      from flagged f
     where f.make is not null and f.model is not null and f.year is not null
       and f.mileage_km is not null and f.price_usd is not null
       and f.price_partial is not true
       and jsonb_typeof(f.price_ref -> 'n') = 'number'
       and jsonb_typeof(f.price_ref -> 'median') = 'number'
       and jsonb_typeof(f.price_ref -> 'diff_pct') = 'number'
       and (f.price_ref ->> 'n')::numeric >= 8
       and (f.price_ref ->> 'median')::numeric > f.price_usd
       and (f.price_ref ->> 'diff_pct')::numeric between 8 and 30
       and not exists (
         select 1
           from jsonb_array_elements(case when jsonb_typeof(f.red_flags) = 'array' then f.red_flags else '[]'::jsonb end) flag
          where coalesce(flag ->> 'id', '') not in ('no_service', 'no_owners', 'short_description', 'no_timing_belt')
       )
     order by f.make, f.model, f.first_seen_at desc
  ), shown as (
    select * from solid order by first_seen_at desc limit 4
  ), models as (
    select sp.filters ->> 'make' as make, sp.filters ->> 'model' as model, count(distinct sp.user_id) as people
      from public.search_profiles sp
     where sp.created_at > now() - interval '30 days'
       and coalesce(sp.filters ->> 'make', '') <> ''
       and coalesce(sp.filters ->> 'model', '') <> ''
     group by 1, 2
    having count(distinct sp.user_id) >= 3
     order by people desc, 1, 2
     limit 10
  )
  select jsonb_build_object(
    'flagged_24h', (select count(*) from flagged),
    'rows', coalesce((
      select jsonb_agg(jsonb_build_object(
               'make', s.make, 'model', s.model, 'trim', s.trim, 'year', s.year,
               'km', s.mileage_km, 'usd', round(s.price_usd),
               'median', round((s.price_ref ->> 'median')::numeric),
               'n', (s.price_ref ->> 'n')::numeric,
               'where', s.location_text, 'source', s.source, 'seen_at', s.first_seen_at
             ) order by s.first_seen_at desc)
        from shown s), '[]'::jsonb),
    'models', coalesce((
      select jsonb_agg(jsonb_build_object('make', mo.make, 'model', mo.model) order by mo.people desc, mo.make, mo.model)
        from models mo), '[]'::jsonb)
  );
$$;

-- welcome_cars: 20261217120000's, plus dealer_name (stripped when null).
create or replace function public.welcome_cars(p_user uuid, p_search bigint, p_limit integer default 3) returns jsonb
language sql stable security definer set search_path = '' as $$
  select coalesce(jsonb_agg(c.car order by c.ord), '[]'::jsonb)
    from (
      select row_number() over (order by case m.level when 'high' then 3 when 'good' then 2 else 1 end desc,
                                         m.score desc, m.id) as ord,
             jsonb_strip_nulls(jsonb_build_object(
               'listing_id', l.id, 'title', l.title, 'make', l.make, 'model', l.model, 'trim', l.trim,
               'year', l.year, 'price', l.price, 'currency', l.currency, 'km', l.mileage_km,
               'location', l.location_text,
               'image', case when jsonb_typeof(l.images) = 'array' then l.images->0 end,
               'level', m.level,
               'diff_pct', case when m.level = 'high' and jsonb_typeof(m.price_ref->'diff_pct') = 'number'
                                then m.price_ref->'diff_pct' end,
               'dealer_name', case when l.dealer_id is not null then public.dealer_public_name(l.dealer_id) end)) as car
        from public.matches m
        join public.search_profiles sp on sp.id = m.search_profile_id
        join public.listings l on l.id = m.listing_id
       where sp.id = p_search and sp.user_id = p_user
         and m.level in ('high', 'good', 'match')
         and l.status = 'active' and l.price is not null and not l.price_partial
         and public.free_result_allowed(p_user, m.listing_id)
         and not exists (select 1 from public.user_listing_interactions i
                          where i.user_id = p_user and i.listing_id = m.listing_id and i.status = 'discarded')
       order by 1
       limit greatest(coalesce(p_limit, 3), 0)) c
$$;

-- missed_car: 20261214120000's (with its strict color rule), plus the gate in
-- the candidates and dealer_name.
create or replace function public.missed_car(p_search bigint, p_ended timestamptz) returns jsonb
language sql stable security definer set search_path = '' as $$
  with sp as (
    select s.origin_lat, s.origin_lon, s.radius_km, coalesce(s.filters, '{}'::jsonb) as f
      from public.search_profiles s
     where s.id = p_search
  ),
  f as (
    select nullif(btrim(sp.f->>'make'), '')  as make,
           nullif(btrim(sp.f->>'model'), '') as model,
           case when sp.f->>'year_min' ~ '^\d+$' then (sp.f->>'year_min')::int end as year_min,
           case when sp.f->>'year_max' ~ '^\d+$' then (sp.f->>'year_max')::int end as year_max,
           case when jsonb_typeof(sp.f->'years') = 'array' and jsonb_array_length(sp.f->'years') > 0
                then array(select (y)::int from jsonb_array_elements_text(sp.f->'years') y where y ~ '^\d+$') end as years,
           case when sp.f->>'km_min' ~ '^\d+(\.\d+)?$' then (sp.f->>'km_min')::numeric end as km_min,
           case when sp.f->>'km_max' ~ '^\d+(\.\d+)?$' then (sp.f->>'km_max')::numeric end as km_max,
           case when sp.f->>'price_min' ~ '^\d+(\.\d+)?$' then (sp.f->>'price_min')::numeric end as price_min,
           case when sp.f->>'price_max' ~ '^\d+(\.\d+)?$' then (sp.f->>'price_max')::numeric end as price_max,
           upper(coalesce(nullif(sp.f->>'currency', ''),
                          case when coalesce(case when sp.f->>'price_max' ~ '^\d+(\.\d+)?$' then (sp.f->>'price_max')::numeric end,
                                             case when sp.f->>'price_min' ~ '^\d+(\.\d+)?$' then (sp.f->>'price_min')::numeric end,
                                             0) >= 1000000
                               then 'ARS' else 'USD' end)) as currency,
           nullif(sp.f->>'transmission', '') as transmission,
           nullif(sp.f->>'fuel', '')         as fuel,
           public.search_body_types(sp.f)    as body_types,
           public.search_colors(sp.f)        as colors,
           case when jsonb_typeof(sp.f->'trims') = 'array'
                then array(select lower(btrim(t)) from jsonb_array_elements_text(sp.f->'trims') t
                            where btrim(t) <> '') end as trims
      from sp
  ),
  fx as (
    select rate from public.fx_rates order by date desc, (kind = 'blue') desc limit 1
  ),
  -- The search's own place and the ones it adds, as matching's search_zones.
  zones as (
    select sp.origin_lat as lat, sp.origin_lon as lon, sp.radius_km::double precision as radius
      from sp
     where sp.radius_km > 0 and sp.origin_lat is not null and sp.origin_lon is not null
    union all
    select (e->>'lat')::double precision, (e->>'lon')::double precision, (e->>'radius_km')::double precision
      from sp, jsonb_array_elements(case when jsonb_typeof(sp.f->'extra_locations') = 'array'
                                         then sp.f->'extra_locations' else '[]'::jsonb end) e
     where e->>'lat' ~ '^\s*[-+]?\d+(\.\d+)?\s*$' and e->>'lon' ~ '^\s*[-+]?\d+(\.\d+)?\s*$'
       and e->>'radius_km' ~ '^\s*[-+]?\d+(\.\d+)?\s*$' and (e->>'radius_km')::double precision > 0
  ),
  cand as (
    select m.level, m.diff_pct, m.score, m.created_at, l.*,
           case
             when l.price is null or l.price <= 0 then null
             when upper(coalesce(l.currency, f.currency)) = f.currency then l.price
             when f.currency = 'USD' then coalesce(l.price_usd, l.price / nullif(fx.rate, 0))
             else l.price * fx.rate
           end as price_in_filter
      from public.expired_search_matches m
      join public.listings l on l.id = m.listing_id
     cross join f
      left join fx on true
     where m.search_profile_id = p_search and m.access_ended_at = p_ended
       and l.price is not null and not l.price_partial
       -- A car hidden from buyers (agencias §2) is not shown, even if it was
       -- counted while it was visible.
       and ((l.dealer_id is null and l.source <> 'directo')
            or public.dealer_listing_hidden(l.source, l.dealer_id, l.dealer_status, l.dealer_confirmed_at) is null)
  )
  select jsonb_strip_nulls(jsonb_build_object(
           'listing_id', c.id, 'title', c.title, 'make', c.make, 'model', c.model, 'trim', c.trim,
           'year', c.year, 'price', c.price, 'currency', c.currency, 'km', c.mileage_km,
           'location', c.location_text,
           'images', case when jsonb_typeof(c.images) = 'array'
                          then (select coalesce(jsonb_agg(i.value order by i.ord), '[]'::jsonb)
                                  from jsonb_array_elements(c.images) with ordinality i (value, ord)
                                 where i.ord <= 3) end,
           'below', c.level = 'high',
           'diff_pct', c.diff_pct,
           'gone', c.status = 'gone',
           'days_listed', case when c.status = 'gone' then greatest(1, ceil(extract(epoch from
                            c.last_seen_at - coalesce(c.published_at, c.first_seen_at)) / 86400)::int) end,
           'dealer_name', case when c.dealer_id is not null then public.dealer_public_name(c.dealer_id) end))
    from cand c
   cross join f
   where (f.make is null or lower(c.make) = lower(f.make))
     and (f.model is null or lower(c.model) = lower(f.model))
     -- A bound the search set needs the listing's value, inside it.
     and ((f.year_min is null and f.year_max is null and f.years is null)
          or (c.year is not null
              and (f.year_min is null or c.year >= f.year_min)
              and (f.year_max is null or c.year <= f.year_max)
              and (f.years is null or cardinality(f.years) = 0 or c.year = any (f.years))))
     and ((f.km_min is null and f.km_max is null)
          or (c.mileage_km is not null
              and (f.km_min is null or c.mileage_km >= f.km_min)
              and (f.km_max is null or c.mileage_km <= f.km_max)))
     and ((f.price_min is null and f.price_max is null)
          or (c.price_in_filter is not null
              and (f.price_min is null or c.price_in_filter >= f.price_min)
              and (f.price_max is null or c.price_in_filter <= f.price_max)))
     -- A car without a year can't be told apart from an older one.
     and c.year is not null
     -- Every word of one of the wanted trims, as matching.trim_matches; with no
     -- trim in the listing, the words of its title.
     and (f.trims is null or cardinality(f.trims) = 0
          or exists (select 1 from unnest(f.trims) t
                      where not exists (select 1 from regexp_split_to_table(replace(t, '!', ''), '\s+') w
                                         where w <> ''
                                           and not (w = any (regexp_split_to_array(
                                                     replace(lower(coalesce(c.trim, c.title, '')), '!', ''), '\s+'))))))
     and (f.transmission is null or c.transmission is null or c.transmission = f.transmission)
     and (f.fuel is null or c.fuel is null or position(lower(f.fuel) in lower(c.fuel)) > 0)
     and (f.body_types is null or c.body_type is null or c.body_type = any (f.body_types))
     -- Color, strict: the listing's own color, never a candidate from the photo.
     and (f.colors is null or c.color is null or c.color = any (f.colors))
     and (not exists (select 1 from zones)
          or (c.lat is not null and c.lon is not null
              and exists (select 1 from zones z where public.haversine_km(z.lat, z.lon, c.lat, c.lon) <= z.radius)))
     -- A believable opportunity: 5 % to 35 % under comparables, or level high without a number.
     and (c.diff_pct between 5 and 35 or (c.diff_pct is null and c.level = 'high'))
   order by c.level = 'high' desc, c.diff_pct desc nulls last, c.score desc nulls last,
            c.created_at desc, c.id desc
   limit 1
$$;

-- missed_since_expiry: 20261211120000's, without hidden listings in found or
-- below. The access end (ended) is a date, not cars: unchanged.
create or replace function public.missed_since_expiry() returns jsonb
language sql stable security definer set search_path = '' as $$
  with me as (
    select (select auth.uid()) as uid
  ), ended as (
    select max(m.access_ended_at) as at
      from public.expired_search_matches m
      join public.search_profiles sp on sp.id = m.search_profile_id
      join me on sp.user_id = me.uid
  )
  select jsonb_build_object('ended_at', max(e.at), 'found', count(distinct m.listing_id),
                            'below', count(distinct m.listing_id) filter (where m.level = 'high'))
    from me
    cross join ended e
    join public.search_profiles sp on sp.user_id = me.uid
    join public.expired_search_matches m on m.search_profile_id = sp.id and m.access_ended_at = e.at
    join public.listings l on l.id = m.listing_id
   where e.at is not null
     and public.plan_limits_for(me.uid)->>'state' = 'expired'
     and ((l.dealer_id is null and l.source <> 'directo')
          or public.dealer_listing_hidden(l.source, l.dealer_id, l.dealer_status, l.dealer_confirmed_at) is null)
  having count(*) > 0
$$;
revoke all on function public.missed_since_expiry() from public, anon;
grant execute on function public.missed_since_expiry() to authenticated;

-- ---------------------------------------------------------------------------
-- 10. Grants
-- ---------------------------------------------------------------------------

-- Everything new starts closed (Supabase grants new functions to anon and
-- authenticated by default).
revoke all on function
  public.dealer_json_number(jsonb),
  public.dealer_json_int(jsonb),
  public.dealer_program(),
  public.dealer_blue_rate(),
  public.dealer_listing_hidden(text, bigint, text, timestamptz),
  public.dealer_public_name(bigint),
  public.is_dealer_member(bigint),
  public.dealer_require_member(),
  public.dealer_profile_problem(text, text, double precision, double precision, text, text, text, text, jsonb),
  public.dealer_item_problem(jsonb),
  public.dealer_item_fields(jsonb),
  public.dealer_hide_listing(bigint),
  public.my_dealer(),
  public.create_dealer(text, text, double precision, double precision, text, text, text, text, jsonb),
  public.update_my_dealer(text, text, double precision, double precision, text, text, text, text, jsonb),
  public.dealer_add_source(text, text, text),
  public.dealer_upsert_item(bigint, jsonb),
  public.dealer_import_items(jsonb, text, text),
  public.dealer_set_item_status(bigint, text),
  public.dealer_confirm_items(bigint[]),
  public.dealer_resolve_duplicate(bigint, boolean),
  public.dealer_set_item_private(bigint, numeric, text, text),
  public.dealer_set_lead_status(bigint, text),
  public.dealer_market_ref(text, text, integer, numeric, bigint),
  public.dealer_model_days_to_sell(text, text, integer),
  public.dealer_demand(text, text, integer, numeric, text, integer, double precision, double precision, uuid[], text),
  public.dealer_demand_level(jsonb, integer),
  public.dealer_stock_insights(),
  public.dealer_market_listings(bigint),
  public.request_dealer_contact(bigint, text, text, text, boolean, text, bigint),
  public.listing_dealer_card(bigint),
  public.dealer_badges(bigint[]),
  public.dealer_sweep(),
  public.admin_dealer_seller_candidates(text, text)
  from public, anon, authenticated;

-- Read by match_cards (security invoker) and the web, signed in or not.
grant execute on function
  public.dealer_program(),
  public.dealer_listing_hidden(text, bigint, text, timestamptz),
  public.dealer_public_name(bigint)
  to anon, authenticated, service_role;

-- The agency's panel and the buyer's side.
grant execute on function
  public.is_dealer_member(bigint),
  public.my_dealer(),
  public.create_dealer(text, text, double precision, double precision, text, text, text, text, jsonb),
  public.update_my_dealer(text, text, double precision, double precision, text, text, text, text, jsonb),
  public.dealer_add_source(text, text, text),
  public.dealer_upsert_item(bigint, jsonb),
  public.dealer_import_items(jsonb, text, text),
  public.dealer_set_item_status(bigint, text),
  public.dealer_confirm_items(bigint[]),
  public.dealer_resolve_duplicate(bigint, boolean),
  public.dealer_set_item_private(bigint, numeric, text, text),
  public.dealer_set_lead_status(bigint, text),
  public.dealer_stock_insights(),
  public.dealer_market_listings(bigint),
  public.request_dealer_contact(bigint, text, text, text, boolean, text, bigint),
  public.listing_dealer_card(bigint),
  public.dealer_badges(bigint[])
  to authenticated, service_role;

-- Worker and /admin only.
grant execute on function
  public.dealer_json_number(jsonb),
  public.dealer_json_int(jsonb),
  public.dealer_blue_rate(),
  public.dealer_require_member(),
  public.dealer_profile_problem(text, text, double precision, double precision, text, text, text, text, jsonb),
  public.dealer_item_problem(jsonb),
  public.dealer_item_fields(jsonb),
  public.dealer_hide_listing(bigint),
  public.dealer_market_ref(text, text, integer, numeric, bigint),
  public.dealer_model_days_to_sell(text, text, integer),
  public.dealer_demand(text, text, integer, numeric, text, integer, double precision, double precision, uuid[], text),
  public.dealer_demand_level(jsonb, integer),
  public.dealer_sweep(),
  public.admin_dealer_seller_candidates(text, text)
  to service_role;

comment on function public.dealer_program() is
  'app_config.dealer_program sanitized: enabled, channel_enabled (booleans, default false), manual_confirm_days '
  '(1-60, default 7), demand_min_count (3-50, default 3).';
comment on function public.dealer_listing_hidden(text, bigint, text, timestamptz) is
  'The send gate (agencias §2): no_dealer, channel_off, not_approved, not_available, unconfirmed, or null when the '
  'listing may reach buyers. Null at once for a listing without dealer_id that is not ''directo''.';
comment on function public.dealer_demand(text, text, integer, numeric, text, integer, double precision, double precision, uuid[], text) is
  'Raw demand for a car (searches and distinct people per nested level). Service role only: clients get it rounded '
  'by dealer_stock_insights (dealer_demand_level).';
comment on function public.dealer_sweep() is
  'Worker, every DEALER_TICK_SECONDS: matches, expired_search_matches and queued/digest notifications of every '
  'dealer or ''directo'' listing the gate hides. Returns what it removed.';

-- ---------------------------------------------------------------------------
-- Photos of the agency's own stock (Storage)
-- ---------------------------------------------------------------------------
-- Bucket dealer-photos, public to read (the photos go out in listings.images to
-- buyers, like any portal's), written only by a member under <dealer_id>/…
-- The web shrinks each photo before uploading; 5 MB is the hard ceiling.
-- dealer_stock_items.images keeps the public URLs (https; http only for the
-- local stack), so the worker and the buyer's pages read them as before.
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('dealer-photos', 'dealer-photos', true, 5242880, array['image/jpeg', 'image/png', 'image/webp'])
on conflict (id) do nothing;

create function public.dealer_photo_path_mine(p_name text) returns boolean
language sql stable security definer set search_path = '' as $$
  select (public.dealer_program() ->> 'enabled')::boolean
     and exists (select 1 from public.dealer_members m
                  where m.user_id = (select auth.uid())
                    and m.dealer_id::text = split_part(p_name, '/', 1))
$$;
revoke all on function public.dealer_photo_path_mine(text) from public, anon;
grant execute on function public.dealer_photo_path_mine(text) to authenticated, service_role;

create policy "dealer photos: member uploads" on storage.objects for insert to authenticated
  with check (bucket_id = 'dealer-photos' and public.dealer_photo_path_mine(name));
create policy "dealer photos: member deletes" on storage.objects for delete to authenticated
  using (bucket_id = 'dealer-photos' and public.dealer_photo_path_mine(name));

notify pgrst, 'reload schema';

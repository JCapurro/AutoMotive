-- Core schema for the Automotive MVP (docs/TECHNICAL_PLAN.md, sección 4).
--
-- Conventions:
--   * every timestamp is timestamptz (UTC); the UI renders America/Argentina/Buenos_Aires;
--   * domain ids are bigint identity, users are the uuid from auth.users;
--   * the worker connects with a privileged role and bypasses RLS; clients go through
--     the policies in the next migration.

-- ---------------------------------------------------------------------------
-- Enums
-- ---------------------------------------------------------------------------

create type public.listing_status       as enum ('active', 'gone');
create type public.match_level          as enum ('high', 'good', 'match', 'low');
create type public.notify_frequency     as enum ('immediate', 'daily');
create type public.interaction_status   as enum ('new', 'seen', 'interested', 'discarded',
                                                 'contacted', 'visit_scheduled', 'purchased');
create type public.rejection_reason     as enum ('too_expensive', 'too_many_km', 'wrong_trim', 'location',
                                                 'automatic', 'seller', 'apparent_condition',
                                                 'documentation', 'other');
create type public.user_plan            as enum ('free', 'pro', 'pass');
create type public.user_role            as enum ('user', 'admin');
create type public.notification_kind    as enum ('new_match', 'opportunity', 'price_drop', 'listing_gone');
create type public.notification_channel as enum ('telegram', 'email', 'web', 'push');
create type public.notification_status  as enum ('queued', 'digest', 'sent', 'failed', 'skipped');
create type public.llm_job_status       as enum ('queued', 'running', 'done', 'failed');
create type public.run_status           as enum ('running', 'ok', 'failed');
-- §38: "¿Automotive influyó en que encontraras este vehículo?" mucho / algo / poco / no.
create type public.purchase_influence   as enum ('a_lot', 'some', 'little', 'none');

-- ---------------------------------------------------------------------------
-- Helpers
-- ---------------------------------------------------------------------------

create function public.set_updated_at() returns trigger
language plpgsql
set search_path = ''
as $$
begin
  new.updated_at := now();
  return new;
end;
$$;

-- ---------------------------------------------------------------------------
-- Users
-- ---------------------------------------------------------------------------

create table public.profiles (
  id                   uuid primary key references auth.users (id) on delete cascade,
  email                text,
  phone                text,
  telegram_chat_id     bigint,
  -- Deep link code for t.me/<bot>?start=<code>; the bot rotates it after linking.
  telegram_link_code   text not null unique default replace(gen_random_uuid()::text, '-', ''),
  plan                 public.user_plan not null default 'free',
  plan_expires_at      timestamptz,
  role                 public.user_role not null default 'user',
  default_origin_lat   double precision check (default_origin_lat between -90 and 90),
  default_origin_lon   double precision check (default_origin_lon between -180 and 180),
  default_origin_label text,
  created_at           timestamptz not null default now(),
  updated_at           timestamptz not null default now()
);
create index profiles_telegram_chat_id_idx on public.profiles (telegram_chat_id);
create trigger profiles_set_updated_at before update on public.profiles
  for each row execute function public.set_updated_at();

-- Every auth user gets a profile row, whatever created it (magic link, admin API, worker).
create function public.handle_new_user() returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  insert into public.profiles (id, email, phone)
  values (new.id, new.email, new.phone)
  on conflict (id) do nothing;
  return new;
end;
$$;
create trigger on_auth_user_created after insert on auth.users
  for each row execute function public.handle_new_user();

-- ---------------------------------------------------------------------------
-- Sources and catalog
-- ---------------------------------------------------------------------------

create table public.sources (
  id                     text primary key,
  name                   text not null,
  enabled                boolean not null default true,
  crawl_interval_seconds integer not null check (crawl_interval_seconds > 0),
  priority               smallint not null default 100,
  last_ok_at             timestamptz,
  consecutive_failures   integer not null default 0,
  created_at             timestamptz not null default now(),
  updated_at             timestamptz not null default now()
);
create trigger sources_set_updated_at before update on public.sources
  for each row execute function public.set_updated_at();

-- VehicleDefinition (§40). One row per (make, model, trim); trim null = model-level row.
-- aliases are lowercase alternative spellings of the model ("gol trend", "up!").
create table public.vehicle_catalog (
  id            bigint generated always as identity primary key,
  make          text not null,
  model         text not null,
  trim          text,
  aliases       text[] not null default '{}',
  year_from     integer,
  year_to       integer,
  transmissions text[] not null default '{}',
  fuels         text[] not null default '{}',
  created_at    timestamptz not null default now(),
  constraint vehicle_catalog_years check (year_to is null or year_from is null or year_to >= year_from),
  constraint vehicle_catalog_unique unique nulls not distinct (make, model, trim)
);
create index vehicle_catalog_make_model_idx on public.vehicle_catalog (lower(make), lower(model));
create index vehicle_catalog_aliases_idx on public.vehicle_catalog using gin (aliases);

-- ---------------------------------------------------------------------------
-- Search profiles and crawl targets
-- ---------------------------------------------------------------------------

create table public.search_profiles (
  id                     bigint generated always as identity primary key,
  user_id                uuid not null references public.profiles (id) on delete cascade,
  name                   text not null,
  filters                jsonb not null check (jsonb_typeof(filters) = 'object'),
  preferences            jsonb not null default '{}' check (jsonb_typeof(preferences) = 'object'),
  raw_query              text,
  origin_lat             double precision check (origin_lat between -90 and 90),
  origin_lon             double precision check (origin_lon between -180 and 180),
  radius_km              real check (radius_km > 0),
  notification_frequency public.notify_frequency not null default 'immediate',
  notify_min_level       public.match_level not null default 'good',
  channels               text[] not null default '{telegram,web}',
  enabled                boolean not null default true,
  bootstrapped_at        timestamptz,
  rematch_requested_at   timestamptz,
  created_at             timestamptz not null default now(),
  updated_at             timestamptz not null default now()
);
create index search_profiles_user_id_idx on public.search_profiles (user_id);
create index search_profiles_enabled_idx on public.search_profiles (id) where enabled;
create trigger search_profiles_set_updated_at before update on public.search_profiles
  for each row execute function public.set_updated_at();

-- Profiles grouped by (source, make, model) with the widest query (sección 5.1).
create table public.crawl_targets (
  id             bigint generated always as identity primary key,
  source         text not null references public.sources (id),
  make           text,
  model          text,
  query          jsonb not null default '{}',
  last_run_at    timestamptz,
  next_run_at    timestamptz,
  active         boolean not null default true,
  first_run_done boolean not null default false,
  created_at     timestamptz not null default now(),
  updated_at     timestamptz not null default now(),
  constraint crawl_targets_unique unique nulls not distinct (source, make, model)
);
create index crawl_targets_due_idx on public.crawl_targets (next_run_at) where active;
create trigger crawl_targets_set_updated_at before update on public.crawl_targets
  for each row execute function public.set_updated_at();

-- ---------------------------------------------------------------------------
-- Listings
-- ---------------------------------------------------------------------------

create table public.listings (
  id                       bigint generated always as identity primary key,
  source                   text not null references public.sources (id),
  external_id              text not null,
  url                      text not null,
  title                    text not null,
  description              text,
  make                     text,
  model                    text,
  trim                     text,
  year                     integer,
  price                    numeric,
  currency                 text check (currency in ('USD', 'ARS')),
  price_usd                numeric,
  mileage_km               integer,
  transmission             text check (transmission in ('manual', 'automatic')),
  fuel                     text,
  location_text            text,
  lat                      double precision,
  lon                      double precision,
  seller_name              text,
  seller_type              text check (seller_type in ('private', 'dealer')),
  images                   jsonb not null default '[]',
  attributes               jsonb not null default '{}',
  published_at             timestamptz,
  first_seen_at            timestamptz not null default now(),
  last_seen_at             timestamptz not null default now(),
  status                   public.listing_status not null default 'active',
  price_partial            boolean not null default false,
  price_partial_reason     text,
  normalization_confidence real,
  fingerprint              text,
  probable_repost_of       bigint references public.listings (id) on delete set null,
  enriched_at              timestamptz,
  unique (source, external_id)
);
create index listings_make_model_year_idx on public.listings (make, model, year);
create index listings_fingerprint_idx on public.listings (fingerprint);
create index listings_first_seen_at_idx on public.listings (first_seen_at desc);
create index listings_probable_repost_of_idx on public.listings (probable_repost_of)
  where probable_repost_of is not null;

-- One row only when something changes (sección 5.3).
create table public.listing_snapshots (
  id          bigint generated always as identity primary key,
  listing_id  bigint not null references public.listings (id) on delete cascade,
  observed_at timestamptz not null default now(),
  price       numeric,
  currency    text,
  price_usd   numeric,
  fx_rate     numeric,
  mileage_km  integer,
  attrs_hash  text not null,
  change_kind text not null
    check (change_kind in ('new', 'price', 'mileage', 'description', 'images', 'attrs'))
);
create index listing_snapshots_listing_idx on public.listing_snapshots (listing_id, observed_at desc);

-- ---------------------------------------------------------------------------
-- Matches, interactions, owned vehicles
-- ---------------------------------------------------------------------------

create table public.matches (
  id                bigint generated always as identity primary key,
  search_profile_id bigint not null references public.search_profiles (id) on delete cascade,
  listing_id        bigint not null references public.listings (id) on delete cascade,
  score             smallint not null check (score between 0 and 100),
  level             public.match_level not null,
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
create index matches_profile_score_idx on public.matches (search_profile_id, score desc, generated_at desc);
create index matches_listing_id_idx on public.matches (listing_id);
create trigger matches_set_updated_at before update on public.matches
  for each row execute function public.set_updated_at();

create table public.user_listing_interactions (
  user_id          uuid not null references public.profiles (id) on delete cascade,
  listing_id       bigint not null references public.listings (id) on delete cascade,
  status           public.interaction_status not null default 'new',
  saved            boolean not null default false,
  rejection_reason public.rejection_reason,
  note             text,
  updated_at       timestamptz not null default now(),
  primary key (user_id, listing_id)
);
create index user_listing_interactions_listing_idx on public.user_listing_interactions (listing_id);
create trigger user_listing_interactions_set_updated_at before update on public.user_listing_interactions
  for each row execute function public.set_updated_at();

-- OwnedVehicle (§39): kept even if the listing disappears, so the vehicle is snapshotted.
create table public.owned_vehicles (
  id                   bigint generated always as identity primary key,
  user_id              uuid not null references public.profiles (id) on delete cascade,
  listing_id           bigint references public.listings (id) on delete set null,
  search_profile_id    bigint references public.search_profiles (id) on delete set null,
  vehicle              jsonb not null default '{}',
  purchase_price       numeric,
  purchase_currency    text check (purchase_currency in ('USD', 'ARS')),
  purchase_date        date,
  automotive_influence public.purchase_influence,
  created_at           timestamptz not null default now(),
  updated_at           timestamptz not null default now()
);
create index owned_vehicles_user_id_idx on public.owned_vehicles (user_id);
create index owned_vehicles_listing_id_idx on public.owned_vehicles (listing_id);
create index owned_vehicles_search_profile_id_idx on public.owned_vehicles (search_profile_id);
create trigger owned_vehicles_set_updated_at before update on public.owned_vehicles
  for each row execute function public.set_updated_at();

-- ---------------------------------------------------------------------------
-- Notifications, events, LLM jobs
-- ---------------------------------------------------------------------------

create table public.notifications (
  id         bigint generated always as identity primary key,
  user_id    uuid not null references public.profiles (id) on delete cascade,
  match_id   bigint references public.matches (id) on delete set null,
  listing_id bigint references public.listings (id) on delete set null,
  kind       public.notification_kind not null,
  channel    public.notification_channel not null,
  status     public.notification_status not null default 'queued',
  -- kind:listing_id[:snapshot_id] — the same listing never alerts twice for the same reason (§15).
  dedupe_key text not null,
  payload    jsonb not null default '{}',
  error      text,
  created_at timestamptz not null default now(),
  sent_at    timestamptz,
  opened_at  timestamptz,
  clicked_at timestamptz,
  unique (user_id, dedupe_key)
);
create index notifications_user_created_idx on public.notifications (user_id, created_at desc);
create index notifications_match_id_idx on public.notifications (match_id);
create index notifications_listing_id_idx on public.notifications (listing_id);
create index notifications_pending_idx on public.notifications (created_at) where status = 'queued';

create table public.events (
  id         bigint generated always as identity primary key,
  user_id    uuid references public.profiles (id) on delete cascade,
  name       text not null,
  props      jsonb not null default '{}',
  created_at timestamptz not null default now()
);
create index events_name_created_idx on public.events (name, created_at desc);
create index events_user_created_idx on public.events (user_id, created_at desc);

create table public.llm_jobs (
  id          bigint generated always as identity primary key,
  user_id     uuid not null default auth.uid() references public.profiles (id) on delete cascade,
  kind        text not null check (kind in ('parse_search', 'extract_listing_facts', 'polish_questions')),
  input       jsonb not null,
  output      jsonb,
  status      public.llm_job_status not null default 'queued',
  error       text,
  provider    text,
  latency_ms  integer,
  created_at  timestamptz not null default now(),
  started_at  timestamptz,
  finished_at timestamptz
);
create index llm_jobs_user_id_idx on public.llm_jobs (user_id);
create index llm_jobs_queue_idx on public.llm_jobs (created_at) where status = 'queued';

-- ---------------------------------------------------------------------------
-- Observability and configuration
-- ---------------------------------------------------------------------------

create table public.collector_runs (
  id          bigint generated always as identity primary key,
  source      text not null references public.sources (id),
  target_id   bigint references public.crawl_targets (id) on delete set null,
  started_at  timestamptz not null default now(),
  finished_at timestamptz,
  status      public.run_status not null default 'running',
  found       integer,
  new         integer,
  updated     integer,
  error       text
);
create index collector_runs_source_started_idx on public.collector_runs (source, started_at desc);
create index collector_runs_target_id_idx on public.collector_runs (target_id);

create table public.pipeline_errors (
  id         bigint generated always as identity primary key,
  stage      text not null,
  ref        text,
  error      text not null,
  created_at timestamptz not null default now()
);
create index pipeline_errors_stage_created_idx on public.pipeline_errors (stage, created_at desc);

create table public.app_config (
  key        text primary key,
  value      jsonb not null,
  updated_at timestamptz not null default now()
);
create trigger app_config_set_updated_at before update on public.app_config
  for each row execute function public.set_updated_at();

create table public.geocode_cache (
  query      text primary key,
  lat        double precision not null,
  lon        double precision not null,
  source     text not null,
  not_found  boolean not null default false,
  updated_at timestamptz not null default now()
);

-- Daily USD/ARS quote (blue and oficial), frozen so price_usd can be reproduced.
create table public.fx_rates (
  date       date not null,
  kind       text not null check (kind in ('blue', 'oficial')),
  rate       numeric not null check (rate > 0),
  source     text,
  fetched_at timestamptz not null default now(),
  primary key (date, kind)
);

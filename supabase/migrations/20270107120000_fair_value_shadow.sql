-- «Valor justo» per model, SHADOW mode (docs/superpowers/specs/2026-11-20-valor-justo-design.md §4, §9).
--
-- A per-model price curve (year level + trim premium + transmission premium + km slope) fitted once a day
-- by the worker (pipeline/fair_value.py) and stored here. The scorer computes, next to today's reference,
-- what the listing is worth by that curve and stores it in matches.score_breakdown.shadow_fair_value: no
-- score, level, alert, email or page changes (f2 keeps deciding with comparables()). No SCORING_VERSION bump.
--
--   * public.price_pool(make, model): the listings of a model that can be someone's comparable today, the
--     rules of comparable_listings() that do not depend on the listing being compared (§4.1). Neither
--     comparable_listings() nor comparables() changes.
--   * public.model_price_curves: one row per model, overwritten by every run (§4.2).
--   * public.fair_value_runs: one row per run, the history; the job purges runs older than 90 days.
--   * app_config.fair_value with mode 'shadow' (the code default is 'off', §9).
--
-- Rollback without a deploy: fair_value.mode = 'off' (the worker stops fitting and computing within its
-- config cache). The tables and what was stored stay.
--
-- Size: ~90 curve rows of a few KB; ~30 KB per run, 90 days kept (~3 MB).
set local lock_timeout = '5s';

-- ---------------------------------------------------------------------------
-- The pool
-- ---------------------------------------------------------------------------

-- comparable_listings()'s rules (20261228120000_dealer_program.sql) that do not depend on the target:
-- same make and model (lower() on both sides), no 'directo', price_usd > 0, no price_partial, seen within
-- max_age_days, active or gone for less than gone_max_age_days (no limit without the key), not
-- «unconfirmed» (confirm_sources + listing_unconfirmed), and a repost counts only while its original does
-- not. Left to the caller, as they are the target's: not the listing itself nor a repost of it, the year
-- window (none without a year) and the km window (a comparable without km passes; none without km).
-- supabase/tests/fair_value_test.sql pins that equivalence. The price floor of comparables() is not
-- copied: the fit trims with its own band (spec §3.2 step 2).
create or replace function public.price_pool(p_make text, p_model text)
returns table (id bigint, probable_repost_of bigint, year integer, "trim" text, transmission text,
               mileage_km integer, price_usd numeric)
language sql
stable
as $$
  with cfg as materialized (
    select coalesce((c.value->>'max_age_days')::integer, 30) as max_age_days,
           (c.value->>'gone_max_age_days')::integer         as gone_days,
           coalesce(c.value->'confirm_sources', '[]'::jsonb)  as confirm_sources,
           coalesce((c.value->>'confirm_grace_hours')::numeric, 36) * interval '1 hour' as grace
      from (select 1) as one
      left join public.app_config c on c.key = 'comparables'
  )
  select o.id, o.probable_repost_of, o.year, o.trim, o.transmission, o.mileage_km, o.price_usd
    from public.listings o
   cross join cfg
   where p_make is not null and p_model is not null
     and lower(o.make) = lower(p_make) and lower(o.model) = lower(p_model)
     and o.source <> 'directo'
     and o.price_usd > 0
     and not o.price_partial
     and o.last_seen_at >= now() - make_interval(days => cfg.max_age_days)
     and (o.status = 'active' or cfg.gone_days is null
          or o.last_seen_at >= now() - make_interval(days => cfg.gone_days))
     and not (cfg.confirm_sources ? o.source
              and exists (select 1 from public.listing_unconfirmed(
                            o.source, o.make, o.model, o.year, o.mileage_km,
                            greatest(o.last_seen_at, o.last_full_seen_at), cfg.confirm_sources, cfg.grace)))
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

comment on function public.price_pool(text, text) is
  'Valor justo (spec 2026-11-20 §4.1): the listings of a model that can be a comparable today, '
  'comparable_listings() without the rules of the target (itself, its reposts, the year and km windows). '
  'Read by the worker''s fair value job.';

-- Supabase grants execute on new functions to everyone: only the worker reads it, as comparables().
revoke execute on function public.price_pool(text, text) from public, anon, authenticated;
grant execute on function public.price_pool(text, text) to service_role;

-- ---------------------------------------------------------------------------
-- The curves and the runs
-- ---------------------------------------------------------------------------

create table if not exists public.fair_value_runs (
  id             bigint generated always as identity primary key,
  started_at     timestamptz not null default now(),
  finished_at    timestamptz,
  status         text not null default 'running' check (status in ('running', 'ok', 'failed')),
  trigger        text not null check (trigger in ('schedule', 'catchup', 'cli')),
  params         jsonb,
  params_hash    text,
  models_seen    integer,
  models_fitted  integer,
  models_enabled integer,
  error          text,
  stats          jsonb
);
create index if not exists fair_value_runs_started_idx on public.fair_value_runs (started_at);

comment on table public.fair_value_runs is
  'Valor justo (spec 2026-11-20 §4.2): each run of the daily fit (worker: pipeline/fair_value.py). '
  'stats = per model n, cv_err, cohort_err, enabled, km_slope, the year levels and guard_flips. '
  'The job deletes runs older than 90 days.';

create table if not exists public.model_price_curves (
  make        text not null,
  model       text not null,
  curve       jsonb not null,
  n           integer not null,
  cv_err      real,
  cohort_err  real,
  enabled     boolean not null default false,
  params_hash text not null,
  fitted_at   timestamptz not null default now(),
  run_id      bigint,
  primary key (make, model),
  check (make = lower(make) and model = lower(model))
);

comment on table public.model_price_curves is
  'Valor justo (spec 2026-11-20 §3, §4.2): the price curve of each model, overwritten by every run. '
  'curve = years {year: {a, n, km}}, trims {trim: {g, n}}, transmissions {transmission: {h, n}}, km_slope, '
  'resid {q25, q75}. enabled = the fit beats today''s model-level reference on the cross-validation (§3.5).';
comment on column public.model_price_curves.cv_err is
  'Median |ln(price / fair value)| over 5 folds (id % 5), on up to cohort_sample listings.';
comment on column public.model_price_curves.cohort_err is
  'Median |ln(price / model-level median)| of today''s rules (year ±year_tol, km ±km_tol_pct, floor_of_p75) on the same listings.';

-- Only the worker (a privileged role, outside RLS) reads and writes them: RLS on and no policy. Supabase's
-- default privileges grant ALL on new public tables to anon, authenticated and service_role: revoke them.
alter table public.model_price_curves enable row level security;
alter table public.fair_value_runs    enable row level security;
revoke all on public.model_price_curves, public.fair_value_runs from public, anon, authenticated, service_role;
grant select, insert, update, delete on public.model_price_curves, public.fair_value_runs to service_role;
revoke all on sequence public.fair_value_runs_id_seq from public, anon, authenticated, service_role;
grant usage, select on sequence public.fair_value_runs_id_seq to service_role;

-- ---------------------------------------------------------------------------
-- app_config.fair_value: worker/intelligence/config.DEFAULT_FAIR_VALUE with mode 'shadow' (the code
-- default is 'off'). Bounds: web/lib/admin-config.ts and intelligence/config.fair_value_config.
-- Keep it ONE json literal: worker/tests/test_fair_value_migration_defaults.py reads it from this file.
-- Not in seed.sql: seed runs after the migrations with on conflict do nothing.
-- ---------------------------------------------------------------------------

insert into public.app_config (key, value) values ('fair_value', '{
  "mode": "shadow", "min_listings": 150, "min_year_n": 8, "min_trim_n": 15,
  "price_trim": {"low": 0.45, "high": 2.2}, "km_range": {"min": 5000, "max": 400000},
  "km_slope_min": -0.35, "max_passes": 4, "cohort_sample": 300,
  "disable_margin": 1.05, "schedule": {"hour": "03:30"}
}'::jsonb)
on conflict (key) do nothing;

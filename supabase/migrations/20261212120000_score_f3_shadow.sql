-- f3 «precio × encaje», shadow mode (docs/superpowers/specs/2026-11-08-recalibracion-score-design.md
-- §4.4, §8, §11). f2 (SCORING_VERSION f2-v5-seller-margin) keeps deciding every score, level, alert,
-- digest and email. The worker computes f3 next to it and stores it in two places:
--   * matches.score_breakdown.shadow_f3: the current view, overwritten by every re-score (no schema change);
--   * public.match_decisions (below): one row per fresh alert candidate and phase, never updated.
-- And app_config.score_model_f3, the only key f3 reads, here with mode 'shadow' and the spec's parameters
-- (§14 «Parámetros»; the pending decisions of §14 run with the recommended option, behind rules.*).
--
-- Rollback without a deploy: score_model_f3.mode = 'off' (the worker stops computing and logging f3 within
-- its 60 s config cache). match_decisions stays (§12).
--
-- Retention: ~180 card + ~150 deferred + a few sweeper rows a day at ~4 KB each, ~1.5 MB/day: ~20 MB over the
-- 14-day shadow, ~0.5 GB/year if left on. Nothing purges it by age. Keep it through the shadow and the 7-day live
-- follow-up (§11.6); then purge with a migration (alter table … disable trigger match_decisions_insert_only;
-- delete … where decided_at < …; enable trigger), or truncate it.
--
-- Privacy: «Borrar mi cuenta» (web/app/privacidad: «eliminamos tu email, tus búsquedas, alertas y todo tu
-- historial») takes the account's rows too. Every other per-user table goes with auth.users by an on delete
-- cascade; this one has no foreign keys, so a trigger on auth.users purges them first (below), whatever
-- deletes the user (delete_my_account, the admin API, the dashboard). Insert-only still holds for everything
-- else: that purge is the one delete the trigger lets through.
--
-- Live only, NOT here: matches.decision_pending_at, app_config.alerts.defer_seller_pref.
set local lock_timeout = '5s';

-- ---------------------------------------------------------------------------
-- The decision log
-- ---------------------------------------------------------------------------

create table if not exists public.match_decisions (
  id                bigint generated always as identity primary key,
  -- No foreign keys on purpose: a cascade or a set null from matches, listings or search_profiles would be
  -- an UPDATE or DELETE here, which the insert-only trigger refuses, and it would then block deleting a match
  -- (a re-score of a listing that no longer fits), a listing (retention) or a search (the user). An account
  -- deletion purges its rows through match_decisions_purge_account (below).
  match_id          bigint not null,
  search_profile_id bigint not null,
  listing_id        bigint not null,
  user_id           uuid,
  model             text not null check (model in ('f2', 'f3')),
  phase             text not null check (phase in ('card', 'deferred', 'sweeper')),
  decided_at        timestamptz not null default now(),
  f3_decides        boolean not null,
  -- f2: what it decided (card), or its current view (deferred, sweeper: f2 never re-decides)
  f2_version        text not null,
  f2_score          smallint check (f2_score between 0 and 100),
  f2_level          text check (f2_level in ('high', 'good', 'match', 'low')),
  f2_decision       text check (f2_decision in ('queued', 'digest', 'none')),
  f2_kind           text check (f2_kind in ('opportunity', 'new_match')),
  f2_reason         text,
  f2_breakdown      jsonb,
  red_flags         text[] not null default '{}',
  -- f3: hypothetical during the shadow
  f3_version        text,
  f3_params         text,
  f3_score          smallint check (f3_score between 0 and 100),
  f3_level          text check (f3_level in ('high', 'good', 'match', 'low', 'excluded')),
  f3_level_uncapped text check (f3_level_uncapped in ('high', 'good', 'match', 'low', 'excluded')),
  f3_decision       text check (f3_decision in ('queued', 'digest', 'none')),
  f3_kind           text check (f3_kind in ('opportunity', 'new_match')),
  f3_reason         text,
  f3_deal_raw       real,
  f3_r              real,
  f3_deal           real,
  f3_d              real,
  f3_d_eff          real,
  f3_fit_level      real,
  f3_fit_score      real,
  f3_flags          text[] not null default '{}',
  f3_a_verificar    text[] not null default '{}',
  f3_seller_capped  boolean,
  agency_voice      text,
  placeholder       boolean,
  would_defer       boolean,
  f3                jsonb,
  -- what was known when deciding
  price_ref         jsonb,
  price             numeric,
  currency          text,
  price_usd         numeric,
  price_partial     boolean,
  title             text,
  source            text,
  year              smallint,
  seller_type       text,
  dealer_inferred   boolean,
  enriched          boolean,
  listing_status    text,
  audience          jsonb,
  -- A retried batch, a second enrichment or a second sweep never adds a row.
  constraint match_decisions_once unique (match_id, model, phase)
);

create index if not exists match_decisions_listing_idx on public.match_decisions (listing_id, decided_at);
create index if not exists match_decisions_profile_idx on public.match_decisions (search_profile_id, decided_at);
-- The account purge (by user_id; the searches go through the index above).
create index if not exists match_decisions_user_idx on public.match_decisions (user_id) where user_id is not null;
-- The 1-minute sweeper: card rows that wait for the detail.
create index if not exists match_decisions_sweep_idx on public.match_decisions (decided_at)
  where phase = 'card' and would_defer;

comment on table public.match_decisions is
  'Insert-only log of alert decisions (score recalibration f3, spec 2026-11-08 §4.4): one row per fresh alert '
  'candidate per (model, phase). model = the formula that decides (shadow: f2). phase card = Notifier.on_matches; '
  'deferred = after the enrichment re-score; sweeper = 20 min later for those still waiting for the detail. '
  'Read by worker/tools/shadow_report.py. No foreign keys and no updates: rows outlive their match, listing and search. '
  'Deleting the account (auth.users) purges its rows (match_decisions_purge_account).';
comment on column public.match_decisions.f3_decides is
  'Whether this row is f3''s decision in live semantics: the card row unless would_defer; then the first '
  'deferred or sweeper row.';
comment on column public.match_decisions.f2_decision is
  'queued | digest | none: what f2 actually did (card). Null on deferred and sweeper rows (f2 decides at the card only).';
comment on column public.match_decisions.f2_reason is
  'Why: threshold, daily_cap, frequency, threshold_not_reached, discarded, backfill, no_level, below_min_level, '
  'dedupe_existing, dedupe_batch, no_channels, no_audience, hidden_trial; f2_card_only on later phases.';
comment on column public.match_decisions.f2_breakdown is 'matches.score_breakdown at decision time, without shadow_f3.';
comment on column public.match_decisions.f3_decision is
  'queued | digest | none: engine.classify with the f3 level and score (no daily cap, no batch dedupe).';
comment on column public.match_decisions.f3 is
  'The whole score_breakdown.shadow_f3 at decision time, alternatives included (recompute offline from it).';
comment on column public.match_decisions.f3_params is 'Hash of score_model_f3 (deal, fit, levels, rules): a change restarts the measurement.';
comment on column public.match_decisions.price_ref is 'Decision-time reference: n, level_used, median, p25, p75, diff_pct.';
comment on column public.match_decisions.audience is
  'The search''s alert settings at decision time (min_level, frequency, threshold_pct, threshold_usd, channels, ...).';

create or replace function public.match_decisions_insert_only() returns trigger
language plpgsql set search_path = '' as $$
begin
  -- The one delete that goes through: the account purge (match_decisions_purge_account, a trigger on
  -- auth.users), which turns this transaction-local flag on around its own statement. Never an update.
  if tg_op = 'DELETE' and pg_trigger_depth() > 1
     and current_setting('app.match_decisions_purge', true) = 'on' then
    return old;
  end if;
  raise exception 'match_decisions is insert-only' using errcode = 'P0001';
end $$;
revoke all on function public.match_decisions_insert_only() from public, anon, authenticated, service_role;

-- TRUNCATE is not blocked: the DB tests reset with it, and a purge goes through a migration.
create or replace trigger match_decisions_insert_only before update or delete on public.match_decisions
  for each row execute function public.match_decisions_insert_only();

-- ---------------------------------------------------------------------------
-- Account deletion: the account's rows go with it
-- ---------------------------------------------------------------------------

-- Before the user row goes (its searches still exist then): the rows with its user_id, and those of its
-- searches (a candidate without an audience has no user_id). A search deleted on its own keeps its rows,
-- as its notifications do (their search_profile_id is set null); the account's deletion then takes them by
-- user_id. Rows without a user_id of a search deleted earlier name no one: no user, no audience.
create or replace function public.match_decisions_purge_account() returns trigger
language plpgsql security definer set search_path = '' as $$
begin
  perform set_config('app.match_decisions_purge', 'on', true);
  delete from public.match_decisions d
   where d.user_id = old.id
      or d.search_profile_id in (select p.id from public.search_profiles p where p.user_id = old.id);
  perform set_config('app.match_decisions_purge', 'off', true);
  return old;
end $$;
revoke all on function public.match_decisions_purge_account() from public, anon, authenticated, service_role;

create or replace trigger match_decisions_purge_account before delete on auth.users
  for each row execute function public.match_decisions_purge_account();

-- Only the worker (a privileged role, outside RLS) writes and reads it: RLS on and no policy. Supabase's
-- default privileges grant ALL on new public tables to anon, authenticated and service_role: revoke them,
-- then give the API's service role only what an insert-only log needs.
alter table public.match_decisions enable row level security;
revoke all on public.match_decisions from public, anon, authenticated, service_role;
grant select, insert on public.match_decisions to service_role;
revoke all on sequence public.match_decisions_id_seq from public, anon, authenticated, service_role;
grant usage, select on sequence public.match_decisions_id_seq to service_role;

-- ---------------------------------------------------------------------------
-- app_config.score_model_f3: worker/intelligence/config.DEFAULT_SCORE_MODEL_F3 with mode 'shadow'
-- (the code default is 'off'). Bounds: web/lib/admin-config.ts and intelligence/config.score_model_f3.
-- Keep it ONE json literal: worker/tests/test_f3_migration_defaults.py reads it from this file.
-- ---------------------------------------------------------------------------

insert into public.app_config (key, value) values ('score_model_f3', '{
  "mode": "shadow",
  "deal": {"d_floor": 12, "d_ceil": 20, "d_mult": 2.5, "cred_min": 5, "cred_max": 35,
           "r_model": 0.9, "r_noyear": 0.3, "kavak_offset": 9},
  "fit": {"unknown": 0.75, "fail": 0.4, "trim_other": 0.5, "unknown_hard": 0.03, "price_target_at_max": 0.6},
  "levels": {"x_high": 0.70, "y_high": 0.70, "c_high": 0.82, "x_good": 0.65, "y_deal": 0.45,
             "y_good": 0.85, "y_min": 0.30, "n_min_high": 10, "fair_min_d": -2, "low_d": -10},
  "rules": {"seller_cap": true, "agency_voice": true, "placeholder": true, "pro_deal_d": true}
}'::jsonb)
on conflict (key) do nothing;

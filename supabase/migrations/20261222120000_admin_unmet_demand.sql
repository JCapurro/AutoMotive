-- /admin/demand: demanda insatisfecha. One row per active search with few or
-- no results, with how many listings each single filter would unlock, and a
-- one-row summary of what the free plan's cap hides. Both are computed by the
-- worker's nightly job (pipeline/unmet_demand.py, app_config.unmet_demand,
-- born off): the page only reads, so it stays fast.
-- Depends on: search_profiles, profiles, app_config, matches, free_trial_results
-- (20261118120000_free_results_cap_50).

-- A search's row goes with the search. No FK to listings: counts, not references.
create table public.admin_unmet_demand (
  search_profile_id bigint primary key references public.search_profiles(id) on delete cascade,
  user_id uuid not null,
  make text,
  model text,
  zone_label text,
  -- Results the search shows now (same count as the low_results bot).
  result_count integer not null check (result_count >= 0),
  -- Active listings of the model seen in the last 30 days, and the ones inside the zone.
  market integer not null check (market >= 0),
  market_in_zone integer not null check (market_in_zone >= 0),
  -- Listings that pass every filter with only that one filter relaxed.
  relaxed_zone integer not null check (relaxed_zone >= 0),
  relaxed_price integer not null check (relaxed_price >= 0),
  relaxed_trim integer not null check (relaxed_trim >= 0),
  relaxed_year integer not null check (relaxed_year >= 0),
  -- The single relaxation that adds the most; 'none' when none adds any (no supply).
  cause text not null check (cause in ('zone', 'price', 'trim', 'year', 'none')),
  computed_at timestamptz not null default now()
);
create index admin_unmet_demand_cause_idx on public.admin_unmet_demand (cause);

-- One row: the last run of the job and what the cap hides.
create table public.admin_unmet_demand_run (
  singleton boolean primary key default true check (singleton),
  computed_at timestamptz not null,
  duration_ms integer not null check (duration_ms >= 0),
  searches integer not null check (searches >= 0),
  -- Searches without a model (by body type): the funnel does not apply, left out.
  skipped_model_less integer not null default 0,
  max_results integer not null,
  min_age_hours numeric not null,
  -- plan_limits.enforced when it ran: with false, no cap hides anything.
  cap_enforced boolean not null default false,
  -- Matches of free accounts beyond their cap on active listings, by best level
  -- ({"high": n, ...}), and how many accounts have them.
  hidden_by_level jsonb not null default '{}'::jsonb,
  hidden_accounts integer not null default 0
);

alter table public.admin_unmet_demand enable row level security;
alter table public.admin_unmet_demand_run enable row level security;
create policy "unmet demand: admin read" on public.admin_unmet_demand for select to authenticated
  using (exists (select 1 from public.profiles p where p.id = (select auth.uid()) and p.role = 'admin'));
create policy "unmet demand run: admin read" on public.admin_unmet_demand_run for select to authenticated
  using (exists (select 1 from public.profiles p where p.id = (select auth.uid()) and p.role = 'admin'));
revoke all on public.admin_unmet_demand, public.admin_unmet_demand_run from public, anon, authenticated;
grant select on public.admin_unmet_demand, public.admin_unmet_demand_run to authenticated;
grant all on public.admin_unmet_demand, public.admin_unmet_demand_run to service_role;

-- The job is off until someone turns it on in /admin/config.
insert into public.app_config (key, value)
values ('unmet_demand', jsonb_build_object('enabled', false, 'max_results', 3, 'min_age_hours', 24,
                                           'batch_size', 100, 'pause_seconds', 2, 'hour', '04:30'))
on conflict (key) do nothing;

-- What the cap hides, for the job: the matches of free accounts (cap enforced)
-- on active listings the account's cumulative quota never admitted, one per
-- account and listing, by the best level, plus a row with a null level for the totals
-- (accounts counted once). Read by the worker's service role only.
create function public.admin_cap_hidden() returns table (level text, matches bigint, accounts bigint)
language sql stable security definer set search_path = '' as $$
  with free_accounts as materialized (
    select p.id from public.profiles p where public.free_result_limit(p.id) is not null),
  hidden as (
    select sp.user_id, m.listing_id, min(m.level) as level
      from public.matches m
      join public.search_profiles sp on sp.id = m.search_profile_id
      join free_accounts f on f.id = sp.user_id
      join public.listings l on l.id = m.listing_id and l.status = 'active'
     where not exists (select 1 from public.free_trial_results r
                        where r.user_id = sp.user_id and r.listing_id = m.listing_id)
     group by sp.user_id, m.listing_id)
  select h.level::text, count(*), count(distinct h.user_id) from hidden h
   group by grouping sets ((h.level), ()) having count(*) > 0
$$;
revoke all on function public.admin_cap_hidden() from public, anon, authenticated;
grant execute on function public.admin_cap_hidden() to service_role;

notify pgrst, 'reload schema';

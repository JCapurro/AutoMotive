-- PRO-02, ciclo 1: margen v1 y umbral en USD
-- (docs/superpowers/specs/2026-11-02-pro02-margen-design.md).
--
-- * matches.margin_ref: the estimated gross margin against the dealers'
--   median of price_ref (F-02 paso 3), written by the worker
--   (worker/intelligence/margin.py) on every scoring and rescore. Null when
--   dealer_n < comparables.min_n. SCORING_VERSION does not change: the
--   worker's rescore_queue picks the matches that should have one and don't.
-- * search_profiles.opportunity_threshold_usd: Pro's threshold by margin, in
--   USD; the plan's minimum (plan_limits.pro.min_threshold_usd) is checked by
--   the web on save and by the worker when it reads it, not by a CHECK.
-- * app_config.dealer_margin: reconditioning 5 % with a minimum of USD 300
--   (Juan, plan §8) and whether the transfer cost (PAR-01) is subtracted.
-- * plan_limits.pro.dealer_margin and min_threshold_usd = 500, only added when
--   missing, so a value changed in /admin/config stays.
-- * margin_ref is not readable by anon/authenticated: the table-wide SELECT
--   on matches becomes a column list without it (RLS lets every user read
--   their own matches whatever the plan, and the worker fills margin_ref for
--   every match). A later migration that adds a column to matches must grant
--   SELECT on it to authenticated (and anon) itself.
-- * my_margin_access(), my_match_margins(bigint[]) and
--   my_margin_sort_keys(bigint): what the web reads, security definer with
--   the owner and the feature checked inside. Without the feature they say
--   no / return nothing.
-- * search_results: 20261119120000_x01_tracking.sql's, plus p_sort = 'margin'
--   (only with the feature). match_cards is left alone.
--
-- Rollback: drop the four functions, re-apply X-01's search_results, grant
-- select on public.matches to anon, authenticated again; the columns and the
-- config rows can stay.

alter table public.matches add column if not exists margin_ref jsonb;
comment on column public.matches.margin_ref is
  'PRO-02: estimated gross margin against price_ref.dealer_median (ranges in USD, worker/intelligence/margin.py). Null without enough dealer comparables. Read by the web only through my_match_margins (Pro).';

-- The Pro-only gate (Juan: all of PRO-02 is Pro) cannot rest on the functions
-- alone: authenticated had SELECT on every column of matches
-- (20260927120100_rls.sql only revoked insert/update/delete). Keep SELECT on
-- every other column, whatever exists when this runs.
do $$
declare cols text;
begin
  select string_agg(format('%I', column_name), ', ' order by ordinal_position) into cols
    from information_schema.columns
   where table_schema = 'public' and table_name = 'matches' and column_name <> 'margin_ref';
  execute 'revoke select on public.matches from anon, authenticated';
  execute format('grant select (%s) on public.matches to anon, authenticated', cols);
end $$;

alter table public.search_profiles add column if not exists opportunity_threshold_usd integer
  constraint search_profiles_opportunity_threshold_usd_check check (opportunity_threshold_usd between 1 and 1000000);
comment on column public.search_profiles.opportunity_threshold_usd is
  'PRO-02: alert at once, without the daily cap, matches whose estimated margin (low end) is at least this many USD; the rest go to the digest. Ignored unless the plan has dealer_margin and the value reaches min_threshold_usd.';

-- 20261007120000 replaced the table UPDATE grant by a column list.
grant update (opportunity_threshold_usd) on public.search_profiles to authenticated;

insert into public.app_config (key, value) values ('dealer_margin', '{
  "as_of": "2026-11-02",
  "source": "Decisión de Juan, 30/10/2026 (docs/PLAN_FASES_BACKLOG_PRODUCTO_2026-10.md §8)",
  "reconditioning": {"pct": 5, "min_usd": 300},
  "transfer": {"enabled": true}
}'::jsonb) on conflict (key) do nothing;

update public.app_config
   set value = jsonb_set(value, '{pro}', '{"dealer_margin": true, "min_threshold_usd": 500}'::jsonb || (value->'pro'))
 where key = 'plan_limits'
   and jsonb_typeof(value->'pro') = 'object'
   and not (value->'pro' ? 'dealer_margin' and value->'pro' ? 'min_threshold_usd');

-- The smallest threshold in USD the account's plan accepts: its own
-- min_threshold_usd, else Pro's (admins get every feature but carry no
-- limits). Null when neither is a whole number: no threshold applies.
create or replace function public.min_threshold_usd(p_user uuid) returns integer
language sql stable security definer set search_path = '' as $$
  select coalesce(
    public.config_whole_number(public.plan_limits_for(p_user)->'limits'->'min_threshold_usd', 1, 1000000),
    public.config_whole_number((select value->'pro'->'min_threshold_usd' from public.app_config where key = 'plan_limits'), 1, 1000000))
$$;

-- The web's one check: {enabled, min_threshold_usd}. A database without this
-- migration has no function, so the web shows nothing of PRO-02.
create or replace function public.my_margin_access() returns jsonb
language sql stable security definer set search_path = '' as $$
  select jsonb_build_object('enabled', public.plan_feature((select auth.uid()), 'dealer_margin'),
                            'min_threshold_usd', public.min_threshold_usd((select auth.uid())))
$$;

-- margin_ref of the caller's own matches (the owner checked here, as the RLS
-- of matches does: authenticated cannot read the column), nothing without
-- the feature.
create or replace function public.my_match_margins(p_match_ids bigint[])
returns table (match_id bigint, margin_ref jsonb)
language sql stable security definer set search_path = '' as $$
  select m.id, m.margin_ref
    from public.matches m
    join public.search_profiles sp on sp.id = m.search_profile_id
   where m.id = any(p_match_ids) and m.margin_ref is not null
     and sp.user_id = (select auth.uid())
     and (select public.my_plan_feature('dealer_margin'))
$$;

-- search_results' sort key: the margin's low end of the caller's own matches
-- of one search, nothing without the feature.
create or replace function public.my_margin_sort_keys(p_profile_id bigint)
returns table (match_id bigint, low numeric)
language sql stable security definer set search_path = '' as $$
  select m.id, (m.margin_ref->'gross_margin_usd'->>'min')::numeric
    from public.matches m
    join public.search_profiles sp on sp.id = m.search_profile_id
   where m.search_profile_id = p_profile_id and m.margin_ref is not null
     and sp.user_id = (select auth.uid())
     and (select public.my_plan_feature('dealer_margin'))
$$;

create or replace function public.search_results(
  p_profile_id bigint, p_filter text default 'all', p_sort text default 'score',
  p_limit integer default 50, p_offset integer default 0
) returns setof public.match_cards language sql stable security invoker set search_path = '' as $$
  with access as (select public.my_plan_snapshot() v), cap as (
    select case when (v->>'enforced')::boolean
      then coalesce((v->'limits'->>'max_visible_results')::int, 2147483647)
      else 2147483647 end n from access
  ), margin_access as (
    select p_sort = 'margin' and public.my_plan_feature('dealer_margin') ok
  ), margins as (
    select k.match_id, k.low from public.my_margin_sort_keys(p_profile_id) k where (select ok from margin_access)
  )
  select c.* from public.match_cards c
  left join margins mg on mg.match_id = c.match_id
  where c.search_profile_id = p_profile_id and case p_filter
    when 'new' then c.listing_status = 'active' and c.status = 'new'
    when 'opportunities' then c.listing_status = 'active' and c.level = 'high' and c.status <> 'discarded'
    when 'saved' then c.saved when 'discarded' then c.status = 'discarded'
    when 'contacted' then c.status = 'contacted'
    when 'visit_scheduled' then c.status = 'visit_scheduled'
    when 'purchased' then c.status = 'purchased'
    else c.listing_status = 'active' and c.status <> 'discarded' end
  order by case when p_sort = 'score' then c.score end desc nulls last,
    case when (select ok from margin_access) then mg.low end desc nulls last,
    case when p_sort = 'price' then c.price_usd end asc nulls last,
    case when p_sort = 'km' then c.mileage_km end asc nulls last,
    coalesce(c.published_at, c.first_seen_at) desc nulls last, c.listing_id desc
  limit least(greatest(coalesce(p_limit, 50), 0), greatest((select n from cap) - greatest(coalesce(p_offset, 0), 0), 0))
  offset greatest(coalesce(p_offset, 0), 0)
$$;

revoke all on function public.min_threshold_usd(uuid) from public, anon, authenticated;
revoke all on function public.my_margin_access(), public.my_match_margins(bigint[]),
  public.my_margin_sort_keys(bigint) from public, anon;
grant execute on function public.my_margin_access(), public.my_match_margins(bigint[]),
  public.my_margin_sort_keys(bigint) to authenticated;

notify pgrst, 'reload schema';

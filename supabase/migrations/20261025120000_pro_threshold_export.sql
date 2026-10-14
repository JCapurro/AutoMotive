-- Planes 2026-10, fase 3 (docs/PLANES_2026-10.md): what Pro adds to Agencia.
--
--   3.2  a per-search opportunity threshold: listings at least X% below
--        comparables are alerted at once without the daily cap, the rest go
--        to the digest (the worker decides: notifications/engine.py)
--   3.3  CSV export of the results (the web builds the file from
--        export_search_results)
--
-- Both are plan features in app_config.plan_limits, next to the limits, so
-- the plans page and what the system allows read the same place:
--   threshold_alerts  the threshold applies
--   csv_export        results can be downloaded

update public.app_config
   set value = jsonb_set(value, '{pro}', coalesce(value->'pro', '{}') || '{"threshold_alerts": true, "csv_export": true}')
 where key = 'plan_limits';

-- X: whole percent below comparables. Null = no threshold (Agencia's daily cap).
alter table public.search_profiles
  add column opportunity_threshold_pct smallint
    check (opportunity_threshold_pct between 1 and 90);
comment on column public.search_profiles.opportunity_threshold_pct is
  'Pro (3.2): alert at once, without the daily cap, listings at least this % below comparables; the rest go to the digest. Ignored unless the plan has threshold_alerts.';

-- Whether the account's current plan includes a feature of app_config.plan_limits.
-- Admins have every feature (plan_limits_for gives them pro access without limits).
create function public.plan_feature(p_user uuid, p_feature text) returns boolean
language sql stable security definer set search_path = '' as $$
  select coalesce((select p.role = 'admin' from public.profiles p where p.id = p_user), false)
      or coalesce(public.plan_limits_for(p_user)->'limits'->>p_feature = 'true', false)
$$;

create function public.my_plan_feature(p_feature text) returns boolean
language sql stable security definer set search_path = '' as $$
  select public.plan_feature((select auth.uid()), p_feature)
$$;

-- How many comparables a percentage needs (app_config.comparables.min_n, as
-- the worker and the web read it). The export runs with the user's rights,
-- which don't reach app_config.
create function public.comparables_min_n() returns integer
language sql stable security definer set search_path = '' as $$
  select coalesce(public.config_whole_number(
    (select value->'min_n' from public.app_config where key = 'comparables'), 1, 1000), 5)
$$;

-- 3.3: the signed-in user's results, as the results page lists them by
-- default (active, not discarded), for one search or all of them.
-- comparables_pct: the price against comparables (-12 = 12% below), only
-- with enough of them, as the web and the alerts show it.
create function public.export_search_results(p_profile_id bigint default null)
returns table (search_name text, detected_at timestamptz, source_name text, title text, version text,
               year integer, mileage_km integer, price numeric, currency text, comparables_pct integer,
               score integer, url text)
language plpgsql stable security invoker set search_path = '' as $$
declare
  v_min_n integer := public.comparables_min_n();
begin
  if not public.my_plan_feature('csv_export') then
    raise exception 'plan_feature_unavailable' using errcode = '42501';
  end if;
  return query
  select c.profile_name::text, c.first_seen_at, coalesce(s.name, c.source)::text, c.title::text, c.trim::text,
         c.year::integer, c.mileage_km::integer, c.price::numeric, c.currency::text,
         case when coalesce((c.price_ref->>'n')::numeric, 0) >= v_min_n and c.price_ref->>'median' is not null
                   and c.price_ref->>'diff_pct' is not null
              then (-round((c.price_ref->>'diff_pct')::numeric))::integer end,
         c.score::integer, l.url::text
    from public.match_cards c
    join public.listings l on l.id = c.listing_id
    left join public.sources s on s.id = c.source
   where c.user_id = (select auth.uid())
     and (p_profile_id is null or c.search_profile_id = p_profile_id)
     and c.listing_status = 'active' and c.status <> 'discarded'
   order by c.profile_name, c.search_profile_id, c.first_seen_at desc nulls last, c.listing_id desc;
end $$;

revoke all on function public.plan_feature(uuid, text) from public, anon, authenticated;
revoke all on function public.my_plan_feature(text), public.comparables_min_n(),
  public.export_search_results(bigint) from public, anon;
grant execute on function public.my_plan_feature(text), public.comparables_min_n(),
  public.export_search_results(bigint) to authenticated;

notify pgrst, 'reload schema';

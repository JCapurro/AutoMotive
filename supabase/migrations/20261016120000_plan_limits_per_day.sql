-- Planes 2026-10 (fase 1): app_config.plan_limits is the one place that says
-- what each plan includes; the database, the worker and the web read it.
--   max_profiles              active searches (one model each)
--   max_visible_results       results per search; absent = all of them
--   immediate_alerts_per_day  immediate alerts per Argentine calendar day; the
--                             rest go to the daily digest (0 = digest only)
-- Upsert keeps `enforced` and any other key already there. Editable from
-- /admin/config without a deploy.
insert into public.app_config(key, value) values ('plan_limits', '{
  "enforced": false,
  "free": {"max_profiles": 1, "max_visible_results": 100, "immediate_alerts_per_day": 3},
  "pass": {"max_profiles": 3, "immediate_alerts_per_day": 10},
  "pro":  {"max_profiles": 20, "immediate_alerts_per_day": 50}}')
on conflict (key) do update set value = app_config.value
  || jsonb_build_object('free', (coalesce(app_config.value->'free', '{}') - 'immediate_alerts') || (excluded.value->'free'))
  || jsonb_build_object('pass', (coalesce(app_config.value->'pass', '{}') - 'immediate_alerts' - 'max_visible_results') || (excluded.value->'pass'))
  || jsonb_build_object('pro', (coalesce(app_config.value->'pro', '{}') - 'immediate_alerts' - 'max_visible_results') || (excluded.value->'pro'));

-- Immediate alerts a plan includes per day. The legacy boolean immediate_alerts
-- still works: true is the global alerts_max_per_user_day, false is none.
-- Like the web's alertCap(), anything but a whole number >= 0 counts as 0
-- instead of raising (a 7.5 typed in /admin/config must not stop every batch).
create function public.plan_alert_cap(p_access jsonb) returns integer
language sql stable set search_path = '' as $$
  select case
    when p_access->'limits' ? 'immediate_alerts_per_day'
      then case when jsonb_typeof(p_access->'limits'->'immediate_alerts_per_day') = 'number'
                 and (p_access->'limits'->>'immediate_alerts_per_day')::numeric between 0 and 2147483647
                 and (p_access->'limits'->>'immediate_alerts_per_day')::numeric % 1 = 0
            then (p_access->'limits'->>'immediate_alerts_per_day')::numeric::integer
            else 0 end
    when coalesce((p_access->'limits'->>'immediate_alerts')::boolean, false)
      then coalesce((select (value #>> '{}')::integer from public.app_config where key = 'alerts_max_per_user_day'), 10)
    else 0 end
$$;

-- The worker's daily cap for a user: the plan's with enforced limits, the
-- global alerts_max_per_user_day in the open pilot.
create function public.immediate_alert_cap(p_user uuid) returns integer
language sql stable security definer set search_path = '' as $$
  select case when coalesce((a.v->>'enforced')::boolean, false) then public.plan_alert_cap(a.v)
    else coalesce((select (value #>> '{}')::integer from public.app_config where key = 'alerts_max_per_user_day'), 10) end
  from (select public.plan_limits_for(p_user) v) a
$$;

create or replace function public.effective_search_frequency(p_user uuid, p_frequency public.notify_frequency)
returns public.notify_frequency language sql stable security definer set search_path = '' as $$
  select case when coalesce((a.v->>'enforced')::boolean, false) and public.plan_alert_cap(a.v) = 0
    then 'daily'::public.notify_frequency else p_frequency end
  from (select public.plan_limits_for(p_user) v) a
$$;

-- Store the desired frequency: readers resolve a plan without immediate alerts to daily.
create or replace function public.enforce_plan_frequency() returns trigger
language plpgsql security definer set search_path = '' as $$
declare
  v_limits jsonb;
begin
  if new.notification_frequency <> 'immediate'
     or (tg_op = 'UPDATE' and old.notification_frequency = 'immediate') then
    return new;
  end if;
  v_limits := public.plan_limits_for(new.user_id);
  if public.plan_alert_cap(v_limits) > 0 then
    return new;
  end if;

  insert into public.events (user_id, name, props)
  values (new.user_id, 'plan_limit_hit', jsonb_build_object(
    'limit', 'immediate_alerts', 'plan', v_limits ->> 'plan', 'search_profile_id', new.id,
    'enforced', (v_limits ->> 'enforced')::boolean));
  return new;
end;
$$;

revoke all on function public.plan_alert_cap(jsonb), public.immediate_alert_cap(uuid) from public, anon, authenticated;
grant execute on function public.immediate_alert_cap(uuid) to service_role;

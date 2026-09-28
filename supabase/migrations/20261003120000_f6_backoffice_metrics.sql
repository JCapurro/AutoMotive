-- F6: backoffice, métricas y monetización (docs/TECHNICAL_PLAN.md, secciones 10–12).
--
-- * Plan limits (§33, sección 12): plan_limits_for() resolves a user's
--   effective plan (an expired Pro / Search Pass is free) and its limits. The
--   F0 max_profiles trigger uses it, a new trigger covers immediate alerts and
--   record_plan_limit_hit() lets the web log the limits it detects (visible
--   results). With plan_limits.enforced = false (the pilot) every limit only
--   records plan_limit_hit; with true it applies.
-- * Monetization (§52): pro_waitlist + join_waitlist(), and pro_cta_state(),
--   which decides when the web shows "Probar Automotive Pro".
-- * Metrics (sección 11): the v_* views, built on metric_users (admins left
--   out) and metric_alerts (one row per alert a user received, whatever the
--   channels). v_validation_criteria puts the six §53 criteria next to their
--   thresholds (app_config.validation_criteria).
-- * Backoffice (sección 10): admin_* views for the /admin lists.
--
-- Every view is security_invoker and closed to anon/authenticated: /admin reads
-- them with the service role after checking profiles.role = 'admin'.

-- ---------------------------------------------------------------------------
-- app_config
-- ---------------------------------------------------------------------------

insert into public.app_config (key, value) values
  -- §53 thresholds. The PRD gives no number for retention ("varias semanas")
  -- nor for outcome ("algunos usuarios"): these are the pilot's choice.
  ('validation_criteria', '{
     "active_users_min": 30, "alert_open_min_pct": 30, "engagement_min_pct": 15,
     "retention_weeks": 3, "retention_min_pct": 40, "outcome_min_users": 3,
     "payment_intent_min_pct": 10, "activation_target_pct": 70
   }'),
  -- §52: the CTA shows after real activity (alert clicks) or after hitting one
  -- of these limits on purpose. Passive limits (immediate alerts, visible
  -- results) are only measured.
  ('pro_cta', '{"min_alert_clicks": 3, "on_limits": ["max_profiles"]}'),
  -- §33–34: the prices the plans screen shows (hypotheses to validate, no charge yet).
  ('pro_offer', '{"pro_monthly": {"price_usd": 15}, "pass_30": {"price_usd": 12}, "pass_90": {"price_usd": 25}}')
on conflict (key) do nothing;

-- The Search Pass (§34) is Pro for a while: same limits unless tuned apart.
update public.app_config
   set value = value || jsonb_build_object('pass', value -> 'pro')
 where key = 'plan_limits' and not value ? 'pass' and value ? 'pro';

-- ---------------------------------------------------------------------------
-- Plan limits (§33, sección 12)
-- ---------------------------------------------------------------------------

-- {"plan": "free"|"pro"|"pass", "enforced": bool, "limits": {...}} for a user.
-- An expired Pro / Search Pass falls back to free; an unknown user is free.
create function public.plan_limits_for(p_user uuid)
returns jsonb
language sql
stable
security definer
set search_path = ''
as $$
  with cfg as (
    select coalesce((select value from public.app_config where key = 'plan_limits'), '{}'::jsonb) as v
  ),
  plan as (
    select coalesce((
      select case
               when p.plan <> 'free' and p.plan_expires_at is not null and p.plan_expires_at < now()
                 then 'free'
               else p.plan::text
             end
        from public.profiles p where p.id = p_user), 'free') as name
  )
  select jsonb_build_object(
           'plan',     plan.name,
           'enforced', coalesce((cfg.v ->> 'enforced')::boolean, false),
           'limits',   coalesce(cfg.v -> plan.name, '{}'::jsonb))
    from cfg, plan
$$;

revoke execute on function public.plan_limits_for(uuid) from public, anon, authenticated;

-- The signed-in user's plan and limits (the web adapts results and the CTA).
create function public.my_plan_limits()
returns jsonb
language sql
stable
security definer
set search_path = ''
as $$
  select public.plan_limits_for((select auth.uid()))
$$;

revoke execute on function public.my_plan_limits() from public, anon;
grant execute on function public.my_plan_limits() to authenticated;

-- Same behavior as F0 (max_profiles), now through plan_limits_for().
create or replace function public.enforce_plan_limits() returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_limits jsonb := public.plan_limits_for(new.user_id);
  v_max    integer := (v_limits -> 'limits' ->> 'max_profiles')::integer;
  v_count  integer;
begin
  if v_max is null then
    return new;
  end if;

  select count(*) into v_count from public.search_profiles where user_id = new.user_id;
  if v_count < v_max then
    return new;
  end if;

  insert into public.events (user_id, name, props)
  values (new.user_id, 'plan_limit_hit', jsonb_build_object(
    'limit', 'max_profiles', 'plan', v_limits ->> 'plan',
    'max', v_max, 'current', v_count, 'enforced', (v_limits ->> 'enforced')::boolean));

  if (v_limits ->> 'enforced')::boolean then
    raise exception 'plan_limit_exceeded'
      using errcode = 'P0001',
            detail  = format('plan %s allows %s search profiles', v_limits ->> 'plan', v_max);
  end if;
  return new;
end;
$$;

-- Immediate alerts are Pro (§33). A free search that asks for them records
-- plan_limit_hit when it's created or switched to immediate; enforced, it
-- becomes daily (the digest).
create function public.enforce_plan_frequency() returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_limits jsonb;
begin
  if new.notification_frequency <> 'immediate'
     or (tg_op = 'UPDATE' and old.notification_frequency = 'immediate') then
    return new;
  end if;
  v_limits := public.plan_limits_for(new.user_id);
  if coalesce((v_limits -> 'limits' ->> 'immediate_alerts')::boolean, true) then
    return new;
  end if;

  insert into public.events (user_id, name, props)
  values (new.user_id, 'plan_limit_hit', jsonb_build_object(
    'limit', 'immediate_alerts', 'plan', v_limits ->> 'plan', 'search_profile_id', new.id,
    'enforced', (v_limits ->> 'enforced')::boolean));

  if (v_limits ->> 'enforced')::boolean then
    new.notification_frequency := 'daily';
  end if;
  return new;
end;
$$;

create trigger search_profiles_enforce_plan_frequency
  before insert or update of notification_frequency on public.search_profiles
  for each row execute function public.enforce_plan_frequency();

revoke execute on function public.enforce_plan_frequency() from public, anon, authenticated;

-- Limits only the web sees (max_visible_results): the web reports the total and
-- this records plan_limit_hit when it's over the plan's limit, at most once a
-- day per limit and search. Returns whether the limit applies (enforced).
create function public.record_plan_limit_hit(p_limit text, p_props jsonb default '{}')
returns boolean
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_user    uuid := auth.uid();
  v_limits  jsonb;
  v_max     integer;
  v_total   integer := (p_props ->> 'total')::integer;
  v_profile text := p_props ->> 'search_profile_id';
begin
  if v_user is null then
    raise exception 'not authenticated' using errcode = '42501';
  end if;
  if p_limit is distinct from 'max_visible_results' then
    raise exception 'unknown limit %', p_limit using errcode = '22023';
  end if;
  v_limits := public.plan_limits_for(v_user);
  v_max := (v_limits -> 'limits' ->> p_limit)::integer;
  if v_max is null or v_total is null or v_total <= v_max then
    return false;
  end if;

  if not exists (
    select 1 from public.events
     where user_id = v_user and name = 'plan_limit_hit' and props ->> 'limit' = p_limit
       and (props ->> 'search_profile_id') is not distinct from v_profile
       and created_at > now() - interval '1 day'
  ) then
    insert into public.events (user_id, name, props)
    values (v_user, 'plan_limit_hit', jsonb_build_object(
      'limit', p_limit, 'plan', v_limits ->> 'plan', 'max', v_max, 'current', v_total,
      'search_profile_id', v_profile::bigint, 'enforced', (v_limits ->> 'enforced')::boolean));
  end if;
  return (v_limits ->> 'enforced')::boolean;
end;
$$;

revoke execute on function public.record_plan_limit_hit(text, jsonb) from public, anon;
grant execute on function public.record_plan_limit_hit(text, jsonb) to authenticated;

-- ---------------------------------------------------------------------------
-- "Probar Automotive Pro" (§52, sección 9): waitlist, no charge yet
-- ---------------------------------------------------------------------------

create table public.pro_waitlist (
  user_id    uuid primary key references public.profiles (id) on delete cascade,
  -- Pro mensual (§33) or Search Pass 30/90 días (§34).
  plan       text not null check (plan in ('pro_monthly', 'pass_30', 'pass_90')),
  -- Where the user came from: banner, plan_limit, settings…
  placement  text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create trigger pro_waitlist_set_updated_at before update on public.pro_waitlist
  for each row execute function public.set_updated_at();

alter table public.pro_waitlist enable row level security;
create policy "pro_waitlist: read own" on public.pro_waitlist
  for select to authenticated using (user_id = (select auth.uid()));
revoke all on public.pro_waitlist from anon;
revoke insert, update, delete on public.pro_waitlist from authenticated;

-- Joins (or changes the chosen plan) and records waitlist_joined.
create function public.join_waitlist(p_plan text, p_placement text default null)
returns void
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_user     uuid := auth.uid();
  v_previous text;
begin
  if v_user is null then
    raise exception 'not authenticated' using errcode = '42501';
  end if;
  if p_plan is null or p_plan not in ('pro_monthly', 'pass_30', 'pass_90') then
    raise exception 'unknown plan %', p_plan using errcode = '22023';
  end if;
  select plan into v_previous from public.pro_waitlist where user_id = v_user;
  insert into public.pro_waitlist (user_id, plan, placement)
  values (v_user, p_plan, left(p_placement, 40))
  on conflict (user_id) do update set plan = excluded.plan;

  insert into public.events (user_id, name, props)
  values (v_user, 'waitlist_joined', jsonb_build_object(
    'plan', p_plan, 'placement', left(p_placement, 40), 'previous_plan', v_previous));
end;
$$;

revoke execute on function public.join_waitlist(text, text) from public, anon;
grant execute on function public.join_waitlist(text, text) to authenticated;

-- Whether the web shows the Pro CTA to the signed-in user (§52: "cuando un
-- usuario tenga actividad real"): a free user, not on the waitlist yet, with
-- pro_cta.min_alert_clicks clicked alerts or a hit of a pro_cta.on_limits limit.
create function public.pro_cta_state()
returns jsonb
language plpgsql
stable
security definer
set search_path = ''
as $$
declare
  v_user     uuid := auth.uid();
  v_cfg      jsonb;
  v_plan     text;
  v_clicks   integer;
  v_min      integer;
  v_limit    boolean;
  v_waitlist text;
  v_reason   text;
begin
  if v_user is null then
    return jsonb_build_object('show', false);
  end if;
  v_cfg := coalesce((select value from public.app_config where key = 'pro_cta'), '{}'::jsonb);
  v_min := coalesce((v_cfg ->> 'min_alert_clicks')::integer, 3);
  v_plan := public.plan_limits_for(v_user) ->> 'plan';

  select count(distinct props ->> 'notification_id') into v_clicks
    from public.events where user_id = v_user and name = 'alert_clicked';
  select exists (
    select 1 from public.events
     where user_id = v_user and name = 'plan_limit_hit'
       and props ->> 'limit' in (select jsonb_array_elements_text(coalesce(v_cfg -> 'on_limits', '[]'::jsonb)))
  ) into v_limit;
  select plan into v_waitlist from public.pro_waitlist where user_id = v_user;

  v_reason := case when v_limit then 'plan_limit' when v_clicks >= v_min then 'activity' end;
  return jsonb_build_object(
    'show',          v_plan = 'free' and v_waitlist is null and v_reason is not null,
    'reason',        v_reason,
    'plan',          v_plan,
    'alert_clicks',  v_clicks,
    'waitlist_plan', v_waitlist);
end;
$$;

revoke execute on function public.pro_cta_state() from public, anon;
grant execute on function public.pro_cta_state() to authenticated;

-- ---------------------------------------------------------------------------
-- Metrics (sección 11). Weeks and days are Argentina's (Monday weeks).
-- ---------------------------------------------------------------------------

create index events_user_name_created_idx on public.events (user_id, name, created_at desc);
create index notifications_search_profile_id_idx on public.notifications (search_profile_id);

-- The population every metric counts: everyone but the admins. A profile
-- without email is a Telegram-only account from the old wizard: it uses
-- Automotive but never signed up on the web.
create view public.metric_users with (security_invoker = true) as
select p.id, p.email, p.plan, p.plan_expires_at, p.created_at, p.email is null as telegram_only
  from public.profiles p
 where p.role <> 'admin';

-- One row per alert row delivered on a channel: sent immediately, or carried
-- by a digest that was sent. Digests themselves are containers, not alerts.
-- level/score are the ones at send time (payload), not after a re-score.
create view public.metric_alert_rows with (security_invoker = true) as
select n.id                                             as notification_id,
       n.user_id,
       n.listing_id,
       n.search_profile_id,
       n.match_id,
       n.kind::text                                     as kind,
       n.channel::text                                  as channel,
       n.dedupe_key,
       coalesce(n.payload -> 'match' ->> 'level', 'none') as level,
       (n.payload -> 'match' ->> 'score')::integer      as score,
       n.status = 'digest'                              as via_digest,
       coalesce(n.sent_at, d.sent_at)                   as delivered_at,
       n.opened_at,
       n.clicked_at,
       coalesce(i.saved or i.status in ('interested', 'contacted', 'visit_scheduled', 'purchased'), false)
                                                        as saved,
       coalesce(i.status = 'discarded', false)          as discarded,
       i.rejection_reason::text                         as rejection_reason
  from public.notifications n
  join public.metric_users mu on mu.id = n.user_id
  left join public.notifications d on d.id = n.digested_in
  left join public.user_listing_interactions i on i.user_id = n.user_id and i.listing_id = n.listing_id
 where n.kind <> 'digest'
   and (n.status = 'sent' or (n.status = 'digest' and d.status = 'sent'));

-- One row per alert a user received (user, dedupe_key), whatever the channels:
-- opened/clicked on any of them counts once.
create view public.metric_alerts with (security_invoker = true) as
select user_id,
       dedupe_key,
       max(listing_id)          as listing_id,
       max(search_profile_id)   as search_profile_id,
       min(kind)                as kind,
       min(level)               as level,
       max(score)               as score,
       bool_and(via_digest)     as via_digest,
       min(delivered_at)        as delivered_at,
       min(opened_at)           as opened_at,
       min(clicked_at)          as clicked_at,
       bool_or(saved)           as saved,
       bool_or(discarded)       as discarded,
       max(rejection_reason)    as rejection_reason,
       array_agg(distinct channel order by channel) as channels
  from public.metric_alert_rows
 group by user_id, dedupe_key;

-- North Star (§35): relevant listings opened from an alert per active user and
-- week. Relevant = clicked from an alert and not discarded for a reason that
-- says it wasn't a match (automatic, wrong_trim, location); a listing counts
-- once per user, in the week of its first click. Active = received an alert or
-- did something (any event but alert_sent) that week.
create view public.v_north_star_weekly with (security_invoker = true) as
with relevant as (
  select date_trunc('week', min(clicked_at) at time zone 'America/Argentina/Buenos_Aires')::date as week
    from public.metric_alerts
   where clicked_at is not null and listing_id is not null
   group by user_id, listing_id
  having not bool_or(discarded and coalesce(rejection_reason, '') in ('automatic', 'wrong_trim', 'location'))
),
activity as (
  select date_trunc('week', e.created_at at time zone 'America/Argentina/Buenos_Aires')::date as week, e.user_id
    from public.events e
    join public.metric_users mu on mu.id = e.user_id
   where e.name <> 'alert_sent'
  union
  select date_trunc('week', delivered_at at time zone 'America/Argentina/Buenos_Aires')::date, user_id
    from public.metric_alerts
),
active as (
  select week, count(distinct user_id) as n from activity group by week
),
opens as (
  select week, count(*) as n from relevant group by week
)
select a.week,
       a.n                                                    as active_users,
       coalesce(o.n, 0)                                       as relevant_opens,
       round(coalesce(o.n, 0)::numeric / nullif(a.n, 0), 2)   as relevant_opens_per_active_user
  from active a
  left join opens o using (week)
 order by a.week;

-- Activation (§36): web sign-ups → with at least one search (even if deleted
-- later). One row per sign-up week plus the total (cohort_week null).
create view public.v_activation with (security_invoker = true) as
with signups as (
  select date_trunc('week', mu.created_at at time zone 'America/Argentina/Buenos_Aires')::date as cohort_week,
         exists (select 1 from public.search_profiles sp where sp.user_id = mu.id)
           or exists (select 1 from public.events e
                       where e.user_id = mu.id and e.name = 'search_profile_created') as has_search
    from public.metric_users mu
   where not mu.telegram_only
)
select cohort_week,
       count(*)                                                        as signed_up,
       count(*) filter (where has_search)                              as with_search,
       round(100.0 * count(*) filter (where has_search) / nullif(count(*), 0), 1) as activation_pct,
       coalesce((select (value ->> 'activation_target_pct')::numeric
                   from public.app_config where key = 'validation_criteria'), 70) as target_pct
  from signups
 group by grouping sets ((cohort_week), ())
 order by cohort_week nulls last;

-- First value (§36): from creating a search to its first match of level ≥ good
-- (backfill included). first_value_at is null while there's none.
create view public.v_first_value with (security_invoker = true) as
select sp.id                                   as search_profile_id,
       sp.user_id,
       sp.created_at,
       fv.first_value_at,
       fv.is_backfill,
       round((extract(epoch from fv.first_value_at - sp.created_at) / 3600)::numeric, 1) as hours_to_first_value
  from public.search_profiles sp
  join public.metric_users mu on mu.id = sp.user_id
  left join lateral (
    select m.generated_at as first_value_at, m.is_backfill
      from public.matches m
     where m.search_profile_id = sp.id and m.level in ('high', 'good')
     order by m.generated_at
     limit 1
  ) fv on true;

-- Alert funnel (§37) per level at send time and channel: sent → opened →
-- clicked → saved → discarded. level 'none': price drops or disappearances
-- without a match.
create view public.v_alert_funnel with (security_invoker = true) as
select level,
       channel,
       count(*)                                        as sent,
       count(opened_at)                                as opened,
       count(clicked_at)                               as clicked,
       count(*) filter (where saved)                   as saved,
       count(*) filter (where discarded)               as discarded,
       round(100.0 * count(opened_at) / count(*), 1)   as open_rate_pct,
       round(100.0 * count(clicked_at) / count(*), 1)  as click_rate_pct,
       round(100.0 * count(*) filter (where saved) / count(*), 1)     as save_rate_pct,
       round(100.0 * count(*) filter (where discarded) / count(*), 1) as dismiss_rate_pct
  from public.metric_alert_rows
 group by level, channel
 order by array_position(array['high', 'good', 'match', 'low', 'none'], level), channel;

-- High Score Engagement (§37): 🔥 alerts against 🟢/🟡 ones. If the rates don't
-- differ, the score isn't adding value.
create view public.v_high_score_engagement with (security_invoker = true) as
select case when level = 'high' then 'high' else 'match_good' end as segment,
       count(*)                                                     as alerts,
       round(100.0 * count(opened_at) / count(*), 1)                as open_rate_pct,
       round(100.0 * count(clicked_at) / count(*), 1)               as click_rate_pct,
       round(100.0 * count(*) filter (where saved) / count(*), 1)   as save_rate_pct,
       round(100.0 * count(*) filter (where discarded) / count(*), 1) as dismiss_rate_pct,
       round(100.0 * count(*) filter (where clicked_at is not null or saved) / count(*), 1) as engagement_pct
  from public.metric_alerts
 where level in ('high', 'good', 'match')
 group by 1
 order by 1;

-- Noise KPI (§47): immediate alerts per alerted user and day, next to the cap.
create view public.v_alerts_per_user_day with (security_invoker = true) as
with per_user as (
  select (delivered_at at time zone 'America/Argentina/Buenos_Aires')::date as day, user_id, count(*) as alerts
    from public.metric_alerts
   where not via_digest and delivered_at is not null
   group by 1, 2
)
select day,
       count(*)                                        as users,
       sum(alerts)::integer                            as alerts,
       round(sum(alerts)::numeric / count(*), 2)       as alerts_per_user,
       max(alerts)::integer                            as max_per_user,
       (select (value #>> '{}')::integer from public.app_config where key = 'alerts_max_per_user_day') as cap
  from per_user
 group by day
 order by day;

-- Outcomes (§38): each "Compré este vehículo", its influence answer and the
-- time using Automotive; came_from_alert when the user had been alerted of it.
create view public.v_outcomes with (security_invoker = true) as
select ov.id                      as owned_vehicle_id,
       ov.user_id,
       ov.listing_id,
       ov.search_profile_id,
       ov.vehicle ->> 'title'     as title,
       ov.purchase_price,
       ov.purchase_currency,
       ov.purchase_date,
       ov.automotive_influence,
       ov.created_at,
       floor(extract(epoch from ov.created_at - mu.created_at) / 86400)::integer as days_using_automotive,
       floor(extract(epoch from ov.created_at - sp.created_at) / 86400)::integer as days_since_search,
       exists (select 1 from public.metric_alerts a
                where a.user_id = ov.user_id and a.listing_id = ov.listing_id) as came_from_alert
  from public.owned_vehicles ov
  join public.metric_users mu on mu.id = ov.user_id
  left join public.search_profiles sp on sp.id = ov.search_profile_id;

-- The six §53 criteria against app_config.validation_criteria:
--   1. usage: users with an enabled search;
--   2. relevance: alerts opened (Telegram exposes no reads: opened = first click, §37);
--   3. engagement: alerted listings (per user) clicked from the alert, opened at
--      the source or saved / marked "Me interesa";
--   4. retention: of the users whose first search is retention_weeks old, the
--      ones still active in the last 7 days;
--   5. outcome: users who contacted, scheduled a visit or bought;
--   6. monetization: active users (1.) on the waitlist or on a paid plan.
create view public.v_validation_criteria with (security_invoker = true) as
with cfg as (
  select coalesce((select value from public.app_config where key = 'validation_criteria'), '{}'::jsonb) as v
),
active_users as (
  select distinct sp.user_id
    from public.search_profiles sp
    join public.metric_users mu on mu.id = sp.user_id
   where sp.enabled
),
alerted as (
  select a.user_id, a.listing_id,
         bool_or(a.clicked_at is not null or a.saved)
           or exists (select 1 from public.events e
                       where e.user_id = a.user_id and e.name = 'listing_outbound_clicked'
                         and e.props ->> 'listing_id' = a.listing_id::text) as engaged
    from public.metric_alerts a
   where a.listing_id is not null
   group by a.user_id, a.listing_id
),
first_search as (
  select s.user_id, min(s.at) as first_at
    from (select user_id, created_at as at from public.search_profiles
          union all
          select user_id, created_at from public.events where name = 'search_profile_created') s
    join public.metric_users mu on mu.id = s.user_id
   group by s.user_id
),
eligible as (
  select fs.user_id
    from first_search fs, cfg
   where fs.first_at <= now() - make_interval(days => 7 * coalesce((cfg.v ->> 'retention_weeks')::integer, 3))
),
outcome_users as (
  select user_id from public.user_listing_interactions
   where status in ('contacted', 'visit_scheduled', 'purchased')
  union
  select user_id from public.owned_vehicles
  union
  select user_id from public.events
   where name = 'listing_status_changed' and props ->> 'status' in ('contacted', 'visit_scheduled', 'purchased')
),
criteria (ordinal, criterion, label, metric, unit, numerator, denominator, threshold) as (
  select 1, 'usage', 'Uso', 'Usuarios con búsquedas activas', 'users',
         (select count(*) from active_users), null::bigint,
         coalesce((cfg.v ->> 'active_users_min')::numeric, 30)
    from cfg
  union all
  select 2, 'relevance', 'Relevancia', 'Alertas abiertas', 'pct',
         (select count(*) from public.metric_alerts where opened_at is not null),
         (select count(*) from public.metric_alerts),
         coalesce((cfg.v ->> 'alert_open_min_pct')::numeric, 30)
    from cfg
  union all
  select 3, 'engagement', 'Engagement', 'Publicaciones alertadas con click o guardado', 'pct',
         (select count(*) from alerted where engaged),
         (select count(*) from alerted),
         coalesce((cfg.v ->> 'engagement_min_pct')::numeric, 15)
    from cfg
  union all
  select 4, 'retention', 'Retención',
         format('Usuarios con búsqueda de %s+ semanas activos en los últimos 7 días',
                coalesce((cfg.v ->> 'retention_weeks')::integer, 3)),
         'pct',
         (select count(*) from eligible el
           where exists (select 1 from public.events e
                          where e.user_id = el.user_id and e.name <> 'alert_sent'
                            and e.created_at > now() - interval '7 days')),
         (select count(*) from eligible),
         coalesce((cfg.v ->> 'retention_min_pct')::numeric, 40)
    from cfg
  union all
  select 5, 'outcome', 'Outcome', 'Usuarios que contactaron, visitaron o compraron', 'users',
         (select count(*) from outcome_users o join public.metric_users mu on mu.id = o.user_id),
         null::bigint,
         coalesce((cfg.v ->> 'outcome_min_users')::numeric, 3)
    from cfg
  union all
  select 6, 'monetization', 'Monetización', 'Usuarios activos con intención de pago (lista de espera o plan pago)', 'pct',
         (select count(*) from active_users au
           where exists (select 1 from public.pro_waitlist w where w.user_id = au.user_id)
              or exists (select 1 from public.events e
                          where e.user_id = au.user_id and e.name = 'waitlist_joined')
              or exists (select 1 from public.profiles p
                          where p.id = au.user_id and p.plan <> 'free'
                            and (p.plan_expires_at is null or p.plan_expires_at >= now()))),
         (select count(*) from active_users),
         coalesce((cfg.v ->> 'payment_intent_min_pct')::numeric, 10)
    from cfg
)
select ordinal,
       criterion,
       label,
       metric,
       unit,
       numerator,
       denominator,
       case when unit = 'pct' then round(100.0 * numerator / nullif(denominator, 0), 1)
            else numerator::numeric end as value,
       threshold,
       coalesce(case when unit = 'pct' then round(100.0 * numerator / nullif(denominator, 0), 1)
                     else numerator::numeric end >= threshold, false) as met
  from criteria
 order by ordinal;

-- ---------------------------------------------------------------------------
-- Backoffice lists (sección 10)
-- ---------------------------------------------------------------------------

-- Usuarios: plan, searches, alerts per day (last 7 days), last activity.
create view public.admin_users with (security_invoker = true) as
select p.id,
       p.email,
       p.plan,
       p.plan_expires_at,
       p.role,
       p.created_at,
       p.telegram_chat_id is not null                       as telegram_linked,
       p.email is null                                      as telegram_only,
       (select count(*) from public.search_profiles sp where sp.user_id = p.id)                  as searches,
       (select count(*) from public.search_profiles sp where sp.user_id = p.id and sp.enabled)   as enabled_searches,
       (select count(distinct n.dedupe_key) from public.notifications n
         where n.user_id = p.id and n.kind <> 'digest' and n.status = 'sent'
           and n.sent_at > now() - interval '7 days')       as alerts_7d,
       (select max(e.created_at) from public.events e
         where e.user_id = p.id and e.name <> 'alert_sent') as last_activity_at,
       w.plan                                               as waitlist_plan
  from public.profiles p
  left join public.pro_waitlist w on w.user_id = p.id;

-- Búsquedas: filters, matches and alerts, bootstrap state.
create view public.admin_searches with (security_invoker = true) as
select sp.id,
       sp.user_id,
       p.email,
       sp.name,
       sp.filters,
       sp.enabled,
       sp.notification_frequency,
       sp.notify_min_level,
       sp.channels,
       sp.bootstrapped_at,
       sp.rematch_requested_at,
       sp.created_at,
       (select count(*) from public.matches m where m.search_profile_id = sp.id)                        as matches,
       (select count(*) from public.matches m where m.search_profile_id = sp.id and m.level = 'high')   as high_matches,
       (select count(distinct n.dedupe_key) from public.notifications n
         where n.search_profile_id = sp.id and n.kind <> 'digest' and n.status in ('sent', 'digest'))    as alerts
  from public.search_profiles sp
  join public.profiles p on p.id = sp.user_id;

-- Fuentes: health and the last 24 hours of collector_runs.
create view public.admin_source_health with (security_invoker = true) as
select s.id,
       s.name,
       s.enabled,
       s.crawl_interval_seconds,
       s.detail_interval_seconds,
       s.priority,
       s.consecutive_failures,
       s.last_ok_at,
       coalesce(r.runs, 0)       as runs_24h,
       coalesce(r.failed, 0)     as failed_24h,
       coalesce(r.found, 0)      as found_24h,
       coalesce(r.new, 0)        as new_24h,
       coalesce(r.updated, 0)    as updated_24h,
       r.avg_seconds             as avg_seconds_24h,
       last.started_at           as last_run_at,
       last.status               as last_run_status,
       last.error                as last_error
  from public.sources s
  left join lateral (
    select count(*) as runs,
           count(*) filter (where cr.status = 'failed') as failed,
           sum(cr.found) as found, sum(cr.new) as new, sum(cr.updated) as updated,
           round(avg(extract(epoch from cr.finished_at - cr.started_at))::numeric, 1) as avg_seconds
      from public.collector_runs cr
     where cr.source = s.id and cr.started_at > now() - interval '24 hours'
  ) r on true
  left join lateral (
    select cr.started_at, cr.status, cr.error
      from public.collector_runs cr
     where cr.source = s.id
     order by cr.started_at desc
     limit 1
  ) last on true;

-- Matches y scores: distribution by source, level and 10-point bucket.
create view public.admin_score_histogram with (security_invoker = true) as
select l.source,
       m.level,
       least(m.score / 10 * 10, 90)::integer as bucket,
       count(*)                              as matches
  from public.matches m
  join public.listings l on l.id = m.listing_id
 group by 1, 2, 3;

-- Notificaciones: per day and channel. degraded = over the daily cap (sección 7.1).
create view public.admin_notification_daily with (security_invoker = true) as
select (n.created_at at time zone 'America/Argentina/Buenos_Aires')::date as day,
       n.channel,
       count(*) filter (where n.status = 'sent' and n.kind <> 'digest') as sent,
       count(*) filter (where n.kind = 'digest' and n.status = 'sent')  as digests_sent,
       count(*) filter (where n.status = 'digest')                      as to_digest,
       count(*) filter (where n.payload ? 'degraded')                   as degraded,
       count(*) filter (where n.status = 'failed')                      as failed,
       count(*) filter (where n.status = 'queued')                      as queued,
       count(n.clicked_at)                                              as clicked
  from public.notifications n
 group by 1, 2;

-- ---------------------------------------------------------------------------
-- Grants: server-only (service role)
-- ---------------------------------------------------------------------------

revoke all on public.metric_users, public.metric_alert_rows, public.metric_alerts,
              public.v_north_star_weekly, public.v_activation, public.v_first_value,
              public.v_alert_funnel, public.v_high_score_engagement, public.v_alerts_per_user_day,
              public.v_outcomes, public.v_validation_criteria,
              public.admin_users, public.admin_searches, public.admin_source_health,
              public.admin_score_histogram, public.admin_notification_daily
  from anon, authenticated;

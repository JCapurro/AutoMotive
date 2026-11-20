-- Valor justo §6.3 (docs/superpowers/specs/2026-11-20-valor-justo-design.md):
-- the results page now logs search_results_viewed, the listing ids each page
-- showed. Looking at a list must not make anyone «active», so the event joins
-- alert_sent as the events that are not activity in:
--   * v_validation_criteria, criterion 4 (retention);
--   * admin_users.last_activity_at;
--   * v_north_star_weekly's active users (same «any event but alert_sent»
--     rule; not named in the design, left out for the same reason).
-- /admin's active days and retention (web/lib/admin-users-data.ts NOT_ACTIVITY)
-- are the web's side. Each view is its latest definition with only that
-- condition changed.

-- ---------------------------------------------------------------------------
-- v_validation_criteria: 20261119130000_x01_outcome_metric.sql's definition.
-- ---------------------------------------------------------------------------

create or replace view public.v_validation_criteria with (security_invoker = true) as
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
   where status in ('visit_scheduled', 'purchased')
  union
  select user_id from public.owned_vehicles
  union
  select user_id from public.events
   where name = 'listing_status_changed' and props ->> 'status' in ('visit_scheduled', 'purchased')
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
                          where e.user_id = el.user_id and e.name not in ('alert_sent', 'search_results_viewed')
                            and e.created_at > now() - interval '7 days')),
         (select count(*) from eligible),
         coalesce((cfg.v ->> 'retention_min_pct')::numeric, 40)
    from cfg
  union all
  select 5, 'outcome', 'Outcome', 'Usuarios que agendaron una visita o compraron', 'users',
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
-- admin_users: 20261029120000_email_only_accounts.sql's definition.
-- ---------------------------------------------------------------------------

create or replace view public.admin_users with (security_invoker = true) as
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
         where e.user_id = p.id and e.name not in ('alert_sent', 'search_results_viewed')) as last_activity_at,
       w.plan                                               as waitlist_plan,
       p.email_only
  from public.profiles p
  left join public.pro_waitlist w on w.user_id = p.id;

-- ---------------------------------------------------------------------------
-- v_north_star_weekly: 20261003120000_f6_backoffice_metrics.sql's definition.
-- ---------------------------------------------------------------------------

create or replace view public.v_north_star_weekly with (security_invoker = true) as
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
   where e.name not in ('alert_sent', 'search_results_viewed')
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

-- CREATE OR REPLACE keeps the grants; the server-only revoke (20261003) is repeated anyway.
revoke all on public.v_validation_criteria, public.admin_users, public.v_north_star_weekly from anon, authenticated;

notify pgrst, 'reload schema';

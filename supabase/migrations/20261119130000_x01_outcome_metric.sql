-- X-01 · criterio 5 sin «Contactado» (docs/BACKLOG_PRODUCTO_2026-10.md, ítem X-01;
-- diseño docs/superpowers/specs/2026-10-29-x01-seguimiento-design.md, decisión 2
-- aprobada por Juan).
--
-- With X-01 any user marks "Contactado" with one click, so criterion 5
-- (outcome) of v_validation_criteria counts only a scheduled visit or a
-- purchase: visit_scheduled / purchased in user_listing_interactions, an
-- owned_vehicles row, or the equivalent listing_status_changed events.
-- "Contactado" becomes a metric of its own, v_contacted_metric, shown in
-- /admin next to the criteria. outcome_min_users and the other five
-- criteria don't change; metric_alert_rows.saved (criterion 3) still counts
-- contacted as engagement.

-- ---------------------------------------------------------------------------
-- v_validation_criteria: 20261003120000_f6_backoffice_metrics.sql's definition;
-- only outcome_users and criterion 5's metric text change.
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
                          where e.user_id = el.user_id and e.name <> 'alert_sent'
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
-- v_contacted_metric: "Contactado" on its own. users = people (admins out)
-- with a listing in contacted now or a change to it; events = those changes.
-- ---------------------------------------------------------------------------

create view public.v_contacted_metric with (security_invoker = true) as
select (select count(*)
          from (select user_id from public.user_listing_interactions where status = 'contacted'
                union
                select user_id from public.events
                 where name = 'listing_status_changed' and props ->> 'status' = 'contacted') c
          join public.metric_users mu on mu.id = c.user_id) as users,
       (select count(*)
          from public.events e
          join public.metric_users mu on mu.id = e.user_id
         where e.name = 'listing_status_changed' and e.props ->> 'status' = 'contacted') as events;

-- Server-only, like the rest of the metrics (service role).
revoke all on public.v_contacted_metric from anon, authenticated;

notify pgrst, 'reload schema';

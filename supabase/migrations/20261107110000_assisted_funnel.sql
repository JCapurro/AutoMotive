-- Embudo del modo asistido (docs/TECHNICAL_PLAN.md, sección 8.4, medición).
--
-- One row per sign-up day (Buenos Aires) plus the total (signup_day null): the
-- accounts that completed sign-up that day and how many of them, ever since,
-- reached each step:
--
--   signup_completed → assisted_search_requested → assisted_review_shown
--     → search_profile_created
--
-- next to what explains the drop-offs: the manual form after a failed read
-- (assisted_fallback_shown), searches saved without touching Guardar
-- (search_profile_created with mode 'assisted_auto'), refused creations
-- (search_save_failed) and email-only sign-ups that reached the new-search page
-- without their prompt (search_intent_missing). Admins are left out
-- (metric_users), like every other metric.
--
-- security_invoker and closed to anon/authenticated: /admin reads it with the
-- service role after checking profiles.role = 'admin' (as the f6 v_* views).

create view public.v_assisted_funnel with (security_invoker = true) as
with signups as (
  select e.user_id,
         min(e.created_at) as signed_up_at,
         bool_or(e.props ->> 'method' = 'email_only') as email_only
    from public.events e
    join public.metric_users mu on mu.id = e.user_id
   where e.name = 'signup_completed'
   group by e.user_id
),
steps as (
  select s.user_id,
         (s.signed_up_at at time zone 'America/Argentina/Buenos_Aires')::date as signup_day,
         s.email_only,
         bool_or(e.name = 'assisted_search_requested')                           as requested,
         bool_or(e.name = 'assisted_review_shown')                               as review_shown,
         bool_or(e.name = 'assisted_fallback_shown')                             as fallback_shown,
         bool_or(e.name = 'search_profile_created')                              as created,
         bool_or(e.name = 'search_profile_created'
                 and e.props ->> 'mode' in ('assisted', 'assisted_auto', 'assisted_fallback')) as created_assisted,
         bool_or(e.name = 'search_profile_created' and e.props ->> 'mode' = 'assisted_auto') as autosaved,
         bool_or(e.name = 'search_save_failed')                                  as save_failed,
         bool_or(e.name = 'search_intent_missing')                               as intent_missing
    from signups s
    left join public.events e
      on e.user_id = s.user_id
     and e.created_at >= s.signed_up_at
     and e.name in ('assisted_search_requested', 'assisted_review_shown', 'assisted_fallback_shown',
                    'search_profile_created', 'search_save_failed', 'search_intent_missing')
   group by s.user_id, s.signed_up_at, s.email_only
)
select signup_day,
       count(*)                                         as signed_up,
       count(*) filter (where email_only)               as email_only,
       count(*) filter (where requested)                as assisted_requested,
       count(*) filter (where review_shown)             as review_shown,
       count(*) filter (where created)                  as search_created,
       count(*) filter (where created_assisted)         as search_created_assisted,
       count(*) filter (where autosaved)                as autosaved,
       count(*) filter (where fallback_shown)           as fallback_shown,
       count(*) filter (where save_failed)              as save_failed,
       count(*) filter (where intent_missing)           as intent_missing,
       round(100.0 * count(*) filter (where review_shown and created)
                   / nullif(count(*) filter (where review_shown), 0), 1) as review_to_search_pct
  from steps
 group by grouping sets ((signup_day), ())
 order by signup_day desc nulls last;

comment on view public.v_assisted_funnel is
  'Embudo del modo asistido por día de alta: signup → pedido asistido → revisión → búsqueda creada (sección 8.4). Solo service_role.';

revoke all on public.v_assisted_funnel from anon, authenticated;

-- Trusted profile administrators have permanent access without commercial caps.
-- Preserve ordinary users' trial, payment, expiry and plan limits.
create or replace function public.plan_limits_for(p_user uuid) returns jsonb
language sql stable security definer set search_path = '' as $$
  with cfg as (
    select coalesce((select value from public.app_config where key = 'plan_limits'), '{}') v
  ), access as (
    select p.*, coalesce((cfg.v->>'enforced')::boolean, false) enforced,
           p.plan <> 'free' and (p.plan_expires_at is null or p.plan_expires_at > now()) paid,
           p.free_trial_started_at + interval '72 hours' trial_end
    from public.profiles p cross join cfg where p.id = p_user
  ), resolved as (
    select *, case when role = 'admin' then 'pro' when paid then plan::text else 'free' end effective_plan,
           case when role = 'admin' then 'paid' when not enforced then 'pilot' when paid then 'paid'
                when free_trial_started_at is null then 'available'
                when trial_end > now() then 'trial' else 'expired' end state
    from access
  )
  select coalesce((select jsonb_build_object(
    'plan', r.effective_plan, 'enforced', r.enforced,
    'active', r.state in ('pilot', 'paid', 'trial'), 'state', r.state,
    'trial_started_at', r.free_trial_started_at, 'trial_expires_at', r.trial_end,
    'expires_at', case when r.role = 'admin' then null when r.paid then r.plan_expires_at else r.trial_end end,
    'limits', case when r.role = 'admin' then '{"immediate_alerts":true}'::jsonb
                   else coalesce(cfg.v->r.effective_plan, '{}') end,
    'active_searches', (select count(*) from public.search_profiles sp where sp.user_id = p_user and sp.enabled))
    from resolved r cross join cfg),
    '{"plan":"free","enforced":true,"active":false,"state":"expired","limits":{"max_profiles":0}}'::jsonb)
$$;

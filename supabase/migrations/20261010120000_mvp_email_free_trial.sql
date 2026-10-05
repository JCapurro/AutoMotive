-- Web/email MVP. Replacing the legacy Telegram default preserves explicit
-- web-only preferences (including email opt-outs).
alter table public.profiles alter column default_channels set default '{email,web}';
alter table public.search_profiles alter column channels set default '{email,web}';

update public.profiles
set default_channels = array_replace(default_channels, 'telegram', 'email')
where 'telegram' = any(default_channels) and not ('email' = any(default_channels)) and email is not null;
update public.profiles set default_channels = array_remove(default_channels, 'telegram')
where 'telegram' = any(default_channels);
update public.search_profiles sp
set channels = array_replace(sp.channels, 'telegram', 'email')
from public.profiles p
where p.id = sp.user_id and 'telegram' = any(sp.channels)
  and not ('email' = any(sp.channels)) and 'email' = any(p.default_channels);
update public.search_profiles set channels = array_remove(channels, 'telegram')
where 'telegram' = any(channels);

-- Opening the free trial must not open paid enrollment. Rollout is explicit,
-- admin-only and idempotent; migration alone never starts the trial clock.
create function public.enable_free_trial() returns jsonb
language plpgsql security definer set search_path = '' as $$
declare v_actor uuid := (select auth.uid()); v_started int; v_paused int;
begin
  if coalesce((select auth.role()), '') <> 'service_role'
    and not exists(select 1 from public.profiles where id = v_actor and role = 'admin') then
    raise exception 'admin_required' using errcode = '42501'; end if;
  perform 1 from public.app_config where key = 'plan_limits' for update;
  if coalesce((select (value->>'enforced')::boolean from public.app_config where key = 'plan_limits'), false) then
    return jsonb_build_object('already_enabled',true); end if;
  with started as (
    update public.profiles p set free_trial_started_at = now()
      where p.free_trial_started_at is null and p.plan = 'free'
        and exists(select 1 from public.search_profiles sp where sp.user_id = p.id and sp.enabled)
      returning p.id
  ) insert into public.events(user_id, name, props)
    select id, 'free_trial_started', jsonb_build_object('rollout',true, 'expires_at', now() + interval '72 hours') from started;
  get diagnostics v_started = row_count;
  update public.app_config set value = jsonb_set(value,'{enforced}','true') where key = 'plan_limits';
  v_paused := public.expire_commercial_access();
  insert into public.events(user_id, name, props) values(v_actor, 'free_trial_enabled',
    jsonb_build_object('trials_started',v_started, 'searches_paused',v_paused));
  return jsonb_build_object('trials_started',v_started, 'searches_paused',v_paused);
end $$;
revoke all on function public.enable_free_trial() from public, anon;
grant execute on function public.enable_free_trial() to authenticated;
grant execute on function public.enable_free_trial() to service_role;

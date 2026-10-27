-- Writes and their audit record commit together. Only the server's service client
-- can call this invoker function, after requireAdmin has obtained the actor.
create table public.admin_config_audit (
  id bigint generated always as identity primary key,
  target_type text not null check (target_type in ('app_config', 'sources')),
  target_key text not null,
  actor_id uuid not null,
  actor_email text,
  before_value jsonb not null,
  after_value jsonb not null,
  created_at timestamptz not null default now()
);
create index admin_config_audit_target_idx on public.admin_config_audit (target_type, target_key, created_at desc, id desc);
alter table public.admin_config_audit enable row level security;
revoke all on public.admin_config_audit from public, anon, authenticated, service_role;
grant select, insert on public.admin_config_audit to service_role;
revoke all on sequence public.admin_config_audit_id_seq from public, anon, authenticated, service_role;
grant usage, select on sequence public.admin_config_audit_id_seq to service_role;

create function public.admin_update_setting(
  p_target_type text, p_target_key text, p_expected jsonb, p_value jsonb, p_actor_id uuid
) returns bigint
language plpgsql security invoker set search_path = '' as $$
declare
  v_before jsonb;
  v_email text;
  v_id bigint;
begin
  select email into v_email from public.profiles where id = p_actor_id and role = 'admin';
  if not found then raise exception 'admin_required' using errcode = '42501'; end if;
  if p_expected is null or p_value is null or p_value = 'null'::jsonb
     or p_target_key is null or p_target_key = '' then
    raise exception 'invalid_setting' using errcode = '22023';
  end if;

  if p_target_type = 'app_config' then
    if p_target_key = 'commercial_pilot' then raise exception 'commercial_pilot_requires_billing' using errcode = '22023'; end if;
    select value into v_before from public.app_config where key = p_target_key for update;
    if not found then raise exception 'setting_not_found' using errcode = 'P0002'; end if;
    if v_before is distinct from p_expected then raise exception 'setting_conflict' using errcode = '40001'; end if;
    if jsonb_typeof(v_before) is distinct from jsonb_typeof(p_value) then raise exception 'invalid_setting_shape' using errcode = '22023'; end if;
    if p_target_key = 'plan_limits' and (v_before->'enforced') is distinct from (p_value->'enforced') then
      raise exception 'commercial_pilot_requires_billing' using errcode = '22023';
    end if;
    update public.app_config set value = p_value where key = p_target_key;
  elsif p_target_type = 'sources' then
    if jsonb_typeof(p_value) is distinct from 'object'
       or jsonb_typeof(p_value->'enabled') is distinct from 'boolean'
       or jsonb_typeof(p_value->'crawl_interval_seconds') is distinct from 'number' then
      raise exception 'invalid_source' using errcode = '22023';
    end if;
    if (select count(*) from jsonb_object_keys(p_value)) <> 2
       or (p_value->>'crawl_interval_seconds')::numeric not between 60 and 86400
       or (p_value->>'crawl_interval_seconds')::numeric % 1 <> 0 then
      raise exception 'invalid_source' using errcode = '22023';
    end if;
    select jsonb_build_object('enabled', enabled, 'crawl_interval_seconds', crawl_interval_seconds)
      into v_before from public.sources where id = p_target_key for update;
    if not found then raise exception 'setting_not_found' using errcode = 'P0002'; end if;
    if v_before is distinct from p_expected then raise exception 'setting_conflict' using errcode = '40001'; end if;
    update public.sources set enabled = (p_value->>'enabled')::boolean,
      crawl_interval_seconds = (p_value->>'crawl_interval_seconds')::integer where id = p_target_key;
  else
    raise exception 'invalid_setting_target' using errcode = '22023';
  end if;

  insert into public.admin_config_audit (target_type, target_key, actor_id, actor_email, before_value, after_value)
  values (p_target_type, p_target_key, p_actor_id, v_email, v_before, p_value) returning id into v_id;
  return v_id;
end;
$$;
revoke all on function public.admin_update_setting(text, text, jsonb, jsonb, uuid) from public, anon, authenticated;
grant execute on function public.admin_update_setting(text, text, jsonb, jsonb, uuid) to service_role;
comment on function public.admin_update_setting(text, text, jsonb, jsonb, uuid) is
  'Admin-only server write: row lock, expected-value comparison, update and immutable before/after audit in one transaction.';
notify pgrst, 'reload schema';

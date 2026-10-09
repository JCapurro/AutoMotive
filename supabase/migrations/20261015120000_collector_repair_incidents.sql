-- Persist collector incidents even when the local Codex monitor is offline.
-- This queue is private: only the server and local privileged worker use it.
create table public.collector_repair_incidents (
  id uuid primary key default gen_random_uuid(),
  source text not null references public.sources(id),
  problem text not null check (btrim(problem) <> ''),
  health_checked_at timestamptz not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  resolved_at timestamptz,
  status text not null default 'pending'
    check (status in ('pending', 'dispatching', 'open', 'needs_input', 'resolved', 'cancelled')),
  claim_token uuid,
  lease_owner text,
  lease_expires_at timestamptz,
  thread_id text check (thread_id is null or btrim(thread_id) <> ''),
  note text,
  check ((resolved_at is null and status in ('pending', 'dispatching', 'open', 'needs_input'))
    or (resolved_at is not null and status in ('resolved', 'cancelled')))
);
create unique index collector_repair_one_active_source
  on public.collector_repair_incidents(source) where resolved_at is null;
create index collector_repair_dispatch_queue
  on public.collector_repair_incidents(created_at, id)
  where resolved_at is null and thread_id is null;

alter table public.collector_repair_incidents enable row level security;
revoke all on public.collector_repair_incidents from public, anon, authenticated, service_role;
grant select, insert, update on public.collector_repair_incidents to service_role;

-- Shared by the trigger and the initial backfill. A missing/failed base check,
-- stale snapshot or implausible future timestamp means unknown health.
create function public.capture_collector_repairs(p_checked_at timestamptz, p_checks jsonb)
returns void language plpgsql security invoker set search_path = '' as $$
begin
  if p_checked_at is null
    or p_checked_at <= clock_timestamp() - interval '12 minutes'
    or p_checked_at > clock_timestamp() + interval '1 minute'
    or not coalesce(p_checks ? 'base' and p_checks->'base' = 'null'::jsonb, false) then
    return;
  end if;

  -- Keep the reservation token and chat association after recovery, including
  -- recovery between chat creation and attach by the local monitor.
  update public.collector_repair_incidents r
    set status = case when s.enabled and p_checks ? ('collector:' || r.source)
        then 'resolved' else 'cancelled' end,
        resolved_at = clock_timestamp(), updated_at = clock_timestamp(),
        health_checked_at = p_checked_at
    from public.sources s
    where r.source = s.id and r.resolved_at is null
      and (not s.enabled or not p_checks ? ('collector:' || r.source)
        or p_checks->('collector:' || r.source) = 'null'::jsonb);

  insert into public.collector_repair_incidents(source, problem, health_checked_at)
  select s.id, c.value #>> '{}', p_checked_at
  from jsonb_each(p_checks) c join public.sources s on c.key = 'collector:' || s.id
  where s.enabled and jsonb_typeof(c.value) = 'string' and btrim(c.value #>> '{}') <> ''
  on conflict (source) where resolved_at is null do update
    set problem = excluded.problem, health_checked_at = excluded.health_checked_at,
        updated_at = clock_timestamp();
end $$;
revoke all on function public.capture_collector_repairs(timestamptz, jsonb)
  from public, anon, authenticated;
grant execute on function public.capture_collector_repairs(timestamptz, jsonb) to service_role;

create function public.capture_collector_repairs_on_health()
returns trigger language plpgsql security invoker set search_path = '' as $$
begin
  perform public.capture_collector_repairs(new.checked_at, new.checks);
  return new;
end $$;
revoke all on function public.capture_collector_repairs_on_health() from public, anon, authenticated;
grant execute on function public.capture_collector_repairs_on_health() to service_role;

create trigger platform_health_capture_collector_repairs
after insert or update of checked_at, checks on public.platform_health_checks
for each row execute function public.capture_collector_repairs_on_health();

select public.capture_collector_repairs(checked_at, checks) from public.platform_health_checks;

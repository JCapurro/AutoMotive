-- F5: modo asistido con LLM (docs/TECHNICAL_PLAN.md, sección 8).
--
-- * llm_jobs joins the supabase_realtime publication: the web waits for its
--   job's result without polling (RLS: only the owner's rows arrive).
-- * parse_search input is {"text": "..."} with 3–1000 characters.
-- * A per-user hourly cap on jobs (app_config.llm_limits): each job is a
--   `claude -p` call on the worker's host.
-- * llm_job_stats: volume, failures and latency p50/p95 per provider (server-only).

-- ---------------------------------------------------------------------------
-- Realtime
-- ---------------------------------------------------------------------------

do $$
begin
  if exists (select 1 from pg_publication where pubname = 'supabase_realtime') then
    alter publication supabase_realtime add table public.llm_jobs;
  end if;
end;
$$;

-- ---------------------------------------------------------------------------
-- Input shape
-- ---------------------------------------------------------------------------

-- coalesce: without a "text" key the expression is null, which a check lets through.
alter table public.llm_jobs add constraint llm_jobs_parse_search_input check (
  kind <> 'parse_search'
  or coalesce(jsonb_typeof(input -> 'text') = 'string'
              and char_length(btrim(input ->> 'text')) between 3 and 1000, false)
);

create index llm_jobs_running_idx on public.llm_jobs (started_at) where status = 'running';

-- ---------------------------------------------------------------------------
-- Rate limit: app_config.llm_limits.per_user_hour jobs per user and hour.
-- ---------------------------------------------------------------------------

insert into public.app_config (key, value) values
  ('llm_limits', '{"per_user_hour": 30}')
on conflict (key) do nothing;

create function public.enforce_llm_rate_limit() returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_max   integer;
  v_count integer;
begin
  select (value ->> 'per_user_hour')::integer into v_max
    from public.app_config where key = 'llm_limits';
  if v_max is null then
    return new;
  end if;

  select count(*) into v_count
    from public.llm_jobs
   where user_id = new.user_id and created_at > now() - interval '1 hour';
  if v_count >= v_max then
    raise exception 'llm_rate_limited'
      using errcode = 'P0001',
            detail  = format('%s LLM jobs in the last hour (max %s)', v_count, v_max);
  end if;
  return new;
end;
$$;

create trigger llm_jobs_enforce_rate_limit before insert on public.llm_jobs
  for each row execute function public.enforce_llm_rate_limit();

revoke execute on function public.enforce_llm_rate_limit() from public, anon, authenticated;

-- ---------------------------------------------------------------------------
-- Latency (F5 acceptance: "la latencia p95 queda registrada"). The admin
-- (F6) reads it with the service role, next to the local LLM's numbers.
-- ---------------------------------------------------------------------------

create view public.llm_job_stats with (security_invoker = true) as
select provider,
       kind,
       date_trunc('day', created_at)                                   as day,
       count(*)                                                        as jobs,
       count(*) filter (where status = 'done')                         as done,
       count(*) filter (where status = 'failed')                       as failed,
       percentile_cont(0.5)  within group (order by latency_ms)
         filter (where latency_ms is not null)                         as latency_p50_ms,
       percentile_cont(0.95) within group (order by latency_ms)
         filter (where latency_ms is not null)                         as latency_p95_ms,
       max(latency_ms)                                                 as latency_max_ms
  from public.llm_jobs
 where provider is not null
 group by provider, kind, date_trunc('day', created_at);

revoke all on public.llm_job_stats from anon, authenticated;

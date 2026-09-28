-- F7, punto 8: the worker's heartbeat. One row the worker updates every
-- minute; the admin shows it and tools/watchdog.py (a scheduled task outside
-- the worker) alerts the admin when it goes stale — the source alerts live
-- inside the worker and die with it.
create table public.worker_heartbeat (
  id         smallint primary key default 1 check (id = 1),
  started_at timestamptz not null,
  beat_at    timestamptz not null default now(),
  host       text,
  pid        integer
);

-- No client access (like collector_runs): the admin reads it with the service role.
alter table public.worker_heartbeat enable row level security;
revoke all on public.worker_heartbeat from anon, authenticated;

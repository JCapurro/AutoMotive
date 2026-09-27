-- Row Level Security (docs/TECHNICAL_PLAN.md, sección 4.4).
--
-- RLS is enabled on every table. A table with RLS and no policy for a role is closed
-- to that role, which is how the server-only tables (app_config, collector_runs,
-- pipeline_errors, crawl_targets, geocode_cache, fx_rates) are kept away from clients.
-- The worker and the admin backoffice use privileged connections that bypass RLS.
--
-- Policies call (select auth.uid()) so Postgres evaluates it once per statement.

alter table public.profiles                  enable row level security;
alter table public.sources                   enable row level security;
alter table public.vehicle_catalog           enable row level security;
alter table public.search_profiles           enable row level security;
alter table public.crawl_targets             enable row level security;
alter table public.listings                  enable row level security;
alter table public.listing_snapshots         enable row level security;
alter table public.matches                   enable row level security;
alter table public.user_listing_interactions enable row level security;
alter table public.owned_vehicles            enable row level security;
alter table public.notifications             enable row level security;
alter table public.events                    enable row level security;
alter table public.llm_jobs                  enable row level security;
alter table public.collector_runs            enable row level security;
alter table public.pipeline_errors           enable row level security;
alter table public.app_config                enable row level security;
alter table public.geocode_cache             enable row level security;
alter table public.fx_rates                  enable row level security;

-- Nothing here is public: anonymous visitors only see the landing page.
revoke all on all tables in schema public from anon;

-- ---------------------------------------------------------------------------
-- profiles: own row. plan, role and the Telegram link are managed server-side.
-- ---------------------------------------------------------------------------

create policy "profiles: read own" on public.profiles
  for select to authenticated using (id = (select auth.uid()));
create policy "profiles: update own" on public.profiles
  for update to authenticated using (id = (select auth.uid())) with check (id = (select auth.uid()));

revoke insert, update, delete on public.profiles from authenticated;
grant update (phone, default_origin_lat, default_origin_lon, default_origin_label)
  on public.profiles to authenticated;

-- ---------------------------------------------------------------------------
-- Reference data: readable by any signed-in user (forms, autocomplete).
-- ---------------------------------------------------------------------------

create policy "sources: authenticated read" on public.sources
  for select to authenticated using (true);
create policy "vehicle_catalog: authenticated read" on public.vehicle_catalog
  for select to authenticated using (true);
revoke insert, update, delete on public.sources, public.vehicle_catalog from authenticated;

-- ---------------------------------------------------------------------------
-- Owner-only tables: user_id = auth.uid()
-- ---------------------------------------------------------------------------

create policy "search_profiles: own rows" on public.search_profiles
  for all to authenticated
  using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));

create policy "user_listing_interactions: own rows" on public.user_listing_interactions
  for all to authenticated
  using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));

create policy "owned_vehicles: own rows" on public.owned_vehicles
  for all to authenticated
  using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));

-- Notifications are written by the worker; the user only marks them opened/clicked.
create policy "notifications: read own" on public.notifications
  for select to authenticated using (user_id = (select auth.uid()));
create policy "notifications: update own" on public.notifications
  for update to authenticated
  using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));
revoke insert, update, delete on public.notifications from authenticated;
grant update (opened_at, clicked_at) on public.notifications to authenticated;

-- Events are append-only from the client.
create policy "events: read own" on public.events
  for select to authenticated using (user_id = (select auth.uid()));
create policy "events: insert own" on public.events
  for insert to authenticated with check (user_id = (select auth.uid()));
revoke update, delete on public.events from authenticated;

-- LLM jobs: the web enqueues (kind + input); the worker fills in the rest.
create policy "llm_jobs: read own" on public.llm_jobs
  for select to authenticated using (user_id = (select auth.uid()));
create policy "llm_jobs: enqueue own" on public.llm_jobs
  for insert to authenticated with check (user_id = (select auth.uid()) and status = 'queued');
revoke insert, update, delete on public.llm_jobs from authenticated;
grant insert (user_id, kind, input) on public.llm_jobs to authenticated;

-- ---------------------------------------------------------------------------
-- Worker-written, user-readable
-- ---------------------------------------------------------------------------

create policy "listings: authenticated read" on public.listings
  for select to authenticated using (true);
create policy "listing_snapshots: authenticated read" on public.listing_snapshots
  for select to authenticated using (true);
revoke insert, update, delete on public.listings, public.listing_snapshots from authenticated;

create policy "matches: read through own profiles" on public.matches
  for select to authenticated using (
    exists (
      select 1 from public.search_profiles sp
      where sp.id = search_profile_id and sp.user_id = (select auth.uid())
    )
  );
revoke insert, update, delete on public.matches from authenticated;

-- ---------------------------------------------------------------------------
-- Server-only: no policies, no grants.
-- ---------------------------------------------------------------------------

revoke all on public.app_config, public.collector_runs, public.pipeline_errors,
              public.crawl_targets, public.geocode_cache, public.fx_rates
  from authenticated;

-- ---------------------------------------------------------------------------
-- Plan limits (§33): a before-insert trigger on search_profiles.
-- With plan_limits.enforced = false (the pilot) it only records plan_limit_hit;
-- with enforced = true it rejects the insert (and the event rolls back with it).
-- ---------------------------------------------------------------------------

create function public.enforce_plan_limits() returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
  cfg      jsonb;
  v_plan   text;
  v_max    integer;
  v_count  integer;
  enforced boolean;
begin
  select value into cfg from public.app_config where key = 'plan_limits';
  if cfg is null then
    return new;
  end if;

  -- An expired Pro/Search Pass falls back to the free limits.
  select case
           when p.plan <> 'free' and p.plan_expires_at is not null and p.plan_expires_at < now()
             then 'free'
           else p.plan::text
         end
    into v_plan
    from public.profiles p
   where p.id = new.user_id;

  v_max := (cfg -> coalesce(v_plan, 'free') ->> 'max_profiles')::integer;
  if v_max is null then
    return new;
  end if;

  select count(*) into v_count from public.search_profiles where user_id = new.user_id;
  if v_count < v_max then
    return new;
  end if;

  enforced := coalesce((cfg ->> 'enforced')::boolean, false);
  insert into public.events (user_id, name, props)
  values (new.user_id, 'plan_limit_hit', jsonb_build_object(
    'limit', 'max_profiles', 'plan', coalesce(v_plan, 'free'),
    'max', v_max, 'current', v_count, 'enforced', enforced));

  if enforced then
    raise exception 'plan_limit_exceeded'
      using errcode = 'P0001',
            detail  = format('plan %s allows %s search profiles', coalesce(v_plan, 'free'), v_max);
  end if;
  return new;
end;
$$;

create trigger search_profiles_enforce_plan_limits before insert on public.search_profiles
  for each row execute function public.enforce_plan_limits();

-- Trigger/definer functions are not an API surface.
revoke execute on function public.enforce_plan_limits() from public, anon, authenticated;
revoke execute on function public.handle_new_user() from public, anon, authenticated;

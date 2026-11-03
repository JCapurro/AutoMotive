-- PAR-04 · Guías por modelo y preguntas específicas
-- (docs/BACKLOG_PRODUCTO_2026-10.md, ítem PAR-04; diseño
-- docs/superpowers/specs/2026-11-03-par04-guias-design.md, decisiones 1 a 6).
--
-- * model_guides: one guide per (make, model, generation), five fixed
--   sections, questions, sources and draft | published. anon and
--   authenticated read only published rows and only the public columns.
--   Nobody but service_role writes: the admin web writes through the
--   admin_* RPCs below (security definer, granted to service_role only, with
--   p_actor_id checked against profiles.role = 'admin').
-- * llm_jobs gains kind 'model_guide'. It is not a system job: the admin who
--   asks for the draft is its user_id (llm_jobs.user_id stays NOT NULL).
--   Users cannot enqueue it themselves (the "enqueue own" policy excludes it)
--   and the per-user hourly limit ignores it: it has its own caps in
--   app_config.llm_limits.model_guide, checked by admin_request_model_guide.
-- * app_config.llm_limits.model_guide starts with enabled = false: the
--   generation stays off until Juan approves the provider and the caps.
--   Writing a guide by hand works either way.
--
-- Does not apply or depend on 20261107130000_timing_chain_catalog.sql (still
-- NOT APPLIED in production). Applies on an empty base after the earlier
-- migrations; the web of main does not read any of it.

-- ---------------------------------------------------------------------------
-- model_guides
-- ---------------------------------------------------------------------------

create table public.model_guides (
  id               bigint generated always as identity primary key,
  make             text not null check (char_length(make) between 1 and 80),
  model            text not null check (char_length(model) between 1 and 80),
  generation_label text check (generation_label is null or char_length(generation_label) between 1 and 80),
  year_from        integer check (year_from between 1950 and 2100),
  year_to          integer check (year_to between 1950 and 2100),
  slug_make        text not null check (slug_make ~ '^[a-z0-9]+(-[a-z0-9]+)*$'),
  slug_model       text not null check (slug_model ~ '^[a-z0-9]+(-[a-z0-9]+)*$'),
  body             jsonb not null default '{}' check (jsonb_typeof(body) = 'object'),
  questions        jsonb not null default '[]' check (jsonb_typeof(questions) = 'array'),
  sources          jsonb not null default '[]' check (jsonb_typeof(sources) = 'array'),
  status           text not null default 'draft' check (status in ('draft', 'published')),
  origin           text not null default 'manual' check (origin in ('manual', 'llm')),
  llm_job_id       bigint references public.llm_jobs (id) on delete set null,
  -- "<provider>|<prompt version>", e.g. "openai:gpt-6-luna|model_guide-v1".
  llm_version      text,
  generated_at     timestamptz,
  reviewed_by      uuid references public.profiles (id) on delete set null,
  reviewed_at      timestamptz,
  published_at     timestamptz,
  created_at       timestamptz not null default now(),
  updated_at       timestamptz not null default now(),
  constraint model_guides_years check (year_to is null or year_from is null or year_to >= year_from),
  constraint model_guides_unique unique nulls not distinct (make, model, generation_label),
  constraint model_guides_slug_unique unique nulls not distinct (slug_make, slug_model, generation_label),
  constraint model_guides_published_reviewed
    check (status = 'draft' or (reviewed_at is not null and published_at is not null))
);
comment on table public.model_guides is
  'PAR-04: guías orientativas por modelo. Solo las published se leen fuera del admin; la IA escribe solo borradores.';

create index model_guides_published_idx on public.model_guides (slug_make, slug_model) where status = 'published';
create index model_guides_make_model_idx on public.model_guides (lower(make), lower(model));

create trigger model_guides_set_updated_at before update on public.model_guides
  for each row execute function public.set_updated_at();

alter table public.model_guides enable row level security;

-- Only the public columns, only published rows. reviewed_by, origin,
-- llm_job_id, llm_version, generated_at and the drafts never leave the admin.
revoke all on public.model_guides from public, anon, authenticated;
grant select (id, make, model, generation_label, year_from, year_to, slug_make, slug_model,
              body, questions, sources, published_at, updated_at)
  on public.model_guides to anon, authenticated;
create policy "model_guides: read published" on public.model_guides
  for select to anon, authenticated using (status = 'published');

-- Why a guide cannot be published as it stands, or null. The five sections
-- must have at least one line, the questions 3 to 8, and every source must
-- be checked by the reviewer (the ones the LLM suggests may not exist).
create function public.model_guide_problem(p_body jsonb, p_questions jsonb, p_sources jsonb)
returns text language sql immutable set search_path = '' as $$
  select case
    when jsonb_typeof(p_body) is distinct from 'object' then 'guide_incomplete'
    when exists (select 1 from unnest(array['known_issues', 'visit_checklist', 'versions_equipment',
                                            'maintenance_costs', 'generations']) k
                  where jsonb_typeof(p_body -> k) is distinct from 'array'
                     or jsonb_array_length(p_body -> k) = 0) then 'guide_incomplete'
    when jsonb_typeof(p_questions) is distinct from 'array'
      or jsonb_array_length(p_questions) not between 3 and 8 then 'guide_incomplete'
    when jsonb_typeof(p_sources) is distinct from 'array' then 'guide_incomplete'
    when exists (select 1 from jsonb_array_elements(p_sources) s
                  where (s -> 'verified') is distinct from 'true'::jsonb) then 'guide_sources_unverified'
    else null
  end
$$;
revoke all on function public.model_guide_problem(jsonb, jsonb, jsonb) from public, anon, authenticated;
grant execute on function public.model_guide_problem(jsonb, jsonb, jsonb) to service_role;

-- ---------------------------------------------------------------------------
-- Admin writes
-- ---------------------------------------------------------------------------

-- Creates (p_id null) or edits a guide. The make and model must be a model
-- row of vehicle_catalog (trim is null) and are stored with its spelling, so
-- the guide crosses with listings.catalog_model. p_expected_updated_at
-- guards against overwriting another edit (like admin_update_setting). A
-- published guide may be edited only into a publishable state; the editor
-- counts as its reviewer.
create function public.admin_save_model_guide(
  p_id bigint, p_values jsonb, p_expected_updated_at timestamptz, p_actor_id uuid
) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare
  v_make text;
  v_model text;
  v_row public.model_guides;
  v_problem text;
begin
  if not exists (select 1 from public.profiles where id = p_actor_id and role = 'admin') then
    raise exception 'admin_required' using errcode = '42501';
  end if;
  if jsonb_typeof(p_values) is distinct from 'object' then
    raise exception 'invalid_guide' using errcode = '22023';
  end if;
  select vc.make, vc.model into v_make, v_model
    from public.vehicle_catalog vc
   where vc.trim is null
     and lower(vc.make) = lower(btrim(p_values ->> 'make'))
     and lower(vc.model) = lower(btrim(p_values ->> 'model'));
  if not found then raise exception 'guide_unknown_model' using errcode = '22023'; end if;

  if p_id is null then
    insert into public.model_guides (make, model, generation_label, year_from, year_to, slug_make, slug_model,
                                     body, questions, sources)
    values (v_make, v_model, nullif(btrim(p_values ->> 'generation_label'), ''),
            (p_values ->> 'year_from')::integer, (p_values ->> 'year_to')::integer,
            p_values ->> 'slug_make', p_values ->> 'slug_model',
            coalesce(p_values -> 'body', '{}'), coalesce(p_values -> 'questions', '[]'),
            coalesce(p_values -> 'sources', '[]'))
    returning * into v_row;
  else
    select * into v_row from public.model_guides where id = p_id for update;
    if not found then raise exception 'guide_not_found' using errcode = 'P0002'; end if;
    if p_expected_updated_at is null or v_row.updated_at is distinct from p_expected_updated_at then
      raise exception 'guide_conflict' using errcode = '40001';
    end if;
    if v_row.status = 'published' then
      v_problem := public.model_guide_problem(coalesce(p_values -> 'body', '{}'),
                                              coalesce(p_values -> 'questions', '[]'),
                                              coalesce(p_values -> 'sources', '[]'));
      if v_problem is not null then raise exception '%', v_problem using errcode = '22023'; end if;
    end if;
    update public.model_guides
       set make = v_make, model = v_model,
           generation_label = nullif(btrim(p_values ->> 'generation_label'), ''),
           year_from = (p_values ->> 'year_from')::integer,
           year_to = (p_values ->> 'year_to')::integer,
           slug_make = p_values ->> 'slug_make', slug_model = p_values ->> 'slug_model',
           body = coalesce(p_values -> 'body', '{}'),
           questions = coalesce(p_values -> 'questions', '[]'),
           sources = coalesce(p_values -> 'sources', '[]'),
           reviewed_by = case when status = 'published' then p_actor_id else reviewed_by end,
           reviewed_at = case when status = 'published' then now() else reviewed_at end
     where id = p_id
    returning * into v_row;
  end if;
  return jsonb_build_object('id', v_row.id, 'updated_at', v_row.updated_at, 'status', v_row.status,
                            'slug_make', v_row.slug_make, 'slug_model', v_row.slug_model);
exception
  when unique_violation then raise exception 'guide_duplicate' using errcode = '23505';
end;
$$;

-- Publishing records the reviewer; unpublishing goes back to draft and keeps
-- the last review. Nothing is published incomplete or with unchecked sources.
create function public.admin_set_model_guide_status(p_id bigint, p_status text, p_actor_id uuid)
returns jsonb
language plpgsql security definer set search_path = '' as $$
declare
  v_row public.model_guides;
  v_problem text;
begin
  if not exists (select 1 from public.profiles where id = p_actor_id and role = 'admin') then
    raise exception 'admin_required' using errcode = '42501';
  end if;
  if p_status is null or p_status not in ('draft', 'published') then
    raise exception 'invalid_guide_status' using errcode = '22023';
  end if;
  select * into v_row from public.model_guides where id = p_id for update;
  if not found then raise exception 'guide_not_found' using errcode = 'P0002'; end if;
  if p_status = 'published' then
    v_problem := public.model_guide_problem(v_row.body, v_row.questions, v_row.sources);
    if v_problem is not null then raise exception '%', v_problem using errcode = '22023'; end if;
    update public.model_guides
       set status = 'published', reviewed_by = p_actor_id, reviewed_at = now(), published_at = now()
     where id = p_id returning * into v_row;
  else
    update public.model_guides set status = 'draft' where id = p_id returning * into v_row;
  end if;
  return jsonb_build_object('id', v_row.id, 'status', v_row.status, 'updated_at', v_row.updated_at,
                            'slug_make', v_row.slug_make, 'slug_model', v_row.slug_model);
end;
$$;

-- The models with the most active searches (enabled and within their plan),
-- by catalog model row, with the catalog's years and their guide's state.
-- Only aggregate counts: never a user, a search or a filter besides the model.
create function public.admin_guide_candidates(p_limit integer default 30)
returns table (make text, model text, year_from integer, year_to integer, active_searches bigint,
               guide_id bigint, guide_status text)
language sql stable security definer set search_path = '' as $$
  with active as (
    select lower(btrim(sp.filters ->> 'make')) as make, lower(btrim(sp.filters ->> 'model')) as model
      from public.search_profiles sp
     where sp.enabled and public.search_access_active(sp.id)
       and nullif(btrim(sp.filters ->> 'model'), '') is not null
  ), counted as (
    select vc.make, vc.model, vc.year_from, vc.year_to, count(*) as n
      from active a
      join public.vehicle_catalog vc
        on vc.trim is null and lower(vc.make) = a.make and lower(vc.model) = a.model
     group by vc.make, vc.model, vc.year_from, vc.year_to
  )
  select c.make, c.model, c.year_from, c.year_to, c.n,
         g.id, g.status
    from counted c
    left join lateral (
      select mg.id, mg.status from public.model_guides mg
       where mg.make = c.make and mg.model = c.model
       order by (mg.status = 'published') desc, mg.generation_label nulls first, mg.id
       limit 1) g on true
   order by c.n desc, c.make, c.model
   limit greatest(1, least(coalesce(p_limit, 30), 200))
$$;

revoke all on function public.admin_save_model_guide(bigint, jsonb, timestamptz, uuid) from public, anon, authenticated;
revoke all on function public.admin_set_model_guide_status(bigint, text, uuid) from public, anon, authenticated;
revoke all on function public.admin_guide_candidates(integer) from public, anon, authenticated;
grant execute on function public.admin_save_model_guide(bigint, jsonb, timestamptz, uuid) to service_role;
grant execute on function public.admin_set_model_guide_status(bigint, text, uuid) to service_role;
grant execute on function public.admin_guide_candidates(integer) to service_role;

-- ---------------------------------------------------------------------------
-- llm_jobs: kind 'model_guide'
-- ---------------------------------------------------------------------------

alter table public.llm_jobs drop constraint llm_jobs_kind_check;
alter table public.llm_jobs add constraint llm_jobs_kind_check
  check (kind in ('parse_search', 'extract_listing_facts', 'polish_questions', 'model_guide'));

alter table public.llm_jobs add constraint llm_jobs_model_guide_input check (
  kind <> 'model_guide'
  or coalesce(jsonb_typeof(input -> 'guide_id') = 'number'
              and jsonb_typeof(input -> 'make') = 'string'
              and jsonb_typeof(input -> 'model') = 'string', false)
);

-- A user cannot enqueue a guide by inserting directly: only admin_request_model_guide does.
drop policy "llm_jobs: enqueue own" on public.llm_jobs;
create policy "llm_jobs: enqueue own" on public.llm_jobs
  for insert to authenticated
  with check (user_id = (select auth.uid()) and status = 'queued' and kind <> 'model_guide');

-- The worker's cache lookup: a done guide job with the same key.
create index llm_jobs_model_guide_cache_idx on public.llm_jobs ((output ->> 'cache_key'))
  where kind = 'model_guide' and status = 'done';

-- The per-user hourly cap (last defined in 20261029120000_email_only_accounts)
-- ignores guides: a batch of 30 would otherwise eat the admin's assisted mode.
create or replace function public.enforce_llm_rate_limit() returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_limits jsonb;
  v_max    integer;
  v_count  integer;
begin
  if new.kind = 'model_guide' then
    return new;
  end if;
  select value into v_limits from public.app_config where key = 'llm_limits';
  v_max := (v_limits ->> 'per_user_hour')::integer;
  if exists (select 1 from public.profiles where id = new.user_id and email_only) then
    v_max := coalesce((v_limits ->> 'email_only_per_user_hour')::integer, 5);
  end if;
  if v_max is null then
    return new;
  end if;

  select count(*) into v_count
    from public.llm_jobs
   where user_id = new.user_id and created_at > now() - interval '1 hour' and kind <> 'model_guide';
  if v_count >= v_max then
    raise exception 'llm_rate_limited'
      using errcode = 'P0001',
            detail  = format('%s LLM jobs in the last hour (max %s)', v_count, v_max);
  end if;
  return new;
end;
$$;
revoke execute on function public.enforce_llm_rate_limit() from public, anon, authenticated;

-- How many guide jobs count for the caps since `p_since`: the ones waiting
-- or running (they will call the provider) and the ones that did call it.
-- A cache hit (provider 'cache') and a job that never reached the provider
-- (expired in the queue, generation off: provider null) do not count.
create function public.model_guide_jobs_since(p_since timestamptz)
returns integer language sql stable security definer set search_path = '' as $$
  select count(*)::integer from public.llm_jobs
   where kind = 'model_guide' and created_at >= p_since
     and (status in ('queued', 'running') or (provider is not null and provider <> 'cache'))
$$;
revoke all on function public.model_guide_jobs_since(timestamptz) from public, anon, authenticated;
grant execute on function public.model_guide_jobs_since(timestamptz) to service_role;

-- The admin asks for a draft. Checks the generation is on, the caps (day and
-- month in Argentina, under an advisory lock so two requests cannot both
-- take the last one), that the guide is a draft (a published guide is never
-- regenerated: unpublish it first), that no job of it is pending, and that
-- hand edits after the last generation are only replaced with p_force
-- (which also skips the worker's cache: «Regenerar»).
create function public.admin_request_model_guide(p_guide_id bigint, p_force boolean, p_actor_id uuid)
returns bigint
language plpgsql security definer set search_path = '' as $$
declare
  v_cfg jsonb;
  v_guide public.model_guides;
  v_today timestamptz;
  v_month timestamptz;
  v_day_n integer;
  v_month_n integer;
  v_id bigint;
begin
  if not exists (select 1 from public.profiles where id = p_actor_id and role = 'admin') then
    raise exception 'admin_required' using errcode = '42501';
  end if;
  select value -> 'model_guide' into v_cfg from public.app_config where key = 'llm_limits';
  if v_cfg is null or (v_cfg -> 'enabled') is distinct from 'true'::jsonb then
    raise exception 'guide_generation_off' using errcode = '22023';
  end if;
  perform pg_advisory_xact_lock(hashtext('public.admin_request_model_guide'));

  select * into v_guide from public.model_guides where id = p_guide_id for update;
  if not found then raise exception 'guide_not_found' using errcode = 'P0002'; end if;
  if v_guide.status <> 'draft' then
    raise exception 'guide_published' using errcode = '22023';
  end if;
  if exists (select 1 from public.llm_jobs
              where kind = 'model_guide' and status in ('queued', 'running')
                and (input ->> 'guide_id')::bigint = p_guide_id) then
    raise exception 'guide_job_pending' using errcode = '22023';
  end if;
  if not coalesce(p_force, false)
     and (jsonb_path_exists(v_guide.body, '$.*[*]') or jsonb_array_length(v_guide.questions) > 0
          or jsonb_array_length(v_guide.sources) > 0)
     and (v_guide.generated_at is null or v_guide.updated_at > v_guide.generated_at) then
    raise exception 'guide_has_manual_edits' using errcode = '22023';
  end if;

  v_today := date_trunc('day', now() at time zone 'America/Argentina/Buenos_Aires')
             at time zone 'America/Argentina/Buenos_Aires';
  v_month := date_trunc('month', now() at time zone 'America/Argentina/Buenos_Aires')
             at time zone 'America/Argentina/Buenos_Aires';
  v_day_n := public.model_guide_jobs_since(v_today);
  v_month_n := public.model_guide_jobs_since(v_month);
  if v_day_n >= coalesce((v_cfg ->> 'per_day')::integer, 0) then
    raise exception 'guide_daily_cap'
      using errcode = 'P0001', detail = format('%s de %s hoy', v_day_n, v_cfg ->> 'per_day');
  end if;
  if v_month_n >= coalesce((v_cfg ->> 'per_month')::integer, 0) then
    raise exception 'guide_monthly_cap'
      using errcode = 'P0001', detail = format('%s de %s este mes', v_month_n, v_cfg ->> 'per_month');
  end if;

  insert into public.llm_jobs (user_id, kind, input)
  values (p_actor_id, 'model_guide',
          jsonb_build_object('guide_id', v_guide.id, 'make', v_guide.make, 'model', v_guide.model,
                             'generation_label', v_guide.generation_label,
                             'year_from', v_guide.year_from, 'year_to', v_guide.year_to,
                             'force', coalesce(p_force, false)))
  returning id into v_id;
  return v_id;
end;
$$;
revoke all on function public.admin_request_model_guide(bigint, boolean, uuid) from public, anon, authenticated;
grant execute on function public.admin_request_model_guide(bigint, boolean, uuid) to service_role;

-- ---------------------------------------------------------------------------
-- app_config (editable from /admin/config; added without overwriting)
-- ---------------------------------------------------------------------------

update public.app_config
   set value = value || '{"model_guide": {"enabled": false, "per_day": 30, "per_month": 60,
                                          "queued_ttl_minutes": 60, "timeout_seconds": 180,
                                          "max_questions_in_listing": 3}}'::jsonb
 where key = 'llm_limits' and jsonb_typeof(value) = 'object' and not value ? 'model_guide';

-- The pilot: the guide ids Juan marks to review first (a label in /admin/guides).
insert into public.app_config (key, value) values ('model_guides', '{"pilot": []}')
on conflict (key) do nothing;

notify pgrst, 'reload schema';

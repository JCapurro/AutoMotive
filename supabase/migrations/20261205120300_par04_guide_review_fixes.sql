-- PAR-04 · Guías por modelo: arreglos de la revisión (docs/BACKLOG_PRODUCTO_2026-10.md,
-- ítem PAR-04; diseño docs/superpowers/specs/2026-11-03-par04-guias-design.md,
-- decisiones 2, 5, 8 y 9).
--
-- * model_guides.content_updated_at: when the guide's content (sections,
--   questions, sources, years, generation) last changed, by hand or by the
--   worker. Publishing or unpublishing bumps updated_at (set_updated_at) but
--   is not a hand edit: admin_request_model_guide and the worker's
--   apply_draft compare content_updated_at, not updated_at, with
--   generated_at / the request.
-- * Unpublishing a guide withdraws its questions from the matches that carry
--   them (seller_questions, contact_questions, question_origins) right away,
--   whatever the listing's state; saving a published guide withdraws the
--   questions it no longer has. The worker stores each guide question's text
--   in question_origins, so the withdrawal removes exactly what was written.
-- * guard_match_access (last defined in 20261007120000_ese_auto_commercial)
--   lets through an update that changes nothing but those three columns: a
--   withdrawal never gives access to a result.
-- * log_guide_event: a cap per guide per minute and per hour
--   (app_config.model_guides.events, 30 and 300 by default). Past it the call
--   does nothing and says nothing; the anon key cannot fill public.events.
--
-- Needs 20261205120000..20261204120200. Does not apply or depend on
-- 20261107130000_timing_chain_catalog.sql. Applies on an empty base after the
-- earlier migrations; the web of main does not read any of it.

-- ---------------------------------------------------------------------------
-- content_updated_at
-- ---------------------------------------------------------------------------

alter table public.model_guides add column content_updated_at timestamptz not null default now();
update public.model_guides set content_updated_at = coalesce(generated_at, updated_at);
comment on column public.model_guides.content_updated_at is
  'PAR-04: último cambio del contenido (a mano o del worker). Publicar o despublicar no lo cambia.';

-- Any write that changes the content moves it (the admin RPC, the worker, SQL by hand).
create function public.model_guides_touch_content() returns trigger
language plpgsql set search_path = '' as $$
begin
  if (new.make, new.model, new.generation_label, new.year_from, new.year_to, new.body, new.questions, new.sources)
     is distinct from
     (old.make, old.model, old.generation_label, old.year_from, old.year_to, old.body, old.questions, old.sources) then
    new.content_updated_at := now();
  end if;
  return new;
end $$;
revoke all on function public.model_guides_touch_content() from public, anon, authenticated;

create trigger model_guides_touch_content before update on public.model_guides
  for each row execute function public.model_guides_touch_content();

-- ---------------------------------------------------------------------------
-- Withdrawing a guide's questions from the matches
-- ---------------------------------------------------------------------------

-- An update that only rewrites the seller questions is never a new result.
create or replace function public.guard_match_access()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  if tg_op = 'UPDATE'
     and (to_jsonb(new) - array['seller_questions', 'contact_questions', 'question_origins', 'updated_at'])
         = (to_jsonb(old) - array['seller_questions', 'contact_questions', 'question_origins', 'updated_at']) then
    return new;
  end if;
  if coalesce((select (value->>'enforced')::boolean from public.app_config where key = 'plan_limits'), false)
    and not public.search_access_active(new.search_profile_id) then return null; end if;
  return new;
end $$;

-- Removes from every match the questions of guide `p_guide_id` whose text is
-- not in `p_keep` (null or empty: all of them). The texts come from
-- question_origins (what the worker wrote) and the guide's current questions.
-- seller_questions joins the questions with a space and starts with the
-- greeting, so a guide question is always preceded by one. Returns how many
-- matches changed.
create function public.model_guide_withdraw_questions(p_guide_id bigint, p_keep text[])
returns integer
language plpgsql security definer set search_path = '' as $$
declare
  v_current text[];
  v_m record;
  v_texts text[];
  v_text text;
  v_seller text;
  v_contact text[];
  v_n integer := 0;
begin
  select coalesce(array_agg(btrim(q ->> 'text')) filter (where q ->> 'text' is not null), '{}')
    into v_current
    from public.model_guides g, jsonb_array_elements(g.questions) q
   where g.id = p_guide_id;
  for v_m in
    select m.id, m.seller_questions, m.contact_questions, m.question_origins
      from public.matches m
     where m.question_origins @> jsonb_build_array(jsonb_build_object('guide_id', p_guide_id))
       for update
  loop
    select coalesce(array_agg(distinct t), '{}') into v_texts
      from (select btrim(o ->> 'text') as t
              from jsonb_array_elements(v_m.question_origins) o
             where (o -> 'guide_id') = to_jsonb(p_guide_id) and o ->> 'text' is not null
            union
            select unnest(v_current)) s
     where t <> '' and not (t = any (coalesce(p_keep, '{}')));
    v_seller := v_m.seller_questions;
    v_contact := v_m.contact_questions;
    foreach v_text in array v_texts loop
      v_seller := replace(v_seller, ' ' || v_text, '');
      v_contact := array_remove(v_contact, v_text);
    end loop;
    update public.matches
       set seller_questions = v_seller,
           contact_questions = v_contact,
           question_origins = (
             select coalesce(jsonb_agg(o order by n), '[]'::jsonb)
               from jsonb_array_elements(v_m.question_origins) with ordinality e(o, n)
              where (o -> 'guide_id') is distinct from to_jsonb(p_guide_id)
                 or btrim(coalesce(o ->> 'text', '')) = any (coalesce(p_keep, '{}')))
     where id = v_m.id;
    v_n := v_n + 1;
  end loop;
  return v_n;
end;
$$;
revoke all on function public.model_guide_withdraw_questions(bigint, text[]) from public, anon, authenticated;
grant execute on function public.model_guide_withdraw_questions(bigint, text[]) to service_role;

create index if not exists matches_question_origins_idx on public.matches using gin (question_origins jsonb_path_ops)
  where question_origins is not null;

-- ---------------------------------------------------------------------------
-- Admin writes (as in 20261205120000, plus the withdrawal)
-- ---------------------------------------------------------------------------

create or replace function public.admin_save_model_guide(
  p_id bigint, p_values jsonb, p_expected_updated_at timestamptz, p_actor_id uuid
) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare
  v_make text;
  v_model text;
  v_row public.model_guides;
  v_problem text;
  v_body jsonb := coalesce(p_values -> 'body', '{}');
  v_questions jsonb := coalesce(p_values -> 'questions', '[]');
  v_sources jsonb := coalesce(p_values -> 'sources', '[]');
  v_generation text := nullif(btrim(p_values ->> 'generation_label'), '');
  v_year_from integer := (p_values ->> 'year_from')::integer;
  v_year_to integer := (p_values ->> 'year_to')::integer;
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
    values (v_make, v_model, v_generation, v_year_from, v_year_to,
            p_values ->> 'slug_make', p_values ->> 'slug_model', v_body, v_questions, v_sources)
    returning * into v_row;
  else
    select * into v_row from public.model_guides where id = p_id for update;
    if not found then raise exception 'guide_not_found' using errcode = 'P0002'; end if;
    if p_expected_updated_at is null or v_row.updated_at is distinct from p_expected_updated_at then
      raise exception 'guide_conflict' using errcode = '40001';
    end if;
    if v_row.status = 'published' then
      v_problem := public.model_guide_problem(v_body, v_questions, v_sources);
      if v_problem is not null then raise exception '%', v_problem using errcode = '22023'; end if;
    end if;
    update public.model_guides
       set make = v_make, model = v_model,
           generation_label = v_generation, year_from = v_year_from, year_to = v_year_to,
           slug_make = p_values ->> 'slug_make', slug_model = p_values ->> 'slug_model',
           body = v_body, questions = v_questions, sources = v_sources,
           reviewed_by = case when status = 'published' then p_actor_id else reviewed_by end,
           reviewed_at = case when status = 'published' then now() else reviewed_at end
     where id = p_id
    returning * into v_row;
    -- A published guide's removed questions leave the matches now, not at the next rescore.
    if v_row.status = 'published' then
      perform public.model_guide_withdraw_questions(
        v_row.id,
        (select coalesce(array_agg(btrim(q ->> 'text')), '{}') from jsonb_array_elements(v_row.questions) q));
    end if;
  end if;
  return jsonb_build_object('id', v_row.id, 'updated_at', v_row.updated_at, 'status', v_row.status,
                            'slug_make', v_row.slug_make, 'slug_model', v_row.slug_model);
exception
  when unique_violation then raise exception 'guide_duplicate' using errcode = '23505';
end;
$$;

create or replace function public.admin_set_model_guide_status(p_id bigint, p_status text, p_actor_id uuid)
returns jsonb
language plpgsql security definer set search_path = '' as $$
declare
  v_row public.model_guides;
  v_problem text;
  v_withdrawn integer := 0;
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
    -- Nothing of an unpublished guide stays in the matches.
    v_withdrawn := public.model_guide_withdraw_questions(p_id, null);
  end if;
  return jsonb_build_object('id', v_row.id, 'status', v_row.status, 'updated_at', v_row.updated_at,
                            'slug_make', v_row.slug_make, 'slug_model', v_row.slug_model,
                            'withdrawn_matches', v_withdrawn);
end;
$$;

-- As in 20261205120000, comparing content_updated_at (not updated_at) with generated_at.
create or replace function public.admin_request_model_guide(p_guide_id bigint, p_force boolean, p_actor_id uuid)
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
     and (v_guide.generated_at is null or v_guide.content_updated_at > v_guide.generated_at) then
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

-- ---------------------------------------------------------------------------
-- log_guide_event with a cap per guide
-- ---------------------------------------------------------------------------

create index if not exists events_guide_created_idx on public.events (((props ->> 'guide_id')), created_at desc)
  where name in ('guide_viewed', 'guide_cta_clicked', 'guide_questions_copied');

update public.app_config
   set value = value || '{"events": {"per_guide_minute": 30, "per_guide_hour": 300}}'::jsonb
 where key = 'model_guides' and jsonb_typeof(value) = 'object' and not value ? 'events';

create or replace function public.log_guide_event(p_name text, p_slug_make text, p_slug_model text)
returns void
language plpgsql security definer set search_path = '' as $$
declare
  v_guide record;
  v_cfg jsonb;
  v_minute integer;
  v_hour integer;
begin
  if p_name is null or p_name not in ('guide_viewed', 'guide_cta_clicked', 'guide_questions_copied') then
    raise exception 'invalid_guide_event' using errcode = '22023';
  end if;
  select g.id, g.make, g.model into v_guide
    from public.model_guides g
   where g.status = 'published' and g.slug_make = p_slug_make and g.slug_model = p_slug_model
   order by g.generation_label nulls first, g.id
   limit 1;
  if not found then
    raise exception 'guide_not_found' using errcode = 'P0002';
  end if;
  select value -> 'events' into v_cfg from public.app_config where key = 'model_guides';
  v_minute := coalesce((v_cfg ->> 'per_guide_minute')::integer, 30);
  v_hour := coalesce((v_cfg ->> 'per_guide_hour')::integer, 300);
  -- One counter per guide (any of the three names): past the cap, nothing is written.
  perform pg_advisory_xact_lock(hashtext('public.log_guide_event'), v_guide.id::integer);
  if (select count(*) from public.events e
       where e.name in ('guide_viewed', 'guide_cta_clicked', 'guide_questions_copied')
         and (e.props ->> 'guide_id') = v_guide.id::text
         and e.created_at > now() - interval '1 minute') >= v_minute
     or (select count(*) from public.events e
          where e.name in ('guide_viewed', 'guide_cta_clicked', 'guide_questions_copied')
            and (e.props ->> 'guide_id') = v_guide.id::text
            and e.created_at > now() - interval '1 hour') >= v_hour then
    return;
  end if;
  insert into public.events (user_id, name, props)
  values ((select auth.uid()), p_name,
          jsonb_build_object('guide_id', v_guide.id, 'make', v_guide.make, 'model', v_guide.model));
end;
$$;
revoke all on function public.log_guide_event(text, text, text) from public;
grant execute on function public.log_guide_event(text, text, text) to anon, authenticated, service_role;

notify pgrst, 'reload schema';

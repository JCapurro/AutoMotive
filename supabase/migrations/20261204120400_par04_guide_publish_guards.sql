-- PAR-04 · Guías por modelo: segunda tanda de arreglos de la revisión
-- (docs/superpowers/specs/2026-11-03-par04-guias-design.md, decisiones 2, 8 y 9).
--
-- * Publishing needs at least one source, every one checked
--   (guide_sources_missing / guide_sources_unverified): an empty list is not
--   «todas las fuentes verificadas».
-- * admin_set_model_guide_status takes the updated_at the admin saw
--   (p_expected_updated_at). Publishing refuses a guide that changed since
--   (guide_changed): a draft the worker rewrote after «Regenerar», or another
--   edit, is never published from a stale page. Unpublishing needs no
--   version: taking a page down is always allowed.
-- * model_guide_withdraw_questions removes exactly what the worker wrote for
--   the guide: the texts question_origins records with its guide_id (never
--   a template question with the same text), and whole questions, never a
--   piece of another one. The worker writes every question's text in
--   question_origins; with all of them there, seller_questions is rebuilt
--   from the entries that stay (match_questions_without).
-- * anon reads content_updated_at: the public page's «Última actualización»
--   and the sitemap's lastModified are the content's date, not the last
--   publish or unpublish.
--
-- Needs 20261204120000..20261204120300.

-- ---------------------------------------------------------------------------
-- Publishing rules
-- ---------------------------------------------------------------------------

create or replace function public.model_guide_problem(p_body jsonb, p_questions jsonb, p_sources jsonb)
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
    when jsonb_array_length(p_sources) = 0 then 'guide_sources_missing'
    when exists (select 1 from jsonb_array_elements(p_sources) s
                  where (s -> 'verified') is distinct from 'true'::jsonb) then 'guide_sources_unverified'
    else null
  end
$$;

drop function public.admin_set_model_guide_status(bigint, text, uuid);

-- Publishing needs p_expected_updated_at = the row's updated_at (what the
-- admin had on screen); unpublishing ignores it.
create function public.admin_set_model_guide_status(
  p_id bigint, p_status text, p_actor_id uuid, p_expected_updated_at timestamptz default null
) returns jsonb
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
    if p_expected_updated_at is null or v_row.updated_at is distinct from p_expected_updated_at then
      raise exception 'guide_changed' using errcode = '40001';
    end if;
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
revoke all on function public.admin_set_model_guide_status(bigint, text, uuid, timestamptz) from public, anon, authenticated;
grant execute on function public.admin_set_model_guide_status(bigint, text, uuid, timestamptz) to service_role;

-- ---------------------------------------------------------------------------
-- Withdrawing exactly the guide's questions
-- ---------------------------------------------------------------------------

-- A match's questions without the entries of the guides `p_guide_ids` whose
-- text is not in `p_keep` (null or empty: none kept). question_origins is in
-- the order of seller_questions (the questions joined with a space). When
-- every entry carries its text and they add up to seller_questions, it is
-- rebuilt from the entries that stay. Otherwise (a row scored before the
-- worker wrote every text) a dropped text is removed only where it is a
-- whole question: it appears once and is preceded by a space; if it also
-- appears inside another question, seller_questions is left as it was.
-- contact_questions loses the dropped texts unless an entry that stays has
-- the same text.
create function public.match_questions_without(
  p_seller text, p_contact text[], p_origins jsonb, p_guide_ids bigint[], p_keep text[],
  out seller_questions text, out contact_questions text[], out question_origins jsonb)
language plpgsql immutable set search_path = '' as $$
declare
  v_dropped text[];
  v_kept text[];
  v_complete boolean;
  v_joined text;
  v_kept_joined text;
  v_text text;
begin
  with e as (
    select o, n,
           (o ? 'guide_id' and (o ->> 'guide_id')::bigint = any (coalesce(p_guide_ids, '{}'))
            and not (btrim(coalesce(o ->> 'text', '')) = any (coalesce(p_keep, '{}')))) as dropped
      from jsonb_array_elements(case when jsonb_typeof(p_origins) = 'array' then p_origins else '[]' end)
           with ordinality x(o, n))
  select coalesce(jsonb_agg(o order by n) filter (where not dropped), '[]'::jsonb),
         coalesce(array_agg(btrim(o ->> 'text') order by n)
                    filter (where dropped and btrim(coalesce(o ->> 'text', '')) <> ''), '{}'),
         coalesce(array_agg(btrim(o ->> 'text') order by n) filter (where not dropped and o ->> 'text' is not null), '{}'),
         coalesce(bool_and(o ->> 'text' is not null), false),
         string_agg(o ->> 'text', ' ' order by n),
         string_agg(o ->> 'text', ' ' order by n) filter (where not dropped)
    into question_origins, v_dropped, v_kept, v_complete, v_joined, v_kept_joined
    from e;

  if cardinality(v_dropped) = 0 then
    seller_questions := p_seller;
    contact_questions := p_contact;
    question_origins := case when jsonb_typeof(p_origins) = 'array' then question_origins else p_origins end;
    return;
  end if;

  if p_seller is null then
    seller_questions := null;
  elsif v_complete and v_joined = p_seller then
    seller_questions := coalesce(v_kept_joined, '');
  else
    seller_questions := p_seller;
    foreach v_text in array v_dropped loop
      if position(' ' || v_text in seller_questions) > 0
         and length(seller_questions) - length(replace(seller_questions, v_text, '')) = length(v_text) then
        seller_questions := replace(seller_questions, ' ' || v_text, '');
      end if;
    end loop;
  end if;

  if p_contact is null then
    contact_questions := null;
  else
    select coalesce(array_agg(c order by i), '{}') into contact_questions
      from unnest(p_contact) with ordinality u(c, i)
     where not (btrim(c) = any (v_dropped)) or btrim(c) = any (v_kept);
  end if;
end;
$$;
revoke all on function public.match_questions_without(text, text[], jsonb, bigint[], text[]) from public, anon, authenticated;
grant execute on function public.match_questions_without(text, text[], jsonb, bigint[], text[]) to service_role;

-- Removes from every match the questions of guide `p_guide_id` whose text is
-- not in `p_keep` (null or empty: all of them): only what question_origins
-- records for that guide. Returns how many matches changed.
create or replace function public.model_guide_withdraw_questions(p_guide_id bigint, p_keep text[])
returns integer
language plpgsql security definer set search_path = '' as $$
declare
  v_m record;
  v_r record;
  v_n integer := 0;
begin
  for v_m in
    select m.id, m.seller_questions, m.contact_questions, m.question_origins
      from public.matches m
     where m.question_origins @> jsonb_build_array(jsonb_build_object('guide_id', p_guide_id))
       for update
  loop
    select * into v_r
      from public.match_questions_without(v_m.seller_questions, v_m.contact_questions, v_m.question_origins,
                                          array[p_guide_id], p_keep);
    if v_r.question_origins is distinct from v_m.question_origins
       or v_r.seller_questions is distinct from v_m.seller_questions
       or v_r.contact_questions is distinct from v_m.contact_questions then
      update public.matches
         set seller_questions = v_r.seller_questions,
             contact_questions = v_r.contact_questions,
             question_origins = v_r.question_origins
       where id = v_m.id;
      v_n := v_n + 1;
    end if;
  end loop;
  return v_n;
end;
$$;

-- ---------------------------------------------------------------------------
-- The content's date, public
-- ---------------------------------------------------------------------------

grant select (content_updated_at) on public.model_guides to anon, authenticated;

notify pgrst, 'reload schema';

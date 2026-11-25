-- Auditoría de matches: quién revisó, persona o automático.
--
-- admin_match_reviews.reviewer_id dice qué cuenta admin guardó el veredicto,
-- pero un script que llame a admin_match_review_save con esa cuenta queda igual
-- que una persona (24/11: 60 revisiones en 11 min, ~6 s entre una y otra). Se
-- agrega reviewer_kind: 'person' lo declara la acción web de /admin/matches/audit
-- (pasa por requireAdmin, o sea una sesión de admin), 'automated' lo declara
-- cualquier script. NULL = guardado antes de este campo o por quien no lo
-- declaró: no se sabe. Es una declaración de quien llama, no una prueba.
--
-- admin_match_review_queue devuelve además reviewer_id, reviewer_kind y el
-- email del revisor (la pantalla es solo de admins).

alter table public.admin_match_reviews
  add column reviewer_kind text check (reviewer_kind in ('person', 'automated'));
comment on column public.admin_match_reviews.reviewer_kind is
  'person = guardado desde la pantalla de admin; automated = guardado por un script; null = no declarado (antes del campo).';

drop function public.admin_match_review_save(bigint, text, text[], text, uuid);
create function public.admin_match_review_save(
  p_id bigint, p_verdict text, p_reasons text[], p_note text, p_actor_id uuid, p_reviewer_kind text default null
) returns jsonb language plpgsql security invoker set search_path = '' as $$
declare v_reasons text[] := coalesce(p_reasons, '{}');
begin
  if not exists (select 1 from public.profiles where id = p_actor_id and role = 'admin') then
    raise exception 'admin_required' using errcode = '42501';
  end if;
  if p_verdict is null or p_verdict not in ('good', 'fair', 'bad') then
    raise exception 'invalid_verdict' using errcode = '22023';
  end if;
  if p_reviewer_kind is not null and p_reviewer_kind not in ('person', 'automated') then
    raise exception 'invalid_reviewer_kind' using errcode = '22023';
  end if;
  if p_verdict = 'good' then v_reasons := '{}'; end if;
  if p_verdict <> 'good' and cardinality(v_reasons) = 0 then
    raise exception 'reasons_required' using errcode = '22023';
  end if;
  if not (v_reasons <@ array['version', 'zone', 'price', 'year', 'not_a_car', 'duplicate', 'ended', 'other']::text[]) then
    raise exception 'invalid_reason' using errcode = '22023';
  end if;
  update public.admin_match_reviews
     set verdict = p_verdict, reasons = (select coalesce(array_agg(distinct x order by x), '{}') from unnest(v_reasons) x),
         note = nullif(btrim(coalesce(p_note, '')), ''), reviewer_id = p_actor_id, reviewer_kind = p_reviewer_kind,
         reviewed_at = now()
   where id = p_id;
  if not found then raise exception 'review_not_found' using errcode = 'P0002'; end if;
  return jsonb_build_object('id', p_id, 'verdict', p_verdict);
end $$;

revoke all on function public.admin_match_review_save(bigint, text, text[], text, uuid, text) from public, anon, authenticated;
grant execute on function public.admin_match_review_save(bigint, text, text[], text, uuid, text) to service_role;

create or replace function public.admin_match_review_queue(p_week date default null)
returns jsonb language sql stable security invoker set search_path = '' as $$
  select coalesce(jsonb_agg(row order by (row->>'id')::bigint), '[]'::jsonb) from (
    select jsonb_build_object(
      'id', r.id, 'match_id', r.match_id, 'level', r.level, 'source', r.source,
      'verdict', r.verdict, 'reasons', to_jsonb(r.reasons), 'note', r.note, 'reviewed_at', r.reviewed_at,
      'reviewer_id', r.reviewer_id, 'reviewer_kind', r.reviewer_kind, 'reviewer_email', p.email,
      'score', m.score, 'is_backfill', m.is_backfill, 'search_profile_id', m.search_profile_id,
      'listing', case when l.id is null then null else jsonb_build_object(
        'id', l.id, 'title', l.title, 'make', l.make, 'model', l.model, 'trim', l.trim, 'year', l.year,
        'price_usd', l.price_usd, 'price', l.price, 'currency', l.currency, 'mileage_km', l.mileage_km,
        'location_text', l.location_text, 'url', l.url, 'status', l.status, 'body_type', l.body_type,
        'transmission', l.transmission, 'fuel', l.fuel) end,
      'search', case when sp.id is null then null else jsonb_build_object(
        'id', sp.id, 'name', sp.name, 'filters', sp.filters, 'preferences', sp.preferences,
        'raw_query', sp.raw_query, 'radius_km', sp.radius_km) end
    ) as row
      from public.admin_match_reviews r
      left join public.profiles p on p.id = r.reviewer_id
      left join public.matches m on m.id = r.match_id
      left join public.listings l on l.id = m.listing_id
      left join public.search_profiles sp on sp.id = m.search_profile_id
     where r.sample_week = coalesce(p_week, public.admin_match_review_week())
  ) q;
$$;

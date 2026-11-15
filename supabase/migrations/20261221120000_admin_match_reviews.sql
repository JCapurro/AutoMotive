-- Auditoría semanal de matches (backoffice, /admin/matches/audit).
--
-- Una auditoría manual de 142 búsquedas encontró 31 matches buenos, 61 regulares
-- y 50 malos, y la mayor pérdida de precisión venía de la versión (trim) blanda.
-- Desde entonces nada mide la precisión. Cada semana se sortean 60 matches que
-- realmente llegaron en una alerta, se revisan a mano (Bien / Regular / Mal) y
-- se mira cómo evoluciona el porcentaje.
--
-- 1. admin_match_reviews: una fila por match y semana. Referencia solo a
--    matches (nunca a listings) y guarda nivel y fuente del momento del sorteo.
-- 2. admin_match_review_draw(): sortea (o completa) la muestra de la semana.
-- 3. admin_match_review_queue(): la muestra con todo lo que la pantalla muestra.
-- 4. admin_match_review_save(): guarda un veredicto.
-- 5. admin_match_review_stats(): precisión por semana, nivel, fuente y razones.
--
-- Todo es solo para el servidor (service role) tras requireAdmin, como
-- admin_update_setting. Depende solo del esquema base (matches, notifications,
-- search_profiles, profiles, listings en lectura).

create table public.admin_match_reviews (
  id          bigint generated always as identity primary key,
  sample_week date not null check (extract(isodow from sample_week) = 1),
  match_id    bigint references public.matches (id) on delete set null,
  -- Foto del momento del sorteo: la estadística no cambia si el match se re-puntúa o se borra.
  level       public.match_level not null,
  source      text not null,
  verdict     text check (verdict in ('good', 'fair', 'bad')),
  reasons     text[] not null default '{}',
  note        text check (note is null or char_length(note) <= 1000),
  reviewer_id uuid references public.profiles (id) on delete set null,
  reviewed_at timestamptz,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now(),
  unique (sample_week, match_id),
  check (reasons <@ array['version', 'zone', 'price', 'year', 'not_a_car', 'duplicate', 'ended', 'other']::text[]),
  -- Regular y Mal explican por qué; Bien y sin revisar no llevan razones.
  check ((verdict in ('fair', 'bad') and cardinality(reasons) >= 1) or (verdict is distinct from 'fair' and verdict is distinct from 'bad' and cardinality(reasons) = 0)),
  check ((verdict is null) = (reviewed_at is null))
);
create index admin_match_reviews_week_idx on public.admin_match_reviews (sample_week, id);
create trigger admin_match_reviews_set_updated_at before update on public.admin_match_reviews
  for each row execute function public.set_updated_at();
alter table public.admin_match_reviews enable row level security;
revoke all on public.admin_match_reviews from public, anon, authenticated, service_role;
grant select, insert, update on public.admin_match_reviews to service_role;
revoke all on sequence public.admin_match_reviews_id_seq from public, anon, authenticated, service_role;
grant usage, select on sequence public.admin_match_reviews_id_seq to service_role;

-- Lunes (hora de Argentina) de la semana que contiene a p_at.
create function public.admin_match_review_week(p_at timestamptz default now())
returns date language sql stable set search_path = '' as $$
  select (date_trunc('week', p_at at time zone 'America/Argentina/Buenos_Aires'))::date;
$$;

-- Sortea la muestra de la semana. Idempotente: si ya hay filas, devuelve las
-- mismas y solo completa hasta p_size. Candidatos: matches que salieron en una
-- alerta enviada en los 7 días previos (o previos al cierre de esa semana), sin
-- búsquedas de admins y sin los que ya se sortearon en otra semana. Se reparte
-- en rondas por (nivel, fuente): primero uno de cada grupo, después otro, etc.,
-- así los grupos chicos entran completos y los grandes se reparten parejo.
create function public.admin_match_review_draw(p_week date default null, p_size integer default 60)
returns jsonb language plpgsql security invoker set search_path = '' as $$
declare
  v_week date := coalesce(p_week, public.admin_match_review_week());
  v_end timestamptz;
  v_have integer;
  v_added integer;
begin
  if extract(isodow from v_week) <> 1 or p_size is null or p_size not between 1 and 200 then
    raise exception 'invalid_review_week' using errcode = '22023';
  end if;
  -- Dos sorteos a la vez para la misma semana no deben pasarse de la muestra.
  perform pg_advisory_xact_lock(hashtext('admin_match_review_draw'), (v_week - date '2000-01-01'));
  v_end := least(now(), ((v_week + 7)::timestamp at time zone 'America/Argentina/Buenos_Aires'));
  select count(*) into v_have from public.admin_match_reviews where sample_week = v_week;

  if v_have < p_size then
    with candidate as (
      select m.id as match_id, m.level, l.source
        from public.matches m
        join public.listings l on l.id = m.listing_id
        join public.search_profiles sp on sp.id = m.search_profile_id
       where exists (
               select 1 from public.notifications n
                where n.match_id = m.id and n.status = 'sent'
                  and n.sent_at >= v_end - interval '7 days' and n.sent_at < v_end)
         and not exists (select 1 from public.profiles p where p.id = sp.user_id and p.role = 'admin')
         and not exists (select 1 from public.admin_match_reviews r where r.match_id = m.id)
    ), ranked as (
      select c.*, row_number() over (partition by c.level, c.source order by random())
                  + coalesce((select count(*) from public.admin_match_reviews r
                               where r.sample_week = v_week and r.level = c.level and r.source = c.source), 0) as round
        from candidate c
    )
    insert into public.admin_match_reviews (sample_week, match_id, level, source)
    select v_week, match_id, level, source
      from ranked order by round, random() limit (p_size - v_have)
    on conflict (sample_week, match_id) do nothing;
    get diagnostics v_added = row_count;
  else
    v_added := 0;
  end if;

  return jsonb_build_object('week', v_week, 'total', v_have + v_added, 'added', v_added, 'target', p_size);
end $$;

-- La muestra de la semana, en orden fijo, con todo lo que muestra la pantalla.
create function public.admin_match_review_queue(p_week date default null)
returns jsonb language sql stable security invoker set search_path = '' as $$
  select coalesce(jsonb_agg(row order by (row->>'id')::bigint), '[]'::jsonb) from (
    select jsonb_build_object(
      'id', r.id, 'match_id', r.match_id, 'level', r.level, 'source', r.source,
      'verdict', r.verdict, 'reasons', to_jsonb(r.reasons), 'note', r.note, 'reviewed_at', r.reviewed_at,
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
      left join public.matches m on m.id = r.match_id
      left join public.listings l on l.id = m.listing_id
      left join public.search_profiles sp on sp.id = m.search_profile_id
     where r.sample_week = coalesce(p_week, public.admin_match_review_week())
  ) q;
$$;

-- Guarda (o corrige) el veredicto de una fila de la muestra.
create function public.admin_match_review_save(
  p_id bigint, p_verdict text, p_reasons text[], p_note text, p_actor_id uuid
) returns jsonb language plpgsql security invoker set search_path = '' as $$
declare v_reasons text[] := coalesce(p_reasons, '{}');
begin
  if not exists (select 1 from public.profiles where id = p_actor_id and role = 'admin') then
    raise exception 'admin_required' using errcode = '42501';
  end if;
  if p_verdict is null or p_verdict not in ('good', 'fair', 'bad') then
    raise exception 'invalid_verdict' using errcode = '22023';
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
         note = nullif(btrim(coalesce(p_note, '')), ''), reviewer_id = p_actor_id, reviewed_at = now()
   where id = p_id;
  if not found then raise exception 'review_not_found' using errcode = 'P0002'; end if;
  return jsonb_build_object('id', p_id, 'verdict', p_verdict);
end $$;

-- Filas agrupadas por semana, nivel y fuente (solo revisadas) y razones por semana.
-- El agrupado final por semana / nivel / fuente se hace en web/lib/admin-match-audit.ts.
create function public.admin_match_review_stats(p_weeks integer default 12)
returns jsonb language sql stable security invoker set search_path = '' as $$
  select jsonb_build_object(
    'rows', coalesce((
      select jsonb_agg(jsonb_build_object(
        'week', sample_week, 'level', level, 'source', source, 'sampled', sampled,
        'good', good, 'fair', fair, 'bad', bad) order by sample_week desc, level, source)
        from (select sample_week, level, source, count(*) as sampled,
                     count(*) filter (where verdict = 'good') as good,
                     count(*) filter (where verdict = 'fair') as fair,
                     count(*) filter (where verdict = 'bad') as bad
                from public.admin_match_reviews
               where sample_week >= public.admin_match_review_week() - (7 * greatest(coalesce(p_weeks, 12), 1))
               group by 1, 2, 3) g), '[]'::jsonb),
    'reasons', coalesce((
      select jsonb_agg(jsonb_build_object('week', sample_week, 'reason', reason, 'verdict', verdict, 'n', n)
                       order by sample_week desc, reason)
        from (select sample_week, reason, verdict, count(*) as n
                from public.admin_match_reviews, unnest(reasons) as reason
               where verdict is not null
                 and sample_week >= public.admin_match_review_week() - (7 * greatest(coalesce(p_weeks, 12), 1))
               group by 1, 2, 3) g), '[]'::jsonb)
  );
$$;

revoke all on function public.admin_match_review_week(timestamptz) from public, anon, authenticated;
revoke all on function public.admin_match_review_draw(date, integer) from public, anon, authenticated;
revoke all on function public.admin_match_review_queue(date) from public, anon, authenticated;
revoke all on function public.admin_match_review_save(bigint, text, text[], text, uuid) from public, anon, authenticated;
revoke all on function public.admin_match_review_stats(integer) from public, anon, authenticated;
grant execute on function public.admin_match_review_week(timestamptz) to service_role;
grant execute on function public.admin_match_review_draw(date, integer) to service_role;
grant execute on function public.admin_match_review_queue(date) to service_role;
grant execute on function public.admin_match_review_save(bigint, text, text[], text, uuid) to service_role;
grant execute on function public.admin_match_review_stats(integer) to service_role;

-- 2.5 con la oportunidad que se perdió (docs/MAILS_DE_PLAN.md, «2.5 Conteo
-- después de vencer»).
--
-- Juan, 26/10/2026: el mail a las búsquedas vencidas deja de ser solo un
-- número y muestra el mejor auto que apareció desde el vencimiento, con foto
-- y precio: «esta es la oportunidad que te perdiste». Si ya no está
-- publicado, lo dice y cuenta cuántos días duró.
--
-- expired_search_matches guarda además el puntaje y el % por debajo de
-- comparables de cada coincidencia contada (el worker ya los calcula al
-- evaluarla). missed_car elige el auto y claim_lifecycle_emails lo agrega al
-- payload como `car` al reservar el mail. Sin un auto para mostrar (todos con
-- precio parcial, por ejemplo), el payload no lleva `car` y el mail sale como
-- antes, con el conteo.
--
-- claim_lifecycle_emails se renombra a claim_lifecycle_emails_bonus (la de
-- 20261111120000) y la nueva la llama para todos los tipos.

alter table public.expired_search_matches
  add column score    smallint check (score between 0 and 100),
  add column diff_pct real;
comment on column public.expired_search_matches.score is
  'The match score the worker gave the listing when it counted it. Null on rows counted before 2026-10-26.';
comment on column public.expired_search_matches.diff_pct is
  'Percent below the comparables median (positive = cheaper), when there were enough comparables.';

-- The one car the 2.5 email shows: among what the search counted for that
-- access end, opportunities first, then the furthest below comparables, the
-- best score and the newest. Never a partial price. Null when there is none.
create function public.missed_car(p_search bigint, p_ended timestamptz) returns jsonb
language sql stable security definer set search_path = '' as $$
  select jsonb_strip_nulls(jsonb_build_object(
           'listing_id', l.id, 'title', l.title, 'make', l.make, 'model', l.model, 'trim', l.trim,
           'year', l.year, 'price', l.price, 'currency', l.currency, 'km', l.mileage_km,
           'location', l.location_text,
           'images', case when jsonb_typeof(l.images) = 'array'
                          then (select coalesce(jsonb_agg(i.value order by i.ord), '[]'::jsonb)
                                  from jsonb_array_elements(l.images) with ordinality i (value, ord)
                                 where i.ord <= 3) end,
           'below', m.level = 'high',
           'diff_pct', m.diff_pct,
           'gone', l.status = 'gone',
           -- How long it was published, only once it's gone: from its
           -- publication (or first sighting) to the last time it was seen.
           'days_listed', case when l.status = 'gone' then greatest(1, ceil(extract(epoch from
                            l.last_seen_at - coalesce(l.published_at, l.first_seen_at)) / 86400)::int) end))
    from public.expired_search_matches m
    join public.listings l on l.id = m.listing_id
   where m.search_profile_id = p_search and m.access_ended_at = p_ended
     and l.price is not null and not l.price_partial
   order by m.level = 'high' desc, m.diff_pct desc nulls last, m.score desc nulls last,
            m.created_at desc, l.id desc
   limit 1
$$;

alter function public.claim_lifecycle_emails(text, interval, integer) rename to claim_lifecycle_emails_bonus;

create function public.claim_lifecycle_emails(p_kind text, p_window interval, p_limit integer)
returns setof public.lifecycle_emails
language plpgsql security definer set search_path = '' as $$
declare
  r public.lifecycle_emails;
  v_car jsonb;
begin
  for r in select * from public.claim_lifecycle_emails_bonus(p_kind, p_window, p_limit) loop
    if r.kind = 'count_after_expiry' and r.search_profile_id is not null then
      begin
        v_car := public.missed_car(r.search_profile_id, (r.payload->>'ended_at')::timestamptz);
      exception when others then
        v_car := null;
      end;
      if v_car is not null then
        update public.lifecycle_emails set payload = payload || jsonb_build_object('car', v_car)
         where id = r.id
        returning * into r;
      end if;
    end if;
    return next r;
  end loop;
end $$;

revoke all on function public.claim_lifecycle_emails_bonus(text, interval, integer),
  public.missed_car(bigint, timestamptz), public.claim_lifecycle_emails(text, interval, integer)
  from public, anon, authenticated;
grant execute on function public.claim_lifecycle_emails(text, interval, integer) to service_role;

notify pgrst, 'reload schema';

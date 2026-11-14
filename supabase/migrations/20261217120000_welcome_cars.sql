-- Bienvenida con autos (docs/MAILS_DE_PLAN.md, search_activated).
--
-- El 14/11/2026, de 480 cuentas con una búsqueda, 98 tenían coincidencias ya
-- publicadas y ninguna alerta: una alerta solo sale por un auto nuevo. La
-- bienvenida decía «Ya encontramos N autos» sin mostrar ninguno. Ahora lleva
-- los 3 mejores de la búsqueda que eligió, para que el primer email ya
-- muestre un auto.
--
-- Solo lo que la cuenta puede ver: publicaciones activas, con precio completo,
-- dentro del cupo de la prueba (free_result_allowed) y que no descartó. Sin
-- autos, el payload no lleva `cars` y el email queda como estaba.
set local lock_timeout = '5s';

-- The best visible matches of one search, best level first, then score.
create function public.welcome_cars(p_user uuid, p_search bigint, p_limit integer default 3) returns jsonb
language sql stable security definer set search_path = '' as $$
  select coalesce(jsonb_agg(c.car order by c.ord), '[]'::jsonb)
    from (
      select row_number() over (order by case m.level when 'high' then 3 when 'good' then 2 else 1 end desc,
                                         m.score desc, m.id) as ord,
             jsonb_strip_nulls(jsonb_build_object(
               'listing_id', l.id, 'title', l.title, 'make', l.make, 'model', l.model, 'trim', l.trim,
               'year', l.year, 'price', l.price, 'currency', l.currency, 'km', l.mileage_km,
               'location', l.location_text,
               'image', case when jsonb_typeof(l.images) = 'array' then l.images->0 end,
               'level', m.level,
               'diff_pct', case when m.level = 'high' and jsonb_typeof(m.price_ref->'diff_pct') = 'number'
                                then m.price_ref->'diff_pct' end)) as car
        from public.matches m
        join public.search_profiles sp on sp.id = m.search_profile_id
        join public.listings l on l.id = m.listing_id
       where sp.id = p_search and sp.user_id = p_user
         and m.level in ('high', 'good', 'match')
         and l.status = 'active' and l.price is not null and not l.price_partial
         and public.free_result_allowed(p_user, m.listing_id)
         and not exists (select 1 from public.user_listing_interactions i
                          where i.user_id = p_user and i.listing_id = m.listing_id and i.status = 'discarded')
       order by 1
       limit greatest(coalesce(p_limit, 3), 0)) c
$$;
revoke all on function public.welcome_cars(uuid, bigint, integer) from public, anon, authenticated;

alter function public.claim_lifecycle_emails(text, interval, integer) rename to claim_lifecycle_emails_counts;

create function public.claim_lifecycle_emails(p_kind text, p_window interval, p_limit integer)
returns setof public.lifecycle_emails
language plpgsql security definer set search_path = '' as $$
declare
  r public.lifecycle_emails;
  v_cars jsonb;
begin
  for r in select * from public.claim_lifecycle_emails_counts(p_kind, p_window, p_limit) loop
    if r.kind = 'search_activated' and r.search_profile_id is not null then
      v_cars := public.welcome_cars(r.user_id, r.search_profile_id);
      if jsonb_array_length(v_cars) > 0 then
        update public.lifecycle_emails e
           set payload = e.payload || jsonb_build_object('cars', v_cars)
         where e.id = r.id
        returning * into r;
      end if;
    end if;
    return next r;
  end loop;
end $$;

revoke all on function public.claim_lifecycle_emails_counts(text, interval, integer),
  public.claim_lifecycle_emails(text, interval, integer)
  from public, anon, authenticated;
grant execute on function public.claim_lifecycle_emails(text, interval, integer) to service_role;

notify pgrst, 'reload schema';

-- Aviso de auto cerca de la zona (docs/AVISO_CERCA_DE_ZONA.md).
--
-- El 14/11/2026, 91 de 480 cuentas con una búsqueda no tenían ningún
-- resultado, y en 58 el bloqueo principal era la zona. El aviso de zona
-- (docs/AVISO_ZONA.md) vive en la web y depende de que la persona vuelva.
-- Este llega por email: cuando aparece un auto nuevo que cumple todo menos
-- la zona, y queda cerca, se lo mostramos y la persona decide si amplía.
-- La búsqueda no se amplía sola.
--
-- * near_zone_notices: un aviso por búsqueda y publicación. Solo el worker
--   (pipeline/near_zone.py) lo lee y lo escribe.
-- * app_config.near_zone: el interruptor y sus límites. Nace apagado.
set local lock_timeout = '5s';

create table public.near_zone_notices (
  id                bigint generated always as identity primary key,
  search_profile_id bigint not null references public.search_profiles (id) on delete cascade,
  user_id           uuid not null references public.profiles (id) on delete cascade,
  listing_id        bigint not null references public.listings (id) on delete cascade,
  -- From the search's place to the listing, and the search's radius then.
  distance_km       real not null check (distance_km >= 0),
  radius_km         real not null check (radius_km > 0),
  status            text not null default 'pending' check (status in ('pending', 'sent', 'failed')),
  error             text,
  created_at        timestamptz not null default now(),
  sent_at           timestamptz,
  unique (search_profile_id, listing_id)
);
create index near_zone_notices_user_idx on public.near_zone_notices (user_id);
create index near_zone_notices_listing_idx on public.near_zone_notices (listing_id);

comment on table public.near_zone_notices is
  'Aviso de auto cerca de la zona: a new listing that passes every filter of a search but its zone, told by email once (worker pipeline/near_zone.py).';

alter table public.near_zone_notices enable row level security;
revoke all on public.near_zone_notices from public, anon, authenticated;
grant all on public.near_zone_notices to service_role;

insert into public.app_config(key, value)
values ('near_zone', jsonb_build_object(
  'enabled', false, 'max_results', 3, 'max_extra_km', 100, 'max_age_days', 3,
  'cooldown_days', 3, 'max_per_tick', 10, 'send_from', '09:00', 'send_until', '21:00'))
on conflict (key) do nothing;

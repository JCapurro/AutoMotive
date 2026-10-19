-- Búsquedas duplicadas (launch QA, 19/10/2026): two submits of the same search
-- at the same moment (two tabs, two devices) both passed the web's "is there an
-- identical active search?" check and alerted twice. The database now refuses
-- a second ACTIVE search with the same filters and place for the same user; a
-- paused copy may exist (resuming it is refused while the other is active).
--
-- jsonb::text is canonical (keys sorted, no whitespace), so equal filters hash
-- equal. A null place (todo el país) counts as one place.
--
-- Rows that already collide stay, the newest ones paused: the pilot had none
-- (checked 19/10/2026); local QA databases do.
update public.search_profiles sp
set enabled = false
where sp.enabled
  and exists (
    select 1 from public.search_profiles older
    where older.enabled
      and older.user_id = sp.user_id
      and md5(older.filters::text) = md5(sp.filters::text)
      and older.origin_lat is not distinct from sp.origin_lat
      and older.origin_lon is not distinct from sp.origin_lon
      and older.radius_km is not distinct from sp.radius_km
      and older.id < sp.id
  );

create unique index search_profiles_active_unique_idx on public.search_profiles (
  user_id,
  md5(filters::text),
  coalesce(origin_lat, 1000),
  coalesce(origin_lon, 1000),
  coalesce(radius_km, 0)
) where enabled;

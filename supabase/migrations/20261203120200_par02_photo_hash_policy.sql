-- PAR-02 resto · Fixes to app_config.risk for bases that already applied
-- 20261203120000 before it was corrected (docs/superpowers/specs/2026-11-02-par02-resto-design.md,
-- decisions 6 and 9). On an empty base 20261203120000 already writes these
-- values and this migration changes nothing.
--
-- * photo_hash.skip_sources: no source has the id 'instagram'; the Instagram
--   collectors are onlycarsusados and sc_clasificados
--   (worker/collectors/instagram.py). 'instagram' is replaced by those two ids,
--   keeping any other source Juan added.
-- * cross_source.photo_conflict_km_pct (10) and photo_conflict_price_pct (15):
--   how far apart two listings with a shared photo must be to count as other
--   data (duplicate_photos). Added only when missing.
-- Only app_config changes: the web of main does not read these keys.

set local lock_timeout = '5s';

-- Inside DO: the Supabase CLI applies a file outside a transaction block, where a
-- bare LOCK TABLE fails. Applied in a transaction (production), it holds until commit.
do $$ begin
  lock table public.app_config in share row exclusive mode;
end $$;

update public.app_config c
   set value = jsonb_set(c.value, '{photo_hash,skip_sources}', (
         select coalesce(jsonb_agg(s order by min_pos), '[]'::jsonb)
           from (select s, min(pos) as min_pos
                   from (select e.s, e.pos
                           from jsonb_array_elements_text(c.value -> 'photo_hash' -> 'skip_sources')
                                with ordinality as e(s, pos)
                          where e.s <> 'instagram'
                         union all
                         select x.s, i.pos + x.k * 0.1
                           from jsonb_array_elements_text(c.value -> 'photo_hash' -> 'skip_sources')
                                with ordinality as i(s, pos)
                          cross join (values ('onlycarsusados', 1), ('sc_clasificados', 2)) as x(s, k)
                          where i.s = 'instagram') t
                  group by s) u))
 where c.key = 'risk'
   and jsonb_typeof(c.value) = 'object'
   and jsonb_typeof(c.value -> 'photo_hash') = 'object'
   and jsonb_typeof(c.value -> 'photo_hash' -> 'skip_sources') = 'array'
   and c.value -> 'photo_hash' -> 'skip_sources' ? 'instagram';

update public.app_config c
   set value = jsonb_set(c.value, '{cross_source}',
         jsonb_build_object('photo_conflict_km_pct', 10, 'photo_conflict_price_pct', 15) || (c.value -> 'cross_source'))
 where c.key = 'risk'
   and jsonb_typeof(c.value) = 'object'
   and jsonb_typeof(c.value -> 'cross_source') = 'object'
   and not (c.value -> 'cross_source' ? 'photo_conflict_km_pct' and c.value -> 'cross_source' ? 'photo_conflict_price_pct');

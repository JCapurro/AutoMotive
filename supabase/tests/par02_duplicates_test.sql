-- PAR-02 (resto), migration 20261203120000_par02_duplicates.sql
-- (docs/superpowers/specs/2026-11-02-par02-resto-design.md): the
-- listing_duplicates and photo_hash_runs tables, their keys, checks, cascade
-- and RLS, the new app_config.risk keys and app_config.red_flags.order. The
-- re-run below repeats the migration's config statements to check they keep
-- what /admin/config tuned. The job is tested in
-- worker/tests/test_risk_duplicates_postgres.py.
-- Run with: supabase test db
begin;
create extension if not exists pgtap with schema extensions;
select no_plan();

-- ---------------------------------------------------------------- listing_duplicates
select has_table('public', 'listing_duplicates', 'listing_duplicates exists');
select col_is_pk('public', 'listing_duplicates', array['listing_id', 'other_id'], 'its key is (listing_id, other_id)');
select col_not_null('public', 'listing_duplicates', 'shown', 'shown is not null');
select col_not_null('public', 'listing_duplicates', 'kind', 'kind is not null');
select col_is_null('public', 'listing_duplicates', 'photo_distance', 'photo_distance is nullable');
select has_index('public', 'listing_duplicates', 'listing_duplicates_other_id_idx', 'indexed by other_id');
select fk_ok('public', 'listing_duplicates', 'listing_id', 'public', 'listings', 'id');
select fk_ok('public', 'listing_duplicates', 'other_id', 'public', 'listings', 'id');
select is((select relrowsecurity from pg_class where oid = 'public.listing_duplicates'::regclass), true,
          'RLS is enabled on listing_duplicates');
select is((select count(*)::int from pg_policies where schemaname = 'public' and tablename = 'listing_duplicates'), 0,
          'listing_duplicates has no policy');

insert into public.listings (source, external_id, url, title, make, model, year)
values ('mercadolibre', 'par02-dup-a', 'https://example.test/a', 'Ford Fiesta', 'Ford', 'Fiesta', 2017),
       ('mercadolibre', 'par02-dup-b', 'https://example.test/b', 'Ford Fiesta', 'Ford', 'Fiesta', 2017);

select lives_ok($$
  insert into public.listing_duplicates (listing_id, other_id, kind, shown, evidence)
  select a.id, b.id, 'cross_source_data', false, '{"km_pct": 1}'
    from public.listings a, public.listings b
   where a.external_id = 'par02-dup-a' and b.external_id = 'par02-dup-b'
$$, 'a pair is stored');
select throws_ok($$
  insert into public.listing_duplicates (listing_id, other_id, kind, shown)
  select a.id, a.id, 'duplicate_photos', true from public.listings a where a.external_id = 'par02-dup-a'
$$, '23514', null, 'a listing is never its own duplicate');
select throws_ok($$
  insert into public.listing_duplicates (listing_id, other_id, kind, shown)
  select b.id, a.id, 'same_seller', true
    from public.listings a, public.listings b where a.external_id = 'par02-dup-a' and b.external_id = 'par02-dup-b'
$$, '23514', null, 'kind is a closed list');
select throws_ok($$
  insert into public.listing_duplicates (listing_id, other_id, kind, shown, photo_distance)
  select b.id, a.id, 'duplicate_photos', true, 65
    from public.listings a, public.listings b where a.external_id = 'par02-dup-a' and b.external_id = 'par02-dup-b'
$$, '23514', null, 'photo_distance is at most 64 bits');

delete from public.listings where external_id = 'par02-dup-b';
select is((select count(*)::int from public.listing_duplicates d
             join public.listings a on a.id = d.listing_id where a.external_id = 'par02-dup-a'), 0,
          'deleting a listing deletes its pairs');

-- ---------------------------------------------------------------- photo_hash_runs
select has_table('public', 'photo_hash_runs', 'photo_hash_runs exists');
select has_index('public', 'photo_hash_runs', 'photo_hash_runs_started_at_idx', 'indexed by started_at');
select fk_ok('public', 'photo_hash_runs', 'listing_id', 'public', 'listings', 'id');
select is((select relrowsecurity from pg_class where oid = 'public.photo_hash_runs'::regclass), true,
          'RLS is enabled on photo_hash_runs');
insert into public.photo_hash_runs (listing_id, images_requested)
select id, 3 from public.listings where external_id = 'par02-dup-a';
delete from public.listings where external_id = 'par02-dup-a';
select is((select count(*)::int from public.photo_hash_runs where listing_id is null and images_requested = 3), 1,
          'a run outlives its listing (set null): the budget still counts it');

-- ---------------------------------------------------------------- users see nothing
set local role authenticated;
select throws_ok($$select * from public.listing_duplicates$$, '42501', null, 'authenticated cannot read listing_duplicates');
select throws_ok($$select * from public.photo_hash_runs$$, '42501', null, 'authenticated cannot read photo_hash_runs');
reset role;
set local role anon;
select throws_ok($$select * from public.listing_duplicates$$, '42501', null, 'anon cannot read listing_duplicates');
reset role;

-- ---------------------------------------------------------------- app_config
select is((select value -> 'photo_hash' ->> 'enabled' from public.app_config where key = 'risk'), 'false',
          'the photo hash is off by default');
select is((select value -> 'photo_hash' -> 'skip_sources' from public.app_config where key = 'risk'),
          '["facebook", "instagram"]'::jsonb, 'Facebook and Instagram images are never downloaded by default');
select is((select (value ->> 'photo_hash_count')::int from public.app_config where key = 'risk'), 3, 'photo_hash_count = 3');
select is((select (value ->> 'phash_max_distance')::int from public.app_config where key = 'risk'), 6, 'phash_max_distance = 6');
select is((select value -> 'signals' from public.app_config where key = 'risk'),
          '{"private_many_listings": "on", "cross_source_photos": "on", "cross_source_data": "shadow", "duplicate_photos": "on"}'::jsonb,
          'the data-only duplicate starts in shadow');
select is((select value -> 'cross_source' from public.app_config where key = 'risk'),
          '{"km_tol_pct": 3, "price_tol_pct": 5, "data_min_km": 10000, "data_max_dist_km": 50}'::jsonb,
          'cross_source tolerances');
select ok((select value ? 'checklist_enabled' and value ? 'links' from public.app_config where key = 'risk'),
          'risk keeps checklist_enabled and links');
select is((select jsonb_array_length(value -> 'order') from public.app_config where key = 'red_flags'), 19,
          'red_flags.order lists the 19 ids');
select is((select value -> 'order' -> 0 from public.app_config where key = 'red_flags'), '"duplicate_photos"'::jsonb,
          'duplicate_photos goes first');
select is((select (value ->> 'much_cheaper_pct')::int from public.app_config where key = 'red_flags'), 25,
          'the red_flags thresholds did not change');

-- Values tuned from /admin/config survive a re-run.
update public.app_config set value = value || '{"phash_max_distance": 4, "checklist_enabled": false,
  "signals": {"cross_source_data": "on"}}' where key = 'risk';
update public.app_config set value = value || '{"order": ["much_cheaper"]}' where key = 'red_flags';

update public.app_config c
   set value = jsonb_build_object(
         'photo_hash_count', 3, 'phash_max_distance', 6,
         'photo_hash', jsonb_build_object('enabled', false),
         'cross_source', jsonb_build_object('km_tol_pct', 3),
         'signals', jsonb_build_object('cross_source_data', 'shadow')) || c.value
 where c.key = 'risk' and jsonb_typeof(c.value) = 'object';
update public.app_config
   set value = value || jsonb_build_object('order', jsonb_build_array('duplicate_photos'))
 where key = 'red_flags' and jsonb_typeof(value) = 'object' and not (value ? 'order');

select is((select (value ->> 'phash_max_distance')::int from public.app_config where key = 'risk'), 4,
          'a re-run keeps a tuned phash_max_distance');
select is((select value -> 'signals' ->> 'cross_source_data' from public.app_config where key = 'risk'), 'on',
          'a re-run keeps tuned signals');
select is((select value ->> 'checklist_enabled' from public.app_config where key = 'risk'), 'false',
          'a re-run keeps checklist_enabled');
select is((select value -> 'order' from public.app_config where key = 'red_flags'), '["much_cheaper"]'::jsonb,
          'a re-run keeps a tuned order');

select * from finish();
rollback;

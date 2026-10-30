-- F-02 paso 1 (migration 20261123120000_f02_seller_count.sql,
-- docs/superpowers/specs/2026-10-30-f02-vendedor-design.md): the seller key and
-- count columns, their partial index, the runs table, the config row and the
-- admin_seller_coverage view. The job is tested in
-- worker/tests/test_seller_classification_postgres.py.
-- Run with: supabase test db
begin;
create extension if not exists pgtap with schema extensions;
select no_plan();

-- ---------------------------------------------------------------- columns and index
select has_column('public', 'listings', 'seller_key', 'listings.seller_key exists');
select col_type_is('public', 'listings', 'seller_key', 'text', 'seller_key is text');
select col_is_null('public', 'listings', 'seller_key', 'seller_key is nullable');
select has_column('public', 'listings', 'seller_listing_count', 'listings.seller_listing_count exists');
select col_type_is('public', 'listings', 'seller_listing_count', 'integer', 'seller_listing_count is integer');
select col_is_null('public', 'listings', 'seller_listing_count', 'seller_listing_count is nullable');
select hasnt_column('public', 'listings', 'dealer_inferred', 'no dealer_inferred in step 1');

select has_index('public', 'listings', 'listings_seller_key_idx', array['source', 'seller_key'],
                 'listings_seller_key_idx on (source, seller_key)');
select is((select pg_get_expr(i.indpred, i.indrelid)
             from pg_index i join pg_class c on c.oid = i.indexrelid
            where c.relname = 'listings_seller_key_idx'),
          '((status = ''active''::listing_status) AND (seller_key IS NOT NULL))',
          'the index is partial: active listings with a key');

-- seller_type and its CHECK did not change.
insert into public.sources(id, name, crawl_interval_seconds) values ('f02test', 'F-02 test', 3600);
select throws_ok($$insert into public.listings(source, external_id, url, title, seller_type)
                   values ('f02test', 'bad', 'https://example.test/bad', 'x', 'dealer_inferred')$$,
                 '23514', null, 'seller_type still rejects dealer_inferred');

-- ---------------------------------------------------------------- runs table
select has_table('public', 'seller_classification_runs', 'seller_classification_runs exists');
select lives_ok($$insert into public.seller_classification_runs(trigger, mode) values ('cli', 'dry_run')$$,
                'a run with the defaults');
select is((select status from public.seller_classification_runs order by id desc limit 1), 'running',
          'a run starts as running');
select throws_ok($$insert into public.seller_classification_runs(trigger, mode) values ('ingest', 'write')$$,
                 '23514', null, 'trigger is startup, nightly or cli');
select throws_ok($$insert into public.seller_classification_runs(trigger, mode) values ('cli', 'preview')$$,
                 '23514', null, 'mode is dry_run or write');
select throws_ok($$insert into public.seller_classification_runs(trigger, mode, status) values ('cli', 'write', 'done')$$,
                 '23514', null, 'status is running, ok or failed');

-- ---------------------------------------------------------------- config and idempotency
select is((select value from public.app_config where key = 'seller_classification'),
          '{"enabled": true, "min_listings": 6, "window_days": 30}'::jsonb,
          'seller_classification is born enabled, 6 listings, 30 days');
update public.app_config set value = '{"enabled": false, "min_listings": 8, "window_days": 20}'
 where key = 'seller_classification';
insert into public.app_config (key, value)
values ('seller_classification', '{"enabled": true, "min_listings": 6, "window_days": 30}')
on conflict (key) do nothing;
select is((select value from public.app_config where key = 'seller_classification'),
          '{"enabled": false, "min_listings": 8, "window_days": 20}'::jsonb,
          'a re-run of the insert keeps an edited row');
select is((select count(*)::int from public.app_config where key = 'seller_classification'), 1,
          'a re-run adds no row');

-- ---------------------------------------------------------------- the coverage view
-- f02test: 4 active (one with nothing, one private over the threshold, one
-- dealer under it, one with a blank name) and a gone one that must not count.
insert into public.listings(source, external_id, url, title, seller_type, seller_name, seller_key,
                            seller_listing_count, status) values
  ('f02test', 'a1', 'https://example.test/a1', 'x', null,      null,       null,       null, 'active'),
  ('f02test', 'a2', 'https://example.test/a2', 'x', 'private', 'Juan',     'juan',     6,    'active'),
  ('f02test', 'a3', 'https://example.test/a3', 'x', 'dealer',  'Autos SA', 'autos sa', 5,    'active'),
  ('f02test', 'a4', 'https://example.test/a4', 'x', 'private', '  ',       null,       null, 'active'),
  ('f02test', 'g1', 'https://example.test/g1', 'x', null,      null,       null,       9,    'gone');

update public.app_config set value = '{"enabled": true, "min_listings": 6, "window_days": 30}'
 where key = 'seller_classification';
select results_eq(
  $$select active::int, seller_type_null::int, seller_type_null_pct, seller_name_null::int, seller_name_null_pct,
           seller_key_null::int, seller_key_null_pct, over_threshold::int, min_listings
      from public.admin_seller_coverage where source = 'f02test'$$,
  $$values (4, 1, 25.0::numeric, 2, 50.0::numeric, 2, 50.0::numeric, 1, 6)$$,
  'per source: active, nulls and their %, over the threshold (gone left out)');

update public.app_config set value = jsonb_set(value, '{min_listings}', '5') where key = 'seller_classification';
select is((select over_threshold::int from public.admin_seller_coverage where source = 'f02test'), 2,
          'min_listings 5 counts the group of 5');

-- Every value the worker rejects falls back to 6 (review NEW-C: no cast can raise).
update public.app_config set value = jsonb_set(value, '{min_listings}', '"seis"') where key = 'seller_classification';
select is((select over_threshold::int || '/' || min_listings from public.admin_seller_coverage where source = 'f02test'),
          '1/6', 'min_listings "seis" -> 6');
update public.app_config set value = jsonb_set(value, '{min_listings}', '"5"') where key = 'seller_classification';
select is((select over_threshold::int || '/' || min_listings from public.admin_seller_coverage where source = 'f02test'),
          '1/6', 'min_listings "5" -> 6');
update public.app_config set value = jsonb_set(value, '{min_listings}', '5.5') where key = 'seller_classification';
select is((select over_threshold::int || '/' || min_listings from public.admin_seller_coverage where source = 'f02test'),
          '1/6', 'min_listings 5.5 -> 6');
update public.app_config set value = jsonb_set(value, '{min_listings}', '1') where key = 'seller_classification';
select is((select over_threshold::int || '/' || min_listings from public.admin_seller_coverage where source = 'f02test'),
          '1/6', 'min_listings 1 -> 6');
update public.app_config set value = jsonb_set(value, '{min_listings}', '101') where key = 'seller_classification';
select is((select over_threshold::int || '/' || min_listings from public.admin_seller_coverage where source = 'f02test'),
          '1/6', 'min_listings 101 -> 6');
update public.app_config set value = jsonb_set(value, '{min_listings}', 'true') where key = 'seller_classification';
select is((select over_threshold::int || '/' || min_listings from public.admin_seller_coverage where source = 'f02test'),
          '1/6', 'min_listings true -> 6');
update public.app_config set value = jsonb_set(value, '{min_listings}', 'null') where key = 'seller_classification';
select is((select over_threshold::int || '/' || min_listings from public.admin_seller_coverage where source = 'f02test'),
          '1/6', 'min_listings null -> 6');
update public.app_config set value = jsonb_set(value, '{min_listings}', '[5]') where key = 'seller_classification';
select is((select over_threshold::int || '/' || min_listings from public.admin_seller_coverage where source = 'f02test'),
          '1/6', 'min_listings [5] -> 6');
update public.app_config set value = jsonb_set(value, '{min_listings}', '99999999999999') where key = 'seller_classification';
select is((select over_threshold::int || '/' || min_listings from public.admin_seller_coverage where source = 'f02test'),
          '1/6', 'min_listings 99999999999999 -> 6');
update public.app_config set value = '[]' where key = 'seller_classification';
select is((select min_listings from public.admin_seller_coverage where source = 'f02test'), 6,
          'a config that is not an object -> 6');
delete from public.app_config where key = 'seller_classification';
select is((select over_threshold::int || '/' || min_listings from public.admin_seller_coverage where source = 'f02test'),
          '1/6', 'no config row -> 6');

-- ---------------------------------------------------------------- access: service role only
set local role anon;
select throws_ok($$select * from public.app_config$$, '42501', null, 'anon cannot read app_config');
select throws_ok($$select * from public.seller_classification_runs$$, '42501', null, 'anon cannot read the runs');
select throws_ok($$select * from public.admin_seller_coverage$$, '42501', null, 'anon cannot read the coverage');
reset role;
set local role authenticated;
select throws_ok($$select * from public.app_config$$, '42501', null, 'users cannot read app_config');
select throws_ok($$select * from public.seller_classification_runs$$, '42501', null, 'users cannot read the runs');
select throws_ok($$insert into public.seller_classification_runs(trigger, mode) values ('cli', 'write')$$,
                 '42501', null, 'users cannot write the runs');
select throws_ok($$select * from public.admin_seller_coverage$$, '42501', null, 'users cannot read the coverage');
reset role;
set local role service_role;
select lives_ok($$select * from public.admin_seller_coverage$$, 'the service role reads the coverage');
select lives_ok($$insert into public.seller_classification_runs(trigger, mode) values ('nightly', 'write')$$,
                'the service role writes the runs');
reset role;

select * from finish();
rollback;

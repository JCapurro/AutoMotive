-- F-02 paso 1 (migration 20261123120000_f02_seller_count.sql), paso 2
-- (20261124120000_f02_dealer_inferred.sql) and paso 3
-- (20261125120000_f02_price_ref_by_seller.sql),
-- docs/superpowers/specs/2026-10-30-f02-vendedor-design.md: the seller key and
-- count columns, their partial index, the runs table, the config row, the
-- dealer_inferred column, the admin_seller_coverage view and the seller
-- medians of comparables(). The job is tested in
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
-- Step 2: dealer_inferred («posible agencia»), apart from seller_type.
select has_column('public', 'listings', 'dealer_inferred', 'listings.dealer_inferred exists');
select col_type_is('public', 'listings', 'dealer_inferred', 'boolean', 'dealer_inferred is boolean');
select col_not_null('public', 'listings', 'dealer_inferred', 'dealer_inferred is not null');
select col_default_is('public', 'listings', 'dealer_inferred', 'false', 'dealer_inferred defaults to false');

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

-- Step 2: the view keeps the step-1 columns in order and adds two at the end.
select is((select array_agg(column_name::text order by ordinal_position)
             from information_schema.columns
            where table_schema = 'public' and table_name = 'admin_seller_coverage'),
          array['source', 'active', 'seller_type_null', 'seller_type_null_pct', 'seller_name_null',
                'seller_name_null_pct', 'seller_key_null', 'seller_key_null_pct', 'over_threshold',
                'min_listings', 'dealer_inferred', 'seller_unknown_pct'],
          'admin_seller_coverage: step-1 columns in order, then dealer_inferred and seller_unknown_pct');
select results_eq(
  $$select dealer_inferred::int, seller_unknown_pct from public.admin_seller_coverage where source = 'f02test'$$,
  $$values (0, 25.0::numeric)$$,
  'nothing inferred: unknown = the active ones without a seller type');
update public.listings set dealer_inferred = true where source = 'f02test' and external_id in ('a1', 'a2', 'g1');
select results_eq(
  $$select dealer_inferred::int, seller_unknown_pct from public.admin_seller_coverage where source = 'f02test'$$,
  $$values (2, 0.0::numeric)$$,
  'an inferred listing without a type is no longer unknown; a gone one is not counted');

-- ---------------------------------------------------------------- step 3: comparables() by seller
-- Migration 20261125120000_f02_price_ref_by_seller.sql. dealer = seller_type
-- 'dealer' or dealer_inferred; private = seller_type 'private' and not inferred;
-- the rest (no type, not inferred) is neither. Over the same pool and cascade
-- level as n. The seven old keys are checked against literals worked out by
-- hand (the old body cannot run once the migration is applied): sorted prices
-- p0..p(n-1), percentile_cont(f) = p[k] + (p[k+1] - p[k]) * frac((n-1) * f).
-- Source kavak: not in confirm_sources, so no crawl target drops anything.
create function pg_temp.f02_listing(p_model text, p_ext text, p_trim text, p_transmission text, p_price numeric,
                                    p_km integer, p_seller_type text, p_inferred boolean) returns void
language sql as $$
  insert into public.listings (source, external_id, url, title, make, model, trim, year, price, currency, price_usd,
                               mileage_km, transmission, seller_type, dealer_inferred)
  values ('kavak', 'f02-' || p_model || '-' || p_ext, 'https://example.test/f02/' || p_model || '/' || p_ext,
          'F02cmp ' || p_model, 'F02cmp', p_model, p_trim, 2017, p_price, 'USD', p_price, p_km, p_transmission,
          p_seller_type, p_inferred)
$$;
create function pg_temp.f02_ref(p_model text) returns jsonb language sql as $$
  select public.comparables(l.id) from public.listings l where l.external_id = 'f02-' || p_model || '-target'
$$;
create function pg_temp.f02_old(p_ref jsonb) returns text language sql as $$
  select (p_ref - array['dealer_median', 'dealer_n', 'private_median', 'private_n'])::text
$$;

-- Level 1 (trim_transmission), n = 11: 3 dealer, 2 inferred (one says private,
-- one says nothing), 4 private, 2 with no seller data.
select pg_temp.f02_listing('L1', 'target', 'X', 'manual', 10000, 100000, 'private', false);
select pg_temp.f02_listing('L1', e, 'X', 'manual', p, k, st, inf)
  from (values ('d1',  10000,  80000, 'dealer',  false), ('d2', 11000,  84000, 'dealer',  false),
               ('d3',  12000,  88000, 'dealer',  false), ('i1', 13000,  92000, 'private', true),
               ('i2',  14000,  96000, null,      true),  ('p1',  9000, 100000, 'private', false),
               ('p2',   9500, 104000, 'private', false), ('p3', 10500, 108000, 'private', false),
               ('p4',  15000, 112000, 'private', false), ('u1',  8000, 116000, null,      false),
               ('u2',  16000, 120000, null,      false)) v (e, p, k, st, inf);
-- Prices 8000 9000 9500 10000 10500 11000 12000 13000 14000 15000 16000:
-- median p5 = 11000; p25 at 2.5 = 9750; p75 at 7.5 = 13500; km 80000..120000
-- step 4000 → 100000; diff_pct = (1 - 10000 / 11000) * 100 = 9.0909 → 9.09.
select is(pg_temp.f02_old(pg_temp.f02_ref('L1')),
          '{"n": 11, "p25": 9750.00, "p75": 13500.00, "median": 11000.00, "diff_pct": 9.09, '
          '"median_km": 100000, "level_used": "trim_transmission"}',
          'level 1: the seven old keys, byte for byte, as before the migration');
-- Dealer: 10000 11000 12000 13000 14000 → 5, median 12000. Private: 9000 9500
-- 10500 15000 → 4, median (9500 + 10500) / 2 = 10000.
select is((pg_temp.f02_ref('L1') - array['n', 'p25', 'p75', 'median', 'diff_pct', 'median_km', 'level_used'])::text,
          '{"dealer_n": 5, "private_n": 4, "dealer_median": 12000.00, "private_median": 10000.00}',
          'level 1: dealer_n 5 (3 dealer + 2 inferred), private_n 4, and their medians');
select ok((r->>'dealer_n')::int + (r->>'private_n')::int <= (r->>'n')::int,
          'level 1: dealer_n + private_n <= n (the two without seller data are in neither)')
  from pg_temp.f02_ref('L1') r;

-- Level 2 (transmission): 2 with the target's trim (< min_n 5), 4 more with
-- another trim and the same transmission, 3 automatic (only in level 3).
select pg_temp.f02_listing('L2', 'target', 'X', 'manual', 10000, 100000, null, false);
select pg_temp.f02_listing('L2', e, t, tr, p, 100000, st, inf)
  from (values ('x1', 'X', 'manual',    10000, 'dealer',  false), ('x2', 'X', 'manual',    12000, 'private', true),
               ('y1', 'Y', 'manual',     9000, 'private', false), ('y2', 'Y', 'manual',    11000, 'private', false),
               ('y3', 'Y', 'manual',    13000, null,      false), ('y4', 'Y', 'manual',    15000, 'dealer',  false),
               ('a1', 'X', 'automatic', 20000, 'dealer',  false), ('a2', 'X', 'automatic', 21000, 'dealer',  false),
               ('a3', 'X', 'automatic', 22000, 'private', false)) v (e, t, tr, p, st, inf);
-- Prices 9000 10000 11000 12000 13000 15000: median 11500; p25 at 1.25 =
-- 10250; p75 at 3.75 = 12750; diff_pct = (1 - 10000 / 11500) * 100 = 13.04.
select is(pg_temp.f02_old(pg_temp.f02_ref('L2')),
          '{"n": 6, "p25": 10250.00, "p75": 12750.00, "median": 11500.00, "diff_pct": 13.04, '
          '"median_km": 100000, "level_used": "transmission"}',
          'level 2: the seven old keys, byte for byte');
-- Dealer: 10000 12000 15000 → 3, median 12000. Private: 9000 11000 → 2, 10000.
-- The automatic ones (two dealers, one private) are not in this level.
select is((pg_temp.f02_ref('L2') - array['n', 'p25', 'p75', 'median', 'diff_pct', 'median_km', 'level_used'])::text,
          '{"dealer_n": 3, "private_n": 2, "dealer_median": 12000.00, "private_median": 10000.00}',
          'level 2: the seller medians come from the level''s pool, not the whole model');
select ok((r->>'dealer_n')::int + (r->>'private_n')::int <= (r->>'n')::int, 'level 2: dealer_n + private_n <= n')
  from pg_temp.f02_ref('L2') r;

-- Level 3 (model), n = 4 < min_n: the model level with its small n.
select pg_temp.f02_listing('L3', 'target', 'X', 'manual', 12650, 100000, 'dealer', false);
select pg_temp.f02_listing('L3', e, t, tr, p, 100000, st, inf)
  from (values ('x1', 'X', 'manual',    10000, 'private', false), ('y1', 'Y', 'manual', 11000, 'dealer', false),
               ('y2', 'Y', 'manual',    12000, null,      false), ('a1', 'X', 'automatic', 13000, null, true))
       v (e, t, tr, p, st, inf);
-- Prices 10000 11000 12000 13000: median 11500; p25 at 0.75 = 10750; p75 at
-- 2.25 = 12250; diff_pct = (1 - 12650 / 11500) * 100 = -10.00.
select is(pg_temp.f02_old(pg_temp.f02_ref('L3')),
          '{"n": 4, "p25": 10750.00, "p75": 12250.00, "median": 11500.00, "diff_pct": -10.00, '
          '"median_km": 100000, "level_used": "model"}',
          'level 3: the seven old keys, byte for byte');
select is((pg_temp.f02_ref('L3') - array['n', 'p25', 'p75', 'median', 'diff_pct', 'median_km', 'level_used'])::text,
          '{"dealer_n": 2, "private_n": 1, "dealer_median": 12000.00, "private_median": 10000.00}',
          'level 3: dealer 11000 and the inferred 13000, private 10000; the target''s own type does not count');
select ok((r->>'dealer_n')::int + (r->>'private_n')::int <= (r->>'n')::int, 'level 3: dealer_n + private_n <= n')
  from pg_temp.f02_ref('L3') r;

-- No dealers: dealer_n 0 and a null median (the key is there).
select pg_temp.f02_listing('L4', 'target', 'X', 'manual', 10000, 100000, null, false);
select pg_temp.f02_listing('L4', e, 'X', 'manual', p, 100000, st, false)
  from (values ('p1', 9000, 'private'), ('p2', 10000, 'private'), ('p3', 11000, 'private'),
               ('u1', 12000, null), ('u2', 13000, null)) v (e, p, st);
select is((pg_temp.f02_ref('L4') - array['n', 'p25', 'p75', 'median', 'diff_pct', 'median_km', 'level_used'])::text,
          '{"dealer_n": 0, "private_n": 3, "dealer_median": null, "private_median": 10000.00}',
          'no dealers: dealer_n 0 and dealer_median null');
-- An empty level (no comparables at all): both counts 0, both medians null.
select pg_temp.f02_listing('L5', 'target', 'X', 'manual', 10000, 100000, null, false);
select is((pg_temp.f02_ref('L5') - array['p25', 'p75', 'median', 'diff_pct', 'median_km'])::text,
          '{"n": 0, "dealer_n": 0, "private_n": 0, "level_used": "model", "dealer_median": null, "private_median": null}',
          'no comparables: n 0, both counts 0, both medians null');

-- Same function as before: plain SQL, stable, invoker, search_path '', the
-- same signature, and still only the worker's.
select is((select p.prosecdef::text || ' ' || p.provolatile::text || ' ' || l.lanname || ' ' || p.proconfig::text || ' '
                  || p.prorettype::regtype::text
             from pg_proc p join pg_language l on l.oid = p.prolang
            where p.oid = 'public.comparables(bigint,integer,integer,numeric,integer)'::regprocedure),
          'false s sql {"search_path=\"\""} jsonb',
          'comparables(): not security definer, stable, sql, search_path "", returns jsonb');
select is((select count(*)::int from pg_proc where proname = 'comparables' and pronamespace = 'public'::regnamespace),
          1, 'comparables(): no second overload');
select is(array(select r from unnest(array['anon', 'authenticated']) r
                 where has_function_privilege(r, 'public.comparables(bigint,integer,integer,numeric,integer)', 'execute')),
          '{}'::text[], 'comparables(): anon and authenticated still cannot execute it');
select ok(has_function_privilege('service_role', 'public.comparables(bigint,integer,integer,numeric,integer)', 'execute'),
          'comparables(): the service role (the worker) still can');

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

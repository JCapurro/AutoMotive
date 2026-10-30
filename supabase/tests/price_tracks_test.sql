-- PAR-03 (migration 20261121120000_par03_price_tracks.sql): listing_price_tracks()
-- counts drops between consecutive distinct prices, the cumulative fall since
-- the first snapshot, app_config.price_track.min_drop_pct and the grants.
-- Run with: supabase test db
begin;
create extension if not exists pgtap with schema extensions;
select plan(42);

insert into public.listings (id, source, external_id, url, title, make, model, price, currency, price_usd)
overriding system value
select 997000 + n, 'mercadolibre', 'PAR03-' || n, 'https://example.test/par03-' || n, 'Pgtap Baja ' || n,
       'Pgtap', 'Baja', 10000, 'USD', 10000
  from generate_series(1, 12) n;

-- t(k): k days ago at noon, so the order is unambiguous.
create temporary table t_snap (listing_id bigint, days integer, price numeric, currency text, price_usd numeric,
                               fx_rate numeric, kind text default 'price');
insert into t_snap values
  -- 1: one drop, USD
  (997001, 10, 10000, 'USD', 10000, null, 'new'), (997001, 5, 9000, 'USD', 9000, null, 'price'),
  -- 2: three drops, USD
  (997002, 10, 20000, 'USD', 20000, null, 'new'), (997002, 8, 19000, 'USD', 19000, null, 'price'),
  (997002, 6, 18000, 'USD', 18000, null, 'price'), (997002, 4, 17000, 'USD', 17000, null, 'price'),
  -- 3: a drop and then a rise above the first price (net rise)
  (997003, 10, 10000, 'USD', 10000, null, 'new'), (997003, 6, 9000, 'USD', 9000, null, 'price'),
  (997003, 2, 11000, 'USD', 11000, null, 'price'),
  -- 4: repeated prices collapse (a mileage change keeps the price)
  (997004, 10, 10000, 'USD', 10000, null, 'new'), (997004, 8, 10000, 'USD', 10000, null, 'mileage'),
  (997004, 6, 9500, 'USD', 9500, null, 'price'), (997004, 4, 9500, 'USD', 9500, null, 'images'),
  -- 5: ARS, own price stable, the dollar moves
  (997005, 10, 12000000, 'ARS', 10000, 1200, 'new'), (997005, 5, 12000000, 'ARS', 9000, 1333.3333, 'description'),
  -- 6: ARS -> USD, measured in price_usd
  (997006, 10, 12000000, 'ARS', 10000, 1200, 'new'), (997006, 5, 9500, 'USD', 9500, null, 'price'),
  -- 7: a fall under min_drop_pct (0,5 %)
  (997007, 10, 10000, 'USD', 10000, null, 'new'), (997007, 5, 9950, 'USD', 9950, null, 'price'),
  -- 8: no snapshots (none inserted)
  -- 9: one point, and a priceless snapshot that is ignored
  (997009, 10, 10000, 'USD', 10000, null, 'new'), (997009, 5, null, null, null, null, 'attrs'),
  -- 10: ARS drop while the dollar moves: cum_usd with the last fx_rate
  (997010, 10, 12000000, 'ARS', 10000, 1200, 'new'), (997010, 5, 10800000, 'ARS', 7200, 1500, 'price'),
  -- 11: only a rise
  (997011, 10, 10000, 'USD', 10000, null, 'new'), (997011, 5, 10500, 'USD', 10500, null, 'price'),
  -- 12: halves: 2.500,50 of 40.008 is exactly 6,25 %
  (997012, 10, 40008, 'USD', 40008, null, 'new'), (997012, 5, 37507.50, 'USD', 37507.50, null, 'price');

insert into public.listing_snapshots (listing_id, observed_at, price, currency, price_usd, fx_rate, attrs_hash, change_kind)
select listing_id, date_trunc('day', now()) - make_interval(days => days) + interval '12 hours',
       price, currency, price_usd, fx_rate, 'h', kind
  from t_snap;

create temporary table t_track as
select * from public.listing_price_tracks(array(select 997000 + n from generate_series(1, 12) n)::bigint[]);

-- ------------------------------------------------------------ config
select is((select value from public.app_config where key = 'price_track'), '{"min_drop_pct": 1}'::jsonb,
          'app_config.price_track is seeded with min_drop_pct 1');
select is(public.price_track_min_drop_pct(), 1::numeric, 'price_track_min_drop_pct reads it');

-- ------------------------------------------------------------ rows
select is((select count(*)::int from t_track), 11,
          'one row per listing with a priced snapshot (none for the listing without snapshots)');
select is((select count(*)::int from t_track where listing_id = 997008), 0, '... the listing without snapshots has none');
select is((select count(*)::int from public.listing_price_tracks('{}'::bigint[])), 0, 'an empty array returns nothing');
select is((select count(*)::int from public.listing_price_tracks(array[997001, 997001, null]::bigint[])), 1,
          'repeated and null ids return one row');

select results_eq($$select drops, rises, cum_pct, cum_usd, first_price, last_price from t_track where listing_id = 997001$$,
                  $$values (1, 0, 10.0::numeric, 1000::numeric, 10000::numeric, 9000::numeric)$$,
                  'one drop in USD: 10 %, USD 1.000');
select is((select last_drop_at from t_track where listing_id = 997001),
          date_trunc('day', now()) - interval '5 days' + interval '12 hours', '... last_drop_at is the drop');
select is((select first_at from t_track where listing_id = 997001),
          date_trunc('day', now()) - interval '10 days' + interval '12 hours', '... first_at is the first snapshot');

select results_eq($$select drops, rises, cum_pct, cum_usd from t_track where listing_id = 997002$$,
                  $$values (3, 0, 15.0::numeric, 3000::numeric)$$, 'three drops in USD');
select is((select last_drop_at from t_track where listing_id = 997002),
          date_trunc('day', now()) - interval '4 days' + interval '12 hours', '... last_drop_at is the latest drop');

select results_eq($$select drops, rises, cum_pct, cum_usd from t_track where listing_id = 997003$$,
                  $$values (1, 1, -10.0::numeric, -1000::numeric)$$,
                  'a drop and a later rise: net rise, cum_pct negative');
select ok((select cum_pct <= 0 from t_track where listing_id = 997003), '... so no net drop');

select results_eq($$select drops, rises, cum_pct, first_at from t_track where listing_id = 997004$$,
                  $$values (1, 0, 5.0::numeric, date_trunc('day', now()) - interval '10 days' + interval '12 hours')$$,
                  'repeated prices collapse: one drop from the first snapshot');

select results_eq($$select drops, rises, cum_pct, cum_usd from t_track where listing_id = 997005$$,
                  $$values (0, 0, 0.0::numeric, 0::numeric)$$,
                  'ARS with a stable price and the dollar moving: no drop');

select results_eq($$select drops, cum_pct, cum_usd, first_currency, last_currency from t_track where listing_id = 997006$$,
                  $$values (1, 5.0::numeric, 500::numeric, 'ARS'::text, 'USD'::text)$$,
                  'ARS to USD: measured in price_usd');

select results_eq($$select drops, rises, cum_pct from t_track where listing_id = 997007$$,
                  $$values (0, 0, 0.5::numeric)$$, 'a fall under min_drop_pct is no drop');

select results_eq($$select drops, rises, cum_pct, cum_usd, first_at, last_drop_at from t_track where listing_id = 997009$$,
                  $$values (0, 0, 0.0::numeric, 0::numeric,
                            date_trunc('day', now()) - interval '10 days' + interval '12 hours', null::timestamptz)$$,
                  'one point (a priceless snapshot is ignored): no drop');

select results_eq($$select drops, cum_pct, cum_usd, last_currency from t_track where listing_id = 997010$$,
                  $$values (1, 10.0::numeric, 800::numeric, 'ARS'::text)$$,
                  'ARS drop: cum_pct in pesos, cum_usd with the last fx_rate (1.200.000 / 1500)');

select results_eq($$select drops, rises, cum_pct from t_track where listing_id = 997011$$,
                  $$values (0, 1, -5.0::numeric)$$, 'only a rise: no drop');

-- The worker (Python) and the web (JS) round halves differently, so the
-- function hands both the figures already rounded as they are shown.
select results_eq($$select cum_pct, cum_usd from t_track where listing_id = 997012$$,
                  $$values (6.3::numeric, 2501::numeric)$$,
                  'halves round up here: 6,25 % is 6,3 and USD 2.500,50 is 2.501');
select ok((select scale(cum_pct) = 1 and scale(cum_usd) = 0 from t_track where listing_id = 997001),
          '... cum_pct comes with one decimal and cum_usd in whole dollars');

-- ------------------------------------------------------------ min_drop_pct follows app_config
update public.app_config set value = '{"min_drop_pct": 0.4}' where key = 'price_track';
select is((select drops from public.listing_price_tracks(array[997007]::bigint[])), 1,
          'min_drop_pct 0.4: the 0,5 % fall counts');
update public.app_config set value = '{"min_drop_pct": 6}' where key = 'price_track';
select is((select drops from public.listing_price_tracks(array[997002]::bigint[])), 0,
          'min_drop_pct 6: the 5 % steps do not count');
select is((select cum_pct from public.listing_price_tracks(array[997002]::bigint[])), 15.0::numeric,
          '... and cum_pct does not depend on it');
update public.app_config set value = '{"min_drop_pct": "x"}' where key = 'price_track';
select is(public.price_track_min_drop_pct(), 1::numeric, 'a non-numeric min_drop_pct falls back to 1');
update public.app_config set value = '{"min_drop_pct": -3}' where key = 'price_track';
select is(public.price_track_min_drop_pct(), 1::numeric, '... and so does a negative one');
delete from public.app_config where key = 'price_track';
select is(public.price_track_min_drop_pct(), 1::numeric, '... and a missing row');
insert into public.app_config (key, value) values ('price_track', '{"min_drop_pct": 1}');

-- ------------------------------------------------------------ authenticated: what it already reads
insert into auth.users (instance_id, id, aud, role, email, created_at, updated_at) values
  ('00000000-0000-0000-0000-000000000000', '97979797-9797-9797-9797-979797979797', 'authenticated', 'authenticated',
   'par03@pgtap.test', now(), now());

set local role authenticated;
set local request.jwt.claims = '{"sub": "97979797-9797-9797-9797-979797979797", "role": "authenticated"}';
select lives_ok($$select * from public.listing_price_tracks(array[997001]::bigint[])$$,
                'authenticated can call listing_price_tracks');
select is((select count(*)::int from public.listing_price_tracks(array(select 997000 + n from generate_series(1, 12) n)::bigint[])),
          (select count(distinct listing_id)::int from public.listing_snapshots
            where listing_id between 997001 and 997012 and price is not null),
          '... and gets a row for each listing whose snapshots it reads');
select results_eq($$select drops, cum_pct, cum_usd from public.listing_price_tracks(array[997002]::bigint[])$$,
                  $$values (3, 15.0::numeric, 3000::numeric)$$, '... with the same numbers');
select is(public.price_track_min_drop_pct(), 1::numeric, '... and reads the setting without reaching app_config');
select throws_ok($$select * from public.app_config$$, '42501', null, '... while app_config stays closed to it');
reset role;

set local role anon;
select throws_ok($$select * from public.listing_price_tracks(array[997001]::bigint[])$$, '42501', null,
                 'anon cannot call listing_price_tracks');
select throws_ok($$select public.price_track_min_drop_pct()$$, '42501', null, '... nor price_track_min_drop_pct');
reset role;

-- ------------------------------------------------------------ shape
select function_returns('public', 'listing_price_tracks', array['bigint[]'], 'setof record',
                        'listing_price_tracks(bigint[]) returns a set');
select is((select provolatile from pg_proc where oid = 'public.listing_price_tracks(bigint[])'::regprocedure), 's',
          '... stable');
select is((select prosecdef from pg_proc where oid = 'public.listing_price_tracks(bigint[])'::regprocedure), false,
          '... with the caller''s rights');
select is((select proconfig from pg_proc where oid = 'public.listing_price_tracks(bigint[])'::regprocedure),
          array['search_path=""'], '... and an empty search_path');
select is((select prosecdef from pg_proc where oid = 'public.price_track_min_drop_pct()'::regprocedure), true,
          'price_track_min_drop_pct runs as its owner');
select ok(has_function_privilege('service_role', 'public.listing_price_tracks(bigint[])', 'execute'),
          'service_role can execute listing_price_tracks');
select ok(not has_function_privilege('anon', 'public.listing_price_tracks(bigint[])', 'execute'),
          'anon has no execute on listing_price_tracks');

select * from finish();
rollback;

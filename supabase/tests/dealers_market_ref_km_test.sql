-- Agencias: the market reference by km and trim (migration 20270102120000_dealer_market_ref_km.sql).
-- One transaction, rolled back.
begin;
create extension if not exists pgtap with schema extensions;
select no_plan();

insert into auth.users (instance_id, id, aud, role, email, created_at, updated_at) values
  ('00000000-0000-0000-0000-000000000000', 'd8000000-0000-0000-0000-00000000000a', 'authenticated', 'authenticated', 'a@mkm.test', now(), now());
update public.app_config set value = value || '{"enabled": true}' where key = 'dealer_program';
update public.app_config set value = value || '{"min_n": 5}' where key = 'comparables';

-- Pgkm Dos, years 2016-2018. Near 100.000 km (80.000 to 120.000): 9801-9806; of those, trim «Base»: 9801-9805.
insert into public.listings (id, source, external_id, url, title, make, model, "trim", year, mileage_km, price, currency, price_usd,
                             status, price_partial, last_seen_at, attributes)
overriding system value values
  (9801, 'mercadolibre', 'MK-9801', 'https://example.test/mk-9801', 'Dos', 'Pgkm', 'Dos', 'Base',  2017,  80000,  9000, 'USD',  9000, 'active', false, now(), '{}'),
  (9802, 'mercadolibre', 'MK-9802', 'https://example.test/mk-9802', 'Dos', 'Pgkm', 'Dos', 'BASE',  2017,  95000,  9200, 'USD',  9200, 'active', false, now(), '{}'),
  (9803, 'kavak',        'MK-9803', 'https://example.test/mk-9803', 'Dos', 'Pgkm', 'Dos', ' base ', 2016, 100000,  9400, 'USD',  9400, 'active', false, now(), '{}'),
  (9804, 'kavak',        'MK-9804', 'https://example.test/mk-9804', 'Dos', 'Pgkm', 'Dos', 'Base',  2018, 110000,  9600, 'USD',  9600, 'active', false, now(), '{}'),
  (9805, 'mercadolibre', 'MK-9805', 'https://example.test/mk-9805', 'Dos', 'Pgkm', 'Dos', 'Base',  2017, 120000,  9800, 'USD',  9800, 'active', false, now(), '{}'),
  (9806, 'mercadolibre', 'MK-9806', 'https://example.test/mk-9806', 'Dos', 'Pgkm', 'Dos', 'Full',  2017, 100000, 12000, 'USD', 12000, 'active', false, now(), '{}'),
  -- far in km, or without km: only in the whole model
  (9807, 'mercadolibre', 'MK-9807', 'https://example.test/mk-9807', 'Dos', 'Pgkm', 'Dos', 'Base',  2017,  30000, 14000, 'USD', 14000, 'active', false, now(), '{}'),
  (9808, 'mercadolibre', 'MK-9808', 'https://example.test/mk-9808', 'Dos', 'Pgkm', 'Dos', 'Full',  2018,  20000, 16000, 'USD', 16000, 'active', false, now(), '{}'),
  (9809, 'mercadolibre', 'MK-9809', 'https://example.test/mk-9809', 'Dos', 'Pgkm', 'Dos', 'Base',  2017, 120001, 15000, 'USD', 15000, 'active', false, now(), '{}'),
  (9810, 'mercadolibre', 'MK-9810', 'https://example.test/mk-9810', 'Dos', 'Pgkm', 'Dos', 'Base',  2017,   null, 18000, 'USD', 18000, 'active', false, now(), '{}');

-- ---------------------------------------------------------------- dealer_market_ref
select is(public.dealer_market_ref('Pgkm', 'Dos', 2017, 8460, null, 100000, 'Base') - 'blue',
          '{"n": 5, "median": 9400, "p25": 9200, "p75": 9600, "vs_market_pct": -10.0, "enough": true, "year_tol": 1, "days": 30,
            "basis": "version_km", "km": 100000, "km_tol": 20000,
            "wide": {"n": 10, "median": 10900, "vs_market_pct": -22.4}}'::jsonb,
          'same trim and km within 20 %: the five of the trim near 100.000 km (the edge counts, one km more does not)');
select is(public.dealer_market_ref('Pgkm', 'Dos', 2017, 8460, null, 100000, 'Full') - array['blue', 'wide', 'p25', 'p75', 'year_tol', 'days'],
          '{"n": 6, "median": 9500, "vs_market_pct": -10.9, "enough": true, "basis": "km", "km": 100000, "km_tol": 20000}'::jsonb,
          'too few of the trim near: every trim with similar km');
select is(public.dealer_market_ref('Pgkm', 'Dos', 2017, 8460, null, 100000, null) ->> 'basis', 'km', 'no trim: similar km');
select is(public.dealer_market_ref('Pgkm', 'Dos', 2017, 8460, null, 100000, '  ') ->> 'basis', 'km', 'a blank trim is no trim');
select is(public.dealer_market_ref('Pgkm', 'Dos', 2017, 10900, null, null, 'Base') - array['blue', 'p25', 'p75', 'year_tol', 'days'],
          '{"n": 10, "median": 10900, "vs_market_pct": 0.0, "enough": true, "basis": "model", "km": null, "km_tol": null,
            "wide": {"n": 10, "median": 10900, "vs_market_pct": 0.0}}'::jsonb,
          'a car without km: the whole model, as before');
select is(public.dealer_market_ref('Pgkm', 'Dos', 2017, 10900, null, 0, 'Base') ->> 'basis', 'model', '0 km loaded is no km');
select is(public.dealer_market_ref('Pgkm', 'Dos', 2017, 10900, null, 300000, 'Base') - array['blue', 'wide', 'p25', 'p75', 'year_tol', 'days', 'vs_market_pct', 'median'],
          '{"n": 10, "enough": true, "basis": "model", "km": 300000, "km_tol": 60000}'::jsonb,
          'km loaded but nobody near: the whole model (the panel says there are few with similar km)');
select is(public.dealer_market_ref('Pgkm', 'Dos', 2017, 8460, 9801, 100000, 'Base') - array['blue', 'wide', 'p25', 'p75', 'year_tol', 'days', 'median', 'vs_market_pct'],
          '{"n": 5, "enough": true, "basis": "km", "km": 100000, "km_tol": 20000}'::jsonb,
          'the excluded listing leaves four of the trim: similar km of any trim');
select is(public.dealer_market_ref('Pgkm', 'Dos', 2017, 8460, null, 10000, null) -> 'km_tol', '15000'::jsonb,
          'a car with few km: 15.000 km either way');
select is(public.dealer_market_ref('Pgkm', 'Nada', 2017, 8460, null, 100000, 'Base') - 'blue',
          '{"n": 0, "median": null, "p25": null, "p75": null, "vs_market_pct": null, "enough": false, "year_tol": 1, "days": 30,
            "basis": "model", "km": 100000, "km_tol": 20000, "wide": {"n": 0, "median": null, "vs_market_pct": null}}'::jsonb,
          'a model nobody publishes: zeros and nulls');
select is(has_function_privilege('authenticated', 'public.dealer_market_ref(text,text,integer,numeric,bigint,integer,text)', 'execute'), false,
          'dealer_market_ref: service role only');

-- ---------------------------------------------------------------- through the panel
set local role authenticated;
set local request.jwt.claims = '{"sub": "d8000000-0000-0000-0000-00000000000a", "role": "authenticated"}';
select lives_ok($$select public.create_dealer('Mkm A', 'Quilmes', -34.72, -58.25)$$, 'dealer A');
select lives_ok($$select public.dealer_upsert_item(null, '{"make": "Pgkm", "model": "Dos", "trim": "Base", "year": 2017,
                                                         "mileage_km": 100000, "price": 8460, "currency": "USD"}')$$, 'a car with km and trim');
select lives_ok($$select public.dealer_upsert_item(null, '{"make": "Pgkm", "model": "Dos", "trim": "Full", "year": 2017,
                                                         "mileage_km": 100000, "price": 8460, "currency": "USD"}')$$, 'the same in a trim with few listings');
select lives_ok($$select public.dealer_upsert_item(null, '{"make": "Pgkm", "model": "Dos", "year": 2017,
                                                         "price": 8460, "currency": "USD"}')$$, 'and one without km');
reset role;
select set_config('mk.base', (select id::text from public.dealer_stock_items where model = 'Dos' and "trim" = 'Base'), true);
select set_config('mk.full', (select id::text from public.dealer_stock_items where model = 'Dos' and "trim" = 'Full'), true);
select set_config('mk.bare', (select id::text from public.dealer_stock_items where model = 'Dos' and mileage_km is null), true);

set local role authenticated;
set local request.jwt.claims = '{"sub": "d8000000-0000-0000-0000-00000000000a", "role": "authenticated"}';
select is((select array_agg(array[market ->> 'basis', market ->> 'n', market ->> 'vs_market_pct'] order by item_id) from public.dealer_stock_insights()),
          array[array['version_km', '5', '-10.0'], array['km', '6', '-10.9'], array['model', '10', '-22.4']],
          'dealer_stock_insights: each car against its own reference');
select is((select array_agg(listing_id order by listing_id) from public.dealer_market_listings(current_setting('mk.base')::bigint) where in_ref),
          array[9801, 9802, 9803, 9804, 9805]::bigint[], 'dealer_market_listings: in_ref marks the reference (same trim, similar km)');
select is((select count(*)::int from public.dealer_market_listings(current_setting('mk.base')::bigint)), 10, '... and still lists the whole model');
select is((select array_agg(listing_id order by listing_id) from public.dealer_market_listings(current_setting('mk.full')::bigint) where in_ref),
          array[9801, 9802, 9803, 9804, 9805, 9806]::bigint[], '... similar km of any trim for the trim with few listings');
select is((select count(*)::int from public.dealer_market_listings(current_setting('mk.bare')::bigint) where in_ref), 10,
          '... a car without km: every listing is the reference');
select is((select count(*) filter (where in_ref)::int from public.dealer_market_listings(current_setting('mk.base')::bigint)),
          ((select market from public.dealer_stock_insights() where item_id = current_setting('mk.base')::bigint) ->> 'n')::int,
          '... as many in_ref as the n of the reference');
reset role;

select is((select array_agg(s.market ->> 'basis' order by s.item_id)
             from public.dealer_alert_scan((select id from public.dealers where name = 'Mkm A')) s),
          array['version_km', 'km', 'model'], 'dealer_alert_scan: the same references');

select * from finish();
rollback;

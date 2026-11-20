-- Agencias: dealer_price_context() (migration 20270101120000_dealer_price_context.sql): the narrower
-- cuts of the market pool behind «por qué» a price is off. One transaction, rolled back.
begin;
create extension if not exists pgtap with schema extensions;
select no_plan();

insert into auth.users (instance_id, id, aud, role, email, created_at, updated_at) values
  ('00000000-0000-0000-0000-000000000000', 'd7000000-0000-0000-0000-00000000000a', 'authenticated', 'authenticated', 'a@pctx.test', now(), now()),
  ('00000000-0000-0000-0000-000000000000', 'd7000000-0000-0000-0000-00000000000b', 'authenticated', 'authenticated', 'b@pctx.test', now(), now()),
  ('00000000-0000-0000-0000-000000000000', 'd7000000-0000-0000-0000-000000000001', 'authenticated', 'authenticated', 'u@pctx.test', now(), now());
update public.app_config set value = value || '{"enabled": true}' where key = 'dealer_program';

set local role authenticated;
set local request.jwt.claims = '{"sub": "d7000000-0000-0000-0000-00000000000a", "role": "authenticated"}';
select lives_ok($$select public.create_dealer('Pctx A', 'Quilmes', -34.72, -58.25)$$, 'dealer A');
select lives_ok($$select public.dealer_upsert_item(null, '{"make": "Pgctx", "model": "Uno", "trim": " Base 1.6 ", "year": 2017,
                                                         "mileage_km": 100000, "price": 9000, "currency": "USD"}')$$, 'A: a car with km and trim');
select lives_ok($$select public.dealer_upsert_item(null, '{"make": "Pgctx", "model": "Uno", "year": 2017,
                                                         "price": 9000, "currency": "USD"}')$$, 'A: the same car without km or trim');
select lives_ok($$select public.dealer_upsert_item(null, '{"make": "Pgctx", "model": "Nadie", "year": 2017,
                                                         "price": 9000, "currency": "USD"}')$$, 'A: a model nobody publishes');
reset role;
set local role authenticated;
set local request.jwt.claims = '{"sub": "d7000000-0000-0000-0000-00000000000b", "role": "authenticated"}';
select lives_ok($$select public.create_dealer('Pctx B', 'Quilmes', -34.72, -58.25)$$, 'dealer B');
select lives_ok($$select public.dealer_upsert_item(null, '{"make": "Pgctx", "model": "Uno", "year": 2017, "mileage_km": 20000,
                                                         "price": 9000, "currency": "USD"}')$$, 'B: its own car');
reset role;
select set_config('pc.full', (select id::text from public.dealer_stock_items where model = 'Uno' and mileage_km = 100000), true);
select set_config('pc.bare', (select id::text from public.dealer_stock_items where model = 'Uno' and mileage_km is null), true);
select set_config('pc.none', (select id::text from public.dealer_stock_items where model = 'Nadie'), true);
select set_config('pc.b', (select id::text from public.dealer_stock_items where mileage_km = 20000), true);

-- The pool of Pgctx Uno 2017 (year ±1): seven count, the rest are out like in dealer_market_ref.
insert into public.listings (id, source, external_id, url, title, make, model, "trim", year, mileage_km, price, currency, price_usd,
                             status, price_partial, last_seen_at, attributes, seller_type)
overriding system value values
  (9701, 'mercadolibre', 'PC-9701', 'https://example.test/pc-9701', 'Uno', 'Pgctx', 'Uno', 'BASE 1.6',  2017,  95000,  9500, 'USD',  9500, 'active', false, now(), '{}', 'dealer'),
  (9702, 'mercadolibre', 'PC-9702', 'https://example.test/pc-9702', 'Uno', 'Pgctx', 'Uno', 'base 1.6',  2017, 115000,  9000, 'USD',  9000, 'active', false, now(), '{}', 'private'),
  (9703, 'kavak',        'PC-9703', 'https://example.test/pc-9703', 'Uno', 'Pgctx', 'Uno', 'Full 2.0',  2017,  40000, 13000, 'USD', 13000, 'active', false, now(), '{}', 'dealer'),
  (9704, 'kavak',        'PC-9704', 'https://example.test/pc-9704', 'Uno', 'Pgctx', 'Uno', 'Full 2.0',  2018,  30000, 14000, 'USD', 14000, 'active', false, now(), '{}', 'dealer'),
  (9705, 'mercadolibre', 'PC-9705', 'https://example.test/pc-9705', 'Uno', 'Pgctx', 'Uno', 'Base 1.6',  2016, 120000,  8000, 'USD',  8000, 'active', false, now(), '{}', 'private'),
  (9706, 'mercadolibre', 'PC-9706', 'https://example.test/pc-9706', 'Uno', 'Pgctx', 'Uno', null,        2018,   null, 12000, 'USD', 12000, 'active', false, now(), '{}', null),
  (9707, 'mercadolibre', 'PC-9707', 'https://example.test/pc-9707', 'Uno', 'Pgctx', 'Uno', 'Full 2.0',  2016,  80000, 11000, 'USD', 11000, 'active', false, now(), '{}', 'private'),
  -- out: two years away, seen 31 days ago, gone, partial price, directo, not a vehicle
  (9711, 'mercadolibre', 'PC-9711', 'https://example.test/pc-9711', 'Uno', 'Pgctx', 'Uno', 'Base 1.6',  2019, 100000,  1000, 'USD',  1000, 'active', false, now(), '{}', 'dealer'),
  (9712, 'mercadolibre', 'PC-9712', 'https://example.test/pc-9712', 'Uno', 'Pgctx', 'Uno', 'Base 1.6',  2017, 100000,  1000, 'USD',  1000, 'active', false, now() - interval '31 days', '{}', 'dealer'),
  (9713, 'mercadolibre', 'PC-9713', 'https://example.test/pc-9713', 'Uno', 'Pgctx', 'Uno', 'Base 1.6',  2017, 100000,  1000, 'USD',  1000, 'gone',   false, now(), '{}', 'dealer'),
  (9714, 'mercadolibre', 'PC-9714', 'https://example.test/pc-9714', 'Uno', 'Pgctx', 'Uno', 'Base 1.6',  2017, 100000,  1000, 'USD',  1000, 'active', true,  now(), '{}', 'dealer'),
  (9715, 'directo',      'PC-9715', 'https://example.test/pc-9715', 'Uno', 'Pgctx', 'Uno', 'Base 1.6',  2017, 100000,  1000, 'USD',  1000, 'active', false, now(), '{}', 'dealer'),
  (9716, 'mercadolibre', 'PC-9716', 'https://example.test/pc-9716', 'Uno', 'Pgctx', 'Uno', 'Base 1.6',  2017, 100000,  1000, 'USD',  1000, 'active', false, now(), '{"_not_vehicle": true}', 'dealer');

set local role authenticated;
set local request.jwt.claims = '{"sub": "d7000000-0000-0000-0000-00000000000a", "role": "authenticated"}';
select is((select array_agg(item_id order by item_id) from public.dealer_price_context()),
          array[current_setting('pc.full')::bigint, current_setting('pc.bare')::bigint, current_setting('pc.none')::bigint],
          'dealer_price_context: my cars on sale, not another dealer''s');
select is((select context from public.dealer_price_context() where item_id = current_setting('pc.full')::bigint),
          '{"km": 100000, "km_n": 6, "km_median": 87500,
            "same_year":  {"n": 3, "median": 9500},
            "similar_km": {"n": 4, "median": 9250},
            "closest":    {"n": 2, "median": 9250},
            "same_trim":  {"n": 3, "median": 9000},
            "dealers":    {"n": 3, "median": 13000}}'::jsonb,
          '... same year, km within 20 %, both, same trim (case and spaces apart) and dealers, over the pool of dealer_market_ref');
select is((select (context -> 'same_year' ->> 'n')::int + 4 from public.dealer_price_context() where item_id = current_setting('pc.full')::bigint),
          ((select market from public.dealer_stock_insights() where item_id = current_setting('pc.full')::bigint) ->> 'n')::int,
          '... the same pool as the market reference (7 listings)');
select is((select context from public.dealer_price_context() where item_id = current_setting('pc.bare')::bigint),
          '{"km": null, "km_n": 6, "km_median": 87500,
            "same_year":  {"n": 3, "median": 9500},
            "similar_km": {"n": 0, "median": null},
            "closest":    {"n": 0, "median": null},
            "same_trim":  {"n": 0, "median": null},
            "dealers":    {"n": 3, "median": 13000}}'::jsonb,
          '... a car without km or trim: no cut by km or trim');
select is((select context from public.dealer_price_context() where item_id = current_setting('pc.none')::bigint),
          '{"km": null, "km_n": 0, "km_median": null,
            "same_year":  {"n": 0, "median": null},
            "similar_km": {"n": 0, "median": null},
            "closest":    {"n": 0, "median": null},
            "same_trim":  {"n": 0, "median": null},
            "dealers":    {"n": 0, "median": null}}'::jsonb,
          '... a model with no listings: zeros and nulls');
select lives_ok(format($$select public.dealer_set_item_status(%s, 'sold')$$, current_setting('pc.bare')), 'A sells one');
select is((select count(*)::int from public.dealer_price_context()), 2, '... a sold car has no context');
reset role;

set local role authenticated;
set local request.jwt.claims = '{"sub": "d7000000-0000-0000-0000-000000000001", "role": "authenticated"}';
select throws_ok($$select * from public.dealer_price_context()$$, 'P0001', 'not_member', 'someone without a dealer: not_member');
reset role;
select is(has_function_privilege('anon', 'public.dealer_price_context()', 'execute'), false, 'not for anon');

update public.app_config set value = value || '{"enabled": false}' where key = 'dealer_program';
set local role authenticated;
set local request.jwt.claims = '{"sub": "d7000000-0000-0000-0000-00000000000a", "role": "authenticated"}';
select throws_ok($$select * from public.dealer_price_context()$$, 'P0001', 'dealer_program_off', 'with the program off: dealer_program_off');
reset role;

select * from finish();
rollback;

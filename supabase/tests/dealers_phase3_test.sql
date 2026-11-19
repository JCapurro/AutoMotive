-- Agencias, fase 3 (migration 20261231120000_dealer_phase3.sql): «Qué comprar», sellers who accept
-- agencies' contact and the dealers' requests. Needs 20261228120000_dealer_program.sql applied first.
-- Run on a cloned database (docs/superpowers/specs/2026-11-18-agencias-design.md §7.1). One transaction, rolled back.
begin;
create extension if not exists pgtap with schema extensions;
select no_plan();

-- ---------------------------------------------------------------- users
-- A owns «TT Autos» (Quilmes), B owns «Otra Agencia»; U1-U3 are buyers; X is an admin;
-- S1-S7 answered «¿Tenés que vender tu auto?».
insert into auth.users (instance_id, id, aud, role, email, created_at, updated_at)
select '00000000-0000-0000-0000-000000000000', u.id::uuid, 'authenticated', 'authenticated', u.email, now(), now()
  from (values ('d3000000-0000-0000-0000-00000000000a', 'a@phase3.test'),
               ('d3000000-0000-0000-0000-00000000000b', 'b@phase3.test'),
               ('d3000000-0000-0000-0000-000000000001', 'u1@phase3.test'),
               ('d3000000-0000-0000-0000-000000000002', 'u2@phase3.test'),
               ('d3000000-0000-0000-0000-000000000003', 'u3@phase3.test'),
               ('d3000000-0000-0000-0000-00000000000f', 'x@phase3.test'),
               ('d3000000-0000-0000-0000-000000000011', 's1@phase3.test'),
               ('d3000000-0000-0000-0000-000000000012', 's2@phase3.test'),
               ('d3000000-0000-0000-0000-000000000013', 's3@phase3.test'),
               ('d3000000-0000-0000-0000-000000000014', 's4@phase3.test'),
               ('d3000000-0000-0000-0000-000000000015', 's5@phase3.test'),
               ('d3000000-0000-0000-0000-000000000017', 's7@phase3.test')) as u(id, email);
update public.profiles set role = 'admin'
 where id in ('d3000000-0000-0000-0000-00000000000f', 'd3000000-0000-0000-0000-000000000015');

-- ================================================================ 1. switch
update public.app_config set value = '{"enabled": false, "channel_enabled": false, "manual_confirm_days": 7, "demand_min_count": 3}'
 where key = 'dealer_program';
select is(public.dealer_sellers_config(),
          '{"sellers": false, "sellers_enabled": false, "seller_requests_per_day": 5, "seller_requests_per_seller_week": 3, "request_days": 14}'::jsonb,
          'dealer_sellers_config(): off by default, 5 requests a day, 3 per seller a week, 14 days to answer');
update public.app_config set value = '{"enabled": false, "sellers_enabled": true}' where key = 'dealer_program';
select is(public.dealer_sellers_config()->'sellers', 'false'::jsonb, 'sellers_enabled without enabled: off');
update public.app_config set value = '{"enabled": true, "sellers_enabled": "true", "seller_requests_per_day": 0}' where key = 'dealer_program';
select is(array[public.dealer_sellers_config()->>'sellers', public.dealer_sellers_config()->>'seller_requests_per_day'],
          array['false', '5'], 'a string switch -> off; 0 a day -> 5');
update public.app_config set value = '{"enabled": true, "sellers_enabled": true, "seller_requests_per_day": 51}' where key = 'dealer_program';
select is(array[public.dealer_sellers_config()->>'sellers', public.dealer_sellers_config()->>'seller_requests_per_day'],
          array['true', '5'], 'both on -> on; 51 a day -> 5');
update public.app_config set value = '{"enabled": true, "sellers_enabled": true, "seller_requests_per_day": 12}' where key = 'dealer_program';
select is(public.dealer_sellers_config()->'seller_requests_per_day', '12'::jsonb, '12 a day stays');
update public.app_config set value = '{"enabled": true, "sellers_enabled": true, "seller_requests_per_day": "7"}' where key = 'dealer_program';
select is(public.dealer_sellers_config()->'seller_requests_per_day', '5'::jsonb, 'a string number -> 5');
select is(public.dealer_program(),
          '{"enabled": true, "channel_enabled": false, "manual_confirm_days": 7, "demand_min_count": 3}'::jsonb,
          'dealer_program() ignores the new keys (its twins do not change)');

select is(has_function_privilege('authenticated', 'public.dealer_eligible_sellers(bigint)', 'execute')
          or has_function_privilege('authenticated', 'public.dealer_require_approved()', 'execute'),
          false, 'the internal helpers are not for clients');
select is(has_function_privilege('anon', 'public.dealer_buy_opportunities()', 'execute')
          or has_function_privilege('anon', 'public.dealer_sellers()', 'execute')
          or has_function_privilege('anon', 'public.dealer_request_seller(text,text)', 'execute')
          or has_function_privilege('anon', 'public.answer_dealer_seller_request(bigint,boolean,text,text,boolean,text)', 'execute'),
          false, 'no RPC for anon');
select is(has_table_privilege('authenticated', 'public.dealer_seller_requests', 'select')
          or has_table_privilege('authenticated', 'public.dealer_seller_requests', 'insert')
          or has_table_privilege('authenticated', 'public.sell_intent_vehicles', 'insert')
          or has_table_privilege('authenticated', 'public.sell_intent_vehicles', 'update'),
          false, 'clients never read requests nor write the seller''s car directly');

-- ================================================================ 2. dealers
update public.app_config set value = '{"enabled": true, "channel_enabled": false, "manual_confirm_days": 7, "demand_min_count": 3}'
 where key = 'dealer_program';
set local role authenticated;
set local request.jwt.claims = '{"sub": "d3000000-0000-0000-0000-00000000000a", "role": "authenticated"}';
select lives_ok($$select public.create_dealer('TT Autos', 'Quilmes', -34.72, -58.25)$$, 'A creates TT Autos');
set local request.jwt.claims = '{"sub": "d3000000-0000-0000-0000-00000000000b", "role": "authenticated"}';
select lives_ok($$select public.create_dealer('Otra Agencia', 'Berazategui', -34.76, -58.21)$$, 'B creates Otra Agencia');
reset role;
do $d$ begin
  perform set_config('t.dealer_a', (select id::text from public.dealers where name = 'TT Autos'), true);
  perform set_config('t.dealer_b', (select id::text from public.dealers where name = 'Otra Agencia'), true);
end $d$;
update public.dealers set approved_at = now() where id = current_setting('t.dealer_a')::bigint;
-- Two more dealers, only for the per-seller cap.
insert into public.dealers (name, locality_label, lat, lon, approved_at) values
  ('Pgtres', 'Quilmes', -34.72, -58.25, now()), ('Pgcuatro', 'Quilmes', -34.72, -58.25, now());

insert into public.fx_rates (date, kind, rate, source) values (current_date + 2, 'blue', 1000, 'test')
on conflict (date, kind) do update set rate = excluded.rate;

-- ================================================================ 3. «Qué comprar»
set local session_replication_role = replica;
insert into public.search_profiles (user_id, name, filters, enabled, origin_lat, origin_lon, radius_km, created_at)
select s.u::uuid, 'q', s.f::jsonb, s.en, s.lat, s.lon, s.r, now() - make_interval(days => s.age)
  from (values
  -- Etios: 3 people, 4 searches, all active and in zone (U3 through an extra location).
  ('d3000000-0000-0000-0000-000000000001', '{"make": "Pgbuy", "model": "Etios", "year_min": 2018, "year_max": 2020, "price_max": 14000000, "currency": "ARS"}', true, -34.72, -58.25, 30, 0),
  ('d3000000-0000-0000-0000-000000000001', '{"make": "Pgbuy", "model": "etios", "year_min": 2017, "year_max": 2019, "price_max": 20000000}', true, -34.72, -58.25, 30, 0),
  ('d3000000-0000-0000-0000-000000000002', '{"make": "Pgbuy", "model": "Etios", "year_min": 2018, "year_max": 2021, "price_max": 15000000, "currency": "ARS"}', true, -34.72, -58.25, 30, 0),
  ('d3000000-0000-0000-0000-000000000003', '{"make": "Pgbuy", "model": "Etios", "years": [2019, 2020], "price_max": 10000, "currency": "USD",
                                            "extra_locations": [{"lat": -34.70, "lon": -58.30, "radius_km": 20}]}', true, -31.42, -64.18, 10, 0),
  -- Pgfew: 2 people, 3 searches -> never listed.
  ('d3000000-0000-0000-0000-000000000001', '{"make": "Pgbuy", "model": "Pgfew"}', true, -34.72, -58.25, 30, 0),
  ('d3000000-0000-0000-0000-000000000001', '{"make": "Pgbuy", "model": "Pgfew", "year_min": 2010}', true, -34.72, -58.25, 30, 0),
  ('d3000000-0000-0000-0000-000000000002', '{"make": "Pgbuy", "model": "Pgfew"}', true, -34.72, -58.25, 30, 0),
  -- Pgexcl: 2 people plus the admin and A (the dealer's own member) -> never listed.
  ('d3000000-0000-0000-0000-000000000001', '{"make": "Pgbuy", "model": "Pgexcl"}', true, null, null, null, 0),
  ('d3000000-0000-0000-0000-000000000002', '{"make": "Pgbuy", "model": "Pgexcl"}', true, null, null, null, 0),
  ('d3000000-0000-0000-0000-00000000000f', '{"make": "Pgbuy", "model": "Pgexcl"}', true, null, null, null, 0),
  ('d3000000-0000-0000-0000-00000000000a', '{"make": "Pgbuy", "model": "Pgexcl"}', true, null, null, null, 0),
  -- Pgfar: 3 people, all of them in Córdoba with 20 km -> out of the zone.
  ('d3000000-0000-0000-0000-000000000001', '{"make": "Pgbuy", "model": "Pgfar"}', true, -31.42, -64.18, 20, 0),
  ('d3000000-0000-0000-0000-000000000002', '{"make": "Pgbuy", "model": "Pgfar"}', true, -31.42, -64.18, 20, 0),
  ('d3000000-0000-0000-0000-000000000003', '{"make": "Pgbuy", "model": "Pgfar"}', true, -31.42, -64.18, 20, 0),
  -- Pgnozone: 3 people without a zone (they count), one of them paused but recent.
  ('d3000000-0000-0000-0000-000000000001', '{"make": "Pgbuy", "model": "Pgnozone"}', true, null, null, null, 0),
  ('d3000000-0000-0000-0000-000000000002', '{"make": "Pgbuy", "model": "Pgnozone"}', true, null, null, null, 0),
  ('d3000000-0000-0000-0000-000000000003', '{"make": "Pgbuy", "model": "Pgnozone"}', false, null, null, null, 10),
  -- Pgstock: 3 people, A has it available -> out. Pgsold: 3 people, A sold it -> in; one year given.
  ('d3000000-0000-0000-0000-000000000001', '{"make": "Pgbuy", "model": "Pgstock"}', true, null, null, null, 0),
  ('d3000000-0000-0000-0000-000000000002', '{"make": "Pgbuy", "model": "Pgstock"}', true, null, null, null, 0),
  ('d3000000-0000-0000-0000-000000000003', '{"make": "Pgbuy", "model": "Pgstock"}', true, null, null, null, 0),
  ('d3000000-0000-0000-0000-000000000001', '{"make": "Pgbuy", "model": "Pgsold", "year_min": 2015}', true, null, null, null, 0),
  ('d3000000-0000-0000-0000-000000000002', '{"make": "Pgbuy", "model": "Pgsold"}', true, null, null, null, 0),
  ('d3000000-0000-0000-0000-000000000003', '{"make": "Pgbuy", "model": "Pgsold"}', true, null, null, null, 0),
  -- Pgold: the third person's search is paused and 100 days old -> 2 people.
  ('d3000000-0000-0000-0000-000000000001', '{"make": "Pgbuy", "model": "Pgold"}', true, null, null, null, 0),
  ('d3000000-0000-0000-0000-000000000002', '{"make": "Pgbuy", "model": "Pgold"}', true, null, null, null, 0),
  ('d3000000-0000-0000-0000-000000000003', '{"make": "Pgbuy", "model": "Pgold"}', false, null, null, null, 100),
  -- Pgpriv: the third person only buys from private sellers -> 2 people.
  ('d3000000-0000-0000-0000-000000000001', '{"make": "Pgbuy", "model": "Pgpriv"}', true, null, null, null, 0),
  ('d3000000-0000-0000-0000-000000000002', '{"make": "Pgbuy", "model": "Pgpriv"}', true, null, null, null, 0),
  ('d3000000-0000-0000-0000-000000000003', '{"make": "Pgbuy", "model": "Pgpriv", "seller_types": ["private"]}', true, null, null, null, 0)
  ) as s(u, f, en, lat, lon, r, age);
set local session_replication_role = origin;

insert into public.dealer_stock_items (dealer_id, origin, make, model, year, price, currency, status, confirmed_at)
values (current_setting('t.dealer_a')::bigint, 'manual', 'Pgbuy', 'Pgstock', 2018, 10000, 'USD', 'available', now()),
       (current_setting('t.dealer_a')::bigint, 'manual', 'Pgbuy', 'Pgsold', 2018, 10000, 'USD', 'sold', now());

-- Etios supply (years 2018-2020): 9931 near (Quilmes), 9932 far (Córdoba); the others never count.
insert into public.listings (id, source, external_id, url, title, make, model, year, price, currency, price_usd,
                             lat, lon, status, last_seen_at, attributes)
overriding system value values
  (9931, 'mercadolibre', 'P3-9931', 'https://example.test/p3-9931', 'Pgbuy Etios', 'Pgbuy', 'Etios', 2019, 9000, 'USD', 9000, -34.71, -58.28, 'active', now(), '{}'),
  (9932, 'kavak',        'P3-9932', 'https://example.test/p3-9932', 'Pgbuy Etios', 'Pgbuy', 'Etios', 2020, 9500, 'USD', 9500, -31.42, -64.18, 'active', now(), '{}'),
  (9933, 'mercadolibre', 'P3-9933', 'https://example.test/p3-9933', 'Pgbuy Etios', 'Pgbuy', 'Etios', 2015, 7000, 'USD', 7000, -34.71, -58.28, 'active', now(), '{}'),
  (9934, 'directo',      'P3-9934', 'https://example.test/p3-9934', 'Pgbuy Etios', 'Pgbuy', 'Etios', 2019, 9000, 'USD', 9000, -34.71, -58.28, 'active', now(), '{}'),
  (9935, 'mercadolibre', 'P3-9935', 'https://example.test/p3-9935', 'Pgbuy Etios', 'Pgbuy', 'Etios', 2019, 9000, 'USD', 9000, -34.71, -58.28, 'gone', now(), '{}'),
  (9936, 'mercadolibre', 'P3-9936', 'https://example.test/p3-9936', 'Pgbuy Etios', 'Pgbuy', 'Etios', 2019, 9000, 'USD', 9000, -34.71, -58.28, 'active', now() - interval '40 days', '{}'),
  (9937, 'mercadolibre', 'P3-9937', 'https://example.test/p3-9937', 'Pgbuy Etios', 'Pgbuy', 'Etios', 2019, 9000, 'USD', 9000, -34.71, -58.28, 'active', now(), '{"_not_vehicle": true}');

set local role authenticated;
set local request.jwt.claims = '{"sub": "d3000000-0000-0000-0000-000000000001", "role": "authenticated"}';
select throws_ok($$select * from public.dealer_buy_opportunities()$$, 'P0001', 'not_member', 'a buyer: not_member');
set local request.jwt.claims = '{"sub": "d3000000-0000-0000-0000-00000000000b", "role": "authenticated"}';
select throws_ok($$select * from public.dealer_buy_opportunities()$$, 'P0001', 'not_approved', 'a dealer not approved: not_approved');
set local request.jwt.claims = '{"sub": "d3000000-0000-0000-0000-00000000000a", "role": "authenticated"}';
select is((select array_agg(model order by model) from public.dealer_buy_opportunities()),
          array['Etios', 'Pgnozone', 'Pgsold'],
          'Qué comprar: 3+ people in the zone; under 3, admins, members, out of zone, old, private-only and in stock out');
select is((select model from public.dealer_buy_opportunities() limit 1), 'Etios', '... by demand, most searched first');
select is((select row(make, searches, active_searches, year_from, year_to, budget, budget_currency, supply_total, supply_near)::text
             from public.dealer_buy_opportunities() where model = 'Etios'),
          row('Pgbuy', 4, '4'::jsonb, 2018, 2020, 14500000::numeric, 'ARS', 2, 1)::text,
          'Etios: 4 searches, all active; years 2018-2020 (medians); budget the median, in pesos, rounded; supply 2, 1 near');
select is((select row(searches, active_searches, year_from, year_to, budget, budget_currency)::text
             from public.dealer_buy_opportunities() where model = 'Pgnozone'),
          row(3, '"few"'::jsonb, null::integer, null::integer, null::numeric, null::text)::text,
          'Pgnozone: 2 active people -> «few»; no years nor budget given -> null');
select is((select year_from from public.dealer_buy_opportunities() where model = 'Pgsold'), null,
          'Pgsold: a year given by only one person is not shown');
select is((select array_agg(listing_id::text || ':' || near::text order by listing_id)
             from public.dealer_buy_market_listings('Pgbuy', 'Etios', 2018, 2020)),
          array['9931:true', '9932:false'], 'dealer_buy_market_listings: the very listings behind the supply count');
select throws_ok($$select * from public.dealer_buy_market_listings('Pgbuy', ' ', 2018, 2020)$$, 'P0001', 'invalid_model',
                 'dealer_buy_market_listings without a model: invalid_model');
reset role;

update public.app_config set value = '{"enabled": true, "channel_enabled": false, "manual_confirm_days": 7, "demand_min_count": 4}'
 where key = 'dealer_program';
set local role authenticated;
set local request.jwt.claims = '{"sub": "d3000000-0000-0000-0000-00000000000a", "role": "authenticated"}';
select is((select count(*)::integer from public.dealer_buy_opportunities()), 0, 'with demand_min_count 4, 3 people are not enough');
reset role;
update public.app_config set value = '{"enabled": true, "channel_enabled": false, "manual_confirm_days": 7, "demand_min_count": 3}'
 where key = 'dealer_program';

set local role authenticated;
set local request.jwt.claims = '{"sub": "d3000000-0000-0000-0000-00000000000b", "role": "authenticated"}';
select is((select count(*)::integer from public.dealer_buy_market_listings('Pgbuy', 'Etios', null, null)), 3,
          'the market list needs no approval (public listings); without years the 2015 one counts too');
reset role;

-- ================================================================ 4. sellers: who a dealer sees
update public.app_config set value = jsonb_set(value, '{agencies_contact}', 'true') where key = 'sell_intent';
insert into public.sell_intent (user_id, answer, source, wants_notice, agencies_contact_ok) values
  ('d3000000-0000-0000-0000-000000000011', 'yes', 'email', true, true),   -- near, describes the car
  ('d3000000-0000-0000-0000-000000000012', 'yes', 'ficha', false, true),  -- no car, no location
  ('d3000000-0000-0000-0000-000000000013', 'yes', 'email', true, false),  -- did not tick the agencies box
  ('d3000000-0000-0000-0000-000000000014', 'no', 'email', false, false),  -- not selling
  ('d3000000-0000-0000-0000-000000000015', 'yes', 'email', false, true),  -- an admin
  ('d3000000-0000-0000-0000-000000000017', 'yes', 'email', false, true),  -- 600 km away
  ('d3000000-0000-0000-0000-00000000000a', 'yes', 'email', false, true);  -- A itself
set local session_replication_role = replica;
insert into public.search_profiles (user_id, name, filters, enabled, origin_lat, origin_lon, radius_km) values
  ('d3000000-0000-0000-0000-000000000011', 's', '{"model": "Pgsellerloc"}', true, -34.73, -58.26, 20),
  ('d3000000-0000-0000-0000-000000000017', 's', '{"model": "Pgsellerloc"}', true, -31.42, -64.18, 20);
set local session_replication_role = origin;

set local role authenticated;
set local request.jwt.claims = '{"sub": "d3000000-0000-0000-0000-000000000014", "role": "authenticated"}';
select throws_ok($$select public.save_my_sell_vehicle('Fiat', 'Palio', 2012, 87400)$$, 'P0001', 'sell_intent_required',
                 'save_my_sell_vehicle after «No»: sell_intent_required');
set local request.jwt.claims = '{"sub": "d3000000-0000-0000-0000-000000000011", "role": "authenticated"}';
select throws_ok($$select public.save_my_sell_vehicle('Fiat', 'Palio', 1900, 87400)$$, 'P0001', 'invalid_vehicle:year',
                 'save_my_sell_vehicle with a wrong year: invalid_vehicle:year');
select lives_ok($$select public.save_my_sell_vehicle(' Fiat ', 'Palio', 2012, 87400)$$, 'S1 says what car they sell');
select is((select make || ' ' || model from public.sell_intent_vehicles), 'Fiat Palio', '... and reads only their own row');
select throws_ok($$insert into public.sell_intent_vehicles (user_id, make, model)
                   values ('d3000000-0000-0000-0000-000000000011', 'X', 'Y')$$, '42501', null,
                 'no direct write to sell_intent_vehicles');

set local request.jwt.claims = '{"sub": "d3000000-0000-0000-0000-00000000000a", "role": "authenticated"}';
select throws_ok($$select * from public.dealer_sellers()$$, 'P0001', 'sellers_off', 'dealer_sellers with the switch off: sellers_off');
select throws_ok($$select public.dealer_request_seller('x')$$, 'P0001', 'sellers_off', 'dealer_request_seller with the switch off: sellers_off');
reset role;
update public.app_config set value = value || '{"sellers_enabled": true}' where key = 'dealer_program';

set local role authenticated;
set local request.jwt.claims = '{"sub": "d3000000-0000-0000-0000-00000000000b", "role": "authenticated"}';
select throws_ok($$select * from public.dealer_sellers()$$, 'P0001', 'not_approved', 'a dealer not approved: not_approved');
set local request.jwt.claims = '{"sub": "d3000000-0000-0000-0000-000000000001", "role": "authenticated"}';
select throws_ok($$select * from public.dealer_sellers()$$, 'P0001', 'not_member', 'a buyer: not_member');

set local request.jwt.claims = '{"sub": "d3000000-0000-0000-0000-00000000000a", "role": "authenticated"}';
select is((select array_agg(x order by x) from (select coalesce(model, '-') || ':' || distance_band as x
                                                    from public.dealer_sellers()) s),
          array['-:unknown', 'Palio:lt10'],'dealer_sellers: «Sí» + agencies box only; not the one without the box, «No», an admin, 600 km away, nor its own member');
select is((select row(make, year, mileage_km_rounded, recent, request_id, can_request)::text
             from public.dealer_sellers() where model = 'Palio'),
          row('Fiat', 2012, 85000, true, null::bigint, true)::text,
          'the car as the seller gave it, km rounded to 5.000, «este mes», no request yet');
select is((select model from public.dealer_sellers() limit 1), 'Palio', '... nearest first');
select ok((select bool_and(ref ~ '^[0-9a-f]{32}$' and ref not like '%d3000000%') from public.dealer_sellers()),
          'refs are opaque, never a user id');
select set_config('t.ref_s1', (select ref from public.dealer_sellers() where model = 'Palio'), true);
select set_config('t.ref_s2', (select ref from public.dealer_sellers() where model is null), true);

-- ================================================================ 5. requests
select throws_ok($$select public.dealer_request_seller('00000000000000000000000000000000')$$, 'P0001', 'seller_not_found',
                 'an unknown ref: seller_not_found');
select throws_ok(format('select public.dealer_request_seller(%L, %L)', current_setting('t.ref_s1'), repeat('x', 301)),
                 'P0001', 'invalid_message', 'a message over 300: invalid_message');
select is((public.dealer_request_seller(current_setting('t.ref_s1'), 'Hola, compramos tu auto.') - 'request_id'),
          '{"created": true, "status": "pending"}'::jsonb, 'A asks to contact S1: pending, no contact handed over');
select is((public.dealer_request_seller(current_setting('t.ref_s1')) - 'request_id'),
          '{"created": false, "status": "pending"}'::jsonb, '... again: the same request');
select is((select row(request_status, shared_name, shared_phone, shared_email, can_request)::text
             from public.dealer_sellers() where model = 'Palio'),
          row('pending', null::text, null::text, null::text, false)::text,
          'the dealer sees «pending» and no contact');
select throws_ok($$select * from public.dealer_seller_requests$$, '42501', null, 'no direct read of dealer_seller_requests');
reset role;
select is((select array_agg(distinct k order by k) from public.events e, jsonb_object_keys(e.props) k
            where e.name = 'dealer_seller_requested'),
          array['dealer_id', 'request_id'], 'the event has no seller id nor message');
select is((select count(*)::integer from public.dealer_seller_requests where dealer_id = current_setting('t.dealer_a')::bigint), 1,
          'one row for A');

-- Per dealer and day.
update public.app_config set value = value || '{"seller_requests_per_day": 1}' where key = 'dealer_program';
set local role authenticated;
set local request.jwt.claims = '{"sub": "d3000000-0000-0000-0000-00000000000a", "role": "authenticated"}';
select throws_ok(format('select public.dealer_request_seller(%L)', current_setting('t.ref_s2')), 'P0001', 'rate_limited',
                 'over seller_requests_per_day: rate_limited');
reset role;
update public.app_config set value = value || '{"seller_requests_per_day": 5}' where key = 'dealer_program';

-- Per seller and week: S2 already got 3 requests (B and the two others).
update public.dealers set approved_at = now() where id = current_setting('t.dealer_b')::bigint;
insert into public.dealer_seller_requests (dealer_id, seller_user_id)
select d.id, 'd3000000-0000-0000-0000-000000000012' from public.dealers d
 where d.name in ('Otra Agencia', 'Pgtres', 'Pgcuatro');
set local role authenticated;
set local request.jwt.claims = '{"sub": "d3000000-0000-0000-0000-00000000000a", "role": "authenticated"}';
select is((select can_request from public.dealer_sellers() where model is null), false, 'a seller with 3 requests this week: can_request false');
select throws_ok(format('select public.dealer_request_seller(%L)', current_setting('t.ref_s2')), 'P0001', 'seller_busy',
                 '... and asking: seller_busy');

-- Between dealers.
set local request.jwt.claims = '{"sub": "d3000000-0000-0000-0000-00000000000b", "role": "authenticated"}';
select throws_ok(format('select public.dealer_request_seller(%L)', current_setting('t.ref_s1')), 'P0001', 'seller_not_found',
                 'B cannot use A''s ref (refs are per dealer)');
select is((select request_id from public.dealer_sellers() where model = 'Palio'), null, 'B does not see A''s request');
select ok((select ref from public.dealer_sellers() where model = 'Palio') <> current_setting('t.ref_s1'), 'B''s ref for S1 is not A''s');
select is((select count(*)::integer from public.dealer_sellers()), 3, 'B sees S1, S2 and A (not a member of B)');
reset role;

-- ================================================================ 6. the seller decides
set local role authenticated;
set local request.jwt.claims = '{"sub": "d3000000-0000-0000-0000-000000000011", "role": "authenticated"}';
select is((select row(dealer_name, dealer_locality, message, status)::text from public.my_dealer_seller_requests()),
          row('TT Autos', 'Quilmes', 'Hola, compramos tu auto.', 'pending')::text, 'S1 sees who asked');
select set_config('t.req_s1', (select id::text from public.my_dealer_seller_requests()), true);
set local request.jwt.claims = '{"sub": "d3000000-0000-0000-0000-000000000013", "role": "authenticated"}';
select throws_ok(format('select public.answer_dealer_seller_request(%s, true, %L, %L, false, %L)', current_setting('t.req_s1'),
                        'Otro', '1155556666', 'Acepto que Ese Auto le pase mis datos a TT Autos.'),
                 'P0001', 'request_not_found', 'someone else answering S1''s request: request_not_found');
set local request.jwt.claims = '{"sub": "d3000000-0000-0000-0000-000000000011", "role": "authenticated"}';
select throws_ok(format('select public.answer_dealer_seller_request(%s, true, %L, %L, false, null)', current_setting('t.req_s1'),
                        'Sergio', '1155556666'),
                 'P0001', 'consent_required', 'accepting without the consent text: consent_required');
select throws_ok(format('select public.answer_dealer_seller_request(%s, true, %L, %L, false, %L)', current_setting('t.req_s1'),
                        'S', '1155556666', 'Acepto que Ese Auto le pase mis datos a TT Autos.'),
                 'P0001', 'invalid_contact:name', 'a one-letter name: invalid_contact:name');
select throws_ok(format('select public.answer_dealer_seller_request(%s, true, %L, null, false, %L)', current_setting('t.req_s1'),
                        'Sergio', 'Acepto que Ese Auto le pase mis datos a TT Autos.'),
                 'P0001', 'invalid_contact:phone', 'nothing to share: invalid_contact:phone');
select lives_ok(format('select public.answer_dealer_seller_request(%s, true, %L, %L, false, %L)', current_setting('t.req_s1'),
                       ' Sergio ', '11 5555-6666', 'Acepto que Ese Auto le pase mi nombre y mi teléfono a TT Autos.'),
                'S1 accepts, sharing a name and a phone (not the email)');
set local request.jwt.claims = '{"sub": "d3000000-0000-0000-0000-00000000000a", "role": "authenticated"}';
select is((select row(request_status, shared_name, shared_phone, shared_email)::text from public.dealer_sellers() where model = 'Palio'),
          row('accepted', 'Sergio', '1155556666', null::text)::text, 'A gets only what S1 chose to share');
set local request.jwt.claims = '{"sub": "d3000000-0000-0000-0000-00000000000b", "role": "authenticated"}';
select is((select row(request_id, shared_phone)::text from public.dealer_sellers() where model = 'Palio'),
          row(null::bigint, null::text)::text, 'B gets nothing of it');
reset role;
select is((select props->>'accepted' from public.events where name = 'dealer_seller_answered'), 'true', 'the answer is an event (no contact in it)');

-- S2 declines B; C's request expired.
update public.dealer_seller_requests set created_at = now() - interval '15 days'
 where seller_user_id = 'd3000000-0000-0000-0000-000000000012' and dealer_id = (select id from public.dealers where name = 'Pgtres');
do $d$ begin
  perform set_config('t.req_b', (select id::text from public.dealer_seller_requests
                                  where dealer_id = current_setting('t.dealer_b')::bigint), true);
  perform set_config('t.req_c', (select r.id::text from public.dealer_seller_requests r join public.dealers d on d.id = r.dealer_id
                                  where d.name = 'Pgtres'), true);
end $d$;
set local role authenticated;
set local request.jwt.claims = '{"sub": "d3000000-0000-0000-0000-000000000012", "role": "authenticated"}';
select lives_ok(format('select public.answer_dealer_seller_request(%s, false)', current_setting('t.req_b')), 'S2 declines B');
select is((select status from public.my_dealer_seller_requests() where dealer_name = 'Pgtres'), 'expired', 'a request older than 14 days: expired');
select throws_ok(format('select public.answer_dealer_seller_request(%s, true, %L, %L, false, %L)', current_setting('t.req_c'),
                        'Sergio', '1155556666', 'Acepto que Ese Auto le pase mis datos a Pgtres.'),
                 'P0001', 'request_not_found', '... and can no longer be answered');
set local request.jwt.claims = '{"sub": "d3000000-0000-0000-0000-00000000000b", "role": "authenticated"}';
select is((select request_status from public.dealer_sellers() where model is null and request_id is not null), 'declined',
          'B sees «declined»');
reset role;

-- S1 unticks the agencies box: no dealer lists them any more.
update public.sell_intent set agencies_contact_ok = false where user_id = 'd3000000-0000-0000-0000-000000000011';
set local role authenticated;
set local request.jwt.claims = '{"sub": "d3000000-0000-0000-0000-00000000000a", "role": "authenticated"}';
select is((select count(*)::integer from public.dealer_sellers() where model = 'Palio'), 0,
          'a seller who withdrew is not listed (nor their contact)');
reset role;

-- ================================================================ 7. everything off
update public.app_config set value = value || '{"enabled": false}' where key = 'dealer_program';
set local role authenticated;
set local request.jwt.claims = '{"sub": "d3000000-0000-0000-0000-00000000000a", "role": "authenticated"}';
select throws_ok($$select * from public.dealer_sellers()$$, 'P0001', 'dealer_program_off', 'enabled=false: dealer_sellers off');
select throws_ok($$select * from public.dealer_buy_opportunities()$$, 'P0001', 'dealer_program_off', 'enabled=false: Qué comprar off');
set local request.jwt.claims = '{"sub": "d3000000-0000-0000-0000-000000000012", "role": "authenticated"}';
select throws_ok(format('select public.answer_dealer_seller_request(%s, false)', current_setting('t.req_b')), 'P0001', 'sellers_off',
                 'enabled=false: the seller''s answer is off too');
reset role;

select * from finish();
rollback;

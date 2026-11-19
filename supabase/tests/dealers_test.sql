-- Agencias: panel de stock y canal de venta (migration 20261228120000_dealer_program.sql,
-- docs/superpowers/specs/2026-11-18-agencias-design.md §3 and §7.1). Run with: supabase test db,
-- or on a cloned database (see §7.1 of the spec). Everything runs in one transaction and rolls back.
begin;
create extension if not exists pgtap with schema extensions;
select no_plan();

-- guard_match_access / the free quota would drop the fixtures' matches.
update public.app_config set value = jsonb_set(value, '{enforced}', 'false') where key = 'plan_limits';

-- ---------------------------------------------------------------- users
-- A owns «TT Autos», B owns «Otra Agencia», U/V/W/Y are buyers, X is an admin, E a buyer whose access ended.
insert into auth.users (instance_id, id, aud, role, email, created_at, updated_at) values
  ('00000000-0000-0000-0000-000000000000', 'd1000000-0000-0000-0000-00000000000a', 'authenticated', 'authenticated', 'a@dealers.test', now(), now()),
  ('00000000-0000-0000-0000-000000000000', 'd1000000-0000-0000-0000-00000000000b', 'authenticated', 'authenticated', 'b@dealers.test', now(), now()),
  ('00000000-0000-0000-0000-000000000000', 'd1000000-0000-0000-0000-000000000001', 'authenticated', 'authenticated', 'u@dealers.test', now(), now()),
  ('00000000-0000-0000-0000-000000000000', 'd1000000-0000-0000-0000-000000000002', 'authenticated', 'authenticated', 'v@dealers.test', now(), now()),
  ('00000000-0000-0000-0000-000000000000', 'd1000000-0000-0000-0000-000000000003', 'authenticated', 'authenticated', 'w@dealers.test', now(), now()),
  ('00000000-0000-0000-0000-000000000000', 'd1000000-0000-0000-0000-000000000004', 'authenticated', 'authenticated', 'y@dealers.test', now(), now()),
  ('00000000-0000-0000-0000-000000000000', 'd1000000-0000-0000-0000-00000000000f', 'authenticated', 'authenticated', 'x@dealers.test', now(), now()),
  ('00000000-0000-0000-0000-000000000000', 'd1000000-0000-0000-0000-00000000000e', 'authenticated', 'authenticated', 'e@dealers.test', now(), now());
update public.profiles set role = 'admin' where id = 'd1000000-0000-0000-0000-00000000000f';

-- ================================================================ 1. switch defaults and sanitizing
select is((select value from public.app_config where key = 'dealer_program'),
          '{"enabled": false, "channel_enabled": false, "manual_confirm_days": 7, "demand_min_count": 3}'::jsonb,
          'app_config.dealer_program: both switches off, 7 days, 3 people');
select is(public.dealer_program(),
          '{"enabled": false, "channel_enabled": false, "manual_confirm_days": 7, "demand_min_count": 3}'::jsonb,
          'dealer_program() with the defaults');
select is((select array[enabled::text, name] from public.sources where id = 'directo'), array['false', 'Agencias'],
          'source directo exists, disabled');

update public.app_config set value = '{"demand_min_count": 1}' where key = 'dealer_program';
select is(public.dealer_program()->'demand_min_count', '3'::jsonb, 'demand_min_count 1 -> 3');
update public.app_config set value = '{"demand_min_count": 2}' where key = 'dealer_program';
select is(public.dealer_program()->'demand_min_count', '3'::jsonb, 'demand_min_count 2 -> 3');
update public.app_config set value = '{"demand_min_count": 51}' where key = 'dealer_program';
select is(public.dealer_program()->'demand_min_count', '3'::jsonb, 'demand_min_count 51 -> 3');
update public.app_config set value = '{"demand_min_count": 10, "manual_confirm_days": 30}' where key = 'dealer_program';
select is(public.dealer_program()->'demand_min_count', '10'::jsonb, 'demand_min_count 10 stays');
select is(public.dealer_program()->'manual_confirm_days', '30'::jsonb, 'manual_confirm_days 30 stays');
update public.app_config set value = '{"manual_confirm_days": 0}' where key = 'dealer_program';
select is(public.dealer_program()->'manual_confirm_days', '7'::jsonb, 'manual_confirm_days 0 -> 7');
update public.app_config set value = '{"manual_confirm_days": 61}' where key = 'dealer_program';
select is(public.dealer_program()->'manual_confirm_days', '7'::jsonb, 'manual_confirm_days 61 -> 7');
update public.app_config set value = '{"manual_confirm_days": 7.5, "demand_min_count": "5"}' where key = 'dealer_program';
select is(public.dealer_program(),
          '{"enabled": false, "channel_enabled": false, "manual_confirm_days": 7, "demand_min_count": 3}'::jsonb,
          'a fraction or a string number -> defaults');
update public.app_config set value = '{"enabled": "true", "channel_enabled": 1}' where key = 'dealer_program';
select is(public.dealer_program(),
          '{"enabled": false, "channel_enabled": false, "manual_confirm_days": 7, "demand_min_count": 3}'::jsonb,
          'switches that are not booleans -> off');
update public.app_config set value = '[]' where key = 'dealer_program';
select is(public.dealer_program()->'enabled', 'false'::jsonb, 'a value that is not an object -> defaults');
delete from public.app_config where key = 'dealer_program';
select is(public.dealer_program(),
          '{"enabled": false, "channel_enabled": false, "manual_confirm_days": 7, "demand_min_count": 3}'::jsonb,
          'no row -> defaults');
insert into public.app_config (key, value)
values ('dealer_program', '{"enabled": false, "channel_enabled": false, "manual_confirm_days": 7, "demand_min_count": 3}');
select is(has_function_privilege('anon', 'public.dealer_program()', 'execute'), true, 'dealer_program(): anon can read it');
select is(has_function_privilege('authenticated', 'public.dealer_demand(text,text,integer,numeric,text,integer,double precision,double precision,uuid[],text)', 'execute')
          or has_function_privilege('authenticated', 'public.dealer_market_ref(text,text,integer,numeric,bigint)', 'execute')
          or has_function_privilege('authenticated', 'public.dealer_sweep()', 'execute')
          or has_function_privilege('authenticated', 'public.dealer_hide_listing(bigint)', 'execute')
          or has_function_privilege('authenticated', 'public.admin_dealer_seller_candidates(text,text)', 'execute'),
          false, 'raw demand, market reference, sweep, hide and admin candidates: service role only');
select is(has_function_privilege('anon', 'public.request_dealer_contact(bigint,text,text,text,boolean,text,bigint)', 'execute')
          or has_function_privilege('anon', 'public.create_dealer(text,text,double precision,double precision,text,text,text,text,jsonb)', 'execute'),
          false, 'the RPCs are not for anon');

-- ================================================================ 2. create_dealer
set local role authenticated;
set local request.jwt.claims = '{"sub": "d1000000-0000-0000-0000-00000000000a", "role": "authenticated"}';
select throws_ok($$select public.create_dealer('TT Autos', 'Quilmes', -34.72, -58.25)$$,
                 'P0001', 'dealer_program_off', 'create_dealer with enabled=false: dealer_program_off');
select is(public.my_dealer(), null, 'my_dealer() is null without a dealer');
reset role;

update public.app_config set value = '{"enabled": true, "channel_enabled": false, "manual_confirm_days": 7, "demand_min_count": 3}'
 where key = 'dealer_program';

set local role authenticated;
set local request.jwt.claims = '{"role": "authenticated"}';
select throws_ok($$select public.create_dealer('TT Autos', 'Quilmes', -34.72, -58.25)$$,
                 'P0001', 'not_signed_in', 'create_dealer without a session: not_signed_in');
set local request.jwt.claims = '{"sub": "d1000000-0000-0000-0000-00000000000a", "role": "authenticated"}';
select lives_ok($$select public.create_dealer(' TT Autos ', 'Quilmes', -34.72, -58.25, '11 2233-4455', '+54 9 11 2233-4455',
                                              'TT@Ejemplo.test', 'Av. Calchaquí 100',
                                              '[{"kind": "web", "url": "https://tt.example.test"}]')$$,
                'create_dealer with enabled=true creates it');
select is(public.my_dealer()->>'name', 'TT Autos', 'my_dealer(): the name, trimmed');
select is(array[public.my_dealer()->>'phone', public.my_dealer()->>'whatsapp', public.my_dealer()->>'contact_email'],
          array['1122334455', '5491122334455', 'tt@ejemplo.test'], '... phones as digits, email in lower case');
select is((public.my_dealer()->>'approved')::boolean, false, '... not approved yet');
select is((select role from public.dealer_members where user_id = 'd1000000-0000-0000-0000-00000000000a'), 'owner',
          '... and the owner membership');
select throws_ok($$select public.create_dealer('TT Dos', 'Quilmes', -34.72, -58.25)$$,
                 'P0001', 'already_member', 'a second dealer: already_member');
reset role;
do $d$ begin perform set_config('dt.dealer_a', (select id::text from public.dealers where name = 'TT Autos'), true); end $d$;

set local role authenticated;
set local request.jwt.claims = '{"sub": "d1000000-0000-0000-0000-00000000000b", "role": "authenticated"}';
select throws_ok($$select public.create_dealer('X', 'Quilmes', -34.72, -58.25)$$,
                 'P0001', 'invalid_dealer:name', 'a one-letter name: invalid_dealer:name');
select throws_ok($$select public.create_dealer('Otra Agencia', 'Quilmes', -34.72, -58.25, null, '123')$$,
                 'P0001', 'invalid_dealer:whatsapp', 'a short WhatsApp: invalid_dealer:whatsapp');
select throws_ok($$select public.create_dealer('Otra Agencia', 'Quilmes', -34.72, -58.25, null, null, null, null,
                                               '[{"kind": "web", "url": "http://x.test"}]')$$,
                 'P0001', 'invalid_dealer:profile_links', 'a link without https: invalid_dealer:profile_links');
select throws_ok($$select public.create_dealer('Otra Agencia', 'Quilmes', null, -58.25)$$,
                 'P0001', 'invalid_dealer:lat', 'no location: invalid_dealer:lat');
select lives_ok($$select public.create_dealer('Otra Agencia', 'Berazategui', -34.76, -58.21)$$, 'B creates its dealer');
reset role;
do $d$ begin perform set_config('dt.dealer_b', (select id::text from public.dealers where name = 'Otra Agencia'), true); end $d$;

-- ================================================================ 3. the agency's RPCs
set local role authenticated;
set local request.jwt.claims = '{"sub": "d1000000-0000-0000-0000-00000000000a", "role": "authenticated"}';
do $d$ begin perform set_config('dt.item_manual',
                  public.dealer_upsert_item(null, '{"make": "Pgdealer", "model": "Nadie", "trim": "SE", "year": 2017,
                                                    "mileage_km": 90000, "price": 20000000, "currency": "ars",
                                                    "images": ["https://img.test/1.jpg"], "in_stock_since": "2026-10-01",
                                                    "unknown_key": 1}')::text, true); end $d$;
select is((select array[origin, currency, sync_state, status] from public.dealer_stock_items
            where id = current_setting('dt.item_manual')::bigint),
          array['manual', 'ARS', 'pending', 'available'], 'dealer_upsert_item(null): a manual item, pending, available');
select isnt((select confirmed_at from public.dealer_stock_items where id = current_setting('dt.item_manual')::bigint), null,
            '... confirmed when created');
select throws_ok($$select public.dealer_upsert_item(null, '{"make": "Ford", "model": "Focus", "year": 1900, "price": 1, "currency": "USD"}')$$,
                 'P0001', 'invalid_item:year', 'a year before 1950: invalid_item:year');
select throws_ok($$select public.dealer_upsert_item(null, '{"make": "Ford", "model": "Focus", "year": 2017, "currency": "USD"}')$$,
                 'P0001', 'invalid_item:price', 'no price: invalid_item:price');
select throws_ok($$select public.dealer_upsert_item(null, '{"make": "Ford", "model": "Focus", "year": 2017, "price": 10, "currency": "EUR"}')$$,
                 'P0001', 'invalid_item:currency', 'a currency that is not ARS or USD: invalid_item:currency');
select throws_ok($$select public.dealer_upsert_item(null, '{"make": "Ford", "model": "Focus", "year": 2017, "price": 10, "currency": "USD",
                                                           "images": ["http://img.test/1.jpg"]}')$$,
                 'P0001', 'invalid_item:images', 'an image without https: invalid_item:images');
select throws_ok($$select public.dealer_upsert_item(null, '{"make": " ", "model": "Focus", "year": 2017, "price": 10, "currency": "USD"}')$$,
                 'P0001', 'invalid_item:make', 'an empty make: invalid_item:make');
select throws_ok($$select public.dealer_upsert_item(null, '{"make": "Ford", "model": "Focus", "year": 2017, "price": 10, "currency": "USD",
                                                           "in_stock_since": "2026-02-30"}')$$,
                 'P0001', 'invalid_item:in_stock_since', 'an impossible date: invalid_item:in_stock_since');
select lives_ok($$select public.dealer_upsert_item(current_setting('dt.item_manual')::bigint, '{"price": 21000000, "trim": null}')$$,
                'editing: only the keys given');
select is((select array[price::text, coalesce(trim, '-'), model] from public.dealer_stock_items
            where id = current_setting('dt.item_manual')::bigint),
          array['21000000', '-', 'Nadie'], '... price replaced, trim cleared, the rest kept');

-- Spreadsheet: all or nothing.
select throws_ok($$select public.dealer_import_items(
                     '[{"make": "Pgdealer", "model": "Hoja", "year": 2018, "price": 15000, "currency": "USD"},
                       {"make": "Pgdealer", "model": "Hoja", "year": 3000, "price": 15000, "currency": "USD"}]',
                     'stock.xlsx', 'xlsx')$$,
                 'P0001', 'invalid_item:2:year', 'a bad row: invalid_item:<row>:<field>');
select is((select count(*)::int from public.dealer_stock_items where model = 'Hoja'), 0, '... and nothing is written');
select throws_ok($$select public.dealer_import_items((select jsonb_agg('{}'::jsonb) from generate_series(1, 501)), 'x.csv', 'csv')$$,
                 'P0001', 'too_many_rows', '501 rows: too_many_rows');
select is(public.dealer_import_items(
            '[{"make": "Pgdealer", "model": "Hoja", "year": 2018, "price": 15000, "currency": "USD", "dominio": "AB123CD"},
              {"make": "Pgdealer", "model": "Hoja", "year": 2019, "price": 25000000, "currency": "ARS"}]',
            'stock.xlsx', 'xlsx')->'imported', '2'::jsonb, 'two good rows are imported');
select is((select count(*)::int from public.dealer_stock_items where model = 'Hoja' and origin = 'sheet'
              and confirmed_at is not null and import_id is not null), 2, '... as confirmed sheet items of the import');

select lives_ok($$select public.dealer_add_source('mercadolibre', 'https://www.mercadolibre.com.ar/perfil/TTAUTOS', 'TT AUTOS')$$,
                'dealer_add_source: a pending source');
select throws_ok($$select public.dealer_add_source('directo', 'https://x.test', 'TT')$$,
                 'P0001', 'invalid_source', 'directo is not a source to sync');
select throws_ok($$select public.dealer_add_source('nope', 'https://x.test', 'TT')$$,
                 'P0001', 'invalid_source', 'an unknown source: invalid_source');
select is(public.my_dealer()->'sources'->0->>'status', 'pending', 'my_dealer() lists it as pending');
select lives_ok($$select public.dealer_set_item_private(current_setting('dt.item_manual')::bigint, 15000000, 'ars', 'Lo trajo un cliente')$$,
                'dealer_set_item_private: what it paid');
select throws_ok($$select public.dealer_set_item_private(current_setting('dt.item_manual')::bigint, 15000000, null, null)$$,
                 'P0001', 'invalid_item:purchase_currency', 'a purchase price without currency');
select is((select purchase_currency from public.dealer_item_private where item_id = current_setting('dt.item_manual')::bigint),
          'ARS', '... the dealer reads it back');
reset role;

-- B's own item, for the RLS checks and the unapproved demand.
set local role authenticated;
set local request.jwt.claims = '{"sub": "d1000000-0000-0000-0000-00000000000b", "role": "authenticated"}';
do $d$ begin perform set_config('dt.item_b',
                  public.dealer_upsert_item(null, '{"make": "Pgdealer", "model": "Demand", "year": 2017, "price": 20000000,
                                                    "currency": "ARS"}')::text, true); end $d$;
select throws_ok($$select public.dealer_upsert_item(current_setting('dt.item_manual')::bigint, '{"price": 1}')$$,
                 'P0001', 'item_not_found', 'B cannot edit A''s item');
select throws_ok($$select public.dealer_set_item_status(current_setting('dt.item_manual')::bigint, 'sold')$$,
                 'P0001', 'item_not_found', 'B cannot change the status of A''s item');
select throws_ok($$select public.dealer_set_item_private(current_setting('dt.item_manual')::bigint, 1, 'USD', null)$$,
                 'P0001', 'item_not_found', 'B cannot write A''s private data');
reset role;

-- ================================================================ fixtures: approval and listings
update public.dealers set approved_at = now() where id = current_setting('dt.dealer_a')::bigint;

insert into public.fx_rates (date, kind, rate, source) values (current_date + 1, 'blue', 1600, 'test')
on conflict (date, kind) do update set rate = excluded.rate;

-- Pgdealer Focus: 9801 a common listing, 98xx directo / synced of A or B.
insert into public.listings (id, source, external_id, url, title, make, model, year, price, currency, price_usd,
                             mileage_km, lat, lon, dealer_id, dealer_status, dealer_confirmed_at, first_seen_at)
overriding system value values
  (9801, 'mercadolibre', 'DT-9801', 'https://example.test/dt-9801', 'Pgdealer Focus', 'Pgdealer', 'Focus', 2017,
   15000, 'USD', 15000, 90000, -34.72, -58.25, null, null, null, now()),
  (9802, 'directo', 'DT-9802', 'https://example.test/dt-9802', 'Pgdealer Focus TT', 'Pgdealer', 'Focus', 2017,
   16000, 'USD', 16000, 80000, -34.72, -58.25, current_setting('dt.dealer_a')::bigint, 'available', now(), now()),
  (9803, 'directo', 'DT-9803', 'https://example.test/dt-9803', 'Pgdealer Focus reservado', 'Pgdealer', 'Focus', 2017,
   16000, 'USD', 16000, 80000, -34.72, -58.25, current_setting('dt.dealer_a')::bigint, 'reserved', now(), now()),
  (9804, 'directo', 'DT-9804', 'https://example.test/dt-9804', 'Pgdealer Focus sin confirmar', 'Pgdealer', 'Focus', 2017,
   16000, 'USD', 16000, 80000, -34.72, -58.25, current_setting('dt.dealer_a')::bigint, 'available', now() - interval '8 days', now()),
  (9805, 'directo', 'DT-9805', 'https://example.test/dt-9805', 'Pgdealer Focus sin aprobar', 'Pgdealer', 'Focus', 2017,
   16000, 'USD', 16000, 80000, -34.76, -58.21, current_setting('dt.dealer_b')::bigint, 'available', now(), now()),
  (9806, 'mercadolibre', 'DT-9806', 'https://example.test/dt-9806', 'Pgdealer Focus vendido', 'Pgdealer', 'Focus', 2017,
   15500, 'USD', 15500, 85000, -34.72, -58.25, current_setting('dt.dealer_a')::bigint, 'sold', now(), now()),
  (9807, 'mercadolibre', 'DT-9807', 'https://example.test/dt-9807', 'Pgdealer Focus sincronizado', 'Pgdealer', 'Focus', 2017,
   15500, 'USD', 15500, 85000, -34.72, -58.25, current_setting('dt.dealer_a')::bigint, 'available', now(), now()),
  (9808, 'directo', 'DT-9808', 'https://example.test/dt-9808', 'Pgdealer Focus estados', 'Pgdealer', 'Focus', 2017,
   16000, 'USD', 16000, 80000, -34.72, -58.25, current_setting('dt.dealer_a')::bigint, 'available', now(), now());
-- Five more visible directo listings for the 24 h cap.
insert into public.listings (id, source, external_id, url, title, make, model, year, price, currency, price_usd,
                             dealer_id, dealer_status, dealer_confirmed_at)
overriding system value
select 9810 + g, 'directo', 'DT-981' || g, 'https://example.test/dt-981' || g, 'Pgdealer Cupo', 'Pgdealer', 'Cupo', 2018,
       10000, 'USD', 10000, current_setting('dt.dealer_a')::bigint, 'available', now()
  from generate_series(1, 6) g;

insert into public.dealer_stock_items (dealer_id, origin, listing_id, make, model, year, price, currency, status,
                                       confirmed_at, sync_state, matched_at)
values (current_setting('dt.dealer_a')::bigint, 'manual', 9802, 'Pgdealer', 'Focus', 2017, 16000, 'USD', 'available', now(), 'synced', now()),
       (current_setting('dt.dealer_a')::bigint, 'manual', 9803, 'Pgdealer', 'Focus', 2017, 16000, 'USD', 'reserved', now(), 'synced', now()),
       (current_setting('dt.dealer_a')::bigint, 'manual', 9804, 'Pgdealer', 'Focus', 2017, 16000, 'USD', 'available', now() - interval '8 days', 'synced', now()),
       (current_setting('dt.dealer_a')::bigint, 'manual', 9808, 'Pgdealer', 'Focus', 2017, 16000, 'USD', 'available', now(), 'synced', now());
insert into public.dealer_stock_items (dealer_id, origin, listing_id, status, sync_state, matched_at)
values (current_setting('dt.dealer_a')::bigint, 'sync', 9806, 'sold', 'linked', now()),
       (current_setting('dt.dealer_a')::bigint, 'sync', 9807, 'available', 'linked', now());
do $d$ begin perform set_config('dt.item_9808', (select id::text from public.dealer_stock_items where listing_id = 9808), true); end $d$;
do $d$ begin perform set_config('dt.item_9804', (select id::text from public.dealer_stock_items where listing_id = 9804), true); end $d$;
do $d$ begin perform set_config('dt.item_9807', (select id::text from public.dealer_stock_items where listing_id = 9807), true); end $d$;

-- Searches (triggers off: plan limits and observation).
set local session_replication_role = replica;
insert into public.search_profiles (id, user_id, name, filters, enabled) overriding system value values
  (9851, 'd1000000-0000-0000-0000-000000000001', 'Focus U', '{"make": "Pgdealer", "model": "Focus"}', true),
  (9852, 'd1000000-0000-0000-0000-00000000000e', 'Focus E', '{"make": "Pgdealer", "model": "Focus"}', false),
  (9853, 'd1000000-0000-0000-0000-00000000000e', 'Solo ocultos E', '{"make": "Pgdealer", "model": "Focus"}', false);
set local session_replication_role = origin;

-- ================================================================ 5. dealer_listing_hidden: the 9 cases
select is(public.dealer_listing_hidden('mercadolibre', null, null, null), null, 'gate 1: a common listing passes');
select is(public.dealer_listing_hidden('directo', null, 'available', now()), 'no_dealer', 'gate 2: directo without dealer');
select is(public.dealer_listing_hidden('directo', current_setting('dt.dealer_a')::bigint, 'available', now()), 'channel_off',
          'gate 3: directo with the channel off');
update public.app_config set value = '{"enabled": true, "channel_enabled": true, "manual_confirm_days": 7, "demand_min_count": 3}'
 where key = 'dealer_program';
select is(public.dealer_listing_hidden('directo', current_setting('dt.dealer_b')::bigint, 'available', now()), 'not_approved',
          'gate 4: directo of an unapproved dealer');
update public.dealers set status = 'paused' where id = current_setting('dt.dealer_a')::bigint;
select is(public.dealer_listing_hidden('directo', current_setting('dt.dealer_a')::bigint, 'available', now()), 'not_approved',
          'gate 4: ... or a paused one');
update public.dealers set status = 'active' where id = current_setting('dt.dealer_a')::bigint;
select is(public.dealer_listing_hidden('directo', current_setting('dt.dealer_a')::bigint, 'reserved', now()), 'not_available',
          'gate 5: directo reserved');
select is(public.dealer_listing_hidden('directo', current_setting('dt.dealer_a')::bigint, null, now()), 'not_available',
          'gate 5: ... or without a status');
select is(public.dealer_listing_hidden('directo', current_setting('dt.dealer_a')::bigint, 'available', now() - interval '8 days'),
          'unconfirmed', 'gate 6: confirmed 8 days ago with manual_confirm_days = 7');
select is(public.dealer_listing_hidden('directo', current_setting('dt.dealer_a')::bigint, 'available', null),
          'unconfirmed', 'gate 6: ... or never');
select is(public.dealer_listing_hidden('directo', current_setting('dt.dealer_a')::bigint, 'available', now() - interval '6 days'),
          null, 'gate 7: confirmed 6 days ago passes');
select is(public.dealer_listing_hidden('directo', current_setting('dt.dealer_a')::bigint, 'available', now()), null,
          'gate 7: directo visible');
select is(public.dealer_listing_hidden('mercadolibre', current_setting('dt.dealer_a')::bigint, 'sold', null), 'not_available',
          'gate 8: synced and sold');
select is(public.dealer_listing_hidden('mercadolibre', current_setting('dt.dealer_a')::bigint, 'reserved', null), 'not_available',
          'gate 8: synced and reserved');
select is(public.dealer_listing_hidden('mercadolibre', current_setting('dt.dealer_a')::bigint, 'available', null), null,
          'gate 9: synced and available passes');
select is(public.dealer_listing_hidden('mercadolibre', current_setting('dt.dealer_b')::bigint, 'available', null), null,
          'gate 9: ... even for an unapproved dealer (only directo needs approval)');
select is(public.dealer_public_name(current_setting('dt.dealer_a')::bigint), 'TT Autos', 'dealer_public_name: approved, channel on');
select is(public.dealer_public_name(current_setting('dt.dealer_b')::bigint), null, '... null for an unapproved dealer');

-- ================================================================ 6. match_cards
insert into public.matches (search_profile_id, listing_id, score, level, score_breakdown, match_reasons, scoring_version)
select 9851, l.id, 80, case when l.id in (9801, 9802) then 'high' else 'good' end::public.match_level, '{}', '{}', 'test'
  from public.listings l where l.id between 9801 and 9808;

select is(array(select attname::text from pg_attribute
                 where attrelid = 'public.match_cards'::regclass and attnum > 0 and not attisdropped
                 order by attnum desc limit 4),
          array['dealer_confirmed_at', 'dealer_name', 'dealer_id', 'color_method'],
          'match_cards: dealer_id, dealer_name, dealer_confirmed_at appended after color_method');

set local role authenticated;
set local request.jwt.claims = '{"sub": "d1000000-0000-0000-0000-000000000001", "role": "authenticated"}';
select is(array(select listing_id from public.match_cards where search_profile_id = 9851 order by listing_id),
          array[9801, 9802, 9807, 9808]::bigint[], 'match_cards: hidden listings (reserved, unconfirmed, unapproved, sold) are out');
select is((select dealer_name from public.match_cards where listing_id = 9802), 'TT Autos', '... a visible directo carries dealer_name');
select is((select dealer_name from public.match_cards where listing_id = 9807), 'TT Autos', '... a synced one too');
select is((select array[dealer_id::text, dealer_name, dealer_confirmed_at::text] from public.match_cards where listing_id = 9801),
          array[null, null, null]::text[], '... a common listing has no dealer columns');
select is((select array[title, make, source, level::text] from public.match_cards where listing_id = 9801),
          array['Pgdealer Focus', 'Pgdealer', 'mercadolibre', 'high'], '... and the rest of the row as before');
reset role;

update public.app_config set value = '{"enabled": true, "channel_enabled": false, "manual_confirm_days": 7, "demand_min_count": 3}'
 where key = 'dealer_program';
set local role authenticated;
set local request.jwt.claims = '{"sub": "d1000000-0000-0000-0000-000000000001", "role": "authenticated"}';
select is(array(select listing_id from public.match_cards where search_profile_id = 9851 order by listing_id),
          array[9801, 9807]::bigint[], 'match_cards with the channel off: no directo');
select is((select dealer_name from public.match_cards where listing_id = 9807), null, '... and no dealer_name');
reset role;
update public.app_config set value = '{"enabled": true, "channel_enabled": true, "manual_confirm_days": 7, "demand_min_count": 3}'
 where key = 'dealer_program';

-- ================================================================ 7. comparables and landing_feed
select is((select count(*)::int from public.comparable_listings(9801) where source = 'directo'), 0,
          'comparable_listings ignores directo');
select is((select array_agg(id order by id) from public.comparable_listings(9801)), array[9806, 9807]::bigint[],
          '... and keeps the portal listings, synced ones included');
select is((public.comparables(9801)->>'n')::int, 2, 'comparables() counts only those');
select is((select count(*)::int from public.comparable_listings(9802) where source = 'directo'), 0,
          '... a directo listing is not compared with itself or its siblings');
select is((public.landing_feed()->>'flagged_24h')::int,
          (select count(distinct l.id)::int from public.listings l join public.matches m on m.listing_id = l.id
            where l.first_seen_at > now() - interval '24 hours' and l.status = 'active' and m.level = 'high'
              and l.source <> 'directo'),
          'landing_feed does not count directo');
select cmp_ok((select count(distinct l.id)::int from public.listings l join public.matches m on m.listing_id = l.id
                where l.first_seen_at > now() - interval '24 hours' and l.status = 'active' and m.level = 'high'),
              '>', (public.landing_feed()->>'flagged_24h')::int, '... although a directo was flagged high (fixture check)');

-- ================================================================ 8. preview_search
select is((public.preview_search('{"make": "Pgdealer", "model": "Focus"}')->>'count')::int, 4,
          'preview_search: the common one, the visible directo and the two visible synced (9801, 9802, 9807, 9808)');
select is((public.preview_search('{"make": "Pgdealer", "model": "Focus", "seller_types": ["private"]}')->>'count')::int, 1,
          '... with seller_types private, no listing with dealer_id (any plan)');
select is((public.preview_search('{"make": "Pgdealer", "model": "Focus", "seller_types": ["dealer"]}')->>'count')::int, 4,
          '... with seller_types dealer, all of them');
update public.app_config set value = '{"enabled": true, "channel_enabled": false, "manual_confirm_days": 7, "demand_min_count": 3}'
 where key = 'dealer_program';
select is((public.preview_search('{"make": "Pgdealer", "model": "Focus"}')->>'count')::int, 2,
          '... with the channel off, no directo');
update public.app_config set value = '{"enabled": true, "channel_enabled": true, "manual_confirm_days": 7, "demand_min_count": 3}'
 where key = 'dealer_program';

-- ================================================================ 13-15. welcome_cars, missed_car, missed_since_expiry
select is((select c ? 'dealer_name' from jsonb_array_elements(public.welcome_cars('d1000000-0000-0000-0000-000000000001', 9851, 10)) c
            where (c->>'listing_id')::bigint = 9801), false, 'welcome_cars: no dealer_name for a common listing');
select is((select c->>'dealer_name' from jsonb_array_elements(public.welcome_cars('d1000000-0000-0000-0000-000000000001', 9851, 10)) c
            where (c->>'listing_id')::bigint = 9802), 'TT Autos', '... dealer_name for a labeled one');

-- E's paused search counted these while they were visible.
insert into public.expired_search_matches (search_profile_id, listing_id, access_ended_at, level, diff_pct) values
  (9852, 9801, '2026-11-01 12:00+00', 'high', 10),
  (9852, 9802, '2026-11-01 12:00+00', 'high', 30),
  (9852, 9803, '2026-11-01 12:00+00', 'high', 34),
  (9852, 9804, '2026-11-01 12:00+00', 'high', 33),
  (9852, 9805, '2026-11-01 12:00+00', 'high', 32),
  (9852, 9806, '2026-11-01 12:00+00', 'high', 31),
  (9853, 9803, '2026-11-01 12:00+00', 'high', 20),
  (9853, 9806, '2026-11-01 12:00+00', 'high', 20);
select is(public.missed_car(9852, '2026-11-01 12:00+00')->>'listing_id', '9802',
          'missed_car: the hidden ones (reserved, 8 days unconfirmed, unapproved, synced sold) are skipped');
select is(public.missed_car(9852, '2026-11-01 12:00+00')->>'dealer_name', 'TT Autos', '... the visible directo carries dealer_name');
select is(public.missed_car(9853, '2026-11-01 12:00+00'), null, '... only hidden ones: null');
update public.app_config set value = '{"enabled": true, "channel_enabled": false, "manual_confirm_days": 7, "demand_min_count": 3}'
 where key = 'dealer_program';
select is(public.missed_car(9852, '2026-11-01 12:00+00')->>'listing_id', '9801', '... with the channel off, the common one');
select is(public.missed_car(9852, '2026-11-01 12:00+00') ? 'dealer_name', false, '... without dealer_name');

-- missed_since_expiry as E, with access ended.
update public.app_config set value = jsonb_set(value, '{enforced}', 'true') where key = 'plan_limits';
update public.profiles set free_trial_started_at = now() - interval '10 days' where id = 'd1000000-0000-0000-0000-00000000000e';
set local role authenticated;
set local request.jwt.claims = '{"sub": "d1000000-0000-0000-0000-00000000000e", "role": "authenticated"}';
select is(array[(public.missed_since_expiry()->>'found')::int, (public.missed_since_expiry()->>'below')::int], array[1, 1],
          'missed_since_expiry with the channel off: only the common one');
reset role;
update public.app_config set value = '{"enabled": true, "channel_enabled": true, "manual_confirm_days": 7, "demand_min_count": 3}'
 where key = 'dealer_program';
set local role authenticated;
set local request.jwt.claims = '{"sub": "d1000000-0000-0000-0000-00000000000e", "role": "authenticated"}';
select is(array[(public.missed_since_expiry()->>'found')::int, (public.missed_since_expiry()->>'below')::int], array[2, 2],
          'missed_since_expiry: the common and the visible directo found; hidden ones neither found nor below');
reset role;
update public.app_config set value = jsonb_set(value, '{enforced}', 'false') where key = 'plan_limits';

-- 14. missed_car keeps the strict color rule.
insert into public.listings (id, source, external_id, url, title, make, model, year, price, currency, price_usd, color, attributes)
overriding system value values
  (9861, 'mercadolibre', 'DT-9861', 'https://example.test/dt-9861', 'Pgdealer Color azul', 'Pgdealer', 'Color', 2018, 10000, 'USD', 10000, 'azul', '{}'),
  (9862, 'mercadolibre', 'DT-9862', 'https://example.test/dt-9862', 'Pgdealer Color rojo', 'Pgdealer', 'Color', 2018, 10000, 'USD', 10000, 'rojo', '{}'),
  (9863, 'mercadolibre', 'DT-9863', 'https://example.test/dt-9863', 'Pgdealer Color azul foto roja', 'Pgdealer', 'Color', 2018, 10000, 'USD', 10000, 'azul',
   '{"_color": {"method": "vision", "candidates": [{"color": "azul", "prob": 40}, {"color": "rojo", "prob": 60}]}}');
set local session_replication_role = replica;
insert into public.search_profiles (id, user_id, name, filters, enabled) overriding system value values
  (9864, 'd1000000-0000-0000-0000-00000000000e', 'Rojo', '{"make": "Pgdealer", "model": "Color", "colors": ["rojo"]}', false),
  (9865, 'd1000000-0000-0000-0000-00000000000e', 'Cualquiera', '{"make": "Pgdealer", "model": "Color"}', false);
set local session_replication_role = origin;
insert into public.expired_search_matches (search_profile_id, listing_id, access_ended_at, level, diff_pct)
select s.id, v.listing_id, '2026-11-01 12:00+00', 'good', v.diff
  from (values (9864::bigint), (9865::bigint)) s (id)
 cross join (values (9861::bigint, 30::real), (9862, 10), (9863, 25)) v (listing_id, diff);
select is(public.missed_car(9864, '2026-11-01 12:00+00')->>'listing_id', '9862',
          'missed_car with colors rojo: the red one, not the blue one, not the blue one with a red photo candidate');
select is(public.missed_car(9865, '2026-11-01 12:00+00')->>'listing_id', '9861', '... without colors, the best diff');

-- ================================================================ 4. the buyer's contact
update public.app_config set value = '{"enabled": true, "channel_enabled": false, "manual_confirm_days": 7, "demand_min_count": 3}'
 where key = 'dealer_program';
set local role authenticated;
set local request.jwt.claims = '{"sub": "d1000000-0000-0000-0000-000000000001", "role": "authenticated"}';
select throws_ok($$select public.request_dealer_contact(9802, 'Juana Pérez', '11 5555-6666', null, true,
                   'Acepto que Ese Auto le pase mi nombre, mi teléfono y mi mensaje a TT Autos.')$$,
                 'P0001', 'dealer_program_off', 'contact with the channel off: dealer_program_off');
reset role;
update public.app_config set value = '{"enabled": true, "channel_enabled": true, "manual_confirm_days": 7, "demand_min_count": 3}'
 where key = 'dealer_program';
set local session_replication_role = replica;
insert into public.notifications (id, user_id, listing_id, kind, channel, status, dedupe_key)
overriding system value values
  (98901, 'd1000000-0000-0000-0000-000000000001', 9811, 'new_match', 'telegram', 'sent', 'dt:9811'),
  (98902, 'd1000000-0000-0000-0000-000000000002', 9812, 'new_match', 'email', 'sent', 'dt:9812');
set local session_replication_role = origin;

set local role authenticated;
set local request.jwt.claims = '{"sub": "d1000000-0000-0000-0000-000000000001", "role": "authenticated"}';
select throws_ok($$select public.request_dealer_contact(9802, 'Juana Pérez', '11 5555-6666', null, false,
                   'Acepto que Ese Auto le pase mi nombre, mi teléfono y mi mensaje a TT Autos.')$$,
                 'P0001', 'consent_required', 'without the box ticked: consent_required');
select throws_ok($$select public.request_dealer_contact(9802, 'Juana Pérez', '11 5555-6666', null, true, 'Acepto')$$,
                 'P0001', 'consent_required', '... or without the consent text');
select throws_ok($$select public.request_dealer_contact(9803, 'Juana Pérez', '11 5555-6666', null, true,
                   'Acepto que Ese Auto le pase mi nombre, mi teléfono y mi mensaje a TT Autos.')$$,
                 'P0001', 'contact_unavailable', 'a hidden listing (reserved): contact_unavailable');
select throws_ok($$select public.request_dealer_contact(9801, 'Juana Pérez', '11 5555-6666', null, true,
                   'Acepto que Ese Auto le pase mi nombre, mi teléfono y mi mensaje a TT Autos.')$$,
                 'P0001', 'contact_unavailable', 'a common listing: contact_unavailable');
select throws_ok($$select public.request_dealer_contact(9802, 'Juana Pérez', '1234', null, true,
                   'Acepto que Ese Auto le pase mi nombre, mi teléfono y mi mensaje a TT Autos.')$$,
                 'P0001', 'invalid_contact:phone', 'a short phone: invalid_contact:phone');
select throws_ok($$select public.request_dealer_contact(9802, 'J', '11 5555-6666', null, true,
                   'Acepto que Ese Auto le pase mi nombre, mi teléfono y mi mensaje a TT Autos.')$$,
                 'P0001', 'invalid_contact:name', 'a one-letter name: invalid_contact:name');
select is((public.request_dealer_contact(9802, ' Juana Pérez ', '+54 11 5555-6666', 'Hola, ¿sigue disponible?', true,
                   'Acepto que Ese Auto le pase mi nombre, mi teléfono y mi mensaje a TT Autos.')->>'created')::boolean,
          true, 'a valid request creates the lead');
select is((public.request_dealer_contact(9802, 'Juana Pérez', '11 5555-6666', null, true,
                   'Acepto que Ese Auto le pase mi nombre, mi teléfono y mi mensaje a TT Autos.')
           - 'lead_id' - 'created_at'),
          '{"created": false, "dealer_name": "TT Autos", "whatsapp": "5491122334455", "vehicle": "Pgdealer Focus 2017"}'::jsonb,
          'the same request again: created false, with the WhatsApp and the vehicle');
select is((public.request_dealer_contact(9811, 'Juana Pérez', '11 5555-6666', null, true,
                   'Acepto que Ese Auto le pase mi nombre, mi teléfono y mi mensaje a TT Autos.', 98901)->>'created')::boolean,
          true, 'a lead from a Telegram alert');
select lives_ok($$select public.request_dealer_contact(9812, 'Juana Pérez', '11 5555-6666', null, true,
                   'Acepto que Ese Auto le pase mi nombre, mi teléfono y mi mensaje a TT Autos.', 98902)$$,
                'a lead with someone else''s notification');
select lives_ok($$select public.request_dealer_contact(9813, 'Juana Pérez', '11 5555-6666', null, true,
                   'Acepto que Ese Auto le pase mi nombre, mi teléfono y mi mensaje a TT Autos.')$$, '4th lead');
select lives_ok($$select public.request_dealer_contact(9814, 'Juana Pérez', '11 5555-6666', null, true,
                   'Acepto que Ese Auto le pase mi nombre, mi teléfono y mi mensaje a TT Autos.')$$, '5th lead');
select throws_ok($$select public.request_dealer_contact(9815, 'Juana Pérez', '11 5555-6666', null, true,
                   'Acepto que Ese Auto le pase mi nombre, mi teléfono y mi mensaje a TT Autos.')$$,
                 'P0001', 'rate_limited', 'the 6th new lead in 24 h: rate_limited');
select is((select array_agg(origin order by listing_id) from public.dealer_leads), array['ficha', 'telegram', 'ficha', 'ficha', 'ficha'],
          'the buyer sees their 5 leads; the origin comes from their own notification only');
select is((select array[buyer_name, buyer_phone, message] from public.dealer_leads where listing_id = 9802),
          array['Juana Pérez', '541155556666', 'Hola, ¿sigue disponible?'], '... name trimmed, phone as digits');
select is((public.listing_dealer_card(9802) - 'confirmed_at' - 'my_lead' - 'dealer_id'),
          '{"dealer_name": "TT Autos", "badge": true, "is_directo": true, "hidden_reason": null, "viewer_is_member": false,
            "can_request": false, "whatsapp": "5491122334455"}'::jsonb,
          'listing_dealer_card after asking: no new request, the WhatsApp shows');
select is(public.listing_dealer_card(9801), null, 'listing_dealer_card of a common listing: null');
select is(array(select listing_id from public.dealer_badges(array[9801, 9802, 9803, 9807, 9802]::bigint[]) order by 1),
          array[9802, 9807]::bigint[], 'dealer_badges: only labeled, visible ones, once');
reset role;

set local role authenticated;
set local request.jwt.claims = '{"sub": "d1000000-0000-0000-0000-000000000002", "role": "authenticated"}';
select is((select count(*)::int from public.dealer_leads), 0, 'another buyer sees none of those leads');
select is((public.listing_dealer_card(9802)->>'can_request')::boolean, true, '... and can still ask');
select is(public.listing_dealer_card(9802)->'whatsapp', 'null'::jsonb, '... without the WhatsApp before asking');
select is(array[public.listing_dealer_card(9804)->'dealer_id', public.listing_dealer_card(9804)->'hidden_reason',
                public.listing_dealer_card(9804)->'confirmed_at', public.listing_dealer_card(9804)->'badge'],
          array['null', 'null', 'null', 'false']::jsonb[],
          'listing_dealer_card of a hidden car to a non-member: not whose it is nor why it is hidden');
select is((select array_agg(id order by id) from public.listings where id between 9801 and 9808),
          array[9801, 9802, 9806, 9807, 9808]::bigint[],
          'RLS: a non-member does not read hidden directo listings (reserved, unconfirmed, unapproved); portal ones stay');
reset role;

set local role authenticated;
set local request.jwt.claims = '{"sub": "d1000000-0000-0000-0000-00000000000a", "role": "authenticated"}';
select throws_ok($$select public.request_dealer_contact(9802, 'Dueño TT', '11 5555-6666', null, true,
                   'Acepto que Ese Auto le pase mi nombre, mi teléfono y mi mensaje a TT Autos.')$$,
                 'P0001', 'contact_unavailable', 'a member asking for their own car: contact_unavailable');
select is((select count(*)::int from public.dealer_leads where dealer_id = current_setting('dt.dealer_a')::bigint), 5,
          'the dealer sees its 5 leads');
select throws_ok($$select buyer_user_id from public.dealer_leads$$, '42501', null,
                 '... but not buyer_user_id');
select throws_ok($$select consent_text from public.dealer_leads$$, '42501', null, '... nor consent_text');
select is((public.listing_dealer_card(9804)->>'viewer_is_member')::boolean, true, 'listing_dealer_card: a member sees their own hidden car');
select is(public.listing_dealer_card(9804)->>'hidden_reason', 'unconfirmed', '... with the reason');
select is((select count(*)::int from public.listings where id in (9802, 9803, 9804, 9808)), 4,
          'RLS: a member reads its own hidden directo listings');
select is((select count(*)::int from public.listings where id = 9805), 0, '... but not another dealer''s');
select is((public.my_dealer()->'counts'->>'leads_new')::int, 5, 'my_dealer() counts the new leads');
select lives_ok($$select public.dealer_set_lead_status((select min(id) from public.dealer_leads), 'contacted')$$,
                'dealer_set_lead_status on its own lead');
select isnt((select status_changed_at from public.dealer_leads where id = (select min(id) from public.dealer_leads)), null,
            '... stamps status_changed_at');
select throws_ok($$select public.dealer_set_lead_status((select min(id) from public.dealer_leads), 'ganado')$$,
                 'P0001', 'invalid_status', 'an unknown lead status: invalid_status');
reset role;
do $d$ begin perform set_config('dt.lead_a', (select min(id)::text from public.dealer_leads where dealer_id = current_setting('dt.dealer_a')::bigint), true); end $d$;

select is((select count(*)::int from public.events where name = 'dealer_lead_created'
             and user_id = 'd1000000-0000-0000-0000-000000000001'), 5, 'one dealer_lead_created event per new lead');
select is((select count(*)::int from public.events where name = 'dealer_lead_created'
             and props ?| array['buyer_name', 'buyer_phone', 'message', 'name', 'phone']), 0,
          '... with no name, phone or message in props');

-- ================================================================ 3. RLS: B sees nothing of A
set local role authenticated;
set local request.jwt.claims = '{"sub": "d1000000-0000-0000-0000-00000000000b", "role": "authenticated"}';
select is((select count(*)::int from public.dealers where id = current_setting('dt.dealer_a')::bigint), 0, 'RLS: B does not see A''s dealer');
select is((select count(*)::int from public.dealer_members where dealer_id = current_setting('dt.dealer_a')::bigint), 0, '... nor its members');
select is((select count(*)::int from public.dealer_sources where dealer_id = current_setting('dt.dealer_a')::bigint), 0, '... nor its sources');
select is((select count(*)::int from public.dealer_imports where dealer_id = current_setting('dt.dealer_a')::bigint), 0, '... nor its imports');
select is((select count(*)::int from public.dealer_stock_items where dealer_id = current_setting('dt.dealer_a')::bigint), 0, '... nor its items');
select is((select count(*)::int from public.dealer_item_private), 0, '... nor its private data');
select is((select count(*)::int from public.dealer_leads where dealer_id = current_setting('dt.dealer_a')::bigint), 0, '... nor its leads');
select is((select count(*)::int from public.dealers), 1, '... B sees its own dealer');
select throws_ok($$select public.dealer_set_lead_status(current_setting('dt.lead_a')::bigint, 'lost')$$,
                 'P0001', 'lead_not_found', 'B cannot change A''s lead');
select throws_ok($$insert into public.dealers (name, locality_label, lat, lon) values ('Directa', 'Quilmes', 0, 0)$$,
                 '42501', null, 'no direct insert into dealers');
select throws_ok($$update public.dealer_stock_items set price = 1$$, '42501', null, 'no direct update of items');
reset role;

select is((select count(*)::int
             from unnest(array['dealers', 'dealer_members', 'dealer_sources', 'dealer_imports', 'dealer_stock_items',
                               'dealer_item_private', 'dealer_leads']) t,
                  unnest(array['insert', 'update', 'delete']) p
            where has_table_privilege('authenticated', 'public.' || t, p)), 0,
          'authenticated: no insert, update or delete on the seven tables');
select is((select count(*)::int
             from unnest(array['dealers', 'dealer_members', 'dealer_sources', 'dealer_imports', 'dealer_stock_items',
                               'dealer_item_private', 'dealer_leads']) t
            where has_table_privilege('anon', 'public.' || t, 'select')), 0, 'anon: no select on the seven tables');
select is((select count(*)::int from pg_class
            where oid in ('public.dealers'::regclass, 'public.dealer_members'::regclass, 'public.dealer_sources'::regclass,
                          'public.dealer_imports'::regclass, 'public.dealer_stock_items'::regclass,
                          'public.dealer_item_private'::regclass, 'public.dealer_leads'::regclass)
              and relrowsecurity), 7, 'RLS is enabled on the seven tables');
select is(has_column_privilege('authenticated', 'public.dealer_leads', 'buyer_user_id', 'select'), false,
          'dealer_leads.buyer_user_id is not readable by clients');
select is(has_column_privilege('authenticated', 'public.dealer_leads', 'notification_id', 'select'), false,
          '... nor notification_id');
select is(has_column_privilege('authenticated', 'public.dealer_leads', 'buyer_phone', 'select'), true,
          '... buyer_phone is (for the dealer, behind RLS)');

-- ================================================================ 9. dealer_sweep
insert into public.expired_search_matches (search_profile_id, listing_id, access_ended_at, level, diff_pct)
values (9853, 9802, '2026-11-01 12:00+00', 'good', 10);
set local session_replication_role = replica;
insert into public.notifications (user_id, listing_id, kind, channel, status, dedupe_key) values
  ('d1000000-0000-0000-0000-000000000001', 9803, 'new_match', 'email', 'queued', 'dt:sweep:9803'),
  ('d1000000-0000-0000-0000-000000000001', 9804, 'new_match', 'email', 'digest', 'dt:sweep:9804'),
  ('d1000000-0000-0000-0000-000000000002', 9803, 'new_match', 'email', 'sent', 'dt:sweep:9803:sent'),
  ('d1000000-0000-0000-0000-000000000001', 9801, 'new_match', 'email', 'queued', 'dt:sweep:9801'),
  ('d1000000-0000-0000-0000-000000000001', 9802, 'new_match', 'email', 'queued', 'dt:sweep:9802');
set local session_replication_role = origin;
do $d$ begin perform set_config('dt.m_hidden', (select count(*)::text from public.matches where listing_id in (9803, 9804, 9805, 9806)), true); end $d$;
do $d$ begin perform set_config('dt.e_hidden', (select count(*)::text from public.expired_search_matches where listing_id in (9803, 9804, 9805, 9806)), true); end $d$;
select is((select array[matches_deleted, notifications_skipped, expired_deleted] from public.dealer_sweep()),
          array[current_setting('dt.m_hidden')::int, 2, current_setting('dt.e_hidden')::int],
          'dealer_sweep: the hidden listings'' matches, queued/digest notifications and 2.5 rows');
select is((select count(*)::int from public.matches where listing_id in (9803, 9804, 9805, 9806)), 0, '... no match left on a hidden listing');
select is((select count(*)::int from public.expired_search_matches where listing_id in (9803, 9804, 9805, 9806)), 0,
          '... nor a 2.5 row');
select is((select array_agg(status::text || ':' || coalesce(error, '') order by dedupe_key collate "C") from public.notifications
            where dedupe_key like 'dt:sweep:%'),
          array['queued:', 'queued:', 'skipped:dealer_hidden', 'sent:', 'skipped:dealer_hidden'],
          '... the pending ones skipped, a sent one and the visible ones untouched');
select is((select count(*)::int from public.matches where listing_id in (9801, 9802, 9807, 9808)), 4,
          '... the common and the visible listings keep their matches');
select is((select count(*)::int from public.expired_search_matches where listing_id in (9801, 9802)), 3,
          '... and their 2.5 rows');
select is((select matched_at from public.dealer_stock_items where listing_id = 9803), null, '... the hidden item will be matched again');
select is((select array[matches_deleted, notifications_skipped, expired_deleted] from public.dealer_sweep()), array[0, 0, 0],
          'a second sweep has nothing to do');

-- ================================================================ 10. dealer_set_item_status and dealer_confirm_items
insert into public.expired_search_matches (search_profile_id, listing_id, access_ended_at, level, diff_pct)
values (9852, 9808, '2026-11-01 12:00+00', 'good', 10);
set local role authenticated;
set local request.jwt.claims = '{"sub": "d1000000-0000-0000-0000-00000000000a", "role": "authenticated"}';
select lives_ok($$select public.dealer_set_item_status(current_setting('dt.item_9808')::bigint, 'reserved')$$, 'reserve an item');
reset role;
select is((select dealer_status from public.listings where id = 9808), 'reserved', '... copied to the listing');
select is((select count(*)::int from public.matches where listing_id = 9808)
          + (select count(*)::int from public.expired_search_matches where listing_id = 9808), 0,
          '... its matches and 2.5 rows are gone at once');
insert into public.matches (search_profile_id, listing_id, score, level, score_breakdown, match_reasons, scoring_version)
values (9851, 9808, 80, 'good', '{}', '{}', 'test') on conflict do nothing;
update public.dealer_stock_items set matched_at = now() where listing_id = 9808;
set local role authenticated;
set local request.jwt.claims = '{"sub": "d1000000-0000-0000-0000-00000000000a", "role": "authenticated"}';
select lives_ok($$select public.dealer_set_item_status(current_setting('dt.item_9808')::bigint, 'available')$$, 'back to available');
reset role;
select is((select array[l.dealer_status, i.status, coalesce(i.matched_at::text, 'null')] from public.listings l
             join public.dealer_stock_items i on i.listing_id = l.id where l.id = 9808),
          array['available', 'available', 'null'], '... visible again, matched_at null so the worker matches it');
select is((select count(*)::int from public.matches where listing_id = 9808), 1, '... a visible car keeps its match');
set local role authenticated;
set local request.jwt.claims = '{"sub": "d1000000-0000-0000-0000-00000000000a", "role": "authenticated"}';
select lives_ok($$select public.dealer_set_item_status(current_setting('dt.item_9808')::bigint, 'sold')$$, 'sell it');
reset role;
select is((select array[dealer_status, (select count(*)::text from public.matches where listing_id = 9808)]
             from public.listings where id = 9808), array['sold', '0'], '... sold: copied and no match left');
set local role authenticated;
set local request.jwt.claims = '{"sub": "d1000000-0000-0000-0000-00000000000a", "role": "authenticated"}';
select lives_ok($$select public.dealer_set_item_status(current_setting('dt.item_9808')::bigint, 'archived')$$, 'archive it');
select throws_ok($$select public.dealer_set_item_status(current_setting('dt.item_9808')::bigint, 'perdido')$$,
                 'P0001', 'invalid_status', 'an unknown status: invalid_status');
select throws_ok($$select public.dealer_set_item_status(current_setting('dt.item_9807')::bigint, 'archived')$$,
                 'P0001', 'invalid_status', 'a synced item cannot be archived');
select lives_ok($$select public.dealer_set_item_status(current_setting('dt.item_9807')::bigint, 'reserved')$$,
                'a synced item can be reserved');
reset role;
select is((select dealer_status from public.listings where id = 9808), 'sold', 'archived -> sold on the listing');
select is((select count(*)::int from public.matches where listing_id = 9807), 0, 'the reserved synced listing lost its match');
select is(public.dealer_listing_hidden('directo', current_setting('dt.dealer_a')::bigint, 'available',
                                       (select dealer_confirmed_at from public.listings where id = 9804)),
          'unconfirmed', '9804 is unconfirmed before «Confirmar stock»');
set local role authenticated;
set local request.jwt.claims = '{"sub": "d1000000-0000-0000-0000-00000000000a", "role": "authenticated"}';
select is(public.dealer_confirm_items(array[current_setting('dt.item_9804')::bigint]), 1, 'dealer_confirm_items: one item');
select is((public.my_dealer()->'counts'->>'unconfirmed')::int, 0, 'my_dealer(): nothing left to confirm');
reset role;
select is((select array[(l.dealer_confirmed_at = now())::text, coalesce(i.matched_at::text, 'null')]
             from public.listings l join public.dealer_stock_items i on i.listing_id = l.id where l.id = 9804),
          array['true', 'null'], '... copied to the listing; it was expired, so it is matched again');
select is(public.dealer_listing_hidden('directo', current_setting('dt.dealer_a')::bigint, 'available',
                                       (select dealer_confirmed_at from public.listings where id = 9804)),
          null, '... and it passes the gate');

-- ================================================================ 11. dealer_market_ref
insert into public.listings (id, source, external_id, url, title, make, model, year, price, currency, price_usd,
                             status, price_partial, last_seen_at, attributes, dealer_id, dealer_status, dealer_confirmed_at)
overriding system value values
  (9871, 'mercadolibre', 'DT-9871', 'https://example.test/dt-9871', 'Mref', 'Pgdealer', 'Mref', 2016, 10000, 'USD', 10000, 'active', false, now(), '{}', null, null, null),
  (9872, 'kavak',        'DT-9872', 'https://example.test/dt-9872', 'Mref', 'Pgdealer', 'Mref', 2017, 12000, 'USD', 12000, 'active', false, now(), '{}', null, null, null),
  (9873, 'mercadolibre', 'DT-9873', 'https://example.test/dt-9873', 'Mref', 'Pgdealer', 'Mref', 2018, 14000, 'USD', 14000, 'active', false, now(), '{}', null, null, null),
  (9874, 'mercadolibre', 'DT-9874', 'https://example.test/dt-9874', 'Mref', 'Pgdealer', 'Mref', 2019, 99000, 'USD', 99000, 'active', false, now(), '{}', null, null, null),
  (9875, 'mercadolibre', 'DT-9875', 'https://example.test/dt-9875', 'Mref', 'Pgdealer', 'Mref', 2017, 99000, 'USD', 99000, 'active', false, now() - interval '31 days', '{}', null, null, null),
  (9876, 'mercadolibre', 'DT-9876', 'https://example.test/dt-9876', 'Mref', 'Pgdealer', 'Mref', 2017, 99000, 'USD', 99000, 'gone', false, now(), '{}', null, null, null),
  (9877, 'mercadolibre', 'DT-9877', 'https://example.test/dt-9877', 'Mref', 'Pgdealer', 'Mref', 2017, 99000, 'USD', 99000, 'active', true, now(), '{}', null, null, null),
  (9878, 'directo',      'DT-9878', 'https://example.test/dt-9878', 'Mref', 'Pgdealer', 'Mref', 2017, 99000, 'USD', 99000, 'active', false, now(), '{}',
   current_setting('dt.dealer_a')::bigint, 'available', now()),
  (9879, 'mercadolibre', 'DT-9879', 'https://example.test/dt-9879', 'Mref', 'Pgdealer', 'Mref', 2017, 99000, 'USD', 99000, 'active', false, now(), '{"_not_vehicle": true}', null, null, null),
  (9880, 'mercadolibre', 'DT-9880', 'https://example.test/dt-9880', 'Mref', 'Pgdealer', 'Mref', 2017, 99000, 'USD', 99000, 'active', false, now(), '{}', null, null, null);
select is(public.dealer_market_ref('pgdealer', 'MREF', 2017, 15000, 9880) - 'blue',
          '{"n": 3, "median": 12000, "p25": 11000, "p75": 13000, "vs_market_pct": 25.0, "enough": false,
            "year_tol": 1, "days": 30}'::jsonb,
          'dealer_market_ref: years -1/0/+1 of any portal source; not +2, 31 days old, gone, partial, directo, not a vehicle or the excluded one');
select is((public.dealer_market_ref('Pgdealer', 'Mref', 2017, 9000, 9880)->>'vs_market_pct')::numeric, -25.0,
          '... cheaper than the market is negative');
select is(public.dealer_market_ref('Pgdealer', 'Mref', 2017, 15000, 9880)->'blue', '1600'::jsonb, '... with the blue it used');
select is((public.dealer_market_ref('Pgdealer', 'Mref', 2017, 15000, null)->>'n')::int, 4, '... without exclusion, 4');
select is(public.dealer_market_ref('Pgdealer', 'Nada', 2017, 15000, null)->'vs_market_pct', 'null'::jsonb,
          '... no comparables: no percentage');

-- ================================================================ 12. dealer_demand and dealer_stock_insights
-- Car: Pgdealer Demand 2017, 20.000.000 ARS (12.500 USD at 1.600), 90.000 km, dealer A in Quilmes.
set local session_replication_role = replica;
insert into public.search_profiles (id, user_id, name, filters, enabled, origin_lat, origin_lon, radius_km, created_at)
overriding system value values
  -- V: in year, price and zone, active; and one with no filters and no zone, paused but recent.
  (9891, 'd1000000-0000-0000-0000-000000000002', 'd1', '{"make": "Pgdealer", "model": "Demand", "year_min": 2015, "year_max": 2019,
                                                       "price_max": 25000000, "currency": "ARS"}', true, -34.72, -58.25, 30, now()),
  (9892, 'd1000000-0000-0000-0000-000000000002', 'd2', '{"model": "demand"}', false, null, null, null, now()),
  -- W: out of year; private sellers only.
  (9893, 'd1000000-0000-0000-0000-000000000003', 'd3', '{"make": "Pgdealer", "model": "Demand", "year_min": 2019}', true, null, null, null, now()),
  (9894, 'd1000000-0000-0000-0000-000000000003', 'd4', '{"make": "Pgdealer", "model": "Demand", "seller_types": ["private"]}', true, null, null, null, now()),
  -- Y: fits in USD, far away; an old paused one; another make.
  (9895, 'd1000000-0000-0000-0000-000000000004', 'd5', '{"make": "Pgdealer", "model": "Demand", "price_max": 15000}', true, -31.42, -64.18, 50, now()),
  (9896, 'd1000000-0000-0000-0000-000000000004', 'd6', '{"make": "Pgdealer", "model": "Demand"}', false, null, null, null, now() - interval '100 days'),
  (9897, 'd1000000-0000-0000-0000-000000000004', 'd7', '{"make": "Otra", "model": "Demand"}', true, null, null, null, now()),
  -- The admin and the dealer's own member: never counted.
  (9898, 'd1000000-0000-0000-0000-00000000000f', 'd8', '{"make": "Pgdealer", "model": "Demand"}', true, null, null, null, now()),
  (9899, 'd1000000-0000-0000-0000-00000000000a', 'd9', '{"make": "Pgdealer", "model": "Demand"}', true, null, null, null, now());
set local session_replication_role = origin;

select is(public.dealer_demand('Pgdealer', 'Demand', 2017, 20000000, 'ARS', 90000, -34.72, -58.25,
                               array['d1000000-0000-0000-0000-00000000000a']::uuid[], 'directo'),
          '{"model": {"searches": 5, "people": 3}, "fits": {"searches": 3, "people": 2},
            "zone": {"searches": 2, "people": 1}, "active_zone": {"searches": 1, "people": 1}}'::jsonb,
          'dealer_demand: nested levels; out of year and private-only out of fits; no zone counts in zone; admins, members, old and other makes out');
select is(public.dealer_demand('Pgdealer', 'Demand', 2017, 20000000, 'ARS', 90000, null, null, '{}', 'directo')->'zone', 'null'::jsonb,
          '... no dealer location: zone is null');
select is(public.dealer_demand_level('{"searches": 4, "people": 2}', 3), '"few"'::jsonb, 'dealer_demand_level: 2 people, 4 searches -> few');
select is(public.dealer_demand_level('{"searches": 5, "people": 3}', 3), '5'::jsonb, '... 3 people -> the number of searches');
select is(public.dealer_demand_level('{"searches": 0, "people": 0}', 3), '0'::jsonb, '... none -> 0');
select is(public.dealer_demand_level('{"searches": 2, "people": 2}', 2), '"few"'::jsonb, '... a minimum under 3 is still 3');
select is(public.dealer_demand_level(null, 3), 'null'::jsonb, '... no level -> null');

set local role authenticated;
set local request.jwt.claims = '{"sub": "d1000000-0000-0000-0000-00000000000a", "role": "authenticated"}';
select lives_ok($$select public.dealer_upsert_item(null, '{"make": "Pgdealer", "model": "Demand", "year": 2017, "mileage_km": 90000,
                                                         "price": 20000000, "currency": "ARS"}')$$, 'an item of the demanded model');
select is((select demand from public.dealer_stock_insights() where model = 'Demand'),
          '{"approved": true, "window_days": 90, "min_count": 3,
            "levels": {"model": 5, "fits": "few", "zone": "few", "active_zone": "few"}}'::jsonb,
          'dealer_stock_insights: demand rounded in SQL (a number only with 3+ people)');
select is((select demand->'levels' from public.dealer_stock_insights() where model = 'Nadie'),
          '{"model": 0, "fits": 0, "zone": 0, "active_zone": 0}'::jsonb, '... a model nobody searches: 0');
select is((select array[hidden_reason, price_usd::text, (confirm_due_at = confirmed_at + interval '7 days')::text]
             from public.dealer_stock_insights() where model = 'Demand'),
          array['pending_sync', '12500.00', 'true'], '... without a listing: pending_sync; ARS / blue; due in 7 days');
select is((select hidden_reason from public.dealer_stock_insights() where listing_id = 9802), null,
          '... a visible directo: null (it is sent)');
select is((select hidden_reason from public.dealer_stock_insights() where listing_id = 9803), 'not_available',
          '... a reserved one: not_available');
select is((select count(*)::int from public.dealer_stock_insights() where listing_id = 9808), 0, '... archived items are left out');
select is((select market ? 'n' and market ? 'median' and model_days_to_sell ? 'n' from public.dealer_stock_insights() where listing_id = 9802),
          true, '... with the market reference and the days to sell');
select is((select days_in_stock from public.dealer_stock_insights() where model = 'Nadie'),
          ((now() at time zone 'America/Argentina/Buenos_Aires')::date - date '2026-10-01')::int,
          '... days in stock from in_stock_since');
reset role;

set local role authenticated;
set local request.jwt.claims = '{"sub": "d1000000-0000-0000-0000-00000000000b", "role": "authenticated"}';
select is((select demand from public.dealer_stock_insights() where model = 'Demand'), '{"approved": false}'::jsonb,
          'an unapproved dealer sees no demand');
reset role;

set local role authenticated;
set local request.jwt.claims = '{"sub": "d1000000-0000-0000-0000-000000000001", "role": "authenticated"}';
select throws_ok($$select * from public.dealer_stock_insights()$$, 'P0001', 'not_member',
                 'dealer_stock_insights for someone without a dealer: not_member');
reset role;

set local session_replication_role = replica;
insert into public.search_profiles (id, user_id, name, filters, enabled, created_at) overriding system value values
  -- V only wants Mercado Libre; W wrote an invalid seller type (no filter, as matching reads it).
  (9900, 'd1000000-0000-0000-0000-000000000002', 'd10', '{"make": "Pgdealer", "model": "Demand", "sources": ["mercadolibre"]}', true, now()),
  (9901, 'd1000000-0000-0000-0000-000000000003', 'd11', '{"model": "Demand", "seller_types": ["foo"]}', true, now());
set local session_replication_role = origin;
select is((public.dealer_demand('Pgdealer', 'Demand', 2017, 20000000, 'ARS', 90000, null, null,
                               array['d1000000-0000-0000-0000-00000000000a']::uuid[], 'directo')
             -> 'fits' ->> 'searches')::int, 4,
          'dealer_demand: a search limited to other sources does not fit a directo car; an invalid seller type is no filter');
select is((public.dealer_demand('Pgdealer', 'Demand', 2017, 20000000, 'ARS', 90000, null, null,
                               array['d1000000-0000-0000-0000-00000000000a']::uuid[], 'mercadolibre')
             -> 'fits' ->> 'searches')::int, 5,
          '... and it fits a car of that source');

set local role authenticated;
set local request.jwt.claims = '{"sub": "d1000000-0000-0000-0000-00000000000a", "role": "authenticated"}';
select lives_ok($$select public.update_my_dealer('TT Autos', 'Quilmes', -34.72, -58.25, '1199998888', '5491122334455',
                                                 'tt@ejemplo.test')$$, 'update_my_dealer: a new phone');
select is((public.my_dealer()->>'approved')::boolean, true, '... keeps the approval');
select lives_ok($$select public.update_my_dealer('TT Autos', 'Quilmes', -34.60, -58.38, '1199998888', '5491122334455',
                                                 'tt@ejemplo.test')$$, 'update_my_dealer: a new place');
select is((public.my_dealer()->>'approved')::boolean, false, '... goes back to review');
select is((select demand from public.dealer_stock_insights() where model = 'Demand'), '{"approved": false}'::jsonb,
          '... and its demand by zone is hidden until Juan approves it again');
reset role;
update public.dealers set approved_at = now() where id = current_setting('dt.dealer_a')::bigint;
set local role authenticated;
set local request.jwt.claims = '{"sub": "d1000000-0000-0000-0000-00000000000a", "role": "authenticated"}';
select lives_ok($$select public.update_my_dealer('TT Motors', 'Quilmes', -34.60, -58.38, '1199998888', '5491122334455',
                                                 'tt@ejemplo.test')$$, 'update_my_dealer: a new name');
select is((public.my_dealer()->>'approved')::boolean, false, '... goes back to review too');
reset role;

update public.app_config set value = '{"enabled": false, "channel_enabled": true, "manual_confirm_days": 7, "demand_min_count": 3}'
 where key = 'dealer_program';
set local role authenticated;
set local request.jwt.claims = '{"sub": "d1000000-0000-0000-0000-00000000000a", "role": "authenticated"}';
select throws_ok($$select * from public.dealer_stock_insights()$$, 'P0001', 'dealer_program_off',
                 'with enabled=false the panel RPCs answer dealer_program_off');
select is(public.dealer_listing_hidden('directo', current_setting('dt.dealer_a')::bigint, 'available', now()), 'channel_off',
          '... and channel_enabled alone does not open the channel');
reset role;

-- ================================================================ admin candidates
update public.listings set seller_key = 'ttautos', seller_name = 'TT AUTOS' where id in (9806, 9807);
select is((select array[seller_key, seller_name, active::text] from public.admin_dealer_seller_candidates('mercadolibre', 'tt')),
          array['ttautos', 'TT AUTOS', '2'], 'admin_dealer_seller_candidates: by key or name, grouped');
select is((select count(*)::int from public.admin_dealer_seller_candidates('mercadolibre', '%')), 0,
          '... a hint of one wildcard finds nothing');

select * from finish();
rollback;

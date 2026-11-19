-- Agencias, fase 1 (migration 20261229120000_dealer_phase1_extras.sql): the new switches, the
-- agency's alerts (preference, state, scan) and the stock read from a photo or a PDF (cap, type,
-- size, the queue's policy). Run after dealers_test.sql's migration, on a cloned database
-- (docs/superpowers/specs/2026-11-18-agencias-design.md §7.1). One transaction, rolled back.
begin;
create extension if not exists pgtap with schema extensions;
select no_plan();

insert into auth.users (instance_id, id, aud, role, email, created_at, updated_at) values
  ('00000000-0000-0000-0000-000000000000', 'f1000000-0000-0000-0000-00000000000a', 'authenticated', 'authenticated', 'a@phase1.test', now(), now()),
  ('00000000-0000-0000-0000-000000000000', 'f1000000-0000-0000-0000-00000000000b', 'authenticated', 'authenticated', 'b@phase1.test', now(), now()),
  ('00000000-0000-0000-0000-000000000000', 'f1000000-0000-0000-0000-000000000001', 'authenticated', 'authenticated', 'u@phase1.test', now(), now());

-- ================================================================ 1. switches
select is((select value -> 'alerts_enabled' from public.app_config where key = 'dealer_program'), 'false'::jsonb,
          'app_config.dealer_program gets alerts_enabled false');
select is((select value -> 'photo_import_enabled' from public.app_config where key = 'dealer_program'), 'false'::jsonb,
          'app_config.dealer_program gets photo_import_enabled false');
select is(public.dealer_program() - array['enabled', 'channel_enabled', 'manual_confirm_days', 'demand_min_count'],
          '{"alerts_enabled": false, "alerts_every_hours": 24, "photo_import_enabled": false, "photo_import_daily_limit": 5}'::jsonb,
          'dealer_program(): the phase 1 defaults');

update public.app_config set value = '{"alerts_every_hours": 5, "photo_import_daily_limit": 0}' where key = 'dealer_program';
select is(public.dealer_program() -> 'alerts_every_hours', '24'::jsonb, 'alerts_every_hours 5 -> 24');
select is(public.dealer_program() -> 'photo_import_daily_limit', '5'::jsonb, 'photo_import_daily_limit 0 -> 5');
update public.app_config set value = '{"alerts_every_hours": 169, "photo_import_daily_limit": 51}' where key = 'dealer_program';
select is(public.dealer_program() -> 'alerts_every_hours', '24'::jsonb, 'alerts_every_hours 169 -> 24');
select is(public.dealer_program() -> 'photo_import_daily_limit', '5'::jsonb, 'photo_import_daily_limit 51 -> 5');
update public.app_config set value = '{"alerts_every_hours": 6, "photo_import_daily_limit": 50, "alerts_enabled": true, "photo_import_enabled": true}' where key = 'dealer_program';
select is(public.dealer_program() - array['enabled', 'channel_enabled', 'manual_confirm_days', 'demand_min_count'],
          '{"alerts_enabled": true, "alerts_every_hours": 6, "photo_import_enabled": true, "photo_import_daily_limit": 50}'::jsonb,
          'the edges stay');
update public.app_config set value = '{"alerts_enabled": "true", "photo_import_enabled": 1, "alerts_every_hours": 12.5}' where key = 'dealer_program';
select is(public.dealer_program() - array['enabled', 'channel_enabled', 'manual_confirm_days', 'demand_min_count'],
          '{"alerts_enabled": false, "alerts_every_hours": 24, "photo_import_enabled": false, "photo_import_daily_limit": 5}'::jsonb,
          'switches that are not booleans and fractions -> defaults');

-- ================================================================ 2. permissions of the new objects
select is(has_table_privilege('authenticated', 'public.dealer_alerts', 'select'), false, 'dealer_alerts: no client read');
select is(has_table_privilege('authenticated', 'public.dealer_alert_state', 'select'), false, 'dealer_alert_state: no client read');
select is(has_table_privilege('authenticated', 'public.dealer_stock_reads', 'select'), false, 'dealer_stock_reads: no client read');
select is(has_table_privilege('authenticated', 'public.dealer_stock_reads', 'insert'), false, 'dealer_stock_reads: no client insert');
select is((select bool_and(relrowsecurity) from pg_class
            where oid in ('public.dealer_alerts'::regclass, 'public.dealer_alert_state'::regclass,
                          'public.dealer_stock_reads'::regclass)), true, 'RLS on the three new tables');
select is(has_function_privilege('authenticated', 'public.dealer_alert_scan(bigint, numeric, numeric)', 'execute'), false,
          'dealer_alert_scan: service role only');
select is(has_function_privilege('anon', 'public.dealer_request_stock_read(text, text, text)', 'execute'), false,
          'dealer_request_stock_read: not anon');
select is(has_function_privilege('anon', 'public.dealer_set_alerts(boolean)', 'execute'), false, 'dealer_set_alerts: not anon');

-- ================================================================ 3. fixtures: two dealers, A approved
update public.app_config set value = '{"enabled": true, "channel_enabled": false}' where key = 'dealer_program';
set local role authenticated;
set local request.jwt.claims = '{"sub": "f1000000-0000-0000-0000-00000000000a", "role": "authenticated"}';
select set_config('p1.dealer_a', public.create_dealer('Fase Uno Autos', 'Quilmes', -34.72, -58.25)::text, true);
select set_config('p1.item_a', public.dealer_upsert_item(null, '{"make": "Pgfase", "model": "Corolla", "year": 2019, "price": 20000, "currency": "USD", "mileage_km": 60000}')::text, true);
select set_config('p1.item_r', public.dealer_upsert_item(null, '{"make": "Pgfase", "model": "Corolla", "year": 2019, "price": 18000, "currency": "USD"}')::text, true);
select public.dealer_set_item_status(current_setting('p1.item_r')::bigint, 'reserved');
set local request.jwt.claims = '{"sub": "f1000000-0000-0000-0000-00000000000b", "role": "authenticated"}';
select set_config('p1.dealer_b', public.create_dealer('Otra Fase', 'Rosario', -32.95, -60.65)::text, true);
reset role;
update public.dealers set approved_at = now() where id = current_setting('p1.dealer_a')::bigint;

-- ================================================================ 4. the agency's preference
select is((select alerts_email from public.dealers where id = current_setting('p1.dealer_a')::bigint), true,
          'alerts_email is on by default (the general switch decides)');
set local role authenticated;
set local request.jwt.claims = '{"sub": "f1000000-0000-0000-0000-00000000000a", "role": "authenticated"}';
select lives_ok($$select public.dealer_set_alerts(false)$$, 'a member turns its alerts off');
select is((select alerts_email from public.dealers where id = current_setting('p1.dealer_a')::bigint), false,
          '... and reads it back (RLS: members read their dealer)');
select throws_ok($$select public.dealer_set_alerts(null)$$, 'P0001', 'invalid_dealer:alerts_email', 'null is not a preference');
select lives_ok($$select public.dealer_set_alerts(true)$$, 'and on again');
set local request.jwt.claims = '{"sub": "f1000000-0000-0000-0000-000000000001", "role": "authenticated"}';
select throws_ok($$select public.dealer_set_alerts(false)$$, 'P0001', 'not_member', 'a buyer has no dealer');
reset role;
select is((select alerts_email from public.dealers where id = current_setting('p1.dealer_b')::bigint), true,
          'B''s preference untouched');

-- ================================================================ 5. dealer_alert_scan
-- The market pool: 6 Pgfase Corolla 2018-2020 near Quilmes at USD 19-23k; plus the candidates.
insert into public.listings (id, source, external_id, url, title, make, model, year, price, currency, price_usd,
                             mileage_km, lat, lon, first_seen_at, last_seen_at)
overriding system value
select 9900 + g, 'mercadolibre', 'P1-' || g, 'https://example.test/p1-' || g, 'Pgfase Corolla', 'Pgfase', 'Corolla',
       2018 + (g % 3), 19000 + g * 500, 'USD', 19000 + g * 500, 70000, -34.73, -58.26, now() - interval '20 days', now()
  from generate_series(1, 6) g;
-- No state yet: nothing counts as new.
insert into public.listings (id, source, external_id, url, title, make, model, year, price, currency, price_usd,
                             mileage_km, lat, lon, first_seen_at, last_seen_at)
overriding system value values
  (9911, 'kavak', 'P1-11', 'https://example.test/p1-11', 'Pgfase Corolla barato', 'Pgfase', 'Corolla', 2019,
   17000, 'USD', 17000, 65000, -34.70, -58.27, now() - interval '1 hour', now());

select is((select s.cheaper from public.dealer_alert_scan(current_setting('p1.dealer_a')::bigint) s
            where s.item_id = current_setting('p1.item_a')::bigint), null,
          'scan: without a saved state no look-alike is new');
select is((select count(*)::integer from public.dealer_alert_scan(current_setting('p1.dealer_a')::bigint)), 1,
          'scan: only the available car (not the reserved one)');
select is((select (s.market ->> 'n')::integer from public.dealer_alert_scan(current_setting('p1.dealer_a')::bigint) s), 7,
          'scan: the market reference of dealer_market_ref (6 + the cheap one)');
select is((select jsonb_typeof(s.demand) from public.dealer_alert_scan(current_setting('p1.dealer_a')::bigint) s), 'object',
          'scan: raw demand in the zone for an approved dealer');
select is((select s.demand ->> 'people' from public.dealer_alert_scan(current_setting('p1.dealer_a')::bigint) s), '0',
          '... with nobody searching it');
select is((select s.days_in_stock from public.dealer_alert_scan(current_setting('p1.dealer_a')::bigint) s), 0,
          'scan: days in stock');

insert into public.dealer_alert_state (item_id, cheaper_since)
values (current_setting('p1.item_a')::bigint, now() - interval '2 hours');
-- More candidates: far, barely cheaper, seen before the state, with many more km, another dealer's own.
insert into public.listings (id, source, external_id, url, title, make, model, year, price, currency, price_usd,
                             mileage_km, lat, lon, first_seen_at, last_seen_at, status)
overriding system value values
  (9912, 'kavak', 'P1-12', 'https://example.test/p1-12', 'lejos', 'Pgfase', 'Corolla', 2019, 15000, 'USD', 15000,
   60000, -32.95, -60.65, now() - interval '1 hour', now(), 'active'),
  (9913, 'kavak', 'P1-13', 'https://example.test/p1-13', 'apenas', 'Pgfase', 'Corolla', 2019, 19000, 'USD', 19000,
   60000, -34.71, -58.25, now() - interval '1 hour', now(), 'active'),
  (9914, 'kavak', 'P1-14', 'https://example.test/p1-14', 'viejo', 'Pgfase', 'Corolla', 2019, 14000, 'USD', 14000,
   60000, -34.71, -58.25, now() - interval '3 hours', now(), 'active'),
  (9915, 'kavak', 'P1-15', 'https://example.test/p1-15', 'muchos km', 'Pgfase', 'Corolla', 2019, 14500, 'USD', 14500,
   200000, -34.71, -58.25, now() - interval '1 hour', now(), 'active'),
  (9916, 'kavak', 'P1-16', 'https://example.test/p1-16', 'terminado', 'Pgfase', 'Corolla', 2019, 14200, 'USD', 14200,
   60000, -34.71, -58.25, now() - interval '1 hour', now(), 'gone');

select is((select s.cheaper ->> 'listing_id' from public.dealer_alert_scan(current_setting('p1.dealer_a')::bigint) s), '9911',
          'scan: the cheapest new look-alike within 30 km, ≥ 8 % cheaper, similar km, active');
select is((select (s.cheaper ->> 'distance_km')::integer < 30 from public.dealer_alert_scan(current_setting('p1.dealer_a')::bigint) s), true,
          '... with its distance');
select is((select s.cheaper ->> 'listing_id' from public.dealer_alert_scan(current_setting('p1.dealer_a')::bigint, 8, 500) s), '9912',
          'scan: with a 500 km radius the far one (cheaper) wins');
select is((select s.cheaper ->> 'listing_id' from public.dealer_alert_scan(current_setting('p1.dealer_a')::bigint, 20) s), null,
          'scan: none is 20 % cheaper among the new near ones');
select is((select s.state ->> 'cheaper_since' is not null from public.dealer_alert_scan(current_setting('p1.dealer_a')::bigint) s), true,
          'scan: the saved state comes along');
update public.dealers set approved_at = null where id = current_setting('p1.dealer_a')::bigint;
select is((select s.demand from public.dealer_alert_scan(current_setting('p1.dealer_a')::bigint) s), null,
          'scan: no demand for a dealer not approved');
update public.dealers set approved_at = now() where id = current_setting('p1.dealer_a')::bigint;
select is((select count(*)::integer from public.dealer_alert_scan(-1)), 0, 'scan: an unknown dealer gives nothing');

-- dealer_alerts: each alert once per dealer.
insert into public.dealer_alerts (dealer_id, item_id, kind, dedup_key)
values (current_setting('p1.dealer_a')::bigint, current_setting('p1.item_a')::bigint, 'slow', 'slow:x');
select throws_ok($$insert into public.dealer_alerts (dealer_id, item_id, kind, dedup_key)
                   values (current_setting('p1.dealer_a')::bigint, current_setting('p1.item_a')::bigint, 'slow', 'slow:x')$$,
                 '23505', null, 'dealer_alerts: the same dedup_key twice is refused');
select throws_ok($$insert into public.dealer_alerts (dealer_id, item_id, kind, dedup_key)
                   values (current_setting('p1.dealer_a')::bigint, null, 'bajó', 'x:y')$$,
                 '23514', null, 'dealer_alerts: unknown kinds are refused');

-- ================================================================ 6. stock read from a photo or a PDF
set local role authenticated;
set local request.jwt.claims = '{"sub": "f1000000-0000-0000-0000-00000000000a", "role": "authenticated"}';
select throws_ok($$select public.dealer_request_stock_read(encode('hola'::bytea, 'base64'), 'image/jpeg', 'lista.jpg')$$,
                 'P0001', 'photo_import_off', 'request: off by default');
reset role;
update public.app_config set value = '{"enabled": true, "photo_import_enabled": true, "photo_import_daily_limit": 2}' where key = 'dealer_program';
set local role authenticated;
set local request.jwt.claims = '{"sub": "f1000000-0000-0000-0000-00000000000a", "role": "authenticated"}';
select throws_ok($$select public.dealer_request_stock_read(encode('hola'::bytea, 'base64'), 'image/gif', 'x.gif')$$,
                 'P0001', 'invalid_file:type', 'request: only jpeg, png, webp or pdf');
select throws_ok($$select public.dealer_request_stock_read('%%% no es base64 %%%', 'image/jpeg', 'x.jpg')$$,
                 'P0001', 'invalid_file:data', 'request: data that is not base64');
select throws_ok($$select public.dealer_request_stock_read('', 'image/jpeg', 'x.jpg')$$,
                 'P0001', 'invalid_file:data', 'request: empty data');
select throws_ok($$select public.dealer_request_stock_read(repeat('A', 5600004), 'application/pdf', 'x.pdf')$$,
                 'P0001', 'file_too_big', 'request: more than 4 MB');
select set_config('p1.job1', public.dealer_request_stock_read(encode('foto de la lista'::bytea, 'base64'), 'image/jpeg', 'lista.jpg')::text, true);
select is((select kind || ':' || status from public.llm_jobs where id = current_setting('p1.job1')::bigint),
          'dealer_stock_read:queued', 'request: a queued job the user reads (RLS: own jobs)');
select is((select (input ->> 'dealer_id')::bigint from public.llm_jobs where id = current_setting('p1.job1')::bigint),
          current_setting('p1.dealer_a')::bigint, '... for my dealer');
select lives_ok($$select public.dealer_request_stock_read(encode('%PDF-1.4'::bytea, 'base64'), 'application/pdf', 'lista.pdf')$$,
                'request: a PDF');
select throws_ok($$select public.dealer_request_stock_read(encode('otra'::bytea, 'base64'), 'image/png', 'x.png')$$,
                 'P0001', 'photo_import_limit', 'request: the daily cap per dealer (2)');
select throws_ok($$insert into public.llm_jobs (user_id, kind, input)
                   values ('f1000000-0000-0000-0000-00000000000a', 'dealer_stock_read', '{"read_id": 1, "dealer_id": 1}')$$,
                 '42501', null, 'llm_jobs: the client cannot queue a stock read directly (no cap)');
select lives_ok($$insert into public.llm_jobs (user_id, kind, input)
                  values ('f1000000-0000-0000-0000-00000000000a', 'parse_search', '{"text": "un corolla 2019"}')$$,
                'llm_jobs: the assisted mode still queues as before');
set local request.jwt.claims = '{"sub": "f1000000-0000-0000-0000-00000000000b", "role": "authenticated"}';
select lives_ok($$select public.dealer_request_stock_read(encode('foto'::bytea, 'base64'), 'image/webp', 'b.webp')$$,
                'request: the cap is per dealer (B still has its own)');
set local request.jwt.claims = '{"sub": "f1000000-0000-0000-0000-000000000001", "role": "authenticated"}';
select throws_ok($$select public.dealer_request_stock_read(encode('foto'::bytea, 'base64'), 'image/jpeg', 'x.jpg')$$,
                 'P0001', 'not_member', 'request: a buyer has no dealer');
reset role;
select is((select array[bytes::text, media_type, filename, (data = 'foto de la lista'::bytea)::text]
             from public.dealer_stock_reads where job_id = current_setting('p1.job1')::bigint),
          array['16', 'image/jpeg', 'lista.jpg', 'true'], 'the file is stored for the worker, linked to its job');
select is((select count(*)::integer from public.dealer_stock_reads where dealer_id = current_setting('p1.dealer_a')::bigint), 2,
          'two reads for A (the refused ones left nothing)');
select throws_ok($$insert into public.llm_jobs (user_id, kind, input)
                   values ('f1000000-0000-0000-0000-00000000000a', 'dealer_stock_read', '{"read_id": "x"}')$$,
                 '23514', null, 'llm_jobs: a stock read needs read_id and dealer_id');

-- ================================================================ 7. import kinds
set local role authenticated;
set local request.jwt.claims = '{"sub": "f1000000-0000-0000-0000-00000000000a", "role": "authenticated"}';
select is((public.dealer_import_items('[{"make": "Pgfase", "model": "Corolla", "year": 2019, "price": 20000, "currency": "USD"}]',
                                       'lista.jpg', 'photo') ->> 'imported')::integer, 1, 'import: kind photo');
select is((public.dealer_import_items('[{"make": "Pgfase", "model": "Corolla", "year": 2019, "price": 20000, "currency": "USD"}]',
                                       'lista.pdf', 'pdf') ->> 'imported')::integer, 1, 'import: kind pdf');
select throws_ok($$select public.dealer_import_items('[]', 'x', 'jpeg')$$, 'P0001', 'invalid_item:kind', 'import: other kinds refused');
select is((select array_agg(kind order by kind) from public.dealer_imports where dealer_id = current_setting('p1.dealer_a')::bigint),
          array['pdf', 'photo'], 'the imports say where they came from');
reset role;

select * from finish();
rollback;

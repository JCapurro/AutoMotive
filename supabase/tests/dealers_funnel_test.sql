-- Agencias, fase 2: el embudo del canal de venta (migration 20261230120000_dealer_funnel.sql).
-- Needs 20261228120000_dealer_program.sql. Run on a cloned database (spec §7.1); one transaction, rolled back.
begin;
create extension if not exists pgtap with schema extensions;
select no_plan();

-- guard_match_access / the free quota would drop the fixtures' matches.
update public.app_config set value = jsonb_set(value, '{enforced}', 'false') where key = 'plan_limits';
update public.app_config set value = '{"enabled": true, "channel_enabled": true, "manual_confirm_days": 7, "demand_min_count": 3}'
 where key = 'dealer_program';

-- ---------------------------------------------------------------- users
-- A owns «Funnel A», B owns «Funnel B», C owns «Funnel C» (nothing sent); U/V/W/Y buyers; X admin.
insert into auth.users (instance_id, id, aud, role, email, created_at, updated_at) values
  ('00000000-0000-0000-0000-000000000000', 'f1000000-0000-0000-0000-00000000000a', 'authenticated', 'authenticated', 'a@funnel.test', now(), now()),
  ('00000000-0000-0000-0000-000000000000', 'f1000000-0000-0000-0000-00000000000b', 'authenticated', 'authenticated', 'b@funnel.test', now(), now()),
  ('00000000-0000-0000-0000-000000000000', 'f1000000-0000-0000-0000-00000000000c', 'authenticated', 'authenticated', 'c@funnel.test', now(), now()),
  ('00000000-0000-0000-0000-000000000000', 'f1000000-0000-0000-0000-000000000001', 'authenticated', 'authenticated', 'u@funnel.test', now(), now()),
  ('00000000-0000-0000-0000-000000000000', 'f1000000-0000-0000-0000-000000000002', 'authenticated', 'authenticated', 'v@funnel.test', now(), now()),
  ('00000000-0000-0000-0000-000000000000', 'f1000000-0000-0000-0000-000000000003', 'authenticated', 'authenticated', 'w@funnel.test', now(), now()),
  ('00000000-0000-0000-0000-000000000000', 'f1000000-0000-0000-0000-000000000004', 'authenticated', 'authenticated', 'y@funnel.test', now(), now()),
  ('00000000-0000-0000-0000-000000000000', 'f1000000-0000-0000-0000-00000000000f', 'authenticated', 'authenticated', 'x@funnel.test', now(), now());
update public.profiles set role = 'admin' where id = 'f1000000-0000-0000-0000-00000000000f';

insert into public.dealers (id, name, locality_label, lat, lon, approved_at, created_at) overriding system value values
  (9901, 'Funnel A', 'Quilmes', -34.72, -58.25, now(), now() - interval '60 days'),
  (9902, 'Funnel B', 'Berazategui', -34.76, -58.21, now(), now() - interval '50 days'),
  (9903, 'Funnel C', 'Lanús', -34.70, -58.39, null, now() - interval '40 days');
insert into public.dealer_members (dealer_id, user_id) values
  (9901, 'f1000000-0000-0000-0000-00000000000a'),
  (9902, 'f1000000-0000-0000-0000-00000000000b'),
  (9903, 'f1000000-0000-0000-0000-00000000000c');

-- ---------------------------------------------------------------- permissions
select is(has_function_privilege('authenticated', 'public.admin_dealer_funnel(timestamptz,timestamptz)', 'execute')
          or has_function_privilege('anon', 'public.admin_dealer_funnel(timestamptz,timestamptz)', 'execute'),
          false, 'admin_dealer_funnel: not for anon or authenticated');
select is(has_function_privilege('authenticated', 'public.dealer_funnel(timestamptz,timestamptz,bigint)', 'execute'),
          false, 'dealer_funnel (raw): not for authenticated');
select ok(has_function_privilege('service_role', 'public.admin_dealer_funnel(timestamptz,timestamptz)', 'execute'),
          'admin_dealer_funnel: service role may execute (the admin page, after requireAdmin)');
select ok(has_function_privilege('authenticated', 'public.my_dealer_reach()', 'execute')
          and not has_function_privilege('anon', 'public.my_dealer_reach()', 'execute'),
          'my_dealer_reach: authenticated, not anon');
select ok(has_function_privilege('authenticated', 'public.dealer_declare_sale(bigint,bigint,boolean)', 'execute')
          and not has_function_privilege('anon', 'public.dealer_declare_sale(bigint,bigint,boolean)', 'execute'),
          'dealer_declare_sale: authenticated, not anon');
select is(has_table_privilege('authenticated', 'public.dealer_match_log', 'select'), false,
          'dealer_match_log: closed to clients');
select is(has_table_privilege('authenticated', 'public.dealer_sales', 'insert')
          or has_table_privilege('authenticated', 'public.dealer_sales', 'update')
          or has_table_privilege('authenticated', 'public.dealer_sales', 'delete'), false,
          'dealer_sales: clients only read (writes through dealer_declare_sale)');

set local role authenticated;
set local request.jwt.claims = '{"sub": "f1000000-0000-0000-0000-00000000000f", "role": "authenticated"}';
select throws_ok($$select public.admin_dealer_funnel(now() - interval '30 days', now())$$, '42501', null,
                 'even an admin account cannot call admin_dealer_funnel with its session');
select throws_ok($$select public.dealer_funnel(now() - interval '30 days', now(), 9901)$$, '42501', null,
                 '... nor the raw dealer_funnel');
select throws_ok($$select public.my_dealer_reach()$$, 'P0001', 'not_member', 'my_dealer_reach without an agency: not_member');
select throws_ok($$select count(*) from public.dealer_match_log$$, '42501', null, 'no client reads dealer_match_log');
reset role;

-- ---------------------------------------------------------------- stock
-- 9911/9912 directo of A (visible), 9913 a common listing, 9914 directo of B, 9915 directo of A (sold later).
insert into public.listings (id, source, external_id, url, title, make, model, year, price, currency, price_usd,
                             dealer_id, dealer_status, dealer_confirmed_at)
overriding system value values
  (9911, 'directo', 'FN-9911', 'https://example.test/fn-9911', 'Pgfunnel Focus', 'Pgfunnel', 'Focus', 2017, 16000, 'USD', 16000, 9901, 'available', now()),
  (9912, 'directo', 'FN-9912', 'https://example.test/fn-9912', 'Pgfunnel Etios', 'Pgfunnel', 'Etios', 2019, 12000, 'USD', 12000, 9901, 'available', now()),
  (9913, 'mercadolibre', 'FN-9913', 'https://example.test/fn-9913', 'Pgfunnel Focus común', 'Pgfunnel', 'Focus', 2017, 15000, 'USD', 15000, null, null, null),
  (9914, 'directo', 'FN-9914', 'https://example.test/fn-9914', 'Pgfunnel Gol', 'Pgfunnel', 'Gol', 2015, 7000, 'USD', 7000, 9902, 'available', now()),
  (9915, 'directo', 'FN-9915', 'https://example.test/fn-9915', 'Pgfunnel Corolla', 'Pgfunnel', 'Corolla', 2018, 18000, 'USD', 18000, 9901, 'available', now());
insert into public.dealer_stock_items (id, dealer_id, origin, listing_id, make, model, year, price, currency, status,
                                       confirmed_at, sync_state, matched_at, created_at)
overriding system value values
  (99011, 9901, 'manual', 9911, 'Pgfunnel', 'Focus', 2017, 16000, 'USD', 'available', now(), 'synced', now(), now() - interval '10 days'),
  (99012, 9901, 'manual', 9912, 'Pgfunnel', 'Etios', 2019, 12000, 'USD', 'available', now(), 'synced', now(), now() - interval '10 days'),
  (99013, 9901, 'manual', null, 'Pgfunnel', 'Ka', 2016, 6000, 'USD', 'available', now(), 'pending', null, now() - interval '2 days'),
  (99014, 9901, 'manual', null, 'Pgfunnel', 'Fiesta', 2014, 5000, 'USD', 'archived', now(), 'pending', null, now() - interval '45 days'),
  (99015, 9901, 'manual', 9915, 'Pgfunnel', 'Corolla', 2018, 18000, 'USD', 'available', now(), 'synced', now(), now() - interval '5 days'),
  (99021, 9902, 'manual', 9914, 'Pgfunnel', 'Gol', 2015, 7000, 'USD', 'available', now(), 'synced', now(), now() - interval '10 days');

-- ---------------------------------------------------------------- matches -> dealer_match_log
set local session_replication_role = replica;
insert into public.search_profiles (id, user_id, name, filters, enabled) overriding system value values
  (99051, 'f1000000-0000-0000-0000-000000000001', 'Focus U', '{"make": "Pgfunnel", "model": "Focus"}', true),
  (99052, 'f1000000-0000-0000-0000-000000000002', 'Focus V', '{"make": "Pgfunnel", "model": "Focus"}', true),
  (99053, 'f1000000-0000-0000-0000-000000000003', 'Etios W', '{"make": "Pgfunnel", "model": "Etios"}', true),
  (99054, 'f1000000-0000-0000-0000-00000000000f', 'Focus X (admin)', '{"make": "Pgfunnel", "model": "Focus"}', true),
  (99055, 'f1000000-0000-0000-0000-00000000000a', 'Focus A (own agency)', '{"make": "Pgfunnel", "model": "Focus"}', true);
set local session_replication_role = origin;

insert into public.matches (search_profile_id, listing_id, score, level, score_breakdown, match_reasons, scoring_version)
values (99051, 9911, 80, 'high', '{}', '{}', 'test'), (99052, 9911, 70, 'good', '{}', '{}', 'test'),
       (99053, 9912, 75, 'good', '{}', '{}', 'test'), (99054, 9911, 80, 'high', '{}', '{}', 'test'),
       (99055, 9911, 80, 'high', '{}', '{}', 'test'),
       (99051, 9913, 60, 'good', '{}', '{}', 'test');

select is((select count(*)::int from public.dealer_match_log where listing_id in (9911, 9912)), 5,
          'dealer_match_log: one row per dealer car and search matched');
select is((select count(*)::int from public.dealer_match_log where listing_id = 9913), 0,
          '... and none for a common listing');
select is((select array[dealer_id::text, user_id::text] from public.dealer_match_log
            where listing_id = 9912 and search_profile_id = 99053),
          array['9901', 'f1000000-0000-0000-0000-000000000003'], '... with the dealer and the search owner');

update public.dealer_match_log set first_matched_at = now() - interval '40 days'
 where listing_id = 9911 and search_profile_id = 99052;
insert into public.matches (search_profile_id, listing_id, score, level, score_breakdown, match_reasons, scoring_version)
values (99052, 9911, 90, 'high', '{}', '{}', 'test')
on conflict (search_profile_id, listing_id) do update set score = excluded.score;
delete from public.matches where listing_id = 9911 and search_profile_id = 99052;
insert into public.matches (search_profile_id, listing_id, score, level, score_breakdown, match_reasons, scoring_version)
values (99052, 9911, 90, 'high', '{}', '{}', 'test');
select ok((select first_matched_at < now() - interval '39 days' from public.dealer_match_log
            where listing_id = 9911 and search_profile_id = 99052),
          'an upsert or a re-match after a hide keeps the first time');
update public.dealer_match_log set first_matched_at = now() - interval '1 day'
 where listing_id = 9911 and search_profile_id = 99052;

-- ---------------------------------------------------------------- alerts
-- U: 9911 by email and Telegram (one alert). V: 9911 carried by a sent digest. W: 9912 as a top match of a
-- sent digest. Y: skipped (not delivered). X: admin. A: own member. W: 9911 40 days ago (outside 30 days).
-- V: 9912 20 days ago, before the item existed. U: 9914 (dealer B).
insert into public.notifications (id, user_id, listing_id, kind, channel, status, dedupe_key, sent_at, payload)
overriding system value values
  (99101, 'f1000000-0000-0000-0000-000000000001', 9911, 'new_match', 'email', 'sent', 'match:9911', now() - interval '5 minutes', '{}'),
  (99102, 'f1000000-0000-0000-0000-000000000001', 9911, 'new_match', 'telegram', 'sent', 'match:9911', now() - interval '5 minutes', '{}'),
  (99103, 'f1000000-0000-0000-0000-000000000002', null, 'digest', 'email', 'sent', 'digest:fn-v', now() - interval '5 minutes', '{"items": []}'),
  (99104, 'f1000000-0000-0000-0000-000000000003', null, 'digest', 'email', 'sent', 'digest:fn-w', now() - interval '5 minutes',
   '{"items": [{"section": "matches", "listing_id": 9912}, {"section": "matches", "listing_id": 9913}, {"listing_id": "x"}]}'),
  (99106, 'f1000000-0000-0000-0000-000000000004', 9911, 'new_match', 'email', 'skipped', 'match:9911', null, '{}'),
  (99107, 'f1000000-0000-0000-0000-00000000000f', 9911, 'new_match', 'email', 'sent', 'match:9911', now() - interval '5 minutes', '{}'),
  (99108, 'f1000000-0000-0000-0000-00000000000a', 9911, 'new_match', 'email', 'sent', 'match:9911', now() - interval '5 minutes', '{}'),
  (99109, 'f1000000-0000-0000-0000-000000000003', 9911, 'new_match', 'email', 'sent', 'match:9911', now() - interval '40 days', '{}'),
  (99110, 'f1000000-0000-0000-0000-000000000002', 9912, 'new_match', 'email', 'sent', 'match:9912', now() - interval '20 days', '{}'),
  (99111, 'f1000000-0000-0000-0000-000000000001', 9914, 'new_match', 'email', 'sent', 'match:9914', now() - interval '5 minutes', '{}');
insert into public.notifications (id, user_id, listing_id, kind, channel, status, dedupe_key, digested_in)
overriding system value values
  (99105, 'f1000000-0000-0000-0000-000000000002', 9911, 'new_match', 'email', 'digest', 'match:9911', 99103);

-- ---------------------------------------------------------------- leads
insert into public.dealer_leads (id, dealer_id, item_id, listing_id, buyer_user_id, buyer_name, buyer_phone, message,
                                 consent_text, origin)
overriding system value values
  (99201, 9901, 99011, 9911, 'f1000000-0000-0000-0000-000000000001', 'Ulises Comprador', '1155550001', 'Hola',
   'Acepto que Ese Auto le pase mis datos a Funnel A.', 'email'),
  (99202, 9901, 99012, 9912, 'f1000000-0000-0000-0000-000000000002', 'Valeria Compradora', '1155550002', null,
   'Acepto que Ese Auto le pase mis datos a Funnel A.', 'ficha'),
  (99203, 9901, 99011, 9911, 'f1000000-0000-0000-0000-000000000003', 'Walter Comprador', '1155550003', null,
   'Acepto que Ese Auto le pase mis datos a Funnel A.', 'web'),
  (99204, 9901, 99012, 9912, 'f1000000-0000-0000-0000-00000000000f', 'Admin Prueba', '1155550009', null,
   'Acepto que Ese Auto le pase mis datos a Funnel A.', 'ficha'),
  (99205, 9902, 99021, 9914, 'f1000000-0000-0000-0000-000000000004', 'Yanina Compradora', '1155550004', null,
   'Acepto que Ese Auto le pase mis datos a Funnel B.', 'ficha');
select is((select furthest_status from public.dealer_leads where id = 99201), 'new', 'a new lead starts at furthest_status new');

set local role authenticated;
set local request.jwt.claims = '{"sub": "f1000000-0000-0000-0000-00000000000a", "role": "authenticated"}';
select lives_ok($$select public.dealer_set_lead_status(99201, 'contacted')$$, 'A marks U contacted');
select lives_ok($$select public.dealer_set_lead_status(99201, 'lost')$$, '... then «No avanzó»');
select lives_ok($$select public.dealer_set_lead_status(99202, 'reserved')$$, 'A marks V reserved');
select lives_ok($$select public.dealer_set_lead_status(99202, 'sold')$$, '... then «Compró»');
select is(array(select furthest_status from public.dealer_leads where id in (99201, 99202, 99203) order by id),
          array['contacted', 'sold', 'new'], 'furthest_status keeps the furthest step (lost does not erase contacted)');
select ok((select furthest_status is not null from public.dealer_leads where id = 99201),
          'the agency reads furthest_status of its leads');

-- ---------------------------------------------------------------- declared sales
select throws_ok($$select public.dealer_declare_sale(null, 99202, null)$$, 'P0001', 'invalid_sale', 'no answer: invalid_sale');
select throws_ok($$select public.dealer_declare_sale(null, null, true)$$, 'P0001', 'invalid_sale', 'no car and no lead: invalid_sale');
select throws_ok($$select public.dealer_declare_sale(null, 99203, true)$$, 'P0001', 'not_sold', 'a lead that did not buy: not_sold');
select throws_ok($$select public.dealer_declare_sale(99015, null, true)$$, 'P0001', 'not_sold', 'a car not sold: not_sold');
select throws_ok($$select public.dealer_declare_sale(99011, 99202, true)$$, 'P0001', 'invalid_sale', 'a lead of another car: invalid_sale');
select throws_ok($$select public.dealer_declare_sale(null, 99205, true)$$, 'P0001', 'lead_not_found', 'another agency''s lead: lead_not_found');
select throws_ok($$select public.dealer_declare_sale(99021, null, true)$$, 'P0001', 'item_not_found', 'another agency''s car: item_not_found');

select lives_ok($$select public.dealer_set_item_status(99015, 'sold')$$, 'A marks the Corolla sold');
select is((public.my_dealer_reach() -> 'pending_sales')::jsonb @> '[{"item_id": 99015}]'::jsonb
          and (public.my_dealer_reach() -> 'pending_sales')::jsonb @> '[{"lead_id": 99202, "item_id": 99012}]'::jsonb,
          true, 'pending_sales: the sold car and the «Compró» lead wait for the answer');
select is(jsonb_array_length(public.my_dealer_reach() -> 'pending_sales'), 2, '... only those two');
select lives_ok($$select public.dealer_declare_sale(null, 99202, true)$$, 'V bought through Ese Auto');
select lives_ok($$select public.dealer_declare_sale(99015, null, true)$$, 'the Corolla: first yes ...');
select lives_ok($$select public.dealer_declare_sale(99015, null, false)$$, '... then no: the answer is replaced');
select is((select count(*)::int from public.dealer_sales where dealer_id = 9901), 2, 'one declaration per car');
select is((select via_ese_auto from public.dealer_sales where item_id = 99015), false, '... with the last answer');
select is((select array[item_id, lead_id] from public.dealer_sales where via_ese_auto), array[99012::bigint, 99202],
          'a lead declaration stores its car and the lead');
select is(jsonb_array_length(public.my_dealer_reach() -> 'pending_sales'), 0, 'nothing pending after answering');
select is((select count(*)::int from public.dealer_sales), 2, 'A reads its own declarations');

-- ---------------------------------------------------------------- my_dealer_reach
select is(public.my_dealer_reach() -> 'people', '3'::jsonb, 'A this month: 3 people reached (U, V, W), a number');
select is(public.my_dealer_reach() -> 'leads', '4'::jsonb, '... 4 leads (all of its inbox this month)');
select is(public.my_dealer_reach() -> 'min_count', '3'::jsonb, '... min_count 3');
select is(public.my_dealer_reach() -> 'sales_via_ese_auto', '1'::jsonb, '... 1 sale through Ese Auto');

set local request.jwt.claims = '{"sub": "f1000000-0000-0000-0000-00000000000b", "role": "authenticated"}';
select is(public.my_dealer_reach() -> 'people', '"few"'::jsonb, 'B: 1 person reached is shown as "few"');
select is(public.my_dealer_reach() -> 'leads', '1'::jsonb, '... and only its own lead');
select is((select count(*)::int from public.dealer_sales), 0, 'B does not read A''s declarations');
select throws_ok($$select public.dealer_declare_sale(99015, null, true)$$, 'P0001', 'item_not_found', 'B cannot answer for A''s car');

set local request.jwt.claims = '{"sub": "f1000000-0000-0000-0000-00000000000c", "role": "authenticated"}';
select is(public.my_dealer_reach() -> 'people', '0'::jsonb, 'C (nothing sent): 0, not "few"');
reset role;

update public.app_config set value = '{"enabled": true, "channel_enabled": true, "manual_confirm_days": 7, "demand_min_count": 4}'
 where key = 'dealer_program';
set local role authenticated;
set local request.jwt.claims = '{"sub": "f1000000-0000-0000-0000-00000000000a", "role": "authenticated"}';
select is(public.my_dealer_reach() -> 'people', '"few"'::jsonb, 'with demand_min_count 4, A''s 3 people are "few"');
reset role;
update public.app_config set value = '{"enabled": false, "channel_enabled": true, "manual_confirm_days": 7, "demand_min_count": 3}'
 where key = 'dealer_program';
set local role authenticated;
select throws_ok($$select public.my_dealer_reach()$$, 'P0001', 'dealer_program_off', 'program off: dealer_program_off');
reset role;
update public.app_config set value = '{"enabled": true, "channel_enabled": true, "manual_confirm_days": 7, "demand_min_count": 3}'
 where key = 'dealer_program';

-- ---------------------------------------------------------------- admin_dealer_funnel
set local role service_role;
select throws_ok($$select public.admin_dealer_funnel(now(), now() - interval '1 day')$$, '22023', 'invalid_funnel_range', 'end before start');
select throws_ok($$select public.admin_dealer_funnel(now() - interval '401 days', now())$$, '22023', 'invalid_funnel_range', 'more than 400 days');
select throws_ok($$select public.admin_dealer_funnel(null, now())$$, '22023', 'invalid_funnel_range', 'null start');

create temp table fn on commit drop as select public.admin_dealer_funnel(now() - interval '30 days', now() + interval '1 minute') as f;
create temp table fa on commit drop as select d from fn, jsonb_array_elements(f -> 'dealers') d where d ->> 'dealer_id' = '9901';
select is((select d - 'dealer_id' - 'name' - 'approved' - 'status' from fa),
          '{"stock": 4, "visible": 2, "loaded": 4, "matched_cars": 2, "matched_searches": 3,
            "alerts": 3, "alerted_cars": 2, "people": 3,
            "leads": 3, "contacted": 2, "reserved": 1, "sold": 1, "lost": 1, "still_new": 1,
            "sales_via_ese_auto": 1, "sales_elsewhere": 1}'::jsonb,
          'dealer A over 30 days: stock, visible, matches, alerts, people, leads by step and declared sales');
select is((select array[d ->> 'name', d ->> 'approved', d ->> 'status'] from fa), array['Funnel A', 'true', 'active'],
          '... with its name, approval and status');
select is((select d -> 'people' from fn, jsonb_array_elements(f -> 'dealers') d where d ->> 'dealer_id' = '9902'), '1'::jsonb,
          'dealer B: 1 person (the admin view shows the raw number)');
select is((select f -> 'total' -> 'people' from fn), '3'::jsonb, 'total people are distinct across dealers (U counts once)');
select is((select f -> 'total' -> 'alerts' from fn), '4'::jsonb, 'total alerts: 3 of A + 1 of B');
select is((select f -> 'total' -> 'leads' from fn), '4'::jsonb, 'total leads: the admin''s own test lead is left out');
select is((select jsonb_array_length(f -> 'dealers') >= 3 from fn), true, 'every dealer has a row, C included');
select is((select f::text ~* 'ulises|valeria|walter|yanina|1155550|funnel\.test|f1000000' from fn), false,
          'no buyer name, phone, email or id in the admin funnel');

create temp table f7 on commit drop as select public.admin_dealer_funnel(now() - interval '7 days', now() + interval '1 minute') as f;
select is((select d -> 'loaded' from f7, jsonb_array_elements(f -> 'dealers') d where d ->> 'dealer_id' = '9901'), '2'::jsonb,
          '7 days: only the cars loaded in the window (Ka and Corolla)');
create temp table fold on commit drop as
  select public.admin_dealer_funnel(now() - interval '60 days', now() - interval '30 days') as f;
select is((select d -> 'alerts' from fold, jsonb_array_elements(f -> 'dealers') d where d ->> 'dealer_id' = '9901'), '0'::jsonb,
          'an alert sent before the car was in the agency''s stock does not count for it');
reset role;

select * from finish();
rollback;

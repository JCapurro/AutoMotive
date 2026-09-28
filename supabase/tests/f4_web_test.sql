-- F4 web reads and writes (migration 20261001120000_f4_web.sql). Run with: supabase test db
begin;
create extension if not exists pgtap with schema extensions;
select plan(34);

insert into auth.users (instance_id, id, aud, role, email, created_at, updated_at) values
  ('00000000-0000-0000-0000-000000000000', '33333333-3333-3333-3333-333333333333',
   'authenticated', 'authenticated', 'a@f4.test', now() - interval '10 days', now()),
  ('00000000-0000-0000-0000-000000000000', '44444444-4444-4444-4444-444444444444',
   'authenticated', 'authenticated', 'b@f4.test', now(), now());
update public.profiles set created_at = now() - interval '10 days'
 where id = '33333333-3333-3333-3333-333333333333';

-- A has two searches of the same model, B one. A made-up model keeps other data out.
insert into public.search_profiles (id, user_id, name, filters, bootstrapped_at) overriding system value values
  (9101, '33333333-3333-3333-3333-333333333333', 'Uno A',  '{"make": "Pgtap", "model": "Uno"}', now()),
  (9102, '33333333-3333-3333-3333-333333333333', 'Uno A2', '{"make": "Pgtap", "model": "Uno"}', now()),
  (9103, '44444444-4444-4444-4444-444444444444', 'Uno B',  '{"make": "Pgtap", "model": "Uno"}', now());

insert into public.listings (id, source, external_id, url, title, make, model, year, price, currency,
                             price_usd, mileage_km, transmission, lat, lon, first_seen_at, price_partial)
overriding system value values
  (9101, 'mercadolibre', 'F4-1', 'https://example.test/f4-1', 'Pgtap Uno 1', 'Pgtap', 'Uno', 2017,
   10000, 'USD', 10000, 100000, 'manual', -34.60, -58.38, now() - interval '3 hours', false),
  (9102, 'mercadolibre', 'F4-2', 'https://example.test/f4-2', 'Pgtap Uno 2', 'Pgtap', 'Uno', 2018,
   9000000, 'ARS', 9000, 80000, null, null, null, now() - interval '2 hours', false),
  (9103, 'mercadolibre', 'F4-3', 'https://example.test/f4-3', 'Pgtap Uno 3', 'Pgtap', 'Uno', 2015,
   12000, 'USD', 12000, 150000, 'automatic', -31.42, -64.19, now() - interval '1 hour', false),
  (9104, 'mercadolibre', 'F4-4', 'https://example.test/f4-4', 'Pgtap Uno 4', 'Pgtap', 'Uno', 2017,
   500, 'USD', 500, 100000, 'manual', -34.60, -58.38, now(), true);

insert into public.matches (search_profile_id, listing_id, score, level, score_breakdown, match_reasons,
                            scoring_version) values
  (9101, 9101, 90, 'high',  '{}', '{}', 'test'),
  (9101, 9102, 72, 'good',  '{}', '{}', 'test'),
  (9101, 9103, 55, 'match', '{}', '{}', 'test'),
  (9102, 9101, 80, 'good',  '{}', '{}', 'test'),
  (9103, 9101, 60, 'match', '{}', '{}', 'test');

insert into public.user_listing_interactions (user_id, listing_id, status, saved, rejection_reason) values
  ('33333333-3333-3333-3333-333333333333', 9102, 'seen', true, null),
  ('33333333-3333-3333-3333-333333333333', 9103, 'discarded', false, 'too_expensive');

-- A quote only this test uses: preview_search takes the latest one.
insert into public.fx_rates (date, kind, rate, source) values ('2999-01-01', 'blue', 1000, 'test');

update public.profiles set telegram_user_id = 424242, telegram_chat_id = 424242
 where id = '33333333-3333-3333-3333-333333333333';

-- ---------------------------------------------------------------- user A
set local role authenticated;
set local request.jwt.claims = '{"sub": "33333333-3333-3333-3333-333333333333", "role": "authenticated"}';

select is((select count(*)::int from public.match_cards), 4, 'match_cards: only A''s matches');
select is((select count(*)::int from public.match_cards where user_id <> '33333333-3333-3333-3333-333333333333'),
          0, '... none of B''s');

-- dashboard_summary
select results_eq(
  $$select profile_id, total, new_this_week, opportunities_this_week, unseen, pending
      from public.dashboard_summary() order by profile_id$$,
  $$values (9101::bigint, 2, 2, 1, 1, false), (9102::bigint, 1, 1, 0, 1, false)$$,
  'dashboard_summary: discarded left out, unseen = never opened');

-- search_results
select results_eq($$select listing_id from public.search_results(9101, 'new')$$,
                  $$values (9101::bigint)$$, 'filter new: not opened yet');
select results_eq($$select listing_id from public.search_results(9101, 'opportunities')$$,
                  $$values (9101::bigint)$$, 'filter opportunities: 🔥 only');
select results_eq($$select listing_id from public.search_results(9101, 'all')$$,
                  $$values (9102::bigint), (9101::bigint)$$, 'filter all: no discarded, newest first');
select results_eq($$select listing_id from public.search_results(9101, 'saved')$$,
                  $$values (9102::bigint)$$, 'filter saved');
select results_eq($$select listing_id from public.search_results(9101, 'discarded')$$,
                  $$values (9103::bigint)$$, 'filter discarded');
select results_eq($$select listing_id from public.search_results(9101, 'all', 'price')$$,
                  $$values (9102::bigint), (9101::bigint)$$, 'sort price: lowest USD first');
select results_eq($$select listing_id from public.search_results(9101, 'all', 'score')$$,
                  $$values (9101::bigint), (9102::bigint)$$, 'sort score');
select results_eq($$select listing_id from public.search_results(9101, 'all', 'km')$$,
                  $$values (9102::bigint), (9101::bigint)$$, 'sort km');
select results_eq($$select listing_id from public.search_results(9101, 'all', 'recent', 1, 1)$$,
                  $$values (9101::bigint)$$, 'limit and offset');
select is((select count(*)::int from public.search_results(9103)), 0, 'another user''s search reads nothing');
select results_eq($$select new_count, opportunities_count, all_count, saved_count, discarded_count
                      from public.search_result_counts(9101)$$,
                  $$values (1, 1, 2, 1, 1)$$, 'search_result_counts');

-- recent_opportunities
select results_eq($$select listing_id, score from public.recent_opportunities()$$,
                  $$values (9101::bigint, 90::smallint), (9102::bigint, 72::smallint)$$,
                  'recent_opportunities: best match per listing, 🔥 and 🟢, by score');

-- preview_search
select is((public.preview_search('{"make": "Pgtap", "model": "Uno", "year_min": 2016,
                                   "price_max": 11000, "currency": "USD"}')->>'count')::int, 2,
          'preview: year and USD cap (an ARS listing compared in USD), partial prices out');
select is((public.preview_search('{"make": "pgtap", "model": "UNO", "transmission": "manual"}')->>'count')::int, 2,
          'preview: case-insensitive; an unknown transmission doesn''t discard');
select is((public.preview_search('{"make": "Pgtap", "model": "Uno"}', -34.6037, -58.3816, 60)->>'count')::int, 2,
          'preview: radius drops Córdoba, keeps the listing without coordinates');
select is((public.preview_search('{"make": "Pgtap", "model": "Uno"}')->>'count')::int, 3,
          'preview: no location, the whole country');
select is((public.preview_search('{"make": "Pgtap", "model": "Uno", "price_max": 9500000,
                                   "currency": "ARS"}')->>'count')::int, 1,
          'preview: an ARS cap converts USD listings with the latest quote');
select is(jsonb_array_length(public.preview_search('{"make": "Pgtap", "model": "Uno"}')->'sample'), 3,
          'preview: a sample of up to 3');
select is((public.preview_search('{"model": "Uno"}')->>'count')::int, 0, 'preview: needs a make');

-- record_purchase
select ok(public.record_purchase(9101, 9101, 10000, 'USD', '2026-09-20') > 0, 'record_purchase returns the id');
select is((select count(*)::int from public.owned_vehicles), 1, 'an OwnedVehicle');
select is((select vehicle->>'make' from public.owned_vehicles), 'Pgtap', '... with a snapshot of the vehicle');
select is((select status::text from public.user_listing_interactions where listing_id = 9101), 'purchased',
          'the listing is marked purchased');
select is((select (props->>'days_using_automotive')::int from public.events where name = 'vehicle_purchased'), 10,
          'vehicle_purchased records the time using Automotive');
select is(public.record_purchase(9101, 9103, 9500, 'USD', null),
          (select id from public.owned_vehicles), 'buying again updates the same row');
select is((select search_profile_id from public.owned_vehicles), 9101::bigint,
          '... and another user''s search id is ignored');
select lives_ok($$update public.owned_vehicles set automotive_influence = 'a_lot'$$,
                'the §38 answer is stored');

-- Telegram
select throws_ok($$select public.link_telegram('x', 1, 1)$$, '42501', null,
                 'only the bot links Telegram');
select lives_ok($$select public.unlink_telegram()$$, 'A can unlink Telegram');
select is((select telegram_chat_id from public.profiles), null, '... the chat is gone');

-- ---------------------------------------------------------------- anon
reset role;
set local role anon;
select throws_ok($$select * from public.match_cards$$, '42501', null, 'anonymous visitors read no cards');

select * from finish();
rollback;

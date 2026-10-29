-- X-01 seguimiento (migration 20261119120000_x01_tracking.sql). Run with: supabase test db
-- Run in an isolated local database; all fixtures roll back.
begin;
create extension if not exists pgtap with schema extensions;
select no_plan();

insert into auth.users (instance_id, id, aud, role, email, created_at, updated_at) values
  ('00000000-0000-0000-0000-000000000000', '61616161-6161-6161-6161-616161616161', 'authenticated', 'authenticated', 'a@x01.test', now(), now()),
  ('00000000-0000-0000-0000-000000000000', '62626262-6262-6262-6262-626262626262', 'authenticated', 'authenticated', 'b@x01.test', now(), now());

-- A and B follow the same car; a made-up model keeps other data out.
insert into public.search_profiles (id, user_id, name, filters, bootstrapped_at) overriding system value values
  (9961, '61616161-6161-6161-6161-616161616161', 'Seguimiento A', '{"make": "Pgtap", "model": "Sigo"}', now()),
  (9962, '62626262-6262-6262-6262-626262626262', 'Seguimiento B', '{"make": "Pgtap", "model": "Sigo"}', now());

insert into public.listings (id, source, external_id, url, title, make, model, price, currency, price_usd, status)
overriding system value values
  (996001, 'mercadolibre', 'X01-1', 'https://example.test/x01-1', 'Pgtap Sigo 1', 'Pgtap', 'Sigo', 10000, 'USD', 10000, 'active'),
  (996002, 'mercadolibre', 'X01-2', 'https://example.test/x01-2', 'Pgtap Sigo 2', 'Pgtap', 'Sigo', 9000, 'USD', 9000, 'gone'),
  (996003, 'mercadolibre', 'X01-3', 'https://example.test/x01-3', 'Pgtap Sigo 3', 'Pgtap', 'Sigo', 11000, 'USD', 11000, 'active'),
  (996004, 'mercadolibre', 'X01-4', 'https://example.test/x01-4', 'Pgtap Sigo 4', 'Pgtap', 'Sigo', 12000, 'USD', 12000, 'active'),
  (996005, 'mercadolibre', 'X01-5', 'https://example.test/x01-5', 'Pgtap Sigo 5', 'Pgtap', 'Sigo', 13000, 'USD', 13000, 'active');

insert into public.matches (search_profile_id, listing_id, score, level, score_breakdown, match_reasons, scoring_version)
select 9961, 996000 + n, 100 - n, 'good', '{}', '{}', 'test' from generate_series(1, 5) n
union all select 9962, 996001, 70, 'good', '{}', '{}', 'test';

insert into public.user_listing_interactions (user_id, listing_id, status, saved, note) values
  ('61616161-6161-6161-6161-616161616161', 996001, 'contacted', false, 'nota de A'),
  ('61616161-6161-6161-6161-616161616161', 996002, 'contacted', true, null),
  ('61616161-6161-6161-6161-616161616161', 996003, 'visit_scheduled', false, null),
  ('61616161-6161-6161-6161-616161616161', 996004, 'purchased', false, null),
  ('62626262-6262-6262-6262-626262626262', 996001, 'seen', false, 'nota de B');

-- ---------------------------------------------------------------- user A
set local role authenticated;
set local request.jwt.claims = '{"sub": "61616161-6161-6161-6161-616161616161", "role": "authenticated"}';

-- RLS on user_listing_interactions (20260927120100_rls.sql: "own rows").
select is((select count(*)::int from public.user_listing_interactions where user_id = '62626262-6262-6262-6262-626262626262'),
          0, 'RLS: A does not see B''s follow-up');
update public.user_listing_interactions set note = 'escrita por A', status = 'discarded'
 where user_id = '62626262-6262-6262-6262-626262626262';
select throws_ok(
  $$insert into public.user_listing_interactions (user_id, listing_id, status) values ('62626262-6262-6262-6262-626262626262', 996005, 'contacted')$$,
  '42501', null, 'RLS: A cannot write a row as B');

-- match_cards.note: the user's own note only.
select is((select note from public.match_cards where search_profile_id = 9961 and listing_id = 996001), 'nota de A',
          'match_cards.note: A''s note on A''s card');
select is((select count(*)::int from public.match_cards where note = 'nota de B'), 0, 'match_cards.note: never B''s note');
select is((select note from public.match_cards where search_profile_id = 9961 and listing_id = 996005), null,
          'match_cards.note: null without a follow-up');

-- search_results: the three new filters, gone listings included.
select results_eq($$select listing_id from public.search_results(9961, 'contacted')$$,
                  $$values (996001::bigint), (996002::bigint)$$, 'filter contacted: the gone one too');
select is((select listing_status from public.search_results(9961, 'contacted') where listing_id = 996002), 'gone',
          '... still marked gone');
select results_eq($$select listing_id from public.search_results(9961, 'visit_scheduled')$$,
                  $$values (996003::bigint)$$, 'filter visit_scheduled');
select results_eq($$select listing_id from public.search_results(9961, 'purchased')$$,
                  $$values (996004::bigint)$$, 'filter purchased');
select results_eq($$select listing_id from public.search_results(9961, 'all')$$,
                  $$values (996001::bigint), (996003::bigint), (996004::bigint), (996005::bigint)$$,
                  'filter all unchanged: active only');
select is((select count(*)::int from public.search_results(9962, 'contacted')), 0, 'another user''s search reads nothing');

-- search_follow_counts
select results_eq($$select contacted_count, visit_scheduled_count, purchased_count from public.search_follow_counts(9961)$$,
                  $$values (2, 1, 1)$$, 'search_follow_counts');
select is((select contacted_count from public.search_follow_counts(9961)),
          (select count(*)::int from public.search_results(9961, 'contacted', 'score', 1000, 0)), '... contacted = its filter');
select is((select visit_scheduled_count from public.search_follow_counts(9961)),
          (select count(*)::int from public.search_results(9961, 'visit_scheduled', 'score', 1000, 0)), '... visit_scheduled = its filter');
select is((select purchased_count from public.search_follow_counts(9961)),
          (select count(*)::int from public.search_results(9961, 'purchased', 'score', 1000, 0)), '... purchased = its filter');
select results_eq($$select contacted_count, visit_scheduled_count, purchased_count from public.search_follow_counts(9962)$$,
                  $$values (0, 0, 0)$$, 'search_follow_counts: nothing of another user''s search');

reset role;

select is((select note || '/' || status from public.user_listing_interactions
            where user_id = '62626262-6262-6262-6262-626262626262' and listing_id = 996001),
          'nota de B/seen', 'RLS: A''s update left B''s row untouched');

-- The note's technical cap.
select throws_ok(
  $$update public.user_listing_interactions set note = repeat('a', 2001)
     where user_id = '61616161-6161-6161-6161-616161616161' and listing_id = 996001$$,
  '23514', null, 'a note over 2000 characters is rejected');
select lives_ok(
  $$update public.user_listing_interactions set note = repeat('a', 2000)
     where user_id = '61616161-6161-6161-6161-616161616161' and listing_id = 996001$$,
  'a note of 2000 characters is stored');

-- app_config and grants.
select is((select (value ->> 'note_max_chars')::int from public.app_config where key = 'listing_tracking'), 500,
          'app_config.listing_tracking.note_max_chars = 500');
select ok(not has_function_privilege('anon', 'public.search_follow_counts(bigint)', 'execute'),
          'search_follow_counts: not for anon');
select ok(has_function_privilege('authenticated', 'public.search_follow_counts(bigint)', 'execute'),
          'search_follow_counts: for authenticated');

-- ---------------------------------------------------------------- the free trial's cap of 50
update public.app_config set value = jsonb_set(value, '{enforced}', 'true') where key = 'plan_limits';
insert into auth.users (instance_id, id, aud, role, email, created_at, updated_at) values
  ('00000000-0000-0000-0000-000000000000', '63636363-6363-6363-6363-636363636363', 'authenticated', 'authenticated', 'q@x01.test', now(), now());
insert into public.search_profiles (id, user_id, name, filters) overriding system value values
  (9963, '63636363-6363-6363-6363-636363636363', 'Seguimiento cupo', '{"make": "Pgtap", "model": "Sigo"}');
insert into public.listings (id, source, external_id, url, title, make, model) overriding system value
select 996100 + n, 'mercadolibre', 'X01-Q-' || n, 'https://example.test/x01-q-' || n, 'Pgtap Sigo', 'Pgtap', 'Sigo'
  from generate_series(1, 180) n;
insert into public.matches (search_profile_id, listing_id, score, level, score_breakdown, match_reasons, scoring_version)
select 9963, 996100 + n, 90, 'good', '{}', '{}', 'test' from generate_series(1, 180) n;
insert into public.user_listing_interactions (user_id, listing_id, status)
select '63636363-6363-6363-6363-636363636363', 996100 + n,
       (array['contacted', 'visit_scheduled', 'purchased'])[1 + n % 3]::public.interaction_status
  from generate_series(1, 180) n;

set local role authenticated;
set local request.jwt.claims = '{"sub": "63636363-6363-6363-6363-636363636363", "role": "authenticated"}';
select is((select count(*)::int from public.search_results(9963, 'contacted', 'score', 1000, 0))
        + (select count(*)::int from public.search_results(9963, 'visit_scheduled', 'score', 1000, 0))
        + (select count(*)::int from public.search_results(9963, 'purchased', 'score', 1000, 0)),
          50, 'free trial: the three filters together never pass the 50 admitted listings');
select is((select contacted_count + visit_scheduled_count + purchased_count from public.search_follow_counts(9963)),
          50, 'free trial: the counts respect the cap too');
select is((select contacted_count from public.search_follow_counts(9963)),
          (select count(*)::int from public.search_results(9963, 'contacted', 'score', 1000, 0)),
          'free trial: contacted count = its filter');
reset role;

select * from finish();
rollback;

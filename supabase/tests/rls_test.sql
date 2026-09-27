-- Basic RLS checks (sección 4.4). Run with: supabase test db
begin;
create extension if not exists pgtap with schema extensions;
select plan(27);

-- Two users; handle_new_user() creates their profiles.
insert into auth.users (instance_id, id, aud, role, email, created_at, updated_at) values
  ('00000000-0000-0000-0000-000000000000', '11111111-1111-1111-1111-111111111111',
   'authenticated', 'authenticated', 'a@rls.test', now(), now()),
  ('00000000-0000-0000-0000-000000000000', '22222222-2222-2222-2222-222222222222',
   'authenticated', 'authenticated', 'b@rls.test', now(), now());

select is((select count(*)::int from public.profiles where email like '%@rls.test'), 2,
          'auth users get a profile');

insert into public.search_profiles (id, user_id, name, filters) overriding system value values
  (9001, '11111111-1111-1111-1111-111111111111', 'A', '{"make": "Ford", "model": "Fiesta"}'),
  (9002, '22222222-2222-2222-2222-222222222222', 'B', '{"make": "Ford", "model": "Ka"}');
insert into public.listings (id, source, external_id, url, title) overriding system value values
  (9001, 'mercadolibre', 'RLS1', 'https://example.test/1', 'Ford Fiesta');
insert into public.listing_snapshots (listing_id, attrs_hash, change_kind) values (9001, 'h', 'new');
insert into public.matches (search_profile_id, listing_id, score, level, score_breakdown, match_reasons, scoring_version)
values (9001, 9001, 80, 'good', '{}', '{}', 'test'), (9002, 9001, 60, 'match', '{}', '{}', 'test');
insert into public.notifications (id, user_id, listing_id, kind, channel, dedupe_key) overriding system value values
  (9001, '11111111-1111-1111-1111-111111111111', 9001, 'new_match', 'telegram', 'new_match:9001'),
  (9002, '22222222-2222-2222-2222-222222222222', 9001, 'new_match', 'telegram', 'new_match:9001');

-- ---------------------------------------------------------------- user A
set local role authenticated;
set local request.jwt.claims = '{"sub": "11111111-1111-1111-1111-111111111111", "role": "authenticated"}';

select is((select count(*)::int from public.profiles), 1, 'A sees only its own profile');
select is((select count(*)::int from public.search_profiles), 1, 'A sees only its own search profiles');
select is((select name from public.search_profiles), 'A', '... and it is A''s');
select throws_ok(
  $$insert into public.search_profiles (user_id, name, filters)
    values ('22222222-2222-2222-2222-222222222222', 'x', '{}')$$,
  '42501', null, 'A cannot create search profiles for B');

select is((select count(*)::int from public.matches), 1, 'A sees matches only through its profiles');
select is((select count(*)::int from public.listings where id = 9001), 1, 'listings are readable');
select is((select count(*)::int from public.listing_snapshots where listing_id = 9001), 1,
          'listing snapshots are readable');
select ok((select count(*) > 0 from public.vehicle_catalog), 'vehicle_catalog is readable');
select ok((select count(*) > 0 from public.sources), 'sources are readable');

select throws_ok($$insert into public.listings (source, external_id, url, title)
                   values ('mercadolibre', 'x', 'u', 't')$$, '42501', null, 'only the worker writes listings');
select throws_ok($$update public.matches set score = 100$$, '42501', null, 'only the worker writes matches');

select throws_ok($$select * from public.app_config$$, '42501', null, 'app_config is server-only');
select throws_ok($$select * from public.collector_runs$$, '42501', null, 'collector_runs is server-only');
select throws_ok($$select * from public.pipeline_errors$$, '42501', null, 'pipeline_errors is server-only');
select throws_ok($$select * from public.crawl_targets$$, '42501', null, 'crawl_targets is server-only');

select lives_ok($$update public.profiles set phone = '+5491100000000'$$, 'A can edit its phone');
select throws_ok($$update public.profiles set plan = 'pro'$$, '42501', null, 'A cannot change its plan');
select throws_ok($$update public.profiles set role = 'admin'$$, '42501', null, 'A cannot make itself admin');

select is((select count(*)::int from public.notifications), 1, 'A sees only its notifications');
select lives_ok($$update public.notifications set opened_at = now()$$, 'A can mark a notification opened');
select throws_ok($$update public.notifications set status = 'sent'$$, '42501', null,
                 'A cannot change delivery status');

select lives_ok($$insert into public.events (user_id, name)
                  values ('11111111-1111-1111-1111-111111111111', 'listing_saved')$$, 'A can log its events');
select throws_ok($$insert into public.events (user_id, name)
                   values ('22222222-2222-2222-2222-222222222222', 'listing_saved')$$,
                 '42501', null, 'A cannot log events as B');

select lives_ok($$insert into public.llm_jobs (kind, input) values ('parse_search', '{"text": "fiesta"}')$$,
                'A can enqueue an LLM job');
select throws_ok($$insert into public.llm_jobs (kind, input, status)
                   values ('parse_search', '{}', 'done')$$, '42501', null, 'A cannot set a job''s status');

-- ---------------------------------------------------------------- anon
reset role;
set local role anon;
select throws_ok($$select * from public.listings$$, '42501', null, 'anonymous visitors read nothing');

reset role;
select * from finish();
rollback;

-- f3 shadow mode (migration 20261212120000_score_f3_shadow): the insert-only decision log
-- public.match_decisions and app_config.score_model_f3. Run with: supabase test db
-- All fixtures roll back.
begin;
create extension if not exists pgtap with schema extensions;
select no_plan();

-- ---------------------------------------------------------------- schema
select has_table('public', 'match_decisions', 'match_decisions exists');
select col_not_null('public', 'match_decisions', c, 'match_decisions.' || c || ' is not null')
  from unnest(array['match_id', 'search_profile_id', 'listing_id', 'model', 'phase', 'decided_at',
                    'f3_decides', 'f2_version', 'red_flags', 'f3_flags', 'f3_a_verificar']) c;
select col_is_unique('public', 'match_decisions', array['match_id', 'model', 'phase'],
                     'one row per (match, model, phase)');
select has_index('public', 'match_decisions', 'match_decisions_listing_idx', 'index by listing');
select has_index('public', 'match_decisions', 'match_decisions_profile_idx', 'index by search');
select has_index('public', 'match_decisions', 'match_decisions_sweep_idx', 'partial index for the sweeper');
select has_index('public', 'match_decisions', 'match_decisions_user_idx', 'index by user (the account purge)');
select has_trigger('auth', 'users', 'match_decisions_purge_account', 'deleting a user purges its decision rows');
select is((select count(*)::int from pg_constraint where conrelid = 'public.match_decisions'::regclass and contype = 'f'),
          0, 'no foreign keys (a cascade would hit the insert-only trigger)');
select col_type_is('public', 'match_decisions', 'red_flags', 'text[]', 'red_flags is text[]');
select col_type_is('public', 'match_decisions', 'f3', 'jsonb', 'f3 is jsonb');

-- ---------------------------------------------------------------- access
select ok((select relrowsecurity from pg_class where oid = 'public.match_decisions'::regclass), 'RLS is on');
select is((select count(*)::int from pg_policies where schemaname = 'public' and tablename = 'match_decisions'),
          0, 'no policy: only the worker reads it');
select ok(not has_table_privilege('anon', 'public.match_decisions', 'select'), 'anon cannot read');
select ok(not has_table_privilege('anon', 'public.match_decisions', 'insert'), 'anon cannot insert');
select ok(not has_table_privilege('authenticated', 'public.match_decisions', 'select'), 'authenticated cannot read');
select ok(not has_table_privilege('authenticated', 'public.match_decisions', 'insert'), 'authenticated cannot insert');
select ok(has_table_privilege('service_role', 'public.match_decisions', 'select'), 'service role reads');
select ok(has_table_privilege('service_role', 'public.match_decisions', 'insert'), 'service role inserts');
select ok(not has_table_privilege('service_role', 'public.match_decisions', 'update'), 'service role cannot update');
select ok(not has_table_privilege('service_role', 'public.match_decisions', 'delete'), 'service role cannot delete');
select ok(not has_table_privilege('service_role', 'public.match_decisions', 'truncate'), 'service role cannot truncate');

-- ---------------------------------------------------------------- inserts and checks
select lives_ok($$insert into public.match_decisions (match_id, search_profile_id, listing_id, model, phase, f3_decides, f2_version)
                  values (99820001, 9982, 998201, 'f2', 'card', true, 'f2-v5-seller-margin')$$,
                'a minimal card row inserts');
select is((select (decided_at = now(), red_flags, f3_flags, f3_a_verificar)::text from public.match_decisions where match_id = 99820001),
          '(t,{},{},{})', 'decided_at defaults to now(), arrays to empty');
select throws_ok($$insert into public.match_decisions (match_id, search_profile_id, listing_id, model, phase, f3_decides, f2_version)
                   values (99820001, 9982, 998201, 'f2', 'card', false, 'f2-v5-seller-margin')$$,
                 '23505', null, 'the same (match, model, phase) twice is refused');
select lives_ok($$insert into public.match_decisions (match_id, search_profile_id, listing_id, model, phase, f3_decides, f2_version)
                  values (99820001, 9982, 998201, 'f2', 'card', false, 'f2-v5-seller-margin')
                  on conflict (match_id, model, phase) do nothing$$,
                'a retried batch (on conflict do nothing) lives');
select is((select count(*)::int from public.match_decisions where match_id = 99820001), 1, '... and adds no row');
select lives_ok($$insert into public.match_decisions (match_id, search_profile_id, listing_id, model, phase, f3_decides, f2_version)
                  values (99820001, 9982, 998201, 'f2', 'deferred', true, 'f2-v5-seller-margin'),
                         (99820001, 9982, 998201, 'f2', 'sweeper', false, 'f2-v5-seller-margin')$$,
                'the other phases of the same match insert');

select throws_ok($$insert into public.match_decisions (match_id, search_profile_id, listing_id, model, phase, f3_decides, f2_version)
                   values (99820002, 9982, 998201, 'f2', 'later', true, 'v')$$, '23514', null, 'an unknown phase is refused');
select throws_ok($$insert into public.match_decisions (match_id, search_profile_id, listing_id, model, phase, f3_decides, f2_version)
                   values (99820002, 9982, 998201, 'f9', 'card', true, 'v')$$, '23514', null, 'an unknown model is refused');
select throws_ok($$insert into public.match_decisions (match_id, search_profile_id, listing_id, model, phase, f3_decides, f2_version, f2_decision)
                   values (99820002, 9982, 998201, 'f2', 'card', true, 'v', 'sent')$$, '23514', null, 'an unknown f2 decision is refused');
select throws_ok($$insert into public.match_decisions (match_id, search_profile_id, listing_id, model, phase, f3_decides, f2_version, f3_decision)
                   values (99820002, 9982, 998201, 'f2', 'card', true, 'v', 'later')$$, '23514', null, 'an unknown f3 decision is refused');
select throws_ok($$insert into public.match_decisions (match_id, search_profile_id, listing_id, model, phase, f3_decides, f2_version, f2_level)
                   values (99820002, 9982, 998201, 'f2', 'card', true, 'v', 'excluded')$$, '23514', null, 'f2 has no excluded level');
select throws_ok($$insert into public.match_decisions (match_id, search_profile_id, listing_id, model, phase, f3_decides, f2_version, f3_level)
                   values (99820002, 9982, 998201, 'f2', 'card', true, 'v', 'top')$$, '23514', null, 'an unknown f3 level is refused');
select throws_ok($$insert into public.match_decisions (match_id, search_profile_id, listing_id, model, phase, f3_decides, f2_version, f3_score)
                   values (99820002, 9982, 998201, 'f2', 'card', true, 'v', 101)$$, '23514', null, 'a score above 100 is refused');
select throws_ok($$insert into public.match_decisions (match_id, search_profile_id, listing_id, model, phase, f3_decides, f2_version, f2_kind)
                   values (99820002, 9982, 998201, 'f2', 'card', true, 'v', 'price_drop')$$, '23514', null, 'only alert kinds');
select lives_ok($$insert into public.match_decisions (match_id, search_profile_id, listing_id, model, phase, f3_decides, f2_version, f3_level)
                  values (99820002, 9982, 998201, 'f2', 'card', true, 'v', 'excluded')$$, 'f3 can log an excluded level');
select throws_ok($$insert into public.match_decisions (match_id, search_profile_id, listing_id, model, phase, f2_version)
                   values (99820003, 9982, 998201, 'f2', 'card', 'v')$$, '23502', null, 'f3_decides is required');

-- ---------------------------------------------------------------- insert-only
select throws_ok($$update public.match_decisions set f3_decides = false where match_id = 99820001$$,
                 'P0001', 'match_decisions is insert-only', 'update is refused');
select throws_ok($$delete from public.match_decisions where match_id = 99820001$$,
                 'P0001', 'match_decisions is insert-only', 'delete is refused');
select throws_ok($$insert into public.match_decisions (match_id, search_profile_id, listing_id, model, phase, f3_decides, f2_version)
                   values (99820001, 9982, 998201, 'f2', 'card', false, 'v')
                   on conflict (match_id, model, phase) do update set f3_decides = excluded.f3_decides$$,
                 'P0001', 'match_decisions is insert-only', 'an upsert cannot rewrite a row either');
select is((select count(*)::int from public.match_decisions where match_id = 99820001), 3, 'the rows are still there');

-- ---------------------------------------------------------------- the rows outlive their match, listing and search
insert into auth.users (instance_id, id, aud, role, email, created_at, updated_at) values
  ('00000000-0000-0000-0000-000000000000', 'f3f30000-0000-4000-8000-000000000001', 'authenticated', 'authenticated',
   'shadow@score-f3.test', now(), now());
insert into public.search_profiles (id, user_id, name, filters, bootstrapped_at) overriding system value values
  (99821, 'f3f30000-0000-4000-8000-000000000001', 'Sombra f3', '{"make": "Pgtap", "model": "Sombra"}', now());
insert into public.listings (id, source, external_id, url, title, make, model, price, currency, price_usd, status)
overriding system value values
  (998211, 'mercadolibre', 'F3SHADOW-1', 'https://example.test/f3-1', 'Pgtap Sombra 1', 'Pgtap', 'Sombra', 10000, 'USD', 10000, 'active');
insert into public.matches (id, search_profile_id, listing_id, score, level, score_breakdown, match_reasons, scoring_version)
overriding system value values (99821001, 99821, 998211, 88, 'high', '{}', '{}', 'f2-v5-seller-margin');
insert into public.match_decisions (match_id, search_profile_id, listing_id, user_id, model, phase, f3_decides, f2_version,
                                    f2_score, f2_level, f2_decision, f2_kind, f3_level, f3_score, f3_decision, f3_kind)
values (99821001, 99821, 998211, 'f3f30000-0000-4000-8000-000000000001', 'f2', 'card', true, 'f2-v5-seller-margin',
        88, 'high', 'queued', 'opportunity', 'good', 78, 'queued', 'new_match');

select lives_ok($$delete from public.matches where id = 99821001$$, 'deleting the match lives');
select lives_ok($$delete from public.listings where id = 998211$$, 'deleting the listing lives');
select lives_ok($$delete from public.search_profiles where id = 99821$$, 'deleting the search lives');
select is((select (f2_decision, f3_level)::text from public.match_decisions where match_id = 99821001),
          '(queued,good)', 'the decision row stays (a search deleted on its own keeps its rows, as notifications do)');

-- ---------------------------------------------------------------- «Borrar mi cuenta» takes the account's rows
-- The user above (its search already gone) has one more search, still there, with a row without user_id
-- (a candidate without an audience); another user's rows and an unrelated one stay.
insert into auth.users (instance_id, id, aud, role, email, created_at, updated_at) values
  ('00000000-0000-0000-0000-000000000000', 'f3f30000-0000-4000-8000-000000000002', 'authenticated', 'authenticated',
   'other@score-f3.test', now(), now());
insert into public.search_profiles (id, user_id, name, filters, bootstrapped_at) overriding system value values
  (99822, 'f3f30000-0000-4000-8000-000000000001', 'Sombra f3 (2)', '{"make": "Pgtap", "model": "Sombra"}', now()),
  (99823, 'f3f30000-0000-4000-8000-000000000002', 'Otra', '{"make": "Pgtap", "model": "Otra"}', now());
insert into public.match_decisions (match_id, search_profile_id, listing_id, user_id, model, phase, f3_decides, f2_version) values
  (99822001, 99822, 998212, null, 'f2', 'card', true, 'f2-v5-seller-margin'),
  (99822001, 99822, 998212, 'f3f30000-0000-4000-8000-000000000001', 'f2', 'deferred', true, 'f2-v5-seller-margin'),
  (99823001, 99823, 998213, 'f3f30000-0000-4000-8000-000000000002', 'f2', 'card', true, 'f2-v5-seller-margin');

set local role authenticated;
set local request.jwt.claims = '{"sub": "f3f30000-0000-4000-8000-000000000001", "role": "authenticated"}';
select lives_ok($$select public.delete_my_account()$$, 'delete_my_account lives');
reset role;
select is((select count(*)::int from public.match_decisions where match_id in (99821001, 99822001)), 0,
          'the account''s rows are gone: by user_id, and those of its searches without one');
select is((select count(*)::int from public.match_decisions where match_id in (99823001, 99820001)), 4,
          'another account''s rows and the unrelated ones stay');
select is(current_setting('app.match_decisions_purge', true), 'off', 'the purge flag is off again after the purge');
select throws_ok($$delete from public.match_decisions where match_id = 99823001$$,
                 'P0001', 'match_decisions is insert-only', 'after the purge, a plain delete is refused again');
select throws_ok($$select set_config('app.match_decisions_purge', 'on', true);
                   delete from public.match_decisions where match_id = 99823001$$,
                 'P0001', 'match_decisions is insert-only', 'the flag alone does not open it (only the purge trigger)');
select set_config('app.match_decisions_purge', 'on', true);
select throws_ok($$update public.match_decisions set f3_decides = false where match_id = 99823001$$,
                 'P0001', 'match_decisions is insert-only', 'and an update never goes through');
select set_config('app.match_decisions_purge', 'off', true);
-- The admin API and the dashboard delete the user row directly: the same trigger.
select lives_ok($$delete from auth.users where id = 'f3f30000-0000-4000-8000-000000000002'$$, 'deleting a user directly lives');
select is((select count(*)::int from public.match_decisions where match_id = 99823001), 0, '... and takes its rows too');

-- ---------------------------------------------------------------- roles
set local role authenticated;
select throws_ok($$select count(*) from public.match_decisions$$, '42501', null, 'users cannot read the log');
reset role;
set local role anon;
select throws_ok($$select count(*) from public.match_decisions$$, '42501', null, 'anon cannot read the log');
reset role;
set local role service_role;
select lives_ok($$insert into public.match_decisions (match_id, search_profile_id, listing_id, model, phase, f3_decides, f2_version)
                  values (99820010, 9982, 998201, 'f2', 'card', true, 'v')$$, 'the service role inserts');
select is((select count(*)::int from public.match_decisions where match_id = 99820010), 1, '... and reads');
select throws_ok($$update public.match_decisions set f3_decides = false where match_id = 99820010$$,
                 '42501', null, 'the service role has no update privilege');
reset role;

-- ---------------------------------------------------------------- app_config.score_model_f3
select is((select value->>'mode' from public.app_config where key = 'score_model_f3'), 'shadow', 'score_model_f3 runs in shadow');
select is((select array_agg(k order by k) from public.app_config a, jsonb_object_keys(a.value) k where a.key = 'score_model_f3'),
          array['deal', 'fit', 'levels', 'mode', 'rules'], 'mode plus four groups');
select ok((select bool_and(jsonb_typeof(value->g) = 'object') from public.app_config, unnest(array['deal', 'fit', 'levels', 'rules']) g
            where key = 'score_model_f3'), 'each group is an object');
select is((select value #> '{levels,c_high}' from public.app_config where key = 'score_model_f3'), '0.82'::jsonb, 'levels.c_high = 0.82');
select is((select value #> '{levels,n_min_high}' from public.app_config where key = 'score_model_f3'), '10'::jsonb, 'levels.n_min_high = 10');
select is((select value #> '{deal,kavak_offset}' from public.app_config where key = 'score_model_f3'), '9'::jsonb, 'deal.kavak_offset = 9');
select is((select value #> '{fit,unknown}' from public.app_config where key = 'score_model_f3'), '0.75'::jsonb, 'fit.unknown = 0.75');
select is((select count(*)::int from public.app_config a, jsonb_each(a.value->'rules') r
            where a.key = 'score_model_f3' and jsonb_typeof(r.value) = 'boolean' and r.value = 'true'::jsonb),
          4, 'the four rules are on (the recommended options of §14), as booleans');
select is((select count(*)::int from public.app_config a, jsonb_path_query(a.value, 'strict $.**') v
            where a.key = 'score_model_f3' and jsonb_typeof(v) = 'string'), 1, 'the only string is mode');
select is((select count(*)::int from public.app_config a, jsonb_path_query(a.value, 'strict $.**') v
            where a.key = 'score_model_f3' and jsonb_typeof(v) = 'number'), 23, 'every parameter is a number');

-- Values tuned from /admin/config survive a re-run of the migration's insert.
update public.app_config set value = jsonb_set(value, '{levels,c_high}', '0.84') where key = 'score_model_f3';
insert into public.app_config (key, value) values ('score_model_f3', '{"mode": "shadow"}'::jsonb) on conflict (key) do nothing;
select is((select value #> '{levels,c_high}' from public.app_config where key = 'score_model_f3'), '0.84'::jsonb,
          'a re-run keeps a tuned c_high');
select is((select count(*)::int from public.app_config where key = 'score_model_f3'), 1, 'a re-run adds no row');

-- ---------------------------------------------------------------- truncate (the DB tests reset with it)
select lives_ok($$truncate public.match_decisions$$, 'truncate is not blocked');
select is((select count(*)::int from public.match_decisions), 0, '... and empties the log');

select * from finish();
rollback;

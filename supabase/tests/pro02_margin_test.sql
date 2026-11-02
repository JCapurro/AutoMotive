-- PRO-02 ciclo 1 (migration 20261130120000_pro02_margin.sql). Run with: supabase test db
-- Run in an isolated local database; all fixtures roll back.
begin;
create extension if not exists pgtap with schema extensions;
select no_plan();

-- ---------------------------------------------------------------- schema and config
select has_column('public', 'matches', 'margin_ref', 'matches.margin_ref exists');
select col_type_is('public', 'matches', 'margin_ref', 'jsonb', '... as jsonb');
select has_column('public', 'search_profiles', 'opportunity_threshold_usd', 'search_profiles.opportunity_threshold_usd exists');
select ok(has_column_privilege('authenticated', 'public.search_profiles', 'opportunity_threshold_usd', 'UPDATE'),
          'authenticated can update opportunity_threshold_usd (column grant)');

select is((select value #> '{reconditioning,pct}' from public.app_config where key = 'dealer_margin'), '5'::jsonb,
          'dealer_margin.reconditioning.pct = 5');
select is((select value #> '{reconditioning,min_usd}' from public.app_config where key = 'dealer_margin'), '300'::jsonb,
          'dealer_margin.reconditioning.min_usd = 300');
select is((select value #> '{transfer,enabled}' from public.app_config where key = 'dealer_margin'), 'true'::jsonb,
          'dealer_margin.transfer.enabled = true');
select is((select value #> '{pro,dealer_margin}' from public.app_config where key = 'plan_limits'), 'true'::jsonb,
          'plan_limits.pro.dealer_margin = true');
select is((select value #> '{pro,min_threshold_usd}' from public.app_config where key = 'plan_limits'), '500'::jsonb,
          'plan_limits.pro.min_threshold_usd = 500');
select is((select value #> '{pass,dealer_margin}' from public.app_config where key = 'plan_limits'), null,
          '... only Pro (Particular has no key)');
select is((select value #> '{pro,threshold_alerts}' from public.app_config where key = 'plan_limits'), 'true'::jsonb,
          'the rest of Pro''s limits is untouched');

-- Re-running the plan_limits update keeps a value an admin changed.
update public.app_config set value = jsonb_set(value, '{pro,min_threshold_usd}', '800') where key = 'plan_limits';
update public.app_config
   set value = jsonb_set(value, '{pro}', '{"dealer_margin": true, "min_threshold_usd": 500}'::jsonb || (value->'pro'))
 where key = 'plan_limits' and jsonb_typeof(value->'pro') = 'object'
   and not (value->'pro' ? 'dealer_margin' and value->'pro' ? 'min_threshold_usd');
select is((select value #> '{pro,min_threshold_usd}' from public.app_config where key = 'plan_limits'), '800'::jsonb,
          'the migration''s update is idempotent and keeps an edited minimum');
update public.app_config set value = jsonb_set(value, '{pro,min_threshold_usd}', '500') where key = 'plan_limits';

select ok(not has_function_privilege('anon', 'public.my_match_margins(bigint[])', 'execute'), 'my_match_margins: not for anon');
select ok(has_function_privilege('authenticated', 'public.my_match_margins(bigint[])', 'execute'), 'my_match_margins: for authenticated');
select ok(has_function_privilege('authenticated', 'public.my_margin_access()', 'execute'), 'my_margin_access: for authenticated');
select ok(not has_function_privilege('authenticated', 'public.min_threshold_usd(uuid)', 'execute'), 'min_threshold_usd: worker only');
select ok(not has_column_privilege('authenticated', 'public.matches', 'margin_ref', 'SELECT'),
          'matches.margin_ref: not readable by authenticated (only through my_match_margins)');
select ok(not has_column_privilege('anon', 'public.matches', 'margin_ref', 'SELECT'), '... nor by anon');
select ok(has_column_privilege('authenticated', 'public.matches', 'price_ref', 'SELECT')
          and has_column_privilege('authenticated', 'public.matches', 'score', 'SELECT')
          and has_column_privilege('authenticated', 'public.matches', 'contact_questions', 'SELECT'),
          'the other columns of matches stay readable');
select ok(not has_function_privilege('anon', 'public.my_margin_sort_keys(bigint)', 'execute'), 'my_margin_sort_keys: not for anon');

-- ---------------------------------------------------------------- fixtures: a Pro, a Particular and an admin
insert into auth.users (instance_id, id, aud, role, email, created_at, updated_at) values
  ('00000000-0000-0000-0000-000000000000', 'c0200000-0000-0000-0000-000000000001', 'authenticated', 'authenticated', 'pro@pro02.test', now(), now()),
  ('00000000-0000-0000-0000-000000000000', 'c0200000-0000-0000-0000-000000000002', 'authenticated', 'authenticated', 'pass@pro02.test', now(), now()),
  ('00000000-0000-0000-0000-000000000000', 'c0200000-0000-0000-0000-000000000003', 'authenticated', 'authenticated', 'admin@pro02.test', now(), now());
update public.profiles p set plan = v.plan::public.user_plan, plan_expires_at = now() + interval '30 days', role = v.role::public.user_role
  from (values ('c0200000-0000-0000-0000-000000000001'::uuid, 'pro', 'user'),
               ('c0200000-0000-0000-0000-000000000002'::uuid, 'pass', 'user'),
               ('c0200000-0000-0000-0000-000000000003'::uuid, 'free', 'admin')) v (id, plan, role)
 where p.id = v.id;

select is(public.min_threshold_usd('c0200000-0000-0000-0000-000000000001'), 500, 'min_threshold_usd: Pro, its own 500');
select is(public.min_threshold_usd('c0200000-0000-0000-0000-000000000002'), 500, '... Particular: Pro''s (the feature gates it)');
select is(public.min_threshold_usd('c0200000-0000-0000-0000-000000000003'), 500, '... an admin: Pro''s');
select ok(public.plan_feature('c0200000-0000-0000-0000-000000000001', 'dealer_margin'), 'plan_feature dealer_margin: Pro yes');
select ok(not public.plan_feature('c0200000-0000-0000-0000-000000000002', 'dealer_margin'), '... Particular no');

insert into public.search_profiles (id, user_id, name, filters, bootstrapped_at) overriding system value values
  (9971, 'c0200000-0000-0000-0000-000000000001', 'Margen Pro', '{"make": "Pgtap", "model": "Margen"}', now()),
  (9972, 'c0200000-0000-0000-0000-000000000002', 'Margen Particular', '{"make": "Pgtap", "model": "Margen"}', now());

select throws_ok($$update public.search_profiles set opportunity_threshold_usd = 0 where id = 9971$$, '23514', null,
                 'opportunity_threshold_usd: 0 is rejected');
select lives_ok($$update public.search_profiles set opportunity_threshold_usd = 500 where id = 9971$$,
                'opportunity_threshold_usd: 500 is stored');

insert into public.listings (id, source, external_id, url, title, make, model, price, currency, price_usd, status)
overriding system value values
  (997001, 'mercadolibre', 'PRO02-1', 'https://example.test/pro02-1', 'Pgtap Margen 1', 'Pgtap', 'Margen', 10000, 'USD', 10000, 'active'),
  (997002, 'mercadolibre', 'PRO02-2', 'https://example.test/pro02-2', 'Pgtap Margen 2', 'Pgtap', 'Margen', 11000, 'USD', 11000, 'active'),
  (997003, 'mercadolibre', 'PRO02-3', 'https://example.test/pro02-3', 'Pgtap Margen 3', 'Pgtap', 'Margen', 12000, 'USD', 12000, 'active');

-- Scores and margins in opposite orders; 997003 has no margin.
insert into public.matches (id, search_profile_id, listing_id, score, level, score_breakdown, match_reasons, scoring_version, margin_ref)
overriding system value values
  (99710001, 9971, 997001, 90, 'good', '{}', '{}', 'test', '{"v": 1, "gross_margin_usd": {"min": 300, "max": 400}}'),
  (99710002, 9971, 997002, 80, 'good', '{}', '{}', 'test', '{"v": 1, "gross_margin_usd": {"min": 1500, "max": 1700}}'),
  (99710003, 9971, 997003, 70, 'good', '{}', '{}', 'test', null),
  (99720001, 9972, 997001, 90, 'good', '{}', '{}', 'test', '{"v": 1, "gross_margin_usd": {"min": 300, "max": 400}}'),
  (99720002, 9972, 997002, 80, 'good', '{}', '{}', 'test', '{"v": 1, "gross_margin_usd": {"min": 1500, "max": 1700}}');

-- ---------------------------------------------------------------- the Pro
set local role authenticated;
set local request.jwt.claims = '{"sub": "c0200000-0000-0000-0000-000000000001", "role": "authenticated"}';

select is(public.my_margin_access(), '{"enabled": true, "min_threshold_usd": 500}'::jsonb, 'my_margin_access: Pro');
select results_eq($$select match_id from public.my_match_margins(array[99710001, 99710002, 99710003, 99720001]::bigint[]) order by 1$$,
                  $$values (99710001::bigint), (99710002::bigint)$$,
                  'my_match_margins: the Pro''s own matches with a margin, never another user''s');
select results_eq($$select listing_id from public.search_results(9971, 'all', 'margin')$$,
                  $$values (997002::bigint), (997001::bigint), (997003::bigint)$$,
                  'search_results margin: by the margin''s low end, without margin last');
select is((select count(*)::int from public.my_margin_sort_keys(9972)), 0,
          'my_margin_sort_keys: never another user''s search');
select throws_ok($$select margin_ref from public.matches where id = 99710001$$, '42501', null,
                 'the Pro cannot read matches.margin_ref directly either');
select results_eq($$select listing_id from public.search_results(9971, 'all', 'score')$$,
                  $$values (997001::bigint), (997002::bigint), (997003::bigint)$$, 'search_results score unchanged');

reset role;

-- ---------------------------------------------------------------- the Particular
set local role authenticated;
set local request.jwt.claims = '{"sub": "c0200000-0000-0000-0000-000000000002", "role": "authenticated"}';

select is(public.my_margin_access()->'enabled', 'false'::jsonb, 'my_margin_access: Particular, not enabled');
select is((select count(*)::int from public.my_match_margins(array[99720001, 99720002]::bigint[])), 0,
          'my_match_margins: nothing without the feature, even of the own matches');
select throws_ok($$select margin_ref from public.matches where id = 99720001$$, '42501', null,
                 'matches.margin_ref: the Particular cannot read it through PostgREST/RLS');
select is((select count(*)::int from public.matches where search_profile_id = 9972), 2,
          '... but still reads its own matches');
select is((select count(*)::int from public.my_margin_sort_keys(9972)), 0,
          'my_margin_sort_keys: nothing without the feature, even of the own search');
select is((select array_agg(listing_id) from public.search_results(9972, 'all', 'margin')),
          (select array_agg(listing_id) from public.search_results(9972, 'all', 'recent')),
          'search_results margin without the feature: the recent order');

reset role;

-- ---------------------------------------------------------------- an admin
set local role authenticated;
set local request.jwt.claims = '{"sub": "c0200000-0000-0000-0000-000000000003", "role": "authenticated"}';
select is(public.my_margin_access(), '{"enabled": true, "min_threshold_usd": 500}'::jsonb,
          'my_margin_access: an admin has the feature and Pro''s minimum');
reset role;

select * from finish();
rollback;

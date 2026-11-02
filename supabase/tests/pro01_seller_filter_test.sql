-- PRO-01 (migrations 20261128120000_pro01_seller_filter_contact.sql and
-- 20261128120100_pro01_preview_seller.sql), docs/superpowers/specs/2026-10-31-pro01-contacto-design.md:
-- the plan keys, the shape of filters.seller_types, profiles.contact_template,
-- matches.contact_questions and preview_search's strict seller filter. The
-- worker side is tested in worker/tests/test_pro01_postgres.py.
-- Run with: supabase test db
begin;
create extension if not exists pgtap with schema extensions;
select no_plan();

update public.app_config set value = jsonb_set(value, '{enforced}', 'false') where key = 'plan_limits';

-- ---------------------------------------------------------------- users
-- F free, P Particular (pass), R Pro, A admin (free plan).
insert into auth.users (instance_id, id, aud, role, email, created_at, updated_at) values
  ('00000000-0000-0000-0000-000000000000', 'c1000000-0000-0000-0000-000000000001', 'authenticated', 'authenticated', 'f@pro01.test', now(), now()),
  ('00000000-0000-0000-0000-000000000000', 'c1000000-0000-0000-0000-000000000002', 'authenticated', 'authenticated', 'p@pro01.test', now(), now()),
  ('00000000-0000-0000-0000-000000000000', 'c1000000-0000-0000-0000-000000000003', 'authenticated', 'authenticated', 'r@pro01.test', now(), now()),
  ('00000000-0000-0000-0000-000000000000', 'c1000000-0000-0000-0000-000000000004', 'authenticated', 'authenticated', 'a@pro01.test', now(), now());
update public.profiles p set plan = v.plan::public.user_plan, plan_expires_at = v.expires, role = v.role::public.user_role
  from (values
    ('c1000000-0000-0000-0000-000000000001'::uuid, 'free', null::timestamptz, 'user'),
    ('c1000000-0000-0000-0000-000000000002'::uuid, 'pass', now() + interval '20 days', 'user'),
    ('c1000000-0000-0000-0000-000000000003'::uuid, 'pro',  now() + interval '20 days', 'user'),
    ('c1000000-0000-0000-0000-000000000004'::uuid, 'free', null, 'admin')
  ) as v (id, plan, expires, role)
 where p.id = v.id;

-- ---------------------------------------------------------------- plan keys
select is((select value->'pro'->>'seller_filter' from public.app_config where key = 'plan_limits'), 'true',
          'plan_limits.pro.seller_filter is on');
select is((select value->'pro'->>'contact_email' from public.app_config where key = 'plan_limits'), 'true',
          'plan_limits.pro.contact_email is on');
select is((select value->'pass'->>'seller_filter' from public.app_config where key = 'plan_limits'), null,
          'Particular has no seller_filter (it keeps the soft preference)');
select ok(public.plan_feature('c1000000-0000-0000-0000-000000000003', 'seller_filter'), 'plan_feature: Pro has seller_filter');
select ok(public.plan_feature('c1000000-0000-0000-0000-000000000003', 'contact_email'), '... and contact_email');
select ok(public.plan_feature('c1000000-0000-0000-0000-000000000004', 'seller_filter'), '... an admin has every feature');
select ok(not public.plan_feature('c1000000-0000-0000-0000-000000000002', 'seller_filter'), '... Particular does not');
select ok(not public.plan_feature('c1000000-0000-0000-0000-000000000002', 'contact_email'), '... nor the email block');
select ok(not public.plan_feature('c1000000-0000-0000-0000-000000000001', 'seller_filter'), '... nor the free plan');

-- ---------------------------------------------------------------- search_filters_problem
select is(public.search_filters_problem('{"make": "Ford", "model": "Fiesta", "seller_types": ["private"]}'), null,
          'seller_types ["private"] is valid');
select is(public.search_filters_problem('{"make": "Ford", "model": "Fiesta", "seller_types": ["dealer"]}'), null,
          '... ["dealer"] too');
select is(public.search_filters_problem('{"make": "Ford", "model": "Fiesta"}'), null, '... and absent');
select is(public.search_filters_problem('{"make": "Ford", "model": "Fiesta", "seller_types": null}'), null,
          '... and JSON null');
select is(public.search_filters_problem('{"make": "Ford", "model": "Fiesta", "seller_types": []}'), 'invalid_filters',
          'an empty array is rejected (no filter is no key)');
select is(public.search_filters_problem('{"make": "Ford", "model": "Fiesta", "seller_types": ["dealer_inferred"]}'),
          'invalid_filters', 'dealer_inferred is not a value: ["dealer"] includes it');
select is(public.search_filters_problem('{"make": "Ford", "model": "Fiesta", "seller_types": ["private", "dealer"]}'),
          'invalid_filters', 'both types is no filter: rejected');
select is(public.search_filters_problem('{"make": "Ford", "model": "Fiesta", "seller_types": "private"}'),
          'invalid_filters', 'a string is rejected');
select is(public.search_filters_problem('{"make": "Ford", "model": "Fiesta", "seller_types": {"a": 1}}'),
          'invalid_filters', 'an object is rejected');
select is(public.search_filters_problem('{"make": false}'), 'invalid_filters', 'the old rules still hold');
select is((select provolatile from pg_proc where oid = 'public.search_filters_problem(jsonb)'::regprocedure), 'i',
          'search_filters_problem is still immutable');
select ok(not has_function_privilege('authenticated', 'public.search_filters_problem(jsonb)', 'execute'),
          '... and still server-only');

insert into public.search_profiles (id, user_id, name, filters, enabled) overriding system value values
  (9901, 'c1000000-0000-0000-0000-000000000003', 'Strict', '{"make": "Pgtap", "model": "Carro", "seller_types": ["private"]}', true);
select throws_ok($$update public.search_profiles set filters = '{"make": "Pgtap", "model": "Carro", "seller_types": ["x"]}' where id = 9901$$,
                 '22023', 'invalid_filters', 'the trigger rejects a malformed seller_types');

-- ---------------------------------------------------------------- profiles.contact_template
select has_column('public', 'profiles', 'contact_template', 'profiles.contact_template exists');
select col_type_is('public', 'profiles', 'contact_template', 'text', '... as text');
select ok(has_column_privilege('authenticated', 'public.profiles', 'contact_template', 'update'),
          'authenticated can update its own contact_template');
select lives_ok($$update public.profiles set contact_template = null where id = 'c1000000-0000-0000-0000-000000000003'$$,
                'null is the default template');
select lives_ok($$update public.profiles set contact_template = repeat('a', 500) where id = 'c1000000-0000-0000-0000-000000000003'$$,
                '500 characters fit');
select throws_ok($$update public.profiles set contact_template = repeat('a', 501) where id = 'c1000000-0000-0000-0000-000000000003'$$,
                 '23514', null, '501 do not');
select throws_ok($$update public.profiles set contact_template = '' where id = 'c1000000-0000-0000-0000-000000000003'$$,
                 '23514', null, 'an empty template is rejected (null is the default)');
select throws_ok($$update public.profiles set contact_template = E'  \n ' where id = 'c1000000-0000-0000-0000-000000000003'$$,
                 '23514', null, '... and one of only spaces');
update public.profiles set contact_template = null where id = 'c1000000-0000-0000-0000-000000000003';

-- ---------------------------------------------------------------- matches.contact_questions
select has_column('public', 'matches', 'contact_questions', 'matches.contact_questions exists');
select col_type_is('public', 'matches', 'contact_questions', 'text[]', '... as text[]');
select col_is_null('public', 'matches', 'contact_questions', '... nullable (rows before PRO-01)');

-- ---------------------------------------------------------------- preview_search
insert into public.listings (id, source, external_id, url, title, make, model, year, price, currency,
                             price_usd, seller_type, dealer_inferred, first_seen_at)
overriding system value values
  (9911, 'mercadolibre', 'P01-1', 'https://example.test/p01-1', 'Pgtap Carro', 'Pgtap', 'Carro', 2018, 15000, 'USD', 15000, 'private', false, now()),
  (9912, 'mercadolibre', 'P01-2', 'https://example.test/p01-2', 'Pgtap Carro', 'Pgtap', 'Carro', 2018, 15000, 'USD', 15000, 'dealer', false, now()),
  (9913, 'mercadolibre', 'P01-3', 'https://example.test/p01-3', 'Pgtap Carro', 'Pgtap', 'Carro', 2018, 15000, 'USD', 15000, 'private', true, now()),
  (9914, 'mercadolibre', 'P01-4', 'https://example.test/p01-4', 'Pgtap Carro', 'Pgtap', 'Carro', 2018, 15000, 'USD', 15000, null, false, now());

set local role authenticated;
set local request.jwt.claims = '{"sub": "c1000000-0000-0000-0000-000000000003", "role": "authenticated"}';
select is((public.preview_search('{"make": "Pgtap", "model": "Carro"}')->>'count')::int, 4,
          'preview without seller_types: every seller');
select is((public.preview_search('{"make": "Pgtap", "model": "Carro", "seller_types": ["private"]}')->>'count')::int, 2,
          'Pro, only private: no dealer, no «posible agencia», the unknown seller passes');
select is((public.preview_search('{"make": "Pgtap", "model": "Carro", "seller_types": ["dealer"]}')->>'count')::int, 3,
          'Pro, only dealers: dealers, «posibles agencias» and the unknown seller');

set local request.jwt.claims = '{"sub": "c1000000-0000-0000-0000-000000000002", "role": "authenticated"}';
select is((public.preview_search('{"make": "Pgtap", "model": "Carro", "seller_types": ["private"]}')->>'count')::int, 4,
          'Particular: seller_types is ignored (a soft preference does not filter)');
reset role;

select * from finish();
rollback;

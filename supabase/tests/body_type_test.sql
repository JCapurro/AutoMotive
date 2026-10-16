-- Carrocería and model-less searches (migration 20261030120000_body_type.sql,
-- docs/CARROCERIA.md). Run with: supabase test db
begin;
create extension if not exists pgtap with schema extensions;
select plan(58);

-- ---------------------------------------------------------------- app_config, as the migration left it
select is((select value->'pass'->>'model_less_search' from public.app_config where key = 'plan_limits'), 'true',
          'plan_limits: Particular searches without a model');
select is((select value->'pro'->>'model_less_search' from public.app_config where key = 'plan_limits'), 'true',
          '... and Pro');
select is((select value->'free'->>'model_less_search' from public.app_config where key = 'plan_limits'), null,
          '... the free trial doesn''t');
select is((select value from public.app_config where key = 'body_type_targets'),
          '{"sources": ["mercadolibre", "kavak"], "interval_seconds": 1800}'::jsonb,
          'body_type_targets: Mercado Libre and Kavak every 30 minutes');

-- Known switches, whatever the database has (the plan features stay as above).
update public.app_config set value = jsonb_set(value, '{enforced}', 'false') where key = 'plan_limits';
insert into public.app_config (key, value) values ('commercial_pilot', '{"enabled": true}')
on conflict (key) do update set value = excluded.value;
insert into public.app_config (key, value) values ('lifecycle_emails', '{"enabled": true, "kinds": {"count_after_expiry": true}}')
on conflict (key) do update set value = excluded.value;

-- ---------------------------------------------------------------- users
-- F free (trial not started), F2 free, P Particular, R Pro, A admin,
-- X Particular (reactivation), E a Particular pass that ended (2.5).
insert into auth.users (instance_id, id, aud, role, email, created_at, updated_at) values
  ('00000000-0000-0000-0000-000000000000', 'b1000000-0000-0000-0000-000000000001', 'authenticated', 'authenticated', 'f@bt.test', now(), now()),
  ('00000000-0000-0000-0000-000000000000', 'b1000000-0000-0000-0000-000000000002', 'authenticated', 'authenticated', 'f2@bt.test', now(), now()),
  ('00000000-0000-0000-0000-000000000000', 'b1000000-0000-0000-0000-000000000003', 'authenticated', 'authenticated', 'p@bt.test', now(), now()),
  ('00000000-0000-0000-0000-000000000000', 'b1000000-0000-0000-0000-000000000004', 'authenticated', 'authenticated', 'r@bt.test', now(), now()),
  ('00000000-0000-0000-0000-000000000000', 'b1000000-0000-0000-0000-000000000005', 'authenticated', 'authenticated', 'a@bt.test', now(), now()),
  ('00000000-0000-0000-0000-000000000000', 'b1000000-0000-0000-0000-000000000006', 'authenticated', 'authenticated', 'x@bt.test', now(), now()),
  ('00000000-0000-0000-0000-000000000000', 'b1000000-0000-0000-0000-000000000007', 'authenticated', 'authenticated', 'e@bt.test', now(), now());

update public.profiles p set plan = v.plan::public.user_plan, plan_expires_at = v.expires,
                             role = v.role::public.user_role, default_channels = '{email,web}'
  from (values
    ('b1000000-0000-0000-0000-000000000001'::uuid, 'free', null::timestamptz, 'user'),
    ('b1000000-0000-0000-0000-000000000002'::uuid, 'free', null, 'user'),
    ('b1000000-0000-0000-0000-000000000003'::uuid, 'pass', now() + interval '20 days', 'user'),
    ('b1000000-0000-0000-0000-000000000004'::uuid, 'pro',  now() + interval '20 days', 'user'),
    ('b1000000-0000-0000-0000-000000000005'::uuid, 'free', null, 'admin'),
    ('b1000000-0000-0000-0000-000000000006'::uuid, 'pass', now() + interval '20 days', 'user'),
    ('b1000000-0000-0000-0000-000000000007'::uuid, 'pass', now() - interval '2 days', 'user')
  ) as v (id, plan, expires, role)
 where p.id = v.id;

-- ---------------------------------------------------------------- schema
select throws_ok($$insert into public.listings (source, external_id, url, title, body_type)
                   values ('mercadolibre', 'BT-X', 'https://example.test/bt-x', 'x', 'van')$$,
                 '23514', null, 'listings.body_type: only the 9 codes');
select throws_ok($$update public.vehicle_catalog set body_types = '{suv,van}'
                    where id = (select min(id) from public.vehicle_catalog)$$,
                 '23514', null, 'vehicle_catalog.body_types: only the 9 codes');
insert into public.crawl_targets (source, query) values ('kavak', '{"inventory": true}') on conflict do nothing;
select lives_ok($$insert into public.crawl_targets (source, body_type) values ('kavak', 'suv'), ('kavak', 'pickup')$$,
                'crawl_targets: a target per (source, body type), next to the inventory one');
select throws_ok($$insert into public.crawl_targets (source, body_type) values ('kavak', 'suv')$$,
                 '23505', null, '... only one');
select throws_ok($$insert into public.crawl_targets (source, body_type) values ('kavak', 'van')$$,
                 '23514', null, '... of a known body type');
select is((select attname::text from pg_attribute
            where attrelid = 'public.match_cards'::regclass and attnum > 0 and not attisdropped
            order by attnum desc limit 1), 'body_type', 'match_cards: body_type is the last column');
select ok(has_column_privilege('authenticated', 'public.search_profiles', 'opportunity_threshold_pct', 'UPDATE'),
          'the web can edit a search: it always sends opportunity_threshold_pct');

-- ---------------------------------------------------------------- the guard, pilot (enforced = false)
select lives_ok($$insert into public.search_profiles (id, user_id, name, filters) overriding system value values
                  (9811, 'b1000000-0000-0000-0000-000000000002', 'SUV hasta USD 20.000',
                   '{"body_types": ["suv"], "price_max": 20000, "currency": "USD"}')$$,
                'pilot: a free model-less search goes through, like max_profiles');
select is((select count(*)::int from public.events
            where user_id = 'b1000000-0000-0000-0000-000000000002' and name = 'plan_limit_hit'
              and props->>'limit' = 'model_less_search' and props->>'search_profile_id' = '9811'), 1,
          '... and records plan_limit_hit');
select throws_ok($$insert into public.search_profiles (user_id, name, filters)
                   values ('b1000000-0000-0000-0000-000000000002', 'x', '{}')$$,
                 '22023', 'search_needs_model_or_body_type', 'pilot: no model and no body types is still rejected');
select ok(public.search_access_active(9811), 'pilot: the free model-less search runs');
update public.search_profiles set filters = filters || '{"price_max": 18000}' where id = 9811;
select is((select count(*)::int from public.events
            where name = 'plan_limit_hit' and props->>'limit' = 'model_less_search'
              and props->>'search_profile_id' = '9811'), 1,
          '... measured once, not again on every edit');

-- ---------------------------------------------------------------- the guard, enforced
update public.app_config set value = jsonb_set(value, '{enforced}', 'true') where key = 'plan_limits';

-- F, through the API as the web would.
set local role authenticated;
set local request.jwt.claims = '{"sub": "b1000000-0000-0000-0000-000000000001", "role": "authenticated"}';
select throws_ok($$insert into public.search_profiles (user_id, name, filters)
                   values ('b1000000-0000-0000-0000-000000000001', 'SUV',
                           '{"body_types": ["suv"], "price_max": 20000, "currency": "USD"}')$$,
                 '42501', 'plan_feature_unavailable', 'free: no model-less search');
-- The database and the worker read "model-less" the same: a make that isn't
-- text can't slip a search past the plan check, and blank text is none.
select throws_ok($$insert into public.search_profiles (user_id, name, filters)
                   values ('b1000000-0000-0000-0000-000000000001', 'SUV',
                           '{"make": false, "body_types": ["suv"], "price_max": 20000}')$$,
                 '22023', 'invalid_filters', 'free: a make that is not text is rejected');
select throws_ok($$insert into public.search_profiles (user_id, name, filters)
                   values ('b1000000-0000-0000-0000-000000000001', 'SUV',
                           '{"make": [], "model": 0, "body_types": ["suv"], "price_max": 20000}')$$,
                 '22023', 'invalid_filters', '... nor a list or a number');
select throws_ok($$insert into public.search_profiles (user_id, name, filters)
                   values ('b1000000-0000-0000-0000-000000000001', 'SUV',
                           '{"make": "\t", "model": " \n", "body_types": ["suv"], "price_max": 20000}')$$,
                 '42501', 'plan_feature_unavailable', '... and a blank make and model are none');
reset role;
select is(array[public.search_is_model_less('{"make": null, "model": "\t "}'),
                public.search_is_model_less('{"make": "Ford"}'),
                public.search_is_model_less('{"make": false}')],
          array[true, false, false], 'search_is_model_less: null and blank are none, anything else a vehicle');
select is(public.search_filters_problem('{"make": "Ford", "body_types": ["suv", 1]}'), 'invalid_filters',
          'search_filters_problem: body_types must be text');
select is((select free_trial_started_at from public.profiles where id = 'b1000000-0000-0000-0000-000000000001'),
          null, '... and the rejected search doesn''t start the trial');
select lives_ok($$insert into public.search_profiles (id, user_id, name, filters) overriding system value values
                  (9831, 'b1000000-0000-0000-0000-000000000001', 'Pgtap Carro',
                   '{"make": "Pgtap", "model": "Carro", "body_types": ["suv"]}')$$,
                'free: body types within a model (no price needed)');
select lives_ok($$insert into public.search_profiles (id, user_id, name, filters, enabled) overriding system value values
                  (9832, 'b1000000-0000-0000-0000-000000000001', 'SUV',
                   '{"body_types": ["suv"], "price_max": 20000}', false)$$,
                'free: a paused model-less search can be stored');
select throws_ok($$update public.search_profiles set enabled = true where id = 9832$$,
                 '42501', 'plan_feature_unavailable',
                 '... not enabled (checked before max_profiles, which would also reject it)');

-- P: Particular. The web may send empty make and model.
select lives_ok($$insert into public.search_profiles (id, user_id, name, filters) overriding system value values
                  (9821, 'b1000000-0000-0000-0000-000000000003', 'SUV hasta USD 20.000',
                   '{"make": "", "model": "", "body_types": ["suv"], "price_max": 20000, "currency": "USD"}')$$,
                'pass: a model-less search');
select throws_ok($$insert into public.search_profiles (user_id, name, filters)
                   values ('b1000000-0000-0000-0000-000000000003', 'x', '{"price_max": 20000}')$$,
                 '22023', 'search_needs_model_or_body_type', '... needs body types');
select throws_ok($$insert into public.search_profiles (user_id, name, filters)
                   values ('b1000000-0000-0000-0000-000000000003', 'x', '{"body_types": [], "price_max": 20000}')$$,
                 '22023', 'search_needs_model_or_body_type', '... at least one');
select throws_ok($$insert into public.search_profiles (user_id, name, filters)
                   values ('b1000000-0000-0000-0000-000000000003', 'x', '{"body_types": ["suv", "van"], "price_max": 20000}')$$,
                 '22023', 'search_needs_model_or_body_type', '... known ones');
select throws_ok($$insert into public.search_profiles (user_id, name, filters)
                   values ('b1000000-0000-0000-0000-000000000003', 'x', '{"body_types": ["suv"]}')$$,
                 '22023', 'search_needs_max_price', '... and a max price');
select throws_ok($$insert into public.search_profiles (user_id, name, filters)
                   values ('b1000000-0000-0000-0000-000000000003', 'x', '{"body_types": ["suv"], "price_max": 0}')$$,
                 '22023', 'search_needs_max_price', '... above zero');
select throws_ok($$update public.search_profiles set filters = filters - 'price_max' where id = 9821$$,
                 '22023', 'search_needs_max_price', '... also when edited');

-- R (Pro) and A (admin).
select lives_ok($$insert into public.search_profiles (user_id, name, filters)
                  values ('b1000000-0000-0000-0000-000000000004', 'SUV o Pick-up',
                          '{"body_types": ["suv", "pickup"], "price_max": 25000000, "currency": "ARS"}')$$,
                'pro: a model-less search');
select lives_ok($$insert into public.search_profiles (user_id, name, filters)
                  values ('b1000000-0000-0000-0000-000000000005', 'Rural',
                          '{"body_types": ["rural"], "price_max": 15000}')$$,
                'admin: a model-less search');
select is((select count(*)::int from public.events
            where name = 'plan_limit_hit' and props->>'limit' = 'model_less_search'
              and user_id in ('b1000000-0000-0000-0000-000000000003', 'b1000000-0000-0000-0000-000000000004',
                              'b1000000-0000-0000-0000-000000000005')), 0,
          '... paid plans and admins hit no limit');

-- ---------------------------------------------------------------- search_access_active
update public.profiles set free_trial_started_at = now() - interval '1 hour'
 where id = 'b1000000-0000-0000-0000-000000000002';
select ok(not public.search_access_active(9811), 'enforced: a trial''s model-less search doesn''t run');
select ok(public.search_access_active(9821), '... a Particular one does');
select is(public.expire_commercial_access('b1000000-0000-0000-0000-000000000002'), 1,
          'expire_commercial_access pauses it');
select lives_ok($$update public.search_profiles set filters = filters || '{"make": "Pgtap", "model": "Carro"}', enabled = true
                   where id = 9811$$, '... with a model it can be enabled again');
select ok(public.search_access_active(9811), '... and it runs');

-- ---------------------------------------------------------------- reactivation
-- X: two searches paused by the plan; the newest is a legacy one without
-- make, model or body types, which the trigger would reject.
insert into public.search_profiles (id, user_id, name, filters, enabled) overriding system value values
  (9841, 'b1000000-0000-0000-0000-000000000006', 'Pgtap Carro', '{"make": "Pgtap", "model": "Carro"}', false),
  (9842, 'b1000000-0000-0000-0000-000000000006', 'Viejo', '{}', false);
insert into public.events (user_id, name, props, created_at) values
  ('b1000000-0000-0000-0000-000000000006', 'search_paused_by_plan', '{"search_profile_id": 9841}', now() - interval '2 days'),
  ('b1000000-0000-0000-0000-000000000006', 'search_paused_by_plan', '{"search_profile_id": 9842}', now() - interval '1 day');
select is(public.reactivate_paused_searches('b1000000-0000-0000-0000-000000000006'), 1,
          'reactivation skips the search the trigger would reject');
select results_eq($$select id, enabled from public.search_profiles
                     where user_id = 'b1000000-0000-0000-0000-000000000006' order by id$$,
                  $$values (9841::bigint, true), (9842::bigint, false)$$,
                  '... and still enables the rest');

-- ---------------------------------------------------------------- count after expiry (2.5)
insert into public.search_profiles (id, user_id, name, filters, enabled) overriding system value values
  (9851, 'b1000000-0000-0000-0000-000000000007', 'Pgtap Carro', '{"make": "Pgtap", "model": "Carro"}', false),
  (9852, 'b1000000-0000-0000-0000-000000000007', 'SUV', '{"body_types": ["suv"], "price_max": 20000}', false);
insert into public.events (user_id, name, props) values
  ('b1000000-0000-0000-0000-000000000007', 'search_paused_by_plan', '{"search_profile_id": 9851}'),
  ('b1000000-0000-0000-0000-000000000007', 'search_paused_by_plan', '{"search_profile_id": 9852}');
select results_eq($$select search_profile_id from public.count_after_expiry_searches()
                     where user_id = 'b1000000-0000-0000-0000-000000000007'$$,
                  $$values (9851::bigint)$$, '2.5 counts only the searches with a model');

-- ---------------------------------------------------------------- preview_search
-- Only these listings have a body type here.
update public.listings set body_type = null where body_type is not null;
insert into public.fx_rates (date, kind, rate, source) values ('2999-01-01', 'blue', 1000, 'test');
insert into public.listings (id, source, external_id, url, title, make, model, year, price, currency,
                             price_usd, body_type, first_seen_at)
overriding system value values
  (9801, 'mercadolibre', 'BT-1', 'https://example.test/bt-1', 'Pgtap Carro SUV', 'Pgtap', 'Carro', 2018,
   15000, 'USD', 15000, 'suv', now() - interval '1 hour'),
  (9802, 'mercadolibre', 'BT-2', 'https://example.test/bt-2', 'Pgtap Carro', 'Pgtap', 'Carro', 2018,
   15000, 'USD', 15000, null, now() - interval '2 hours'),
  (9803, 'mercadolibre', 'BT-3', 'https://example.test/bt-3', 'Pgtap Carro sedán', 'Pgtap', 'Carro', 2018,
   15000, 'USD', 15000, 'sedan', now() - interval '3 hours'),
  (9804, 'kavak', 'BT-4', 'https://example.test/bt-4', 'Otra Cosa', 'Otra', 'Cosa', 2019,
   30000, 'USD', 30000, 'suv', now() - interval '4 hours'),
  (9805, 'kavak', 'BT-5', 'https://example.test/bt-5', 'Otra Cosa pick-up', 'Otra', 'Cosa', 2019,
   18000000, 'ARS', 18000, 'pickup', now() - interval '5 hours'),
  (9806, 'mercadolibre', 'BT-6', 'https://example.test/bt-6', 'Chery Tiggo', null, null, 2020,
   12000, 'USD', 12000, 'suv', now());

select is((public.preview_search('{"body_types": ["suv"], "price_max": 20000, "currency": "USD"}')->>'count')::int, 2,
          'preview without a model: every make, the price cap, and an unknown body type doesn''t count');
select is((public.preview_search('{"body_types": ["suv", "pickup"], "price_max": 20000, "currency": "USD"}')->>'count')::int, 3,
          '... several body types (an ARS listing compared in USD)');
select is((public.preview_search('{"make": "", "model": " ", "body_types": ["suv"], "price_max": 20000}')->>'count')::int, 2,
          '... empty make and model are no model');
select is(public.preview_search('{"body_types": ["suv"], "price_max": 20000}')->'sample'->0->>'body_type', 'suv',
          '... the sample carries the body type');
select is((public.preview_search('{"make": "Pgtap", "model": "Carro", "body_types": ["suv"]}')->>'count')::int, 2,
          'preview within a model: an unknown body type doesn''t discard, another one does');
select is((public.preview_search('{"make": "Pgtap", "body_types": ["sedan"]}')->>'count')::int, 2,
          '... within a make too');
select is((public.preview_search('{}')->>'count')::int
          + (public.preview_search('{"body_types": []}')->>'count')::int, 0,
          'preview: empty filters count nothing');
select is((public.preview_search('{"model": "Carro", "body_types": ["suv"]}')->>'count')::int, 0,
          'preview: a model still needs its make');

set local role authenticated;
set local request.jwt.claims = '{"sub": "b1000000-0000-0000-0000-000000000001", "role": "authenticated"}';
select is((public.preview_search('{"body_types": ["suv"], "price_max": 20000}')->>'count')::int, 2,
          'preview: the count isn''t gated by the plan (listings are readable anyway)');
reset role;

-- ---------------------------------------------------------------- what the web reads
insert into public.matches (search_profile_id, listing_id, score, level, score_breakdown, match_reasons, scoring_version)
values (9821, 9801, 90, 'high', '{}', '{}', 'test');

set local role authenticated;
set local request.jwt.claims = '{"sub": "b1000000-0000-0000-0000-000000000003", "role": "authenticated"}';
select is((select body_type from public.match_cards where search_profile_id = 9821), 'suv', 'match_cards.body_type');
select is((select body_type from public.search_results(9821)), 'suv', 'search_results returns it');
select is((select body_type from public.recent_opportunities() where listing_id = 9801), 'suv',
          'recent_opportunities too');
select ok(public.record_purchase(9801, 9821, 15000, 'USD', null) > 0, 'record_purchase');
select is((select vehicle->>'body_type' from public.owned_vehicles where listing_id = 9801), 'suv',
          '... keeps the body type in the snapshot');
reset role;

select * from finish();
rollback;

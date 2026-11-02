-- PRO-01, Respuestas de Juan 02/11 (migration 20261129120000_pro01_plan_change_rematch.sql,
-- docs/superpowers/specs/2026-10-31-pro01-contacto-design.md): a change of plan
-- that flips plan_feature('seller_filter') marks the user's strict searches
-- for rematch, whichever path wrote it (a profile write, the time-based expiry
-- swept by expire_commercial_access, plan_limits edited, a search moved to
-- another user); match_cards.seller_unknown. Every payment path end to end,
-- and the rematch itself, are in worker/tests/test_pro01_plan_change_postgres.py.
-- Run with: supabase test db
begin;
create extension if not exists pgtap with schema extensions;
select no_plan();

update public.app_config set value = jsonb_set(value, '{enforced}', 'false') where key = 'plan_limits';

-- ---------------------------------------------------------------- users
-- R Pro, P Particular (pass), F free, E Pro that will expire, T telegram-like free owner.
insert into auth.users (instance_id, id, aud, role, email, created_at, updated_at) values
  ('00000000-0000-0000-0000-000000000000', 'c2000000-0000-0000-0000-000000000001', 'authenticated', 'authenticated', 'r@pro01pc.test', now(), now()),
  ('00000000-0000-0000-0000-000000000000', 'c2000000-0000-0000-0000-000000000002', 'authenticated', 'authenticated', 'p@pro01pc.test', now(), now()),
  ('00000000-0000-0000-0000-000000000000', 'c2000000-0000-0000-0000-000000000003', 'authenticated', 'authenticated', 'f@pro01pc.test', now(), now()),
  ('00000000-0000-0000-0000-000000000000', 'c2000000-0000-0000-0000-000000000004', 'authenticated', 'authenticated', 'e@pro01pc.test', now(), now()),
  ('00000000-0000-0000-0000-000000000000', 'c2000000-0000-0000-0000-000000000005', 'authenticated', 'authenticated', 't@pro01pc.test', now(), now());

select has_column('public', 'profiles', 'seller_filter_access', 'profiles.seller_filter_access exists');
select col_not_null('public', 'profiles', 'seller_filter_access', '... not null');
select ok(not (select seller_filter_access from public.profiles where id = 'c2000000-0000-0000-0000-000000000001'),
          'a new free account starts without it (insert trigger)');
select ok(not has_column_privilege('authenticated', 'public.profiles', 'seller_filter_access', 'update'),
          'a user cannot write it');

update public.profiles p set plan = v.plan::public.user_plan, plan_expires_at = v.expires
  from (values
    ('c2000000-0000-0000-0000-000000000001'::uuid, 'pro',  now() + interval '20 days'),
    ('c2000000-0000-0000-0000-000000000002'::uuid, 'pass', now() + interval '20 days'),
    ('c2000000-0000-0000-0000-000000000003'::uuid, 'free', null::timestamptz),
    ('c2000000-0000-0000-0000-000000000004'::uuid, 'pro',  now() + interval '20 days'),
    ('c2000000-0000-0000-0000-000000000005'::uuid, 'free', null)
  ) as v (id, plan, expires)
 where p.id = v.id;

select is((select array_agg(seller_filter_access order by id) from public.profiles where email like '%@pro01pc.test'),
          array[true, false, false, true, false], 'the trigger stores the flag: Pro on, Particular and free off');

-- One strict and one plain search per user; 99x1 strict, 99x2 plain.
insert into public.search_profiles (id, user_id, name, filters, enabled, radius_km) overriding system value values
  (9921, 'c2000000-0000-0000-0000-000000000001', 'R strict', '{"make": "Pgtap", "model": "Carro", "seller_types": ["private"]}', true, 1),
  (9922, 'c2000000-0000-0000-0000-000000000001', 'R plain',  '{"make": "Pgtap", "model": "Carro"}', true, 2),
  (9931, 'c2000000-0000-0000-0000-000000000002', 'P strict', '{"make": "Pgtap", "model": "Carro", "seller_types": ["dealer"]}', true, 1),
  (9932, 'c2000000-0000-0000-0000-000000000002', 'P plain',  '{"make": "Pgtap", "model": "Carro", "seller_types": null}', true, 2),
  (9941, 'c2000000-0000-0000-0000-000000000003', 'F strict', '{"make": "Pgtap", "model": "Carro", "seller_types": ["private"]}', true, 1),
  (9951, 'c2000000-0000-0000-0000-000000000004', 'E strict', '{"make": "Pgtap", "model": "Carro", "seller_types": ["private"]}', true, 1),
  (9952, 'c2000000-0000-0000-0000-000000000004', 'E plain',  '{"make": "Pgtap", "model": "Carro"}', true, 2),
  (9961, 'c2000000-0000-0000-0000-000000000005', 'T strict', '{"make": "Pgtap", "model": "Carro", "seller_types": ["private"]}', false, 1),
  (9962, 'c2000000-0000-0000-0000-000000000005', 'T plain',  '{"make": "Pgtap", "model": "Carro"}', false, 2);

create function pg_temp.marked() returns bigint[] language sql as $$
  select coalesce(array_agg(id order by id), '{}') from public.search_profiles
   where id between 9921 and 9962 and rematch_requested_at is not null
$$;
create function pg_temp.reset() returns void language sql as $$
  update public.search_profiles set rematch_requested_at = null where id between 9921 and 9962
$$;

select pg_temp.reset();
-- ---------------------------------------------------------------- profile writes
update public.profiles set plan = 'pro', plan_expires_at = now() + interval '30 days'
 where id = 'c2000000-0000-0000-0000-000000000002';
select is(pg_temp.marked(), '{9931}'::bigint[], 'upgrade Particular to Pro: only its strict search is marked (not one with seller_types null)');
select ok((select seller_filter_access from public.profiles where id = 'c2000000-0000-0000-0000-000000000002'), '... and the flag is stored');

select pg_temp.reset();
update public.profiles set plan = 'pass' where id = 'c2000000-0000-0000-0000-000000000002';
select is(pg_temp.marked(), '{9931}'::bigint[], 'downgrade Pro to Particular: marked again');

select pg_temp.reset();
update public.profiles set plan_expires_at = now() + interval '60 days' where id = 'c2000000-0000-0000-0000-000000000001';
select is(pg_temp.marked(), '{}'::bigint[], 'a Pro renewal (later plan_expires_at) flips nothing: nothing marked');
update public.profiles set plan = 'pass' where id = 'c2000000-0000-0000-0000-000000000003';
select is(pg_temp.marked(), '{}'::bigint[], 'free to Particular flips nothing either');
update public.profiles set plan = 'free', plan_expires_at = null where id = 'c2000000-0000-0000-0000-000000000003';
update public.profiles set contact_template = 'Hola {auto}' where id = 'c2000000-0000-0000-0000-000000000001';
select is(pg_temp.marked(), '{}'::bigint[], 'nor a write of another column');

update public.profiles set plan_expires_at = now() - interval '1 minute' where id = 'c2000000-0000-0000-0000-000000000001';
select is(pg_temp.marked(), '{9921}'::bigint[], 'a write that ends Pro (plan_expires_at in the past) marks it at once');
select pg_temp.reset();
update public.profiles set plan_expires_at = now() + interval '20 days' where id = 'c2000000-0000-0000-0000-000000000001';
select is(pg_temp.marked(), '{9921}'::bigint[], '... and one that brings it back too');

select pg_temp.reset();
update public.profiles set role = 'admin' where id = 'c2000000-0000-0000-0000-000000000003';
select is(pg_temp.marked(), '{9941}'::bigint[], 'an admin has every feature: a free user made admin is marked');
select pg_temp.reset();
update public.profiles set role = 'user' where id = 'c2000000-0000-0000-0000-000000000003';
select is(pg_temp.marked(), '{9941}'::bigint[], '... and back to user too');

-- ---------------------------------------------------------------- time-based expiry
-- The clock passes plan_expires_at without a write: simulated with the trigger off.
select pg_temp.reset();
alter table public.profiles disable trigger profiles_sync_seller_filter;
update public.profiles set plan_expires_at = now() - interval '1 minute' where id = 'c2000000-0000-0000-0000-000000000004';
alter table public.profiles enable trigger profiles_sync_seller_filter;
select ok((select seller_filter_access from public.profiles where id = 'c2000000-0000-0000-0000-000000000004'),
          'expired without a write: the stored flag is stale');
select ok(not public.plan_feature('c2000000-0000-0000-0000-000000000004', 'seller_filter'), '... while plan_feature already says no');
select is(public.sync_seller_filter_access(), 1, 'the sweep marks the one strict search of the expired Pro');
select is(pg_temp.marked(), '{9951}'::bigint[], '... 9951, not its plain one');
select ok(not (select seller_filter_access from public.profiles where id = 'c2000000-0000-0000-0000-000000000004'), '... and stores the flag');
select is(public.sync_seller_filter_access(), 0, 'a second sweep marks nothing');

select pg_temp.reset();
alter table public.profiles disable trigger profiles_sync_seller_filter;
update public.profiles set plan_expires_at = now() + interval '20 days' where id = 'c2000000-0000-0000-0000-000000000004';
update public.profiles set seller_filter_access = true where id = 'c2000000-0000-0000-0000-000000000004';
update public.profiles set plan_expires_at = now() - interval '1 minute' where id = 'c2000000-0000-0000-0000-000000000004';
alter table public.profiles enable trigger profiles_sync_seller_filter;
select lives_ok($$select public.expire_commercial_access()$$, 'expire_commercial_access() (the worker''s tick) runs the sweep');
select is(pg_temp.marked(), '{9951}'::bigint[], '... and marks the expired Pro''s strict search');

select pg_temp.reset();
alter table public.profiles disable trigger profiles_sync_seller_filter;
update public.profiles set plan_expires_at = now() + interval '20 days', seller_filter_access = true where id = 'c2000000-0000-0000-0000-000000000004';
update public.profiles set plan_expires_at = now() - interval '1 minute' where id = 'c2000000-0000-0000-0000-000000000004';
alter table public.profiles enable trigger profiles_sync_seller_filter;
select lives_ok($$select public.expire_commercial_access('c2000000-0000-0000-0000-000000000004')$$,
                'expire_commercial_access(user) (refunds, Telegram merges) syncs that user');
select is(pg_temp.marked(), '{9951}'::bigint[], '... marked');
update public.profiles set plan_expires_at = now() + interval '20 days' where id = 'c2000000-0000-0000-0000-000000000004';

-- ---------------------------------------------------------------- plan_limits edited
select pg_temp.reset();
update public.app_config set value = jsonb_set(value, '{pro,max_profiles}', '21') where key = 'plan_limits';
select is(pg_temp.marked(), '{}'::bigint[], 'plan_limits edited without touching seller_filter: nothing marked');
update public.app_config set value = jsonb_set(value, '{pro,seller_filter}', 'false') where key = 'plan_limits';
select is(pg_temp.marked(), '{9921,9951}'::bigint[], 'pro.seller_filter turned off: every Pro''s strict search is marked');
select ok(not (select seller_filter_access from public.profiles where id = 'c2000000-0000-0000-0000-000000000001'), '... flag stored off');
select pg_temp.reset();
update public.app_config set value = jsonb_set(value, '{pass,seller_filter}', 'true') where key = 'plan_limits';
select is(pg_temp.marked(), '{9931}'::bigint[], 'pass.seller_filter turned on: the Particular''s strict search');
select pg_temp.reset();
update public.app_config set value = jsonb_set(jsonb_set(value, '{pro,seller_filter}', 'true'), '{pass}', (value->'pass') - 'seller_filter')
 where key = 'plan_limits';
select is(pg_temp.marked(), '{9921,9931,9951}'::bigint[], 'both back (a key removed counts as a change)');

-- ---------------------------------------------------------------- a search moved to another user
select pg_temp.reset();
update public.search_profiles set user_id = 'c2000000-0000-0000-0000-000000000001' where id in (9961, 9962);
select is(pg_temp.marked(), '{9961}'::bigint[], 'a strict search moved from a free user to a Pro (link_telegram) is marked; the plain one is not');
select pg_temp.reset();
update public.search_profiles set user_id = 'c2000000-0000-0000-0000-000000000003' where id = 9961;
select is(pg_temp.marked(), '{9961}'::bigint[], '... and from a Pro to a free user');
select pg_temp.reset();
update public.search_profiles set user_id = 'c2000000-0000-0000-0000-000000000005' where id = 9961;
select is(pg_temp.marked(), '{}'::bigint[], '... but not between two users without the feature');

-- ---------------------------------------------------------------- privileges
select ok(not has_function_privilege('authenticated', 'public.sync_seller_filter_access(uuid, boolean)', 'execute'),
          'sync_seller_filter_access is server-only');
select ok(not has_function_privilege('anon', 'public.sync_seller_filter_access(uuid, boolean)', 'execute'), '... for anon too');

-- ---------------------------------------------------------------- match_cards.seller_unknown
insert into public.listings (id, source, external_id, url, title, make, model, year, price, currency, price_usd, seller_type, first_seen_at)
overriding system value values
  (9971, 'mercadolibre', 'P01PC-1', 'https://example.test/p01pc-1', 'Pgtap Carro', 'Pgtap', 'Carro', 2018, 15000, 'USD', 15000, null, now()),
  (9972, 'mercadolibre', 'P01PC-2', 'https://example.test/p01pc-2', 'Pgtap Carro', 'Pgtap', 'Carro', 2018, 15000, 'USD', 15000, 'private', now()),
  (9973, 'mercadolibre', 'P01PC-3', 'https://example.test/p01pc-3', 'Pgtap Carro', 'Pgtap', 'Carro', 2018, 15000, 'USD', 15000, null, now()),
  (9974, 'mercadolibre', 'P01PC-4', 'https://example.test/p01pc-4', 'Pgtap Carro', 'Pgtap', 'Carro', 2018, 15000, 'USD', 15000, null, now());
insert into public.matches (search_profile_id, listing_id, score, level, score_breakdown, match_reasons, red_flags, scoring_version) values
  (9921, 9971, 70, 'good', '{}', '{"seller": {"result": "unknown", "detail": "la publicación no lo informa", "kind": "hard"}}', '[]', 'pgtap'),
  (9921, 9972, 80, 'good', '{}', '{"seller": {"result": "ok", "detail": "particular", "kind": "hard"}}', '[]', 'pgtap'),
  (9922, 9973, 70, 'good', '{}', '{"seller_type": {"result": "unknown", "detail": "la publicación no lo informa", "kind": "soft"}}', '[]', 'pgtap'),
  (9922, 9974, 70, 'good', '{}', '{}', '[]', 'pgtap');
select has_column('public', 'match_cards', 'seller_unknown', 'match_cards.seller_unknown exists');
select is((select array_agg(seller_unknown order by listing_id) from public.match_cards where listing_id between 9971 and 9974),
          array[true, false, false, false],
          'true only when the strict filter let an unknown seller through; not a known seller, not the soft preference, not no reason');
select is((select attname from pg_attribute where attrelid = 'public.match_cards'::regclass and attnum > 0 and not attisdropped
            order by attnum desc limit 1), 'seller_unknown', '... appended last');

set local role authenticated;
set local request.jwt.claims = '{"sub": "c2000000-0000-0000-0000-000000000001", "role": "authenticated"}';
select is((select seller_unknown from public.search_results(9921) where listing_id = 9971), true,
          'search_results (setof match_cards) returns it');
reset role;

select * from finish();
rollback;

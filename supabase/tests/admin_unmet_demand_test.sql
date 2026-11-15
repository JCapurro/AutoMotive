-- /admin/demand (migration 20261222120000_admin_unmet_demand.sql). Run with: supabase test db
-- Run in an isolated local database; all fixtures roll back.
begin;
create extension if not exists pgtap with schema extensions;
select no_plan();

insert into auth.users (instance_id, id, aud, role, email, created_at, updated_at) values
  ('00000000-0000-0000-0000-000000000000', '71717171-7171-4171-8171-717171717171', 'authenticated', 'authenticated', 'admin@demand.test', now(), now()),
  ('00000000-0000-0000-0000-000000000000', '72727272-7272-4272-8272-727272727272', 'authenticated', 'authenticated', 'user@demand.test', now(), now());
update public.profiles set role = 'admin' where id = '71717171-7171-4171-8171-717171717171';

insert into public.search_profiles (id, user_id, name, filters, bootstrapped_at) overriding system value values
  (9971, '72727272-7272-4272-8272-727272727272', 'Pgtap demanda', '{"make": "Pgtap", "model": "Demanda"}', now());
insert into public.admin_unmet_demand (search_profile_id, user_id, make, model, zone_label, result_count, market,
  market_in_zone, relaxed_zone, relaxed_price, relaxed_trim, relaxed_year, cause)
values (9971, '72727272-7272-4272-8272-727272727272', 'Pgtap', 'Demanda', 'Córdoba', 1, 9, 2, 5, 1, 0, 0, 'zone');
insert into public.admin_unmet_demand_run (computed_at, duration_ms, searches, max_results, min_age_hours)
values (now(), 1200, 1, 3, 24);

select throws_ok($$update public.admin_unmet_demand set cause = 'otra'$$, '23514', null, 'cause is one of the five');
select throws_ok($$update public.admin_unmet_demand set relaxed_zone = -1$$, '23514', null, 'counts are not negative');

-- Admin reads both tables; nobody writes through the API.
set local role authenticated;
set local request.jwt.claims = '{"sub": "71717171-7171-4171-8171-717171717171", "role": "authenticated"}';
select is((select count(*)::int from public.admin_unmet_demand), 1, 'admin reads the rows');
select is((select count(*)::int from public.admin_unmet_demand_run), 1, 'admin reads the run');
select throws_ok($$delete from public.admin_unmet_demand$$, '42501', null, 'not even an admin writes through the API');

set local request.jwt.claims = '{"sub": "72727272-7272-4272-8272-727272727272", "role": "authenticated"}';
select is((select count(*)::int from public.admin_unmet_demand), 0, 'a user sees no rows');
select is((select count(*)::int from public.admin_unmet_demand_run), 0, 'a user sees no run');
select throws_ok($$select * from public.admin_cap_hidden()$$, '42501', null, 'the cap counter is for the service role only');

reset role;
set local role anon;
select throws_ok($$select count(*) from public.admin_unmet_demand$$, '42501', null, 'anonymous: no access');
reset role;

-- The cap counter: with the cap enforced, a free account's match the quota never admitted is hidden.
insert into public.listings (id, source, external_id, url, title, make, model, price, currency, price_usd, status)
overriding system value values
  (997101, 'mercadolibre', 'DEM-1', 'https://example.test/dem-1', 'Pgtap Demanda 1', 'Pgtap', 'Demanda', 10000, 'USD', 10000, 'active'),
  (997102, 'mercadolibre', 'DEM-2', 'https://example.test/dem-2', 'Pgtap Demanda 2', 'Pgtap', 'Demanda', 11000, 'USD', 11000, 'active'),
  (997103, 'mercadolibre', 'DEM-3', 'https://example.test/dem-3', 'Pgtap Demanda 3', 'Pgtap', 'Demanda', 12000, 'USD', 12000, 'gone');
insert into public.matches (search_profile_id, listing_id, score, level, score_breakdown, match_reasons, scoring_version)
select 9971, 997100 + n, 80, 'high'::public.match_level, '{}'::jsonb, '{}'::jsonb, 'test' from generate_series(1, 3) n;
-- Matches go in with the cap off; then it is enforced and the quota holds only listing 1.
update public.app_config set value = jsonb_set(value, '{enforced}', 'true') where key = 'plan_limits';
delete from public.free_trial_results where user_id = '72727272-7272-4272-8272-727272727272';
insert into public.free_trial_results (user_id, listing_id) values ('72727272-7272-4272-8272-727272727272', 997101);
select is((select matches::int from public.admin_cap_hidden() where level = 'high'), 1,
  'hides the active match outside the quota (not the admitted one, not the gone listing)');
select is((select accounts::int from public.admin_cap_hidden() where level is null), 1, 'the totals row counts the account once');
update public.app_config set value = jsonb_set(value, '{enforced}', 'false') where key = 'plan_limits';
select is((select count(*)::int from public.admin_cap_hidden()), 0, 'with the cap off nothing is hidden');

select is((select value->>'enabled' from public.app_config where key = 'unmet_demand'), 'false', 'the job ships off');

select * from finish();
rollback;

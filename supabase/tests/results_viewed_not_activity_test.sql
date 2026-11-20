-- Valor justo §6.3 (migration 20270108120000_results_viewed_not_activity.sql). Run with: supabase test db
-- search_results_viewed is not activity: criterion 4, admin_users.last_activity_at
-- and v_north_star_weekly ignore it; any other event still counts.
-- Run in an isolated local database; all fixtures roll back. The views count
-- every user, so each check compares against the numbers before the fixture.
begin;
create extension if not exists pgtap with schema extensions;
select no_plan();

insert into auth.users (instance_id, id, aud, role, email, created_at, updated_at) values
  ('00000000-0000-0000-0000-000000000000', '71717171-7171-7171-7171-717171717171', 'authenticated', 'authenticated', 'a@results-viewed.test', now() - interval '400 days', now());

-- An old search: eligible for criterion 4 whatever retention_weeks says.
insert into public.search_profiles (id, user_id, name, filters, bootstrapped_at, created_at) overriding system value values
  (9971, '71717171-7171-7171-7171-717171717171', 'Lista', '{"make": "Pgtap", "model": "Lista"}', now(), now() - interval '400 days');

create temp table base as
select (select numerator from public.v_validation_criteria where criterion = 'retention') as retained,
       (select denominator from public.v_validation_criteria where criterion = 'retention') as eligible,
       coalesce((select active_users from public.v_north_star_weekly
                  where week = date_trunc('week', now() at time zone 'America/Argentina/Buenos_Aires')::date), 0) as active;

select is((select denominator from public.v_validation_criteria where criterion = 'retention'),
          (select eligible from base), 'fixture: the eligible count is the baseline');
select is((select last_activity_at from public.admin_users where id = '71717171-7171-7171-7171-717171717171'), null,
          'fixture: no activity yet');

-- ---------------------------------------------------------------- a list shown: not activity
insert into public.events (user_id, name, props) values
  ('71717171-7171-7171-7171-717171717171', 'search_results_viewed',
   '{"profile_id": 9971, "sort": "score", "filter": "all", "page": 1, "listing_ids": [1, 2, 3]}');

select is((select numerator from public.v_validation_criteria where criterion = 'retention'),
          (select retained from base), 'criterion 4: search_results_viewed does not retain anyone');
select is((select last_activity_at from public.admin_users where id = '71717171-7171-7171-7171-717171717171'), null,
          'admin_users.last_activity_at: search_results_viewed is not activity');
select is(coalesce((select active_users from public.v_north_star_weekly
                     where week = date_trunc('week', now() at time zone 'America/Argentina/Buenos_Aires')::date), 0),
          (select active from base), 'v_north_star_weekly: search_results_viewed makes no active user');

-- ---------------------------------------------------------------- a car opened: activity, as before
insert into public.events (user_id, name, props) values
  ('71717171-7171-7171-7171-717171717171', 'listing_detail_viewed',
   '{"listing_id": 1, "via": "web", "profile_id": 9971, "sort": "score", "position": 1}');

select is((select numerator from public.v_validation_criteria where criterion = 'retention'),
          (select retained + 1 from base), 'criterion 4: any other event still counts');
select isnt((select last_activity_at from public.admin_users where id = '71717171-7171-7171-7171-717171717171'), null,
            'admin_users.last_activity_at: listing_detail_viewed still counts');
select is(coalesce((select active_users from public.v_north_star_weekly
                     where week = date_trunc('week', now() at time zone 'America/Argentina/Buenos_Aires')::date), 0),
          (select active + 1 from base), 'v_north_star_weekly: listing_detail_viewed still makes an active user');

-- The views stay server-only.
select ok(not has_table_privilege('authenticated', 'public.v_validation_criteria', 'select'), 'v_validation_criteria: not for authenticated');
select ok(not has_table_privilege('authenticated', 'public.admin_users', 'select'), 'admin_users: not for authenticated');
select ok(not has_table_privilege('anon', 'public.v_north_star_weekly', 'select'), 'v_north_star_weekly: not for anon');

select * from finish();
rollback;

-- Prueba gratis, paso 1 (docs/PRUEBA_HONESTA.md): the trial's reserve for new
-- listings, the matches it hides, and the emails' visible counts.
-- Run in an isolated local database; all fixtures roll back.
begin;
select plan(28);

select is((select value from public.app_config where key = 'trial_reserve'),
          '{"enabled": false, "backfill_max": 30}'::jsonb, 'the reserve ships off, with 30');
update public.app_config set value = jsonb_set(jsonb_set(jsonb_set(value, '{enforced}', 'true'),
  '{free,max_total_results}', '5'), '{free,max_profiles}', '3')
where key = 'plan_limits';

insert into auth.users(instance_id,id,aud,role,email,created_at,updated_at) values
('00000000-0000-0000-0000-000000000000','52525252-5252-5252-5252-525252525250','authenticated','authenticated','reserve@example.test',now(),now()),
('00000000-0000-0000-0000-000000000000','52525252-5252-5252-5252-525252525251','authenticated','authenticated','reserve-off@example.test',now(),now()),
('00000000-0000-0000-0000-000000000000','52525252-5252-5252-5252-525252525252','authenticated','authenticated','reserve-paid@example.test',now(),now());
update public.profiles set plan = 'pass', plan_expires_at = now() + interval '30 days'
 where id = '52525252-5252-5252-5252-525252525252';
-- Searches created a day ago: listings seen since then and published recently are new.
insert into public.search_profiles(id,user_id,name,filters,created_at) overriding system value values
(9870,'52525252-5252-5252-5252-525252525250','Reserve','{"make":"Ford","model":"Fiesta"}',now() - interval '1 day'),
(9871,'52525252-5252-5252-5252-525252525251','Off','{"make":"Ford","model":"Fiesta"}',now() - interval '1 day'),
(9872,'52525252-5252-5252-5252-525252525252','Paid','{"make":"Ford","model":"Fiesta"}',now() - interval '1 day'),
(9873,'52525252-5252-5252-5252-525252525250','Reserve 2','{"make":"Ford","model":"Ka"}',now() - interval '1 day');
-- 1-10: stock (seen before the searches); 11-20: new; 21: seen after, but published long ago.
insert into public.listings(id,source,external_id,url,title,make,model,first_seen_at,published_at) overriding system value
select 987000+n,'mercadolibre','reserve-'||n,'https://example.test/reserve-'||n,'Reserve','Ford','Fiesta',
       case when n <= 10 then now() - interval '5 days' else now() end,
       case when n = 21 then now() - interval '40 days' end
  from generate_series(1,21) n;

-- Off: today's rule, first come first in, up to the limit.
insert into public.matches(search_profile_id,listing_id,score,level,score_breakdown,match_reasons,scoring_version,is_backfill)
select 9871,987000+n,90,'good','{}','{}','test',true from generate_series(1,8) n;
select is((select count(*)::int from public.free_trial_results where user_id='52525252-5252-5252-5252-525252525251'),5,
          'off: stock fills the whole trial, as before');
select is((select count(*)::int from public.free_trial_results where user_id='52525252-5252-5252-5252-525252525251' and is_backfill),5,
          'off: what was admitted is recorded as stock');

-- On: stock takes at most 3 of the 5.
update public.app_config set value = '{"enabled": true, "backfill_max": 3}' where key = 'trial_reserve';
insert into public.matches(search_profile_id,listing_id,score,level,score_breakdown,match_reasons,scoring_version,is_backfill)
select 9870,987000+n,90,'good','{}','{}','test',true from generate_series(1,6) n;
select is((select count(*)::int from public.free_trial_results where user_id='52525252-5252-5252-5252-525252525250'),3,
          'on: stock stops at backfill_max');
-- A crawl's old listing stored as news (is_backfill false) is stock all the same.
insert into public.matches(search_profile_id,listing_id,score,level,score_breakdown,match_reasons,scoring_version,is_backfill)
values (9870,987007,90,'good','{}','{}','test',false);
select ok(not exists (select 1 from public.free_trial_results where listing_id=987007),
          'on: a listing seen before the search is stock, whatever the worker said');
insert into public.matches(search_profile_id,listing_id,score,level,score_breakdown,match_reasons,scoring_version,is_backfill)
values (9870,987021,90,'good','{}','{}','test',false);
select ok(not exists (select 1 from public.free_trial_results where listing_id=987021),
          'on: a listing published longer ago than recommended_max_age_days is stock');
-- New listings take the rest, on any of the account's searches.
insert into public.matches(search_profile_id,listing_id,score,level,score_breakdown,match_reasons,scoring_version,is_backfill)
values (9870,987011,90,'good','{}','{}','test',false), (9873,987012,90,'good','{}','{}','test',false);
select is((select count(*)::int from public.free_trial_results where user_id='52525252-5252-5252-5252-525252525250' and is_backfill = false),2,
          'on: new listings fill the reserved room');
insert into public.matches(search_profile_id,listing_id,score,level,score_breakdown,match_reasons,scoring_version,is_backfill)
values (9870,987013,90,'good','{}','{}','test',false);
select is((select count(*)::int from public.free_trial_results where user_id='52525252-5252-5252-5252-525252525250'),5,
          'on: the total limit still holds');
-- A rescore (update) of held-back stock doesn't admit it while the reserve is on.
update public.matches set score = 91 where search_profile_id = 9870 and listing_id = 987004;
select ok(not exists (select 1 from public.free_trial_results where listing_id=987004 and user_id='52525252-5252-5252-5252-525252525250'),
          'on: an update never sneaks stock in');
-- Paid accounts have no quota.
insert into public.matches(search_profile_id,listing_id,score,level,score_breakdown,match_reasons,scoring_version,is_backfill)
select 9872,987000+n,90,'good','{}','{}','test',true from generate_series(1,6) n;
select is((select count(*)::int from public.free_trial_results where user_id='52525252-5252-5252-5252-525252525252'),0,
          'paid: no trial ledger');

-- Broken values are off.
update public.app_config set value = '{"enabled": true}' where key = 'trial_reserve';
select is(public.trial_reserve_backfill_max(), null, 'no backfill_max: off, never 0');
update public.app_config set value = '{"enabled": true, "backfill_max": "x"}' where key = 'trial_reserve';
select is(public.trial_reserve_backfill_max(), null, 'a text backfill_max: off');
update public.app_config set value = '{"enabled": true, "backfill_max": -2}' where key = 'trial_reserve';
select is(public.trial_reserve_backfill_max(), null, 'a negative backfill_max: off');
update public.app_config set value = '{"enabled": "true", "backfill_max": 3}' where key = 'trial_reserve';
select is(public.trial_reserve_backfill_max(), null, 'enabled must be true itself');
update public.app_config set value = '{"enabled": true, "backfill_max": 3}' where key = 'trial_reserve';
select is(public.trial_reserve_backfill_max(), 3, 'on: 3');

-- Turned off again, held-back stock can come in on the next update.
update public.app_config set value = '{"enabled": false, "backfill_max": 3}' where key = 'trial_reserve';
delete from public.free_trial_results where user_id='52525252-5252-5252-5252-525252525250' and listing_id = 987012;
update public.matches set score = 92 where search_profile_id = 9870 and listing_id = 987004;
select ok(exists (select 1 from public.free_trial_results where listing_id=987004 and user_id='52525252-5252-5252-5252-525252525250'),
          'off again: held-back stock is admitted as before');
update public.app_config set value = '{"enabled": true, "backfill_max": 3}' where key = 'trial_reserve';

-- The page: hidden matches of one's own search, active listings only.
update public.listings set status = 'gone' where id = 987006;
set local role authenticated;
set local request.jwt.claim.sub = '52525252-5252-5252-5252-525252525250';
select is(public.my_search_hidden_results(9870), 4, 'hidden: the active matches the trial does not show');
select is(public.my_search_hidden_results(9871), 0, 'hidden: another account''s search is 0');
select is((public.my_plan_limits()->>'free_backfill_max')::int, 3, 'my_plan_limits: the reserve''s cap');
select is((public.my_plan_limits()->>'free_backfill_used')::int, 4, 'my_plan_limits: stock admitted');
set local request.jwt.claim.sub = '52525252-5252-5252-5252-525252525252';
select is(public.my_search_hidden_results(9872), 0, 'hidden: 0 without a trial quota');
select is(public.my_plan_limits()->'free_backfill_max', 'null'::jsonb, 'my_plan_limits: no reserve cap without a quota');
reset role;

-- The emails count what the trial shows, on the search that shows the most.
select is(public.trial_reserve_backfill_max(), 3, 'still on for the emails');
update public.app_config set value = jsonb_set(value, '{enabled}', 'true') where key = 'lifecycle_emails';
update public.profiles set free_trial_started_at = now() - interval '73 hours'
 where id = '52525252-5252-5252-5252-525252525250';
update public.search_profiles set created_at = now() - interval '50 minutes' where user_id = '52525252-5252-5252-5252-525252525250';
select ok(exists (select 1 from public.claim_lifecycle_emails('search_activated', interval '1 hour', 100) e
                   where e.user_id = '52525252-5252-5252-5252-525252525250'), 'welcome claimed');
select is((select payload - 'model' from public.lifecycle_emails
            where user_id = '52525252-5252-5252-5252-525252525250' and kind = 'search_activated'),
          '{"found": 5, "below": 0, "hidden": 4, "trial_limit": 5, "trial_left": 0}'::jsonb,
          'welcome: visible found, active hidden, and what the trial has left');
select is((select search_profile_id from public.lifecycle_emails
            where user_id = '52525252-5252-5252-5252-525252525250' and kind = 'search_activated'), 9870::bigint,
          'welcome: the search that shows the most');
-- An account without a trial quota keeps its counts as before: every match, no trial keys.
update public.search_profiles set created_at = now() - interval '50 minutes' where user_id = '52525252-5252-5252-5252-525252525252';
select is((select payload - 'model' from public.claim_lifecycle_emails('search_activated', interval '1 hour', 100) e
            where e.user_id = '52525252-5252-5252-5252-525252525252'),
          '{"found": 6, "below": 0}'::jsonb, 'paid: the welcome counts every match, as before');
select is((select payload->'found' from public.lifecycle_emails
            where user_id = '52525252-5252-5252-5252-525252525251' and kind = 'search_activated'), null,
          'no email for an account whose first search is not due');

select * from finish();
rollback;

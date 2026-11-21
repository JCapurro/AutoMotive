-- Prueba gratis «40 + N» (docs/PRUEBA_COMPLETA.md): the cap on new results,
-- the random stock sample, what the web reads, the completion time and the
-- trial_complete email. Legacy config (the row as it is) keeps today's rules.
-- Run in an isolated local database; all fixtures roll back.
begin;
select plan(58);

-- The migration leaves the switch as it was, and the new email off.
select is((select value from public.app_config where key = 'trial_reserve'),
          '{"enabled": false, "backfill_max": 30}'::jsonb, 'the migration does not touch trial_reserve');
select is((select value #> '{kinds,trial_complete}' from public.app_config where key = 'lifecycle_emails'),
          'false'::jsonb, 'trial_complete ships off');

update public.app_config set value = jsonb_set(jsonb_set(jsonb_set(value, '{enforced}', 'true'),
  '{free,max_total_results}', '10'), '{free,max_profiles}', '3')
where key = 'plan_limits';

-- A: new mode · B: legacy · C: paid · D: admin · E: a re-run ·
-- F: started before notice_since · P: paid after completing · Q: trial ended.
insert into auth.users(instance_id,id,aud,role,email,created_at,updated_at)
select '00000000-0000-0000-0000-000000000000', ('53535353-5353-5353-5353-5353535353' || n)::uuid,
       'authenticated','authenticated','complete-'||n||'@example.test',now(),now()
  from unnest(array['60','61','62','63','64','65','66','67']) n;
update public.profiles set plan = 'pass', plan_expires_at = now() + interval '30 days'
 where id = '53535353-5353-5353-5353-535353535362';
update public.profiles set role = 'admin' where id = '53535353-5353-5353-5353-535353535363';

-- Searches made two days ago (no welcome due), all pending their first run.
insert into public.search_profiles(id,user_id,name,filters,created_at) overriding system value values
(9880,'53535353-5353-5353-5353-535353535360','A','{"make":"Ford","model":"Fiesta"}',now() - interval '2 days'),
(9881,'53535353-5353-5353-5353-535353535361','B','{"make":"Ford","model":"Fiesta"}',now() - interval '2 days'),
(9882,'53535353-5353-5353-5353-535353535362','C','{"make":"Ford","model":"Fiesta"}',now() - interval '2 days'),
(9883,'53535353-5353-5353-5353-535353535363','D','{"make":"Ford","model":"Fiesta"}',now() - interval '2 days'),
(9884,'53535353-5353-5353-5353-535353535364','E','{"make":"Ford","model":"Fiesta"}',now() - interval '2 days');
update public.profiles set free_trial_started_at = now() - interval '2 hours'
 where id in ('53535353-5353-5353-5353-535353535360','53535353-5353-5353-5353-535353535361',
              '53535353-5353-5353-5353-535353535362','53535353-5353-5353-5353-535353535363',
              '53535353-5353-5353-5353-535353535364','53535353-5353-5353-5353-535353535366');
update public.profiles set free_trial_started_at = now() - interval '11 hours' where id = '53535353-5353-5353-5353-535353535365';
update public.profiles set free_trial_started_at = now() - interval '73 hours' where id = '53535353-5353-5353-5353-535353535367';

-- 1-12: stock (seen days before the searches); 13-20: new.
insert into public.listings(id,source,external_id,url,title,make,model,first_seen_at) overriding system value
select 988000+n,'mercadolibre','complete-'||n,'https://example.test/complete-'||n,'Complete','Ford','Fiesta',
       case when n <= 12 then now() - interval '5 days' else now() end
  from generate_series(1,20) n;

-- ---------------------------------------------------------------------------
-- Legacy: production's shape without the new fields is today's behaviour
-- ---------------------------------------------------------------------------
update public.app_config set value = '{"enabled": true, "backfill_max": 4}' where key = 'trial_reserve';
select is(public.trial_reserve_new_max(), null, 'legacy: no cap');
select is(public.trial_reserve_random_stock(), false, 'legacy: no random sample');
select is(public.trial_reserve_notice_since(), null, 'legacy: no notice');

insert into public.matches(search_profile_id,listing_id,score,level,score_breakdown,match_reasons,scoring_version,is_backfill)
select 9881,988000+n,90,'good','{}','{}','test',true from generate_series(1,6) n;
select is((select array_agg(listing_id - 988000 order by listing_id) from public.free_trial_results
            where user_id = '53535353-5353-5353-5353-535353535361'), array[1,2,3,4]::bigint[],
          'legacy: stock is first-come up to backfill_max, even while the search is pending');
insert into public.matches(search_profile_id,listing_id,score,level,score_breakdown,match_reasons,scoring_version,is_backfill)
select 9881,988000+n,90,'good','{}','{}','test',false from generate_series(13,17) n;
select is((select count(*)::int from public.free_trial_results
            where user_id = '53535353-5353-5353-5353-535353535361' and is_backfill = false), 5,
          'legacy: new results have no cap of their own');
select is(public.trial_completed_at('53535353-5353-5353-5353-535353535361'), null, 'legacy: never complete');
set local role authenticated;
set local request.jwt.claim.sub = '53535353-5353-5353-5353-535353535361';
select is(public.my_plan_limits()->'free_new_max', 'null'::jsonb, 'legacy: my_plan_limits has no cap');
select is((public.my_plan_limits()->>'free_new_used')::int, 5, 'my_plan_limits: new results admitted');
reset role;
-- The legacy welcome: what is left of the whole quota, no trial_new.
update public.app_config set value = jsonb_set(value, '{enabled}', 'true') where key = 'lifecycle_emails';
update public.search_profiles set created_at = now() - interval '50 minutes' where id = 9881;
select is((select payload->'trial_left' from public.claim_lifecycle_emails('search_activated', interval '1 hour', 100) e
            where e.user_id = '53535353-5353-5353-5353-535353535361'), '1'::jsonb,
          'legacy welcome: trial_left is the quota left (10 - 9)');
select ok(not (select payload ? 'trial_new' from public.lifecycle_emails
                where user_id = '53535353-5353-5353-5353-535353535361' and kind = 'search_activated'),
          'legacy welcome: no trial_new');

-- ---------------------------------------------------------------------------
-- The switch
-- ---------------------------------------------------------------------------
update public.app_config set value = '{"enabled": true, "backfill_max": 4, "new_max": "x"}' where key = 'trial_reserve';
select is(public.trial_reserve_new_max(), null, 'a text new_max: no cap');
update public.app_config set value = '{"enabled": true, "backfill_max": 4, "new_max": -1}' where key = 'trial_reserve';
select is(public.trial_reserve_new_max(), null, 'a negative new_max: no cap');
update public.app_config set value = '{"enabled": false, "backfill_max": 4, "new_max": 2, "random_stock": true}' where key = 'trial_reserve';
select is(public.trial_reserve_new_max(), null, 'the reserve off: no cap');
select is(public.trial_reserve_random_stock(), false, 'the reserve off: no sample');
update public.app_config set value = '{"enabled": true, "backfill_max": 4, "new_max": 2, "random_stock": "true", "notice_since": "mañana"}' where key = 'trial_reserve';
select is(public.trial_reserve_random_stock(), false, 'random_stock must be true itself');
select is(public.trial_reserve_notice_since(), null, 'an unreadable notice_since: no email');
update public.app_config set value = jsonb_build_object('enabled', true, 'backfill_max', 4, 'new_max', 2,
  'random_stock', true, 'notice_since', now() - interval '10 hours') where key = 'trial_reserve';
select is(public.trial_reserve_new_max(), 2, 'new mode: the cap');
select is(public.trial_reserve_random_stock(), true, 'new mode: the random sample');
select is(public.trial_reserve_notice_since(), now() - interval '10 hours', 'new mode: notice_since');

-- ---------------------------------------------------------------------------
-- Random stock
-- ---------------------------------------------------------------------------
update public.listings set status = 'gone' where id = 988004;
insert into public.matches(search_profile_id,listing_id,score,level,score_breakdown,match_reasons,scoring_version,is_backfill)
select 9880,988000+n,90,'good','{}','{}','test',true from generate_series(1,4) n;
select is((select count(*)::int from public.free_trial_results where user_id = '53535353-5353-5353-5353-535353535360'), 0,
          'random stock: nothing admitted while the first run is pending');
insert into public.matches(search_profile_id,listing_id,score,level,score_breakdown,match_reasons,scoring_version,is_backfill)
values (9880,988013,90,'good','{}','{}','test',false);
select is((select count(*)::int from public.free_trial_results
            where user_id = '53535353-5353-5353-5353-535353535360' and is_backfill = false), 1,
          'a new match of a pending search is admitted at once');
-- The run ends: mark_bootstrapped.
update public.search_profiles set bootstrapped_at = now(), rematch_requested_at = null where id = 9880;
select is((select count(*)::int from public.free_trial_results
            where user_id = '53535353-5353-5353-5353-535353535360' and is_backfill), 3,
          'the run ends: least(cap, n) admitted (3 active of 4, cap 4)');
select is((select array_agg(listing_id - 988000 order by listing_id) from public.free_trial_results
            where user_id = '53535353-5353-5353-5353-535353535360' and is_backfill), array[1,2,3]::bigint[],
          'the sample is that search''s active stock');
-- Stock that arrives later, with the search ready: first-come, up to the cap.
insert into public.matches(search_profile_id,listing_id,score,level,score_breakdown,match_reasons,scoring_version,is_backfill)
values (9880,988005,90,'good','{}','{}','test',true);
select ok(exists (select 1 from public.free_trial_results where user_id = '53535353-5353-5353-5353-535353535360' and listing_id = 988005),
          'late stock is admitted first-come');

-- The welcome in new mode: what is left is new cars.
update public.search_profiles set created_at = now() - interval '50 minutes' where id = 9880;
select is((select payload->'trial_left' from public.claim_lifecycle_emails('search_activated', interval '1 hour', 100) e
            where e.user_id = '53535353-5353-5353-5353-535353535360'), '1'::jsonb,
          'new-mode welcome: trial_left is new_max minus new results (2 - 1)');
select is((select payload->'trial_new' from public.lifecycle_emails
            where user_id = '53535353-5353-5353-5353-535353535360' and kind = 'search_activated'), '2'::jsonb,
          'new-mode welcome: trial_new is the cap');
select is((select payload->'trial_limit' from public.lifecycle_emails
            where user_id = '53535353-5353-5353-5353-535353535360' and kind = 'search_activated'), '10'::jsonb,
          'new-mode welcome: trial_limit stays');

insert into public.matches(search_profile_id,listing_id,score,level,score_breakdown,match_reasons,scoring_version,is_backfill)
values (9880,988006,90,'good','{}','{}','test',true);
select ok(not exists (select 1 from public.free_trial_results where user_id = '53535353-5353-5353-5353-535353535360' and listing_id = 988006),
          'stock keeps its backfill_max cap');

-- A re-run fills only the room left.
insert into public.matches(search_profile_id,listing_id,score,level,score_breakdown,match_reasons,scoring_version,is_backfill)
select 9884,988000+n,90,'good','{}','{}','test',true from generate_series(7,8) n;
select is((select count(*)::int from public.free_trial_results where user_id = '53535353-5353-5353-5353-535353535364'), 0,
          're-run account: nothing while the first run is pending');
update public.search_profiles set bootstrapped_at = now(), rematch_requested_at = null where id = 9884;
select is((select count(*)::int from public.free_trial_results where user_id = '53535353-5353-5353-5353-535353535364'), 2,
          'first run: both (2 below the cap)');
update public.search_profiles set rematch_requested_at = now() where id = 9884;
insert into public.matches(search_profile_id,listing_id,score,level,score_breakdown,match_reasons,scoring_version,is_backfill)
select 9884,988000+n,90,'good','{}','{}','test',true from generate_series(9,11) n;
select is((select count(*)::int from public.free_trial_results where user_id = '53535353-5353-5353-5353-535353535364'), 2,
          're-run: its stock waits too');
update public.search_profiles set rematch_requested_at = null where id = 9884;
select is((select count(*)::int from public.free_trial_results where user_id = '53535353-5353-5353-5353-535353535364'), 4,
          're-run ends: only the room left (4 - 2)');
select is((select count(*)::int from public.free_trial_results
            where user_id = '53535353-5353-5353-5353-535353535364' and listing_id between 988009 and 988011), 2,
          're-run: 2 of its 3 new stock matches');
select is(public.trial_completed_at('53535353-5353-5353-5353-535353535364'), null, 'no new results: not complete');

-- ---------------------------------------------------------------------------
-- The cap on new results
-- ---------------------------------------------------------------------------
insert into public.matches(search_profile_id,listing_id,score,level,score_breakdown,match_reasons,scoring_version,is_backfill)
values (9880,988014,90,'good','{}','{}','test',false);
insert into public.matches(search_profile_id,listing_id,score,level,score_breakdown,match_reasons,scoring_version,is_backfill)
values (9880,988015,90,'good','{}','{}','test',false);
select is((select count(*)::int from public.free_trial_results
            where user_id = '53535353-5353-5353-5353-535353535360' and is_backfill = false), 2,
          'the next new match after new_max is not admitted');
select is(public.free_result_allowed('53535353-5353-5353-5353-535353535360', 988015), false, 'free_result_allowed: hidden');
select is(public.trial_completed_at('53535353-5353-5353-5353-535353535360'),
          (select admitted_at from public.free_trial_results
            where user_id = '53535353-5353-5353-5353-535353535360' and listing_id = 988014),
          'trial_completed_at: when the new_max-th new result came in');
set local role authenticated;
set local request.jwt.claim.sub = '53535353-5353-5353-5353-535353535360';
-- 6 (stock past the cap) and 15 (new past the cap); 4 is gone.
select is(public.my_search_hidden_results(9880), 2, 'hidden counts both caps');
select is((public.my_plan_limits()->>'free_new_max')::int, 2, 'my_plan_limits: the cap');
select is((public.my_plan_limits()->>'free_new_used')::int, 2, 'my_plan_limits: new results admitted');
select is((public.my_plan_limits()->>'free_backfill_used')::int, 4, 'my_plan_limits: stock admitted');
reset role;

-- ---------------------------------------------------------------------------
-- Paid, admin and the unenforced pilot: untouched
-- ---------------------------------------------------------------------------
insert into public.matches(search_profile_id,listing_id,score,level,score_breakdown,match_reasons,scoring_version,is_backfill)
select sp, 988000+n,90,'good','{}','{}','test',n <= 12
  from unnest(array[9882,9883]) sp, unnest(array[1,2,3,13,14,15,16]) n;
select is((select count(*)::int from public.free_trial_results where user_id = '53535353-5353-5353-5353-535353535362'), 0,
          'paid: no ledger');
select is((select count(*)::int from public.free_trial_results where user_id = '53535353-5353-5353-5353-535353535363'), 0,
          'admin: no ledger');
update public.app_config set value = jsonb_set(value, '{enforced}', 'false') where key = 'plan_limits';
insert into public.matches(search_profile_id,listing_id,score,level,score_breakdown,match_reasons,scoring_version,is_backfill)
values (9881,988018,90,'good','{}','{}','test',false);
select is((select count(*)::int from public.free_trial_results where user_id = '53535353-5353-5353-5353-535353535361'), 9,
          'pilot: nothing admitted, nothing removed');
set local role authenticated;
set local request.jwt.claim.sub = '53535353-5353-5353-5353-535353535361';
select is(public.my_plan_limits()->'free_new_max', 'null'::jsonb, 'pilot: no cap for the web');
reset role;
update public.app_config set value = jsonb_set(value, '{enforced}', 'true') where key = 'plan_limits';

-- ---------------------------------------------------------------------------
-- trial_complete
-- ---------------------------------------------------------------------------
-- A completed 59 minutes ago; F, P and Q completed 61 minutes ago.
update public.free_trial_results set admitted_at = now() - interval '59 minutes'
 where user_id = '53535353-5353-5353-5353-535353535360' and is_backfill = false;
insert into public.free_trial_results(user_id, listing_id, is_backfill, admitted_at)
select u::uuid, 988000+n, false, now() - interval '61 minutes'
  from unnest(array['53535353-5353-5353-5353-535353535365','53535353-5353-5353-5353-535353535366',
                    '53535353-5353-5353-5353-535353535367']) u, generate_series(13,14) n;
update public.profiles set plan = 'pass', plan_expires_at = now() + interval '30 days'
 where id = '53535353-5353-5353-5353-535353535366';

select is((select count(*)::int from public.claim_lifecycle_emails('trial_complete', interval '48 hours', 100)), 0,
          'never with the kind off');
update public.app_config set value = jsonb_set(value, '{kinds,trial_complete}', 'true') where key = 'lifecycle_emails';
select is((select count(*)::int from public.claim_lifecycle_emails('trial_complete', interval '48 hours', 100)), 0,
          'not before 60 minutes, not before notice_since, not after paying, not after the trial');
update public.free_trial_results set admitted_at = now() - interval '61 minutes'
 where user_id = '53535353-5353-5353-5353-535353535360' and is_backfill = false;
select is((select array_agg(user_id) from public.claim_lifecycle_emails('trial_complete', interval '48 hours', 100)),
          array['53535353-5353-5353-5353-535353535360']::uuid[], '60 minutes after completing: claimed');
select is((select payload from public.lifecycle_emails
            where user_id = '53535353-5353-5353-5353-535353535360' and kind = 'trial_complete'),
          '{"model": "Ford Fiesta", "new": 2, "shown": 6, "hidden": 2}'::jsonb,
          'payload: the cap, what the search shows and what it hides');
select is((select target || ' ' || event_key || ' ' || search_profile_id from public.lifecycle_emails
            where user_id = '53535353-5353-5353-5353-535353535360' and kind = 'trial_complete'),
          '/app/searches/9880 complete 9880', 'to the search it picked');
select is((select count(*)::int from public.claim_lifecycle_emails('trial_complete', interval '48 hours', 100)), 0,
          'once per account');
-- notice_since earlier: F is in, Q's trial already ended, P paid.
update public.app_config set value = jsonb_set(value, '{notice_since}', to_jsonb(now() - interval '100 hours'))
 where key = 'trial_reserve';
select is((select array_agg(user_id || ' ' || target) from public.claim_lifecycle_emails('trial_complete', interval '48 hours', 100)),
          array['53535353-5353-5353-5353-535353535365 /app'], 'only trials started since notice_since; no search: /app');
-- At send time: still in the trial.
select ok(public.lifecycle_email_eligible((select id from public.lifecycle_emails
            where user_id = '53535353-5353-5353-5353-535353535360' and kind = 'trial_complete')), 'eligible while the trial runs');
update public.profiles set free_trial_started_at = now() - interval '73 hours' where id = '53535353-5353-5353-5353-535353535360';
select ok(not public.lifecycle_email_eligible((select id from public.lifecycle_emails
            where user_id = '53535353-5353-5353-5353-535353535360' and kind = 'trial_complete')), 'not once the trial ended');
-- Without new mode nobody is claimed, even with the kind on.
update public.app_config set value = '{"enabled": true, "backfill_max": 4}' where key = 'trial_reserve';
delete from public.lifecycle_emails where kind = 'trial_complete';
update public.profiles set free_trial_started_at = now() - interval '2 hours' where id = '53535353-5353-5353-5353-535353535360';
select is((select count(*)::int from public.claim_lifecycle_emails('trial_complete', interval '48 hours', 100)), 0,
          'rolled back to the legacy fields: no trial_complete');
-- Rolled back: new results have no cap again.
insert into public.matches(search_profile_id,listing_id,score,level,score_breakdown,match_reasons,scoring_version,is_backfill)
values (9880,988016,90,'good','{}','{}','test',false);
select ok(exists (select 1 from public.free_trial_results where user_id = '53535353-5353-5353-5353-535353535360' and listing_id = 988016),
          'rolled back: the next new match is admitted');

select * from finish();
rollback;

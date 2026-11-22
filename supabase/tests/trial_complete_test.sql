-- Prueba gratis de 50 publicaciones (docs/PRUEBA_COMPLETA.md): no cap on new
-- results, the random stock sample, what the web reads, the completion at the
-- account's limit and the trial_complete email. A row without notice_since
-- (production's shape) keeps today's rules. Run in an isolated local
-- database; all fixtures roll back.
begin;
select plan(60);

-- The migrations leave the switch as it was, and the new email off.
select is((select value from public.app_config where key = 'trial_reserve'),
          '{"enabled": false, "backfill_max": 30}'::jsonb, 'the migrations do not touch trial_reserve');
select is((select value #> '{kinds,trial_complete}' from public.app_config where key = 'lifecycle_emails'),
          'false'::jsonb, 'trial_complete ships off');
select hasnt_function('public', 'trial_reserve_new_max', 'trial_reserve_new_max is gone');

update public.app_config set value = jsonb_set(jsonb_set(jsonb_set(value, '{enforced}', 'true'),
  '{free,max_total_results}', '10'), '{free,max_profiles}', '3')
where key = 'plan_limits';

-- A: notice mode · B: legacy · C: paid · D: admin · E: a re-run ·
-- F: started before notice_since · P: paid after completing · Q: trial ended ·
-- G: fills its quota with new results only · H: stays below its quota.
insert into auth.users(instance_id,id,aud,role,email,created_at,updated_at)
select '00000000-0000-0000-0000-000000000000', ('53535353-5353-5353-5353-5353535353' || n)::uuid,
       'authenticated','authenticated','complete-'||n||'@example.test',now(),now()
  from unnest(array['60','61','62','63','64','65','66','67','68','69']) n;
update public.profiles set plan = 'pass', plan_expires_at = now() + interval '30 days'
 where id = '53535353-5353-5353-5353-535353535362';
update public.profiles set role = 'admin' where id = '53535353-5353-5353-5353-535353535363';

-- Searches made two days ago (no welcome due), all pending their first run.
insert into public.search_profiles(id,user_id,name,filters,created_at) overriding system value values
(9880,'53535353-5353-5353-5353-535353535360','A','{"make":"Ford","model":"Fiesta"}',now() - interval '2 days'),
(9881,'53535353-5353-5353-5353-535353535361','B','{"make":"Ford","model":"Fiesta"}',now() - interval '2 days'),
(9882,'53535353-5353-5353-5353-535353535362','C','{"make":"Ford","model":"Fiesta"}',now() - interval '2 days'),
(9883,'53535353-5353-5353-5353-535353535363','D','{"make":"Ford","model":"Fiesta"}',now() - interval '2 days'),
(9884,'53535353-5353-5353-5353-535353535364','E','{"make":"Ford","model":"Fiesta"}',now() - interval '2 days'),
(9888,'53535353-5353-5353-5353-535353535368','G','{"make":"Ford","model":"Ka"}',now() - interval '2 days'),
(9889,'53535353-5353-5353-5353-535353535369','H','{"make":"Ford","model":"Ka"}',now() - interval '2 days');
update public.profiles set free_trial_started_at = now() - interval '2 hours'
 where id in ('53535353-5353-5353-5353-535353535360','53535353-5353-5353-5353-535353535361',
              '53535353-5353-5353-5353-535353535362','53535353-5353-5353-5353-535353535363',
              '53535353-5353-5353-5353-535353535364','53535353-5353-5353-5353-535353535366',
              '53535353-5353-5353-5353-535353535368','53535353-5353-5353-5353-535353535369');
update public.profiles set free_trial_started_at = now() - interval '11 hours' where id = '53535353-5353-5353-5353-535353535365';
update public.profiles set free_trial_started_at = now() - interval '73 hours' where id = '53535353-5353-5353-5353-535353535367';

-- 1-12: stock (seen days before the searches); 13-40: new.
insert into public.listings(id,source,external_id,url,title,make,model,first_seen_at) overriding system value
select 988000+n,'mercadolibre','complete-'||n,'https://example.test/complete-'||n,'Complete','Ford','Fiesta',
       case when n <= 12 then now() - interval '5 days' else now() end
  from generate_series(1,40) n;

-- ---------------------------------------------------------------------------
-- Legacy: production's shape without notice_since is today's behaviour
-- ---------------------------------------------------------------------------
update public.app_config set value = '{"enabled": true, "backfill_max": 4}' where key = 'trial_reserve';
select is(public.trial_reserve_random_stock(), false, 'legacy: no random sample');
select is(public.trial_reserve_notice_since(), null, 'legacy: no notice mode');

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
select is(public.trial_completed_at('53535353-5353-5353-5353-535353535361'), null, 'below the limit: not complete');
set local role authenticated;
set local request.jwt.claim.sub = '53535353-5353-5353-5353-535353535361';
select ok(not (public.my_plan_limits() ? 'free_new_max') and not (public.my_plan_limits() ? 'free_new_used'),
          'my_plan_limits: no new-result fields');
select is((public.my_plan_limits()->>'free_results_used')::int, 9, 'my_plan_limits: results admitted');
select is((public.my_plan_limits()->>'free_backfill_max')::int, 4, 'my_plan_limits: the stock cap');
reset role;
-- The legacy welcome: what is left of the whole quota, nothing added.
update public.app_config set value = jsonb_set(value, '{enabled}', 'true') where key = 'lifecycle_emails';
update public.search_profiles set created_at = now() - interval '50 minutes' where id = 9881;
select is((select payload->'trial_left' from public.claim_lifecycle_emails('search_activated', interval '1 hour', 100) e
            where e.user_id = '53535353-5353-5353-5353-535353535361'), '1'::jsonb,
          'legacy welcome: trial_left is the quota left (10 - 9)');
select ok(not (select payload ?| array['trial_new', 'trial_notice'] from public.lifecycle_emails
                where user_id = '53535353-5353-5353-5353-535353535361' and kind = 'search_activated'),
          'legacy welcome: no trial_new, no trial_notice');

-- ---------------------------------------------------------------------------
-- The switch
-- ---------------------------------------------------------------------------
update public.app_config set value = jsonb_build_object('enabled', false, 'backfill_max', 4, 'random_stock', true,
  'notice_since', now() - interval '10 hours') where key = 'trial_reserve';
select is(public.trial_reserve_notice_since(), null, 'the reserve off: no notice mode');
select is(public.trial_reserve_random_stock(), false, 'the reserve off: no sample');
update public.app_config set value = '{"enabled": true, "backfill_max": 4, "random_stock": "true", "notice_since": "mañana"}' where key = 'trial_reserve';
select is(public.trial_reserve_random_stock(), false, 'random_stock must be true itself');
select is(public.trial_reserve_notice_since(), null, 'an unreadable notice_since: no notice mode');
update public.app_config set value = jsonb_build_object('enabled', true, 'backfill_max', 4,
  'random_stock', true, 'notice_since', now() - interval '10 hours') where key = 'trial_reserve';
select is(public.trial_reserve_random_stock(), true, 'random_stock on');
select is(public.trial_reserve_notice_since(), now() - interval '10 hours', 'notice mode: notice_since');

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
select is((select array_agg(listing_id - 988000 order by listing_id) from public.free_trial_results
            where user_id = '53535353-5353-5353-5353-535353535360' and is_backfill), array[1,2,3]::bigint[],
          'the run ends: that search''s active stock, up to the cap (3 active of 4)');
-- Stock that arrives later, with the search ready: first-come, up to the cap.
insert into public.matches(search_profile_id,listing_id,score,level,score_breakdown,match_reasons,scoring_version,is_backfill)
values (9880,988005,90,'good','{}','{}','test',true);
select ok(exists (select 1 from public.free_trial_results where user_id = '53535353-5353-5353-5353-535353535360' and listing_id = 988005),
          'late stock is admitted first-come');
insert into public.matches(search_profile_id,listing_id,score,level,score_breakdown,match_reasons,scoring_version,is_backfill)
values (9880,988006,90,'good','{}','{}','test',true);
select ok(not exists (select 1 from public.free_trial_results where user_id = '53535353-5353-5353-5353-535353535360' and listing_id = 988006),
          'stock keeps its backfill_max cap');

-- The welcome in notice mode: trial_notice, and trial_left as the legacy claim computes it.
update public.search_profiles set created_at = now() - interval '50 minutes' where id = 9880;
select is((select payload->'trial_left' from public.claim_lifecycle_emails('search_activated', interval '1 hour', 100) e
            where e.user_id = '53535353-5353-5353-5353-535353535360'), '5'::jsonb,
          'notice-mode welcome: trial_left is the quota left (10 - 5)');
select is((select payload->'trial_notice' from public.lifecycle_emails
            where user_id = '53535353-5353-5353-5353-535353535360' and kind = 'search_activated'), 'true'::jsonb,
          'notice-mode welcome: trial_notice');
select is((select payload->'trial_limit' from public.lifecycle_emails
            where user_id = '53535353-5353-5353-5353-535353535360' and kind = 'search_activated'), '10'::jsonb,
          'notice-mode welcome: trial_limit stays');
select ok(not (select payload ? 'trial_new' from public.lifecycle_emails
                where user_id = '53535353-5353-5353-5353-535353535360' and kind = 'search_activated'),
          'notice-mode welcome: no trial_new');

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

-- ---------------------------------------------------------------------------
-- No cap on new results: they fill the rest of the quota
-- ---------------------------------------------------------------------------
insert into public.matches(search_profile_id,listing_id,score,level,score_breakdown,match_reasons,scoring_version,is_backfill)
select 9880,988000+n,90,'good','{}','{}','test',false from generate_series(14,17) n;
select is((select count(*)::int from public.free_trial_results where user_id = '53535353-5353-5353-5353-535353535360'), 9,
          'new matches keep coming in below the limit (4 stock + 5 new)');
select is(public.trial_completed_at('53535353-5353-5353-5353-535353535360'), null, '9 of 10: not complete');
insert into public.matches(search_profile_id,listing_id,score,level,score_breakdown,match_reasons,scoring_version,is_backfill)
select 9880,988000+n,90,'good','{}','{}','test',false from generate_series(18,19) n;
select is((select count(*)::int from public.free_trial_results
            where user_id = '53535353-5353-5353-5353-535353535360' and is_backfill = false), 6,
          'new results up to the limit (6), no cap of their own');
select is(public.free_result_allowed('53535353-5353-5353-5353-535353535360', 988019), false, 'past the limit: hidden');
select ok(public.trial_completed_at('53535353-5353-5353-5353-535353535360') is not null, 'at the limit: complete');
set local role authenticated;
set local request.jwt.claim.sub = '53535353-5353-5353-5353-535353535360';
-- 6 (stock past its cap) and 19 (past the limit); 4 is gone.
select is(public.my_search_hidden_results(9880), 2, 'hidden counts the stock cap and the limit');
select is((public.my_plan_limits()->>'free_results_used')::int, 10, 'my_plan_limits: the quota is full');
select is((public.my_plan_limits()->>'free_backfill_used')::int, 4, 'my_plan_limits: stock admitted');
reset role;

-- G fills its quota with new results only; H stays below it.
update public.search_profiles set bootstrapped_at = now() where id in (9888, 9889);
insert into public.matches(search_profile_id,listing_id,score,level,score_breakdown,match_reasons,scoring_version,is_backfill)
select 9888,988000+n,90,'good','{}','{}','test',false from generate_series(20,30) n;
select is((select count(*)::int from public.free_trial_results where user_id = '53535353-5353-5353-5353-535353535368'), 10,
          'new results only: up to the limit');
select is(public.trial_completed_at('53535353-5353-5353-5353-535353535368'),
          (select admitted_at from public.free_trial_results where user_id = '53535353-5353-5353-5353-535353535368'
            order by admitted_at, listing_id offset 9 limit 1),
          'trial_completed_at: when the limit-th result came in');
insert into public.matches(search_profile_id,listing_id,score,level,score_breakdown,match_reasons,scoring_version,is_backfill)
select 9889,988000+n,90,'good','{}','{}','test',false from generate_series(31,35) n;
select is(public.trial_completed_at('53535353-5353-5353-5353-535353535369'), null, 'below the limit: never complete');

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
select is(public.trial_completed_at('53535353-5353-5353-5353-535353535362'), null, 'paid: never complete');
update public.app_config set value = jsonb_set(value, '{enforced}', 'false') where key = 'plan_limits';
insert into public.matches(search_profile_id,listing_id,score,level,score_breakdown,match_reasons,scoring_version,is_backfill)
values (9889,988036,90,'good','{}','{}','test',false);
select is((select count(*)::int from public.free_trial_results where user_id = '53535353-5353-5353-5353-535353535369'), 5,
          'pilot: nothing admitted, nothing removed');
select is(public.trial_completed_at('53535353-5353-5353-5353-535353535368'), null, 'pilot: no quota, never complete');
update public.app_config set value = jsonb_set(value, '{enforced}', 'true') where key = 'plan_limits';

-- ---------------------------------------------------------------------------
-- trial_complete
-- ---------------------------------------------------------------------------
-- A completed 59 minutes ago; G, F, P and Q 61 minutes ago.
update public.free_trial_results set admitted_at = now() - interval '59 minutes'
 where user_id = '53535353-5353-5353-5353-535353535360';
update public.free_trial_results set admitted_at = now() - interval '61 minutes'
 where user_id = '53535353-5353-5353-5353-535353535368';
insert into public.free_trial_results(user_id, listing_id, is_backfill, admitted_at)
select u::uuid, 988000+n, false, now() - interval '61 minutes'
  from unnest(array['53535353-5353-5353-5353-535353535365','53535353-5353-5353-5353-535353535366',
                    '53535353-5353-5353-5353-535353535367']) u, generate_series(13,22) n;
update public.profiles set plan = 'pass', plan_expires_at = now() + interval '30 days'
 where id = '53535353-5353-5353-5353-535353535366';

select is((select count(*)::int from public.claim_lifecycle_emails('trial_complete', interval '48 hours', 100)), 0,
          'never with the kind off');
update public.app_config set value = jsonb_set(value, '{kinds,trial_complete}', 'true') where key = 'lifecycle_emails';
select is((select array_agg(user_id) from public.claim_lifecycle_emails('trial_complete', interval '48 hours', 100)),
          array['53535353-5353-5353-5353-535353535368']::uuid[],
          'claimed 60 minutes after the quota filled; not before, not below it, not before notice_since, not after paying or the trial');
select is((select payload from public.lifecycle_emails
            where user_id = '53535353-5353-5353-5353-535353535368' and kind = 'trial_complete'),
          '{"model": "Ford Ka", "total": 10, "shown": 10, "hidden": 1}'::jsonb,
          'payload: the limit, what the search shows and what it hides');
update public.free_trial_results set admitted_at = now() - interval '61 minutes'
 where user_id = '53535353-5353-5353-5353-535353535360';
select is((select array_agg(user_id) from public.claim_lifecycle_emails('trial_complete', interval '48 hours', 100)),
          array['53535353-5353-5353-5353-535353535360']::uuid[], 'stock and new results together: claimed');
select is((select payload from public.lifecycle_emails
            where user_id = '53535353-5353-5353-5353-535353535360' and kind = 'trial_complete'),
          '{"model": "Ford Fiesta", "total": 10, "shown": 10, "hidden": 2}'::jsonb,
          'payload: no count of new results');
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
-- Without notice mode nobody is claimed, even with the kind on.
update public.app_config set value = '{"enabled": true, "backfill_max": 4}' where key = 'trial_reserve';
delete from public.lifecycle_emails where kind = 'trial_complete';
update public.profiles set free_trial_started_at = now() - interval '2 hours' where id = '53535353-5353-5353-5353-535353535360';
select is((select count(*)::int from public.claim_lifecycle_emails('trial_complete', interval '48 hours', 100)), 0,
          'rolled back to the legacy fields: no trial_complete');
-- Rolled back: the welcome passes through untouched.
update public.search_profiles set created_at = now() - interval '50 minutes' where id = 9889;
select ok(not (select payload ? 'trial_notice' from public.claim_lifecycle_emails('search_activated', interval '1 hour', 100) e
                where e.user_id = '53535353-5353-5353-5353-535353535369'), 'rolled back: no trial_notice');

select * from finish();
rollback;

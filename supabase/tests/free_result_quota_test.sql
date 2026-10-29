-- Run in an isolated local database; all fixtures roll back.
begin;
select no_plan();
update public.app_config set value = jsonb_set(jsonb_set(value, '{enforced}', 'true'), '{free,max_profiles}', '3')
where key = 'plan_limits';
insert into auth.users(instance_id,id,aud,role,email,created_at,updated_at) values
('00000000-0000-0000-0000-000000000000','50505050-5050-5050-5050-505050505050','authenticated','authenticated','quota@example.test',now(),now()),
('00000000-0000-0000-0000-000000000000','50505050-5050-5050-5050-505050505051','authenticated','authenticated','quota-other@example.test',now(),now());
insert into public.search_profiles(id,user_id,name,filters) overriding system value values
(9850,'50505050-5050-5050-5050-505050505050','Quota','{"make":"Ford","model":"Fiesta"}'),
(9851,'50505050-5050-5050-5050-505050505051','Other','{"make":"Ford","model":"Fiesta"}');
insert into public.listings(id,source,external_id,url,title,make,model) overriding system value
select 985000+n,'mercadolibre','quota-'||n,'https://example.test/quota-'||n,'Quota','Ford','Fiesta' from generate_series(1,60) n;
insert into public.matches(search_profile_id,listing_id,score,level,score_breakdown,match_reasons,scoring_version)
select 9850,985000+n,90,'good','{}','{}','test' from generate_series(1,60) n;
select is((select count(*)::int from public.free_trial_results where user_id='50505050-5050-5050-5050-505050505050'),50,'50 distinct listings admitted');
select is((select count(*)::int from public.matches where search_profile_id=9850),60,'additional matches retained for a future paid plan');
set local role authenticated;
set local request.jwt.claim.sub = '50505050-5050-5050-5050-505050505050';
select is((public.my_plan_limits()->>'free_results_used')::int,50,'snapshot reports cumulative use');
select is((public.my_plan_limits()->>'free_results_limit')::int,50,'snapshot reports limit');
select is((select count(*)::int from public.search_results(9850,'all','score',1000,0)),50,'cannot request more than quota');
select is((select count(*)::int from public.search_results(9850,'all','price',1000,50)),0,'offset cannot bypass quota');
select is((select count(*)::int from public.match_cards where search_profile_id=9850),50,'direct view also respects quota');
select is((select all_count from public.search_result_counts(9850)),50,'counts reflect accessible results');
select is((select count(*)::int from public.free_trial_results),50,'ledger only readable by its owner');
select throws_ok($$insert into public.free_trial_results(user_id,listing_id) values ('50505050-5050-5050-5050-505050505050',999999)$$,'42501',null,'client cannot grant itself another listing');
reset role;
select ok(not public.notification_access_active('50505050-5050-5050-5050-505050505050',9850,985060),'extra listing cannot generate an alert');
select ok(public.notification_access_active('50505050-5050-5050-5050-505050505050',9850,985001),'admitted listing can generate an alert');
insert into public.notifications(user_id,search_profile_id,listing_id,kind,channel,dedupe_key)
values('50505050-5050-5050-5050-505050505050',9850,985060,'new_match','email','quota-hidden');
select is((select count(*)::int from public.notifications where dedupe_key='quota-hidden'),0,'hidden result never queued as an alert');
insert into public.notifications(user_id,kind,channel,dedupe_key,payload)
values('50505050-5050-5050-5050-505050505050','digest','email','quota-digest',
  '{"items":[{"listing_id":985001,"section":"new"},{"listing_id":985060,"section":"new"}]}');
select is((select jsonb_array_length(payload->'items') from public.notifications where dedupe_key='quota-digest'),1,'digest contains admitted results only');
-- Mimic a mail queued before the migration, then check at dispatch as well.
alter table public.notifications disable trigger notifications_free_result_digest;
insert into public.notifications(user_id,kind,channel,dedupe_key,payload)
values('50505050-5050-5050-5050-505050505050','digest','email','quota-queued',
  '{"items":[{"listing_id":985060,"section":"new"}]}');
alter table public.notifications enable trigger notifications_free_result_digest;
select ok(not public.prepare_notification_delivery((select id from public.notifications where dedupe_key='quota-queued')),'already queued hidden-only digest cannot be dispatched');
select is((select status::text from public.notifications where dedupe_key='quota-queued'),'skipped','hidden-only mail skipped');
-- Recreating a search and receiving the same listing never replenishes quota.
delete from public.search_profiles where id=9850;
insert into public.search_profiles(id,user_id,name,filters) overriding system value values
(9852,'50505050-5050-5050-5050-505050505050','Quota recreated','{"make":"Ford","model":"Fiesta"}');
insert into public.matches(search_profile_id,listing_id,score,level,score_breakdown,match_reasons,scoring_version)
select 9852,985000+n,90,'good','{}','{}','test' from generate_series(1,60) n;
select is((select count(*)::int from public.free_trial_results where user_id='50505050-5050-5050-5050-505050505050'),50,'deleting and recreating searches preserves quota');
set local role authenticated;
select is((select count(*)::int from public.search_results(9852,'all','recent',1000,0)),50,'sort changes return the same admitted set');
reset role;
-- The other account gets its own quota.
insert into public.matches(search_profile_id,listing_id,score,level,score_breakdown,match_reasons,scoring_version)
values(9851,985060,90,'good','{}','{}','test');
select is((select count(*)::int from public.free_trial_results where user_id='50505050-5050-5050-5050-505050505051'),1,'quota belongs to each account');
-- Upgrade unlocks matches that were retained behind the quota.
update public.profiles set plan='pass',plan_expires_at=now()+interval '30 days' where id='50505050-5050-5050-5050-505050505050';
set local role authenticated;
select is((select count(*)::int from public.search_results(9852,'all','score',1000,0)),60,'paid access unlocks every result');
reset role;
update public.profiles set plan='free',plan_expires_at=null where id='50505050-5050-5050-5050-505050505050';
set local role authenticated;
select is((select count(*)::int from public.search_results(9852,'all','score',1000,0)),50,'returning to free keeps the consumed quota');
reset role;
update public.profiles set role='admin' where id='50505050-5050-5050-5050-505050505050';
set local role authenticated;
select is((select count(*)::int from public.search_results(9852,'all','score',1000,0)),60,'admin exempt');
reset role;
select * from finish();
rollback;

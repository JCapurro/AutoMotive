-- Dedicated local test database only. All fixtures and changes roll back.
begin;
create extension if not exists pgtap with schema extensions;
select no_plan();

select has_function('public', 'admin_decision_metrics', array['timestamp with time zone','timestamp with time zone','timestamp with time zone']);
select ok(not (select prosecdef from pg_proc where oid='public.admin_decision_metrics(timestamptz,timestamptz,timestamptz)'::regprocedure), 'RPC is security invoker');
select ok((select proconfig @> array['search_path=""'] from pg_proc where oid='public.admin_decision_metrics(timestamptz,timestamptz,timestamptz)'::regprocedure), 'fixed empty search_path');
select ok(not has_function_privilege('anon', 'public.admin_decision_metrics(timestamptz,timestamptz,timestamptz)', 'execute'), 'anon cannot execute');
select ok(not has_function_privilege('authenticated', 'public.admin_decision_metrics(timestamptz,timestamptz,timestamptz)', 'execute'), 'authenticated cannot execute');
select ok(has_function_privilege('service_role', 'public.admin_decision_metrics(timestamptz,timestamptz,timestamptz)', 'execute'), 'service role may execute');
select throws_ok($$select public.admin_decision_metrics('2026-01-01 03:00Z','2026-04-02 03:00Z','2026-04-02 12:00Z')$$, '22023', 'invalid_metrics_range', 'rejects more than 90 days');
select throws_ok($$select public.admin_decision_metrics('2026-02-01 03:00Z','2026-02-01 03:00Z','2026-02-08 12:00Z')$$, '22023', 'invalid_metrics_range', 'rejects zero days');
select throws_ok($$select public.admin_decision_metrics('2026-02-01 00:00Z','2026-02-08 00:00Z','2026-02-08 12:00Z')$$, '22023', 'invalid_metrics_range', 'requires Argentina midnight');
select throws_ok($$select public.admin_decision_metrics('2026-02-01 03:00Z','2026-02-08 03:00Z','2026-02-07 03:00Z')$$, '22023', 'invalid_metrics_range', 'as-of cannot precede period close');
select throws_ok($$select public.admin_decision_metrics(null,'2026-02-08 03:00Z','2026-02-08 12:00Z')$$, '22023', 'invalid_metrics_range', 'rejects null range');

-- Isolate fixture construction from billing/search lifecycle triggers. The RPC
-- itself runs normally, and no trigger/schema change survives this transaction.
set local session_replication_role = replica;
update public.admin_metric_observation set first_value_tracking_since='2026-01-01 03:00Z';
delete from public.notifications;
delete from public.events;
delete from public.matches;
delete from public.commercial_payments;
delete from public.billing_checkouts;
delete from public.search_profiles;
delete from public.profiles;
delete from auth.users;

insert into auth.users (id, email) values
 ('da000000-0000-4000-8000-000000000001','one@metrics.test'),
 ('da000000-0000-4000-8000-000000000002','young@metrics.test'),
 ('da000000-0000-4000-8000-000000000003','previous@metrics.test'),
 ('da000000-0000-4000-8000-000000000004','boundary@metrics.test'),
 ('da000000-0000-4000-8000-000000000005','late@metrics.test'),
 ('da000000-0000-4000-8000-000000000006','mature@metrics.test'),
 ('da000000-0000-4000-8000-00000000000a','admin@metrics.test');
insert into public.profiles (id,email,created_at,role)
select id,email,case right(id::text,1)
 when '1' then '2026-02-01 03:00Z'::timestamptz when '2' then '2026-02-07 04:00Z'::timestamptz
 when '3' then '2026-01-25 03:00Z'::timestamptz when '4' then '2026-02-08 03:00Z'::timestamptz
 when '5' then '2026-02-05 03:00Z'::timestamptz when '6' then '2026-02-07 03:00Z'::timestamptz
 else '2026-02-01 03:00Z'::timestamptz end,
 case when right(id::text,1)='a' then 'admin'::public.user_role else 'user'::public.user_role end from auth.users;

insert into public.search_profiles(id,user_id,name,filters,created_at) overriding system value values
 (99001,'da000000-0000-4000-8000-000000000001','first','{}','2026-02-02 02:00Z'),
 (99002,'da000000-0000-4000-8000-000000000002','immature','{}','2026-02-07 05:00Z'),
 (99003,'da000000-0000-4000-8000-000000000003','previous','{}','2026-01-25 05:00Z'),
 (99004,'da000000-0000-4000-8000-000000000004','boundary','{}','2026-02-08 03:00Z'),
 (99005,'da000000-0000-4000-8000-000000000005','late activation','{}','2026-02-06 04:00Z'),
 (99006,'da000000-0000-4000-8000-000000000006','mature boundary','{}','2026-02-07 03:00Z'),
 (99007,'da000000-0000-4000-8000-000000000001','young search','{"make":"other"}','2026-02-07 04:00Z'),
 (9900,'da000000-0000-4000-8000-00000000000a','admin','{}','2026-02-01 04:00Z');
insert into public.listings(id,source,external_id,url,title) overriding system value
select 99001,id,'admin-metrics-fixture','https://example.test/fixture','fixture' from public.sources limit 1;
insert into public.matches(search_profile_id,listing_id,score,level,score_breakdown,match_reasons,scoring_version,generated_at) values
 (99001,99001,80,'good','{}','[]','test','2026-02-02 04:00Z'),
 (99002,99001,90,'high','{}','[]','test','2026-02-07 06:00Z'),
 (99003,99001,90,'high','{}','[]','test','2026-01-25 06:00Z'),
 (99005,99001,80,'good','{}','[]','test','2026-02-07 05:00Z'), -- 25h: too late
 (99006,99001,90,'high','{}','[]','test','2026-02-08 03:00Z'), -- at exclusive end
 (9900,99001,90,'high','{}','[]','test','2026-02-01 05:00Z');
-- Known immutable observations in this synthetic fully instrumented fixture.
-- Production migration explicitly does not infer these from mutable matches.
insert into public.admin_search_observations(search_profile_id,user_id,search_created_at,first_good_at)
select s.id,s.user_id,s.created_at,(select min(m.generated_at) from public.matches m where m.search_profile_id=s.id and m.level in ('good','high'))
from public.search_profiles s;
insert into public.events(user_id,name,created_at) values
 ('da000000-0000-4000-8000-000000000001','listing_saved','2026-02-01 03:00Z'),
 ('da000000-0000-4000-8000-000000000001','listing_saved','2026-02-01 04:00Z'),
 ('da000000-0000-4000-8000-000000000005','alert_sent','2026-02-02 04:00Z'),
 ('da000000-0000-4000-8000-000000000002','listing_detail_viewed','2026-02-08 03:00Z'),
 ('da000000-0000-4000-8000-000000000003','alert_clicked','2026-01-25 03:00Z'),
 ('da000000-0000-4000-8000-00000000000a','listing_saved','2026-02-01 03:00Z');
insert into public.billing_checkouts(id,user_id,offer,offer_version,amount,billing_email,status,provider_id,created_at,sync_error) values
 ('db000000-0000-4000-8000-000000000001','da000000-0000-4000-8000-000000000001','pro_monthly','test',200,'one@metrics.test','authorized','authorized-fixture','2026-02-01 03:00Z',null),
 ('db000000-0000-4000-8000-000000000002','da000000-0000-4000-8000-000000000002','pass_30','test',50,'young@metrics.test','pending',null,'2026-02-01 03:00Z','sync failure'),
 ('db000000-0000-4000-8000-00000000000a','da000000-0000-4000-8000-00000000000a','pro_monthly','test',999,'admin@metrics.test','pending',null,'2026-02-01 03:00Z','admin failure');
insert into public.commercial_payments(user_id,offer,offer_version,amount,currency,provider,reference,paid_at,period_start,period_end,refunded_at) values
 ('da000000-0000-4000-8000-000000000001','pass_30','test',100,'ARS','test','old-refunded','2026-01-31 03:00Z','2026-01-31 03:00Z','2026-03-02 03:00Z','2026-02-02 03:00Z'),
 ('da000000-0000-4000-8000-000000000001','pro_monthly','test',200,'ARS','test','agency-1','2026-02-01 03:00Z','2026-02-01 03:00Z','2026-03-03 03:00Z',null),
 ('da000000-0000-4000-8000-000000000001','pro_monthly','test',300,'ARS','test','agency-2','2026-02-02 03:00Z','2026-02-02 03:00Z','2026-03-04 03:00Z',null),
 ('da000000-0000-4000-8000-000000000002','pass_30','test',50,'ARS','test','new-refunded-later','2026-02-03 03:00Z','2026-02-03 03:00Z','2026-03-05 03:00Z','2026-02-09 03:00Z'),
 ('da000000-0000-4000-8000-000000000004','pass_30','test',20,'ARS','test','boundary','2026-02-08 03:00Z','2026-02-08 03:00Z','2026-03-10 03:00Z',null),
 ('da000000-0000-4000-8000-00000000000a','pro_monthly','test',999,'ARS','test','admin','2026-02-01 03:00Z','2026-02-01 03:00Z','2026-03-03 03:00Z','2026-02-02 03:00Z');
insert into public.notifications(user_id,kind,channel,status,dedupe_key,created_at) values
 ('da000000-0000-4000-8000-000000000001','new_match','web','queued','metrics:queued','2026-02-01 03:00Z'),
 ('da000000-0000-4000-8000-000000000002','new_match','web','failed','metrics:failed','2026-02-01 03:00Z'),
 ('da000000-0000-4000-8000-00000000000a','new_match','web','failed','metrics:admin','2026-02-01 03:00Z');
set local session_replication_role = origin;

set local role service_role;
create temporary table metrics_snapshot as select public.admin_decision_metrics('2026-02-01 03:00Z','2026-02-08 03:00Z','2026-02-08 12:00Z') as value;
reset role;
select is((select value#>>'{current,signups}' from metrics_snapshot),'4','signups include start, exclude end and admins');
select is((select value#>>'{previous,signups}' from metrics_snapshot),'1','previous same-length adjacent period');
select is((select value#>>'{current,activationEligible}' from metrics_snapshot),'3','only signups with 24h observation at period end');
select is((select value#>>'{current,activatedWithin24h}' from metrics_snapshot),'2','activation excludes search after24h and immature user');
select is((select value#>>'{current,searchesCreated}' from metrics_snapshot),'5','searches use half-open range and exclude admins');
select is((select value#>>'{current,firstValueEligible}' from metrics_snapshot),'3','only mature searches enter value denominator');
select is((select value#>>'{current,firstValueWithin24h}' from metrics_snapshot),'1','late, immature and exclusive-end matches do not improve value');
select is((select (value#>>'{current,firstValueMedianHours}')::numeric from metrics_snapshot),2::numeric,'median includes only achieved first values');
select is((select value#>>'{current,activeUsers}' from metrics_snapshot),'1','distinct human activity excludes alert_sent, admins and end boundary');
select is((select (value#>>'{current,grossRevenue}')::numeric from metrics_snapshot),550::numeric,'gross by paid_at includes later-refunded payment');
select is((select (value#>>'{previous,grossRevenue}')::numeric from metrics_snapshot),100::numeric,'prior payment remains gross in prior period');
select is((select (value#>>'{current,refunds}')::numeric from metrics_snapshot),100::numeric,'refund belongs to refund date, not payment date');
select is((select value#>>'{current,particularSales}' from metrics_snapshot),'1','particular sales by paid date');
select is((select value#>>'{current,agencyPayments}' from metrics_snapshot),'2','agency payments separated');
select is((select value#>>'{current,firstPayingUsers}' from metrics_snapshot),'1','renewals are not first-paying users');
select is((select jsonb_array_length(value->'daily') from metrics_snapshot),7,'every complete day has a series row');
select is((select value#>>'{daily,0,day}' from metrics_snapshot),'2026-02-01','daily grouping is Argentina local date');
select is((select value#>>'{daily,6,grossRevenue}' from metrics_snapshot),'0','empty final day is an observed zero');
select is((select value#>>'{currentState,enabledSearches}' from metrics_snapshot),'7','current enabled searches exclude admin');
select is((select value#>>'{currentState,searchesWithoutValue24h}' from metrics_snapshot),'1','current attention removes a search once value arrives, even after24h');
select is((select value#>>'{currentState,pendingNotifications}' from metrics_snapshot),'1','queued user notification');
select is((select value#>>'{currentState,failedNotifications}' from metrics_snapshot),'1','failed notifications exclude admins');
select is((select value#>>'{currentState,pendingCheckouts}' from metrics_snapshot),'1','authorized subscriptions are not pending checkouts');
select is((select value#>>'{currentState,checkoutSyncErrors}' from metrics_snapshot),'1','checkout errors exclude admins');
select is((select (value#>>'{currentState,agencyMonthlyEquivalent}')::numeric from metrics_snapshot),300::numeric,'monthly equivalent deduplicates overlapping payments per account');
select is((select (value#>>'{currentState,authorizedRecurringMrr}')::numeric from metrics_snapshot),200::numeric,'authorized recurring MRR uses provider-authorized subscription amount separately');
select is((public.admin_decision_metrics('2025-01-01 03:00Z','2025-01-08 03:00Z','2025-01-08 12:00Z')#>>'{current,firstValueMedianHours}')::numeric,null::numeric,'empty cohort has no median');

-- Re-scoring preserves generated_at. A later promotion must not manufacture
-- a historical within24h hit, and downgrades/deletes cannot erase an observation.
update public.matches set generated_at='2026-02-06 05:00Z', level='low' where search_profile_id=99005;
update public.matches set level='good' where search_profile_id=99005;
select is((public.admin_decision_metrics('2026-02-01 03:00Z','2026-02-08 03:00Z','2026-02-08 12:00Z')#>>'{current,firstValueWithin24h}'), '1', 'later promotion never backdates first value to original generated_at');
update public.matches set level='low' where search_profile_id=99005;
update public.matches set level='low' where search_profile_id=99001;
select is((public.admin_decision_metrics('2026-02-01 03:00Z','2026-02-08 03:00Z','2026-02-08 12:00Z')#>>'{current,firstValueWithin24h}'), '1', 'downgrade preserves immutable first value');
delete from public.matches where search_profile_id=99001;
select is((public.admin_decision_metrics('2026-02-01 03:00Z','2026-02-08 03:00Z','2026-02-08 12:00Z')#>>'{current,firstValueWithin24h}'), '1', 'deleting a match preserves immutable first value');
insert into public.events(user_id,name,props,created_at) values ('da000000-0000-4000-8000-000000000006','search_profile_created','{"profile_id":99006}','2026-02-07 03:00Z');
delete from public.search_profiles where id=99006;
select is((public.admin_decision_metrics('2026-02-01 03:00Z','2026-02-08 03:00Z','2026-02-08 12:00Z')#>>'{current,activatedWithin24h}'), '2', 'deleting a search preserves activation from its creation event');
select is((public.admin_decision_metrics('2026-02-01 03:00Z','2026-02-08 03:00Z','2026-02-08 12:00Z')#>>'{current,searchesCreated}'), '5', 'search creation history survives deletion and deduplicates event plus row');
insert into public.events(user_id,name,created_at) values ('da000000-0000-4000-8000-000000000002','search_profile_paused','2026-02-06 03:00Z');
select is((public.admin_decision_metrics('2026-02-01 03:00Z','2026-02-08 03:00Z','2026-02-08 12:00Z')#>>'{current,activeUsers}'), '3', 'human pause and creation actions are activity');
-- PAR-02: copying the «Antes de señar» checklist is an explicit action; seeing it is not.
insert into public.events(user_id,name,props,created_at) values ('da000000-0000-4000-8000-000000000005','risk_checklist_viewed','{"listing_id":99001}','2026-02-06 03:00Z');
select is((public.admin_decision_metrics('2026-02-01 03:00Z','2026-02-08 03:00Z','2026-02-08 12:00Z')#>>'{current,activeUsers}'), '3', 'a viewed risk checklist is not activity (PAR-02)');
insert into public.events(user_id,name,props,created_at) values ('da000000-0000-4000-8000-000000000005','risk_checklist_copied','{"listing_id":99001}','2026-02-06 04:00Z');
select is((public.admin_decision_metrics('2026-02-01 03:00Z','2026-02-08 03:00Z','2026-02-08 12:00Z')#>>'{current,activeUsers}'), '4', 'a copied risk checklist is activity (PAR-02)');
select is((public.admin_decision_metrics('2026-02-01 03:00Z','2026-02-08 03:00Z','2026-02-08 12:00Z')#>>'{current,firstValueUnobserved}'), '0', 'instrumented synthetic cohort has full coverage');
update public.admin_metric_observation set first_value_tracking_since='2026-02-03 03:00Z';
select is((public.admin_decision_metrics('2026-02-01 03:00Z','2026-02-08 03:00Z','2026-02-08 12:00Z')#>>'{current,firstValueUnobserved}'), '1', 'legacy mature search is reported as unobserved, not a failed result');
select is((public.admin_decision_metrics('2026-02-01 03:00Z','2026-02-08 03:00Z','2026-02-08 12:00Z')#>>'{current,firstValueEligible}'), '2', 'legacy search is excluded from observable denominator');
select is((public.admin_decision_metrics('2026-02-01 03:00Z','2026-02-08 03:00Z','2026-02-08 12:00Z')#>>'{current,firstValueWithin24h}'), '0', 'no historical inference even if a legacy search has an old good match');
select is((public.admin_decision_metrics('2026-02-01 03:00Z','2026-02-08 03:00Z','2026-02-08 12:00Z')->>'firstValueTrackingSince')::timestamptz, '2026-02-03 03:00Z'::timestamptz, 'snapshot reports real instrumented coverage start');
create temporary table promotion_started as select statement_timestamp() as at;
insert into public.matches(search_profile_id,listing_id,score,level,score_breakdown,match_reasons,scoring_version,generated_at)
values(99007,99001,10,'low','{}','[]','test','2026-02-07 05:00Z');
update public.matches set level='high' where search_profile_id=99007;
select ok((select o.first_good_at>=t.at from public.admin_search_observations o cross join promotion_started t where search_profile_id=99007), 'promotion is timestamped when it actually happens');
select ok((select first_good_at>search_created_at+interval '24 hours' from public.admin_search_observations where search_profile_id=99007), 'first observation cannot be backdated through generated_at');
select ok(not has_table_privilege('authenticated','public.admin_search_observations','update'), 'users cannot rewrite first-good observations');
select ok(not has_table_privilege('authenticated','public.admin_search_observations','delete'), 'users cannot erase observations');
select ok(not has_table_privilege('authenticated','public.admin_metric_observation','update'), 'users cannot rewrite coverage cutoff');
select ok(not has_table_privilege('anon','public.admin_search_observations','select'), 'observation data is not public');

-- Invoker trigger must preserve an ordinary authenticated search INSERT.
update public.app_config set value=jsonb_set(value,'{enforced}','false') where key='plan_limits';
set local role authenticated;
set local request.jwt.claims = '{"sub":"da000000-0000-4000-8000-000000000004","role":"authenticated"}';
select lives_ok($$insert into public.search_profiles(user_id,name,filters) values('da000000-0000-4000-8000-000000000004','authenticated observation','{"make":"observation-fixture"}')$$, 'authenticated search INSERT still works with invoker observation trigger');
select is((select count(*)::int from public.admin_search_observations where user_id='da000000-0000-4000-8000-000000000004'),2,'user sees only own source observations');
select throws_ok($$insert into public.admin_search_observations(search_profile_id,user_id,search_created_at,first_good_at) values(999990,'da000000-0000-4000-8000-000000000004',now(),now())$$,'42501',null,'user cannot forge a good observation');
select throws_ok($$insert into public.admin_search_observations(search_profile_id,user_id,search_created_at) values(999991,'da000000-0000-4000-8000-000000000004',now())$$,'42501',null,'user cannot register an absent source');
reset role;
-- Account linking transfers live search ownership before the old profile is
-- removed. Immutable observations must follow that transfer atomically.
create temporary table owner_transfer_before as select first_good_at from public.admin_search_observations where search_profile_id=99007;
set local role service_role;
update public.billing_checkouts set user_id='da000000-0000-4000-8000-000000000004' where user_id='da000000-0000-4000-8000-000000000001';
update public.commercial_payments set user_id='da000000-0000-4000-8000-000000000004' where user_id='da000000-0000-4000-8000-000000000001';
update public.search_profiles set user_id='da000000-0000-4000-8000-000000000004' where id=99007;
reset role;
select is((select user_id from public.admin_search_observations where search_profile_id=99007),'da000000-0000-4000-8000-000000000004'::uuid,'account linking transfers observation owner with live search');
select is((select first_good_at from public.admin_search_observations where search_profile_id=99007),(select first_good_at from owner_transfer_before),'account linking preserves the immutable first-good timestamp');
delete from public.profiles where id='da000000-0000-4000-8000-000000000001';
select is((select count(*)::int from public.admin_search_observations where search_profile_id=99007),1,'old account deletion cannot erase transferred observation');
select * from finish();
rollback;

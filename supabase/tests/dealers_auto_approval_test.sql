-- Agencias: an agency is approved by its plan (migration 20270104120000_dealer_auto_approval.sql).
-- One transaction, rolled back.
begin;
create extension if not exists pgtap with schema extensions;
select no_plan();

-- P pays Pro, F is on the free plan, X is an admin, E had Pro until yesterday.
insert into auth.users (instance_id, id, aud, role, email, created_at, updated_at) values
  ('00000000-0000-0000-0000-000000000000', 'da000000-0000-0000-0000-00000000000a', 'authenticated', 'authenticated', 'p@auto.test', now(), now()),
  ('00000000-0000-0000-0000-000000000000', 'da000000-0000-0000-0000-00000000000b', 'authenticated', 'authenticated', 'f@auto.test', now(), now()),
  ('00000000-0000-0000-0000-000000000000', 'da000000-0000-0000-0000-00000000000c', 'authenticated', 'authenticated', 'x@auto.test', now(), now()),
  ('00000000-0000-0000-0000-000000000000', 'da000000-0000-0000-0000-00000000000d', 'authenticated', 'authenticated', 'e@auto.test', now(), now());
update public.profiles set plan = 'pro', plan_expires_at = now() + interval '10 days' where id = 'da000000-0000-0000-0000-00000000000a';
update public.profiles set role = 'admin' where id = 'da000000-0000-0000-0000-00000000000c';
update public.profiles set plan = 'pro', plan_expires_at = now() - interval '1 day' where id = 'da000000-0000-0000-0000-00000000000d';
update public.app_config set value = jsonb_set(value, '{enforced}', 'true') where key = 'plan_limits';
update public.app_config set value = value || '{"enabled": true, "channel_enabled": true}' where key = 'dealer_program';

set local role authenticated;
set local request.jwt.claims = '{"sub": "da000000-0000-0000-0000-00000000000a", "role": "authenticated"}';
select lives_ok($$select public.create_dealer('Auto Pro', 'Quilmes', -34.72, -58.25)$$, 'a Pro account creates its agency');
select is((public.my_dealer() ->> 'approved')::boolean, true, '... and it is approved from the first minute, without a click');
reset role;
set local role authenticated;
set local request.jwt.claims = '{"sub": "da000000-0000-0000-0000-00000000000b", "role": "authenticated"}';
select lives_ok($$select public.create_dealer('Auto Free', 'Quilmes', -34.72, -58.25)$$, 'a free account creates its agency');
select is((public.my_dealer() ->> 'approved')::boolean, false, '... and it is not approved: the panel without demand or sending');
reset role;
set local role authenticated;
set local request.jwt.claims = '{"sub": "da000000-0000-0000-0000-00000000000c", "role": "authenticated"}';
select lives_ok($$select public.create_dealer('Auto Admin', 'Quilmes', -34.72, -58.25)$$, 'an admin creates one');
select is((public.my_dealer() ->> 'approved')::boolean, true, '... approved: an admin has Pro everywhere');
reset role;
set local role authenticated;
set local request.jwt.claims = '{"sub": "da000000-0000-0000-0000-00000000000d", "role": "authenticated"}';
select lives_ok($$select public.create_dealer('Auto Vencida', 'Quilmes', -34.72, -58.25)$$, 'an account whose Pro ended creates one');
select is((public.my_dealer() ->> 'approved')::boolean, false, '... not approved');
reset role;

select is((select approved_by from public.dealers where name = 'Auto Pro'), null, 'an automatic approval has no approved_by');
select is(public.dealer_sync_approvals(), 0, 'dealer_sync_approvals: nothing to change when plans and approvals agree');

-- The plans move: the free one pays, the Pro one expires.
update public.profiles set plan = 'pro', plan_expires_at = now() + interval '30 days' where id = 'da000000-0000-0000-0000-00000000000b';
update public.profiles set plan_expires_at = now() - interval '1 minute' where id = 'da000000-0000-0000-0000-00000000000a';
select is(public.dealer_sync_approvals(), 2, '... two agencies change');
select is((select array_agg(name order by name) from public.dealers where approved_at is not null and name like 'Auto %'),
          array['Auto Admin', 'Auto Free'], '... the one that paid is on, the one that expired is off');
select is(public.dealer_sync_approvals(), 0, '... and a second pass changes nothing');

-- A hand-made approval does not outlive the plan, and a lapsed plan that pays again comes back.
update public.dealers set approved_at = now() where name = 'Auto Vencida';
select is(public.dealer_sync_approvals(), 1, 'an approval without a plan is cleared');
update public.profiles set plan_expires_at = now() + interval '5 days' where id = 'da000000-0000-0000-0000-00000000000a';
select is(public.dealer_sync_approvals(), 1, 'paying again approves again');
select is((select approved_at is not null from public.dealers where name = 'Auto Pro'), true, '... Auto Pro is back');

-- Renaming or moving keeps the approval; a paused agency keeps it too but stays hidden by its status.
set local role authenticated;
set local request.jwt.claims = '{"sub": "da000000-0000-0000-0000-00000000000a", "role": "authenticated"}';
select lives_ok($$select public.update_my_dealer('Auto Pro Renombrada', 'Avellaneda', -34.66, -58.36)$$, 'a new name and place');
select is((public.my_dealer() ->> 'approved')::boolean, true, '... keeps the approval');
reset role;
update public.dealers set status = 'paused' where name = 'Auto Pro Renombrada';
select is(public.dealer_sync_approvals(), 0, 'pausing is not the plan''s business');
select is(public.dealer_listing_hidden('directo', (select id from public.dealers where name = 'Auto Pro Renombrada'), 'available', now()) is not null, true,
          '... and the cars of a paused agency stay hidden');

select is(has_function_privilege('authenticated', 'public.dealer_sync_approvals()', 'execute')
          or has_function_privilege('authenticated', 'public.dealer_plan_active(bigint)', 'execute'), false,
          'sync and plan check: service role only');

select * from finish();
rollback;

begin;
create extension if not exists pgtap with schema extensions;
set local search_path = public, extensions;
select no_plan();

insert into auth.users (id, email) values
  ('a4d17000-0000-4000-8000-000000000001', 'audit-admin@example.test'),
  ('a4d17000-0000-4000-8000-000000000002', 'audit-user@example.test');
update public.profiles set role = 'admin' where id = 'a4d17000-0000-4000-8000-000000000001';
insert into public.app_config (key, value) values ('admin_audit_fixture', '{"count":1,"unknown":{"keep":true}}');
insert into public.sources (id, name, crawl_interval_seconds, priority) values ('admin_audit_source', 'Audit test source', 123, 42);

select ok((select relrowsecurity from pg_class where oid = 'public.admin_config_audit'::regclass), 'audit has RLS enabled');
select ok(not (select prosecdef from pg_proc where oid = 'public.admin_update_setting(text,text,jsonb,jsonb,uuid)'::regprocedure), 'write RPC is security invoker');
select ok(not has_function_privilege('anon', 'public.admin_update_setting(text,text,jsonb,jsonb,uuid)', 'execute'), 'anon cannot call the write RPC');
select ok(not has_function_privilege('authenticated', 'public.admin_update_setting(text,text,jsonb,jsonb,uuid)', 'execute'), 'authenticated cannot call the write RPC');
select ok(has_function_privilege('service_role', 'public.admin_update_setting(text,text,jsonb,jsonb,uuid)', 'execute'), 'service role can call the write RPC');
select ok(not has_table_privilege('anon', 'public.admin_config_audit', 'select'), 'anon cannot read audit');
select ok(not has_table_privilege('authenticated', 'public.admin_config_audit', 'insert'), 'authenticated cannot forge audit');
select ok(not has_table_privilege('service_role', 'public.admin_config_audit', 'update'), 'service role cannot rewrite audit history');

set local role anon;
select throws_ok($$select public.admin_update_setting('app_config','admin_audit_fixture','{}','{}','a4d17000-0000-4000-8000-000000000001')$$, '42501', null, 'anon request is denied');
reset role;
set local role authenticated;
select throws_ok($$select * from public.admin_config_audit$$, '42501', null, 'authenticated audit read is denied');
reset role;
set local role service_role;
select throws_ok($$select public.admin_update_setting('app_config','admin_audit_fixture','{}','{}','a4d17000-0000-4000-8000-000000000002')$$, '42501', 'admin_required', 'even a service request requires a current admin actor');
select throws_ok($$select public.admin_update_setting('app_config','admin_audit_fixture','{}','null','a4d17000-0000-4000-8000-000000000001')$$, '22023', 'invalid_setting', 'null config is rejected');
select throws_ok($$select public.admin_update_setting('app_config','admin_audit_fixture','{"count":1,"unknown":{"keep":true}}','[]','a4d17000-0000-4000-8000-000000000001')$$, '22023', 'invalid_setting_shape', 'config shape cannot change');
select throws_ok($$select public.admin_update_setting('app_config','commercial_pilot','{}','{}','a4d17000-0000-4000-8000-000000000001')$$, '22023', 'commercial_pilot_requires_billing', 'generic RPC cannot start the pilot');
select throws_ok($$select public.admin_update_setting('app_config','plan_limits',value,jsonb_set(value,'{enforced}',to_jsonb(not coalesce((value->>'enforced')::boolean,false))),'a4d17000-0000-4000-8000-000000000001') from public.app_config where key='plan_limits'$$, '22023', 'commercial_pilot_requires_billing', 'generic RPC cannot bypass pilot by toggling enforced');

select lives_ok($$select public.admin_update_setting('app_config','admin_audit_fixture','{"count":1,"unknown":{"keep":true}}','{"count":2,"unknown":{"keep":true}}','a4d17000-0000-4000-8000-000000000001')$$, 'config and audit commit as a service request');
select is((select value->>'count' from public.app_config where key='admin_audit_fixture'), '2', 'new config value is stored');
select is((select count(*)::integer from public.admin_config_audit where target_key='admin_audit_fixture'), 1, 'exactly one audit was inserted');
select is((select actor_email from public.admin_config_audit where target_key='admin_audit_fixture'), 'audit-admin@example.test', 'actor email comes from the admin profile');
select is((select before_value->>'count' from public.admin_config_audit where target_key='admin_audit_fixture'), '1', 'audit stores before');
select is((select after_value->>'count' from public.admin_config_audit where target_key='admin_audit_fixture'), '2', 'audit stores after');
select ok((select created_at is not null from public.admin_config_audit where target_key='admin_audit_fixture'), 'audit has server timestamp');
select throws_ok($$select public.admin_update_setting('app_config','admin_audit_fixture','{"count":1,"unknown":{"keep":true}}','{"count":3}','a4d17000-0000-4000-8000-000000000001')$$, '40001', 'setting_conflict', 'stale update is rejected under the row lock');
select is((select value->>'count' from public.app_config where key='admin_audit_fixture'), '2', 'conflict does not overwrite the winning update');
select is((select count(*)::integer from public.admin_config_audit where target_key='admin_audit_fixture'), 1, 'conflict inserts no false audit');

select throws_ok($$select public.admin_update_setting('sources','admin_audit_source','{"enabled":true,"crawl_interval_seconds":123}','{"enabled":false,"crawl_interval_seconds":60.5}','a4d17000-0000-4000-8000-000000000001')$$, '22023', 'invalid_source', 'fractional cadence is rejected');
select throws_ok($$select public.admin_update_setting('sources','admin_audit_source','{"enabled":true,"crawl_interval_seconds":123}','{"enabled":"false","crawl_interval_seconds":120}','a4d17000-0000-4000-8000-000000000001')$$, '22023', 'invalid_source', 'source boolean must be a boolean');
select throws_ok($$select public.admin_update_setting('sources','admin_audit_source','{"enabled":true,"crawl_interval_seconds":123}','{"enabled":false,"crawl_interval_seconds":120,"priority":1}','a4d17000-0000-4000-8000-000000000001')$$, '22023', 'invalid_source', 'source RPC cannot modify unrelated fields');
select lives_ok($$select public.admin_update_setting('sources','admin_audit_source','{"enabled":true,"crawl_interval_seconds":123}','{"enabled":false,"crawl_interval_seconds":125}','a4d17000-0000-4000-8000-000000000001')$$, 'source state and exact seconds are saved together');
select is((select crawl_interval_seconds from public.sources where id='admin_audit_source'), 125, 'source seconds are not rounded');
select is((select priority::integer from public.sources where id='admin_audit_source'), 42, 'source unrelated settings survive');
select is((select count(*)::integer from public.admin_config_audit where target_key='admin_audit_source'), 1, 'source change is audited');
select throws_ok($$select public.admin_update_setting('sources','admin_audit_source','{"enabled":true,"crawl_interval_seconds":123}','{"enabled":true,"crawl_interval_seconds":200}','a4d17000-0000-4000-8000-000000000001')$$, '40001', 'setting_conflict', 'stale source update is rejected');
reset role;

-- Force an audit INSERT failure after the setting UPDATE. The entire RPC must roll back.
create function pg_temp.reject_audit_test() returns trigger language plpgsql as $$
begin
  if new.target_key = 'admin_audit_fixture' then raise exception 'audit_test_failure' using errcode = '23514'; end if;
  return new;
end;
$$;
create trigger reject_audit_test before insert on public.admin_config_audit for each row execute function pg_temp.reject_audit_test();
set local role service_role;
select throws_ok($$select public.admin_update_setting('app_config','admin_audit_fixture','{"count":2,"unknown":{"keep":true}}','{"count":9}','a4d17000-0000-4000-8000-000000000001')$$, '23514', 'audit_test_failure', 'audit failure is returned to the caller');
select is((select value->>'count' from public.app_config where key='admin_audit_fixture'), '2', 'audit failure rolls back config update');
select is((select count(*)::integer from public.admin_config_audit where target_key='admin_audit_fixture'), 1, 'failed transaction leaves no history row');
reset role;
drop trigger reject_audit_test on public.admin_config_audit;

select * from finish();
rollback;

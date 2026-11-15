begin;
create extension if not exists pgtap with schema extensions;
set local search_path = public, extensions;
select no_plan();

insert into auth.users (id, email) values
  ('e8e00000-0000-4000-8000-000000000001', 'exp-admin@example.test'),
  ('e8e00000-0000-4000-8000-000000000002', 'exp-user@example.test');
update public.profiles set role = 'admin' where id = 'e8e00000-0000-4000-8000-000000000001';

-- Access
select ok((select relrowsecurity from pg_class where oid = 'public.admin_experiments'::regclass), 'experiments have RLS enabled');
select ok(not has_table_privilege('anon', 'public.admin_experiments', 'select'), 'anon cannot read experiments');
select ok(not has_table_privilege('authenticated', 'public.admin_experiments', 'select'), 'authenticated cannot read experiments');
select ok(not has_table_privilege('authenticated', 'public.admin_experiments', 'insert'), 'authenticated cannot write experiments');
select ok(not has_table_privilege('service_role', 'public.admin_experiments', 'delete'), 'service role cannot delete experiments');
select ok(not has_function_privilege('anon', 'public.admin_create_experiment(uuid,text,text,text,text,text,text,numeric,timestamptz,date)', 'execute'), 'anon cannot create');
select ok(not has_function_privilege('authenticated', 'public.admin_update_experiment(uuid,text,text,text,text,text,text,numeric,timestamptz,date)', 'execute'), 'authenticated cannot update');
select ok(not has_function_privilege('authenticated', 'public.admin_record_experiment_verdict(uuid,text,text,text,numeric,text)', 'execute'), 'authenticated cannot record a verdict');
select ok(has_function_privilege('service_role', 'public.admin_record_experiment_verdict(uuid,text,text,text,numeric,text)', 'execute'), 'service role can record a verdict');

-- Seed
select is((select count(*)::integer from public.admin_experiments where slug in ('trial_reserve','landing_hero','zone_notice','near_zone')), 4, 'the four running experiments are seeded');
select is((select status from public.admin_experiments where slug = 'near_zone'), 'paused', 'near_zone is paused');
select is((select baseline_value from public.admin_experiments where slug = 'trial_reserve'), 48::numeric, 'trial_reserve baseline is 48');
select is((select baseline_value from public.admin_experiments where slug = 'landing_hero'), null, 'landing_hero baseline is not invented');
select is((select count(*)::integer from public.admin_experiments e join public.app_config c on c.key = e.config_key where e.slug in ('trial_reserve','landing_hero','zone_notice','near_zone')), 4, 'each seeded config_key exists in app_config');

set local role service_role;
select throws_ok($$select public.admin_create_experiment('e8e00000-0000-4000-8000-000000000002','t_one','T','k','h','m',null,null,null,null)$$, '42501', 'admin_required', 'a non-admin actor cannot create');
select throws_ok($$select public.admin_update_experiment('e8e00000-0000-4000-8000-000000000002','trial_reserve','T',null,'','',null,null,null,null)$$, '42501', 'admin_required', 'a non-admin actor cannot update');
select throws_ok($$select public.admin_record_experiment_verdict('e8e00000-0000-4000-8000-000000000002','trial_reserve','won','x',1,'n')$$, '42501', 'admin_required', 'a non-admin actor cannot record a verdict');

select is(public.admin_create_experiment('e8e00000-0000-4000-8000-000000000001','t_one','  Prueba uno ',' app_k ','Si pasa A, pasa B','Mide C','base 10',10,'2026-11-15 12:00+00','2026-11-25'), 't_one', 'admin creates an experiment');
select is((select status from public.admin_experiments where slug = 't_one'), 'running', 'a new experiment is running');
select is((select title from public.admin_experiments where slug = 't_one'), 'Prueba uno', 'title is trimmed');
select throws_ok($$select public.admin_create_experiment('e8e00000-0000-4000-8000-000000000001','t_one','Otra',null,'','',null,null,null,null)$$, '23505', 'experiment_exists', 'duplicate slug is rejected');
select throws_ok($$select public.admin_create_experiment('e8e00000-0000-4000-8000-000000000001','Mal Slug','Otra',null,'','',null,null,null,null)$$, '23514', null, 'a bad slug is rejected');

select lives_ok($$select public.admin_update_experiment('e8e00000-0000-4000-8000-000000000001','t_one','Prueba uno bis','','H2','M2',null,null,null,'2026-12-01')$$, 'admin edits an experiment');
select is((select title || '|' || coalesce(config_key, 'null') || '|' || review_at::text from public.admin_experiments where slug = 't_one'), 'Prueba uno bis|null|2026-12-01', 'edit stores new values and an empty switch becomes null');
select throws_ok($$select public.admin_update_experiment('e8e00000-0000-4000-8000-000000000001','nope','T',null,'','',null,null,null,null)$$, 'P0002', 'experiment_not_found', 'unknown slug is not found');

select lives_ok($$select public.admin_record_experiment_verdict('e8e00000-0000-4000-8000-000000000001','t_one','won','Subió a 60 %',60,'Se queda prendido')$$, 'admin records a verdict');
select is((select status || '|' || result_value::text || '|' || (decided_at is not null)::text from public.admin_experiments where slug = 't_one'), 'won|60|true', 'verdict stores status, result and decision date');
select throws_ok($$select public.admin_record_experiment_verdict('e8e00000-0000-4000-8000-000000000001','t_one','maybe',null,null,null)$$, '22023', 'invalid_status', 'unknown status is rejected');
select lives_ok($$select public.admin_record_experiment_verdict('e8e00000-0000-4000-8000-000000000001','t_one','running','ignorado',1,'ignorada')$$, 'admin reopens the experiment');
select is((select status || '|' || coalesce(result_text, 'null') || '|' || coalesce(verdict_note, 'null') || '|' || (decided_at is null)::text from public.admin_experiments where slug = 't_one'), 'running|null|null|true', 'reopening clears the result and the decision date');
select lives_ok($$select public.admin_record_experiment_verdict('e8e00000-0000-4000-8000-000000000001','t_one','paused',null,null,'Esperando un arreglo')$$, 'admin pauses the experiment');
select is((select verdict_note from public.admin_experiments where slug = 't_one'), 'Esperando un arreglo', 'a paused experiment keeps its note');
reset role;

select throws_ok($$update public.admin_experiments set status = 'won' where slug = 't_one'$$, '23514', null, 'a verdict without a decision date is rejected by the table');

select * from finish();
rollback;

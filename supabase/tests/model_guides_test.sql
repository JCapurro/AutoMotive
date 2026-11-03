-- PAR-04 (migrations 20261204120000_par04_model_guides, 20261204120100_par04_guide_events,
-- 20261204120200_par04_question_origins): who reads model_guides, who writes,
-- what can be published, the guide jobs in llm_jobs and log_guide_event.
begin;
create extension if not exists pgtap with schema extensions;
set local search_path = public, extensions;
select no_plan();

insert into auth.users (id, email) values
  ('9a1de000-0000-4000-8000-000000000001', 'guides-admin@example.test'),
  ('9a1de000-0000-4000-8000-000000000002', 'guides-user@example.test');
update public.profiles set role = 'admin' where id = '9a1de000-0000-4000-8000-000000000001';

-- A complete guide, as the editor sends it.
create temporary table v (values jsonb) on commit drop;
insert into v values ('{
  "make": "ford", "model": "fiesta", "generation_label": null, "year_from": 2011, "year_to": 2019,
  "slug_make": "ford", "slug_model": "fiesta",
  "body": {"known_issues": [{"text": "Caja Powershift: tirones en primera."}],
           "visit_checklist": [{"text": "Probar la caja en frío."}],
           "versions_equipment": [{"text": "S, SE y Titanium."}],
           "maintenance_costs": [{"text": "Distribución por correa: revisar cuándo se cambió."}],
           "generations": [{"label": "Mk7", "year_from": 2011, "year_to": 2019, "text": "Kinetic Design."}]},
  "questions": [{"text": "¿Tiene los services hechos?", "why": "x"}, {"text": "¿Cuándo se cambió la correa?", "why": "x"},
                {"text": "¿La caja hace tirones en frío?", "why": "x"}],
  "sources": [{"title": "Manual", "url": "https://example.test/manual", "kind": "manual", "verified": false}]
}');
grant select on v to service_role;

-- ---------------------------------------------------------------------------
-- Privileges
-- ---------------------------------------------------------------------------

select ok((select relrowsecurity from pg_class where oid = 'public.model_guides'::regclass), 'model_guides has RLS');
select ok(not has_table_privilege('anon', 'public.model_guides', 'insert'), 'anon cannot insert guides');
select ok(not has_table_privilege('authenticated', 'public.model_guides', 'update'), 'authenticated cannot update guides');
select ok(not has_table_privilege('authenticated', 'public.model_guides', 'delete'), 'authenticated cannot delete guides');
select ok(has_column_privilege('anon', 'public.model_guides', 'body', 'select'), 'anon reads the body');
select ok(not has_column_privilege('anon', 'public.model_guides', 'reviewed_by', 'select'), 'anon cannot read reviewed_by');
select ok(not has_column_privilege('authenticated', 'public.model_guides', 'llm_version', 'select'), 'authenticated cannot read llm_version');
select ok(not has_column_privilege('anon', 'public.model_guides', 'status', 'select'), 'anon cannot read status');
select ok(has_column_privilege('authenticated', 'public.matches', 'question_origins', 'select'),
          'question_origins is readable like the other columns of matches (RLS: own rows)');
select ok(not has_function_privilege('authenticated', 'public.admin_save_model_guide(bigint,jsonb,timestamptz,uuid)', 'execute'),
          'authenticated cannot call admin_save_model_guide');
select ok(not has_function_privilege('anon', 'public.admin_set_model_guide_status(bigint,text,uuid)', 'execute'),
          'anon cannot publish');
select ok(not has_function_privilege('authenticated', 'public.admin_request_model_guide(bigint,boolean,uuid)', 'execute'),
          'authenticated cannot request a guide job');
select ok(not has_function_privilege('authenticated', 'public.admin_guide_candidates(integer)', 'execute'),
          'authenticated cannot list candidates');
select ok(has_function_privilege('anon', 'public.log_guide_event(text,text,text)', 'execute'), 'anon can log guide events');

-- ---------------------------------------------------------------------------
-- Admin writes
-- ---------------------------------------------------------------------------

set local role service_role;
select throws_ok($$select public.admin_save_model_guide(null, (select values from v), null, '9a1de000-0000-4000-8000-000000000002')$$,
                 '42501', 'admin_required', 'a non-admin actor cannot save');
select throws_ok($$select public.admin_save_model_guide(null, jsonb_set((select values from v), '{model}', '"Tesla"'), null,
                   '9a1de000-0000-4000-8000-000000000001')$$,
                 '22023', 'guide_unknown_model', 'the model must be in the catalog');
select lives_ok($$select public.admin_save_model_guide(null, (select values from v), null, '9a1de000-0000-4000-8000-000000000001')$$,
                'the admin creates a guide');
reset role;
select is((select make || ' ' || model || ' ' || status || ' ' || origin from public.model_guides),
          'Ford Fiesta draft manual', 'stored with the catalog spelling, as a hand-written draft');

set local role service_role;
select throws_ok($$select public.admin_save_model_guide(null, (select values from v), null, '9a1de000-0000-4000-8000-000000000001')$$,
                 '23505', 'guide_duplicate', 'one guide per model and generation');
select throws_ok($$select public.admin_save_model_guide((select id from public.model_guides), (select values from v),
                   '2000-01-01', '9a1de000-0000-4000-8000-000000000001')$$,
                 '40001', 'guide_conflict', 'an outdated updated_at does not overwrite');
select throws_ok($$select public.admin_set_model_guide_status((select id from public.model_guides), 'published',
                   '9a1de000-0000-4000-8000-000000000001')$$,
                 '22023', 'guide_sources_unverified', 'not published with an unchecked source');
select lives_ok($$select public.admin_save_model_guide(g.id, jsonb_set((select values from v), '{body,generations}', '[]'),
                  g.updated_at, '9a1de000-0000-4000-8000-000000000001') from public.model_guides g$$,
                'a draft may be saved incomplete');
select throws_ok($$select public.admin_set_model_guide_status((select id from public.model_guides), 'published',
                   '9a1de000-0000-4000-8000-000000000001')$$,
                 '22023', 'guide_incomplete', 'not published with an empty section');
reset role;

-- Direct writes bypass nothing: the published row needs a review.
select throws_ok($$update public.model_guides set status = 'published'$$, '23514', null,
                 'a published row without review breaks the check');

set local role service_role;
select lives_ok($$select public.admin_save_model_guide(g.id, jsonb_set((select values from v), '{sources,0,verified}', 'true'),
                  g.updated_at, '9a1de000-0000-4000-8000-000000000001') from public.model_guides g$$,
                'the reviewer checks the source');
select lives_ok($$select public.admin_set_model_guide_status((select id from public.model_guides), 'published',
                  '9a1de000-0000-4000-8000-000000000001')$$, 'then publishes');
reset role;
select ok((select reviewed_by = '9a1de000-0000-4000-8000-000000000001' and reviewed_at is not null and published_at is not null
             from public.model_guides), 'publishing records the reviewer');

-- A second guide that stays a draft.
insert into public.model_guides (make, model, slug_make, slug_model) values ('Volkswagen', 'Gol Trend', 'volkswagen', 'gol-trend');

-- ---------------------------------------------------------------------------
-- Reads
-- ---------------------------------------------------------------------------

set local role anon;
select is((select string_agg(slug_model, ',') from public.model_guides), 'fiesta', 'anon reads only the published guide');
select throws_ok($$select reviewed_by from public.model_guides$$, '42501', null, 'anon cannot select reviewed_by');
select throws_ok($$select * from public.model_guides$$, '42501', null, 'select * is denied (column grants)');
reset role;
set local role authenticated;
set local request.jwt.claims = '{"sub": "9a1de000-0000-4000-8000-000000000002", "role": "authenticated"}';
select is((select count(*)::int from public.model_guides), 1, 'a user reads only the published guide');
select throws_ok($$select llm_version from public.model_guides$$, '42501', null, 'a user cannot select llm_version');
select throws_ok($$update public.model_guides set body = '{}'$$, '42501', null, 'a user cannot update');
reset role;

-- ---------------------------------------------------------------------------
-- llm_jobs: kind model_guide
-- ---------------------------------------------------------------------------

set local role authenticated;
set local request.jwt.claims = '{"sub": "9a1de000-0000-4000-8000-000000000002", "role": "authenticated"}';
select throws_ok($$insert into public.llm_jobs (user_id, kind, input)
                   values ('9a1de000-0000-4000-8000-000000000002', 'model_guide',
                           '{"guide_id": 1, "make": "Ford", "model": "Fiesta"}')$$,
                 '42501', null, 'a user cannot enqueue a guide job');
select lives_ok($$insert into public.llm_jobs (user_id, kind, input)
                  values ('9a1de000-0000-4000-8000-000000000002', 'parse_search', '{"text": "Busco un Fiesta"}')$$,
                'a user still enqueues parse_search');
reset role;
select throws_ok($$insert into public.llm_jobs (user_id, kind, input)
                   values ('9a1de000-0000-4000-8000-000000000001', 'model_guide', '{"make": "Ford"}')$$,
                 '23514', null, 'a guide job needs guide_id, make and model');

set local role service_role;
select throws_ok($$select public.admin_request_model_guide((select id from public.model_guides where model = 'Gol Trend'), false,
                   '9a1de000-0000-4000-8000-000000000001')$$,
                 '22023', 'guide_generation_off', 'the generation starts off');
reset role;
update public.app_config set value = jsonb_set(jsonb_set(value, '{model_guide,enabled}', 'true'), '{model_guide,per_day}', '1')
 where key = 'llm_limits';
set local role service_role;
select throws_ok($$select public.admin_request_model_guide((select id from public.model_guides where model = 'Gol Trend'), false,
                   '9a1de000-0000-4000-8000-000000000002')$$,
                 '42501', 'admin_required', 'only an admin asks for a draft');
select throws_ok($$select public.admin_request_model_guide((select id from public.model_guides where model = 'Fiesta'), false,
                   '9a1de000-0000-4000-8000-000000000001')$$,
                 '22023', 'guide_published', 'a published guide is never regenerated');
select lives_ok($$select public.admin_request_model_guide((select id from public.model_guides where model = 'Gol Trend'), false,
                  '9a1de000-0000-4000-8000-000000000001')$$, 'the admin asks for a draft');
select throws_ok($$select public.admin_request_model_guide((select id from public.model_guides where model = 'Gol Trend'), false,
                   '9a1de000-0000-4000-8000-000000000001')$$,
                 '22023', 'guide_job_pending', 'one pending job per guide');
reset role;
select is((select user_id::text || ' ' || kind || ' ' || status from public.llm_jobs where kind = 'model_guide'),
          '9a1de000-0000-4000-8000-000000000001 model_guide queued', 'the job belongs to the admin');
-- The job is done (it called the provider): the daily cap of 1 is reached.
update public.llm_jobs set status = 'done', provider = 'openai:x', output = '{}' where kind = 'model_guide';
insert into public.model_guides (make, model, slug_make, slug_model) values ('Toyota', 'Etios', 'toyota', 'etios');
set local role service_role;
select throws_ok($$select public.admin_request_model_guide((select id from public.model_guides where model = 'Etios'), false,
                   '9a1de000-0000-4000-8000-000000000001')$$,
                 'P0001', 'guide_daily_cap', 'the daily cap');
reset role;
-- A cache hit does not count.
update public.llm_jobs set provider = 'cache' where kind = 'model_guide';
set local role service_role;
select lives_ok($$select public.admin_request_model_guide((select id from public.model_guides where model = 'Etios'), false,
                  '9a1de000-0000-4000-8000-000000000001')$$, 'a cache hit does not count for the cap');
reset role;
update public.app_config set value = jsonb_set(jsonb_set(value, '{model_guide,per_day}', '30'), '{model_guide,per_month}', '1')
 where key = 'llm_limits';
update public.llm_jobs set status = 'done', provider = 'openai:x', output = '{}' where kind = 'model_guide';
insert into public.model_guides (make, model, slug_make, slug_model) values ('Toyota', 'Corolla', 'toyota', 'corolla');
set local role service_role;
select throws_ok($$select public.admin_request_model_guide((select id from public.model_guides where model = 'Corolla'), false,
                   '9a1de000-0000-4000-8000-000000000001')$$,
                 'P0001', 'guide_monthly_cap', 'the monthly cap');
reset role;

-- Hand edits after the last generation are replaced only with force.
update public.app_config set value = jsonb_set(value, '{model_guide,per_month}', '60') where key = 'llm_limits';
update public.model_guides set questions = '[{"text": "¿Hola?"}]' where model = 'Corolla';
set local role service_role;
select throws_ok($$select public.admin_request_model_guide((select id from public.model_guides where model = 'Corolla'), false,
                   '9a1de000-0000-4000-8000-000000000001')$$,
                 '22023', 'guide_has_manual_edits', 'hand edits need force');
select lives_ok($$select public.admin_request_model_guide((select id from public.model_guides where model = 'Corolla'), true,
                  '9a1de000-0000-4000-8000-000000000001')$$, 'force replaces them');
reset role;

-- The hourly cap of the assisted mode ignores guides.
update public.app_config set value = jsonb_set(value, '{per_user_hour}', '2') where key = 'llm_limits';
select lives_ok($$insert into public.llm_jobs (user_id, kind, input)
                  values ('9a1de000-0000-4000-8000-000000000001', 'parse_search', '{"text": "Busco un Fiesta"}')$$,
                'three guide jobs in the hour do not use up the admin''s assisted mode');
select lives_ok($$insert into public.llm_jobs (user_id, kind, input)
                  values ('9a1de000-0000-4000-8000-000000000001', 'parse_search', '{"text": "Busco un Fiesta"}')$$,
                'the second assisted job of the hour');
select throws_ok($$insert into public.llm_jobs (user_id, kind, input)
                   values ('9a1de000-0000-4000-8000-000000000001', 'parse_search', '{"text": "Busco un Fiesta"}')$$,
                 'P0001', 'llm_rate_limited', 'the third goes over per_user_hour');

-- ---------------------------------------------------------------------------
-- Candidates
-- ---------------------------------------------------------------------------

insert into public.search_profiles (user_id, name, filters) values
  ('9a1de000-0000-4000-8000-000000000002', 'a', '{"make": "Ford", "model": "fiesta"}'),
  ('9a1de000-0000-4000-8000-000000000002', 'b', '{"make": "Ford", "model": "Fiesta"}'),
  ('9a1de000-0000-4000-8000-000000000002', 'c', '{"make": "Ford"}');
set local role service_role;
select ok((select active_searches >= 2 and guide_status = 'published' from public.admin_guide_candidates(200)
            where make = 'Ford' and model = 'Fiesta'), 'candidates count searches by catalog model, with the guide state');
reset role;

-- ---------------------------------------------------------------------------
-- log_guide_event
-- ---------------------------------------------------------------------------

set local request.jwt.claims = '{"role": "anon"}';
set local role anon;
select throws_ok($$select public.log_guide_event('listing_saved', 'ford', 'fiesta')$$, '22023', 'invalid_guide_event',
                 'only the three guide events');
select throws_ok($$select public.log_guide_event('guide_viewed', 'volkswagen', 'gol-trend')$$, 'P0002', 'guide_not_found',
                 'not for a draft');
select lives_ok($$select public.log_guide_event('guide_viewed', 'ford', 'fiesta')$$, 'a visitor logs guide_viewed');
reset role;
select ok((select user_id is null and props->>'make' = 'Ford' from public.events where name = 'guide_viewed'),
          'without a user, with the guide');
set local role authenticated;
set local request.jwt.claims = '{"sub": "9a1de000-0000-4000-8000-000000000002", "role": "authenticated"}';
select lives_ok($$select public.log_guide_event('guide_cta_clicked', 'ford', 'fiesta')$$, 'a user logs guide_cta_clicked');
reset role;
select is((select user_id::text from public.events where name = 'guide_cta_clicked'),
          '9a1de000-0000-4000-8000-000000000002', 'with the user');
set local role service_role;
select is((select viewed::int + cta_clicked::int from public.admin_guide_event_counts(30)
            where guide_id = (select id from public.model_guides where model = 'Fiesta')), 2, 'the admin counts them');
reset role;

-- Unpublishing goes back to draft and keeps the review.
set local role service_role;
select lives_ok($$select public.admin_set_model_guide_status((select id from public.model_guides where model = 'Fiesta'), 'draft',
                  '9a1de000-0000-4000-8000-000000000001')$$, 'unpublish');
reset role;
set local role anon;
select is((select count(*)::int from public.model_guides), 0, 'an unpublished guide disappears for anon');
reset role;

select * from finish();
rollback;

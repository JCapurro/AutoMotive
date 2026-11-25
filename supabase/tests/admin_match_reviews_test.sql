-- Dedicated local test database only. All fixtures and changes roll back.
begin;
create extension if not exists pgtap with schema extensions;
set local search_path = public, extensions;
select no_plan();

select has_table('admin_match_reviews');
select ok((select relrowsecurity from pg_class where oid = 'public.admin_match_reviews'::regclass), 'reviews have RLS enabled');
select ok(not has_table_privilege('authenticated', 'public.admin_match_reviews', 'select'), 'authenticated cannot read reviews');
select ok(not has_table_privilege('anon', 'public.admin_match_reviews', 'insert'), 'anon cannot write reviews');
select ok(not has_function_privilege('authenticated', 'public.admin_match_review_draw(date,integer)', 'execute'), 'authenticated cannot draw');
select ok(not has_function_privilege('anon', 'public.admin_match_review_stats(integer)', 'execute'), 'anon cannot read stats');
select ok(has_function_privilege('service_role', 'public.admin_match_review_save(bigint,text,text[],text,uuid,text)', 'execute'), 'service role can save');
select ok(not (select prosecdef from pg_proc where oid = 'public.admin_match_review_draw(date,integer)'::regprocedure), 'draw is security invoker');

-- Fixtures: skip lifecycle triggers; the RPCs themselves run normally.
set local session_replication_role = replica;
delete from public.admin_match_reviews;
delete from public.notifications;
delete from public.matches;
delete from public.search_profiles;
delete from public.listings;
delete from public.profiles;
delete from auth.users;

insert into auth.users (id, email) values
  ('ac000000-0000-4000-8000-000000000001', 'user@audit.test'),
  ('ac000000-0000-4000-8000-0000000000aa', 'admin@audit.test');
insert into public.profiles (id, email, role) values
  ('ac000000-0000-4000-8000-000000000001', 'user@audit.test', 'user'),
  ('ac000000-0000-4000-8000-0000000000aa', 'admin@audit.test', 'admin');
insert into public.search_profiles (id, user_id, name, filters) overriding system value values
  (98001, 'ac000000-0000-4000-8000-000000000001', 'user search', '{}'),
  (98002, 'ac000000-0000-4000-8000-0000000000aa', 'admin search', '{}');
insert into public.listings (id, source, external_id, url, title) overriding system value
select 98000 + n, case when n <= 6 then 'kavak' else 'facebook' end, 'audit-' || n, 'https://example.test/' || n, 'Auto ' || n
  from generate_series(1, 11) n;
-- 1-3 high/kavak, 4-6 good/kavak, 7-8 high/facebook (user search);
-- 9 sent to the admin's search, 10 only queued, 11 sent 10 days ago.
insert into public.matches (id, search_profile_id, listing_id, score, level, score_breakdown, match_reasons, scoring_version) overriding system value
select 98000 + n, case when n = 9 then 98002 else 98001 end, 98000 + n, 80,
       case when n in (1,2,3,7,8,9,10,11) then 'high'::public.match_level else 'good'::public.match_level end, '{}', '[]', 'test'
  from generate_series(1, 11) n;
insert into public.notifications (user_id, match_id, listing_id, kind, channel, status, dedupe_key, sent_at)
select sp.user_id, m.id, m.listing_id, 'new_match', 'email',
       case when m.id = 98010 then 'queued'::public.notification_status else 'sent'::public.notification_status end,
       'audit:' || m.id, case when m.id = 98011 then now() - interval '10 days' else now() - interval '1 day' end
  from public.matches m join public.search_profiles sp on sp.id = m.search_profile_id;
set local session_replication_role = origin;

select throws_ok($$select public.admin_match_review_draw('2026-11-10', 4)$$, '22023', 'invalid_review_week', 'week must be a Monday');
select throws_ok($$select public.admin_match_review_draw(null, 0)$$, '22023', 'invalid_review_week', 'size must be positive');

select is((public.admin_match_review_draw(null, 4))->>'total', '4', 'draw reaches the requested size');
select is((select count(*)::int from public.admin_match_reviews), 4, 'four rows stored');
select ok(not exists (select 1 from public.admin_match_reviews where match_id in (98009, 98010, 98011)),
  'admin searches, unsent alerts and old alerts are never sampled');
select ok((select count(distinct (level, source)) from public.admin_match_reviews) = 3, 'one match from each level/source group before repeating');
select ok((select sample_week = public.admin_match_review_week() from public.admin_match_reviews limit 1), 'sample week is the current Monday');

create temp table first_draw as select match_id from public.admin_match_reviews;
select is((public.admin_match_review_draw(null, 4))->>'added', '0', 'drawing again adds nothing');
select is((select count(*)::int from public.admin_match_reviews), 4, 'still four rows');
select is((public.admin_match_review_draw(null, 6))->>'added', '2', 'a bigger target only tops up');
select is((select count(*)::int from first_draw f join public.admin_match_reviews r using (match_id)), 4, 'earlier rows are kept');
select is((public.admin_match_review_draw(null, 20))->>'total', '8', 'draws only as many as the data allows (8 candidates)');
select is((jsonb_array_length(public.admin_match_review_queue())), 8, 'queue lists the sample');
select ok((public.admin_match_review_queue()->0->'listing'->>'title') like 'Auto %', 'queue carries the listing');
select ok((public.admin_match_review_queue()->0->'search'->>'name') = 'user search', 'queue carries the search');

-- Saving
select throws_ok($$select public.admin_match_review_save((select min(id) from public.admin_match_reviews), 'bad', '{version}', null, 'ac000000-0000-4000-8000-000000000001')$$, '42501', 'admin_required', 'only an admin can save');
select throws_ok($$select public.admin_match_review_save((select min(id) from public.admin_match_reviews), 'meh', '{}', null, 'ac000000-0000-4000-8000-0000000000aa')$$, '22023', 'invalid_verdict', 'unknown verdict is rejected');
select throws_ok($$select public.admin_match_review_save((select min(id) from public.admin_match_reviews), 'bad', '{}', null, 'ac000000-0000-4000-8000-0000000000aa')$$, '22023', 'reasons_required', 'fair and bad need a reason');
select throws_ok($$select public.admin_match_review_save((select min(id) from public.admin_match_reviews), 'bad', '{color}', null, 'ac000000-0000-4000-8000-0000000000aa')$$, '22023', 'invalid_reason', 'reasons come from a fixed set');
select throws_ok($$select public.admin_match_review_save(-1, 'good', '{}', null, 'ac000000-0000-4000-8000-0000000000aa')$$, 'P0002', 'review_not_found', 'unknown row');

select lives_ok($$select public.admin_match_review_save((select min(id) from public.admin_match_reviews), 'bad', '{version,price,version}', '  trim muy distinto ', 'ac000000-0000-4000-8000-0000000000aa')$$, 'saves a bad verdict');
select is((select reasons from public.admin_match_reviews order by id limit 1), array['price','version'], 'reasons are de-duplicated and sorted');
select is((select note from public.admin_match_reviews order by id limit 1), 'trim muy distinto', 'note is trimmed');
select ok((select reviewed_at is not null and reviewer_id = 'ac000000-0000-4000-8000-0000000000aa' from public.admin_match_reviews order by id limit 1), 'reviewer and time are stored');
select lives_ok($$select public.admin_match_review_save((select min(id) + 1 from public.admin_match_reviews), 'good', '{version}', '', 'ac000000-0000-4000-8000-0000000000aa')$$, 'saves a good verdict');
select is((select reasons from public.admin_match_reviews order by id offset 1 limit 1), '{}'::text[], 'good drops reasons');
select is((select note from public.admin_match_reviews order by id offset 1 limit 1), null, 'blank note becomes null');
select lives_ok($$select public.admin_match_review_save((select min(id) from public.admin_match_reviews), 'fair', '{year}', null, 'ac000000-0000-4000-8000-0000000000aa')$$, 'a verdict can be changed');
select is((select reasons from public.admin_match_reviews order by id limit 1), array['year'], 'changed verdict replaces the reasons');
select throws_ok($$update public.admin_match_reviews set verdict = 'bad' where id = (select max(id) from public.admin_match_reviews)$$, '23514', null, 'table refuses a verdict without time or reasons');

-- Quién revisó: persona, automático o sin declarar.
select ok((select reviewer_kind is null from public.admin_match_reviews order by id limit 1), 'a save that declares nothing leaves the kind unknown');
select throws_ok($$select public.admin_match_review_save((select min(id) from public.admin_match_reviews), 'good', '{}', null, 'ac000000-0000-4000-8000-0000000000aa', 'robot')$$, '22023', 'invalid_reviewer_kind', 'the kind is person or automated');
select lives_ok($$select public.admin_match_review_save((select min(id) from public.admin_match_reviews), 'fair', '{year}', null, 'ac000000-0000-4000-8000-0000000000aa', 'person')$$, 'a person can sign a review');
select is((select reviewer_kind from public.admin_match_reviews order by id limit 1), 'person', 'the kind is stored');
select is((public.admin_match_review_queue()->0->>'reviewer_kind'), 'person', 'the queue carries the kind');
select is((public.admin_match_review_queue()->0->>'reviewer_id'), 'ac000000-0000-4000-8000-0000000000aa', 'the queue carries the reviewer');
select lives_ok($$select public.admin_match_review_save((select min(id) from public.admin_match_reviews), 'fair', '{year}', null, 'ac000000-0000-4000-8000-0000000000aa', 'automated')$$, 'a script can say it is automated');
select is((public.admin_match_review_queue()->0->>'reviewer_kind'), 'automated', 'the kind follows the last save');
select lives_ok($$select public.admin_match_review_save((select min(id) from public.admin_match_reviews), 'fair', '{year}', null, 'ac000000-0000-4000-8000-0000000000aa')$$, 'the five-argument call still works');

-- Stats: one good, one fair so far.
select is((select sum((r->>'good')::int) from jsonb_array_elements(public.admin_match_review_stats()->'rows') r), 1::bigint, 'stats count one good');
select is((select sum((r->>'fair')::int) from jsonb_array_elements(public.admin_match_review_stats()->'rows') r), 1::bigint, 'stats count one fair');
select is((select sum((r->>'sampled')::int) from jsonb_array_elements(public.admin_match_review_stats()->'rows') r), 8::bigint, 'stats count the sampled total');
select is((public.admin_match_review_stats()->'reasons'->0->>'reason'), 'year', 'reasons only count reviewed rows');

-- A deleted match keeps its review (snapshot level and source).
delete from public.notifications where match_id = (select match_id from public.admin_match_reviews order by id limit 1);
delete from public.matches where id = (select match_id from public.admin_match_reviews order by id limit 1);
select ok((select match_id is null and level is not null and source is not null from public.admin_match_reviews order by id limit 1), 'review survives a deleted match');

select * from finish();
rollback;

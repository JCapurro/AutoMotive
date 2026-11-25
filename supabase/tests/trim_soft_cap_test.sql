-- Trim blando (migration 20270115120000_trim_soft_cap.sql). Run with: supabase test db
-- app_config.trim_soft_cap is off by default; search_results (default order) puts the matches the worker marked
-- score_breakdown.trim_cap after the rest, and is the order it was without the mark.
-- Run in an isolated local database; all fixtures roll back.
begin;
create extension if not exists pgtap with schema extensions;
select no_plan();

select is((select value from public.app_config where key = 'trim_soft_cap'), '{"enabled": false}'::jsonb,
          'trim_soft_cap: off by default');

insert into auth.users (instance_id, id, aud, role, email, created_at, updated_at) values
  ('00000000-0000-0000-0000-000000000000', 'c0270000-0000-0000-0000-000000000001', 'authenticated', 'authenticated', 'a@trimcap.test', now(), now());
insert into public.search_profiles (id, user_id, name, filters, bootstrapped_at) overriding system value values
  (9961, 'c0270000-0000-0000-0000-000000000001', 'Versión', '{"make": "Pgtap", "model": "Trim", "trims": ["Titanium"]}', now());
insert into public.listings (id, source, external_id, url, title, make, model, trim, price, currency, price_usd, status)
overriding system value
select 996000 + i, 'mercadolibre', 'TRIMCAP-' || i, 'https://example.test/trimcap-' || i, 'Pgtap Trim ' || i,
       'Pgtap', 'Trim', case when i in (1, 3) then 'SE Plus' else 'Titanium' end, 10000, 'USD', 10000, 'active'
  from generate_series(1, 5) i;

-- 1 and 3: another version, marked, with the best scores. 2, 4: the version asked for. 5: no mark key at all.
insert into public.matches (id, search_profile_id, listing_id, score, level, score_breakdown, match_reasons, scoring_version)
overriding system value values
  (99610001, 9961, 996001, 95, 'match', '{"trim_cap": true}', '{}', 'test'),
  (99610002, 9961, 996002, 80, 'good',  '{}', '{}', 'test'),
  (99610003, 9961, 996003, 90, 'match', '{"trim_cap": true}', '{}', 'test'),
  (99610004, 9961, 996004, 70, 'good',  '{}', '{}', 'test'),
  (99610005, 9961, 996005, 60, 'match', '{"trim_cap": false}', '{}', 'test');

set local role authenticated;
set local request.jwt.claims = '{"sub": "c0270000-0000-0000-0000-000000000001", "role": "authenticated"}';

select results_eq($$select listing_id from public.search_results(9961, 'all', 'score')$$,
                  $$values (996002::bigint), (996004::bigint), (996005::bigint), (996001::bigint), (996003::bigint)$$,
                  'score order: the version asked for first, the other versions after, each by score');
select results_eq($$select listing_id from public.search_results(9961, 'all', 'price')$$,
                  $$values (996005::bigint), (996004::bigint), (996003::bigint), (996002::bigint), (996001::bigint)$$,
                  'price order: the mark changes nothing (same price: the tie-break, newest id first)');
select is((select count(*) from public.search_results(9961, 'all', 'score')), 5::bigint,
          'every match is still in the list');

reset role;
update public.matches set score_breakdown = '{}' where search_profile_id = 9961;
set local role authenticated;
set local request.jwt.claims = '{"sub": "c0270000-0000-0000-0000-000000000001", "role": "authenticated"}';
select results_eq($$select listing_id from public.search_results(9961, 'all', 'score')$$,
                  $$values (996001::bigint), (996003::bigint), (996002::bigint), (996004::bigint), (996005::bigint)$$,
                  'without the mark: by score alone, as before');
reset role;

select * from finish();
rollback;

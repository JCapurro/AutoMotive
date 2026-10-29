-- Comparables fase 1 (migration 20261105120000_comparables_confirmed_pool.sql)
-- and fase 2 (20261106120000_comparables_full_read.sql):
-- the config, the grants and the web's door to the pool. The rules themselves
-- are tested in worker/tests/test_intelligence_postgres.py
-- (ComparablesConfirmationTests). Run with: supabase test db
begin;
create extension if not exists pgtap with schema extensions;
select plan(17);

-- ---------------------------------------------------------------- app_config, as the migration left it
select is((select value->'confirm_sources' from public.app_config where key = 'comparables'),
          '["autocity", "carone", "deruedas", "gruporandazzo", "mardelusados", "rosariogarage", "mercadolibre"]'::jsonb,
          'confirm_sources: the sources whose reads are complete, without kavak or autocosmos; mercadolibre since fase 2');
select is((select (value->>'confirm_grace_hours')::int from public.app_config where key = 'comparables'), 36,
          'confirm_grace_hours: 36');
select is((select value->'gone_max_age_days' from public.app_config where key = 'comparables'), null,
          'gone_max_age_days unset: gone listings keep counting');
select is((select value->>'min_n' from public.app_config where key = 'comparables'), '5',
          'the existing keys stay');

-- ---------------------------------------------------------------- grants
select is(array(select r || ' ' || f
                  from unnest(array['anon', 'authenticated']) r,
                       unnest(array['public.listing_unconfirmed(text,text,text,integer,integer,timestamptz,jsonb,interval)',
                                    'public.comparable_listings(bigint,integer,numeric,integer)',
                                    'public.comparables(bigint,integer,integer,numeric,integer)']) f
                 where has_function_privilege(r, f, 'execute')),
          '{}'::text[], 'anon and authenticated can execute neither the internals nor comparables()');
select ok(not has_function_privilege('anon', 'public.comparable_pool(bigint,integer,numeric,integer)', 'execute'),
          'anon cannot execute comparable_pool');
select ok(has_function_privilege('authenticated', 'public.comparable_pool(bigint,integer,numeric,integer)', 'execute'),
          'authenticated can execute comparable_pool (the listing page)');
select is(array(select f
                  from unnest(array['public.listing_unconfirmed(text,text,text,integer,integer,timestamptz,jsonb,interval)',
                                    'public.comparable_listings(bigint,integer,numeric,integer)',
                                    'public.comparable_pool(bigint,integer,numeric,integer)',
                                    'public.comparables(bigint,integer,integer,numeric,integer)']) f
                 where not has_function_privilege('service_role', f, 'execute')),
          '{}'::text[], 'the service role (the worker) can execute all four');
select is((select prosecdef from pg_proc where oid = 'public.comparable_pool(bigint,integer,numeric,integer)'::regprocedure),
          true, 'comparable_pool is security definer');
select is(array(select p.oid::regprocedure::text from pg_proc p
                 where p.oid in ('public.listing_unconfirmed(text,text,text,integer,integer,timestamptz,jsonb,interval)'::regprocedure,
                                 'public.comparable_listings(bigint,integer,numeric,integer)'::regprocedure)
                   and (p.prosecdef or p.proconfig is not null or p.proisstrict or p.provolatile <> 's')),
          '{}'::text[], 'listing_unconfirmed and comparable_listings stay inlinable: stable, no SET, not definer or strict');

-- ---------------------------------------------------------------- the pool, as the web reads it
insert into public.listings (id, source, external_id, url, title, make, model, year, price, currency, price_usd,
                             mileage_km, transmission, last_seen_at) overriding system value values
  (9901, 'mercadolibre',  'pgtap-cmp-1', 'https://example.test/c1', 'Pgtap Comparable', 'Pgtap', 'Comparable', 2017,
   10000, 'USD', 10000, 100000, 'manual', now()),
  (9902, 'rosariogarage', 'pgtap-cmp-2', 'https://example.test/c2', 'Pgtap Comparable', 'Pgtap', 'Comparable', 2017,
   11000, 'USD', 11000, 100000, 'manual', now()),
  (9903, 'rosariogarage', 'pgtap-cmp-3', 'https://example.test/c3', 'Pgtap Comparable', 'Pgtap', 'Comparable', 2017,
   12000, 'USD', 12000, 100000, 'manual', now() - interval '3 days'),
  (9904, 'mercadolibre',  'pgtap-cmp-4', 'https://example.test/c4', 'Pgtap Comparable', 'Pgtap', 'Comparable', 2017,
   13000, 'USD', 13000, 100000, 'manual', now() - interval '20 days');
update public.listings set status = 'gone' where id = 9904;
-- A complete read of the model an hour ago: 9903 (seen 3 days ago) wasn't in it.
-- Since fase 2 the evidence is last_full_read_at, which finish_target moves with
-- last_run_at on the sources without publication dates.
insert into public.crawl_targets (source, make, model, query, last_run_at, last_full_read_at, first_run_done)
values ('rosariogarage', 'Pgtap', 'Comparable', '{"year_min": 2015}', now() - interval '1 hour',
        now() - interval '1 hour', true);

set local role authenticated;
set local request.jwt.claims = '{"sub": "c1000000-0000-0000-0000-000000000001", "role": "authenticated"}';
select is(array(select id from public.comparable_pool(9901) order by id), '{9902, 9904}'::bigint[],
          'authenticated: the pool leaves out what a later complete read no longer saw, and keeps the gone one');
select is((select count(*) from public.comparable_pool(9901, p_max_age_days => 10))::int, 1,
          '... the window still applies');
select throws_ok($$select public.comparables(9901)$$, '42501', null, '... comparables() stays the worker''s');
select throws_ok($$select * from public.comparable_listings(9901)$$, '42501', null, '... and so does the internal pool');
reset role;

set local role anon;
select throws_ok($$select * from public.comparable_pool(9901)$$, '42501', null, 'anon cannot read the pool');
reset role;

set local role service_role;
select is((public.comparables(9901, 1000)->>'n')::int, 2, 'comparables() counts the same pool (n=2)');
select is((public.comparables(9901, 1000)->>'median')::numeric, 12000.00, '... median of 11.000 and 13.000');
reset role;

select * from finish();
rollback;

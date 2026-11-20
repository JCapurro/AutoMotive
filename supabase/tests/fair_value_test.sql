-- Valor justo in shadow (migration 20270107120000_fair_value_shadow): the two tables' access, price_pool()
-- and its equivalence with comparable_listings(), and app_config.fair_value. Run with: supabase test db
-- All fixtures roll back.
begin;
create extension if not exists pgtap with schema extensions;
select no_plan();

-- ---------------------------------------------------------------- schema and access
select has_table('public', 'model_price_curves', 'model_price_curves exists');
select has_table('public', 'fair_value_runs', 'fair_value_runs exists');
select col_is_pk('public', 'model_price_curves', array['make', 'model'], 'one curve per (make, model)');
select has_index('public', 'fair_value_runs', 'fair_value_runs_started_idx', 'runs by start');

select ok((select bool_and(relrowsecurity) from pg_class
            where oid in ('public.model_price_curves'::regclass, 'public.fair_value_runs'::regclass)),
          'RLS is on on both');
select is((select count(*)::int from pg_policies where schemaname = 'public'
            and tablename in ('model_price_curves', 'fair_value_runs')),
          0, 'no policy: only the worker reads them');
select is(array(select r || ' ' || t || ' ' || p
                  from unnest(array['anon', 'authenticated']) r,
                       unnest(array['public.model_price_curves', 'public.fair_value_runs']) t,
                       unnest(array['select', 'insert', 'update', 'delete']) p
                 where has_table_privilege(r, t, p)),
          '{}'::text[], 'anon and authenticated can neither read nor write them');
select ok(has_table_privilege('service_role', 'public.model_price_curves', 'select')
          and has_table_privilege('service_role', 'public.model_price_curves', 'insert')
          and has_table_privilege('service_role', 'public.fair_value_runs', 'update'),
          'the service role reads and writes them');

select throws_ok($$insert into public.model_price_curves (make, model, curve, n, params_hash)
                   values ('Toyota', 'hilux', '{}', 1, 'x')$$, '23514', null, 'make and model are stored in lower case');
select throws_ok($$insert into public.fair_value_runs (trigger) values ('manual')$$, '23514', null,
                 'an unknown trigger is refused');
select lives_ok($$insert into public.fair_value_runs (trigger) values ('cli')$$, 'a run inserts with defaults');
select is((select status from public.fair_value_runs order by id desc limit 1), 'running', 'a run starts as running');

-- ---------------------------------------------------------------- price_pool grants
select ok(not has_function_privilege('anon', 'public.price_pool(text,text)', 'execute'), 'anon cannot execute price_pool');
select ok(not has_function_privilege('authenticated', 'public.price_pool(text,text)', 'execute'),
          'authenticated cannot execute price_pool');
select ok(has_function_privilege('service_role', 'public.price_pool(text,text)', 'execute'),
          'the service role (the worker) executes price_pool');
select is((select provolatile::text from pg_proc where oid = 'public.price_pool(text,text)'::regprocedure), 's',
          'price_pool is stable');

-- ---------------------------------------------------------------- price_pool = comparable_listings without the target's rules
insert into public.listings (id, source, external_id, url, title, make, model, year, price, currency, price_usd,
                             mileage_km, transmission, trim, price_partial, last_seen_at) overriding system value values
  -- targets: with year and km, without year, without km
  (98801, 'rosariogarage', 'pgtap-fv-1',  'https://example.test/fv1',  'Pgtap Pool', 'Pgtap', 'Pool', 2017, 10000, 'USD', 10000, 100000, 'manual', 'Base', false, now()),
  (98802, 'rosariogarage', 'pgtap-fv-2',  'https://example.test/fv2',  'Pgtap Pool', 'Pgtap', 'Pool', null, 10000, 'USD', 10000, 100000, 'manual', 'Base', false, now()),
  (98803, 'rosariogarage', 'pgtap-fv-3',  'https://example.test/fv3',  'Pgtap Pool', 'PGTAP', 'pool', 2017, 10000, 'USD', 10000, null,   'manual', null,   false, now()),
  -- the pool: in, out of the year window, out of the km window, without km, without year
  (98804, 'rosariogarage', 'pgtap-fv-4',  'https://example.test/fv4',  'Pgtap Pool', 'Pgtap', 'Pool', 2016, 11000, 'USD', 11000, 110000, 'automatic', 'Full', false, now()),
  (98805, 'rosariogarage', 'pgtap-fv-5',  'https://example.test/fv5',  'Pgtap Pool', 'Pgtap', 'Pool', 2014, 9000,  'USD', 9000,  120000, 'manual', null,   false, now()),
  (98806, 'rosariogarage', 'pgtap-fv-6',  'https://example.test/fv6',  'Pgtap Pool', 'Pgtap', 'Pool', 2018, 12000, 'USD', 12000, 200000, 'manual', null,   false, now()),
  (98807, 'rosariogarage', 'pgtap-fv-7',  'https://example.test/fv7',  'Pgtap Pool', 'Pgtap', 'Pool', 2017, 10500, 'USD', 10500, null,   'manual', null,   false, now()),
  (98808, 'rosariogarage', 'pgtap-fv-8',  'https://example.test/fv8',  'Pgtap Pool', 'Pgtap', 'Pool', null,  10200, 'USD', 10200, 90000,  'manual', null,   false, now()),
  -- never in it: an agency's own price, a partial price, no price, seen too long ago, another model
  (98809, 'directo',       'pgtap-fv-9',  'https://example.test/fv9',  'Pgtap Pool', 'Pgtap', 'Pool', 2017, 10000, 'USD', 10000, 100000, 'manual', null,   false, now()),
  (98810, 'rosariogarage', 'pgtap-fv-10', 'https://example.test/fv10', 'Pgtap Pool', 'Pgtap', 'Pool', 2017, 3000,  'USD', 3000,  100000, 'manual', null,   true,  now()),
  (98811, 'rosariogarage', 'pgtap-fv-11', 'https://example.test/fv11', 'Pgtap Pool', 'Pgtap', 'Pool', 2017, 0,     'USD', 0,     100000, 'manual', null,   false, now()),
  (98812, 'rosariogarage', 'pgtap-fv-12', 'https://example.test/fv12', 'Pgtap Pool', 'Pgtap', 'Pool', 2017, 10000, 'USD', 10000, 100000, 'manual', null,   false, now() - interval '400 days'),
  (98813, 'rosariogarage', 'pgtap-fv-13', 'https://example.test/fv13', 'Pgtap Pool', 'Pgtap', 'Other', 2017, 10000, 'USD', 10000, 100000, 'manual', null,  false, now()),
  -- reposts: of the first target, of a counting original (out), of an original that no longer counts (in)
  (98814, 'rosariogarage', 'pgtap-fv-14', 'https://example.test/fv14', 'Pgtap Pool', 'Pgtap', 'Pool', 2017, 10100, 'USD', 10100, 100000, 'manual', null,   false, now()),
  (98815, 'rosariogarage', 'pgtap-fv-15', 'https://example.test/fv15', 'Pgtap Pool', 'Pgtap', 'Pool', 2017, 11100, 'USD', 11100, 110000, 'automatic', 'Full', false, now()),
  (98816, 'rosariogarage', 'pgtap-fv-16', 'https://example.test/fv16', 'Pgtap Pool', 'Pgtap', 'Pool', 2017, 10300, 'USD', 10300, 95000,  'manual', null,   false, now());
update public.listings set probable_repost_of = 98801 where id = 98814;
update public.listings set probable_repost_of = 98804 where id = 98815;
update public.listings set probable_repost_of = 98812 where id = 98816;

select is(array(select p.id from public.price_pool('Pgtap', 'Pool') p order by 1),
          array[98801, 98802, 98803, 98804, 98805, 98806, 98807, 98808, 98816]::bigint[],
          'price_pool: the model''s countable listings, case-insensitive, without directo, partial, priceless, '
          'stale, other models or a repost of a counting original (98814, 98815)');

-- The four rules of the target, read from the same config comparable_listings reads.
create temp table fv_cfg as
  select coalesce((value->>'year_tol')::integer, 1) as year_tol, coalesce((value->>'km_tol_pct')::numeric, 25) as km_tol_pct
    from (select 1) one left join public.app_config on key = 'comparables';

select is(array(select p.id from public.listings t cross join fv_cfg cfg
                  cross join public.price_pool(t.make, t.model) p
                 where t.id = tid and p.id <> t.id and p.probable_repost_of is distinct from t.id
                   and (t.year is null or p.year between t.year - cfg.year_tol and t.year + cfg.year_tol)
                   and (t.mileage_km is null or p.mileage_km is null
                        or p.mileage_km between t.mileage_km * (1 - cfg.km_tol_pct / 100)
                                            and t.mileage_km * (1 + cfg.km_tol_pct / 100))
                 order by 1),
          array(select o.id from public.comparable_listings(tid) o order by 1),
          'price_pool with the target''s four rules = comparable_listings for ' || label)
  from (values (98801::bigint, 'a listing with year and km'), (98802, 'a listing without year'),
               (98803, 'a listing without km'), (98816, 'a repost')) as v (tid, label);

-- ---------------------------------------------------------------- app_config.fair_value, as the migration left it
select is((select value->>'mode' from public.app_config where key = 'fair_value'), 'shadow', 'fair_value runs in shadow');
select is((select (value->>'min_listings')::int from public.app_config where key = 'fair_value'), 150,
          'min_listings 150');
select is((select value->'schedule'->>'hour' from public.app_config where key = 'fair_value'), '03:30',
          'fits at 03:30, before the 04:00 re-score');

select * from finish();
rollback;

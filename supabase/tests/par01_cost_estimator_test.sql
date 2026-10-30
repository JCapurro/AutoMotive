-- PAR-01: app_config.cost_estimator and plan_limits.{pass,free}.total_cost
-- (migration 20261126120000_par01_cost_estimator). The re-run below repeats
-- the migration's statements to check they are idempotent.
begin;
select no_plan();

select is((select value->>'as_of' from public.app_config where key = 'cost_estimator'), '2026-10-30',
          'cost_estimator exists, reviewed on 2026-10-30');
select is((select value->>'status' from public.app_config where key = 'cost_estimator'), 'aprobado',
          '... with status aprobado');

-- Every block of the design has a source and an as_of date.
select is((select array_agg(path order by path) from (
             select path from unnest(array['review', 'fx', 'buyer_zone', 'vf_from_price_k', 'transfer_base', 'mrpa_ars',
                                           'dnrpa', 'fixed_ars,form_08', 'fixed_ars,form_12', 'domain_report',
                                           'stamp_tax_pct,caba', 'stamp_tax_pct,ba', 'stamp_tax_pct,rest',
                                           'patente,caba', 'patente,ba', 'patente,rest', 'gestoria']) as path,
                  public.app_config c
            where c.key = 'cost_estimator'
              and (coalesce(btrim(c.value #>> (string_to_array(path, ',') || '{source}'::text[])), '') = ''
                   or coalesce(c.value #>> (string_to_array(path, ',') || '{as_of}'::text[]), '') !~ '^\d{4}-\d{2}-\d{2}$')) bad),
          null, 'every block has a non-empty source and an as_of date');

select is((select (value #>> '{dnrpa,min_mrpa}')::int from public.app_config where key = 'cost_estimator'), 32,
          'dnrpa.min_mrpa = 32');
select is((select (value #>> '{patente,caba,brackets,2,fixed}')::int from public.app_config where key = 'cost_estimator'),
          507150, 'patente.caba.brackets[2].fixed = 507150');
select is((select (value #>> '{patente,ba,ipc_factor,max}')::numeric from public.app_config where key = 'cost_estimator'),
          1.25, 'patente.ba.ipc_factor.max = 1.25');
select is((select (value #>> '{stamp_tax_pct,rest,private,max}')::numeric from public.app_config where key = 'cost_estimator'),
          3.0, 'stamp_tax_pct.rest.private.max = 3.0');
select is((select value #> '{domain_report,in_total}' from public.app_config where key = 'cost_estimator'),
          'false'::jsonb, 'domain_report.in_total = false');
select is((select value #> '{gestoria,official_value}' from public.app_config where key = 'cost_estimator'),
          'null'::jsonb, 'gestoria.official_value is null');
select is((select (value #>> '{patente,values_year}')::int from public.app_config where key = 'cost_estimator'),
          2026, 'patente.values_year = 2026');
-- Juan's answers 5 and 6 to the second review.
select is((select (value #>> '{fx,max_age_days}')::int from public.app_config where key = 'cost_estimator'), 3,
          'fx.max_age_days = 3');
select is((select (value #>> '{buyer_zone,max_locality_km}')::int from public.app_config where key = 'cost_estimator'), 80,
          'buyer_zone.max_locality_km = 80');

select is((select value #> '{pass,total_cost}' from public.app_config where key = 'plan_limits'), 'true'::jsonb,
          'plan_limits: Particular has the total cost');
select is((select value #> '{free,total_cost}' from public.app_config where key = 'plan_limits'), 'true'::jsonb,
          '... and the free plan, during the pilot');
select is((select value #> '{pro,total_cost}' from public.app_config where key = 'plan_limits'), null,
          '... not Pro (PRO-02 shows its transfer costs)');
select is((select value #- '{pass,total_cost}' #- '{free,total_cost}' from public.app_config where key = 'plan_limits')
            ->'pass'->'max_profiles', '3'::jsonb, 'the rest of plan_limits is untouched');

-- plan_feature: pass and free yes, Pro no, an admin always.
insert into auth.users (instance_id, id, aud, role, email, created_at, updated_at) values
  ('00000000-0000-0000-0000-000000000000', 'c0100000-0000-0000-0000-000000000001', 'authenticated', 'authenticated', 'free@par01.test', now(), now()),
  ('00000000-0000-0000-0000-000000000000', 'c0100000-0000-0000-0000-000000000002', 'authenticated', 'authenticated', 'pass@par01.test', now(), now()),
  ('00000000-0000-0000-0000-000000000000', 'c0100000-0000-0000-0000-000000000003', 'authenticated', 'authenticated', 'pro@par01.test', now(), now()),
  ('00000000-0000-0000-0000-000000000000', 'c0100000-0000-0000-0000-000000000004', 'authenticated', 'authenticated', 'admin@par01.test', now(), now());
update public.profiles p set plan = v.plan::public.user_plan, plan_expires_at = v.expires, role = v.role::public.user_role
  from (values
    ('c0100000-0000-0000-0000-000000000001'::uuid, 'free', null::timestamptz, 'user'),
    ('c0100000-0000-0000-0000-000000000002'::uuid, 'pass', now() + interval '20 days', 'user'),
    ('c0100000-0000-0000-0000-000000000003'::uuid, 'pro',  now() + interval '20 days', 'user'),
    ('c0100000-0000-0000-0000-000000000004'::uuid, 'pro',  null, 'admin')
  ) as v (id, plan, expires, role)
 where p.id = v.id;
-- The admin row is a Pro row without the key: the admin gets it anyway.
select is(array[public.plan_feature('c0100000-0000-0000-0000-000000000001', 'total_cost'),
                public.plan_feature('c0100000-0000-0000-0000-000000000002', 'total_cost'),
                public.plan_feature('c0100000-0000-0000-0000-000000000003', 'total_cost'),
                public.plan_feature('c0100000-0000-0000-0000-000000000004', 'total_cost')],
          array[true, true, false, true], 'plan_feature total_cost: free and pass yes, Pro no, admin yes');

-- Values edited from /admin/config survive a re-run.
update public.app_config set value = jsonb_set(value, '{dnrpa,min_mrpa}', '40') where key = 'cost_estimator';
update public.app_config set value = jsonb_set(value, '{free,total_cost}', 'false') where key = 'plan_limits';

insert into public.app_config(key, value) values ('cost_estimator', '{"as_of": "2026-10-30"}')
on conflict (key) do nothing;
update public.app_config
   set value = jsonb_set(value, '{pass,total_cost}', 'true')
 where key = 'plan_limits'
   and jsonb_typeof(value->'pass') = 'object'
   and not (value->'pass' ? 'total_cost');
update public.app_config
   set value = jsonb_set(value, '{free,total_cost}', 'true')
 where key = 'plan_limits'
   and jsonb_typeof(value->'free') = 'object'
   and not (value->'free' ? 'total_cost');

select is((select (value #>> '{dnrpa,min_mrpa}')::int from public.app_config where key = 'cost_estimator'), 40,
          'a re-run keeps an edited cost_estimator');
select is((select count(*)::int from public.app_config where key = 'cost_estimator'), 1, 'a re-run adds no row');
select is((select value #> '{free,total_cost}' from public.app_config where key = 'plan_limits'), 'false'::jsonb,
          'a re-run keeps total_cost turned off');
select is(public.plan_feature('c0100000-0000-0000-0000-000000000001', 'total_cost'), false,
          '... and the free plan loses it without a deploy');

-- Only the service role reads app_config (no anon/authenticated policy).
set local role authenticated;
select throws_ok($$select value from public.app_config where key = 'cost_estimator'$$, '42501', null,
                 'users cannot read cost_estimator');
reset role;
set local role anon;
select throws_ok($$select value from public.app_config where key = 'cost_estimator'$$, '42501', null,
                 'anon cannot read cost_estimator');
reset role;

select * from finish();
rollback;

-- Oportunidad creible (migration 20270113120100_opportunity_gate.sql). Run with: supabase test db
-- app_config.opportunity_gate exists, off, with the 15 % and 10 comparables of Juan's decision.
begin;
create extension if not exists pgtap with schema extensions;
select no_plan();

select is((select value from public.app_config where key = 'opportunity_gate'),
          '{"enabled": false, "min_pct": 15, "min_n": 10}'::jsonb,
          'opportunity_gate: off, 15 % and 10 comparables');
select is((select jsonb_typeof(value -> 'enabled') from public.app_config where key = 'opportunity_gate'), 'boolean',
          'opportunity_gate.enabled is a real boolean');

select * from finish();
rollback;

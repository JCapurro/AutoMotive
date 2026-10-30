-- PAR-02 tramo 1: app_config.red_flags.much_cheaper_verify_pct and app_config.risk
-- (migration 20261122120000_par02_risk_config). The re-run below repeats the
-- migration's two statements to check they are idempotent.
begin;
select no_plan();

select is((select (value->>'much_cheaper_verify_pct')::int from public.app_config where key = 'red_flags'),
          35, 'red_flags has much_cheaper_verify_pct = 35');
select is((select value - 'much_cheaper_verify_pct' from public.app_config where key = 'red_flags'),
          '{"much_cheaper_pct": 25, "anticipo_pct": 50, "min_km_per_year": 5000, "min_description_chars": 150}'::jsonb,
          'the other red_flags keys did not change');
select is((select value from public.app_config where key = 'risk'),
          '{"checklist_enabled": true, "links": {"dnrpa": null, "patentes": [], "infracciones": [], "vtv": null, "form_08": null}}'::jsonb,
          'risk exists, enabled, with every link empty');

-- Values tuned from /admin/config survive a re-run.
update public.app_config set value = jsonb_set(value, '{much_cheaper_verify_pct}', '40') where key = 'red_flags';
update public.app_config set value = '{"checklist_enabled": false, "links": {"dnrpa": {"label": "x", "url": "https://example.test/x"}}}'
 where key = 'risk';

update public.app_config
   set value = value || '{"much_cheaper_verify_pct": 35}'::jsonb
 where key = 'red_flags'
   and jsonb_typeof(value) = 'object'
   and not (value ? 'much_cheaper_verify_pct');
insert into public.app_config(key, value) values
  ('risk', '{"checklist_enabled": true, "links": {"dnrpa": null, "patentes": [], "infracciones": [], "vtv": null, "form_08": null}}')
on conflict (key) do nothing;

select is((select (value->>'much_cheaper_verify_pct')::int from public.app_config where key = 'red_flags'),
          40, 'a re-run keeps a tuned much_cheaper_verify_pct');
select is((select value->>'checklist_enabled' from public.app_config where key = 'risk'),
          'false', 'a re-run keeps an edited risk row');
select is((select count(*)::int from public.app_config where key = 'risk'), 1, 'a re-run adds no row');

-- Only the service role reads app_config (no anon/authenticated policy).
set local role authenticated;
select throws_ok($$select value from public.app_config where key = 'risk'$$, '42501', null, 'users cannot read risk');
reset role;

select * from finish();
rollback;

-- Planes 2026-10: Juan removed Pro's CSV export (3.3) on 15/10/2026
-- (docs/PLANES_2026-10.md). Drop what only it used and its plan feature;
-- the threshold (3.2), plan_feature and my_plan_feature stay.

drop function public.export_search_results(bigint);
drop function public.comparables_min_n();

-- csv_export out of every plan, in case an admin gave it to another one.
update public.app_config c
   set value = (select jsonb_object_agg(k, case when jsonb_typeof(v) = 'object' then v - 'csv_export' else v end)
                  from jsonb_each(c.value) as e (k, v))
 where c.key = 'plan_limits'
   and exists (select 1 from jsonb_each(c.value) as e (k, v)
                where jsonb_typeof(v) = 'object' and v ? 'csv_export');

notify pgrst, 'reload schema';

-- Radar semanal (Prueba A, Validación comercial Fase 4). Solo lectura.
-- Parámetros: reemplazar :week ('2026-10-26') y :zone ('amba' | 'cordoba' | 'litoral').
-- Ranking: autos que más dejaron de publicarse en la semana (gone_count, solo fuentes
-- confirmadas), con al menos 3 casos de días; si no llegan a 10, se completa con los más
-- publicados (sin dato de días). Nunca se habla de «vendidos»: es «dejó de publicarse».
with cfg as (select :week::date wk, :zone::text zn),
ms as (
  select m.*, (m.days_n >= 3) has_days
    from market_stats m, cfg
   where m.week_start = cfg.wk and m.zone = cfg.zn and m.group_kind = 'model'
     and m.year_from < extract(year from cfg.wk)::int and m.price_n >= 8),
ranked as (
  select *, row_number() over (order by has_days desc,
                                        case when has_days then gone_count end desc nulls last,
                                        active_count desc) rk
    from ms),
lz as (
  select listing_id, department,
         case when province_id = '02' then 'amba'
              when province_id = '06' and department in (
                select jsonb_array_elements_text(r -> 'departments')
                  from app_config c, jsonb_array_elements(c.value -> 'rules') r
                 where c.key = 'market_zones' and r ->> 'region' = 'amba' and r ? 'departments') then 'amba'
              when province_id = '14' then 'cordoba'
              when province_id in ('82', '30') then 'litoral' end zone
    from listing_zones where precision = 'locality'),
dep as (
  select lower(l.make) make, lower(l.model) model, l.year - l.year % 2 yf, lz.department,
         count(*) n, percentile_cont(0.5) within group (order by l.price_usd) med
    from listings l join lz on lz.listing_id = l.id, cfg
   where l.status = 'active' and lz.zone = cfg.zn and l.price_usd is not null
     and not coalesce(l.price_partial, false)
   group by 1, 2, 3, 4 having count(*) >= 3),
best as (select distinct on (make, model, yf) * from dep order by make, model, yf, med)
select json_agg(json_build_object(
         'rk', r.rk, 'make', r.make, 'model', r.model, 'year_from', r.year_from,
         'active', r.active_count, 'new', r.new_count, 'gone', r.gone_count,
         'has_days', r.has_days, 'median_days', round(r.median_days_to_gone, 1),
         'median_usd', round(r.median_price_usd), 'p25_usd', round(r.p25_price_usd),
         'cheapest_dept', b.department, 'cheapest_dept_n', b.n, 'cheapest_dept_med', round(b.med::numeric))
       order by r.rk) rows
  from ranked r left join best b on b.make = r.make and b.model = r.model and b.yf = r.year_from
 where r.rk <= 10;

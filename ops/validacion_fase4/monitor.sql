-- Monitor de stock (Prueba A, Validación comercial Fase 4). Solo lectura.
-- Pegar el stock de UNA agencia en «stock» (desde la hoja «Mi stock» de su planilla).
-- Comparables = misma marca y modelo, año ±1, km ±25 %, activos, vistos en los últimos
-- 30 días, sin anticipos ni cuotas, en la misma zona (amba | cordoba | litoral | todas).
-- Las mismas tolerancias que app_config.comparables usa por defecto.
with stock(fila, make, model, year, km, price_usd, zone) as (values
  (1, 'renault', 'sandero', 2017, 85000, 9900::numeric, 'amba')
  -- , (2, 'toyota', 'corolla', 2019, 70000, 18500, 'amba')
),
lz as (
  select listing_id,
         case when province_id = '02' then 'amba'
              when province_id = '06' and department in (
                select jsonb_array_elements_text(r -> 'departments')
                  from app_config c, jsonb_array_elements(c.value -> 'rules') r
                 where c.key = 'market_zones' and r ->> 'region' = 'amba' and r ? 'departments') then 'amba'
              when province_id = '14' then 'cordoba'
              when province_id in ('82', '30') then 'litoral' end zone
    from listing_zones),
comp as (
  select s.fila, l.id, l.price_usd, l.first_seen_at, l.url, l.year, l.mileage_km, l.source
    from stock s
    join listings l on lower(l.make) = s.make and lower(l.model) = s.model
                   and l.year between s.year - 1 and s.year + 1
                   and (l.mileage_km is null or s.km is null
                        or l.mileage_km between s.km * 0.75 and s.km * 1.25)
    left join lz on lz.listing_id = l.id
   where l.status = 'active' and l.last_seen_at > now() - interval '30 days'
     and l.price_usd is not null and not coalesce(l.price_partial, false)
     and (s.zone = 'todas' or lz.zone = s.zone)),
agg as (
  select fila, count(*) n,
         round((percentile_cont(0.5) within group (order by price_usd))::numeric) mediana,
         round((percentile_cont(0.25) within group (order by price_usd))::numeric) p25,
         round(min(price_usd)) minimo
    from comp group by fila),
nuevo as (  -- el más barato aparecido en los últimos 4 días por debajo de su precio
  select distinct on (c.fila) c.fila, round(c.price_usd) precio, c.year, c.mileage_km, c.url, c.source
    from comp c join stock s using (fila)
   where c.first_seen_at > now() - interval '4 days' and c.price_usd < s.price_usd
   order by c.fila, c.price_usd)
select s.fila, s.make, s.model, s.year, s.km, s.price_usd precio_agencia,
       a.n comparables, a.mediana, a.p25, a.minimo,
       case when a.n >= 5 then round(100.0 * (s.price_usd - a.mediana) / a.mediana, 1) end dif_vs_mediana_pct,
       case when a.n is null or a.n < 5 then 'pocos comparables'
            when s.price_usd > a.mediana * 1.05 then 'por encima de la mediana'
            when s.price_usd < a.p25 then 'entre el 25 % más barato'
            else 'en línea con la mediana' end lectura,
       nv.precio nuevo_mas_barato, nv.year nuevo_anio, nv.mileage_km nuevo_km, nv.source nuevo_portal, nv.url nuevo_link
  from stock s left join agg a using (fila) left join nuevo nv using (fila)
 order by s.fila;

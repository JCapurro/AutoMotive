-- Anexo de 2026-11-20-valor-justo-design.md: las consultas con las que se midió (solo lectura).
--
-- Correr de a un modelo: varias a la vez pasan el límite de tiempo del MCP de Supabase.
-- En (A) cambiar la marca y el modelo de la CTE `b`.
--
-- Dos diferencias con lo que pide el diseño, que no cambian las conclusiones:
--   * acá la versión es lower(btrim(trim)); el diseño usa lower(trim), la clave de los gemelos de hoy;
--   * acá el pool son los avisos con precio vistos en 30 días; el diseño usa price_pool() (§4.1), que
--     además saca los 'directo', los no confirmados y los reposts.

-- ---------------------------------------------------------------------------
-- (A) Valor justo contra la referencia actual, con autos que el ajuste no vio
-- ---------------------------------------------------------------------------
-- Entrena con 4 de cada 5 avisos del modelo (id % 5 <> 0) y predice el quinto. La referencia actual
-- es public.comparables() llamada sobre esos mismos avisos (ya excluye al propio aviso).
-- err_* = error absoluto mediano en %, |ln(precio / referencia)|.
with b as materialized (
  select id, year, nullif(btrim(lower(trim)), '') trim, lower(transmission) tr, price_usd p, mileage_km km,
         ln(price_usd) lp, (id % 5 = 0) is_test
    from listings
   where lower(make) = 'toyota' and lower(model) = 'hilux' and year between 2005 and 2026
     and price_usd > 0 and not price_partial and last_seen_at >= now() - interval '30 days'
),
-- 1. nivel del año
y1 as materialized (select year, percentile_cont(0.5) within group (order by lp) a
                      from b where not is_test group by 1 having count(*) >= 6),
-- 2. recorte de precios absurdos (entre 0,45 y 2,2 veces la mediana del año)
r1 as materialized (select b.*, b.lp - y1.a r from b join y1 using (year)
                     where not b.is_test and b.p between 0.45 * exp(y1.a) and 2.2 * exp(y1.a)),
-- 3. prima de cada versión
t1 as materialized (select trim, percentile_cont(0.5) within group (order by r) g
                      from r1 where trim is not null group by 1 having count(*) >= 15),
r1b as materialized (select r1.*, coalesce(t1.g, 0) g from r1 left join t1 using (trim)),
-- 4. nivel del año otra vez, ya sin el efecto de la versión
y2 as materialized (select year, percentile_cont(0.5) within group (order by lp - g) a2 from r1b group by 1),
r2 as materialized (select r1b.*, r1b.lp - r1b.g - y2.a2 r2 from r1b join y2 using (year)),
-- 5. prima de la caja
x1 as materialized (select tr, percentile_cont(0.5) within group (order by r2) h
                      from r2 where tr is not null group by 1 having count(*) >= 15),
r3 as materialized (select r2.*, r2.r2 - coalesce(x1.h, 0) r3 from r2 left join x1 using (tr)),
-- 6. km: pendiente del residuo contra el km relativo al típico de su año
kmc as materialized (select year, avg(ln(km)) mk from r3 where km between 5000 and 400000 group by 1),
ks as materialized (select least(0, greatest(-0.35, regr_slope(r3.r3, ln(r3.km) - kmc.mk))) bk
                      from r3 join kmc using (year) where r3.km between 5000 and 400000),
tst as materialized (
  select b.id, b.p,
         b.lp - (y2.a2 + coalesce(t1.g, 0) + coalesce(x1.h, 0)
                 + case when b.km between 5000 and 400000 and kmc.mk is not null
                        then ks.bk * (ln(b.km) - kmc.mk) else 0 end) eh
    from b join y1 using (year) join y2 using (year)
    left join t1 using (trim) left join x1 using (tr) left join kmc using (year) cross join ks
   where b.is_test and b.p between 0.45 * exp(y1.a) and 2.2 * exp(y1.a)
   order by b.id limit 180
),
c as materialized (select tst.*, public.comparables(tst.id) ref from tst),
j as (select eh, ref->>'level_used' lu, (ref->>'n')::int n,
             case when (ref->>'median')::numeric > 0 then ln(p / (ref->>'median')::numeric) end ec
        from c)
select coalesce(lu, 'TODOS') nivel_de_la_referencia_actual, count(*) n,
       round((100 * percentile_cont(0.5) within group (order by abs(ec)))::numeric, 1) err_actual,
       round((100 * percentile_cont(0.5) within group (order by abs(eh)))::numeric, 1) err_valor_justo,
       round(100.0 * count(*) filter (where abs(ec) > 0.2) / count(*), 1) pct_err20_actual,
       round(100.0 * count(*) filter (where abs(eh) > 0.2) / count(*), 1) pct_err20_valor_justo,
       count(*) filter (where ec <= ln(0.9)) baratos_actual,
       count(*) filter (where eh <= ln(0.9)) baratos_valor_justo,
       count(*) filter (where ec <= ln(0.9) and eh > ln(0.95)) baratos_actual_que_se_caen,
       count(*) filter (where eh <= ln(0.9) and ec > ln(0.95)) baratos_nuevos
  from j where n >= 5 and ec is not null group by rollup (lu) order by 1;

-- ---------------------------------------------------------------------------
-- (B) Lo que abre la gente, comparado dentro de la misma búsqueda y la misma banda de score
-- ---------------------------------------------------------------------------
-- «esperados» = aperturas que tendría el tramo si dentro de cada búsqueda y banda de score se abriera
-- todo por igual. veces_lo_esperado = 1: sin preferencia. Sumar tramos entre búsquedas sin este control
-- engaña: las listas largas tienen tasas por auto más bajas (cada persona abre uno o dos autos).
with s as materialized (
  select sp.id, sp.user_id,
         case when coalesce(upper(sp.filters->>'currency'),
                            case when (sp.filters->>'price_max')::numeric >= 1000000 then 'ARS' else 'USD' end) = 'ARS'
              then (sp.filters->>'price_max')::numeric / 1630.0     -- blue del 20/11/2026
              else (sp.filters->>'price_max')::numeric end as b_usd
    from search_profiles sp where (sp.filters->>'price_max') is not null
), ev as materialized (
  select user_id, (props->>'listing_id')::bigint listing_id
    from events
   where name in ('listing_detail_viewed', 'listing_outbound_clicked', 'alert_clicked')
     and props->>'listing_id' ~ '^[0-9]+$'
   group by 1, 2
), m as materialized (
  select s.id sid,
         case when mt.score < 60 then 'a' when mt.score < 70 then 'b' when mt.score < 80 then 'c' else 'd' end band,
         (ev.listing_id is not null) opened,
         case when (mt.price_ref->>'n')::int >= 5 and (mt.price_ref->>'median') is not null then
           case when (mt.price_ref->>'median')::numeric / s.b_usd < 0.6  then '1_vale_menos_60'
                when (mt.price_ref->>'median')::numeric / s.b_usd < 0.8  then '2_60_a_80'
                when (mt.price_ref->>'median')::numeric / s.b_usd < 0.95 then '3_80_a_95'
                when (mt.price_ref->>'median')::numeric / s.b_usd < 1.1  then '4_95_a_110'
                else '5_mas_110' end
         else '0_sin_referencia' end tramo
    from s join matches mt on mt.search_profile_id = s.id join listings l on l.id = mt.listing_id
    left join ev on ev.user_id = s.user_id and ev.listing_id = l.id
   where l.price_usd > 0 and s.b_usd > 0 and l.price_usd <= 1.02 * s.b_usd
), st as (select sid, band, count(*) n, count(*) filter (where opened) no from m group by 1, 2),
bk as (select sid, band, tramo, count(*) nb, count(*) filter (where opened) ob from m group by 1, 2, 3)
select bk.tramo valor_del_auto_contra_el_tope, sum(bk.ob) abiertos,
       round(sum(st.no * bk.nb::numeric / st.n), 1) esperados,
       round(sum(bk.ob) / nullif(sum(st.no * bk.nb::numeric / st.n), 0), 2) veces_lo_esperado
  from bk join st using (sid, band) where st.no > 0 group by 1 order by 1;

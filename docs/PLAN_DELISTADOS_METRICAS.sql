-- Métricas M1–M5 de docs/PLAN_DELISTADOS.md §4. Solo lectura: correr antes del deploy y una semana después.
--
-- `alive` es la última señal de vida. Con la migración 20270116120000 es listings.alive_checked_at; antes de
-- aplicarla, reemplazar `coalesce(l.alive_checked_at, l.last_seen_at)` por `l.last_seen_at` en todo el archivo.
-- Ventana por defecto: 14 días para M1 y M2, 7 para M4 y M5.

-- M1. Envíos con auto muerto: alertas y ítems de resumen enviados cuyo auto hoy está gone y no tuvo
-- ninguna señal de vida después del envío. Hoy (2026-11-25): 0,3 % (4/1.315). Objetivo: < 0,1 %.
with sent as (
  select n.id, n.kind::text as kind, n.listing_id, n.sent_at
    from notifications n
   where n.status = 'sent' and n.kind in ('new_match', 'opportunity', 'price_drop')
     and n.sent_at >= now() - interval '14 days'
  union all
  select n.id, 'digest_item', (it->>'listing_id')::bigint, n.sent_at
    from notifications n cross join lateral jsonb_array_elements(coalesce(n.payload->'items', '[]')) it
   where n.status = 'sent' and n.kind = 'digest' and n.sent_at >= now() - interval '14 days'
     and coalesce(it->>'section', '') <> 'gone'
)
select s.kind, count(*) as enviadas,
       count(*) filter (where l.status = 'gone'
                          and coalesce(l.alive_checked_at, l.last_seen_at) < s.sent_at) as muertas_al_enviar,
       round(100.0 * count(*) filter (where l.status = 'gone'
                          and coalesce(l.alive_checked_at, l.last_seen_at) < s.sent_at) / nullif(count(*), 0), 2) as pct
  from sent s join listings l on l.id = s.listing_id
 group by rollup (s.kind) order by s.kind nulls last;

-- M2. Clic en auto muerto: clic en una alerta cuyo auto se detectó gone hasta 24 h después del clic sin
-- haberse visto vivo después del clic. Hoy: 1 de 88. Objetivo: 0. (Solo clics de alertas: el panel no
-- registra clics por auto.)
select count(*) as clics,
       count(*) filter (where l.status = 'gone' and l.detail_checked_at <= n.clicked_at + interval '24 hours'
                          and coalesce(l.alive_checked_at, l.last_seen_at) < n.clicked_at) as clic_en_muerto
  from notifications n join listings l on l.id = n.listing_id
 where n.clicked_at >= now() - interval '14 days';

-- M3. Tarjetas dudosas en el panel: tarjetas de búsquedas activas (level <> 'low', auto active) sin señal de
-- vida hace más de 48 h. Hoy: 32 % (5.124/16.128). Objetivo: < 5 %.
select l.source,
       count(*) as tarjetas,
       count(*) filter (where coalesce(l.alive_checked_at, l.last_seen_at) < now() - interval '48 hours') as dudosas,
       round(100.0 * count(*) filter (where coalesce(l.alive_checked_at, l.last_seen_at) < now() - interval '48 hours')
             / nullif(count(*), 0), 1) as pct,
       count(*) filter (where m.level = 'high') as tarjetas_high,
       count(*) filter (where m.level = 'high'
                          and coalesce(l.alive_checked_at, l.last_seen_at) < now() - interval '48 hours') as dudosas_high
  from matches m
  join search_profiles sp on sp.id = m.search_profile_id and sp.enabled
  join listings l on l.id = m.listing_id and l.status = 'active'
 where m.level <> 'low'
 group by rollup (l.source) order by l.source nulls last;

-- M4. Demora de detección: desde la última señal de vida hasta que se detectó el fin, de los gone de la
-- semana, por fuente. Hoy ML 358 h / 653 h. Objetivo: < 48 h / 96 h. (Los marcados por la búsqueda
-- —«Vendido ·» en FB— entran con demora ~0.)
select l.source, count(*) as terminados,
       round(extract(epoch from percentile_cont(0.5) within group (
         order by l.detail_checked_at - coalesce(l.alive_checked_at, l.last_seen_at))) / 3600) as mediana_h,
       round(extract(epoch from percentile_cont(0.9) within group (
         order by l.detail_checked_at - coalesce(l.alive_checked_at, l.last_seen_at))) / 3600) as p90_h
  from listings l
 where l.status = 'gone' and l.detail_checked_at >= now() - interval '7 days'
   and (l.attributes ? '_not_vehicle') is not true
 group by l.source order by terminados desc;

-- M5. Costo. raw_pages guarda solo la última página de cada auto, así que esto cuenta autos leídos por día
-- (piso de las páginas reales); el conteo exacto por pasada está en el log del worker
-- («watchlist matched: N checked (mercadolibre X, facebook Y…)» y «presend: N of M cars checked»).
select date_trunc('day', r.fetched_at at time zone 'America/Argentina/Buenos_Aires')::date as dia,
       l.source, count(*) as autos_leidos
  from raw_pages r join listings l on l.id = r.listing_id
 where r.fetched_at >= now() - interval '7 days'
 group by 1, 2 order by 1 desc, 3 desc;

-- M5 (errores): fallos de chequeo por etapa y fuente. Las pausas del breaker viven en la memoria del
-- worker: en el VPS, `grep -h "paused for" /opt/automotive/logs/worker.log* | cut -c1-10 | sort | uniq -c`
-- y, para FB, las renovaciones de sesión con ops/vps/fb-login.sh.
select date_trunc('day', e.created_at)::date as dia, e.stage, split_part(e.ref, ':', 1) as ref_kind, count(*)
  from pipeline_errors e
 where e.created_at >= now() - interval '7 days' and e.stage in ('watchlist', 'presend', 'enrich')
 group by 1, 2, 3 order by 1 desc, 4 desc;

-- Medición del ruido de avisos (docs/FB_DUPLICADOS_PLACEHOLDER_TERMINADOS.md). SOLO LECTURA.
-- Correr en el SQL editor de Supabase (o execute_sql). Cambiar :desde (fecha de inicio) a mano.

-- 1) Avisos repetidos por cada 100 enviados, por huella (la medición de la auditoría).
--    Un envío es un aviso new_match/opportunity por (usuario, aviso), en cualquier canal (hoy solo
--    hay email) y estado salvo 'skipped'; «repetido» = el usuario ya recibió otro envío con la
--    misma huella (fingerprint no nulo).
with sent as (
  select n.user_id, n.listing_id, min(n.created_at) as created_at, l.fingerprint
    from public.notifications n join public.listings l on l.id = n.listing_id
   where n.kind in ('new_match', 'opportunity')
     and n.status <> 'skipped' and n.created_at >= date '2026-11-24'          -- :desde
   group by n.user_id, n.listing_id, l.fingerprint
), ranked as (
  select *, row_number() over (partition by user_id, fingerprint order by created_at, listing_id) rn
    from sent
)
select count(*) as enviados,
       count(*) filter (where fingerprint is not null and rn > 1) as repetidos_por_huella,
       round(100.0 * count(*) filter (where fingerprint is not null and rn > 1) / nullif(count(*), 0), 2)
         as repetidos_por_100_enviados
  from ranked;

-- 2) Lo mismo con la regla de grupos de repost del PR (misma fuente + vendedor que no es agencia + marca/modelo/año,
--    precio dentro de 3 %, km sin contradicción) y la huella: un envío es repetido si el usuario ya
--    recibió antes otro aviso del mismo auto.
with sent as (
  select n.user_id, n.listing_id, min(n.created_at) as created_at
    from public.notifications n
   where n.kind in ('new_match', 'opportunity')
     and n.status <> 'skipped' and n.created_at >= date '2026-11-24'          -- :desde
   group by n.user_id, n.listing_id
), twin_prior as (
  select s.user_id, s.listing_id,
         exists (
           select 1 from sent p
             join public.listings t on t.id = p.listing_id
             join public.listings a on a.id = s.listing_id
            where (p.created_at, p.listing_id) < (s.created_at, s.listing_id)
              and p.user_id = s.user_id and t.id <> a.id
              and ((a.fingerprint is not null and a.fingerprint = t.fingerprint)
                or a.probable_repost_of = t.id or t.probable_repost_of = a.id
                or (a.source = t.source and a.seller_key is not null and a.seller_key = t.seller_key
                    and coalesce(a.seller_type::text, '') <> 'dealer' and not coalesce(a.dealer_inferred, false)
                    and coalesce(t.seller_type::text, '') <> 'dealer' and not coalesce(t.dealer_inferred, false)
                    and a.year = t.year and lower(a.make) = lower(t.make) and lower(a.model) = lower(t.model)
                    and a.price_usd > 0 and t.price_usd > 0
                    and abs(a.price_usd - t.price_usd) <= 0.03 * greatest(a.price_usd, t.price_usd)
                    and (a.mileage_km is null or t.mileage_km is null
                         or abs(a.mileage_km - t.mileage_km) <= 0.02 * greatest(a.mileage_km, t.mileage_km))))
         ) as repeated
    from sent s
)
select count(*) as enviados, count(*) filter (where repeated) as repetidos_por_grupo,
       round(100.0 * count(*) filter (where repeated) / nullif(count(*), 0), 2) as repetidos_por_100_enviados
  from twin_prior;

-- 3) Avisos terminados en los 10 mejores. (a) Lo que ve el usuario: search_results ya filtra
--    listing_status = 'active' en las vistas «todos», «nuevos» y «oportunidades»; esto debe dar 0.
--    (b) La tabla matches cruda (lo que miden las auditorías): terminados entre los 10 mejores por score.
with top as (
  select m.search_profile_id, l.status,
         row_number() over (partition by m.search_profile_id order by m.score desc nulls last, m.listing_id) rn
    from public.matches m
    join public.listings l on l.id = m.listing_id
    join public.search_profiles sp on sp.id = m.search_profile_id and sp.enabled
)
select count(*) filter (where status = 'gone') as terminados_en_top10_de_matches,
       count(*) as filas_top10,
       round(100.0 * count(*) filter (where status = 'gone') / nullif(count(*), 0), 2) as pct
  from top where rn <= 10;

-- 4) Precios placeholder (un dígito 1-8 repetido 4+ veces) con alerta enviada desde :desde,
--    por nivel: con placeholder_f2 prendido, new_match/opportunity de level good o high debe ser 0.
select m.level, n.kind, count(distinct (n.user_id, n.listing_id)) as enviados
  from public.notifications n
  join public.listings l on l.id = n.listing_id
  join public.matches m on m.id = n.match_id
 where n.kind in ('new_match', 'opportunity') and n.status <> 'skipped'
   and n.created_at >= date '2026-11-24'                                      -- :desde
   and round(l.price)::text ~ '^([1-8])\1{3,}$'
 group by 1, 2 order by 1, 2;

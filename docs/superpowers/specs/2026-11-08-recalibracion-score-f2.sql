-- 2026-11-08-recalibracion-score-f2.sql — anexo SQL del spec 2026-11-08-recalibracion-score-design.md.
-- F2 «precio × encaje» (f3), tal como se midió el 2026-11-08 en producción con SELECT de solo lectura.
--
-- Qué es: la CTE candidata del backtest del Opportunity Score. No es una migración ni código del worker.
-- Cómo se usa: se agrega después del prefijo del backtest (features + state), que arma la CTE st3 con una fila por
-- match y variante ('card' = datos de la tarjeta al generarse el match, 'post' = datos después del detalle).
-- El prefijo y las corridas crudas quedaron en el espacio de trabajo del análisis y no se suben al repo.
--
-- Salida: cand(variant, match_id, score, level, ...) con
--   'F2@card' : decide con la tarjeta (pipeline de hoy)
--   'F2@post' : decide después del detalle (generated_at + 5 min)
--   'F2@dec'  : el pipeline propuesto: tarjeta, salvo búsquedas con preferencia de vendedor cuya tarjeta no trae vendedor,
--               que esperan al detalle (barrido a 20 min) -> fila post
-- Con los seis interruptores de f2par en false y c_high = 0, x_high = 0,75 reproduce F (la propuesta anterior) exacto:
-- 0 diferencias de nivel y de score en 3.209 matches x 3 variantes.
--
-- Diferencias entre esta versión medida y la versión final del spec (§3 y §16 del spec):
--  * Regla 4a: acá el dígito repetido incluye el 9; la versión final usa solo 1–8 (los 9.999 son precios de vidriera).
--  * Regla 4b (mismo precio en >= 3 autos de un vendedor de FB): acá está; la versión final la saca (no existe al decidir).
--  * Regla 5: la versión final saca la rama «concesionari[oa] (oficial|lider)» y pide voz en plural o dos señales.
--  * Regla 6 («Sold ·»): acá bloquea la alerta con el título de hoy (look-ahead); la versión final la saca del score
--    y la pone en el colector de Facebook (aviso terminado = gone).
--  Las tres primeras no cambian ninguna alerta medida. Sacar la regla 6 del score devuelve 1 alerta en el conjunto
--  actual y 4 en el extendido (búsquedas 89, 129, 269 y 350): al decidir no tenían el título «Sold», así que en
--  producción habrían salido igual (verificación del 2026-11-08).
--
-- Reglas nuevas respecto de F:
--  1. Los cortes de nivel leen fit_g = promedio de las preferencias, SIN el −0,03 por filtro duro sin dato. El −0,03 queda
--     solo en el score (ordena dentro del nivel). Saca el escalón de V7 (tarjeta de ML sin caja/combustible: 0,50 − 0,06).
--  2. Vendedor confirmado distinto del preferido (fuente, «posible agencia» F-02 o texto de agencia) -> como mucho
--     «coincidencia» (se lista, no alerta a «buena»/🔥). Vendedor sin dato NO es esto (espera al detalle; 0,75; sin 🔥).
--  3. 🔥 combinada: sin flags, precio >= 0,70, encaje >= 0,70 y 0,6·precio + 0,4·encaje >= 0,82 (F: precio >= 0,75).
--     La banda 🔥 85–99 arranca en ese 82: el ejemplo del PRD da 88 (ref. por versión) u 86 (ref. por modelo).
--  4. Precio simbólico (dígito repetido: 11.111, 9.999, 99.999.999; o en Facebook el mismo precio en >= 3 autos
--     distintos del vendedor en 60 días) = «sin precio»: como mucho «coincidencia», fuera de 🔥.
--  5. Texto de agencia en la descripción de un «particular» = «posible agencia» para la preferencia de vendedor (extensión
--     de F-02: solo actúa vía esa preferencia). Necesita el detalle (la tarjeta no trae descripción).
--  6. Título de Facebook «Sold ·» / «Vendido» = aviso terminado: no alerta y no cuenta como 🔥 vivo (flag 'vendido').
, f2par(pv, x_high, y_high, c_high, x_good, y_good, y_deal, y_min, d_floor, d_ceil, d_mult, d_cred_min, d_cred_max, d_susp,
        u_pref, f_fail, f_trim_other, f_seller_fail, pen_unk, n_min_high, fair_min_d, low_d, kavak_off, model_rel, w_deal,
        gate_known, seller_cap, placeholder, agency_text, sold_out) as (values
  -- pv      xh    yh    ch    xg    yg    yd    ym    dfl   dce   dmu  cmin cmax susp  u     fail  trim  sfail pen   n   fair  low    kav  mrel  w     gk     scap   ph     ag     sold
  ('F2',    0.70, 0.70, 0.82, 0.65, 0.85, 0.45, 0.30, 12.0, 20.0, 2.5, 5.0, 35.0, 50.0, 0.75, 0.40, 0.50, 0.40, 0.03, 10, -2.0, -10.0, 9.0, 0.90, 0.60, true,  true,  true,  true,  true)
)
-- per listing: the junk signals (current listing text; the description exists only after the detail page)
, f2l as materialized (
  select l.id listing_id,
    lower(translate(coalesce(l.title, ''), 'ÁÉÍÓÚÜÑáéíóúüñ', 'AEIOUUNaeiouun')) ~ '^(sold|vendid[oa])\y' sold_title,
    coalesce(round(l.price)::bigint::text ~ '^(\d)\1{3,}$', false) rep_price,
    coalesce(l.source = 'facebook' and l.price > 0 and l.seller_key is not null and (
      select count(distinct coalesce(l2.make, '') || '|' || coalesce(l2.model, '') || '|' || coalesce(l2.year::text, ''))
      from listings l2 where l2.source = l.source and l2.seller_key = l.seller_key and round(l2.price) = round(l.price)
        and l2.first_seen_at >= now() - interval '60 days') >= 3, false) same_price_fb,
    coalesce(l.seller_type = 'private' and lower(translate(coalesce(l.description, ''), 'ÁÉÍÓÚÜÑáéíóúüñ', 'AEIOUUNaeiouun'))
      ~ '(solo (con )?(el |tu )?dni|cuotas fijas|cuotas en pesos|credito prendario|financiamos|financiacion (propia|accesible|en pesos|bancaria|personalizada|disponible)|opciones de financiacion|planes de financiacion|(tomamos|recibimos|aceptamos) (tu |su )?(usado|auto|vehiculo|unidad)|te lo compramos|compramos tu (auto|usado)|somos (una )?(agencia|concesionari)|nuestr[oa] (agencia|concesionari|local|salon|showroom)|concesionari[oa] (oficial|lider)|consignacion|horario de atencion)', false) agency_txt
  from listings l where l.id in (select listing_id from ev)
)
, f2x as materialized (
  select s.variant, s.match_id, s.search_id, s.source, s.year, s.pr_n, s.pr_level_used, s.card, s.price_partial,
    s.listing_status, j.sold_title, j.rep_price, j.same_price_fb, j.agency_txt,
    (coalesce(s.price_t > 0, false) and not s.price_partial) has_price0, s.d_t,
    0.5 + 0.5 * greatest(0, least(1, (coalesce(s.pr_n, 0) - 5) / 15.0)) r_n,
    case when s.year is null then 0.3 else 1.0 end r_year,
    case when s.pr_median > 0 and s.pr_p25 > 0 then 100 * (1 - s.pr_p25 / s.pr_median) end s_lo,
    ( coalesce(s.mr ? 'year' and s.year is null, false)::int
    + coalesce(s.mr ? 'price' and (s.price_partial or not coalesce(s.price_t > 0, false)), false)::int
    + coalesce(s.mr ? 'km' and s.km_t is null, false)::int
    + coalesce(s.mr ? 'transmission' and coalesce(s.trans_t, '') = '', false)::int
    + coalesce(s.mr ? 'fuel' and coalesce(s.fuel_t, '') = '', false)::int
    + coalesce(s.mr->'body_type'->>'result' = 'unknown', false)::int
    + (coalesce(s.mr->'seller'->>'kind' = 'hard', false) and s.seller_eff_t is null)::int
    + (coalesce(s.r_trim_kind = 'hard', false) and coalesce(s.trim_t, '') = '')::int
    + (select count(*) from jsonb_each(s.mr) r where r.value->>'kind' = 'hard' and r.value->>'result' = 'unknown'
         and r.key not in ('year', 'price', 'km', 'transmission', 'fuel', 'body_type', 'seller', 'trim'))::int) n_unk_hard,
    (s.mr ? 'price_target') h_pt, (s.mr ? 'km_target') h_kt, (s.mr ? 'seller_type') h_sel, (s.mr ? 'colors') h_col,
    (s.mr ? 'max_distance_km') h_dist,
    coalesce(s.mr->'trim'->>'kind' = 'soft' and coalesce(array_length(s.wanted_trims, 1), 0) > 0, false) h_trim,
    ((s.mr ? 'seller_type') or coalesce(s.mr->'seller'->>'kind' = 'hard', false)) h_sel_any,
    case when s.pt_value_t is null then null
         when s.pt_value_t <= s.price_target then 1.0
         when pm.pmax_pt > s.price_target
           then 1 - 0.4 * greatest(0, least(1, (s.pt_value_t - s.price_target) / (pm.pmax_pt - s.price_target)))
         else 1 - 0.6 * greatest(0, least(1, (s.pt_value_t - s.price_target) / (0.15 * s.price_target))) end v_pt,
    case when s.km_t is null then null when s.km_t <= s.km_target then 1.0
         else 1 - 0.6 * greatest(0, least(1, (s.km_t - s.km_target) / (0.3 * greatest(s.km_target, 1)))) end v_kt,
    case s.sr_colors when 'ok' then 1.0 when 'fail' then -1.0 end v_col,
    case s.sr_max_distance_km when 'ok' then 1.0 when 'fail' then -1.0 end v_dist,
    case when coalesce(s.trim_t, '') = '' then null when s.trim_pref_match then 1.0 else -2.0 end v_trim,
    s.seller_eff_t, s.pref_seller
  from st3 s
  left join f2l j on j.listing_id = s.listing_id
  cross join lateral (select case when s.price_max is null then null
                                  when s.filter_currency = s.price_target_currency then s.price_max
                                  when s.price_target_currency = 'USD' then s.price_max / s.fx_t
                                  else s.price_max * s.fx_t end pmax_pt) pm
  where s.variant in ('post', 'card')
)
, f2y0 as (
  select p.*, x.*,
    -- placeholder price: treated as no price
    (p.placeholder and (x.rep_price or x.same_price_fb)) symbolic,
    -- effective seller: «posible agencia» by description (detail page only: the card has no description)
    case when p.agency_text and x.agency_txt and not x.card then 'dealer' else x.seller_eff_t end seller2
  from f2x x cross join f2par p
)
, f2y1 as (
  select c.*,
    c.has_price0 and not c.symbolic has_price,
    case when c.symbolic then null else c.d_t end d2,
    case when c.symbolic then null else c.d_t - case when c.source = 'kavak' then c.kavak_off else 0 end end d_eff,
    greatest(c.d_floor, least(c.d_ceil, coalesce(c.d_mult * c.s_lo, 16.0))) d_full,
    c.r_n * c.r_year * case when c.pr_level_used = 'model' then c.model_rel else 1 end r,
    case when c.seller2 is null then null when c.seller2 = c.pref_seller then 1.0 else -1.0 end v_sel,
    (c.h_sel_any and c.seller2 is not null and c.pref_seller is not null and c.seller2 <> c.pref_seller) seller_mismatch,
    (c.h_pt::int + c.h_kt::int + c.h_sel::int + c.h_col::int + c.h_dist::int + c.h_trim::int) n_pref
  from f2y0 c
)
, f2y2 as (
  select c.*,
    ( case when c.h_pt   then coalesce(c.v_pt, c.u_pref) else 0 end
    + case when c.h_kt   then coalesce(c.v_kt, c.u_pref) else 0 end
    + case when c.h_sel  then case when c.v_sel is null then c.u_pref when c.v_sel < 0 then c.f_seller_fail else c.v_sel end else 0 end
    + case when c.h_col  then case when c.v_col is null then c.u_pref when c.v_col < 0 then c.f_fail else c.v_col end else 0 end
    + case when c.h_dist then case when c.v_dist is null then c.u_pref when c.v_dist < 0 then c.f_fail else c.v_dist end else 0 end
    + case when c.h_trim then case when c.v_trim is null then c.u_pref when c.v_trim < 0 then c.f_trim_other else c.v_trim end else 0 end
    ) pref_sum
  from f2y1 c
)
, f2y3 as (
  select c.*,
    case when c.n_pref = 0 then 1.0 else c.pref_sum / c.n_pref end fit_g0,
    case when not c.has_price or c.d_eff is null then null else
      case when q.raw <= 0.4 then q.raw else 0.4 + c.r * (q.raw - 0.4) end end deal,
    coalesce(c.d2 >= c.d_susp, false) suspicious,
    (c.price_partial or coalesce(c.d2 >= 65, false)) excluded,
    coalesce(c.has_price and c.d_eff between c.d_cred_min and c.d_cred_max and c.pr_n >= c.n_min_high
             and c.year is not null and c.d2 < c.d_susp, false) credible_deal
  from f2y2 c
  cross join lateral (select case when c.d_eff is null then null
                                  when c.d_eff <= -20 then 0.0
                                  when c.d_eff <= 0 then 0.4 * (c.d_eff + 20) / 20
                                  when c.d_eff <= c.d_full then 0.4 + 0.6 * c.d_eff / c.d_full
                                  when c.d_eff <= c.d_cred_max then 1.0
                                  when c.d_eff < c.d_susp then 1 - 0.3 * (c.d_eff - c.d_cred_max) / (c.d_susp - c.d_cred_max)
                                  else 0.6 end raw) q
)
, f2y4 as (
  select c.*,
    greatest(0, c.fit_g0 - c.pen_unk * c.n_unk_hard) fit,                               -- score (orders inside a level)
    case when c.gate_known then c.fit_g0 else greatest(0, c.fit_g0 - c.pen_unk * c.n_unk_hard) end fit_g,   -- gates
    concat_ws(',', case when not c.has_price then case when c.symbolic then 'precio_simbolico' else 'sin_precio' end end,
              case when c.year is null then 'sin_año' end,
              case when c.has_price and c.d2 is null then 'sin_comparables' end,
              case when c.d2 is not null and coalesce(c.pr_n, 0) < c.n_min_high then 'pocos_comparables' end,
              case when c.d_eff > c.d_cred_max and c.d2 < c.d_susp then 'muy_por_debajo' end,
              case when c.d2 >= c.d_susp then 'sospechoso' end,
              case when c.h_sel_any and c.seller2 is null then 'vendedor_sin_dato' end,
              case when c.seller_cap and c.seller_mismatch then 'otro_vendedor' end,
              case when c.sold_out and c.sold_title then 'vendido' end) flags
  from f2y3 c
)
, f2y as (
  select c.*,
    -- caps: a confirmed seller mismatch on a stated seller preference -> at most «coincidencia» (never «buena» / 🔥)
    case when c.seller_cap and c.seller_mismatch and c.lvl0 in ('high', 'good') then 'match' else c.lvl0 end lvl,
    (c.sold_out and c.sold_title) no_alert,
    100 * (c.w_deal * coalesce(c.deal, case when c.has_price then 0.4 else 0.2 end) + (1 - c.w_deal) * c.fit) raw_s,
    case when c.deal is null then 'desconocido'
         when c.credible_deal and c.deal >= c.x_high then 'fuerte'
         when c.deal >= c.x_good and (c.d_eff > c.d_cred_max or c.d2 >= c.d_susp or c.year is null
                                      or coalesce(c.pr_n, 0) < c.n_min_high) then 'a_verificar'
         when c.credible_deal or c.deal >= c.x_good then 'bueno'
         when c.d_eff >= c.fair_min_d then 'en_linea' when c.d_eff >= c.low_d then 'algo_caro' else 'caro' end deal_tier,
    (c.variant = 'card' and c.card and c.h_sel_any and c.seller_eff_t is null) defer_here
  from (
    select c.*,
      case when c.excluded then 'excluded'
           when c.flags = '' and c.deal >= c.x_high and c.fit_g >= c.y_high
                and (c.c_high = 0 or c.w_deal * c.deal + (1 - c.w_deal) * c.fit_g >= c.c_high) then 'high'
           when c.has_price and not c.suspicious and c.year is not null
                and (((c.deal >= c.x_good or c.credible_deal) and c.fit_g >= c.y_deal)
                     or (c.fit_g >= c.y_good and (c.d_eff >= c.fair_min_d or c.d2 is null))) then 'good'
           when c.fit_g >= c.y_min and (not c.has_price or c.d2 is null or c.d_eff >= c.low_d or c.suspicious) then 'match'
           else 'low' end lvl0
    from f2y4 c) c
)
, f2z as (
  select c.*, bool_or(c.defer_here) over (partition by c.pv, c.match_id) deferred,
    -- high band 85-99: from raw 70 (F) or, with the combined rule, from the rule's own threshold (100·c_high)
    case lvl when 'high'  then 85 + floor(14 * greatest(0, least(1, (raw_s - case when c_high > 0 then 100 * c_high else 70 end)
                                                                    / (100 - case when c_high > 0 then 100 * c_high else 70 end))) + 0.5)
             when 'good'  then 70 + floor(14 * greatest(0, least(1, (raw_s - 45) / 50.0)) + 0.5)
             when 'match' then 50 + floor(19 * greatest(0, least(1, (raw_s - 25) / 60.0)) + 0.5)
             else floor(49 * greatest(0, least(1, raw_s / 70.0)) + 0.5) end::int score_f
  from f2y c
)
, cand as (
  select pv || '@' || variant variant, match_id, score_f score, lvl level, deal, fit, fit_g, deal_tier, flags, r, d_eff,
         d_full, n_unk_hard, n_pref, raw_s, pv, variant base_variant, deferred, seller_mismatch, sold_title, symbolic,
         agency_txt, listing_status, no_alert, lvl0
  from f2z
  union all
  select pv || '@dec', match_id, score_f, lvl, deal, fit, fit_g, deal_tier, flags, r, d_eff, d_full, n_unk_hard, n_pref,
         raw_s, pv, variant, deferred, seller_mismatch, sold_title, symbolic, agency_txt, listing_status, no_alert, lvl0
  from f2z where (variant = 'card' and not deferred) or (variant = 'post' and deferred)
)

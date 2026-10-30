-- PAR-03 · Días publicado y bajas de precio, parte por aviso
-- (docs/BACKLOG_PRODUCTO_2026-10.md, ítem PAR-03; diseño
-- docs/superpowers/specs/2026-10-29-par03-dias-y-bajas-design.md; plan
-- docs/superpowers/plans/2026-10-29-par03-dias-y-bajas.md).
--
-- * listing_price_tracks(ids): the only definition of a listing's price drops,
--   from its snapshots (one row per listing with at least one priced snapshot).
--   The web calls it with a results page's ids and the worker with a batch of
--   candidates. match_cards, search_results and comparables are left alone.
-- * app_config.price_track.min_drop_pct (1): the smallest fall, in %, that
--   counts as a drop. Apart from price_drop_min_pct (3), which decides alerts.
-- No table, column, RLS or SCORING_VERSION change.

-- ---------------------------------------------------------------------------
-- app_config
-- ---------------------------------------------------------------------------

insert into public.app_config (key, value)
values ('price_track', '{"min_drop_pct": 1}')
on conflict (key) do nothing;

-- app_config.price_track.min_drop_pct for listing_price_tracks(), which runs
-- with the caller's rights (they don't reach app_config). A missing, negative
-- or non-numeric value falls back to the seed's 1.
create function public.price_track_min_drop_pct() returns numeric
language sql stable security definer set search_path = '' as $$
  select coalesce(
    (select (c.value->>'min_drop_pct')::numeric
       from public.app_config c
      where c.key = 'price_track'
        and jsonb_typeof(c.value->'min_drop_pct') = 'number'
        and (c.value->>'min_drop_pct')::numeric >= 0),
    1)
$$;

-- ---------------------------------------------------------------------------
-- listing_price_tracks
-- ---------------------------------------------------------------------------

-- Walks each listing's priced snapshots in order, collapses consecutive repeats
-- (same price and currency, as the listing page's price history does) and
-- compares each pair: in the listing's own currency when it didn't change
-- (an ARS price that stays put is no drop because the dollar moved), in
-- price_usd otherwise (as the worker's price_drop_pct). A pair counts as a drop
-- (or a rise) when it moved at least min_drop_pct.
--   cum_pct: first against last price, positive when it fell; own currency, or
--            price_usd when first and last currencies differ.
--   cum_usd: the same fall in dollars: USD directly; ARS with the last
--            snapshot's fx_rate (today's dollar, so the dollar's move is no
--            drop); price_usd when the currency changed.
--   Both come rounded as they are shown (cum_pct to 0,1 and cum_usd to whole
--   dollars; numeric round(), half away from zero), so the worker (Python)
--   and the web (JS), whose own float rounding differs on halves (6,25 or
--   2.500,50), print the same figures.
create function public.listing_price_tracks(p_listing_ids bigint[])
returns table (listing_id bigint, drops integer, rises integer, first_at timestamptz,
               first_price numeric, first_currency text, last_price numeric, last_currency text,
               cum_pct numeric, cum_usd numeric, last_drop_at timestamptz)
language sql stable security invoker set search_path = '' as $$
  -- materialized: read the setting once, not once per step.
  with cfg as materialized (
    select public.price_track_min_drop_pct() as min_pct
  ),
  ids as (
    select distinct x.id from unnest(p_listing_ids) as x (id) where x.id is not null
  ),
  raw as (
    select i.id as listing_id, s.id as snap_id, s.observed_at, s.price, s.currency, s.price_usd, s.fx_rate,
           lag(s.price)    over w as prev_price,
           lag(s.currency) over w as prev_currency
      from ids i
     cross join lateral (
       select s.id, s.observed_at, s.price, coalesce(s.currency, 'USD') as currency, s.price_usd, s.fx_rate
         from public.listing_snapshots s
        where s.listing_id = i.id and s.price is not null
     ) s
    window w as (partition by i.id order by s.observed_at, s.id)
  ),
  pts as (
    select r.*,
           lag(r.price)     over w as p_price,
           lag(r.currency)  over w as p_currency,
           lag(r.price_usd) over w as p_usd,
           row_number() over w                                           as n_asc,
           row_number() over (partition by r.listing_id order by r.observed_at desc, r.snap_id desc) as n_desc
      from raw r
     where r.prev_price is null or r.prev_price <> r.price or r.prev_currency <> r.currency
    window w as (partition by r.listing_id order by r.observed_at, r.snap_id)
  ),
  steps as (
    select p.listing_id, p.observed_at,
           case when p.p_currency = p.currency
                then case when p.p_price > 0 then (p.p_price - p.price) / p.p_price * 100 end
                else case when p.p_usd > 0 and p.price_usd is not null
                          then (p.p_usd - p.price_usd) / p.p_usd * 100 end
           end as fall_pct
      from pts p
     where p.n_asc > 1
  ),
  counted as (
    select st.listing_id,
           count(*) filter (where st.fall_pct >= cfg.min_pct)::integer        as drops,
           count(*) filter (where -st.fall_pct >= cfg.min_pct)::integer       as rises,
           max(st.observed_at) filter (where st.fall_pct >= cfg.min_pct)      as last_drop_at
      from steps st
     cross join cfg
     group by st.listing_id
  )
  select f.listing_id,
         coalesce(c.drops, 0),
         coalesce(c.rises, 0),
         f.observed_at,
         f.price,
         f.currency,
         l.price,
         l.currency,
         round(case when f.currency = l.currency
                    then case when f.price > 0 then (f.price - l.price) / f.price * 100 end
                    else case when f.price_usd > 0 and l.price_usd is not null
                              then (f.price_usd - l.price_usd) / f.price_usd * 100 end
               end, 1),
         round(case when f.currency = l.currency and l.currency = 'USD' then f.price - l.price
                    when f.currency = l.currency and l.fx_rate > 0 then (f.price - l.price) / l.fx_rate
                    when f.currency = l.currency and l.price_usd > 0 then (f.price - l.price) / (l.price / l.price_usd)
                    when f.currency <> l.currency and f.price_usd is not null and l.price_usd is not null
                    then f.price_usd - l.price_usd
               end, 0),
         c.last_drop_at
    from pts f
    join pts l on l.listing_id = f.listing_id and l.n_desc = 1
    left join counted c on c.listing_id = f.listing_id
   where f.n_asc = 1
   order by f.listing_id
$$;

comment on function public.listing_price_tracks(bigint[]) is
  'PAR-03: per listing, drops and rises between consecutive distinct prices (>= app_config.price_track.min_drop_pct) '
  'and the cumulative fall (cum_pct, cum_usd; positive = it fell) since the first snapshot. Caller''s rights.';

-- ---------------------------------------------------------------------------
-- Grants
-- ---------------------------------------------------------------------------

revoke all on function public.price_track_min_drop_pct(), public.listing_price_tracks(bigint[])
  from public, anon;
grant execute on function public.price_track_min_drop_pct(), public.listing_price_tracks(bigint[])
  to authenticated, service_role;

notify pgrst, 'reload schema';

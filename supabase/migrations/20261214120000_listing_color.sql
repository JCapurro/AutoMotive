-- Filtro de color (docs/PLAN_FILTRO_COLOR.md, sección 8 es el contrato;
-- docs/COLOR.md). Juan approved the plan on 12/11/2026.
--
-- * listings.color: the worker's code (normalization/color.py), null =
--   unknown. listings.attributes._color = {"method": "source" | "text" |
--   "vision", "raw", "confidence", "model", "v", "candidates": [{"color",
--   "prob"}], "photos", "at"} says how it was decided. No index: no query
--   picks listings by color; preview_search filters the make or body type
--   candidates it already has.
-- * search_colors(filters) and listing_color_fits(color, attributes, wanted):
--   the rule of matching.py's `color` (hard, after body_type). Without a
--   filter, without the listing's color, with the color in the list, or with
--   a candidate of prob >= 30 in the list, the listing passes; another color
--   fails.
-- * search_filters_problem: filters.colors is absent, null or an array of the
--   8 codes (an empty array is no filter). The search_profiles trigger
--   (enforce_plan_features) rejects the rest with invalid_filters.
-- * preview_search counts with listing_color_fits, so the live count says
--   what the rematch brings; its sample carries the color.
-- * missed_car (the 2.5 email's car) is strict: the listing's color, if it
--   has one, must be in the list; a candidate is not enough.
-- * match_cards: color and color_method last (search_results and
--   recent_opportunities return setof match_cards and get them too). The web
--   shows «Color: gris · según la foto» (vision) or «· dato del aviso».
-- * color_vision_runs: the persistent daily budget of the vision pass, as
--   photo_hash_runs (the worker reserves under an advisory lock and counts
--   the rolling 24 h).
-- * app_config.color_vision: the vision pass's switch and limits, editable in
--   /admin/config. An existing row is left alone.
-- No SQL read the old soft preference preferences.colors; the worker drops it.
-- Idempotent: it can run twice. No `concurrently`: applied in one transaction.

-- ---------------------------------------------------------------------------
-- listings
-- ---------------------------------------------------------------------------

alter table public.listings add column if not exists color text;
alter table public.listings drop constraint if exists listings_color_check;
alter table public.listings add constraint listings_color_check
  check (color in ('blanco', 'negro', 'gris', 'azul', 'rojo', 'verde', 'beige', 'otro')) not valid;
alter table public.listings validate constraint listings_color_check;
comment on column public.listings.color is
  'Color code (docs/PLAN_FILTRO_COLOR.md), null = unknown: blanco, negro, gris, azul, rojo, verde, '
  'beige, otro. Decided by the worker from the source''s value, the text or the photos (source > '
  'text > vision); attributes._color = {"method", "raw", "confidence", "candidates", ...} says how.';

-- ---------------------------------------------------------------------------
-- Helpers
-- ---------------------------------------------------------------------------

-- filters.colors as an array, or null when there are none.
create or replace function public.search_colors(p_filters jsonb) returns text[]
language sql immutable set search_path = '' as $$
  select case when jsonb_typeof(p_filters->'colors') = 'array'
                   and jsonb_array_length(p_filters->'colors') > 0
              then array(select jsonb_array_elements_text(p_filters->'colors')) end
$$;

-- Whether a listing passes a color filter, as matching.py's `color` rule:
-- only a known color that is not in the list, without a candidate of the
-- photo (prob >= 30, normalization/color.py CANDIDATE_MIN_PROB) in the list,
-- fails. A listing without the color is «color sin confirmar»: it passes.
create or replace function public.listing_color_fits(p_color text, p_attrs jsonb, p_wanted text[])
returns boolean
language sql immutable set search_path = '' as $$
  select p_wanted is null
      or cardinality(p_wanted) = 0
      or p_color is null
      or p_color = any (p_wanted)
      or exists (select 1
                   from jsonb_array_elements(case when jsonb_typeof(p_attrs->'_color'->'candidates') = 'array'
                                                  then p_attrs->'_color'->'candidates'
                                                  else '[]'::jsonb end) c
                  where jsonb_typeof(c->'prob') = 'number'
                    and (c->>'prob')::numeric >= 30
                    and (c->>'color') = any (p_wanted))
$$;

-- 20261128120000's, plus filters.colors. create or replace keeps the grants
-- (server-only) and the volatility.
create or replace function public.search_filters_problem(p_filters jsonb) returns text
language sql immutable set search_path = '' as $$
  select case
    when coalesce(jsonb_typeof(p_filters->'make'), 'null') not in ('null', 'string')
      or coalesce(jsonb_typeof(p_filters->'model'), 'null') not in ('null', 'string')
      or coalesce(jsonb_typeof(p_filters->'body_types'), 'null') not in ('null', 'array')
      or (jsonb_typeof(p_filters->'body_types') = 'array'
          and exists (select 1 from jsonb_array_elements(p_filters->'body_types') b
                       where jsonb_typeof(b) <> 'string'))
      or coalesce(jsonb_typeof(p_filters->'seller_types'), 'null') not in ('null', 'array')
      or (jsonb_typeof(p_filters->'seller_types') = 'array'
          and (jsonb_array_length(p_filters->'seller_types') <> 1
               or not (p_filters->'seller_types'->0) <@ '["private", "dealer"]'::jsonb
               or jsonb_typeof(p_filters->'seller_types'->0) <> 'string'))
      or coalesce(jsonb_typeof(p_filters->'colors'), 'null') not in ('null', 'array')
      or (jsonb_typeof(p_filters->'colors') = 'array'
          and exists (select 1 from jsonb_array_elements(p_filters->'colors') c
                       where jsonb_typeof(c) <> 'string'
                          or (c #>> '{}') not in ('blanco', 'negro', 'gris', 'azul', 'rojo', 'verde', 'beige', 'otro')))
    then 'invalid_filters'
  end
$$;

-- ---------------------------------------------------------------------------
-- preview_search: 20261206120000's, plus the color rule and the sample's color
-- ---------------------------------------------------------------------------

create or replace function public.preview_search(
  p_filters    jsonb,
  p_origin_lat double precision default null,
  p_origin_lon double precision default null,
  p_radius_km  double precision default null
) returns jsonb
language sql
stable
security definer
set search_path = ''
as $$
  with f as (
    select nullif(btrim(p_filters->>'make'), '')           as make,
           nullif(btrim(p_filters->>'model'), '')          as model,
           public.search_is_model_less(p_filters)          as model_less,
           public.search_body_types(p_filters)             as body_types,
           public.search_colors(p_filters)                 as colors,
           (p_filters->>'year_min')::integer               as year_min,
           (p_filters->>'year_max')::integer               as year_max,
           (p_filters->>'price_min')::numeric              as price_min,
           (p_filters->>'price_max')::numeric              as price_max,
           upper(coalesce(nullif(p_filters->>'currency', ''),
                          case when coalesce((p_filters->>'price_max')::numeric,
                                             (p_filters->>'price_min')::numeric, 0) >= 1000000
                               then 'ARS' else 'USD' end)) as currency,
           (p_filters->>'km_min')::integer                 as km_min,
           (p_filters->>'km_max')::integer                 as km_max,
           nullif(p_filters->>'transmission', '')          as transmission,
           nullif(p_filters->>'fuel', '')                  as fuel,
           case when jsonb_typeof(p_filters->'sources') = 'array'
                     and jsonb_array_length(p_filters->'sources') > 0
                then array(select jsonb_array_elements_text(p_filters->'sources')) end as sources,
           case when coalesce((p_filters->>'trim_strict')::boolean, false)
                     and jsonb_typeof(p_filters->'trims') = 'array'
                     and jsonb_array_length(p_filters->'trims') > 0
                then array(select lower(jsonb_array_elements_text(p_filters->'trims'))) end as strict_trims,
           case when jsonb_typeof(p_filters->'seller_types') = 'array'
                     and jsonb_array_length(p_filters->'seller_types') > 0
                     and public.plan_feature((select auth.uid()), 'seller_filter')
                then array(select jsonb_array_elements_text(p_filters->'seller_types')) end as seller_types
  ),
  fx as (
    select rate from public.fx_rates order by date desc, (kind = 'blue') desc limit 1
  ),
  -- The places the search adds, read as numbers. A value that isn't one is
  -- null, so its place is skipped as matching skips it (the case keeps the
  -- cast from ever seeing the text).
  extra as (
    select case when e->>'lat' ~ '^\s*[-+]?\d+(\.\d+)?\s*$' then (e->>'lat')::double precision end as lat,
           case when e->>'lon' ~ '^\s*[-+]?\d+(\.\d+)?\s*$' then (e->>'lon')::double precision end as lon,
           case when e->>'radius_km' ~ '^\s*[-+]?\d+(\.\d+)?\s*$'
                then (e->>'radius_km')::double precision end as radius
      from jsonb_array_elements(case when jsonb_typeof(p_filters->'extra_locations') = 'array'
                                     then p_filters->'extra_locations' else '[]'::jsonb end) e
  ),
  -- The search's own place and the ones it adds, as matching's search_zones.
  zones as (
    select p_origin_lat as lat, p_origin_lon as lon, p_radius_km as radius
     where p_radius_km > 0 and p_origin_lat is not null and p_origin_lon is not null
    union all
    select x.lat, x.lon, x.radius
      from extra x
     where x.lat is not null and x.lon is not null and x.radius > 0
  ),
  -- One branch per shape, each with its own index: (lower(make), lower(model),
  -- year) or listings_body_type_active_idx.
  candidates as (
    select l.*
      from f
      join public.listings l on lower(l.make) = lower(f.make)
     where f.make is not null
       and (f.model is null or lower(l.model) = lower(f.model))
       and l.status = 'active'
       and l.last_seen_at >= now() - interval '30 days'
       and not l.price_partial
    union all
    select l.*
      from f
      join public.listings l on l.body_type = any (f.body_types)
     where f.model_less
       and f.body_types is not null
       and l.status = 'active'
       and l.body_type is not null
       and l.last_seen_at >= now() - interval '30 days'
       and not l.price_partial
  ),
  priced as (
    select l.*,
           case
             when l.price is null or l.price <= 0 then null
             when upper(coalesce(l.currency, f.currency)) = f.currency then l.price
             when f.currency = 'USD' then coalesce(l.price_usd, l.price / nullif(fx.rate, 0))
             else l.price * fx.rate
           end as price_in_filter
      from candidates l
     cross join f
      left join fx on true
  ),
  hits as (
    select p.*
      from priced p
     cross join f
     where (p.year is null or f.year_min is null or p.year >= f.year_min)
       and (p.year is null or f.year_max is null or p.year <= f.year_max)
       and (p.mileage_km is null or f.km_min is null or p.mileage_km >= f.km_min)
       and (p.mileage_km is null or f.km_max is null or p.mileage_km <= f.km_max)
       and (p.price_in_filter is null or f.price_min is null or p.price_in_filter >= f.price_min)
       and (p.price_in_filter is null or f.price_max is null or p.price_in_filter <= f.price_max)
       and (f.transmission is null or p.transmission is null or p.transmission = f.transmission)
       and (f.fuel is null or p.fuel is null or position(lower(f.fuel) in lower(p.fuel)) > 0)
       and (f.body_types is null or p.body_type = any (f.body_types)
            or (p.body_type is null and not f.model_less))
       and public.listing_color_fits(p.color, p.attributes, f.colors)
       and (f.sources is null or p.source = any (f.sources))
       and (f.seller_types is null
            or (case when p.seller_type = 'dealer' or p.dealer_inferred then 'dealer' else p.seller_type end) is null
            or (case when p.seller_type = 'dealer' or p.dealer_inferred then 'dealer' else p.seller_type end)
               = any (f.seller_types))
       and (f.strict_trims is null or p.trim is null
            or exists (select 1 from unnest(f.strict_trims) t where position(t in lower(p.trim)) > 0))
       and (not exists (select 1 from zones)
            or (p.lat is not null and p.lon is not null
                and exists (select 1 from zones z where public.haversine_km(z.lat, z.lon, p.lat, p.lon) <= z.radius)))
  ),
  sample as (
    select h.id, h.title, h.make, h.model, h.trim, h.year, h.price, h.currency, h.mileage_km,
           h.location_text, h.source, h.first_seen_at, h.body_type, h.color
      from hits h
     order by h.first_seen_at desc
     limit 3
  )
  select jsonb_build_object(
           'count',  (select count(*) from hits),
           'sample', coalesce((select jsonb_agg(to_jsonb(s) order by s.first_seen_at desc) from sample s),
                              '[]'::jsonb))
$$;

-- ---------------------------------------------------------------------------
-- missed_car: 20261210120000's, plus the strict color rule
-- ---------------------------------------------------------------------------

create or replace function public.missed_car(p_search bigint, p_ended timestamptz) returns jsonb
language sql stable security definer set search_path = '' as $$
  with sp as (
    select s.origin_lat, s.origin_lon, s.radius_km, coalesce(s.filters, '{}'::jsonb) as f
      from public.search_profiles s
     where s.id = p_search
  ),
  f as (
    select nullif(btrim(sp.f->>'make'), '')  as make,
           nullif(btrim(sp.f->>'model'), '') as model,
           case when sp.f->>'year_min' ~ '^\d+$' then (sp.f->>'year_min')::int end as year_min,
           case when sp.f->>'year_max' ~ '^\d+$' then (sp.f->>'year_max')::int end as year_max,
           case when jsonb_typeof(sp.f->'years') = 'array' and jsonb_array_length(sp.f->'years') > 0
                then array(select (y)::int from jsonb_array_elements_text(sp.f->'years') y where y ~ '^\d+$') end as years,
           case when sp.f->>'km_min' ~ '^\d+(\.\d+)?$' then (sp.f->>'km_min')::numeric end as km_min,
           case when sp.f->>'km_max' ~ '^\d+(\.\d+)?$' then (sp.f->>'km_max')::numeric end as km_max,
           case when sp.f->>'price_min' ~ '^\d+(\.\d+)?$' then (sp.f->>'price_min')::numeric end as price_min,
           case when sp.f->>'price_max' ~ '^\d+(\.\d+)?$' then (sp.f->>'price_max')::numeric end as price_max,
           upper(coalesce(nullif(sp.f->>'currency', ''),
                          case when coalesce(case when sp.f->>'price_max' ~ '^\d+(\.\d+)?$' then (sp.f->>'price_max')::numeric end,
                                             case when sp.f->>'price_min' ~ '^\d+(\.\d+)?$' then (sp.f->>'price_min')::numeric end,
                                             0) >= 1000000
                               then 'ARS' else 'USD' end)) as currency,
           nullif(sp.f->>'transmission', '') as transmission,
           nullif(sp.f->>'fuel', '')         as fuel,
           public.search_body_types(sp.f)    as body_types,
           public.search_colors(sp.f)        as colors,
           case when jsonb_typeof(sp.f->'trims') = 'array'
                then array(select lower(btrim(t)) from jsonb_array_elements_text(sp.f->'trims') t
                            where btrim(t) <> '') end as trims
      from sp
  ),
  fx as (
    select rate from public.fx_rates order by date desc, (kind = 'blue') desc limit 1
  ),
  -- The search's own place and the ones it adds, as matching's search_zones.
  zones as (
    select sp.origin_lat as lat, sp.origin_lon as lon, sp.radius_km::double precision as radius
      from sp
     where sp.radius_km > 0 and sp.origin_lat is not null and sp.origin_lon is not null
    union all
    select (e->>'lat')::double precision, (e->>'lon')::double precision, (e->>'radius_km')::double precision
      from sp, jsonb_array_elements(case when jsonb_typeof(sp.f->'extra_locations') = 'array'
                                         then sp.f->'extra_locations' else '[]'::jsonb end) e
     where e->>'lat' ~ '^\s*[-+]?\d+(\.\d+)?\s*$' and e->>'lon' ~ '^\s*[-+]?\d+(\.\d+)?\s*$'
       and e->>'radius_km' ~ '^\s*[-+]?\d+(\.\d+)?\s*$' and (e->>'radius_km')::double precision > 0
  ),
  cand as (
    select m.level, m.diff_pct, m.score, m.created_at, l.*,
           case
             when l.price is null or l.price <= 0 then null
             when upper(coalesce(l.currency, f.currency)) = f.currency then l.price
             when f.currency = 'USD' then coalesce(l.price_usd, l.price / nullif(fx.rate, 0))
             else l.price * fx.rate
           end as price_in_filter
      from public.expired_search_matches m
      join public.listings l on l.id = m.listing_id
     cross join f
      left join fx on true
     where m.search_profile_id = p_search and m.access_ended_at = p_ended
       and l.price is not null and not l.price_partial
  )
  select jsonb_strip_nulls(jsonb_build_object(
           'listing_id', c.id, 'title', c.title, 'make', c.make, 'model', c.model, 'trim', c.trim,
           'year', c.year, 'price', c.price, 'currency', c.currency, 'km', c.mileage_km,
           'location', c.location_text,
           'images', case when jsonb_typeof(c.images) = 'array'
                          then (select coalesce(jsonb_agg(i.value order by i.ord), '[]'::jsonb)
                                  from jsonb_array_elements(c.images) with ordinality i (value, ord)
                                 where i.ord <= 3) end,
           'below', c.level = 'high',
           'diff_pct', c.diff_pct,
           'gone', c.status = 'gone',
           'days_listed', case when c.status = 'gone' then greatest(1, ceil(extract(epoch from
                            c.last_seen_at - coalesce(c.published_at, c.first_seen_at)) / 86400)::int) end))
    from cand c
   cross join f
   where (f.make is null or lower(c.make) = lower(f.make))
     and (f.model is null or lower(c.model) = lower(f.model))
     -- A bound the search set needs the listing's value, inside it.
     and ((f.year_min is null and f.year_max is null and f.years is null)
          or (c.year is not null
              and (f.year_min is null or c.year >= f.year_min)
              and (f.year_max is null or c.year <= f.year_max)
              and (f.years is null or cardinality(f.years) = 0 or c.year = any (f.years))))
     and ((f.km_min is null and f.km_max is null)
          or (c.mileage_km is not null
              and (f.km_min is null or c.mileage_km >= f.km_min)
              and (f.km_max is null or c.mileage_km <= f.km_max)))
     and ((f.price_min is null and f.price_max is null)
          or (c.price_in_filter is not null
              and (f.price_min is null or c.price_in_filter >= f.price_min)
              and (f.price_max is null or c.price_in_filter <= f.price_max)))
     -- A car without a year can't be told apart from an older one.
     and c.year is not null
     -- Every word of one of the wanted trims, as matching.trim_matches; with no
     -- trim in the listing, the words of its title.
     and (f.trims is null or cardinality(f.trims) = 0
          or exists (select 1 from unnest(f.trims) t
                      where not exists (select 1 from regexp_split_to_table(replace(t, '!', ''), '\s+') w
                                         where w <> ''
                                           and not (w = any (regexp_split_to_array(
                                                     replace(lower(coalesce(c.trim, c.title, '')), '!', ''), '\s+'))))))
     and (f.transmission is null or c.transmission is null or c.transmission = f.transmission)
     and (f.fuel is null or c.fuel is null or position(lower(f.fuel) in lower(c.fuel)) > 0)
     and (f.body_types is null or c.body_type is null or c.body_type = any (f.body_types))
     -- Color, strict: the listing's own color, never a candidate from the photo.
     and (f.colors is null or c.color is null or c.color = any (f.colors))
     and (not exists (select 1 from zones)
          or (c.lat is not null and c.lon is not null
              and exists (select 1 from zones z where public.haversine_km(z.lat, z.lon, c.lat, c.lon) <= z.radius)))
     -- A believable opportunity: 5 % to 35 % under comparables, or level high without a number.
     and (c.diff_pct between 5 and 35 or (c.diff_pct is null and c.level = 'high'))
   order by c.level = 'high' desc, c.diff_pct desc nulls last, c.score desc nulls last,
            c.created_at desc, c.id desc
   limit 1
$$;

-- ---------------------------------------------------------------------------
-- match_cards: 20261129120100's, plus color and color_method last (create or
-- replace only appends columns).
-- ---------------------------------------------------------------------------

create or replace view public.match_cards with (security_invoker = true) as
select m.id                              as match_id,
       m.search_profile_id,
       sp.name                           as profile_name,
       sp.user_id,
       m.listing_id,
       m.score,
       m.level,
       m.is_backfill,
       m.generated_at,
       m.price_ref,
       m.red_flags,
       l.title,
       l.make,
       l.model,
       l.trim,
       l.year,
       l.price,
       l.currency,
       l.price_usd,
       l.mileage_km,
       l.transmission,
       l.fuel,
       l.location_text,
       l.source,
       l.images,
       l.published_at,
       l.first_seen_at,
       l.status                          as listing_status,
       l.probable_repost_of,
       coalesce(i.status, 'new')         as status,
       coalesce(i.saved, false)          as saved,
       i.rejection_reason,
       l.price_published,
       l.price_published_currency,
       l.price_source,
       l.description_facts -> 'price_check' ->> 'effective_kind' as price_kind,
       coalesce((l.description_facts -> 'financing' ->> 'offered')::boolean, false) as financing_offered,
       l.body_type,
       i.note,
       -- Only while the search has the strict filter: a seller type and the
       -- owner's seller_filter as last synced. Short-circuits for the rest.
       case when m.match_reasons -> 'seller' ->> 'result' = 'unknown'
                 and m.match_reasons -> 'seller' ->> 'kind' = 'hard'
                 and jsonb_typeof(sp.filters -> 'seller_types') = 'array'
                 and sp.filters -> 'seller_types' <> '[]'::jsonb
            then coalesce((select p.seller_filter_access from public.profiles p where p.id = sp.user_id), false)
            else false end               as seller_unknown,
       l.color,
       l.attributes -> '_color' ->> 'method' as color_method
  from public.matches m
  join public.search_profiles sp on sp.id = m.search_profile_id
  join public.listings l on l.id = m.listing_id
  left join public.user_listing_interactions i
    on i.user_id = sp.user_id and i.listing_id = m.listing_id;

-- ---------------------------------------------------------------------------
-- color_vision_runs: the vision pass's daily budget
-- ---------------------------------------------------------------------------

create table if not exists public.color_vision_runs (
  id           bigint generated always as identity primary key,
  listing_id   bigint references public.listings(id) on delete set null,
  started_at   timestamptz not null default now(),
  finished_at  timestamptz,
  photos       smallint not null check (photos between 0 and 10),
  model        text,
  result       text,
  error        text
);

create index if not exists color_vision_runs_started_at_idx on public.color_vision_runs (started_at);

comment on table public.color_vision_runs is
  'Each vision call for a listing''s color (docs/PLAN_FILTRO_COLOR.md); the rolling 24 h count is capped '
  'by app_config.color_vision.daily_cap. A reservation counts even if the call fails or the process dies.';

alter table public.color_vision_runs enable row level security;
revoke all on public.color_vision_runs from public, anon, authenticated;
grant all on public.color_vision_runs to service_role;

-- ---------------------------------------------------------------------------
-- app_config
-- ---------------------------------------------------------------------------

insert into public.app_config (key, value) values
  ('color_vision', '{"enabled": true, "daily_cap": 3000, "min_confidence": "media", "skip_sources": []}')
on conflict (key) do nothing;

-- ---------------------------------------------------------------------------
-- Grants: the helpers are server-only, like search_body_types; the worker
-- can ask them too.
-- ---------------------------------------------------------------------------

revoke all on function public.search_colors(jsonb), public.listing_color_fits(text, jsonb, text[])
  from public, anon, authenticated;
grant execute on function public.search_colors(jsonb), public.listing_color_fits(text, jsonb, text[])
  to service_role;

notify pgrst, 'reload schema';

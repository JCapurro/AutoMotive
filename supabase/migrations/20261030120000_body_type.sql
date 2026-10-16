-- Carrocería (docs/CARROCERIA.md). Juan asked for it on 15/10/2026: the body
-- type as a search filter, and for Particular (pass), Pro and admins a search
-- without a model, only by body type ("cualquier SUV hasta USD 20.000").
--
-- * listings.body_type: the worker's normalized code (normalization/body_type.py),
--   null = unknown. listings.attributes._body_type says how it was decided.
-- * vehicle_catalog.body_types: the model's possible bodies, most common first;
--   one value = certain. The data comes in 20261030120100_catalog_body_types.sql.
-- * crawl_targets.body_type: a target per (source, body type), without make
--   or model; the unique key becomes (source, make, model, body_type).
-- * match_cards (and search_results, recent_opportunities) show body_type.
-- * Plan feature model_less_search (pass and pro; admins through plan_feature),
--   enforced twice: the search_profiles trigger when saving and
--   search_access_active when crawling, matching and alerting.
-- * preview_search counts model-less searches with matching.py's rule: an
--   unknown body type fails without a model and doesn't discard within one.
-- * Reactivation skips model-less searches the account can't have; the count
--   after expiry (2.5) leaves them out.
--
-- The codes, in the order the web shows them: sedan, hatchback, suv, pickup,
-- rural, monovolumen, coupe, convertible, utilitario. No code is part of
-- another (matching.py's _choice compares with `in`).

-- ---------------------------------------------------------------------------
-- listings
-- ---------------------------------------------------------------------------

alter table public.listings add column body_type text;
alter table public.listings add constraint listings_body_type_check
  check (body_type in ('sedan', 'hatchback', 'suv', 'pickup', 'rural', 'monovolumen', 'coupe',
                       'convertible', 'utilitario')) not valid;
alter table public.listings validate constraint listings_body_type_check;
comment on column public.listings.body_type is
  'Body type code (docs/CARROCERIA.md), null = unknown. Decided by the worker from the title and '
  'version, the source''s structured value, the doors and vehicle_catalog.body_types; '
  'attributes._body_type = {"method", "raw"} says how.';

-- Model-less rematch and preview: active listings of some body types, newest first.
create index listings_body_type_active_idx on public.listings (body_type, last_seen_at desc)
  where status = 'active' and body_type is not null;

-- ---------------------------------------------------------------------------
-- vehicle_catalog and crawl_targets
-- ---------------------------------------------------------------------------

alter table public.vehicle_catalog
  add column body_types text[] not null default '{}'
    constraint vehicle_catalog_body_types_check
    check (body_types <@ array['sedan', 'hatchback', 'suv', 'pickup', 'rural', 'monovolumen', 'coupe',
                               'convertible', 'utilitario']::text[]);
comment on column public.vehicle_catalog.body_types is
  'The model''s possible body types (docs/CARROCERIA.md), most common first; one value = certain. '
  'Empty = unknown.';

alter table public.crawl_targets
  add column body_type text
    constraint crawl_targets_body_type_check
    check (body_type in ('sedan', 'hatchback', 'suv', 'pickup', 'rural', 'monovolumen', 'coupe',
                         'convertible', 'utilitario'));
comment on column public.crawl_targets.body_type is
  'A target by body type, for model-less searches (docs/CARROCERIA.md): make and model null. '
  'Null for model and inventory targets.';
-- The listings a target by body type's prefilter dropped on its last complete
-- run, for sources without a publication date (Kavak): if one of them is kept
-- later (a wider search, a price cut, the quote), it is old stock, not news.
alter table public.crawl_targets
  add column prefilter_rejected text[] not null default '{}';
comment on column public.crawl_targets.prefilter_rejected is
  'External ids the prefilter of a target by body type dropped (pipeline/crawl.py): stored later, '
  'they are backfill. Only for sources without a publication date.';
alter table public.crawl_targets
  drop constraint crawl_targets_unique,
  add constraint crawl_targets_unique unique nulls not distinct (source, make, model, body_type);

-- ---------------------------------------------------------------------------
-- match_cards: body_type last (create or replace only appends columns);
-- search_results and recent_opportunities return setof match_cards and get it too.
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
       l.body_type
  from public.matches m
  join public.search_profiles sp on sp.id = m.search_profile_id
  join public.listings l on l.id = m.listing_id
  left join public.user_listing_interactions i
    on i.user_id = sp.user_id and i.listing_id = m.listing_id;

-- ---------------------------------------------------------------------------
-- app_config
-- ---------------------------------------------------------------------------

-- The plan feature, next to the limits (docs/PLANES_2026-10.md, «Funciones por plan»).
update public.app_config
   set value = jsonb_set(jsonb_set(value, '{pass}', coalesce(value->'pass', '{}') || '{"model_less_search": true}'),
                         '{pro}', coalesce(value->'pro', '{}') || '{"model_less_search": true}')
 where key = 'plan_limits';

-- Which sources get a target per body type, and how often they run. Each
-- collector also declares the body types it can search (BODY_TYPES).
insert into public.app_config (key, value) values
  ('body_type_targets', '{"sources": ["mercadolibre", "kavak"], "interval_seconds": 1800}')
on conflict (key) do nothing;

-- ---------------------------------------------------------------------------
-- Model-less searches
-- ---------------------------------------------------------------------------

-- A search without make and without model: only by body type. make or model
-- is absent when missing, JSON null or a string of only ASCII whitespace (an
-- explicit set, not the locale's [[:space:]]); any other value (a
-- non-blank string, or a number, boolean, array… that search_filters_problem
-- rejects) counts as present. intelligence/matching.py model_less() is the
-- same rule, and test_body_type_postgres checks both over the same inputs.
create function public.search_is_model_less(p_filters jsonb) returns boolean
language sql immutable set search_path = '' as $$
  select bool_and(case jsonb_typeof(p_filters->k)
                    when 'string' then btrim(p_filters->>k, E' \t\n\r\f\x0b') = ''
                    when 'null' then true
                    else p_filters->k is null
                  end)
    from unnest(array['make', 'model']) k
$$;

-- Why `filters` has a malformed vehicle or body type, or null: make and model
-- must be absent, null or strings, and body_types absent, null or an array of
-- strings. Otherwise the database and the worker could read the same row
-- differently (a model-less search past the plan check, or a make of `false`).
create function public.search_filters_problem(p_filters jsonb) returns text
language sql immutable set search_path = '' as $$
  select case
    when coalesce(jsonb_typeof(p_filters->'make'), 'null') not in ('null', 'string')
      or coalesce(jsonb_typeof(p_filters->'model'), 'null') not in ('null', 'string')
      or coalesce(jsonb_typeof(p_filters->'body_types'), 'null') not in ('null', 'array')
      or (jsonb_typeof(p_filters->'body_types') = 'array'
          and exists (select 1 from jsonb_array_elements(p_filters->'body_types') b
                       where jsonb_typeof(b) <> 'string'))
    then 'invalid_filters'
  end
$$;

-- filters.body_types as an array, or null when there are none.
create function public.search_body_types(p_filters jsonb) returns text[]
language sql immutable set search_path = '' as $$
  select case when jsonb_typeof(p_filters->'body_types') = 'array'
                   and jsonb_array_length(p_filters->'body_types') > 0
              then array(select jsonb_array_elements_text(p_filters->'body_types')) end
$$;

-- Why an enabled search with these filters can't be saved for the account,
-- or null. Only model-less searches have rules: the plan feature (while
-- plan_limits.enforced; the pilot only measures it, like max_profiles), one
-- or more known body types (an unknown body type never matches them) and a
-- max price (it bounds what their targets keep). The text is the error the
-- trigger raises.
create function public.model_less_search_problem(p_user uuid, p_filters jsonb) returns text
language sql stable security definer set search_path = '' as $$
  select case
    when not public.search_is_model_less(p_filters) then null
    when coalesce((public.plan_limits_for(p_user)->>'enforced')::boolean, true)
         and not public.plan_feature(p_user, 'model_less_search') then 'plan_feature_unavailable'
    when public.search_body_types(p_filters) is null
         or not public.search_body_types(p_filters)
                <@ array['sedan', 'hatchback', 'suv', 'pickup', 'rural', 'monovolumen', 'coupe',
                         'convertible', 'utilitario']::text[] then 'search_needs_model_or_body_type'
    when coalesce(case when btrim(p_filters->>'price_max') ~ '^[0-9]+(\.[0-9]+)?$'
                       then btrim(p_filters->>'price_max')::numeric end, 0) <= 0 then 'search_needs_max_price'
  end
$$;

-- The final check when saving (the web asks my_plan_feature first). Filters
-- with a malformed vehicle or body type are rejected (invalid_filters). Then
-- searches with a model, inactive ones and ownership changes (link_telegram;
-- expire_commercial_access reconciles) pass. Triggers fire by name, so this
-- one runs before search_profiles_enforce_plan_frequency and _limits: a
-- rejected search reports this error, not the plan limits'.
create function public.enforce_plan_features() returns trigger
language plpgsql security definer set search_path = '' as $$
declare
  v_problem text;
  v_access  jsonb;
begin
  if tg_op = 'UPDATE' and old.user_id <> new.user_id then return new; end if;
  -- Malformed make, model or body_types, enabled or not: enabling it later
  -- doesn't touch filters.
  if (tg_op = 'INSERT' or new.filters is distinct from old.filters)
     and public.search_filters_problem(new.filters) is not null then
    raise exception 'invalid_filters' using errcode = '22023';
  end if;
  if not new.enabled then return new; end if;
  if not public.search_is_model_less(new.filters) then return new; end if;
  v_problem := public.model_less_search_problem(new.user_id, new.filters);
  if v_problem is not null then
    raise exception '%', v_problem
      using errcode = case when v_problem = 'plan_feature_unavailable' then '42501' else '22023' end;
  end if;
  -- The pilot lets it through; measure it like enforce_plan_limits does, when
  -- the search starts running without a model (not on every later edit).
  if not public.plan_feature(new.user_id, 'model_less_search')
     and (tg_op = 'INSERT' or not old.enabled or not public.search_is_model_less(old.filters)) then
    v_access := public.plan_limits_for(new.user_id);
    insert into public.events (user_id, name, props)
    values (new.user_id, 'plan_limit_hit', jsonb_build_object(
      'limit', 'model_less_search', 'plan', v_access->>'plan', 'search_profile_id', new.id,
      'enforced', (v_access->>'enforced')::boolean));
  end if;
  return new;
end $$;

create trigger search_profiles_enforce_plan_features
  before insert or update of enabled, filters, user_id on public.search_profiles
  for each row execute function public.enforce_plan_features();

-- 20261007's, plus: a model-less search needs the plan feature. It stops
-- being crawled, matched and alerted, and expire_commercial_access pauses it
-- (search_paused_by_plan). Not enforced in the pilot, like max_profiles.
create or replace function public.search_access_active(p_search bigint) returns boolean
language sql stable security definer set search_path = '' as $$
  select coalesce((select sp.enabled and public.commercial_access_active(sp.user_id)
    and (not (a.v->>'enforced')::boolean or
      (select count(*) from public.search_profiles other
        where other.user_id = sp.user_id and other.enabled and other.id <= sp.id)
      <= coalesce((a.v->'limits'->>'max_profiles')::int, 2147483647))
    and case when not (a.v->>'enforced')::boolean or not public.search_is_model_less(sp.filters) then true
             else public.plan_feature(sp.user_id, 'model_less_search') end
    from public.search_profiles sp cross join lateral (select public.plan_limits_for(sp.user_id) v) a
    where sp.id = p_search), false)
$$;

-- ---------------------------------------------------------------------------
-- preview_search: 20261001's, plus body types
-- ---------------------------------------------------------------------------

-- Active listings of the last 30 days (the backfill window) that pass the
-- hard filters of `p_filters` (sección 4.3 shape). As in matching.py a value
-- the listing doesn't inform never discards it, prices are compared after
-- converting currencies (price_usd, or the latest quote) and partial prices
-- are left out. Two shapes: a make (and maybe a model), or no make and no
-- model with body_types. body_types, like matching.py: within a model an
-- unknown body type passes; without one it fails, or "cualquier SUV" would
-- count every listing without the data. Returns {"count": n, "sample": [up to
-- 3 listings, newest first]}.
-- security definer only to read the latest fx rate; it returns nothing a
-- signed-in user can't already read from listings, so the model-less count
-- isn't gated by the plan (the web offers it with my_plan_feature).
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
                then array(select lower(jsonb_array_elements_text(p_filters->'trims'))) end as strict_trims
  ),
  fx as (
    select rate from public.fx_rates order by date desc, (kind = 'blue') desc limit 1
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
       and (f.sources is null or p.source = any (f.sources))
       and (f.strict_trims is null or p.trim is null
            or exists (select 1 from unnest(f.strict_trims) t where position(t in lower(p.trim)) > 0))
       and (p_radius_km is null or p_origin_lat is null or p_origin_lon is null
            or p.lat is null or p.lon is null
            or public.haversine_km(p_origin_lat, p_origin_lon, p.lat, p.lon) <= p_radius_km)
  ),
  sample as (
    select h.id, h.title, h.make, h.model, h.trim, h.year, h.price, h.currency, h.mileage_km,
           h.location_text, h.source, h.first_seen_at, h.body_type
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
-- Reactivation and the count after expiry (2.5)
-- ---------------------------------------------------------------------------

-- 20261024's, plus: skip the paused searches the trigger would reject (a
-- model-less one without the plan feature), so one of them doesn't undo the
-- whole reactivation.
create or replace function public.reactivate_paused_searches(p_user uuid) returns integer
language plpgsql security definer set search_path = '' as $$
declare
  v_room integer;
  v_count integer := 0;
begin
  begin
    select coalesce((a.v->'limits'->>'max_profiles')::integer, 0) - coalesce((a.v->>'active_searches')::integer, 0)
      into v_room from (select public.plan_limits_for(p_user) v) a;
    if coalesce(v_room, 0) > 0 then
      with paused as (
        select sp.id
          from public.search_profiles sp
          join public.events e on e.user_id = sp.user_id and e.name = 'search_paused_by_plan'
                              and e.props->>'search_profile_id' = sp.id::text
         where sp.user_id = p_user and not sp.enabled
           and public.model_less_search_problem(p_user, sp.filters) is null
         group by sp.id
         order by max(e.created_at) desc, sp.id desc
         limit v_room
      )
      update public.search_profiles sp set enabled = true from paused where sp.id = paused.id;
      get diagnostics v_count = row_count;
      if v_count > 0 then
        insert into public.events (user_id, name, props)
        values (p_user, 'searches_reactivated', jsonb_build_object('count', v_count));
      end if;
    end if;
  exception when others then
    raise warning 'reactivate_paused_searches: % (user %)', sqlerrm, p_user;
    v_count := 0;
  end;
  begin
    insert into public.events (user_id, name, props)
    select p_user, 'reactivated_from_count_email',
           jsonb_build_object('email_id', e.id, 'stage', e.payload->'stage', 'clicked', e.clicked_at is not null,
                              'days_after_email', extract(day from now() - e.sent_at)::integer)
      from (select * from public.lifecycle_emails le
             where le.user_id = p_user and le.kind = 'count_after_expiry' and le.status = 'sent'
             order by le.sent_at desc limit 1) e
     where e.sent_at > now() - interval '30 days'
       and not exists (select 1 from public.events r
                        where r.user_id = p_user and r.name = 'reactivated_from_count_email'
                          and r.props->>'email_id' = e.id::text);
  exception when others then
    raise warning 'reactivated_from_count_email: % (user %)', sqlerrm, p_user;
  end;
  return v_count;
end $$;

-- 20261024's, without model-less searches: Juan approved crawling the
-- expired searches' models once a day, not a whole body type.
create or replace function public.count_after_expiry_searches()
returns table (search_profile_id bigint, user_id uuid, ended_at timestamptz)
language sql stable security definer set search_path = '' as $$
  select sp.id, sp.user_id, a.ended_at
    from public.profiles p
    cross join lateral (select public.count_after_expiry_end(p.id) as ended_at) a
    join public.search_profiles sp on sp.user_id = p.id and not sp.enabled
   where public.lifecycle_kind_on('count_after_expiry')
     -- Cheap first: a pass or a trial that ended in the last 22 days.
     and ((p.plan = 'pass' and p.plan_expires_at > now() - interval '22 days')
          or p.free_trial_started_at > now() - interval '22 days' - interval '72 hours')
     and a.ended_at > now() - interval '22 days'
     and not public.search_is_model_less(sp.filters)
     and exists (select 1 from public.events e
                  where e.user_id = p.id and e.name = 'search_paused_by_plan'
                    and e.props->>'search_profile_id' = sp.id::text
                    and e.created_at >= a.ended_at)
$$;

-- ---------------------------------------------------------------------------
-- record_purchase: 20261001's, with the body type in the vehicle snapshot
-- ---------------------------------------------------------------------------

create or replace function public.record_purchase(
  p_listing_id        bigint,
  p_search_profile_id bigint  default null,
  p_price             numeric default null,
  p_currency          text    default null,
  p_date              date    default null
) returns bigint
language plpgsql
security invoker
set search_path = ''
as $$
declare
  v_user     uuid := auth.uid();
  v_listing  public.listings;
  v_profile  bigint;
  v_id       bigint;
  v_date     date := coalesce(p_date, (now() at time zone 'America/Argentina/Buenos_Aires')::date);
  v_vehicle  jsonb;
  v_signup   timestamptz;
  v_search   timestamptz;
begin
  if v_user is null then
    raise exception 'not authenticated' using errcode = '42501';
  end if;
  select * into v_listing from public.listings where id = p_listing_id;
  if not found then
    raise exception 'listing % not found', p_listing_id using errcode = 'P0002';
  end if;
  -- Another user's search (invisible through RLS) is dropped, not trusted.
  select id, created_at into v_profile, v_search
    from public.search_profiles where id = p_search_profile_id;

  v_vehicle := jsonb_build_object(
    'title', v_listing.title, 'make', v_listing.make, 'model', v_listing.model,
    'trim', v_listing.trim, 'year', v_listing.year, 'mileage_km', v_listing.mileage_km,
    'transmission', v_listing.transmission, 'fuel', v_listing.fuel, 'body_type', v_listing.body_type,
    'price', v_listing.price, 'currency', v_listing.currency, 'price_usd', v_listing.price_usd,
    'source', v_listing.source, 'url', v_listing.url, 'location_text', v_listing.location_text,
    'image', v_listing.images->0);

  select id into v_id from public.owned_vehicles
   where user_id = v_user and listing_id = p_listing_id
   order by id limit 1;
  if v_id is null then
    insert into public.owned_vehicles (user_id, listing_id, search_profile_id, vehicle,
                                       purchase_price, purchase_currency, purchase_date)
    values (v_user, p_listing_id, v_profile, v_vehicle, p_price, p_currency, v_date)
    returning id into v_id;
  else
    update public.owned_vehicles
       set search_profile_id = coalesce(v_profile, search_profile_id), vehicle = v_vehicle,
           purchase_price = p_price, purchase_currency = p_currency, purchase_date = v_date
     where id = v_id;
  end if;

  insert into public.user_listing_interactions (user_id, listing_id, status)
  values (v_user, p_listing_id, 'purchased')
  on conflict (user_id, listing_id)
    do update set status = 'purchased', rejection_reason = null;

  select created_at into v_signup from public.profiles where id = v_user;
  insert into public.events (user_id, name, props) values
    (v_user, 'listing_status_changed',
     jsonb_build_object('listing_id', p_listing_id, 'status', 'purchased', 'via', 'web')),
    (v_user, 'vehicle_purchased', jsonb_build_object(
       'listing_id', p_listing_id, 'search_profile_id', v_profile, 'owned_vehicle_id', v_id,
       'price', p_price, 'currency', p_currency, 'date', v_date,
       'days_using_automotive', floor(extract(epoch from now() - v_signup) / 86400),
       'days_since_search_created',
         case when v_search is not null then floor(extract(epoch from now() - v_search) / 86400) end));
  return v_id;
end;
$$;

-- ---------------------------------------------------------------------------
-- Grants: the helpers are server-only; the worker can ask them too.
-- ---------------------------------------------------------------------------

revoke all on function public.search_is_model_less(jsonb), public.search_body_types(jsonb),
  public.search_filters_problem(jsonb), public.model_less_search_problem(uuid, jsonb),
  public.enforce_plan_features()
  from public, anon, authenticated;
grant execute on function public.search_is_model_less(jsonb), public.search_body_types(jsonb),
  public.search_filters_problem(jsonb), public.model_less_search_problem(uuid, jsonb) to service_role;

notify pgrst, 'reload schema';

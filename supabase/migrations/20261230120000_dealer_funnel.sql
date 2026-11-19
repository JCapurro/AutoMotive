-- Agencias, fase 2: medición del embudo del canal de venta
-- (docs/PLAN_AGENCIAS_STOCK_Y_CANAL.md §3 «Nosotros» y §5; diseño en
-- docs/superpowers/specs/2026-11-18-agencias-design.md, §12).
--
-- Requiere 20261228120000_dealer_program.sql. No agrega FK a `listings` ni columnas a
-- `listings`: no hace falta parar el worker. Crea un trigger de sentencia en `matches`
-- (toma un lock corto sobre la tabla al crearlo). Aplicar a mano según la memoria de
-- migraciones de producción, con OK de Juan. Nada de esto se aplica en esta rama.
--
-- What it adds:
-- * dealer_match_log: the first time each (dealer listing, search) pair got a
--   match. matches rows of a dealer car are deleted when it is hidden (sold,
--   reserved, unconfirmed, channel off) and by the nightly rescore, so the
--   funnel cannot be rebuilt from matches. Filled by a statement trigger on
--   matches inserts (only rows whose listing has dealer_id; a common listing
--   costs one primary-key lookup in the join). No FK to listings or
--   search_profiles: the history outlives them, like admin_search_observations.
-- * dealer_leads.furthest_status: the furthest step a lead reached (new <
--   contacted < reserved < sold), kept by a trigger, so a lead that was
--   contacted and then marked «No avanzó» still counts as contacted.
-- * dealer_sales: the declared sale. When the agency marks a lead «Compró» or a
--   car as sold, the panel asks with one click whether the sale came through
--   Ese Auto; dealer_declare_sale() stores the answer (one per car, or per lead
--   when the lead has no car any more).
-- * dealer_funnel(p_start, p_end, p_dealer): the raw funnel of one dealer or
--   of all of them (internal, service role). admin_dealer_funnel(p_start,
--   p_end): per dealer and in total, for /admin/agencias (service role only:
--   the admin page reads it with the admin client after requireAdmin).
--   Aggregates only: no buyer's name, phone or id leaves these functions.
-- * my_dealer_reach(): the agency's own month («este mes tus autos llegaron a
--   N personas y recibiste M consultas»), people rounded to "few" under
--   dealer_program().demand_min_count (never under 3) in SQL; plus the sold
--   cars and leads still waiting for the «¿vino por Ese Auto?» answer.
--
-- Definitions (the same in the admin and the agency views):
-- * An alert of a dealer car = a notification row (not the digest container)
--   delivered on a channel (sent, or carried by a digest that was sent), or a
--   car listed in the items of a sent digest, for a listing linked to a dealer
--   stock item, delivered after the item was created. One per (person, car).
-- * People reached = distinct users behind those alerts. Admin accounts and the
--   dealer's own members are left out of matches, alerts and people.
-- * A lead counts by created_at; its steps by furthest_status; «No avanzó» is
--   the current status 'lost'. A declared sale counts by declared_at, only
--   while its car (or its lead) is still sold.
--
-- Rollback: drop function public.my_dealer_reach(), public.admin_dealer_funnel(timestamptz, timestamptz),
-- public.dealer_funnel(timestamptz, timestamptz, bigint), public.dealer_declare_sale(bigint, bigint, boolean);
-- drop trigger matches_dealer_log on public.matches; drop function public.dealer_log_matches();
-- drop trigger dealer_leads_furthest on public.dealer_leads; drop function public.dealer_lead_furthest();
-- alter table public.dealer_leads drop column furthest_status; drop table public.dealer_sales,
-- public.dealer_match_log.

-- ---------------------------------------------------------------------------
-- 1. First match of each dealer car with each search
-- ---------------------------------------------------------------------------
create table public.dealer_match_log (
  listing_id        bigint not null,
  search_profile_id bigint not null,
  dealer_id         bigint not null references public.dealers (id) on delete cascade,
  user_id           uuid not null references public.profiles (id) on delete cascade,
  first_matched_at  timestamptz not null default now(),
  primary key (listing_id, search_profile_id)
);
create index dealer_match_log_dealer_idx on public.dealer_match_log (dealer_id, first_matched_at);

alter table public.dealer_match_log enable row level security;
revoke all on public.dealer_match_log from public, anon, authenticated;
grant all on public.dealer_match_log to service_role;

create function public.dealer_log_matches() returns trigger
language plpgsql security definer set search_path = '' as $$
begin
  insert into public.dealer_match_log (listing_id, search_profile_id, dealer_id, user_id)
  select n.listing_id, n.search_profile_id, l.dealer_id, sp.user_id
    from new_rows n
    join public.listings l on l.id = n.listing_id
    join public.search_profiles sp on sp.id = n.search_profile_id
   where l.dealer_id is not null
  on conflict (listing_id, search_profile_id) do nothing;
  return null;
end $$;
revoke execute on function public.dealer_log_matches() from public, anon, authenticated;

create trigger matches_dealer_log after insert on public.matches
  referencing new table as new_rows
  for each statement execute function public.dealer_log_matches();

-- Matches of dealer cars that exist today (none in production: nothing to lose).
insert into public.dealer_match_log (listing_id, search_profile_id, dealer_id, user_id, first_matched_at)
select m.listing_id, m.search_profile_id, l.dealer_id, sp.user_id, m.generated_at
  from public.matches m
  join public.listings l on l.id = m.listing_id and l.dealer_id is not null
  join public.search_profiles sp on sp.id = m.search_profile_id
on conflict do nothing;

-- ---------------------------------------------------------------------------
-- 2. The furthest step of a lead
-- ---------------------------------------------------------------------------
alter table public.dealer_leads
  add column furthest_status text not null default 'new'
    check (furthest_status in ('new', 'contacted', 'reserved', 'sold'));
update public.dealer_leads set furthest_status = status where status in ('contacted', 'reserved', 'sold');

create function public.dealer_lead_furthest() returns trigger
language plpgsql set search_path = '' as $$
declare
  v_rank constant text[] := array['new', 'contacted', 'reserved', 'sold'];
begin
  if new.status = any (v_rank)
     and array_position(v_rank, new.status) > array_position(v_rank, coalesce(new.furthest_status, 'new')) then
    new.furthest_status := new.status;
  end if;
  return new;
end $$;
revoke execute on function public.dealer_lead_furthest() from public, anon, authenticated;

create trigger dealer_leads_furthest before insert or update of status on public.dealer_leads
  for each row execute function public.dealer_lead_furthest();

-- The agency reads its own leads through RLS: the new column too.
grant select (furthest_status) on public.dealer_leads to authenticated;

-- ---------------------------------------------------------------------------
-- 3. Declared sales
-- ---------------------------------------------------------------------------
create table public.dealer_sales (
  id           bigint generated always as identity primary key,
  dealer_id    bigint not null references public.dealers (id) on delete cascade,
  item_id      bigint references public.dealer_stock_items (id) on delete cascade,
  lead_id      bigint references public.dealer_leads (id) on delete set null,
  via_ese_auto boolean not null,
  declared_by  uuid references public.profiles (id) on delete set null,
  declared_at  timestamptz not null default now(),
  check (item_id is not null or lead_id is not null)
);
create unique index dealer_sales_item_once on public.dealer_sales (item_id) where item_id is not null;
create unique index dealer_sales_lead_once on public.dealer_sales (lead_id) where item_id is null and lead_id is not null;
create index dealer_sales_dealer_idx on public.dealer_sales (dealer_id, declared_at);

alter table public.dealer_sales enable row level security;
revoke all on public.dealer_sales from public, anon, authenticated;
grant all on public.dealer_sales to service_role;
grant select on public.dealer_sales to authenticated;
create policy "dealer_sales: members read" on public.dealer_sales
  for select to authenticated using (public.is_dealer_member(dealer_id));

-- «¿La venta vino por Ese Auto?». A lead marked «Compró» (p_lead_id) or a car
-- marked sold (p_item_id); with a lead, its car is the one declared. Asking
-- again replaces the answer. Errors: dealer_program_off, not_signed_in,
-- not_member, invalid_sale, lead_not_found, item_not_found, not_sold.
create function public.dealer_declare_sale(p_item_id bigint default null, p_lead_id bigint default null,
                                           p_via_ese_auto boolean default null)
returns void
language plpgsql volatile security definer set search_path = '' as $$
declare
  v_dealer bigint := public.dealer_require_member();
  v_item   bigint := p_item_id;
  v_status text;
  v_id     bigint;
begin
  if p_via_ese_auto is null or (p_item_id is null and p_lead_id is null) then
    raise exception 'invalid_sale' using errcode = 'P0001';
  end if;
  if p_lead_id is not null then
    select ld.item_id, ld.status into v_item, v_status
      from public.dealer_leads ld where ld.id = p_lead_id and ld.dealer_id = v_dealer;
    if not found then
      raise exception 'lead_not_found' using errcode = 'P0001';
    end if;
    if v_status <> 'sold' then
      raise exception 'not_sold' using errcode = 'P0001';
    end if;
    if p_item_id is not null and v_item is distinct from p_item_id then
      raise exception 'invalid_sale' using errcode = 'P0001';
    end if;
  else
    select i.status into v_status
      from public.dealer_stock_items i where i.id = p_item_id and i.dealer_id = v_dealer;
    if not found then
      raise exception 'item_not_found' using errcode = 'P0001';
    end if;
    if v_status <> 'sold' then
      raise exception 'not_sold' using errcode = 'P0001';
    end if;
  end if;

  if v_item is not null then
    select s.id into v_id from public.dealer_sales s where s.item_id = v_item;
  else
    select s.id into v_id from public.dealer_sales s where s.item_id is null and s.lead_id = p_lead_id;
  end if;
  if v_id is null then
    insert into public.dealer_sales (dealer_id, item_id, lead_id, via_ese_auto, declared_by)
    values (v_dealer, v_item, p_lead_id, p_via_ese_auto, (select auth.uid()));
  else
    update public.dealer_sales s
       set via_ese_auto = p_via_ese_auto, lead_id = coalesce(p_lead_id, s.lead_id),
           declared_by = (select auth.uid()), declared_at = now()
     where s.id = v_id;
  end if;
end $$;
revoke execute on function public.dealer_declare_sale(bigint, bigint, boolean) from public, anon;
grant execute on function public.dealer_declare_sale(bigint, bigint, boolean) to authenticated, service_role;

-- ---------------------------------------------------------------------------
-- 4. The funnel
-- ---------------------------------------------------------------------------

-- Raw funnel of one dealer (p_dealer) or of all (null) for [p_start, p_end).
-- Internal: service role only. Counts, never a buyer.
create function public.dealer_funnel(p_start timestamptz, p_end timestamptz, p_dealer bigint default null)
returns jsonb
language sql stable security definer set search_path = '' as $$
  with d as (
    select dl.id from public.dealers dl where p_dealer is null or dl.id = p_dealer
  ), outsiders as (                      -- admins and the dealers' own members are not buyers
    select p.id as user_id, null::bigint as dealer_id from public.profiles p where p.role = 'admin'
    union all
    select m.user_id, m.dealer_id from public.dealer_members m
  ), items as (
    select i.id, i.dealer_id, i.status, i.listing_id, i.created_at,
           l.source, l.dealer_id as l_dealer, l.dealer_status, l.dealer_confirmed_at
      from public.dealer_stock_items i
      join d on d.id = i.dealer_id
      left join public.listings l on l.id = i.listing_id
  ), stock as (
    select count(*) filter (where status <> 'archived') as stock,
           count(*) filter (where status = 'available' and listing_id is not null
                              and public.dealer_listing_hidden(source, l_dealer, dealer_status, dealer_confirmed_at) is null)
             as visible,
           count(*) filter (where created_at >= p_start and created_at < p_end) as loaded
      from items
  ), matched as (
    select count(distinct ml.listing_id) as cars, count(distinct ml.search_profile_id) as searches
      from public.dealer_match_log ml
      join d on d.id = ml.dealer_id
     where ml.first_matched_at >= p_start and ml.first_matched_at < p_end
       and not exists (select 1 from outsiders o
                        where o.user_id = ml.user_id and (o.dealer_id is null or o.dealer_id = ml.dealer_id))
  ), delivered as (                      -- (person, listing, when) of every alert delivered in the window
    select n.user_id, n.listing_id, coalesce(n.sent_at, dg.sent_at) as at
      from public.notifications n
      left join public.notifications dg on dg.id = n.digested_in
     where n.kind <> 'digest'
       and n.listing_id in (select listing_id from items where listing_id is not null)
       and (n.status = 'sent' or (n.status = 'digest' and dg.status = 'sent'))
    union all
    select dg.user_id, (it.item ->> 'listing_id')::bigint, dg.sent_at
      from public.notifications dg
     cross join lateral jsonb_array_elements(
             case when jsonb_typeof(dg.payload -> 'items') = 'array' then dg.payload -> 'items' else '[]'::jsonb end) it(item)
     where dg.kind = 'digest' and dg.status = 'sent'
       and dg.sent_at >= p_start and dg.sent_at < p_end
       and jsonb_typeof(it.item -> 'listing_id') = 'number'
  ), alerts as (
    select distinct dv.user_id, dv.listing_id
      from delivered dv
      join items i on i.listing_id = dv.listing_id
     where dv.at >= p_start and dv.at < p_end and dv.at >= i.created_at
       and not exists (select 1 from outsiders o
                        where o.user_id = dv.user_id and (o.dealer_id is null or o.dealer_id = i.dealer_id))
  ), leads as (
    select count(*) as leads,
           count(*) filter (where ld.furthest_status in ('contacted', 'reserved', 'sold')) as contacted,
           count(*) filter (where ld.furthest_status in ('reserved', 'sold')) as reserved,
           count(*) filter (where ld.furthest_status = 'sold') as sold,
           count(*) filter (where ld.status = 'lost') as lost,
           count(*) filter (where ld.status = 'new') as still_new
      from public.dealer_leads ld
      join d on d.id = ld.dealer_id
     where ld.created_at >= p_start and ld.created_at < p_end
       and not exists (select 1 from public.profiles p where p.id = ld.buyer_user_id and p.role = 'admin')
  ), sales as (
    select count(*) filter (where s.via_ese_auto) as via_ese_auto,
           count(*) filter (where not s.via_ese_auto) as elsewhere
      from public.dealer_sales s
      join d on d.id = s.dealer_id
      left join public.dealer_stock_items i on i.id = s.item_id
      left join public.dealer_leads ld on ld.id = s.lead_id
     where s.declared_at >= p_start and s.declared_at < p_end
       and (i.status = 'sold' or ld.status = 'sold')
  )
  select jsonb_build_object(
           'stock', stock.stock, 'visible', stock.visible, 'loaded', stock.loaded,
           'matched_cars', matched.cars, 'matched_searches', matched.searches,
           'alerts', (select count(*) from alerts),
           'alerted_cars', (select count(distinct listing_id) from alerts),
           'people', (select count(distinct user_id) from alerts),
           'leads', leads.leads, 'contacted', leads.contacted, 'reserved', leads.reserved,
           'sold', leads.sold, 'lost', leads.lost, 'still_new', leads.still_new,
           'sales_via_ese_auto', sales.via_ese_auto, 'sales_elsewhere', sales.elsewhere)
    from stock, matched, leads, sales
$$;
revoke execute on function public.dealer_funnel(timestamptz, timestamptz, bigint) from public, anon, authenticated;
grant execute on function public.dealer_funnel(timestamptz, timestamptz, bigint) to service_role;

-- /admin/agencias: the funnel per dealer and in total (people in the total are
-- distinct across dealers, not a sum). Up to 400 days.
create function public.admin_dealer_funnel(p_start timestamptz, p_end timestamptz) returns jsonb
language plpgsql stable security definer set search_path = '' as $$
begin
  if p_start is null or p_end is null or p_end <= p_start or p_end - p_start > interval '400 days' then
    raise exception 'invalid_funnel_range' using errcode = '22023';
  end if;
  return jsonb_build_object(
    'start', p_start, 'end', p_end,
    'total', public.dealer_funnel(p_start, p_end, null),
    'dealers', coalesce((
      select jsonb_agg(jsonb_build_object('dealer_id', dl.id, 'name', dl.name,
                                          'approved', dl.approved_at is not null, 'status', dl.status)
                       || public.dealer_funnel(p_start, p_end, dl.id)
                       order by dl.created_at, dl.id)
        from public.dealers dl), '[]'::jsonb));
end $$;
revoke execute on function public.admin_dealer_funnel(timestamptz, timestamptz) from public, anon, authenticated;
grant execute on function public.admin_dealer_funnel(timestamptz, timestamptz) to service_role;

-- The agency's month (Argentina time), from the 1st to now: people reached
-- (0, a number from demand_min_count people up, or "few") and its leads (it
-- reads them all in its inbox anyway), plus up to 5 sold cars or «Compró»
-- leads (the newest first, a car once) still without the «¿vino por Ese
-- Auto?» answer.
create function public.my_dealer_reach() returns jsonb
language plpgsql stable security definer set search_path = '' as $$
declare
  v_dealer bigint := public.dealer_require_member();
  v_start  timestamptz := date_trunc('month', now() at time zone 'America/Argentina/Buenos_Aires')
                            at time zone 'America/Argentina/Buenos_Aires';
  v_min    integer := greatest(3, (public.dealer_program() ->> 'demand_min_count')::integer);
  v_f      jsonb := public.dealer_funnel(v_start, now() + interval '1 second', v_dealer);
  v_people integer := (v_f ->> 'people')::integer;
begin
  return jsonb_build_object(
    'since', v_start,
    'min_count', v_min,
    'people', case when v_people = 0 then to_jsonb(0)
                   when v_people >= v_min then to_jsonb(v_people)
                   else to_jsonb('few'::text) end,
    'leads', (select count(*) from public.dealer_leads ld
               where ld.dealer_id = v_dealer and ld.created_at >= v_start),
    'sales_via_ese_auto', (v_f ->> 'sales_via_ese_auto')::integer,
    'pending_sales', coalesce((
      select jsonb_agg(x.p order by x.sold_at desc, x.k)
        from (
          select jsonb_build_object(
                   'item_id', i.id,
                   'lead_id', (select ld.id from public.dealer_leads ld
                                where ld.item_id = i.id and ld.status = 'sold'
                                order by ld.status_changed_at desc nulls last, ld.id desc limit 1),
                   'vehicle', coalesce(nullif(concat_ws(' ', coalesce(l.make, i.make), coalesce(l.model, i.model),
                                                        coalesce(l.year, i.year)::text), ''), 'Auto'),
                   'sold_at', i.updated_at) as p,
                 i.updated_at as sold_at, 'i' || i.id as k
            from public.dealer_stock_items i
            left join public.listings l on l.id = i.listing_id
           where i.dealer_id = v_dealer and i.status = 'sold'
             and i.updated_at >= now() - interval '90 days'
             and not exists (select 1 from public.dealer_sales s where s.item_id = i.id)
          union all
          select jsonb_build_object(
                   'item_id', ld.item_id, 'lead_id', ld.id,
                   'vehicle', coalesce(nullif(concat_ws(' ', l.make, l.model, l.year::text), ''), 'Auto'),
                   'sold_at', coalesce(ld.status_changed_at, ld.updated_at)),
                 coalesce(ld.status_changed_at, ld.updated_at), 'l' || ld.id
            from public.dealer_leads ld
            left join public.listings l on l.id = ld.listing_id
           where ld.dealer_id = v_dealer and ld.status = 'sold'
             and coalesce(ld.status_changed_at, ld.updated_at) >= now() - interval '90 days'
             -- a lead whose car is sold too is already in the first branch
             and not exists (select 1 from public.dealer_stock_items i2 where i2.id = ld.item_id and i2.status = 'sold')
             and not exists (select 1 from public.dealer_sales s
                              where s.item_id = ld.item_id or (s.item_id is null and s.lead_id = ld.id))
          order by 2 desc
          limit 5) x), '[]'::jsonb));
end $$;
revoke execute on function public.my_dealer_reach() from public, anon;
grant execute on function public.my_dealer_reach() to authenticated, service_role;

notify pgrst, 'reload schema';

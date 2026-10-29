-- X-01 · Seguimiento en la UI (docs/BACKLOG_PRODUCTO_2026-10.md, ítem X-01;
-- diseño docs/superpowers/specs/2026-10-29-x01-seguimiento-design.md, entrega b).
--
-- * match_cards: the user's note, appended last (create or replace only appends
--   columns); search_results and recent_opportunities return it too.
-- * search_results: three more filters, contacted / visit_scheduled /
--   purchased. Unlike new and all they don't require an active listing: a
--   contacted car that went offline stays in the user's follow-up.
-- * search_follow_counts: the three filters' counts. search_result_counts is
--   left alone (changing its columns needs a drop and breaks the worker's
--   test_availability_postgres.py).
-- * A technical cap of 2000 characters on the note; the product's limit is
--   app_config.listing_tracking.note_max_chars (500), applied by the web.
-- No RLS, record_purchase or v_validation_criteria change here.

-- ---------------------------------------------------------------------------
-- match_cards: 20261030120000_body_type.sql's definition plus i.note last.
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
       i.note
  from public.matches m
  join public.search_profiles sp on sp.id = m.search_profile_id
  join public.listings l on l.id = m.listing_id
  left join public.user_listing_interactions i
    on i.user_id = sp.user_id and i.listing_id = m.listing_id;

-- ---------------------------------------------------------------------------
-- search_results: 20261013120000_available_opportunities_keep_history.sql's
-- definition; only the p_filter case gains three branches.
-- ---------------------------------------------------------------------------

create or replace function public.search_results(
  p_profile_id bigint, p_filter text default 'all', p_sort text default 'score',
  p_limit integer default 50, p_offset integer default 0
) returns setof public.match_cards language sql stable security invoker set search_path = '' as $$
  with access as (select public.my_plan_snapshot() v), cap as (
    select case when (v->>'enforced')::boolean
      then coalesce((v->'limits'->>'max_visible_results')::int, 2147483647)
      else 2147483647 end n from access
  )
  select c.* from public.match_cards c
  where c.search_profile_id = p_profile_id and case p_filter
    when 'new' then c.listing_status = 'active' and c.status = 'new'
    when 'opportunities' then c.listing_status = 'active' and c.level = 'high' and c.status <> 'discarded'
    when 'saved' then c.saved when 'discarded' then c.status = 'discarded'
    when 'contacted' then c.status = 'contacted'
    when 'visit_scheduled' then c.status = 'visit_scheduled'
    when 'purchased' then c.status = 'purchased'
    else c.listing_status = 'active' and c.status <> 'discarded' end
  order by case when p_sort = 'score' then c.score end desc nulls last,
    case when p_sort = 'price' then c.price_usd end asc nulls last,
    case when p_sort = 'km' then c.mileage_km end asc nulls last,
    coalesce(c.published_at, c.first_seen_at) desc nulls last, c.listing_id desc
  limit least(greatest(coalesce(p_limit, 50), 0), greatest((select n from cap) - greatest(coalesce(p_offset, 0), 0), 0))
  offset greatest(coalesce(p_offset, 0), 0)
$$;

-- ---------------------------------------------------------------------------
-- search_follow_counts: what the results page's three new pills count.
-- Through match_cards, so it inherits RLS and the free trial's cap.
-- ---------------------------------------------------------------------------

create function public.search_follow_counts(p_profile_id bigint)
returns table (contacted_count integer, visit_scheduled_count integer, purchased_count integer)
language sql stable security invoker set search_path = '' as $$
  select (count(*) filter (where c.status = 'contacted'))::integer,
         (count(*) filter (where c.status = 'visit_scheduled'))::integer,
         (count(*) filter (where c.status = 'purchased'))::integer
    from public.match_cards c
   where c.search_profile_id = p_profile_id
$$;

revoke all on function public.search_follow_counts(bigint) from public, anon;
grant execute on function public.search_follow_counts(bigint) to authenticated;

-- ---------------------------------------------------------------------------
-- The note: a technical cap against abuse through PostgREST. NOT VALID first,
-- then VALIDATE: fails if a stored note is already longer (measure before).
-- ---------------------------------------------------------------------------

alter table public.user_listing_interactions
  add constraint user_listing_interactions_note_length
  check (note is null or char_length(note) <= 2000) not valid;
alter table public.user_listing_interactions validate constraint user_listing_interactions_note_length;

-- ---------------------------------------------------------------------------
-- app_config: the product's note limit (web/lib/config.ts, /admin/config).
-- ---------------------------------------------------------------------------

insert into public.app_config (key, value)
values ('listing_tracking', '{"note_max_chars": 500}')
on conflict (key) do nothing;

notify pgrst, 'reload schema';

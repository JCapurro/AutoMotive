-- PRO-01 · «vendedor sin dato» only while the strict filter applies
-- (docs/superpowers/specs/2026-10-31-pro01-contacto-design.md, «Respuestas de
-- Juan 02/11», 4).
--
-- match_cards.seller_unknown read only the stored match_reasons. When the
-- strict filter stops applying (a downgrade or expiry from Pro, a plan_limits
-- edit, seller_types removed from the search), the rematch rewrites the
-- reasons of active listings only: a saved listing that was sold or paused
-- kept {seller: unknown, hard} and its label. Now the label also needs the
-- search's seller_types and the owner's profiles.seller_filter_access (the
-- flag sync_seller_filter_access keeps: writes at once, time-based expiry on
-- every worker tick). plan_feature() is not callable by authenticated, and
-- the view is security_invoker; profiles RLS lets a user read their own row,
-- the only one their match_cards rows need. Same definition otherwise.
-- web/lib/seller.ts strictSellerUnknown applies the same gate.

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
            else false end               as seller_unknown
  from public.matches m
  join public.search_profiles sp on sp.id = m.search_profile_id
  join public.listings l on l.id = m.listing_id
  left join public.user_listing_interactions i
    on i.user_id = sp.user_id and i.listing_id = m.listing_id;

notify pgrst, 'reload schema';

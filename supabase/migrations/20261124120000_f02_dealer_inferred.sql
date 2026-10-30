-- F-02 paso 2 · dealer_inferred («posible agencia»)
-- (docs/BACKLOG_PRODUCTO_2026-10.md, ítem F-02; diseño
-- docs/superpowers/specs/2026-10-30-f02-vendedor-design.md; plan
-- docs/superpowers/plans/2026-10-30-f02-vendedor.md).
--
-- * listings.dealer_inferred: the seller of this listing published
--   min_listings or more cars in the same source in the last window_days and
--   still has them active (seller_listing_count, step 1), and the source does
--   not already say 'dealer'. A column apart from seller_type: its CHECK, the
--   forms and the ingest merge stay as they are, and a reingest never wipes
--   the inference. Written by the worker (db/repos/sellers.py write_groups) at
--   ingest for the groups it touched, at startup and at the anchor slot.
--   Matching, the dealer fees notice and the listing page read it through the
--   "effective seller" helpers (worker/intelligence/seller.py, web/lib/seller.ts).
-- * Seeded here from the step-1 counts, so the rescore of the SCORING_VERSION
--   bump already sees it (the worker also classifies before rescore_outdated).
-- * admin_seller_coverage: same columns, plus dealer_inferred (active listings
--   inferred) and seller_unknown_pct (active ones with no type and no inference).
--
-- Ships in the same deploy as PRO-02, which reuses this deploy's single
-- SCORING_VERSION bump (Juan, 30/10/2026). Not to be deployed alone.

alter table public.listings add column dealer_inferred boolean not null default false;

comment on column public.listings.dealer_inferred is
  'F-02: «posible agencia». seller_listing_count >= app_config.seller_classification.min_listings, '
  'the inference enabled and seller_type not already dealer. Written by the worker; never changes seller_type.';

-- The config as the worker reads it (intelligence/config.py seller_classification):
-- enabled a boolean (default true), min_listings an integer from 2 to 100 (default 6).
-- No cast runs on a value that could make it raise.
update public.listings l
   set dealer_inferred = true
  from (select coalesce((select case when jsonb_typeof(c.value -> 'enabled') = 'boolean'
                                     then (c.value ->> 'enabled')::boolean end
                           from public.app_config c
                          where c.key = 'seller_classification' and jsonb_typeof(c.value) = 'object'), true)
                 as enabled,
               coalesce((select case when jsonb_typeof(c.value -> 'min_listings') = 'number'
                                          and (c.value ->> 'min_listings') ~ '^[0-9]{1,3}$'
                                     then case when (c.value ->> 'min_listings')::int between 2 and 100
                                               then (c.value ->> 'min_listings')::int end
                                end
                           from public.app_config c
                          where c.key = 'seller_classification' and jsonb_typeof(c.value) = 'object'), 6)
                 as min_listings) cfg
 where cfg.enabled
   and l.status = 'active'
   and l.seller_listing_count >= cfg.min_listings
   and l.seller_type is distinct from 'dealer';

create or replace view public.admin_seller_coverage with (security_invoker = true) as
with cfg as (
  select coalesce((
    select case when jsonb_typeof(c.value -> 'min_listings') = 'number'
                     and (c.value ->> 'min_listings') ~ '^[0-9]{1,3}$'
                then case when (c.value ->> 'min_listings')::int between 2 and 100
                          then (c.value ->> 'min_listings')::int end
           end
      from public.app_config c
     where c.key = 'seller_classification' and jsonb_typeof(c.value) = 'object'), 6) as min_listings
)
select l.source,
       count(*)                                                                   as active,
       count(*) filter (where l.seller_type is null)                              as seller_type_null,
       round(100.0 * count(*) filter (where l.seller_type is null) / count(*), 1) as seller_type_null_pct,
       count(*) filter (where nullif(btrim(l.seller_name), '') is null)           as seller_name_null,
       round(100.0 * count(*) filter (where nullif(btrim(l.seller_name), '') is null) / count(*), 1)
                                                                                  as seller_name_null_pct,
       count(*) filter (where l.seller_key is null)                               as seller_key_null,
       round(100.0 * count(*) filter (where l.seller_key is null) / count(*), 1)  as seller_key_null_pct,
       count(*) filter (where l.seller_listing_count >= cfg.min_listings)         as over_threshold,
       cfg.min_listings,
       count(*) filter (where l.dealer_inferred)                                  as dealer_inferred,
       round(100.0 * count(*) filter (where l.seller_type is null and not l.dealer_inferred) / count(*), 1)
                                                                                  as seller_unknown_pct
  from public.listings l
 cross join cfg
 where l.status = 'active'
 group by l.source, cfg.min_listings;

revoke all on public.admin_seller_coverage from public, anon, authenticated;
grant select on public.admin_seller_coverage to service_role;

notify pgrst, 'reload schema';

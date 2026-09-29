-- The description as a source of facts (normalization v3).
--
-- * listings.price / currency / price_usd become the *effective* price: the
--   cash price when the description gives a cheaper one, the total when the
--   published number is a down payment. Matching, comparables and the score
--   read them unchanged. What the source shows is kept in price_published.
-- * description_facts: what the title and description state (amounts by
--   kind, financing, km, year, transmission, fuel), read by rules or by the
--   LLM when the rules can't settle it (worker/normalization/description_facts.py).
-- * raw_pages: the last detail page of each listing, compressed, so a better
--   parser can re-read it without fetching it again (tools/reprocess.py).
-- * Facebook descriptions stored with the page's "Ver más" and "Sugerencias
--   de hoy" (other ads and their prices) are trimmed and queued for a new
--   detail pass, which now expands the text first.

-- ---------------------------------------------------------------------------
-- listings
-- ---------------------------------------------------------------------------

alter table public.listings
  add column price_published          numeric,
  add column price_published_currency text check (price_published_currency in ('USD', 'ARS')),
  add column price_source             text not null default 'published'
                                      check (price_source in ('published', 'description')),
  add column description_facts        jsonb;

comment on column public.listings.price is
  'Effective price (price_source): the published one, or the cash/total price the description gives.';
comment on column public.listings.price_published is
  'The price the source shows (cards and detail page). Snapshots and price drops follow this one.';
comment on column public.listings.price_source is
  'published: price = price_published. description: price comes from description_facts.';
comment on column public.listings.description_facts is
  'Facts the title/description state: amounts by kind (cash, list, down_payment, installment, generic), '
  'financing, mileage_km, year, transmission, fuel, gnc; source rules|llm; price_check (published_kind, mismatch).';

update public.listings
   set price_published = price,
       price_published_currency = currency
 where price_published is null;

-- ---------------------------------------------------------------------------
-- Facebook descriptions with the page around them
-- ---------------------------------------------------------------------------

update public.listings
   set description = nullif(btrim(regexp_replace(
         description,
         '(^|\n)[·\s]*(ver más|see more|sugerencias de hoy|today''s picks|la ubicación es aproximada|enviar mensaje)\s*(\n.*)?$',
         '', 'i')), ''),
       enriched_at = null,
       detail_checked_at = null
 where source = 'facebook'
   and description ~* '(^|\n)[·\s]*(ver más|see more|sugerencias de hoy)\s*(\n|$)';

-- ---------------------------------------------------------------------------
-- raw_pages
-- ---------------------------------------------------------------------------

create table public.raw_pages (
  listing_id     bigint      not null references public.listings (id) on delete cascade,
  kind           text        not null default 'detail' check (kind in ('detail')),
  url            text        not null,
  status         integer     not null,
  fetched_at     timestamptz not null default now(),
  parser_version integer     not null,
  html_gz        bytea       not null,
  primary key (listing_id, kind)
);

comment on table public.raw_pages is
  'Last detail page per listing (gzip of the slimmed HTML), to re-parse without fetching again. '
  'Worker only; kept app_config.retention.raw_page_days.';

alter table public.raw_pages enable row level security;
revoke all on public.raw_pages from anon, authenticated;

create index raw_pages_fetched_at on public.raw_pages (fetched_at);

-- ---------------------------------------------------------------------------
-- Config
-- ---------------------------------------------------------------------------

insert into public.app_config (key, value) values
  ('description_facts', '{"llm": true, "llm_daily_cap": 50}')
on conflict (key) do nothing;

update public.app_config
   set value = value || '{"raw_page_days": 90}'::jsonb
 where key = 'retention' and not value ? 'raw_page_days';

-- ---------------------------------------------------------------------------
-- match_cards: the cards say whether the price is the cash one and if the car
-- can be financed
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
       coalesce((l.description_facts -> 'financing' ->> 'offered')::boolean, false) as financing_offered
  from public.matches m
  join public.search_profiles sp on sp.id = m.search_profile_id
  join public.listings l on l.id = m.listing_id
  left join public.user_listing_interactions i
    on i.user_id = sp.user_id and i.listing_id = m.listing_id;

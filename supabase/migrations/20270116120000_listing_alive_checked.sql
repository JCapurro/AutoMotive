-- Autos que ya terminaron (docs/PLAN_DELISTADOS.md, paso 1: opción B con la columna interna de D).
-- Juan, 2026-11-25.
--
-- listings.alive_checked_at: the last time a source proved the car alive, by a search (a crawl or a stock read
-- saw it) or by its detail page. listings.alive_unseen_checks: how many detail checks in a row found it alive
-- while the searches no longer showed it (0 again as soon as a search sees it). The worker's re-check queue
-- (db/repos/listings.matched_recheck_queue) spaces those checks with it: 12 h, 24 h, 48 h, then every 72 h.
--
-- Internal only: no view, card or RPC of the web reads them. The user still sees a car as vigente or «Ya no
-- está disponible», nothing in between.
--
-- The fill copies last_seen_at, which until now every sighting and every detail check that found the car
-- alive renewed: the best "last proven alive" there is. It updates every row of listings: apply it with the
-- worker stopped (its ingest locks listings rows, and lock_timeout would cut the fill).
set local lock_timeout = '5s';

alter table public.listings
  add column if not exists alive_checked_at timestamptz,
  add column if not exists alive_unseen_checks smallint not null default 0;

update public.listings set alive_checked_at = last_seen_at where alive_checked_at is null;

-- A new listing was just seen by the search that brought it.
alter table public.listings alter column alive_checked_at set default now();

-- M3 and the pre-send check (notifications/dispatch.py) read the active ones by it.
create index if not exists listings_alive_checked_active_idx
  on public.listings (source, alive_checked_at) where status = 'active';

comment on column public.listings.alive_checked_at is
  'Last time a source proved the listing alive: seen by a search or a stock read, or its detail page read '
  'without an end. Internal (worker queues and metrics); never shown.';
comment on column public.listings.alive_unseen_checks is
  'Detail checks in a row that found the listing alive while the searches no longer showed it; 0 when a '
  'search sees it again. Spaces the worker''s re-checks (12 h, 24 h, 48 h, then 72 h).';

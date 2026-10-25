-- Crawl targets as a queue (incident 21/10/2026: a Facebook run hung for an
-- hour and its target, and its run, stayed "running" after the restart).
--
-- A worker lane claims its source's next due target with FOR UPDATE SKIP
-- LOCKED and holds it until claimed_until (its collector timeout plus a
-- margin); finishing the run clears the claim. A worker that dies leaves the
-- claim to expire, so the target is crawled again without anyone cleaning up,
-- and two worker processes never crawl the same target at once.
-- claimed_by and collector_runs.worker are "host:pid": at start a worker
-- frees what a dead process on its own host left, without waiting.

alter table public.crawl_targets
  add column claimed_by text,
  add column claimed_until timestamptz;

alter table public.collector_runs
  add column worker text;

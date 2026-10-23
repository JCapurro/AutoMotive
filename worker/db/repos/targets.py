"""crawl_targets and the source cadence they run on (sección 5.1).

A `count_only` target (only searches whose access ended, 2.5) runs once a day
at most, and as soon as an active search joins it, it runs at the source's
cadence again, starting right away. A target by body type (docs/CARROCERIA.md)
runs at its own cadence, query.interval_seconds (app_config.body_type_targets)."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Iterable

from psycopg.types.json import Jsonb

from db.pool import connection

# 2.5: a model only searches with ended access want is crawled once a day.
COUNT_ONLY_INTERVAL_SECONDS = 86_400

# Whether search profile `sp` wants crawl target `t`, for the three shapes of
# pipeline/crawl.py: an inventory target (no make, model or body type) serves
# every search, a model target the searches of its make/model, and a target by
# body type the searches without a model that want it. A target by body type
# also has make and model null: without `t.body_type IS NULL` any model-less
# search would want every one of them. tools/platform_health.py uses it too.
PROFILE_WANTS_TARGET = (
    "((t.query->>'inventory' = 'true' AND t.make IS NULL AND t.model IS NULL AND t.body_type IS NULL)"
    "  OR (t.body_type IS NULL AND lower(sp.filters->>'make') IS NOT DISTINCT FROM lower(t.make)"
    "      AND lower(sp.filters->>'model') IS NOT DISTINCT FROM lower(t.model))"
    "  OR (t.body_type IS NOT NULL AND public.search_is_model_less(sp.filters)"
    "      AND sp.filters->'body_types' ? t.body_type))"
    " AND (NOT sp.filters ? 'sources' OR sp.filters->'sources' ? t.source)")

# The cadence of a target: its own (a target by body type) or its source's.
INTERVAL_SECONDS = "coalesce((t.query->>'interval_seconds')::int, s.crawl_interval_seconds)"


async def enabled_sources() -> dict[str, dict[str, Any]]:
    async with connection() as cx:
        rows = await (await cx.execute(
            "SELECT id, crawl_interval_seconds, detail_interval_seconds, priority "
            "  FROM sources WHERE enabled ORDER BY priority, id")).fetchall()
    return {r["id"]: r for r in rows}


# sync_targets: the spec (excluded) brings a new value of `key` its target
# (crawl_targets) didn't have.
_CHANGED = ("(excluded.query ? '{0}' AND "
            " crawl_targets.query->'{0}' IS DISTINCT FROM excluded.query->'{0}')")
_POLICY_CHANGED = _CHANGED.format("publication_policy")
_COVERAGE_CHANGED = _CHANGED.format("coverage")


async def sync_targets(specs: Iterable[Any], *, undated: Iterable[str] = ()) -> None:
    """Make crawl_targets mirror `specs` (pipeline.crawl.TargetSpec): upsert the
    wanted ones and deactivate the rest. One UPDATE decides what a change of
    spec does to a target:
      - a new publication policy resets bootstrap once and empties Facebook's
        date memory (its window goes back to 30 days, collectors/_recency.py);
      - a new coverage (the collector's COVERAGE_VERSION: it reads more of the
        source now) resets bootstrap once too, and empties the date memory of
        a target that reads by publication date;
      - a target of an `undated` source (pipeline/news.py UNDATED_SOURCES)
        that is reactivated starts its bootstrap over: the stock it finds was
        listed while nobody read it;
      - any other edit (a wider or narrower query, query.year_band) keeps both.
    query._read, what the target's last complete read covered (finish_target),
    stays while the target is active and goes with a reactivation; a target
    whose spec only lacks it isn't rewritten. A count-only target that gets an
    active search is due at once.

    Whatever else comes to reset first_run_done of a Facebook target must
    empty prefilter_rejected in the same UPDATE: its date memory holds only
    while the window's start never moves back, and a reset takes it back to
    30 days."""
    specs = list(specs)
    async with connection() as cx:
        await cx.execute("CREATE TEMP TABLE wanted (source text, make text, model text, body_type text, "
                         "  query jsonb) ON COMMIT DROP")
        if specs:
            async with cx.cursor() as cur:
                await cur.executemany(
                    "INSERT INTO wanted VALUES (%s, %s, %s, %s, %s)",
                    [(s.source, s.make, s.model, getattr(s, "body_type", None), Jsonb(s.query))
                     for s in specs])
        await cx.execute(
            "INSERT INTO crawl_targets (source, make, model, body_type, query, active) "
            "SELECT source, make, model, body_type, query, true FROM wanted "
            "ON CONFLICT (source, make, model, body_type) DO UPDATE SET "
            "   query = CASE WHEN crawl_targets.active AND crawl_targets.query ? '_read' "
            "     THEN excluded.query || jsonb_build_object('_read', crawl_targets.query->'_read') "
            "     ELSE excluded.query END, active = true "
            f" , first_run_done = CASE WHEN {_POLICY_CHANGED} OR {_COVERAGE_CHANGED} "
            "     OR (NOT crawl_targets.active AND excluded.source = ANY(%s)) "
            "     THEN false ELSE crawl_targets.first_run_done END "
            f" , next_run_at = CASE WHEN {_POLICY_CHANGED} "
            "     OR (crawl_targets.query ? 'count_only' AND NOT excluded.query ? 'count_only') "
            "     THEN NULL ELSE crawl_targets.next_run_at END "
            f" , prefilter_rejected = CASE WHEN {_POLICY_CHANGED} "
            f"     OR ({_COVERAGE_CHANGED} AND excluded.query ? 'publication_policy') "
            "     THEN '{}' ELSE crawl_targets.prefilter_rejected END "
            " WHERE (crawl_targets.query - '_read') IS DISTINCT FROM excluded.query OR NOT crawl_targets.active",
            (sorted(set(undated)),))
        await cx.execute(
            "UPDATE crawl_targets t SET active = false WHERE active AND NOT EXISTS ("
            "  SELECT 1 FROM wanted w WHERE w.source = t.source "
            "     AND w.make IS NOT DISTINCT FROM t.make AND w.model IS NOT DISTINCT FROM t.model "
            "     AND w.body_type IS NOT DISTINCT FROM t.body_type)")


async def publication_dates(target: dict[str, Any]) -> dict[str, int]:
    """Reuse stored publication dates, avoiding a detail request on every daily read.
    A target by body type reads at most the last 25 hours (collectors/_recency.py):
    the dates of its body type seen in the last two days.

    A target by model gets its make's: a search by text also brings models
    with a longer name (Gol → Gol Trend and Golf, Corolla → Corolla Cross),
    and the external ID names the ad. Seen in the last 35 days, which covers
    the widest window: an ad published within it was last seen after that."""
    async with connection() as cx:
        if target.get("body_type"):
            rows = await (await cx.execute(
                "SELECT external_id, published_at FROM listings WHERE source = %s AND body_type = %s "
                "   AND published_at IS NOT NULL AND last_seen_at >= now() - interval '2 days'",
                (target["source"], target["body_type"]))).fetchall()
            return {r["external_id"]: int(r["published_at"].timestamp()) for r in rows}
        rows = await (await cx.execute(
            "SELECT external_id, published_at FROM listings WHERE source = %s "
            " AND lower(make) IS NOT DISTINCT FROM lower(%s) AND published_at IS NOT NULL "
            " AND last_seen_at >= now() - interval '35 days'",
            (target["source"], target.get("make")))).fetchall()
    return {r["external_id"]: int(r["published_at"].timestamp()) for r in rows}


# A due target (t, joined to its source s): active, of an enabled source,
# next_run_at come (or never ran), for a search with access (a count-only
# target was derived this tick from the searches 2.5 counts), and not held by
# a worker (claim_next).
_DUE = (
    " t.active AND s.enabled AND (t.next_run_at IS NULL OR t.next_run_at <= now()) "
    " AND (t.claimed_until IS NULL OR t.claimed_until < now()) "
    " AND (t.query->>'count_only' = 'true' "
    "  OR EXISTS (SELECT 1 FROM search_profiles sp WHERE public.search_access_active(sp.id) "
    f"   AND {PROFILE_WANTS_TARGET})) ")
_TARGET_COLUMNS = ("t.id, t.source, t.make, t.model, t.body_type, t.query, t.first_run_done, "
                   "t.prefilter_rejected, t.last_run_at, "
                   f"{INTERVAL_SECONDS} AS crawl_interval_seconds")


async def due_targets() -> list[dict[str, Any]]:
    """The due targets (_DUE). crawl_interval_seconds is the target's cadence."""
    async with connection() as cx:
        return await (await cx.execute(
            f"SELECT {_TARGET_COLUMNS} FROM crawl_targets t JOIN sources s ON s.id = t.source "
            f" WHERE {_DUE} ORDER BY s.priority, t.next_run_at NULLS FIRST, t.id")).fetchall()


async def claim_next(source: str, worker: str, lease_seconds: int) -> dict[str, Any] | None:
    """Take `source`'s next due target for `worker` until now + lease_seconds;
    None when it has none, or while another target of the source is claimed:
    one crawl per source at a time across every worker (one Facebook session,
    one rate limit). The source's advisory lock makes the check and the claim
    one step, so two workers can't both pass it. Another worker skips the
    target until finish_target or the lease ends.

    A target that never ran (or was reset, next_run_at NULL) goes first, then
    the due targets that notify, then the first-run retries and the
    count-only targets, each by when it was due: a long bootstrap scan never
    waits behind them, and they never wait behind it more than one scan
    (Sentra waited ~140 minutes behind Facebook bootstraps, 2026-10-22). A
    first run that is retried stays one until it completes."""
    async with connection() as cx:
        await cx.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (f"crawl_source:{source}",))
        return await (await cx.execute(
            "WITH next AS (SELECT t.id FROM crawl_targets t JOIN sources s ON s.id = t.source "
            f"  WHERE t.source = %s AND {_DUE} "
            "    AND NOT EXISTS (SELECT 1 FROM crawl_targets c WHERE c.source = t.source "
            "                    AND c.claimed_until > now()) "
            "  ORDER BY t.next_run_at IS NOT NULL, "
            "    (t.first_run_done AND t.query->>'count_only' IS DISTINCT FROM 'true') DESC, "
            "    t.next_run_at, t.id LIMIT 1 FOR UPDATE OF t SKIP LOCKED) "
            "UPDATE crawl_targets t SET claimed_by = %s, claimed_until = now() + make_interval(secs => %s) "
            "  FROM next, sources s WHERE t.id = next.id AND s.id = t.source "
            f"RETURNING {_TARGET_COLUMNS}",
            (source, worker, lease_seconds))).fetchone()


async def claim_holders(host: str) -> list[str]:
    """The workers ("host:pid") of `host` holding a claim, expired or not."""
    async with connection() as cx:
        rows = await (await cx.execute(
            "SELECT DISTINCT claimed_by FROM crawl_targets WHERE split_part(claimed_by, ':', 1) = %s",
            (host,))).fetchall()
    return [r["claimed_by"] for r in rows]


async def release_claims(workers: Iterable[str]) -> int:
    """Free the targets those (dead) workers held. Returns how many."""
    workers = sorted(set(workers))
    if not workers:
        return 0
    async with connection() as cx:
        cur = await cx.execute(
            "UPDATE crawl_targets SET claimed_by = NULL, claimed_until = NULL WHERE claimed_by = ANY(%s)",
            (workers,))
        return cur.rowcount


async def set_prefilter_rejected(target_id: int, external_ids: Iterable[str]) -> None:
    """What a target by body type's prefilter dropped (pipeline/crawl.py
    prefilter) or, on a Facebook target by model, its date memory: the ads
    dated out of the window ("id") or whose page had no date ("id@epoch#n"),
    collectors/_recency.py."""
    async with connection() as cx:
        await cx.execute("UPDATE crawl_targets SET prefilter_rejected = %s WHERE id = %s",
                         (sorted(set(external_ids)), target_id))


async def finish_target(target_id: int, *, ok: bool, retry_seconds: int,
                        covered_until: datetime | None = None, bootstrap: bool = True,
                        read: dict[str, Any] | None = None) -> None:
    """Schedule from completion; keep coverage at the successful scan's start.
    Failure retries without advancing bootstrap or the coverage checkpoint.
    A count-only target waits a day, or the source's interval if longer; a
    target by body type, its own interval. `bootstrap=False`: a successful
    run that doesn't finish the first one (an empty first read, pipeline/crawl.py).
    `read`: what that complete read covered (news.read_envelope), kept in
    query._read on the query the target has now: a search that widened it
    during the run is still outside it on the next one."""
    async with connection() as cx:
        if ok:
            await cx.execute(
                "UPDATE crawl_targets t SET last_run_at = coalesce(%s::timestamptz, now()), "
                "  first_run_done = t.first_run_done OR %s, claimed_by = NULL, claimed_until = NULL, "
                "  query = coalesce(jsonb_set(t.query, '{_read}', %s::jsonb), t.query), "
                "  next_run_at = now() + make_interval(secs => CASE WHEN t.query->>'count_only' = 'true' "
                f"    THEN greatest(s.crawl_interval_seconds, %s) ELSE {INTERVAL_SECONDS} END) "
                "  FROM sources s WHERE s.id = t.source AND t.id = %s",
                (covered_until, bootstrap, Jsonb(read) if read is not None else None,
                 COUNT_ONLY_INTERVAL_SECONDS, target_id))
        else:
            await cx.execute(
                "UPDATE crawl_targets SET next_run_at = now() + make_interval(secs => %s), "
                "  claimed_by = NULL, claimed_until = NULL "
                " WHERE id = %s", (retry_seconds, target_id))

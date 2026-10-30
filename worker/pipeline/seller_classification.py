"""Seller classification (F-02, docs/superpowers/specs/2026-10-30-f02-vendedor-design.md):
every active listing gets listings.seller_listing_count, how many distinct cars
its seller (same source, same seller_key) published in the last window_days and
still has active, and listings.dealer_inferred («posible agencia», paso 2):
that count reaches min_listings and the source does not already say dealer.
The rules are in db/repos/sellers.py.

Full runs (classify_sellers) at worker startup (before rescore_outdated), at
the anchor slot of the nightly loop (before rescore_recent) and from
`python -m tools.seller_classification`. Each fills the seller_key of the
active listings that have a name and none yet, then writes per source in
batches of GROUP_BATCH groups, each batch in its own transaction, re-scores
right away the matches of every listing whose dealer_inferred flipped (or,
still inferred, whose count changed: the reason carries N), also after a
failure for the batches that committed, and
records itself in seller_classification_runs. With
app_config.seller_classification.enabled = false it takes the inference off
every listing (also gone ones) and re-scores those.

At ingest (classify_groups, pipeline/ingest.py) only the groups the batch
touched, after its commit and before the crawl scores it: a new listing of a
known group is a «posible agencia» from its first alert, and the older
listings it flips are re-scored right there, on the crawl path. A failure
there is logged and the ingest goes on; the next full run fixes it.
"""
from __future__ import annotations

import logging
import traceback
from typing import Any, Iterable

import db
from db.repos import sellers
from db.repos.runs import log_error
from intelligence.config import seller_classification

log = logging.getLogger("seller_classification")

TOP_GROUPS = 10


async def _fill_missing_keys() -> int:
    written, after = 0, 0
    while after is not None:
        async with db.connection() as cx:
            after, n = await sellers.backfill_keys(cx, after, missing_only=True)
        written += n
    return written


async def backfill_keys(*, batch: int = sellers.KEY_BATCH) -> dict[str, int]:
    """seller_key recomputed for every listing (active and gone), `batch` ids
    per transaction. The CLI's --backfill-keys, once after the migration."""
    read = written = 0
    after: int | None = 0
    while True:
        async with db.connection() as cx:
            last, n = await sellers.backfill_keys(cx, after, limit=batch)
        if last is None:
            return {"batches": read, "rows_written": written}
        read, written, after = read + 1, written + n, last


def _source_report(source: str, active: int, groups: list[dict[str, Any]], min_listings: int) -> dict[str, Any]:
    counted = [g for g in groups if g["n"] is not None]
    top = sorted(counted, key=lambda g: (-g["n"], g["seller_key"]))[:TOP_GROUPS]
    return {"source": source, "active": active, "groups": len(groups),
            "over_threshold": sum(g["active"] for g in counted if g["n"] >= min_listings),
            "top": [{"key": g["seller_key"], "n": g["n"], "active": g["active"], "names": list(g["names"] or [])}
                    for g in top]}


async def _rescore(listing_ids: list[int]) -> int:
    """Re-score the matches of these listings now (their seller preference
    reason changed). Imported here: pipeline.rescore imports this module."""
    if not listing_ids:
        return 0
    from pipeline.rescore import rescore_listings
    return await rescore_listings(listing_ids)


async def classify_sellers(trigger: str, *, dry_run: bool = False, report: bool = False) -> dict[str, Any]:
    """One run over every source. dry_run writes no listing (not even the
    missing keys), re-scores nothing and records the run as dry_run, with what
    it would write. A failure is recorded on the run and raised; the callers
    log it."""
    cfg = seller_classification(await db.get_config("seller_classification"))
    result: dict[str, Any] = {"trigger": trigger, "mode": "dry_run" if dry_run else "write", "params": cfg,
                              "rows_read": 0, "rows_written": 0, "would_write": 0, "keys_filled": 0,
                              "inferred_changed": 0, "rescored": 0, "sources": []}
    async with db.connection() as cx:
        run_id = await sellers.start_run(cx, trigger, result["mode"], cfg)
    result["run_id"] = run_id
    # Each batch commits on its own: what it flipped is re-scored even when a
    # later batch fails (a later run would not flip those rows again).
    flipped: list[int] = []
    to_rescore: list[int] = []

    def took(written: sellers.Written) -> sellers.Written:
        result["would_write" if dry_run else "rows_written"] += written.rows
        flipped.extend(written.flipped)
        to_rescore.extend(written.rescore)
        return written

    try:
        if not dry_run:
            result["keys_filled"] = await _fill_missing_keys()
        async with db.connection() as cx:
            all_sources = await sellers.sources(cx)
        for source in all_sources:
            async with db.connection() as cx:
                active = await sellers.active_count(cx, source)
                keys = await sellers.group_keys(cx, source)
            for i in range(0, len(keys), sellers.GROUP_BATCH):
                async with db.connection() as cx:
                    took(await sellers.write_groups(cx, source, keys[i:i + sellers.GROUP_BATCH], cfg,
                                                    dry_run=dry_run))
            async with db.connection() as cx:
                took(await sellers.clear_stale(cx, source, dry_run=dry_run))
                if report:
                    result["sources"].append(_source_report(
                        source, active, await sellers.report_groups(cx, source, cfg), cfg["min_listings"]))
            result["rows_read"] += active
        if not cfg["enabled"]:
            # Off: also the listings no group write reaches (gone ones).
            while True:
                async with db.connection() as cx:
                    cleared = took(await sellers.clear_inferred(cx, dry_run=dry_run))
                if dry_run or not cleared.rows:
                    break
        result["inferred_changed"] = len(set(flipped))
        async with db.connection() as cx:
            await sellers.finish_run(cx, run_id, status="ok", rows_read=result["rows_read"],
                                     rows_written=None if dry_run else result["rows_written"],
                                     inferred_changed=result["inferred_changed"])
    except Exception:
        error = traceback.format_exc()
        try:
            async with db.connection() as cx:
                await sellers.finish_run(cx, run_id, status="failed", rows_read=result["rows_read"],
                                         error=error[-4000:])
        except Exception:
            log.exception("could not record the failed seller classification run %s", run_id)
        if not dry_run:
            try:
                await _rescore(list(dict.fromkeys(to_rescore)))
            except Exception:
                log.exception("could not re-score what the failed seller classification run %s flipped", run_id)
        raise
    if not dry_run:
        # After the run is recorded: a rescore failure is logged per profile
        # (pipeline/rescore.py) and the flags stay right.
        result["rescored"] = await _rescore(list(dict.fromkeys(to_rescore)))
    log.info("seller classification (%s, %s): %d active read, %d rows %s, %d keys filled, "
             "%d inferred changed, %d matches re-scored", trigger, result["mode"], result["rows_read"],
             result["would_write" if dry_run else "rows_written"], "to write" if dry_run else "written",
             result["keys_filled"], result["inferred_changed"], result["rescored"])
    return result


async def classify_groups(groups: Iterable[tuple[str, str]], keyless: Iterable[int] = ()) -> list[int]:
    """The ingest's share (decision 7a): count and mark only these (source,
    seller_key) groups, each source in its own short transaction, and drop the
    count and the inference of `keyless` listings (their name became generic).
    The matches of older listings whose inference flipped (or whose count
    changed while inferred: the reason says «publica N autos») are re-scored
    now, also those of the writes that committed before a failure; the batch's
    own listings are scored next by the crawl. Never raises: a failure is
    logged and the next full run fixes the rest. Returns the flipped ids."""
    by_source: dict[str, set[str]] = {}
    for source, key in groups:
        if key:
            by_source.setdefault(source, set()).add(key)
    keyless = list(keyless)
    if not by_source and not keyless:
        return []
    written = sellers.Written()
    try:
        cfg = seller_classification(await db.get_config("seller_classification"))
        for source, keys in sorted(by_source.items()):
            async with db.connection() as cx:
                written.add(await sellers.write_groups(cx, source, sorted(keys), cfg))
        if keyless:
            async with db.connection() as cx:
                written.add(await sellers.clear_listings(cx, keyless))
    except Exception:
        await log_error("seller_classification", "ingest", traceback.format_exc())
    try:
        await _rescore(list(dict.fromkeys(written.rescore)))
    except Exception:
        await log_error("seller_classification", "ingest:rescore", traceback.format_exc())
    return written.flipped

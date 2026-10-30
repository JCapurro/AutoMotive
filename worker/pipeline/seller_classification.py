"""Seller classification (F-02 paso 1,
docs/superpowers/specs/2026-10-30-f02-vendedor-design.md): every active listing
gets listings.seller_listing_count, how many distinct cars its seller
(same source, same seller_key) published in the last window_days and still
has active. The rules are in db/repos/sellers.py.

Runs at worker startup (before rescore_outdated), at the anchor slot of the
nightly loop (before rescore_recent) and from `python -m tools.seller_classification`.
Each run fills the seller_key of the active listings that have a name and
none yet, then writes the counts per source in batches of GROUP_BATCH groups,
each batch in its own transaction, and records itself in
seller_classification_runs. Step 1 changes nothing a user sees and no score:
nothing reads the count yet, and app_config.seller_classification.enabled and
min_listings only matter from step 2 (dealer_inferred).
"""
from __future__ import annotations

import logging
import traceback
from typing import Any

import db
from db.repos import sellers
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


async def classify_sellers(trigger: str, *, dry_run: bool = False, report: bool = False) -> dict[str, Any]:
    """One run over every source. dry_run writes no listing (not even the
    missing keys) and records the run as dry_run, with what it would write.
    A failure is recorded on the run and raised; the callers log it."""
    cfg = seller_classification(await db.get_config("seller_classification"))
    result: dict[str, Any] = {"trigger": trigger, "mode": "dry_run" if dry_run else "write", "params": cfg,
                              "rows_read": 0, "rows_written": 0, "would_write": 0, "keys_filled": 0,
                              "sources": []}
    async with db.connection() as cx:
        run_id = await sellers.start_run(cx, trigger, result["mode"], cfg)
    result["run_id"] = run_id
    try:
        if not dry_run:
            result["keys_filled"] = await _fill_missing_keys()
        async with db.connection() as cx:
            all_sources = await sellers.sources(cx)
        for source in all_sources:
            async with db.connection() as cx:
                active = await sellers.active_count(cx, source)
                keys = await sellers.group_keys(cx, source)
            written = 0
            for i in range(0, len(keys), sellers.GROUP_BATCH):
                async with db.connection() as cx:
                    written += await sellers.write_groups(cx, source, keys[i:i + sellers.GROUP_BATCH], cfg,
                                                          dry_run=dry_run)
            async with db.connection() as cx:
                written += await sellers.clear_stale(cx, source, dry_run=dry_run)
                if report:
                    result["sources"].append(_source_report(
                        source, active, await sellers.report_groups(cx, source, cfg), cfg["min_listings"]))
            result["rows_read"] += active
            result["would_write" if dry_run else "rows_written"] += written
        async with db.connection() as cx:
            await sellers.finish_run(cx, run_id, status="ok", rows_read=result["rows_read"],
                                     rows_written=None if dry_run else result["rows_written"])
    except Exception:
        error = traceback.format_exc()
        try:
            async with db.connection() as cx:
                await sellers.finish_run(cx, run_id, status="failed", rows_read=result["rows_read"],
                                         error=error[-4000:])
        except Exception:
            log.exception("could not record the failed seller classification run %s", run_id)
        raise
    log.info("seller classification (%s, %s): %d active read, %d rows %s, %d keys filled", trigger,
             result["mode"], result["rows_read"], result["would_write" if dry_run else "rows_written"],
             "to write" if dry_run else "written", result["keys_filled"])
    return result

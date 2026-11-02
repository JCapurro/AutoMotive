"""Duplicate detection (PAR-02 resto,
docs/superpowers/specs/2026-11-02-par02-resto-design.md, decision 7): writes
listing_duplicates from the rules of intelligence/duplicates.py and re-scores
the matches of every listing whose shown pairs changed (the duplicate red
flags read them through db/repos/listings.rows_for_scoring). A re-score never
notifies.

* detect_all: every (make, model) group with 2+ sources or a photo hash, at
  worker startup and at the nightly anchor slot (pipeline/rescore.py, after the
  seller classification: the data level reads dealer_inferred) and from
  `python -m tools.risk_duplicates`. Also deletes the pairs of listings no
  group holds any more.
* detect_for: only the groups of some listings, after an ingest
  (pipeline/ingest.py) and after the photo hash pass. Never raises: a failure
  is logged and the next full run fixes it.

Each group is rewritten to its desired state in its own transaction, under an
advisory lock, so running twice changes nothing (idempotent). app_config.risk
.signals: a kind "off" is neither computed nor kept, "shadow" is kept with
shown = false, "on" with shown = true.
"""
from __future__ import annotations

import logging
import traceback
from typing import Any, Iterable

import db
from db.repos import duplicates as repo
from db.repos.runs import log_error
from intelligence import duplicates
from intelligence.config import risk as risk_config

log = logging.getLogger("risk_duplicates")

REPORT_PER_KIND = 20


def _shown(pairs: dict[tuple[int, int], dict[str, Any]]) -> dict[int, set[tuple[int, str]]]:
    out: dict[int, set[tuple[int, str]]] = {}
    for (a, b), row in pairs.items():
        if row["shown"]:
            out.setdefault(a, set()).add((b, row["kind"]))
    return out


def diff(old: dict[tuple[int, int], dict[str, Any]], new: dict[tuple[int, int], dict[str, Any]]
         ) -> tuple[list[tuple[int, int]], list[dict[str, Any]], set[int]]:
    """(deletes, upserts, listings whose shown pairs changed)."""
    deletes = [k for k in old if k not in new]
    upserts = [row for k, row in new.items()
               if k not in old or any(old[k].get(c) != row[c] for c in ("kind", "shown", "photo_distance", "evidence"))]
    before, after = _shown(old), _shown(new)
    changed = {i for i in set(before) | set(after) if before.get(i, set()) != after.get(i, set())}
    return deletes, upserts, changed


async def _rescore(listing_ids: Iterable[int]) -> int:
    ids = sorted(set(listing_ids))
    if not ids:
        return 0
    from pipeline.rescore import rescore_listings      # pipeline.rescore imports this module
    return await rescore_listings(ids)


def _count(result: dict[str, Any], rows: Iterable[dict[str, Any]], key: str) -> None:
    for r in rows:
        bucket = result[key].setdefault(r["kind"], 0)
        result[key][r["kind"]] = bucket + 1


async def _group(group: repo.Group, cfg: dict[str, Any], result: dict[str, Any], *, dry_run: bool,
                 report: bool) -> set[int]:
    async with db.connection() as cx:
        await repo.lock_group(cx, group)
        rows = await repo.group_rows(cx, group)
        old = await repo.stored(cx, group)
        pairs = duplicates.detect(rows, cfg)
        new = duplicates.rows_out(pairs, cfg)
        deletes, upserts, changed = diff(old, new)
        if not dry_run:
            await repo.write(cx, deletes, upserts)
    result["groups"] += 1
    result["rows_read"] += len(rows)
    _count(result, [old[k] for k in deletes], "deleted")
    _count(result, [r for r in upserts if (r["listing_id"], r["other_id"]) not in old], "created")
    _count(result, new.values(), "pairs")
    if report:
        for p in pairs:
            if p.kind in cfg["signals"] and cfg["signals"][p.kind] != "off":
                bucket = result["report"].setdefault(p.kind, [])
                if len(bucket) < REPORT_PER_KIND:
                    bucket.append(p)
    return changed


def _new_result(trigger: str, dry_run: bool, cfg: dict[str, Any]) -> dict[str, Any]:
    return {"trigger": trigger, "mode": "dry_run" if dry_run else "write", "signals": dict(cfg["signals"]),
            "groups": 0, "rows_read": 0, "pairs": {}, "created": {}, "deleted": {}, "changed": 0,
            "rescored": 0, "report": {}}


async def detect_all(trigger: str, *, dry_run: bool = False, report: bool = False,
                     only: repo.Group | None = None) -> dict[str, Any]:
    """One full run (or one group with `only`). dry_run writes nothing and
    re-scores nothing; `result` counts the pair rows (both ways) per kind it
    keeps, creates and deletes. Raises on failure (the callers log it), after
    re-scoring what the groups that committed changed."""
    cfg = risk_config(await db.get_config("risk"))
    result = _new_result(trigger, dry_run, cfg)
    changed: set[int] = set()
    async with db.connection() as cx:
        if not await _table(cx):
            log.info("duplicates: listing_duplicates does not exist yet (migration 20261203120000), skipped")
            result["mode"] = "skipped"
            return result
    try:
        async with db.connection() as cx:
            all_groups = await repo.groups(cx, only)
        for group in all_groups:
            changed |= await _group(group, cfg, result, dry_run=dry_run, report=report)
        if only is None:
            async with db.connection() as cx:
                stale = await repo.stored_elsewhere(cx, all_groups)
                if not dry_run:
                    await repo.write(cx, list(stale), [])
            _count(result, stale.values(), "deleted")
            changed |= {a for (a, _), row in stale.items() if row["shown"]}
    finally:
        result["changed"] = len(changed)
        if not dry_run:
            result["rescored"] = await _rescore(changed)
    log.info("duplicates (%s, %s): %d groups, %d listings, pairs %s, created %s, deleted %s, "
             "%d listings changed, %d matches re-scored", trigger, result["mode"], result["groups"],
             result["rows_read"], result["pairs"], result["created"], result["deleted"], result["changed"],
             result["rescored"])
    return result


async def detect_for(listing_ids: Iterable[int]) -> int:
    """The groups of these listings only; re-scores what changed. Never raises.
    Returns how many listings changed their shown pairs."""
    ids = list(dict.fromkeys(listing_ids))
    if not ids:
        return 0
    changed: set[int] = set()
    try:
        cfg = risk_config(await db.get_config("risk"))
        result = _new_result("ingest", False, cfg)
        async with db.connection() as cx:
            if not await _table(cx):
                return 0
            groups = await repo.groups_of(cx, ids)
        for group in groups:
            changed |= await _group(group, cfg, result, dry_run=False, report=False)
    except Exception:
        await log_error("risk_duplicates", "detect_for", traceback.format_exc())
    try:
        await _rescore(changed)
    except Exception:
        await log_error("risk_duplicates", "detect_for:rescore", traceback.format_exc())
    return len(changed)


async def _table(cx) -> bool:
    """Whether the migration is applied (a worker may deploy before it)."""
    from db.repos.listings import duplicates_table
    return await duplicates_table(cx)

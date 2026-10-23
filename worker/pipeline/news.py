"""Which new listings are not news, on the sources without publication dates
(docs/TECHNICAL_PLAN.md, sección 5.7).

Mercado Libre and Facebook read by publication date (collectors/_recency.py)
and are left alone. On every other source a listing is "new" when its
external_id was never stored, so old stock looks new when:
  - a read brings at once half the stock again (a collector deploy, a wider
    search, a read cut short before): the step;
  - the same car comes back under another ID after its old copy left the
    source: the reappearance, only on the sources whose reads are trusted
    whole. A republication at least price_drop_min_pct cheaper is still
    news, labelled "re-publicado" (_republished);
  - a target of UNDATED_SOURCES read nothing on its first run: crawl._run_one
    holds its bootstrap for EMPTY_FIRST_RUNS empty reads at most, so what it
    reads right after is that first run's backfill.
classify stores the first two as backfill for every search (seen on the web,
never notified) and marks them in listings.attributes._not_news {reason,
run_id, target_id, prev_id}: scheduler.match_alert keeps them backfill on a
retry or for another target, and count_after_expiry (2.5) never counts them.
A first run's new listings are marked 'first_run', only for 2.5: the target's
next runs find them again after its bootstrap. A listing with a recent
publication date (v6) is always news. Each rule has its switch in config
(NEWS_GUARD_*); a failure leaves every listing news, as before.

crawl.run_target calls classify right after the ingest, and a run cut
between the two (a restart) is caught up on the target's next run: the
listings it saw first after the target's last run that got to its end, and
that have no mark, are classified with that run's (listings.unclassified).
"""
from __future__ import annotations

import logging
import traceback
from collections import Counter
from typing import Any, Iterable

import config
from collectors._recency import SOURCES as RECENT_SOURCES
from db.pool import connection
from db.repos import listings, runs
from db.repos.config import get_config
from pipeline.ingest import IngestConfig, IngestResult, price_drop_pct

log = logging.getLogger("news")

FIRST_RUN, STEP, REAPPEARANCE, ENVELOPE, BAND = "first_run", "step", "reappearance", "envelope", "band"
# Old stock: backfill for every search on every run, never counted in 2.5.
# 'envelope' (crawl_targets.query._read) and 'band' (query.year_band) come later.
MUTED = frozenset({STEP, REAPPEARANCE, ENVELOPE, BAND})

# The sources without publication dates (an external_id never stored is all
# "new" means there). v6, mardelusados, usadossantafe and the Instagram
# sources date their listings.
UNDATED_SOURCES = frozenset({"autocity", "autocosmos", "carone", "deruedas", "gruporandazzo", "kavak",
                             "rosariogarage"})
# An empty first read of theirs holds the bootstrap for at most this many
# empty ok runs in a row (kavak Fox read 0, then its stock 31 minutes
# later); past them an empty read finishes it: a narrow search with nothing
# listed, whose first car is news.
EMPTY_FIRST_RUNS = 2

# A step: at least this many new listings, and twice them at least the most
# one of the target's last STEP_RUNS ok runs that read something found.
STEP_MIN_NEW = 5
STEP_RUNS = 3
# A reappearance's old copy is within this many km. Without a seller, the
# same km, and seen this recently or under the same title: private sellers
# round their km.
REAPPEARANCE_KM = 100
REAPPEARANCE_UNSELLERED_HOURS = 72


def is_step(new: int, prev_found: int | None) -> bool:
    """Whether `new` listings are old stock read at once: STEP_MIN_NEW or
    more, and at least half of `prev_found`, the most a recent ok run found
    (autocosmos Fox 2 → 16, kavak Fiesta 9 → 24). A day of news is far from
    it (rosariogarage Gol, 20 new of 181). None: no ok run to compare with."""
    return prev_found is not None and new >= STEP_MIN_NEW and 2 * new >= prev_found


def outside_envelope(row: dict[str, Any], envelope: dict[str, Any] | None) -> bool:
    """Whether a listing falls outside the year_min/year_max/km_max a target
    read with before (crawl_targets.query._read): stock a widened search
    brings, not news. A bound that is None doesn't limit, and an unknown
    year or km is inside."""
    if not envelope:
        return False
    year, km = row.get("year"), row.get("mileage_km")
    if year is not None:
        if envelope.get("year_min") is not None and year < envelope["year_min"]:
            return True
        if envelope.get("year_max") is not None and year > envelope["year_max"]:
            return True
    return km is not None and envelope.get("km_max") is not None and km > envelope["km_max"]


def _mark(row: dict[str, Any] | None) -> dict[str, Any]:
    mark = ((row or {}).get("attributes") or {}).get("_not_news")
    return mark if isinstance(mark, dict) else {}


def muted(row: dict[str, Any] | None) -> bool:
    """A listing classify took for old stock: backfill for every search, on every run."""
    return _mark(row).get("reason") in MUTED


def uncounted(row: dict[str, Any] | None, target_id: int | None) -> bool:
    """Not counted in 2.5 by this target: old stock, or a listing it stored
    on its own first run. Another target's first run still counts: that
    target only found first what is new (test_count_after_expiry.py)."""
    mark = _mark(row)
    return mark.get("reason") in MUTED or (mark.get("reason") == FIRST_RUN and mark.get("target_id") == target_id)


def republished(row: dict[str, Any] | None) -> bool:
    """A cheaper republication classify let through: notified as "re-publicado"."""
    return bool(((row or {}).get("attributes") or {}).get("_republished"))


def _dated_news(row: dict[str, Any], max_age_days: int) -> bool:
    # scheduler imports crawl, which imports this module.
    from pipeline.scheduler import _is_recent
    return row.get("published_at") is not None and _is_recent(row, max_age_days)


async def classify(target: dict[str, Any], items: Iterable[Any], result: IngestResult, *, run_id: int,
                   first_run: bool, complete: bool, readmitted: Iterable[int] = ()) -> frozenset[int]:
    """The ids of this run's new listings that are not news (see the module
    docstring), marked in listings.attributes. `items` is everything the
    collector returned, before normalization and the prefilter; `readmitted`,
    the new listings its prefilter had dropped before (crawl._readmitted):
    backfill already, so they neither make a step nor get a mark. Fails
    open: the error goes to pipeline_errors ('news') and every listing is news."""
    if target["source"] in RECENT_SOURCES:
        return frozenset()
    try:
        return await _classify(target, items, result, run_id=run_id, first_run=first_run, complete=complete,
                               readmitted=frozenset(readmitted))
    except Exception:
        await runs.log_error("news", f"target:{target['id']}", traceback.format_exc())
        return frozenset()


async def _classify(target: dict[str, Any], items: Iterable[Any], result: IngestResult, *, run_id: int,
                    first_run: bool, complete: bool, readmitted: frozenset[int]) -> frozenset[int]:
    def mark(reason: str, prev_id: int | None = None) -> dict[str, Any]:
        return {"_not_news": {"reason": reason, "run_id": run_id, "target_id": target["id"], "prev_id": prev_id}}

    new = list(dict.fromkeys(e.listing_id for e in result.events if e.kind == "listing_new"))
    if result.ids:
        # What a run cut after its ingest (a restart) left without a look.
        async with connection() as cx:
            left = await listings.unclassified(cx, result.ids.values(), target_id=target["id"], run_id=run_id)
        new += [lid for lid in left if lid not in set(new)]
    new = [lid for lid in new if lid not in readmitted]
    if not new:
        return frozenset()
    if first_run:
        # Backfill already (scheduler.match_alert); marked for 2.5 only.
        async with connection() as cx:
            await listings.mark_not_news(cx, [(lid, mark(FIRST_RUN), None) for lid in new])
        return frozenset()
    max_age_days = int(await get_config("recommended_max_age_days", config.RECOMMENDED_MAX_AGE_DAYS))
    settings = await IngestConfig.load()
    # Only a complete read of a source whose reads are trusted whole tells the
    # old copy is gone: the list comparables() confirms with. Kavak,
    # autocosmos and usadossantafe cut their reads short without saying so.
    trusted = (await get_config("comparables", {}) or {}).get("confirm_sources") or ()
    reappearance = config.NEWS_GUARD_REAPPEARANCE and complete and target["source"] in trusted
    inventory = (target.get("query") or {}).get("inventory") is True
    step = config.NEWS_GUARD_STEP and not inventory and is_step(
        len(new), await runs.recent_ok_found(target["id"], exclude_run=run_id, n=STEP_RUNS))
    batch = sorted({str(item.listing_id) for item in items})
    marks: list[tuple[int, dict[str, Any], int | None]] = []
    reasons: Counter[str] = Counter()
    async with connection() as cx:
        for row in await listings.new_rows(cx, new):
            if _dated_news(row, max_age_days):
                continue
            if step:
                marks.append((row["id"], mark(STEP), None))
                reasons[STEP] += 1
                continue
            if not reappearance:
                continue
            old = await listings.find_reappeared(cx, row, batch_external_ids=batch,
                                                 window_days=settings.repost_window_days,
                                                 price_tol_pct=settings.repost_price_tol_pct,
                                                 km_tol=REAPPEARANCE_KM,
                                                 unsellered_hours=REAPPEARANCE_UNSELLERED_HOURS)
            if old is None:
                continue
            # The copy right before, not the chain's first one: comparables()
            # counts a repost while the copy it points to doesn't, so each
            # chain counts once. Only once E3 counts the live copy.
            repost_of = old["id"] if config.NEWS_LINK_REPOST else None
            drop = price_drop_pct(old, row)
            if drop is not None and drop >= settings.price_drop_min_pct:
                marks.append((row["id"], {"_republished": {"run_id": run_id, "target_id": target["id"],
                                                           "prev_id": old["id"], "drop_pct": drop}}, repost_of))
                reasons["republished"] += 1
            else:
                marks.append((row["id"], mark(REAPPEARANCE, old["id"]), repost_of))
                reasons[REAPPEARANCE] += 1
        await listings.mark_not_news(cx, marks)
    if reasons:
        log.info("target=%s %s: of %d new listings, %s", target["id"], target["source"], len(new),
                 ", ".join(f"{n} {reason}" for reason, n in sorted(reasons.items())))
    return frozenset(lid for lid, attrs, _ in marks if "_not_news" in attrs)

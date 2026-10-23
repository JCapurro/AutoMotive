"""Which new listings are not news, on the sources without publication dates
(docs/TECHNICAL_PLAN.md, sección 5.7).

Mercado Libre and Facebook read by publication date (collectors/_recency.py)
and are left alone. On every other source a listing is "new" when its
external_id was never stored, so old stock looks new when:
  - a read brings at once half the stock again (a collector deploy, a wider
    search, a read cut short before): the step;
  - a target's search was widened, and the read brings the stock its
    previous complete read left out by year or km (crawl_targets.query._read,
    read_envelope): the envelope. Not what a target reading the source's
    whole stock of its body type (or all of it) covers and never stored:
    that is new to the source;
  - the same car comes back under another ID after its old copy left the
    source: the reappearance, only on the sources whose reads are trusted
    whole. A republication at least price_drop_min_pct cheaper is still
    news, labelled "re-publicado" (_republished);
  - a target of UNDATED_SOURCES read nothing on its first run: crawl._run_one
    holds its bootstrap for EMPTY_FIRST_RUNS empty reads at most, so what it
    reads right after is that first run's backfill. A target of theirs back
    after a day inactive (NEWS_GUARD_REACTIVATION), or whose collector raises
    COVERAGE_VERSION, starts its bootstrap over (targets.sync_targets);
  - the target read past its searches' years (query.year_band, the
    reference band of pipeline/crawl.py): the band, which none of the
    target's searches matches and which only feeds comparables(). It
    doesn't make a step either; the envelope (query._read) includes it.
classify stores the step, the envelope, the reappearance and the band as
backfill for every search (seen on the web, never notified) and marks them
in listings.attributes._not_news {reason, run_id, target_id, prev_id}:
scheduler.match_alert keeps them backfill on a retry or for another target,
and count_after_expiry (2.5) never counts them. A first run's new listings
are marked 'first_run', only for 2.5: the target's next runs find them again
after its bootstrap. A listing with a recent publication date (v6) is always
news. Each rule has its switch in config (NEWS_GUARD_*); a failure leaves
every listing news, as before, except the band's: band_ids tells them from
the stored rows alone, and scheduler.process_batch asks it on every batch,
whatever classify did (it fails closed).

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
from db.repos import listings, runs, targets
from db.repos.config import get_config
from pipeline.ingest import IngestConfig, IngestResult, price_drop_pct

log = logging.getLogger("news")

FIRST_RUN, STEP, REAPPEARANCE, ENVELOPE, BAND = "first_run", "step", "reappearance", "envelope", "band"
# Old stock: backfill for every search on every run, never counted in 2.5.
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


def read_envelope(target: dict[str, Any], filters: dict[str, Any]) -> dict[str, Any] | None:
    """What a read of `target` with these collector filters
    (crawl.scraper_filters) covers: their year and km bounds, which a
    complete read keeps in crawl_targets.query._read for its next run's
    envelope (targets.finish_target). None for a target the envelope doesn't
    watch: of a source that reads by publication date (Mercado Libre,
    Facebook), by body type (its prefilter remembers what it dropped,
    prefilter_rejected) or a whole inventory (no bounds)."""
    if (target["source"] in RECENT_SOURCES or target.get("body_type")
            or (target.get("query") or {}).get("inventory") is True):
        return None
    bounds = {"year_min": filters.get("anio_min"), "year_max": filters.get("anio_max"),
              "km_max": filters.get("km_max")}
    return {k: v for k, v in bounds.items() if v is not None}


def is_band(row: dict[str, Any], query: dict[str, Any] | None) -> bool:
    """Whether a listing is one only the reference year band brought
    (crawl_targets.query.year_band, pipeline/crawl.py): its year past the
    target's year_min/year_max, which are its searches' own. No search of
    the target matches it (matching keeps the exact years): it feeds
    comparables(). An unknown year is inside, as matching lets it in."""
    q = query or {}
    year = row.get("year")
    if not q.get("year_band") or year is None:
        return False
    return ((q.get("year_min") is not None and year < int(q["year_min"]))
            or (q.get("year_max") is not None and year > int(q["year_max"])))


def band_ids(target: dict[str, Any], rows: Iterable[dict[str, Any]], *, max_age_days: int) -> frozenset[int]:
    """Of these stored rows of `target`'s read, the ones only its reference
    band brought (is_band) that are not news: old stock on a source without
    a publication window. Mercado Libre reads the band only in "Publicados
    hoy", so its band rows are news, and a recent publication date (v6) is
    always news. From the rows alone: scheduler.process_batch asks it on
    every batch, so a classify that failed, a retry or a restart never makes
    them news nor counts them in 2.5 (NEWS_GUARD_BAND)."""
    query = target.get("query") or {}
    if not config.NEWS_GUARD_BAND or target.get("source") in RECENT_SOURCES or not query.get("year_band"):
        return frozenset()
    return frozenset(r["id"] for r in rows if is_band(r, query) and not _dated_news(r, max_age_days))


def _core_share(items: Iterable[Any], query: dict[str, Any] | None) -> float:
    """The share of a read inside its searches' own years. The band adds its
    stock to every banded read's `found`, the step's base: measured against
    that core, a step needs the same new listings as before the band."""
    years = [getattr(item, "anio", None) for item in items]
    if not years:
        return 1.0
    return sum(1 for year in years if not is_band({"year": year}, query)) / len(years)


def _covered(row: dict[str, Any], wide: Iterable[dict[str, Any]]) -> bool:
    """Whether one of these targets (targets.whole_stock_targets) reads `row`
    on every run: the whole source, or its body type within what the
    target's prefilter keeps, not dropped by it before (prefilter_rejected).
    It would have stored the row if it were old stock (kavak 'suv' and a
    Ford EcoSport target widened to 2012)."""
    from pipeline.crawl import prefilter     # crawl imports this module
    for t in wide:
        if t.get("body_type") is None:
            return True
        if row.get("body_type") != t["body_type"] or row.get("external_id") in (t.get("prefilter_rejected") or ()):
            continue
        keep = prefilter(t)
        if keep is None or keep(row):
            return True
    return False


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


async def _step_base(target: dict[str, Any], run_id: int, share: float = 1.0) -> int | None:
    """What a step is measured against: the most one of the target's last
    ok runs that read something found, its core `share` of it (_core_share).
    A target whose ok runs all read nothing (an empty first read's hold
    ended) never loaded: 0, so its whole stock showing up is a step and its
    first few cars are news."""
    base = await runs.recent_ok_found(target["id"], exclude_run=run_id, n=STEP_RUNS)
    if base is None and await runs.empty_ok_streak(target["id"], exclude_run=run_id) > 0:
        return 0
    return base if base is None or share >= 1 else round(base * share)


async def classify(target: dict[str, Any], items: Iterable[Any], result: IngestResult, *, run_id: int,
                   first_run: bool, complete: bool, readmitted: Iterable[int] = ()) -> frozenset[int]:
    """The ids of this run's new listings that are not news (see the module
    docstring), marked in listings.attributes. `items` is everything the
    collector returned, before normalization and the prefilter; `readmitted`,
    the listings of the read its prefilter had dropped before
    (crawl._readmitted): backfill already, so they neither make a step nor
    get a mark. Fails
    open: the error goes to pipeline_errors ('news') and every listing is news,
    but the band's, which scheduler.process_batch tells apart (band_ids)."""
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
    query = target.get("query") or {}
    max_age_days = int(await get_config("recommended_max_age_days", config.RECOMMENDED_MAX_AGE_DAYS))
    banded = config.NEWS_GUARD_BAND and bool(query.get("year_band"))
    rows: list[dict[str, Any]] | None = None
    band: frozenset[int] = frozenset()
    if banded:
        async with connection() as cx:
            rows = await listings.new_rows(cx, new)
        band = band_ids(target, rows, max_age_days=max_age_days)
    if first_run:
        # Backfill already (scheduler.match_alert); marked for 2.5 only, but
        # the band for every target.
        async with connection() as cx:
            await listings.mark_not_news(cx, [(lid, mark(BAND if lid in band else FIRST_RUN), None)
                                              for lid in new])
        return band
    settings = await IngestConfig.load()
    # Only a complete read of a source whose reads are trusted whole tells the
    # old copy is gone: the list comparables() confirms with. Kavak,
    # autocosmos and usadossantafe cut their reads short without saying so.
    trusted = (await get_config("comparables", {}) or {}).get("confirm_sources") or ()
    reappearance = config.NEWS_GUARD_REAPPEARANCE and complete and target["source"] in trusted
    inventory = query.get("inventory") is True
    share = _core_share(items, query) if banded else 1.0
    step = config.NEWS_GUARD_STEP and not inventory and is_step(len(new) - len(band),
                                                                await _step_base(target, run_id, share))
    # The year and km the target's last complete read covered (the claimed
    # query's, from before any widening, the band included): outside them
    # is stock it left out.
    envelope = query.get("_read") if config.NEWS_GUARD_ENVELOPE else None
    wide = await targets.whole_stock_targets(target["source"]) if isinstance(envelope, dict) else []
    batch = sorted({str(item.listing_id) for item in items})
    marks: list[tuple[int, dict[str, Any], int | None]] = []
    reasons: Counter[str] = Counter()
    async with connection() as cx:
        for row in rows if rows is not None else await listings.new_rows(cx, new):
            if row["id"] in band:
                marks.append((row["id"], mark(BAND), None))
                reasons[BAND] += 1
                continue
            if _dated_news(row, max_age_days):
                continue
            if step:
                marks.append((row["id"], mark(STEP), None))
                reasons[STEP] += 1
                continue
            if isinstance(envelope, dict) and outside_envelope(row, envelope) and not _covered(row, wide):
                marks.append((row["id"], mark(ENVELOPE), None))
                reasons[ENVELOPE] += 1
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

"""Which new listings are not news, on the sources without publication dates
(docs/TECHNICAL_PLAN.md, sección 5.7).

Mercado Libre and Facebook read by publication date (collectors/_recency.py)
and are left alone. On every other source a listing is "new" when its
external_id was never stored, so old stock looks new when:
  - a read brings at once half the stock again (a collector deploy, a wider
    search, a read cut short before): the step;
  - a target's search was widened, and the read brings the stock its
    previous complete read left out by year or km (crawl_targets.query._read,
    read_envelope): the envelope. Not what another target would have stored
    if it were old stock (a whole body type or source within what its last
    read covered, a sibling model within its searches' years: _covered):
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
  - the target read past its searches' years for the first time
    (query.year_band, the reference band of pipeline/crawl.py): the band's
    stock its last complete read didn't cover (query._read), but what
    another target covers, as for the envelope (old_band).
classify stores the step, the envelope and the reappearance as backfill for
every search (seen on the web, never notified) and marks them in
listings.attributes._not_news {reason, run_id, target_id, prev_id}:
scheduler.match_alert keeps them backfill on a retry or for another target,
and count_after_expiry (2.5) never counts them. A first run's new listings
are marked 'first_run', and the band's first read 'band', both only for the
target that stored them: its searches never get them as news, 2.5 doesn't
count them for it, and another target that wants them (a body type, a
sibling model, a search whose years include them) still gets them as any
listing. A listing with a recent publication date (v6) is always news. Each
rule has its switch in config (NEWS_GUARD_*); a failure leaves every
listing news, as before, except the band's: band_ids tells it from the
stored rows alone, and scheduler.process_batch asks it on every batch,
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
MUTED = frozenset({STEP, REAPPEARANCE, ENVELOPE})
# Old stock only for the target that stored it (uncounted).
OWN = frozenset({FIRST_RUN, BAND})

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


def _bounds(filters: dict[str, Any]) -> dict[str, Any]:
    bounds = {"year_min": filters.get("anio_min"), "year_max": filters.get("anio_max"),
              "km_max": filters.get("km_max")}
    return {k: v for k, v in bounds.items() if v is not None}


def _reads_whole(target: dict[str, Any]) -> bool:
    """A target by body type or a whole inventory: it reads a whole stock."""
    return bool(target.get("body_type")) or (target.get("query") or {}).get("inventory") is True


def read_envelope(target: dict[str, Any], filters: dict[str, Any]) -> dict[str, Any] | None:
    """What a read of `target` with these collector filters
    (crawl.scraper_filters) covers: their year and km bounds, which a
    complete read keeps in crawl_targets.query._read for its next run's
    envelope (targets.finish_target). None for a target the envelope doesn't
    watch: of a source that reads by publication date (Mercado Libre,
    Facebook), or one reading a whole stock (read_covers)."""
    if target["source"] in RECENT_SOURCES or _reads_whole(target):
        return None
    return _bounds(filters)


def read_covers(target: dict[str, Any], filters: dict[str, Any]) -> dict[str, Any] | None:
    """What a read of a target reading a whole stock (a body type, an
    inventory) covers with these collector filters: their year and km
    bounds, the band included ({} for an inventory). A complete read keeps
    them in query._covers (targets.finish_target), for another target's
    rows (_covered), not as its own envelope: its collector drops what is
    past them before the prefilter (kavak's year_max), so prefilter_rejected
    never remembers that. None for any other target, or one of a source
    that reads by publication date."""
    if target["source"] in RECENT_SOURCES or not _reads_whole(target):
        return None
    return _bounds(filters)


def is_band(row: dict[str, Any], query: dict[str, Any] | None) -> bool:
    """Whether a listing is one only the reference year band brought
    (crawl_targets.query.year_band, pipeline/crawl.py): its year past the
    target's year_min/year_max, which are its searches' own. No search of
    the target matches it (matching keeps the exact years): it feeds
    comparables(). An unknown year is inside, as matching lets it in. Only
    the year: on deruedas a Stepway target reads Sandero cards too."""
    q = query or {}
    year = row.get("year")
    if not q.get("year_band") or year is None:
        return False
    return ((q.get("year_min") is not None and year < int(q["year_min"]))
            or (q.get("year_max") is not None and year > int(q["year_max"])))


def band_ids(target: dict[str, Any], rows: Iterable[dict[str, Any]], *, max_age_days: int) -> frozenset[int]:
    """Of these stored rows of `target`'s read, the ones only its reference
    band brought (is_band), on a source without a publication window:
    Mercado Libre reads the band only in "Publicados hoy", so its band rows
    are news, and a recent publication date (v6) is always news. From the
    rows alone, so scheduler.process_batch asks it on every batch: the
    target's own searches never get them as news (they can't match them)
    and 2.5 never counts them for it, whatever classify did. For any other
    search (one without a model) they are news like any listing, but for
    the band's first read (old_band), or when the band read before comes
    back at once (the band's step, _classify). NEWS_GUARD_BAND."""
    query = target.get("query") or {}
    if not config.NEWS_GUARD_BAND or target.get("source") in RECENT_SOURCES or not query.get("year_band"):
        return frozenset()
    return frozenset(r["id"] for r in rows if is_band(r, query) and not _dated_news(r, max_age_days))


def first_band_read(target: dict[str, Any], rows: Iterable[dict[str, Any]]) -> frozenset[int]:
    """Of these band rows (band_ids), the ones the target's last complete
    read didn't cover (query._read, read_envelope): read for the first time
    because the band was just turned on or a search moved its edge, they
    were listed while nobody here read those years. Old stock, unless
    another target covers it (old_band). A target without a last read (one
    by body type, whose prefilter remembers what it dropped, or none
    complete yet) never covered them."""
    read = (target.get("query") or {}).get("_read")

    def covered(row: dict[str, Any]) -> bool:
        year = row.get("year")
        if not isinstance(read, dict) or year is None:
            return isinstance(read, dict)
        return not ((read.get("year_min") is not None and year < read["year_min"])
                    or (read.get("year_max") is not None and year > read["year_max"]))
    return frozenset(r["id"] for r in rows if not covered(r))


def _band_read_before(query: dict[str, Any]) -> bool:
    """Whether the target's last complete read (query._read) already went
    past its searches' years by the band: then its `found` has the band in it."""
    read, band = query.get("_read"), int(query.get("year_band") or 0)
    if not isinstance(read, dict) or not band:
        return False
    low, high = query.get("year_min"), query.get("year_max")
    return ((low is not None and (read.get("year_min") is None or read["year_min"] <= int(low) - band))
            or (high is not None and (read.get("year_max") is None or read["year_max"] >= int(high) + band)))


def _core_share(items: Iterable[Any], query: dict[str, Any] | None) -> float:
    """The share of a read inside its searches' own years. Once the band is
    read, it adds its stock to every read's `found`, the step's base:
    measured against that core, a step needs the same new listings as
    before the band (_classify scales the base only then)."""
    years = [getattr(item, "anio", None) for item in items]
    if not years:
        return 1.0
    return sum(1 for year in years if not is_band({"year": year}, query)) / len(years)


def _covered(row: dict[str, Any], others: Iterable[dict[str, Any]]) -> bool:
    """Whether one of these other targets of the source
    (targets.covering_targets) would have stored `row` had it been listed
    before its last complete read: then it is new to the source.
      - One reading the whole source, or the row's body type, within the
        year and km that read sent its collector (query._covers, the band
        included) and not dropped by its prefilter then (prefilter_rejected):
        kavak 'suv' and a Ford EcoSport target widened to 2012. Its
        prefilter keeps or remembers all the rest, whatever its query is now.
      - One by model, the row's make and model, within its searches' own
        years and km and what its last read covered (_read, when it has one):
        deruedas 'Sandero 2019-2022' and a Sandero 2021 the band of
        'Stepway 2018-2020' stores first.
    Without a last read kept (a target by body type not read since), none."""
    for t in others:
        q = t.get("query") or {}
        if not _reads_whole(t):
            if _sibling(row, t):
                return True
            continue
        covers = q.get("_covers")
        if not isinstance(covers, dict) or outside_envelope(row, covers):
            continue
        if t.get("body_type") is None or (row.get("body_type") == t["body_type"] and row.get("external_id")
                                          not in (t.get("prefilter_rejected") or ())):
            return True
    return False


def _sibling(row: dict[str, Any], target: dict[str, Any]) -> bool:
    """Whether a target by model reads `row` in its searches' own years (not
    its band): the same make and model, and within its _read too once it has
    one, so a search widened since doesn't vouch for years it never read."""
    q = target.get("query") or {}
    if (not row.get("model") or str(row.get("make") or "").lower() != str(target.get("make") or "").lower()
            or row["model"].lower() != str(target.get("model") or "").lower()):
        return False
    core = {k: int(q[k]) for k in ("year_min", "year_max", "km_max") if q.get(k) is not None}
    read = q.get("_read")
    return not outside_envelope(row, core) and not (isinstance(read, dict) and outside_envelope(row, read))


async def old_band(target: dict[str, Any], rows: Iterable[dict[str, Any]]) -> frozenset[int]:
    """Of these band rows (band_ids), the band's first read (first_band_read)
    that no other target covers (_covered): old stock for every search of the
    batch. What another target covers and never stored is new to the source,
    as for the envelope. Reads the database only when there is a first read."""
    rows = list(rows)
    unread = first_band_read(target, rows)
    if not unread:
        return frozenset()
    others = await targets.covering_targets(target["source"], exclude=target.get("id"))
    return frozenset(r["id"] for r in rows if r["id"] in unread and not _covered(r, others))


def _mark(row: dict[str, Any] | None) -> dict[str, Any]:
    mark = ((row or {}).get("attributes") or {}).get("_not_news")
    return mark if isinstance(mark, dict) else {}


def muted(row: dict[str, Any] | None) -> bool:
    """A listing classify took for old stock: backfill for every search, on every run."""
    return _mark(row).get("reason") in MUTED


def uncounted(row: dict[str, Any] | None, target_id: int | None) -> bool:
    """Not counted in 2.5 by this target: old stock, or a listing it stored
    on its own first run or its band's first read. Another target's first
    run still counts: that target only found first what is new
    (test_count_after_expiry.py), and another target's band is its own
    business (a body type next to a model on Kavak)."""
    mark = _mark(row)
    return mark.get("reason") in MUTED or (mark.get("reason") in OWN and mark.get("target_id") == target_id)


def republished(row: dict[str, Any] | None) -> bool:
    """A cheaper republication classify let through: notified as "re-publicado"."""
    return bool(((row or {}).get("attributes") or {}).get("_republished"))


def _dated_news(row: dict[str, Any], max_age_days: int) -> bool:
    # scheduler imports crawl, which imports this module.
    from pipeline.scheduler import _is_recent
    return row.get("published_at") is not None and _is_recent(row, max_age_days)


async def _step_base(target: dict[str, Any], run_id: int) -> int | None:
    """What a step is measured against: the most one of the target's last
    ok runs that read something found. A target whose ok runs all read
    nothing (an empty first read's hold ended) never loaded: 0, so its whole
    stock showing up is a step and its first few cars are news."""
    base = await runs.recent_ok_found(target["id"], exclude_run=run_id, n=STEP_RUNS)
    if base is None and await runs.empty_ok_streak(target["id"], exclude_run=run_id) > 0:
        return 0
    return base


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
    if first_run:
        # Backfill already (scheduler.match_alert); marked for 2.5 only.
        async with connection() as cx:
            await listings.mark_not_news(cx, [(lid, mark(FIRST_RUN), None) for lid in new])
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
    # The band's first read is old stock, for this target only: what another
    # target wants of it (a body type, a sibling model) is still news there.
    unread = await old_band(target, [r for r in rows or () if r["id"] in band])
    settings = await IngestConfig.load()
    # Only a complete read of a source whose reads are trusted whole tells the
    # old copy is gone: the list comparables() confirms with. Kavak and
    # usadossantafe cut their reads short without saying so. Autocosmos, off
    # the list too, makes a read with a failed page partial, but still takes
    # its 20-page cap and a page without new cards for the whole read.
    trusted = (await get_config("comparables", {}) or {}).get("confirm_sources") or ()
    reappearance = config.NEWS_GUARD_REAPPEARANCE and complete and target["source"] in trusted
    inventory = query.get("inventory") is True
    # The step of the target's own news leaves the band's new listings out,
    # and once a read had the band its `found` is measured on its core
    # (right after it is turned on, the last reads' `found` is all core
    # already). The band read before is news to a search without a model,
    # so then everything but the band's first read, against the whole
    # `found`, is a step of the band's rows alone: old stock back at once on
    # a narrow search, or on a target that never loaded.
    step = band_step = False
    first: frozenset[int] = frozenset()
    if config.NEWS_GUARD_STEP and not inventory:
        base = await _step_base(target, run_id)
        again = banded and _band_read_before(query)
        core = round(base * _core_share(items, query)) if again and base else base
        step = is_step(len(new) - len(band), core)
        if again:
            first = first_band_read(target, [r for r in rows or () if r["id"] in band])
            band_step = is_step(len(new) - len(first), base)
    # The year and km the target's last complete read covered (the claimed
    # query's, from before any widening, the band included): outside them
    # is stock it left out.
    envelope = query.get("_read") if config.NEWS_GUARD_ENVELOPE else None
    wide = await targets.covering_targets(target["source"], exclude=target["id"]) if isinstance(envelope, dict) else []
    batch = sorted({str(item.listing_id) for item in items})
    marks: list[tuple[int, dict[str, Any], int | None]] = []
    reasons: Counter[str] = Counter()
    async with connection() as cx:
        for row in rows if rows is not None else await listings.new_rows(cx, new):
            if row["id"] in unread:
                marks.append((row["id"], mark(BAND), None))
                reasons[BAND] += 1
                continue
            if _dated_news(row, max_age_days):
                continue
            if step or (band_step and row["id"] in band and row["id"] not in first):
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

"""The color pass: a listing's body color from its photos, with the AI
(docs/PLAN_FILTRO_COLOR.md §8 is the contract, docs/COLOR.md the measurement).

Only where it is needed: active listings without a color from the source or
the text (normalization/color.py) that have a match in a live search. A
listing that is a candidate of a search with `filters.colors` is matched too
(an unknown color never fails the rule, intelligence/matching.py), so the
same rule covers both; those go first. Two ways in:

* `color_vision_pass`, every COLOR_VISION_TICK_SECONDS (scheduler.run_loop):
  the queue below, within the daily cap.
* `resolve_inline`, from scheduler.process_batch before notifying: the
  listings of the batch that pass a color search's other filters and have no
  color, with a ~20 s budget per batch. What isn't resolved in time is
  «color sin confirmar» for that notification and is filled later by the
  pass, as backfill: nothing is notified again (a stored match isn't new).

For each listing: up to 10 photos through pipeline/photo_hash.py's safe
downloader (public https, byte and pixel caps, one request per host per
second), Meta's hosts allowed here only (decision 1); each photo fitted to
512x384 JPEG in memory, never stored; then the provider's `listing_color`.

What is written (and only this, never a key attribute, so no snapshot and no
listing_updated):

    listings.color              the top color, or null (no_visible, below
                                app_config.color_vision.min_confidence)
    listings.attributes._color  normalization/color.build("vision", ...) plus
                                result, src (a key of the photos' paths, so a
                                re-signed Facebook URL is the same photo),
                                prompt, attempts and images_md5 (md5 of
                                listings.images, so the queue skips it in SQL)

The vision never overwrites a source or text color (merge_color, and the
UPDATE's own guard against a race with ingest). A listing whose _color
already says vision for the same photos and prompt is not read again; a
failed read is retried up to MAX_ATTEMPTS times for the same photos.

The daily cap is persistent: every call reserves a row in color_vision_runs
first, under an advisory lock, counting the rolling 24 h (the
description_llm_runs pattern); a reservation counts even if the call fails.
"""
from __future__ import annotations

import asyncio
import hashlib
import io
import logging
import time
import traceback
from collections.abc import Callable, Iterable, Mapping
from typing import Any
from urllib.parse import urlsplit

import httpx
from psycopg.types.json import Jsonb

import db
from db.repos.profiles import LIVE_SEARCHES
from db.repos.runs import log_error
from http_clients import async_client
from intelligence import photo_hash as phash
from intelligence.config import risk as risk_config
from llm import prompts
from llm.provider import LLMError, LLMProvider, build_provider
from llm.schemas import LISTING_COLOR_MAX_IMAGES
from normalization import color as colors
from pipeline import photo_hash
from pipeline.rescore import rescore_listings

log = logging.getLogger("color_vision")

MAX_PHOTOS = LISTING_COLOR_MAX_IMAGES          # 10
FIT = (512, 384)                               # docs/COLOR.md: each photo fitted to this, JPEG
JPEG_QUALITY = 85
QUEUE_LIMIT = 200
MAX_ATTEMPTS = 2
INLINE_BUDGET_SECONDS = 20.0
# Listings read at once; the host pacer keeps each host at one request per interval.
CONCURRENCY = 4
_LOCK = 7060141400

CONFIDENCE_RANK = {"baja": 0, "media": 1, "alta": 2}
DEFAULT_CONFIG: dict[str, Any] = {"enabled": False, "daily_cap": 3000, "min_confidence": "media",
                                  "skip_sources": []}
_CAP_BOUNDS = (0, 50_000)
# US$ per million tokens (gpt-6-luna, docs/PLAN_FILTRO_COLOR.md §6): the backfill's estimate.
PRICE_IN, PRICE_OUT = 0.10, 0.50


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def settings(raw: Any) -> dict[str, Any]:
    """app_config.color_vision with defaults and bounds. Without the row (a
    worker deployed before the migration) the pass is off: no spending."""
    out = {**DEFAULT_CONFIG, "skip_sources": []}
    if not isinstance(raw, Mapping):
        return out
    if isinstance(raw.get("enabled"), bool):
        out["enabled"] = raw["enabled"]
    cap = raw.get("daily_cap")
    if isinstance(cap, (int, float)) and not isinstance(cap, bool):
        out["daily_cap"] = int(min(max(cap, _CAP_BOUNDS[0]), _CAP_BOUNDS[1]))
    if raw.get("min_confidence") in CONFIDENCE_RANK:
        out["min_confidence"] = raw["min_confidence"]
    skip = raw.get("skip_sources")
    if isinstance(skip, list) and all(isinstance(s, str) for s in skip):
        out["skip_sources"] = list(skip)
    return out


def download_settings(risk: Any) -> dict[str, Any]:
    """The duplicates downloader's caps (risk.photo_hash): bytes, timeout and
    per-host pacing, the same for color."""
    ph = risk_config(risk)["photo_hash"]
    return {"max_bytes": int(ph["max_bytes"]), "timeout_seconds": float(ph["timeout_seconds"]),
            "per_host_interval_seconds": float(ph["per_host_interval_seconds"])}


# ---------------------------------------------------------------------------
# The answer → listings.color and attributes._color (pure)
# ---------------------------------------------------------------------------

def confidence(prob: int | float) -> str:
    return "alta" if prob >= 80 else "media" if prob >= 50 else "baja"


def photos_key(urls: Iterable[str]) -> str:
    """The photos a reading used, by host and path only: Facebook re-signs
    its URLs (the query) on every read, and it is the same photo."""
    parts = []
    for url in urls:
        try:
            p = urlsplit(url)
        except ValueError:
            continue
        parts.append(f"{(p.hostname or '').lower()}{p.path}")
    return hashlib.sha1("\n".join(parts).encode("utf-8")).hexdigest()[:20]


def _extra(value: dict[str, Any], *, src: str, attempts: int, result: str) -> dict[str, Any]:
    value.update(result=result, src=src, prompt=prompts.LISTING_COLOR_PROMPT_VERSION, attempts=attempts)
    return value


def from_answer(answer: Mapping[str, Any], *, photos: int, src: str, min_confidence: str,
                attempts: int = 1) -> tuple[str | None, dict[str, Any]]:
    """(listings.color, attributes._color) for a provider answer.

    The main color is the most probable one; its probability gives the
    confidence (alta >= 80, media >= 50, baja). Below `min_confidence` the
    main color is null but the candidates stay (matching counts those with
    prob >= 30). visible=false, or only sin_dato: result no_visible."""
    model = answer.get("model")
    ranked = sorted((c for c in answer.get("colors") or []
                     if isinstance(c, Mapping) and colors.is_code(c.get("color"))
                     and isinstance(c.get("prob"), int) and c["prob"] > 0),
                    key=lambda c: -c["prob"])
    if not answer.get("visible") or not ranked:
        return None, _extra(colors.build("vision", None, model=model, photos=photos), src=src,
                            attempts=attempts, result="no_visible")
    top = ranked[0]
    level = confidence(top["prob"])
    raw = ", ".join(f"{c['color']} {c['prob']}" for c in ranked)
    value = colors.build("vision", raw, confidence=level, model=model, candidates=ranked, photos=photos)
    if CONFIDENCE_RANK[level] < CONFIDENCE_RANK.get(min_confidence, 1):
        return None, _extra(value, src=src, attempts=attempts, result="low_confidence")
    return top["color"], _extra(value, src=src, attempts=attempts, result="ok")


def failure(*, photos: int, src: str, attempts: int, result: str, model: str | None = None) -> dict[str, Any]:
    """The _color of a reading that failed ("no_photos", "error"): color
    null, retried while attempts < MAX_ATTEMPTS for the same photos."""
    return _extra(colors.build("vision", None, model=model, photos=photos), src=src, attempts=attempts,
                  result=result)


def needs_vision(row: Mapping[str, Any], urls: list[str]) -> tuple[bool, int]:
    """(read it now, attempts so far for these photos). Never over a color of
    the source or the text; once per photos and prompt, a failure up to
    MAX_ATTEMPTS times."""
    current = (row.get("attributes") or {}).get("_color")
    if colors.rank(current) > colors.rank({"method": "vision"}):
        return False, 0
    if row.get("color") and colors.rank(current) == 0:
        return False, 0                     # a color without _color: someone else's, keep it
    if not urls:
        return False, 0
    if not isinstance(current, Mapping) or current.get("method") != "vision" \
            or current.get("src") != photos_key(urls) or current.get("prompt") != prompts.LISTING_COLOR_PROMPT_VERSION:
        return True, 0
    attempts = int(current.get("attempts") or 0)
    if current.get("result") in ("error", "no_photos"):
        return attempts < MAX_ATTEMPTS, attempts
    return False, attempts


# ---------------------------------------------------------------------------
# Photos
# ---------------------------------------------------------------------------

def prepare_image(data: bytes) -> bytes:
    """One photo as the measurement sent it: EXIF orientation, RGB, at most
    512 px, fitted to 512x384 on grey, JPEG. Raises on a bad or huge image."""
    from PIL import Image, ImageOps

    im = Image.open(io.BytesIO(data))
    if im.width * im.height > phash.MAX_IMAGE_PIXELS:
        raise phash.TooManyPixels("too many pixels")
    im = ImageOps.exif_transpose(im).convert("RGB")
    im.thumbnail((512, 512))
    w, h = FIT
    scale = min(w / im.width, h / im.height)
    im = im.resize((max(1, round(im.width * scale)), max(1, round(im.height * scale))))
    cell = Image.new("RGB", (w, h), (128, 128, 128))
    cell.paste(im, ((w - im.width) // 2, (h - im.height) // 2))
    buf = io.BytesIO()
    cell.save(buf, format="JPEG", quality=JPEG_QUALITY)
    return buf.getvalue()


class LockedPacer(photo_hash.HostPacer):
    """HostPacer for concurrent listings: one waiter per host at a time."""

    def __init__(self, interval: float, **kw: Any) -> None:
        super().__init__(interval, **kw)
        self._locks: dict[str, asyncio.Lock] = {}

    async def wait(self, url: str) -> None:
        host = (urlsplit(url).hostname or "").lower()
        async with self._locks.setdefault(host, asyncio.Lock()):
            await super().wait(url)


async def download(urls: list[str], fetch: photo_hash.Fetch, pacer: photo_hash.HostPacer) -> list[bytes]:
    """The photos that download and decode, ready for the provider."""
    out: list[bytes] = []
    for url in urls[:MAX_PHOTOS]:
        await pacer.wait(url)
        try:
            out.append(await asyncio.to_thread(prepare_image, await fetch(url)))
        except Exception as e:            # timeouts, HTTP errors, unreadable or huge images
            log.debug("color photo skipped: %s", type(e).__name__)
    return out


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

_QUEUE = LIVE_SEARCHES + """
SELECT l.id, l.source, l.images, l.color, l.attributes
  FROM listings l
 WHERE l.status = 'active' AND jsonb_array_length(l.images) > 0
   AND coalesce(l.attributes->'_color'->>'method', 'vision') = 'vision'
   AND (l.color IS NULL OR l.attributes->'_color'->>'method' = 'vision')
   AND NOT (l.source = ANY(%(skip)s))
   AND ((l.attributes->'_color'->>'images_md5') IS DISTINCT FROM md5(l.images::text)
        OR (l.attributes->'_color'->>'result' IN ('error', 'no_photos')
            AND coalesce((l.attributes->'_color'->>'attempts')::int, 0) < %(max_attempts)s))
   AND EXISTS (SELECT 1 FROM matches m JOIN live ON live.id = m.search_profile_id WHERE m.listing_id = l.id)
 ORDER BY EXISTS (SELECT 1 FROM matches m JOIN live ON live.id = m.search_profile_id
                    JOIN search_profiles sp ON sp.id = m.search_profile_id
                   WHERE m.listing_id = l.id AND jsonb_typeof(sp.filters->'colors') = 'array'
                     AND jsonb_array_length(sp.filters->'colors') > 0) DESC,
          l.last_seen_at DESC
 LIMIT %(limit)s
"""


async def queue(*, limit: int, skip_sources: list[str], source: str | None = None) -> list[dict[str, Any]]:
    """Active listings with a live match, without a color of the source or the
    text, whose photos the pass hasn't seen (images_md5); those of a color
    search first, then the newest. needs_vision has the final word."""
    sql, params = _QUEUE, {"skip": skip_sources, "limit": limit, "max_attempts": MAX_ATTEMPTS}
    if source:
        sql = sql.replace("AND NOT (l.source", "AND l.source = %(source)s AND NOT (l.source")
        params["source"] = source
    async with db.connection() as cx:
        return list(await (await cx.execute(sql, params)).fetchall())


async def reserve_run(listing_id: int, photos: int, daily_cap: int) -> int | None:
    """One call of the rolling-24 h budget (color_vision_runs), under an
    advisory lock; the reservation counts even if the call fails."""
    if daily_cap <= 0:
        return None
    async with db.connection() as cx:
        async with cx.transaction():
            await cx.execute("SELECT pg_advisory_xact_lock(%s)", (_LOCK,))
            used = await (await cx.execute(
                "SELECT count(*) AS n FROM color_vision_runs WHERE started_at > now() - interval '1 day'")
            ).fetchone()
            if int(used["n"]) >= daily_cap:
                return None
            run = await (await cx.execute(
                "INSERT INTO color_vision_runs (listing_id, photos) VALUES (%s, %s) RETURNING id",
                (listing_id, min(max(photos, 0), MAX_PHOTOS)))).fetchone()
            return int(run["id"])


async def finish_run(run_id: int, *, model: str | None, result: str | None, error: str | None) -> None:
    """The call's outcome on its reservation (the tokens go to the log and the pass's stats)."""
    async with db.connection() as cx:
        await cx.execute(
            "UPDATE color_vision_runs SET finished_at = now(), model = %s, result = %s, error = %s WHERE id = %s",
            (model, result, error, run_id))


async def save(listing_id: int, color: str | None, value: dict[str, Any]) -> bool:
    """listings.color and attributes._color (+ images_md5), only over no color
    or a vision one: a source or text color that ingest wrote meanwhile wins.
    Not a key attribute: no snapshot, no listing_updated."""
    async with db.connection() as cx:
        cur = await cx.execute(
            "UPDATE listings SET color = %s, attributes = attributes || jsonb_build_object('_color', "
            "       %s::jsonb || jsonb_build_object('images_md5', md5(images::text))) "
            " WHERE id = %s AND coalesce(attributes->'_color'->>'method', 'vision') = 'vision' "
            "   AND (color IS NULL OR attributes->'_color'->>'method' = 'vision')",
            (color, Jsonb(value), listing_id))
        return cur.rowcount > 0


async def mark_seen(listing_id: int) -> None:
    """The photos' URLs changed but not the photos (a re-signed URL): only the
    md5, so the queue stops returning it."""
    async with db.connection() as cx:
        await cx.execute(
            "UPDATE listings SET attributes = jsonb_set(attributes, '{_color,images_md5}', "
            "       to_jsonb(md5(images::text))) "
            " WHERE id = %s AND attributes->'_color'->>'method' = 'vision'", (listing_id,))


# ---------------------------------------------------------------------------
# The reader
# ---------------------------------------------------------------------------

class ColorVision:
    """Reads listings' colors within the config and the cap. Every method
    never raises for one listing; each listing is saved as soon as it's read."""

    def __init__(self, provider: LLMProvider, cfg: Mapping[str, Any], dl: Mapping[str, Any], *,
                 client: httpx.AsyncClient | None = None, resolve: photo_hash.Resolve = photo_hash.system_resolve,
                 pacer: photo_hash.HostPacer | None = None, dry_run: bool = False) -> None:
        self.provider, self.cfg, self.dl, self.dry_run = provider, dict(cfg), dict(dl), dry_run
        self._client, self._owned = client, client is None
        self._resolve = resolve
        self.pacer = pacer or LockedPacer(float(dl["per_host_interval_seconds"]))
        self.stats = {"listings": 0, "calls": 0, "colored": 0, "no_visible": 0, "low_confidence": 0,
                      "failed": 0, "capped": 0, "photos": 0, "tokens_in": 0, "tokens_out": 0}
        self.capped = False
        self.written: list[int] = []

    @classmethod
    async def create(cls, *, provider: LLMProvider | None = None, **kw: Any) -> "ColorVision | None":
        """None when the pass is off, has no cap, Pillow is missing or no
        provider can be built."""
        cfg = settings(await db.get_config("color_vision"))
        if not cfg["enabled"] or cfg["daily_cap"] <= 0:
            return None
        if not phash.available():
            log.warning("color vision: Pillow no instalado, el pase no corre")
            return None
        if provider is None:
            try:
                provider = build_provider()
            except Exception:
                log.warning("color vision: no LLM provider", exc_info=True)
                return None
        return cls(provider, cfg, download_settings(await db.get_config("risk")), **kw)

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = async_client(headers={"User-Agent": "Mozilla/5.0"}, cookies=None)
        return self._client

    async def close(self) -> None:
        if self._owned and self._client is not None:
            await self._client.aclose()
            self._client = None

    def skipped(self, row: Mapping[str, Any]) -> bool:
        return row.get("source") in self.cfg["skip_sources"]

    async def read(self, row: dict[str, Any]) -> bool:
        """Read one listing and save it; updates `row` (color, attributes)
        in place so a caller's scorer sees it. True if it was written."""
        if self.capped or self.skipped(row):
            return False
        urls = photo_hash.first_urls(row.get("images"), MAX_PHOTOS, allow_meta=True)
        need, attempts = needs_vision(row, urls)
        if not need:
            current = (row.get("attributes") or {}).get("_color")
            if isinstance(current, Mapping) and current.get("method") == "vision" and not self.dry_run:
                await mark_seen(row["id"])
            return False
        self.stats["listings"] += 1
        src = photos_key(urls)
        if self.dry_run:
            self.stats["photos"] += len(urls)       # what would be downloaded; nothing is
            return False
        fetch = photo_hash.fetcher(self.client, self.dl, self._resolve, allow_meta=True)
        images = await download(urls, fetch, self.pacer)
        self.stats["photos"] += len(images)
        if not images:
            await self._write(row, None, failure(photos=0, src=src, attempts=attempts + 1, result="no_photos"))
            return False
        run_id = await reserve_run(row["id"], len(images), int(self.cfg["daily_cap"]))
        if run_id is None:
            self.capped = True
            self.stats["capped"] += 1
            log.info("color vision: daily cap of %s calls reached", self.cfg["daily_cap"])
            return False
        answer: dict[str, Any] | None = None
        error: str | None = None
        result: str | None = None
        try:
            self.stats["calls"] += 1
            answer = await self.provider.listing_color(images)
            color, value = from_answer(answer, photos=len(images), src=src,
                                       min_confidence=self.cfg["min_confidence"])
            result = value["result"]
            self.stats["tokens_in"] += answer.get("tokens_in") or 0
            self.stats["tokens_out"] += answer.get("tokens_out") or 0
            self.stats[{"ok": "colored"}.get(result, result)] += 1
            return await self._write(row, color, value)
        except Exception as e:
            error = type(e).__name__ if not isinstance(e, LLMError) else str(e)[:200]
            result = "error"
            self.stats["failed"] += 1
            log.info("color vision: listing %s failed: %s", row.get("id"), type(e).__name__)
            await self._write(row, None, failure(photos=len(images), src=src, attempts=attempts + 1,
                                                 result="error", model=getattr(self.provider, "model", None)))
            return False
        finally:
            try:
                await asyncio.shield(finish_run(run_id, model=(answer or {}).get("model"), result=result,
                                                error=error))
            except Exception as e:
                log.warning("color vision: run completion unavailable (%s)", type(e).__name__)

    async def _write(self, row: dict[str, Any], color: str | None, value: dict[str, Any]) -> bool:
        attrs = row.get("attributes") or {}
        if self.dry_run or colors.merge_color(attrs.get("_color"), value) is None:
            return False
        if not await save(row["id"], color, value):
            return False
        row["color"] = color
        row["attributes"] = {**attrs, "_color": value}
        if color:
            # Only a color changes a match's color rule (a null one is «sin confirmar» either way).
            self.written.append(row["id"])
        return True

    async def read_many(self, rows: Iterable[dict[str, Any]], stop: asyncio.Event | None = None) -> int:
        """Read rows, CONCURRENCY at a time. Returns how many were written."""
        sem = asyncio.Semaphore(CONCURRENCY)
        written = 0

        async def one(row: dict[str, Any]) -> None:
            nonlocal written
            async with sem:
                if (stop is not None and stop.is_set()) or self.capped:
                    return
                try:
                    if await self.read(row):
                        written += 1
                except Exception:
                    await log_error("color_vision", f"listing:{row.get('id')}", traceback.format_exc())

        await asyncio.gather(*(one(r) for r in rows))
        return written


# ---------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------

async def color_vision_pass(stop: asyncio.Event | None = None, *, limit: int = QUEUE_LIMIT,
                            reader: ColorVision | None = None) -> dict[str, int]:
    """One pass over the queue. Never raises."""
    done: dict[str, int] = {}
    owned = reader is None
    try:
        reader = reader or await ColorVision.create()
        if reader is None:
            return done
        rows = await queue(limit=limit, skip_sources=reader.cfg["skip_sources"])
        await reader.read_many(rows, stop)
        done = dict(reader.stats)
        if reader.written:
            # The color rule of their matches goes from «sin confirmar» to a
            # value: re-scored, never notified (a match that now fails is deleted).
            done["rescored"] = await rescore_listings(reader.written)
        if reader.stats["listings"]:
            log.info("color vision: %s", done)
    except Exception:
        await log_error("color_vision", "pass", traceback.format_exc())
    finally:
        if owned and reader is not None:
            await reader.close()
    return done


async def run_loop(stop: asyncio.Event, seconds: float) -> None:
    """color_vision_pass now and every `seconds` until stopped (started by
    scheduler.run_loop). Off in app_config, each round is one config read."""
    while not stop.is_set():
        try:
            await color_vision_pass(stop)
        except Exception:
            log.exception("color vision pass failed")
        try:
            await asyncio.wait_for(stop.wait(), timeout=seconds)
        except asyncio.TimeoutError:
            pass


def inline_wanted(alerts: Iterable[Mapping[str, Any]], candidates: Callable[[Mapping[str, Any]], Iterable[int]],
                  rows: Mapping[int, Mapping[str, Any]]) -> list[int]:
    """The listings of a batch worth reading before notifying: candidates
    (`candidates(profile)`, the ones its other filters pass) of a search
    with filters.colors, without a color."""
    out: list[int] = []
    for alert in alerts:
        profile = alert.get("profile") or {}
        if not colors.wanted_colors(profile.get("filters") or {}):
            continue
        for lid in candidates(profile):
            row = rows.get(lid)
            if row is not None and not row.get("color") and lid not in out:
                out.append(lid)
    return out


async def resolve_inline(rows: list[dict[str, Any]], *, budget: float = INLINE_BUDGET_SECONDS,
                         reader: ColorVision | None = None) -> int:
    """Read these rows' colors within `budget` seconds, updating them in
    place. What isn't read in time stays unknown and the pass fills it later.
    Never raises; returns how many were written."""
    if not rows:
        return 0
    owned = reader is None
    started = time.monotonic()
    try:
        reader = reader or await ColorVision.create()
        if reader is None:
            return 0
        rows = [r for r in rows if not reader.skipped(r)]
        task = asyncio.ensure_future(reader.read_many(rows))
        done, _ = await asyncio.wait({task}, timeout=max(0.0, budget - (time.monotonic() - started)))
        if task in done:
            return task.result()
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass
        written = sum(1 for r in rows if ((r.get("attributes") or {}).get("_color") or {}).get("method") == "vision"
                      and r.get("color"))
        log.info("color vision inline: budget of %.0f s over, %d of %d read", budget, written, len(rows))
        return written
    except Exception:
        await log_error("color_vision", "inline", traceback.format_exc())
        return 0
    finally:
        if owned and reader is not None:
            await reader.close()


def estimated_cost(tokens_in: int, tokens_out: int) -> float:
    return tokens_in / 1e6 * PRICE_IN + tokens_out / 1e6 * PRICE_OUT


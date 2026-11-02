"""The photo hash pass (PAR-02 resto,
docs/superpowers/specs/2026-11-02-par02-resto-design.md, decision 5).
OFF by default (app_config.risk.photo_hash.enabled = false) until Juan
approves it: with it off, nothing is downloaded.

At the end of each enrichment pass (pipeline/enrich.py), with its own budget:
the first risk.photo_hash_count photos of the listings in
db/repos/duplicates.photo_hash_queue get a perceptual hash
(intelligence/photo_hash.py), stored in listings.attributes._photo_hashes:

    {"v": 1, "urls": [...], "hashes": ["hex" | null, ...], "at": iso,
     "attempts": n, "error": str | null}

A listing is hashed again only when its first N URLs change (attempts back to
0) or when a photo failed and attempts < max_attempts: never an endless retry.
Every download reserves its images in photo_hash_runs first (rolling 24 h,
daily_image_cap; a reservation counts even if it fails). Downloads: public
https URLs already stored, no cookies, at most max_bytes (Content-Length and
streamed), only image/*, one image per host every per_host_interval_seconds,
never a source in skip_sources (Facebook and Instagram by default) nor an IP
literal or localhost host. Without Pillow the pass logs once and does nothing.
After hashing, the duplicate detection runs for those listings
(pipeline/risk_duplicates.detect_for).
"""
from __future__ import annotations

import asyncio
import ipaddress
import logging
import time
import traceback
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Mapping
from urllib.parse import urlsplit

import httpx

import db
from db.repos import duplicates as repo
from db.repos.runs import log_error
from http_clients import async_client
from intelligence import photo_hash
from intelligence.config import risk as risk_config
from notifications.media import image_urls

log = logging.getLogger("photo_hash")

VERSION = 1
QUEUE_LIMIT = 200
_ERROR_MAX = 300
_pillow_reported = False


class DownloadError(Exception):
    pass


def first_urls(images: Any, n: int) -> list[str]:
    """The first n photo URLs that may be downloaded (https, a host name)."""
    out = []
    for url in image_urls(images, limit=max(n, 1) * 3):
        if downloadable(url):
            out.append(url)
        if len(out) == n:
            break
    return out


def downloadable(url: str) -> bool:
    try:
        parts = urlsplit(url)
    except ValueError:
        return False
    host = (parts.hostname or "").lower()
    if parts.scheme != "https" or not host or host == "localhost" or host.endswith(".localhost"):
        return False
    try:
        ipaddress.ip_address(host)
        return False                       # an IP literal: never a CDN photo
    except ValueError:
        return True


def needs_hash(stored: Any, urls: list[str], max_attempts: int) -> tuple[bool, int]:
    """(hash it now, attempts so far for these URLs)."""
    if not urls:
        return False, 0
    if not isinstance(stored, Mapping) or stored.get("v") != VERSION or stored.get("urls") != urls:
        return True, 0
    attempts = int(stored.get("attempts") or 0)
    hashes = stored.get("hashes") or []
    complete = len(hashes) == len(urls) and all(photo_hash.valid(h) for h in hashes)
    return (not complete and attempts < max_attempts), attempts


Fetch = Callable[[str], Awaitable[bytes]]


def fetcher(client: httpx.AsyncClient, cfg: Mapping[str, Any]) -> Fetch:
    """Download one image within max_bytes and timeout_seconds."""
    max_bytes = int(cfg["max_bytes"])

    async def fetch(url: str) -> bytes:
        async with client.stream("GET", url, timeout=float(cfg["timeout_seconds"]), follow_redirects=True) as r:
            if r.status_code != 200:
                raise DownloadError(f"HTTP {r.status_code}")
            kind = r.headers.get("content-type", "").split(";")[0].strip().lower()
            if not kind.startswith("image/"):
                raise DownloadError(f"not an image ({kind or 'no content-type'})")
            length = r.headers.get("content-length")
            if length and length.isdigit() and int(length) > max_bytes:
                raise DownloadError("too large")
            if not downloadable(str(r.url)):
                raise DownloadError("redirected to a disallowed URL")
            chunks, size = [], 0
            async for chunk in r.aiter_bytes():
                size += len(chunk)
                if size > max_bytes:
                    raise DownloadError("too large")
                chunks.append(chunk)
            return b"".join(chunks)

    return fetch


class HostPacer:
    """At most one request per host every `interval` seconds."""

    def __init__(self, interval: float, clock: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], Awaitable[None]] = asyncio.sleep) -> None:
        self.interval, self.clock, self.sleep = interval, clock, sleep
        self.last: dict[str, float] = {}

    async def wait(self, url: str) -> None:
        host = (urlsplit(url).hostname or "").lower()
        if self.interval > 0 and host in self.last:
            wait = self.last[host] + self.interval - self.clock()
            if wait > 0:
                await self.sleep(wait)
        self.last[host] = self.clock()


async def hash_listing(row: Mapping[str, Any], urls: list[str], attempts: int, fetch: Fetch,
                       pacer: HostPacer) -> dict[str, Any]:
    """The new _photo_hashes value; never raises for a bad photo."""
    hashes: list[str | None] = []
    errors: list[str] = []
    for url in urls:
        await pacer.wait(url)
        try:
            data = await fetch(url)
            hashes.append(await asyncio.to_thread(photo_hash.phash, data))
        except photo_hash.PillowMissing:
            raise
        except Exception as e:              # timeouts, HTTP errors, unreadable images
            hashes.append(None)
            errors.append(f"{type(e).__name__}: {e}"[:100])
    return {"v": VERSION, "urls": urls, "hashes": hashes, "at": datetime.now(timezone.utc).isoformat(),
            "attempts": attempts + 1, "error": "; ".join(errors)[:_ERROR_MAX] or None}


async def _report_missing_pillow() -> None:
    global _pillow_reported
    if not _pillow_reported:
        _pillow_reported = True
        await log_error("photo_hash", "pillow", "Pillow no instalado: el hash de fotos no corre")


async def photo_hash_pass(stop: asyncio.Event | None = None, *, client: httpx.AsyncClient | None = None,
                          pacer: HostPacer | None = None) -> dict[str, int]:
    """One pass over the queue. Returns {listings, images, hashed}. Never raises."""
    done = {"listings": 0, "images": 0, "hashed": 0}
    try:
        cfg = risk_config(await db.get_config("risk"))
        ph = cfg["photo_hash"]
        if not ph["enabled"]:
            return done
        if not photo_hash.available():
            await _report_missing_pillow()
            return done
        queue = await repo.photo_hash_queue(limit=QUEUE_LIMIT, skip_sources=ph["skip_sources"],
                                            km_tol_pct=cfg["cross_source"]["km_tol_pct"],
                                            price_tol_pct=cfg["cross_source"]["price_tol_pct"])
        owned = client is None
        client = client or async_client(headers={"User-Agent": "Mozilla/5.0"}, cookies=None)
        pacer = pacer or HostPacer(float(ph["per_host_interval_seconds"]))
        fetch = fetcher(client, ph)
        hashed_ids: list[int] = []
        try:
            for row in queue:
                if stop is not None and stop.is_set():
                    break
                if row["source"] in ph["skip_sources"]:
                    continue
                urls = first_urls(row.get("images"), int(cfg["photo_hash_count"]))
                need, attempts = needs_hash(row.get("photo_hashes"), urls, int(ph["max_attempts"]))
                if not need:
                    continue
                run_id = await repo.reserve_photo_run(row["id"], len(urls), int(ph["daily_image_cap"]))
                if run_id is None:
                    log.info("photo hash: daily cap of %s images reached", ph["daily_image_cap"])
                    break
                value: dict[str, Any] | None = None
                try:
                    value = await hash_listing(row, urls, attempts, fetch, pacer)
                    await repo.save_photo_hashes(row["id"], value)
                finally:
                    n = sum(1 for h in (value or {}).get("hashes", []) if h)
                    await repo.finish_photo_run(run_id, hashed=n, error=(value or {}).get("error")
                                                if value else "interrupted")
                done["listings"] += 1
                done["images"] += len(urls)
                done["hashed"] += n
                if n:
                    hashed_ids.append(row["id"])
        finally:
            if owned:
                await client.aclose()
        if done["listings"]:
            log.info("photo hash: %d listings, %d images, %d hashed", done["listings"], done["images"],
                     done["hashed"])
        if hashed_ids:
            from pipeline.risk_duplicates import detect_for
            await detect_for(hashed_ids)
    except photo_hash.PillowMissing:
        await _report_missing_pillow()
    except Exception:
        await log_error("photo_hash", "pass", traceback.format_exc())
    return done

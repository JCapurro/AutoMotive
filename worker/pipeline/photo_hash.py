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
never a source in skip_sources (Facebook and Instagram by default: facebook,
onlycarsusados, sc_clasificados) nor a Meta image host (BLOCKED_HOSTS, whatever
the config says), an IP literal or a localhost host. The color pass
(pipeline/color_vision.py) reuses this downloader with `allow_meta=True`, the
only caller that may fetch Meta hosts (docs/PLAN_FILTRO_COLOR.md, decision 1);
the duplicates pass never passes it. Redirects are followed by
hand, at most MAX_REDIRECTS, and every hop is checked the same way before it is
requested, its host name resolved first: one that resolves to a non-public
address (private, loopback, link-local, reserved) is never requested. Without
Pillow the pass logs once and does nothing.
After hashing, the duplicate detection runs for those listings
(pipeline/risk_duplicates.detect_for).
"""
from __future__ import annotations

import asyncio
import ipaddress
import logging
import socket
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
MAX_REDIRECTS = 3
# Facebook and Instagram images (signed URLs, terms of use: spec question 6).
BLOCKED_HOSTS = ("fbcdn.net", "facebook.com", "fbsbx.com", "cdninstagram.com", "instagram.com")
_ERROR_MAX = 300
_pillow_reported = False


class DownloadError(Exception):
    pass


def first_urls(images: Any, n: int, *, allow_meta: bool = False) -> list[str]:
    """The first n photo URLs that may be downloaded (https, a host name)."""
    out = []
    for url in image_urls(images, limit=max(n, 1) * 3):
        if downloadable(url, allow_meta=allow_meta):
            out.append(url)
        if len(out) == n:
            break
    return out


def meta_host(host: str) -> bool:
    return any(host == b or host.endswith("." + b) for b in BLOCKED_HOSTS)


def downloadable(url: str, *, allow_meta: bool = False) -> bool:
    """A public https URL with a host name. Meta's image hosts only with
    `allow_meta` (the color pass; never the duplicates pass)."""
    try:
        parts = urlsplit(url)
    except ValueError:
        return False
    host = (parts.hostname or "").lower()
    if parts.scheme != "https" or not host or host == "localhost" or host.endswith(".localhost"):
        return False
    if not allow_meta and meta_host(host):
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
Resolve = Callable[[str], Awaitable[list[str]]]


async def system_resolve(host: str) -> list[str]:
    infos = await asyncio.get_running_loop().getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    return [info[4][0] for info in infos]


def public_address(address: str) -> bool:
    try:
        ip = ipaddress.ip_address(address.split("%")[0])
    except ValueError:
        return False
    return ip.is_global and not ip.is_multicast


def fetcher(client: httpx.AsyncClient, cfg: Mapping[str, Any], resolve: Resolve = system_resolve, *,
            allow_meta: bool = False) -> Fetch:
    """Download one image within max_bytes and timeout_seconds. Every hop is
    checked with the same `allow_meta`."""
    max_bytes = int(cfg["max_bytes"])
    timeout = float(cfg["timeout_seconds"])

    async def check(url: str) -> None:
        if not downloadable(url, allow_meta=allow_meta):
            raise DownloadError("disallowed URL")
        host = urlsplit(url).hostname or ""
        try:
            addresses = await asyncio.wait_for(resolve(host), timeout)
        except (OSError, asyncio.TimeoutError) as e:
            raise DownloadError(f"cannot resolve {host}") from e
        if not addresses or not all(public_address(a) for a in addresses):
            raise DownloadError("host resolves to a non-public address")

    async def fetch(url: str) -> bytes:
        for _ in range(MAX_REDIRECTS + 1):
            await check(url)
            async with client.stream("GET", url, timeout=timeout, follow_redirects=False) as r:
                if r.is_redirect and r.headers.get("location"):
                    url = str(r.url.join(r.headers["location"]))
                    continue
                if r.status_code != 200:
                    raise DownloadError(f"HTTP {r.status_code}")
                kind = r.headers.get("content-type", "").split(";")[0].strip().lower()
                if not kind.startswith("image/"):
                    raise DownloadError(f"not an image ({kind or 'no content-type'})")
                length = r.headers.get("content-length")
                if length and length.isdigit() and int(length) > max_bytes:
                    raise DownloadError("too large")
                chunks, size = [], 0
                async for chunk in r.aiter_bytes():
                    size += len(chunk)
                    if size > max_bytes:
                        raise DownloadError("too large")
                    chunks.append(chunk)
                return b"".join(chunks)
        raise DownloadError("too many redirects")

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


def seen_value(stored: Any, urls: list[str]) -> dict[str, Any]:
    """What a listing that needs no download keeps in _photo_hashes."""
    if isinstance(stored, Mapping) and stored.get("v") == VERSION and stored.get("urls") == urls:
        return dict(stored)
    return {"v": VERSION, "urls": urls, "hashes": [], "at": datetime.now(timezone.utc).isoformat(),
            "attempts": 0, "error": None if urls else "no downloadable photo"}


async def photo_hash_pass(stop: asyncio.Event | None = None, *, client: httpx.AsyncClient | None = None,
                          pacer: HostPacer | None = None, resolve: Resolve = system_resolve) -> dict[str, int]:
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
                                            price_tol_pct=cfg["cross_source"]["price_tol_pct"],
                                            version=VERSION, max_attempts=int(ph["max_attempts"]))
        owned = client is None
        client = client or async_client(headers={"User-Agent": "Mozilla/5.0"}, cookies=None)
        pacer = pacer or HostPacer(float(ph["per_host_interval_seconds"]))
        fetch = fetcher(client, ph, resolve)
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
                    # Done, out of attempts or nothing to download: the queue
                    # returned it because its images changed; say it was seen.
                    await repo.mark_photo_hashes_seen(row["id"], seen_value(row.get("photo_hashes"), urls))
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

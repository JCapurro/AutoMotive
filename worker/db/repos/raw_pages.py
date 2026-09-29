"""raw_pages: the last detail page of each listing, compressed (normalization v3).

A detail page is fetched once (enriched_at) and then only by the watchlist.
Keeping it lets a better parser read it again without asking the source
(tools/reprocess.py --raw). Only the slimmed HTML is kept (collectors
BaseScraper.slim_page), gzip'd; the nightly retention drops old ones.
"""
from __future__ import annotations

import gzip
from dataclasses import dataclass
from datetime import datetime
from typing import AsyncIterator

from db.pool import connection


@dataclass(frozen=True)
class RawPage:
    listing_id: int
    source: str
    external_id: str
    url: str
    status: int
    fetched_at: datetime
    parser_version: int
    html: str


def compress(html: str) -> bytes:
    return gzip.compress(html.encode("utf-8"), compresslevel=6)


def decompress(blob: bytes) -> str:
    return gzip.decompress(bytes(blob)).decode("utf-8")


async def save(listing_id: int, *, url: str, status: int, parser_version: int, html: str) -> None:
    async with connection() as cx:
        await cx.execute(
            "INSERT INTO raw_pages (listing_id, kind, url, status, parser_version, html_gz) "
            "VALUES (%s, 'detail', %s, %s, %s, %s) "
            "ON CONFLICT (listing_id, kind) DO UPDATE SET url = excluded.url, "
            "  status = excluded.status, fetched_at = now(), "
            "  parser_version = excluded.parser_version, html_gz = excluded.html_gz",
            (listing_id, url, status, parser_version, compress(html)))


async def iter_for_reparse(*, source: str | None = None, below_version: dict[str, int] | None = None,
                           batch: int = 50) -> AsyncIterator[RawPage]:
    """Stored detail pages, oldest listing first. `below_version`: per source,
    only the pages parsed with an older DETAIL_PARSER_VERSION."""
    last_id = 0
    while True:
        sql = ("SELECT r.listing_id, l.source, l.external_id, r.url, r.status, r.fetched_at, "
               "       r.parser_version, r.html_gz "
               "  FROM raw_pages r JOIN listings l ON l.id = r.listing_id "
               " WHERE r.kind = 'detail' AND r.listing_id > %s")
        params: list = [last_id]
        if source:
            sql += " AND l.source = %s"
            params.append(source)
        async with connection() as cx:
            rows = await (await cx.execute(sql + " ORDER BY r.listing_id LIMIT %s",
                                           [*params, batch])).fetchall()
        if not rows:
            return
        for r in rows:
            last_id = r["listing_id"]
            if below_version is not None and r["parser_version"] >= below_version.get(r["source"], 0):
                continue
            yield RawPage(r["listing_id"], r["source"], r["external_id"], r["url"], r["status"],
                          r["fetched_at"], r["parser_version"], decompress(r["html_gz"]))


async def mark_parsed(listing_id: int, parser_version: int) -> None:
    """The stored page was read again with this parser version (tools/reprocess.py)."""
    async with connection() as cx:
        await cx.execute("UPDATE raw_pages SET parser_version = %s WHERE listing_id = %s AND kind = 'detail'",
                         (parser_version, listing_id))


async def purge_older_than(days: int) -> int:
    async with connection() as cx:
        cur = await cx.execute("DELETE FROM raw_pages WHERE fetched_at < now() - make_interval(days => %s)",
                               (days,))
        return cur.rowcount

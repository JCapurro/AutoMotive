"""Fetching and parsing helpers shared by the detail parsers (fetch_detail)."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Iterator, Sequence

import httpx
from bs4 import BeautifulSoup

from ._browser import browser_context


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "es-AR,es;q=0.9",
}


@dataclass
class Page:
    status: int
    url: str        # final URL, after redirects
    html: str


async def fetch_page(url: str, *, timeout: float = 25.0) -> Page:
    """Plain HTTP GET. Raises on network errors; any HTTP status is returned."""
    async with httpx.AsyncClient(timeout=timeout, headers=HEADERS, follow_redirects=True) as cx:
        r = await cx.get(url)
    return Page(r.status_code, str(r.url), r.text)


async def fetch_rendered(url: str, *, storage_state: str | None = None,
                         settle_ms: int = 2_500, expand: Sequence[str] = ()) -> Page:
    """Load the page in the shared headless browser, for pages that render client-side.

    `expand`: texts of buttons that reveal the rest of the page ("Ver más"
    under a truncated description); the first visible one inside the main
    region is clicked before the page is captured.
    """
    async with browser_context(storage_state=storage_state) as ctx:
        page = await ctx.new_page()
        try:
            response = await page.goto(url, timeout=45_000, wait_until="domcontentloaded")
            await page.wait_for_timeout(settle_ms)
            if expand:
                await _expand(page, expand)
            return Page(response.status if response else 0, page.url, await page.content())
        finally:
            await page.close()


async def _expand(page, texts: Sequence[str]) -> bool:
    scope = page.locator("[role='main']")
    if not await scope.count():
        scope = page.locator("body")
    for text in texts:
        for locator in (scope.get_by_role("button", name=text, exact=True),
                        scope.get_by_text(text, exact=True)):
            try:
                target = locator.first
                if await locator.count() and await target.is_visible():
                    await target.click(timeout=3_000)
                    await page.wait_for_timeout(600)
                    return True
            except Exception:
                continue
    return False


def slim_html(html: str, *, keep: str | None = None, scripts_with: str | None = None) -> str:
    """The page without what no parser reads, for raw_pages: scripts (but
    JSON-LD, and those containing `scripts_with`), styles, SVG icons, iframes.
    `keep`: only that element (Facebook parses its main region alone)."""
    doc = soup(html)
    if keep and (el := doc.select_one(keep)) is not None:
        doc = soup(str(el))
    for tag in doc.select("script, style, svg, noscript, iframe, link[rel='stylesheet']"):
        if tag.name == "script" and ((tag.get("type") or "").lower() == "application/ld+json"
                                     or (scripts_with and scripts_with in (tag.string or ""))):
            continue
        tag.decompose()
    return str(doc)


def soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "lxml")


def json_ld(doc: BeautifulSoup) -> Iterator[dict[str, Any]]:
    """Every schema.org object in the page's JSON-LD blocks (flattening @graph)."""
    for tag in doc.select("script[type='application/ld+json']"):
        try:
            data = json.loads(tag.string or "")
        except (TypeError, ValueError):
            continue
        for item in data if isinstance(data, list) else [data]:
            if not isinstance(item, dict):
                continue
            yield from (g for g in item.get("@graph", [item]) if isinstance(g, dict))


def json_ld_of_type(doc: BeautifulSoup, *types: str) -> dict[str, Any] | None:
    return next((d for d in json_ld(doc) if d.get("@type") in types), None)


def text_of(el) -> str | None:
    if el is None:
        return None
    text = el.get_text(" ", strip=True)
    return re.sub(r"\s+", " ", text) or None


def multiline_text(el) -> str | None:
    """Text with paragraph breaks kept (descriptions)."""
    if el is None:
        return None
    lines = [ln.strip() for ln in el.get_text("\n").splitlines()]
    text = "\n".join(ln for ln in lines if ln)
    return text or None


def to_int(value: Any) -> int | None:
    digits = re.sub(r"\D", "", str(value or ""))
    return int(digits) if digits else None


def dedupe(urls: list[str | None]) -> list[str]:
    return list(dict.fromkeys(u for u in urls if u))

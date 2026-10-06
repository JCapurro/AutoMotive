"""Public-catalog transport and small parsing helpers for regional sources."""
from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse

import httpx

from normalization.money import parse_number
from normalization.normalize import normalize_brand, normalize_text
from ._http import HEADERS, Page
from ._dates import parse_publication_date
from .base import BaseScraper, CollectorBlocked, Listing


def timestamp(value: str | None) -> int | None:
    return parse_publication_date(value)


def price(text: str | None) -> tuple[float | None, str | None]:
    if not text:
        return None, None
    match = re.search(r"(?i)(U\$[DS]|US\$|USD|\$)\s*([\d.,]+)", text)
    if not match:
        return None, None
    amount = parse_number(match[2])
    return (amount if amount and amount > 1 else None,
            "ARS" if match[1] == "$" else "USD")


def matches_vehicle(item: Listing, filters: dict) -> bool:
    """Standalone probes also respect make/model; inventory targets pass {}."""
    title = normalize_text(item.titulo)
    make = normalize_brand(filters.get("marca"))
    model = normalize_text(filters.get("modelo"))
    if make:
        if item.marca:
            if normalize_brand(item.marca) != make:
                return False
        elif not re.search(r"\b" + re.escape(make) + r"\b", title):
            if not (make == "volkswagen" and re.search(r"\bvw\b", title)):
                return False
    if model and not re.search(r"\b" + re.escape(model) + r"\b",
                               normalize_text(item.modelo) if item.modelo else title):
        return False
    return BaseScraper.matches_filters(item, filters)


class PublicCatalogScraper(BaseScraper):
    BASE = ""
    INVENTORY_TARGET = True

    def __init__(self, *, transport: httpx.AsyncBaseTransport | None = None):
        self.transport = transport

    async def _get(self, url: str) -> Page:
        host = urlparse(self.BASE).hostname
        if urlparse(url).hostname != host:
            raise ValueError(f"{self.name}: URL outside the source")
        async with httpx.AsyncClient(headers=HEADERS, timeout=35, follow_redirects=False,
                                     transport=self.transport) as client:
            for _ in range(6):
                response = await client.get(url)
                if not response.is_redirect:
                    page = Page(response.status_code, str(response.url), response.text)
                    self.check_status(page.status)
                    return page
                target = urljoin(str(response.url), response.headers.get("location", ""))
                if urlparse(target).hostname != host or urlparse(target).scheme not in ("http", "https"):
                    raise CollectorBlocked(f"{self.name}: unexpected redirect")
                url = target
        raise CollectorBlocked(f"{self.name}: too many redirects")

    @classmethod
    def check_status(cls, status: int) -> None:
        if status in (401, 403, 429):
            raise CollectorBlocked(f"{cls.name}: HTTP {status}")
        if status not in (200, 404, 410):
            raise RuntimeError(f"{cls.name}: HTTP {status}")

    async def fetch_detail_page(self, url: str) -> Page:
        return await self._get(url)

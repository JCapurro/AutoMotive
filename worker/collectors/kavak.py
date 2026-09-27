"""Kavak Argentina scraper.

Kavak is a SPA — listings render via JS only. Uses the shared headless
browser. Cards have stable per-listing URLs at `/ar/venta/{slug}` which
encode marca, modelo, version and year.
"""
from __future__ import annotations
from dataclasses import replace
import re

from .base import BaseScraper, Listing
from ._browser import browser_context
from normalization.fx import usd_ars_rate


_KM_RE = re.compile(r"([\d\.\,]+)\s*km", re.IGNORECASE)
_YEAR_RE = re.compile(r"\b(19[8-9]\d|20[0-3]\d)\b")
_PRICE_RE = re.compile(r"(US\$|u\$s|\$)\s*([\d\.\,]+)", re.IGNORECASE)


def _slug(s: str) -> str:
    s = s.lower().strip()
    s = s.translate(str.maketrans("áéíóúñü", "aeiounu"))
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def _to_int(s: str) -> int | None:
    digits = re.sub(r"\D", "", s or "")
    return int(digits) if digits else None


class KavakScraper(BaseScraper):
    name = "kavak"
    BASE = "https://www.kavak.com/ar/usados"

    @staticmethod
    def matches_filters(item: Listing, f: dict) -> bool:
        filters = {k: v for k, v in f.items() if k != "vendedor"}
        wanted_currency = (filters.get("moneda") or "").upper()
        item_currency = (item.moneda or "").upper()
        if item.precio and wanted_currency and item_currency and wanted_currency != item_currency:
            rate = usd_ars_rate()
            if wanted_currency == "USD" and item_currency == "ARS":
                item = replace(item, precio=item.precio / rate, moneda="USD")
            elif wanted_currency == "ARS" and item_currency == "USD":
                item = replace(item, precio=item.precio * rate, moneda="ARS")
        return BaseScraper.matches_filters(item, filters)

    def _build_url(self, f: dict) -> str:
        parts = [_slug(f[k]) for k in ("marca", "modelo") if f.get(k)]
        if not parts:
            return self.BASE
        return f"{self.BASE}/" + "-".join(parts)

    async def search(self, filters: dict) -> list[Listing]:
        url = self._build_url(filters)
        out: list[Listing] = []
        seen: set[str] = set()
        async with browser_context() as ctx:
            page = await ctx.new_page()
            try:
                await page.goto(url, timeout=45_000, wait_until="domcontentloaded")
                # Kavak lazy-loads via scroll
                for _ in range(4):
                    await page.mouse.wheel(0, 4000)
                    await page.wait_for_timeout(900)
                cards = await page.locator("a[data-testid][href*='/ar/venta/']").all()
                for c in cards:
                    href = await c.get_attribute("href") or ""
                    if not href:
                        continue
                    full_url = href if href.startswith("http") else "https://www.kavak.com" + href
                    # listing id = URL slug (stable per car)
                    lid = re.sub(r".*/ar/venta/", "", full_url).split("?")[0].rstrip("/")
                    if not lid or lid in seen:
                        continue
                    seen.add(lid)

                    text = (await c.inner_text()).strip()
                    # Extract price (Kavak shows financiación + cash; pick the cash $ ARS value)
                    precio = moneda = None
                    pm = _PRICE_RE.search(text)
                    if pm:
                        sym, num = pm.groups()
                        moneda = "USD" if "us" in sym.lower() else "ARS"
                        precio = float(_to_int(num) or 0) or None

                    km = None
                    if (m := _KM_RE.search(text)):
                        km = _to_int(m.group(1))

                    anio = None
                    if (m := _YEAR_RE.search(text)):
                        anio = int(m.group(1))

                    # Title from URL slug — more reliable than the text blob
                    slug = lid.replace("_", " ").replace("-", " ")
                    title = slug[:200].title()

                    listing = Listing(
                        source=self.name,
                        listing_id=lid,
                        titulo=title,
                        url=full_url,
                        precio=precio,
                        moneda=moneda,
                        marca=filters.get("marca"),
                        modelo=filters.get("modelo"),
                        anio=anio,
                        km=km,
                        vendedor="concesionaria",  # Kavak is dealer-only
                    )
                    self.annotate_partial_price(listing)
                    if self.matches_filters(listing, filters):
                        out.append(listing)
            finally:
                await page.close()
        return out

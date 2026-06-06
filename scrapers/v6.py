"""V6 (v6.com.ar) scraper — AR used cars marketplace.

Listings render client-side via JS. Filters supported via URL:
    brand=<marca>      — e.g. brand=toyota
    model=<modelo>     — e.g. model=corolla
    search=<query>     — free-text fallback
    sort=recent        — newest first
Year/price/km filters aren't honored server-side, so we apply them
client-side via BaseScraper.matches_filters.

Card markup uses `tc-v2-*` classes which have been stable since the
2024 redesign.
"""
from __future__ import annotations
import re
import urllib.parse

from .base import BaseScraper, Listing
from ._browser import browser_context
from ._dates import parse_relative_date


_PRICE_RE = re.compile(r"([\d\.\,]+)\s*(USD|U\$S|US\$|\$|ARS)", re.IGNORECASE)
_KM_RE = re.compile(r"([\d\.\,]+)\s*km", re.IGNORECASE)
_YEAR_RE = re.compile(r"\b(19[8-9]\d|20[0-3]\d)\b")


def _slug(s: str) -> str:
    s = s.lower().strip()
    s = s.translate(str.maketrans("áéíóúñü", "aeiounu"))
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def _to_int(s: str | None) -> int | None:
    digits = re.sub(r"\D", "", s or "")
    return int(digits) if digits else None


def _parse_price(txt: str) -> tuple[float | None, str | None]:
    m = _PRICE_RE.search(txt or "")
    if not m:
        return None, None
    num, cur = m.groups()
    moneda = "USD" if cur.upper() in ("USD", "U$S", "US$") else "ARS"
    digits = re.sub(r"[^\d]", "", num)
    return (float(digits) if digits else None), moneda


class V6Scraper(BaseScraper):
    name = "v6"
    BASE = "https://www.v6.com.ar/publicaciones"

    def _build_url(self, f: dict) -> str:
        qs: dict[str, str] = {"sort": "recent"}
        if f.get("marca"):
            qs["brand"] = _slug(f["marca"])
        q_keys = ("modelo", "version") if qs.get("brand") else ("marca", "modelo", "version")
        q = " ".join(str(f[k]).strip().lower() for k in q_keys if f.get(k)).strip()
        if q:
            qs["search"] = q
        return f"{self.BASE}?{urllib.parse.urlencode(qs)}"

    async def search(self, filters: dict) -> list[Listing]:
        url = self._build_url(filters)
        out: list[Listing] = []
        seen: set[str] = set()
        async with browser_context() as ctx:
            page = await ctx.new_page()
            try:
                await page.goto(url, timeout=45_000, wait_until="domcontentloaded")
                await page.wait_for_timeout(2_500)
                # v6 uses infinite scroll; load up to ~3 batches
                for _ in range(4):
                    await page.mouse.wheel(0, 5_000)
                    await page.wait_for_timeout(1_000)

                anchors = await page.locator("a.tc-v2-link[href^='/auto/']").all()
                for a in anchors:
                    href = (await a.get_attribute("href")) or ""
                    if not href:
                        continue
                    full_url = "https://www.v6.com.ar" + href.split("?")[0]
                    # listing id = trailing 10-char alphanumeric segment
                    m = re.search(r"-([A-Za-z0-9]{10})$", href)
                    lid = m.group(1) if m else href.rsplit("/", 1)[-1]
                    if lid in seen:
                        continue
                    seen.add(lid)

                    # Pull text fields by selector (one DOM round-trip per card)
                    title_el = a.locator(".tc-v2-title").first
                    version_el = a.locator(".tc-v2-version").first
                    price_el = a.locator(".tc-v2-price").first
                    location_el = a.locator(".tc-v2-location").first

                    title = (await title_el.inner_text()).strip() if await title_el.count() else ""
                    if await version_el.count():
                        version = (await version_el.inner_text()).strip()
                        # version is nested inside title; tc-v2-title text already includes it.
                        if version not in title:
                            title = f"{title} {version}".strip()

                    price_txt = (await price_el.inner_text()).strip() if await price_el.count() else ""
                    precio, moneda = _parse_price(price_txt)

                    location = (await location_el.inner_text()).strip() if await location_el.count() else None

                    # Detail tags (year, km, transmission, fuel)
                    tags = await a.locator(".tc-v2-detail-tag").all_inner_texts()
                    anio = km = transmision = combustible = None
                    for t in tags:
                        t = t.strip()
                        if not anio and (m := _YEAR_RE.search(t)):
                            anio = int(m.group(1)); continue
                        if not km and (m := _KM_RE.search(t)):
                            km = _to_int(m.group(1)); continue
                        tl = t.lower()
                        if not transmision and tl in ("mt", "manual"):
                            transmision = "Manual"; continue
                        if not transmision and tl in ("at", "automática", "automatica", "cvt", "dsg"):
                            transmision = "Automática"; continue
                        if not combustible and tl in ("nafta", "diésel", "diesel", "gnc", "híbrido", "hibrido", "eléctrico", "electrico"):
                            combustible = t; continue

                    img_el = a.locator("img.tc-v2-img").first
                    img = await img_el.get_attribute("src") if await img_el.count() else None

                    days_el = a.locator(".tc-v2-days-badge").first
                    published_at = None
                    if await days_el.count():
                        published_at = parse_relative_date(await days_el.inner_text())

                    listing = Listing(
                        source=self.name,
                        listing_id=lid,
                        titulo=title[:200] or "(sin título)",
                        url=full_url,
                        precio=precio,
                        moneda=moneda,
                        marca=filters.get("marca"),
                        modelo=filters.get("modelo"),
                        anio=anio,
                        km=km,
                        ubicacion=location,
                        combustible=combustible,
                        transmision=transmision,
                        published_at=published_at,
                        extra={"img": img} if img else {},
                    )
                    self.annotate_partial_price(listing)
                    if self.matches_filters(listing, filters):
                        out.append(listing)
            finally:
                await page.close()
        return out

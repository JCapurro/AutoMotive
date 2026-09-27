"""Facebook Marketplace scraper.

Requires an authenticated session. Run once interactively to log in:

    python -m collectors.facebook

That saves cookies/storage to FB_STORAGE_STATE; subsequent searches reuse
the session in headless mode via the shared browser instance.

Notes:
- FB rotates DOM frequently. Selectors here target stable cues
  (`/marketplace/item/{digits}` URL pattern) and parse text content
  defensively rather than relying on fragile class names.
- Search city slug is derived from `filters['ubicacion']` when possible;
  otherwise defaults to `buenosaires`.
"""
from __future__ import annotations
import asyncio
import re
import urllib.parse
from pathlib import Path

from playwright.async_api import async_playwright

from .base import BaseScraper, Listing
from ._browser import browser_context
from ._dates import parse_relative_date
from config import FB_STORAGE_STATE
from normalization.geo import nearest_known_location_name


_PRICE_RE = re.compile(r"(US\$|u\$s|USD|ARS|\$)\s*([\d\.\,]+)", re.IGNORECASE)
_MIN_USD_VEHICLE_PRICE = 1_000
_MIN_ARS_VEHICLE_PRICE = 500_000
# FB renders kms as "115 km", "115.000 km" or "115 mil km" (= 115.000 km).
_KM_RE = re.compile(r"(\d[\d\.\,]*)\s*(mil\s+)?km", re.IGNORECASE)
_YEAR_RE = re.compile(r"\b(19[8-9]\d|20[0-3]\d)\b")


# Common AR cities → FB Marketplace location slugs (best-effort)
CITY_SLUGS = {
    "buenos aires":     "buenosaires",
    "capital federal":  "buenosaires",
    "caba":             "buenosaires",
    "córdoba":          "cordoba",
    "cordoba":          "cordoba",
    "rosario":          "rosario",
    "mendoza":          "mendoza",
    "tucumán":          "sanmigueldetucuman",
    "tucuman":          "sanmigueldetucuman",
    "la plata":         "laplata",
    "mar del plata":    "mardelplata",
    "salta":            "salta",
    "santa fe":         "santafe",
    "neuquén":          "neuquen",
    "neuquen":          "neuquen",
    "bahía blanca":     "bahiablanca",
    "bahia blanca":     "bahiablanca",
}


def _city_slug(ubic: str | None) -> str:
    if not ubic:
        return "buenosaires"
    key = ubic.lower().strip()
    return CITY_SLUGS.get(key, "buenosaires")


def _city_slug_from_origin(f: dict) -> str:
    try:
        lat = float(f["origin_lat"])
        lon = float(f["origin_lon"])
    except (KeyError, TypeError, ValueError):
        return "buenosaires"
    nearest = nearest_known_location_name(lat, lon, CITY_SLUGS.keys())
    return CITY_SLUGS.get(nearest or "", "buenosaires")


def _parse_price(txt: str) -> tuple[float | None, str | None]:
    m = _PRICE_RE.search(txt or "")
    if not m:
        return None, None
    sym, num = m.groups()
    digits = re.sub(r"[^\d]", "", num)
    if not digits:
        return None, None
    amount = float(digits)
    sym_l = sym.lower()
    if "us" in sym_l:
        moneda = "USD"
    elif "ars" in sym_l:
        moneda = "ARS"
    else:
        # FB Argentina commonly renders USD listings as "$ 11,900" and ARS
        # vehicle listings as "$ 11,900,000". Treat plain "$" in millions as ARS.
        moneda = "ARS" if amount >= 1_000_000 else "USD"
    if moneda == "USD" and amount < _MIN_USD_VEHICLE_PRICE:
        return None, None
    if moneda == "ARS" and amount < _MIN_ARS_VEHICLE_PRICE:
        return None, None
    return amount, moneda


def _parse_km(txt: str) -> int | None:
    m = _KM_RE.search(txt or "")
    if not m:
        return None
    digits = re.sub(r"[^\d]", "", m.group(1))
    if not digits:
        return None
    n = int(digits)
    if m.group(2):  # "mil km" modifier → multiply
        n *= 1000
    return n


def _parse_year(txt: str) -> int | None:
    m = _YEAR_RE.search(txt or "")
    return int(m.group(1)) if m else None


def _query_terms(f: dict) -> list[str]:
    return [
        str(f[k]).strip().lower()
        for k in ("marca", "modelo", "version")
        if f.get(k) and str(f[k]).strip()
    ]


def _matches_query_text(text: str, f: dict) -> bool:
    haystack = (text or "").lower()
    return all(term in haystack for term in _query_terms(f))


def _title_from_card(label: str, lines: list[str]) -> str:
    label_title = (label or "").split(",", 1)[0].strip()
    if label_title:
        return label_title
    for line in lines:
        if _PRICE_RE.search(line):
            continue
        if line.lower() in {"just listed", "publicado recientemente"}:
            continue
        return line
    return ""


_DATE_LINE_PREFIXES = ("hace ",)
_DATE_LINE_VALUES = {"ayer", "hoy", "anteayer", "just listed", "publicado recientemente"}


def _looks_like_location(line: str, title: str) -> bool:
    """True if `line` could plausibly be a city/area string.

    FB cards mix order — sometimes the last line is km, sometimes the
    publication date, sometimes the location. So we go line-by-line and
    reject anything that matches another field's shape.
    """
    s = (line or "").strip()
    if not s or len(s) < 3:
        return False
    low = s.lower()
    if any(low.startswith(p) for p in _DATE_LINE_PREFIXES):
        return False
    if low in _DATE_LINE_VALUES:
        return False
    if _PRICE_RE.search(s):
        return False
    if _KM_RE.search(s):
        return False
    if _YEAR_RE.fullmatch(s):
        return False
    if title and low == title.strip().lower():
        return False
    # Pure-digit lines (mileage without "km", phone numbers, etc.)
    if re.fullmatch(r"[\d\.\,\s]+", s):
        return False
    return True


def _extract_location(lines: list[str], title: str) -> str | None:
    """Scan the card lines for the first one that looks like a location."""
    for ln in lines:
        if _looks_like_location(ln, title):
            return ln.strip()
    return None


class FacebookMarketplaceScraper(BaseScraper):
    name = "facebook"

    def _build_url(self, f: dict) -> str:
        slug = _city_slug(f.get("ubicacion")) if f.get("ubicacion") else _city_slug_from_origin(f)
        params: dict[str, str] = {}
        q = " ".join(f[k] for k in ("marca", "modelo", "version") if f.get(k)).strip()
        if q:
            params["query"] = q
        if f.get("precio_min"):
            params["minPrice"] = str(int(f["precio_min"]))
        if f.get("precio_max"):
            params["maxPrice"] = str(int(f["precio_max"]))
        if f.get("anio_min"):
            params["minYear"] = str(int(f["anio_min"]))
        if f.get("anio_max"):
            params["maxYear"] = str(int(f["anio_max"]))
        if f.get("km_max"):
            params["maxMileage"] = str(int(f["km_max"]))
        if f.get("transmision"):
            t = f["transmision"].lower()
            if "auto" in t:
                params["transmissionType"] = "automatic"
            elif "manual" in t:
                params["transmissionType"] = "manual"
        if q:
            return (f"https://www.facebook.com/marketplace/{slug}/search/"
                    f"?{urllib.parse.urlencode(params)}")
        params["sortBy"] = "creation_time_descend"
        return (f"https://www.facebook.com/marketplace/{slug}/vehicles/"
                f"?{urllib.parse.urlencode(params)}")

    async def search(self, filters: dict) -> list[Listing]:
        if not Path(FB_STORAGE_STATE).exists():
            print(f"[facebook] No session at {FB_STORAGE_STATE}. "
                  "Run: python -m collectors.facebook   to log in once.")
            return []

        url = self._build_url(filters)
        out: list[Listing] = []
        seen: set[str] = set()
        async with browser_context(storage_state=FB_STORAGE_STATE) as ctx:
            page = await ctx.new_page()
            try:
                await page.goto(url, timeout=45_000, wait_until="domcontentloaded")
                # FB renders the feed asynchronously; settle then scroll
                await page.wait_for_timeout(3_500)
                for _ in range(3):
                    await page.mouse.wheel(0, 4_000)
                    await page.wait_for_timeout(900)

                anchors = await page.locator("a[href*='/marketplace/item/']").all()
                for a in anchors:
                    href = (await a.get_attribute("href")) or ""
                    m = re.search(r"/marketplace/item/(\d+)", href)
                    if not m:
                        continue
                    lid = m.group(1)
                    if lid in seen:
                        continue
                    seen.add(lid)

                    full_url = "https://www.facebook.com" + href.split("?")[0]
                    text = (await a.inner_text()).strip()
                    label = await a.get_attribute("aria-label") or ""
                    if not _matches_query_text(f"{label}\n{text}", filters):
                        continue

                    # FB cards typically read: "PRICE\nTITLE\nLOCATION\nHace X días"
                    lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
                    price, moneda = _parse_price(text)
                    if price is None:
                        price, moneda = _parse_price(label)
                    title = _title_from_card(label, lines) or text[:120]

                    # Pull publication-date string from any "Hace ..." line
                    date_line = next(
                        (ln for ln in lines if ln.lower().startswith("hace ")
                         or ln.lower() in ("ayer", "hoy", "anteayer")),
                        None,
                    )
                    published_at = parse_relative_date(date_line)

                    # Try to grab thumbnail from the anchor's img
                    img = None
                    try:
                        img_el = a.locator("img").first
                        if await img_el.count() > 0:
                            img = await img_el.get_attribute("src")
                    except Exception:
                        pass

                    listing = Listing(
                        source=self.name,
                        listing_id=lid,
                        titulo=title[:200],
                        url=full_url,
                        precio=price,
                        moneda=moneda,
                        marca=filters.get("marca"),
                        modelo=filters.get("modelo"),
                        anio=_parse_year(text),
                        km=_parse_km(text),
                        ubicacion=_extract_location(lines, title),
                        published_at=published_at,
                        extra={"img": img} if img else {},
                    )
                    self.annotate_partial_price(listing)
                    if self.matches_filters(listing, filters):
                        out.append(listing)
            finally:
                await page.close()
        return out


# ------ Interactive login: `python -m collectors.facebook` ------
async def _login_and_save() -> None:
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False)
        ctx = await browser.new_context(locale="es-AR")
        page = await ctx.new_page()
        await page.goto("https://www.facebook.com/login")
        print("Iniciá sesión en la ventana abierta. Cuando estés en la home, "
              "volvé a esta consola y presioná Enter.")
        await asyncio.get_event_loop().run_in_executor(None, input, "")
        await ctx.storage_state(path=FB_STORAGE_STATE)
        print(f"[facebook] sesión guardada en {FB_STORAGE_STATE}")
        await ctx.close()
        await browser.close()


if __name__ == "__main__":
    asyncio.run(_login_and_save())

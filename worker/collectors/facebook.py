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
import unicodedata
import urllib.parse
from pathlib import Path

from playwright.async_api import async_playwright

from .base import BaseScraper, CollectorBlocked, Listing, ListingDetail
from ._browser import browser_context
from ._dates import parse_relative_date
from ._http import Page, fetch_rendered, slim_html, soup
from config import FB_STORAGE_STATE
from normalization.geo import nearest_known_location_name
from normalization.money import MIN_ARS_VEHICLE_PRICE, MIN_USD_VEHICLE_PRICE, plain_dollar_currency


_PRICE_RE = re.compile(r"(US\$|u\$s|USD|ARS|\$)\s*([\d\.\,]+)", re.IGNORECASE)
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
        moneda = plain_dollar_currency(amount)
    if moneda == "USD" and amount < MIN_USD_VEHICLE_PRICE:
        return None, None
    if moneda == "ARS" and amount < MIN_ARS_VEHICLE_PRICE:
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


def parse_card(href: str, text: str, label: str = "", img: str | None = None) -> Listing | None:
    """One marketplace card from its link, visible text and aria-label.

    FB cards typically read: "PRICE\nTITLE\nLOCATION\nHace X días".
    Make/model are left to normalization: the search query is not evidence.
    """
    m = re.search(r"/marketplace/item/(\d+)", href or "")
    if not m:
        return None
    lines = [ln.strip() for ln in (text or "").split("\n") if ln.strip()]
    price, moneda = _parse_price(text)
    if price is None:
        price, moneda = _parse_price(label)
    title = _title_from_card(label, lines) or (text or "")[:120]

    # Pull publication-date string from any "Hace ..." line
    date_line = next(
        (ln for ln in lines if ln.lower().startswith("hace ")
         or ln.lower() in ("ayer", "hoy", "anteayer")),
        None,
    )
    path = href.split("?")[0]
    return Listing(
        source="facebook",
        listing_id=m.group(1),
        titulo=title[:200],
        url=path if path.startswith("http") else "https://www.facebook.com" + path,
        precio=price,
        moneda=moneda,
        anio=_parse_year(text),
        km=_parse_km(text),
        ubicacion=_extract_location(lines, title),
        published_at=parse_relative_date(date_line),
        imagenes=[img] if img else [],
    )


# ---------- item page (fetch_detail) ----------

_GONE_TEXTS = ("ya no esta disponible", "no longer available", "este articulo se vendio",
               "this item has been sold", "el contenido no esta disponible")
_DESCRIPTION_HEADERS = ("descripcion del vendedor", "seller's description")
# Where the description ends: the seller box, the "Ver más" of a text that
# wasn't expanded, the map ("· La ubicación es aproximada") and the other
# ads Facebook suggests below ("Sugerencias de hoy", with their prices).
_DESCRIPTION_STOP = ("informacion del vendedor", "seller information", "detalles del vendedor",
                     "ver menos", "see less", "enviar un mensaje", "send seller a message",
                     "la ubicacion es aproximada", "location is approximate",
                     "sugerencias de hoy", "today's picks")
# Buttons: a whole line, so "Ver más fotos en Instagram" stays in the text.
_DESCRIPTION_STOP_LINES = ("ver mas", "see more", "enviar mensaje", "send message")
_EXPAND = ("Ver más", "See more")
_SUGGESTIONS = ("sugerencias de hoy", "today's picks")
_DETAILS_HEADERS = ("acerca de este vehiculo", "about this vehicle")
_SELLER_HEADERS = ("informacion del vendedor", "seller information")


def _plain(s: str) -> str:
    """Lowercase, no accents, no leading bullet ("· La ubicación es aproximada")."""
    s = "".join(c for c in unicodedata.normalize("NFD", s.lower())
                if unicodedata.category(c) != "Mn")
    return s.lstrip("·•-–— \t")


def _after_colon(line: str) -> str:
    return line.split(":", 1)[1].strip() if ":" in line else line


def _own_images(main) -> list[str | None]:
    """The listing's photos: the CDN images above "Sugerencias de hoy"."""
    out: list[str | None] = []
    for node in main.descendants:
        if isinstance(node, str):
            if _plain(node.strip()).startswith(_SUGGESTIONS):
                break
        elif node.name == "img" and re.search(r"scontent|fbcdn", node.get("src") or ""):
            out.append(node.get("src"))
    return out


def parse_detail(html: str, url: str, status: int = 200) -> ListingDetail:
    """An item page, read from the visible text of its main region: FB's
    class names are generated, so only text cues are stable."""
    if status == 404:
        return ListingDetail(url, gone=True, gone_reason="404")
    doc = soup(html)
    main = doc.select_one("[role='main']") or doc.body
    if main is None:
        raise ValueError(f"facebook detail without content: {url}")
    lines = [ln.strip() for ln in main.get_text("\n").splitlines() if ln.strip()]
    plain = [_plain(ln) for ln in lines]
    # Below "Sugerencias de hoy" are other ads: their prices, titles and
    # words ("concesionaria", "vendido") aren't this listing's.
    if (end := next((i for i, p in enumerate(plain) if p.startswith(_SUGGESTIONS)), None)) is not None:
        lines, plain = lines[:end], plain[:end]
    joined = " ".join(plain)
    if reason := next((t for t in _GONE_TEXTS if t in joined), None):
        return ListingDetail(url, gone=True, gone_reason=reason)
    m = re.search(r"/marketplace/item/(\d+)", url)
    h1 = main.select_one("h1")
    title = (h1.get_text(" ", strip=True) if h1 else None) or (lines[0] if lines else None)
    if not m or not title:
        raise ValueError(f"facebook detail without id/title: {url}")

    # The price sits by the title; the description below may quote others.
    price = moneda = None
    head = next((i for i, p in enumerate(plain) if p in _DESCRIPTION_HEADERS or p in _DETAILS_HEADERS),
                len(lines))
    for ln in lines[:head]:
        price, moneda = _parse_price(ln)
        if price is not None:
            break

    # "Publicado hace 2 días en Vicente López, BA"
    published_at = location = None
    for ln, pl in zip(lines, plain):
        if pl.startswith(("publicado hace", "listed ")):
            hm = re.match(r"(?:publicado|listed)\s+(.*?)(?:\s+(?:en|in)\s+(.+))?$", ln, re.IGNORECASE)
            if hm:
                published_at = parse_relative_date(hm.group(1))
                location = hm.group(2)
            break

    # "Acerca de este vehículo": "Conducido 112.000 kilómetros", "Transmisión manual",
    # "Tipo de combustible: Nafta".
    km = transmision = combustible = None
    atributos: dict[str, str] = {}
    for ln, pl in zip(lines, plain):
        if km is None and pl.startswith(("conducido", "kilometraje", "driven")):
            km = _parse_km(re.sub(r"kil[oó]metros", "km", ln, flags=re.IGNORECASE))
            atributos["Kilometraje"] = ln
        elif transmision is None and pl.startswith(("transmision", "transmission")):
            transmision = re.sub(r"^transmis\w+\s*:?\s*", "", ln, flags=re.IGNORECASE) or ln
            atributos["Transmisión"] = ln
        elif combustible is None and pl.startswith(("tipo de combustible", "fuel type")):
            combustible = _after_colon(ln)
            atributos["Combustible"] = ln

    descripcion = vendedor_nombre = None
    for i, pl in enumerate(plain):
        if descripcion is None and pl in _DESCRIPTION_HEADERS:
            body = []
            for ln, p2 in zip(lines[i + 1:], plain[i + 1:]):
                if p2.startswith(_DESCRIPTION_STOP) or p2 in _DESCRIPTION_STOP_LINES:
                    break
                body.append(ln)
            descripcion = "\n".join(body) or None
        if vendedor_nombre is None and pl in _SELLER_HEADERS:
            rest = [ln for ln, p2 in zip(lines[i + 1:], plain[i + 1:])
                    if p2 not in ("detalles del vendedor", "seller details")]
            vendedor_nombre = rest[0] if rest else None

    images = _own_images(main)
    return ListingDetail(url, listing=Listing(
        source="facebook",
        listing_id=m.group(1),
        titulo=title[:200],
        url=url,
        precio=price,
        moneda=moneda,
        anio=_parse_year(title),
        km=km,
        transmision=transmision,
        combustible=combustible,
        ubicacion=location,
        # Marketplace vehicles are overwhelmingly private sellers; dealers say so.
        vendedor="concesionaria" if "concesionaria" in joined or "dealership" in joined else "particular",
        vendedor_nombre=vendedor_nombre,
        descripcion=descripcion,
        imagenes=list(dict.fromkeys(i for i in images if i)),
        atributos=atributos,
        published_at=published_at,
    ))


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
            raise CollectorBlocked(f"facebook: no session at {FB_STORAGE_STATE}. "
                                   "Run: python -m collectors.facebook   to log in once.")

        url = self._build_url(filters)
        out: list[Listing] = []
        seen: set[str] = set()
        async with browser_context(storage_state=FB_STORAGE_STATE) as ctx:
            page = await ctx.new_page()
            try:
                await page.goto(url, timeout=45_000, wait_until="domcontentloaded")
                if "/login" in page.url or "checkpoint" in page.url:
                    raise CollectorBlocked("facebook: session expired")
                # FB renders the feed asynchronously; settle then scroll
                await page.wait_for_timeout(3_500)
                for _ in range(3):
                    await page.mouse.wheel(0, 4_000)
                    await page.wait_for_timeout(900)

                anchors = await page.locator("a[href*='/marketplace/item/']").all()
                for a in anchors:
                    href = (await a.get_attribute("href")) or ""
                    m = re.search(r"/marketplace/item/(\d+)", href)
                    if not m or m.group(1) in seen:
                        continue
                    seen.add(m.group(1))

                    text = (await a.inner_text()).strip()
                    label = await a.get_attribute("aria-label") or ""
                    if not _matches_query_text(f"{label}\n{text}", filters):
                        continue

                    # Try to grab thumbnail from the anchor's img
                    img = None
                    try:
                        img_el = a.locator("img").first
                        if await img_el.count() > 0:
                            img = await img_el.get_attribute("src")
                    except Exception:
                        pass

                    listing = parse_card(href, text, label, img)
                    if listing is None:
                        continue
                    self.annotate_partial_price(listing)
                    if self.matches_filters(listing, filters):
                        out.append(listing)
            finally:
                await page.close()
        return out

    # 2: "Ver más" is expanded and the description stops before the page around it.
    DETAIL_PARSER_VERSION = 2
    parse_detail = staticmethod(parse_detail)

    async def fetch_detail_page(self, url: str) -> Page:
        if not Path(FB_STORAGE_STATE).exists():
            raise CollectorBlocked(f"facebook: no session at {FB_STORAGE_STATE}")
        page = await fetch_rendered(url, storage_state=FB_STORAGE_STATE, settle_ms=3_500, expand=_EXPAND)
        if "/login" in page.url or "checkpoint" in page.url:
            raise CollectorBlocked("facebook: session expired")
        return page

    def slim_page(self, page: Page) -> str:
        return slim_html(page.html, keep="[role='main']")


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

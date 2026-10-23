"""MercadoLibre Argentina scraper.

Search and item pages are plain HTTP GETs of the public hosts
(autos.mercadolibre.com.ar for searches, auto.mercadolibre.com.ar for ads),
which Mercado Libre serves without a session. The logged-in search at
listado.mercadolibre.com.ar asks for an account, and in October 2026 it put a
security challenge in front of the automated Chrome this collector used.
A challenge or a login wall is never solved: the run fails as blocked.

A target by body type (docs/CARROCERIA.md) reads "Publicados hoy" of the
code's VEHICLE_BODY_TYPE values, and labels the cards with the code only
when the page shows the filter applied.
"""
from __future__ import annotations
import asyncio
from dataclasses import dataclass
import json
import logging
import random
import re
from typing import Any
from urllib.parse import urlsplit

from bs4 import BeautifulSoup

import config
from normalization import body_type
from .base import BaseScraper, CollectorBlocked, Listing, ListingDetail, SearchResults
from . import _recency
from ._recency import PublicationWindow
from ._dates import publication_date
from ._http import Page, dedupe, fetch_page, json_ld_of_type, multiline_text, soup, text_of, to_int


log = logging.getLogger("collectors.mercadolibre")

# The wall's own sentence ("Para continuar, ingresá a tu cuenta"): every
# logged-out page has "Ingresá" in its header, and an ad's description can say
# "para continuar" (MLA-3770582028, 22/10/2026), so the two words apart are no wall.
_LOGIN_TEXT_RE = re.compile(r"para continuar,?\s+ingres[aá]")


def _wall_reason(url: str, body_text: str = "") -> str | None:
    url_l = (url or "").lower()
    text_l = (body_text or "").lower()
    if "/captcha/" in url_l or ("por seguridad" in text_l and "complet" in text_l and "desaf" in text_l):
        return "security challenge"
    if ("account-verification" in url_l or "/login" in url_l or _LOGIN_TEXT_RE.search(text_l)):
        return "login required"
    return None


def _looks_like_login_wall(url: str, body_text: str = "") -> bool:
    return _wall_reason(url, body_text) is not None


def _safe_url(url: str) -> str:
    """Log the destination without login query parameters or fragments."""
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.hostname}{parts.path}"


async def _page_pause() -> None:
    await asyncio.sleep(random.uniform(3.0, 5.5))


# ---------- URL building ----------

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slug(s: str) -> str:
    s = s.lower().strip()
    # strip accents minimally
    repl = str.maketrans("áéíóúñü", "aeiounu")
    s = s.translate(repl)
    return _SLUG_RE.sub("-", s).strip("-")


BASE = "https://autos.mercadolibre.com.ar"
PAGE_SIZE = 48
# "Publicados hoy" lists the last 24 hours, not the calendar day: at 00:19 on
# 15/10/2026 it still listed most ads it had at 18:54 the day before. The hour
# on top absorbs the window's 10-minute overlap and scheduling delays; a gap of
# 24 to 25 hours can miss what was published in that margin.
TODAY_FILTER_SPAN = _recency.TODAY_SPAN

# Dates read from ads, by id, for the worker's lifetime: an ad outside the
# window is never stored, and would otherwise be read again on every scan.
_dates: dict[str, int | None] = {}
# A scan that ran out of date fetches: a long window (a first run) ends
# incomplete until the ads it read cover it (tools/platform_health.py).
DATE_FETCH_LIMIT = "mercadolibre: date fetch limit reached"

# Mercado Libre's VEHICLE_BODY_TYPE values (category MLA1744, 15/10/2026),
# most listed first. normalization/body_type.py maps each one to its code:
# suv is SUV, Off-Road and Crossover; Light Truck (452751) maps to none, so
# no target searches it.
BODY_TYPE_IDS = ("479344", "452759", "452758", "452756", "452750", "452752", "452749", "452760",
                 "452748", "452751", "452754", "452761", "452753", "452755", "452757")
IDS_BY_BODY_TYPE: dict[str, tuple[str, ...]] = {
    code: tuple(i for i in BODY_TYPE_IDS if body_type.from_source(i) == code) for code in body_type.CODES}


def _build_url(filters: dict, page: int = 1, *, today: bool = False,
               body_type_id: str | None = None) -> str:
    """A public autos search: /<marca>/<modelo>/ and ML's _Filter_value suffixes.

    The public host sorts by relevance (newest first needs an account), so a
    publication window is read whole, or as "Publicados hoy" for today. The
    version stays out of the path: the cards are filtered after reading them.

    A search by body type (`body_type_id`, no make or model) puts the suffixes
    in the order Mercado Libre's own pagination links use (15/10/2026): any
    other order answers with a redirect to that one, a hop more per page.
    """
    path = "/" + "".join(f"{_slug(str(filters[k]))}/" for k in ("marca", "modelo") if filters.get(k))

    # ML encodes filters as _Filter_value pairs appended to the path
    years = km = None
    if filters.get("anio_min") or filters.get("anio_max"):
        lo = int(filters["anio_min"]) if filters.get("anio_min") else 1990
        hi = int(filters["anio_max"]) if filters.get("anio_max") else 2030
        years = f"_VEHICLE*YEAR_{lo}-{hi}"
    if filters.get("km_max"):
        km = f"_KILOMETERS_*-{int(filters['km_max'])}km"
    since = "_PublishedToday_YES" if today else None
    offset = f"_Desde_{(page - 1) * PAGE_SIZE + 1}" if page > 1 else None

    if body_type_id:
        segments = (offset, since, km, "_NoIndex_True", f"_VEHICLE*BODY*TYPE_{body_type_id}", years)
    else:
        segments = (years, km, since, offset, "_NoIndex_True")
    return BASE + path + "".join(s for s in segments if s)


# ---------- card parsing ----------

_YEAR_RE = re.compile(r"\b(19[8-9]\d|20[0-3]\d)\b")
_KM_RE = re.compile(r"([\d\.\,]+)\s*Km", re.IGNORECASE)


def _to_int(s: str) -> int | None:
    if not s:
        return None
    digits = re.sub(r"\D", "", s)
    return int(digits) if digits else None


def _extract_id(href: str) -> str | None:
    if not href:
        return None
    m = re.search(r"MLA-?(\d+)", href)
    return f"MLA{m.group(1)}" if m else None


def _parse_card(card_html: str) -> Listing | None:
    """One search result. Make/model are left to normalization (sección 5.2):
    the card only has the title, and the search filter is not evidence."""
    soup = BeautifulSoup(card_html, "lxml")

    a = soup.select_one("a.poly-component__title")
    if not a:
        return None
    href = a.get("href", "").split("#")[0]
    title = a.get_text(strip=True)
    lid = _extract_id(href)
    if not lid:
        return None

    # price
    precio: float | None = None
    moneda: str | None = None
    money_el = soup.select_one("[data-andes-money-amount='true']")
    if money_el:
        sym = money_el.select_one(".andes-money-amount__currency-symbol")
        frac = money_el.select_one(".andes-money-amount__fraction")
        cents = money_el.select_one(".andes-money-amount__cents")
        if frac:
            digits = re.sub(r"\D", "", frac.get_text())
            if digits:
                precio = float(digits)
                if cents:
                    cents_d = re.sub(r"\D", "", cents.get_text())
                    if cents_d:
                        precio += float(f"0.{cents_d}")
        # currency from aria-label
        aria = (money_el.get("aria-label") or "").lower()
        if "dólar" in aria or "dolar" in aria or "us$" in aria or sym and sym.get_text(strip=True) == "US$":
            moneda = "USD"
        elif sym and sym.get_text(strip=True) in ("$", "ARS"):
            moneda = "ARS"

    # attributes (year, km)
    anio = km = None
    for li in soup.select("li.poly-attributes_list__item"):
        txt = li.get_text(strip=True)
        if not anio and (m := _YEAR_RE.search(txt)):
            anio = int(m.group(1))
            continue
        if not km and (m := _KM_RE.search(txt)):
            km = _to_int(m.group(1))

    location = None
    loc_el = soup.select_one(".poly-component__location")
    if loc_el:
        location = loc_el.get_text(strip=True)

    img = soup.select_one("img.poly-component__picture")
    img_url = img.get("src") if img else None

    return Listing(
        source="mercadolibre",
        listing_id=lid,
        titulo=title,
        url=href,
        precio=precio,
        moneda=moneda,
        anio=anio,
        km=km,
        ubicacion=location,
        published_at=publication_date(soup),
        imagenes=[img_url] if img_url else [],
    )


def parse_search(html: str) -> list[Listing]:
    """Cards of a search results page, in page order, without duplicates."""
    doc = BeautifulSoup(html, "lxml")
    out: dict[str, Listing] = {}
    for card in doc.select("li.ui-search-layout__item"):
        listing = _parse_card(str(card))
        if listing and listing.listing_id not in out:
            out[listing.listing_id] = listing
    return list(out.values())


def _results(html: str) -> list[Listing]:
    """The cards of a results page; [] for ML's "no results" placeholder.
    A page that is neither, or whose cards don't parse, raises: never a
    silent zero."""
    doc = soup(html)
    if doc.select_one(".ui-search-rescue") is not None:
        return []
    if not doc.select("li.ui-search-layout__item"):
        raise RuntimeError("mercadolibre: the page has no results list")
    cards = parse_search(html)
    if not cards:
        raise ValueError("mercadolibre: result cards exist but none could be parsed")
    return cards


_JSON = json.JSONDecoder()


def _embedded(html: str, key: str) -> Any:
    """The value of the first `"key":` of the state the page embeds, or None."""
    at = html.find(f'"{key}":')
    if at < 0:
        return None
    try:
        return _JSON.raw_decode(html, at + len(key) + 3)[0]
    except ValueError:
        return None


@dataclass(frozen=True)
class SearchState:
    """What a results page says about itself, in the state Mercado Libre
    embeds in it (__NORDIC_RENDERING_CTX__): the filters it applied, as
    (key, value) pairs, how many results the search has and how many pages
    it lets read (42 at most: 2,016 results)."""
    applied: frozenset[tuple[str, str]]
    total: int | None
    page_count: int | None

    def applies(self, body_type_id: str) -> bool:
        """The page shows that body type and "Publicados hoy" applied."""
        return {("VEHICLE_BODY_TYPE", body_type_id), ("since", "today")} <= self.applied

    @property
    def truncated(self) -> bool:
        """More results than the pages Mercado Libre serves."""
        return (self.total is not None and self.page_count is not None
                and self.total > self.page_count * PAGE_SIZE)


def search_state(html: str) -> SearchState:
    event = _embedded(html, "event_data")
    event = event if isinstance(event, dict) else {}
    applied = event.get("applied_filters")
    if applied is None:
        applied = _embedded(html, "applied_filters")
    pagination = _embedded(html, "pagination")
    pagination = pagination if isinstance(pagination, dict) else {}

    def number(value: Any) -> int | None:
        return value if isinstance(value, int) and not isinstance(value, bool) else None

    return SearchState(
        applied=frozenset((str(f.get("key")), str(f.get("value")))
                          for f in (applied if isinstance(applied, list) else []) if isinstance(f, dict)),
        total=number(event.get("total")),
        page_count=number(pagination.get("page_count")),
    )


# ---------- detail page ----------

_GONE_TEXTS = ("publicacion pausada", "publicacion finalizada", "esta publicacion esta pausada",
               "esta publicacion finalizo", "publicacion inactiva")


def _plain(s: str) -> str:
    return s.lower().translate(str.maketrans("áéíóú", "aeiou"))


def parse_detail(html: str, url: str, status: int = 200) -> ListingDetail:
    """An item page (auto.mercadolibre.com.ar/MLA-…)."""
    if status == 404:
        return ListingDetail(url, gone=True, gone_reason="404")
    doc = soup(html)
    page_text = _plain(doc.get_text(" ", strip=True))
    if reason := next((t for t in _GONE_TEXTS if t in page_text), None):
        return ListingDetail(url, gone=True, gone_reason=reason)

    ld = json_ld_of_type(doc, "Vehicle", "Car", "Product") or {}
    offer = ld.get("offers") or {}
    availability = str(offer.get("availability") or "")
    if availability and not availability.endswith("InStock"):
        return ListingDetail(url, gone=True, gone_reason=availability.rsplit("/", 1)[-1])

    title = text_of(doc.select_one("h1.ui-pdp-title")) or ld.get("name")
    lid = _extract_id(url) or (str(ld["sku"]) if ld.get("sku") else None)
    if not title or not lid:
        raise ValueError(f"mercadolibre detail without title/id: {url}")

    # "Características" tables: Marca, Modelo, Año, Versión, Kilómetros, Transmisión…
    specs: dict[str, str] = {}
    for row in doc.select("table tr"):
        th, td = row.select_one("th"), row.select_one("td")
        if th and td and (k := text_of(th)) and (v := text_of(td)):
            specs.setdefault(k, v)

    precio = float(offer["price"]) if offer.get("price") else None
    moneda = {"ARS": "ARS", "USD": "USD"}.get(str(offer.get("priceCurrency") or "").upper())
    if precio is None:
        price_el = doc.select_one(".ui-pdp-price__second-line [data-andes-money-amount='true']")
        meta = price_el.select_one("meta[itemprop='price']") if price_el else None
        if meta and meta.get("content"):
            precio = float(meta["content"])
            sym = text_of(price_el.select_one(".andes-money-amount__currency-symbol")) or ""
            moneda = "USD" if "US" in sym.upper() else "ARS"

    # "2026 | 0 km · Publicado hace 7 meses"
    subtitle = text_of(doc.select_one(".ui-pdp-subtitle, .ui-pdp-header__subtitle")) or ""
    published = re.search(r"publicad[oa]\s+(.+)$", subtitle, re.IGNORECASE)

    seller_header = _plain(text_of(doc.select_one(".ui-vip-seller-profile__header")) or "")
    vendedor = ("concesionaria" if "concesionaria" in seller_header or "tienda oficial" in seller_header
                else "particular" if "vendedor" in seller_header or "particular" in seller_header
                else None)
    seller_name = text_of(doc.select_one(".ui-pdp-seller-validated__title"))
    if seller_name:
        seller_name = re.sub(r"^publicado por\s+", "", seller_name, flags=re.IGNORECASE)

    images = dedupe([img.get("data-zoom") or img.get("src")
                     for img in doc.select("figure.ui-pdp-gallery__figure img")])
    brand = ld.get("brand")
    body = ld.get("bodyType")

    return ListingDetail(url, listing=Listing(
        source="mercadolibre",
        listing_id=lid,
        titulo=title,
        url=url,
        precio=precio,
        moneda=moneda,
        marca=specs.get("Marca") or (brand if isinstance(brand, str) else None),
        modelo=specs.get("Modelo"),
        version=specs.get("Versión"),
        anio=to_int(specs.get("Año")),
        km=to_int(specs.get("Kilómetros")),
        combustible=specs.get("Tipo de combustible"),
        transmision=specs.get("Transmisión"),
        carroceria=specs.get("Tipo de carrocería") or (body if isinstance(body, str) else None),
        vendedor=vendedor,
        vendedor_nombre=seller_name,
        descripcion=multiline_text(doc.select_one(".ui-pdp-description__content")),
        imagenes=images,
        atributos=specs,
        published_at=publication_date(doc, structured=ld,
                                      text=published.group(1) if published else None),
    ))


# ---------- transport ----------

async def _get(url: str, what: str, *, allow_404: bool = False) -> Page:
    """GET a public page. A challenge, a login wall or 403/429 raise
    CollectorBlocked: the run fails, nothing tries to get past it."""
    page = await fetch_page(url, timeout=45.0)
    body = soup(page.html).get_text(" ", strip=True) if page.html else ""
    if reason := _wall_reason(page.url, body):
        raise CollectorBlocked(f"mercadolibre {what}: {reason}; HTTP {page.status}; destination={_safe_url(page.url)}")
    if page.status in (403, 429):
        raise CollectorBlocked(f"mercadolibre {what}: HTTP {page.status}; destination={_safe_url(page.url)}")
    if page.status >= 400 and not (allow_404 and page.status == 404):
        raise RuntimeError(f"mercadolibre {what} HTTP {page.status}: {_safe_url(page.url)}")
    return page


# ---------- scraper ----------

class BodyTypeNotApplied(RuntimeError):
    """A results page of a search by body type that doesn't show the filter
    applied. Its cards can't be labeled with the body type, and the run fails."""


def _searched_body_type(filters: dict) -> str | None:
    """The code a target by body type searches (docs/CARROCERIA.md):
    filters["carroceria"] without a make or model. None for any other search."""
    code = filters.get("carroceria")
    if not code or filters.get("marca") or filters.get("modelo"):
        return None
    return str(code)


class MercadoLibreScraper(BaseScraper):
    DETAIL_PARSER_VERSION = 3  # 3: Listing.carroceria ("Tipo de carrocería", JSON-LD bodyType)
    name = "mercadolibre"
    BODY_TYPES = frozenset(code for code, ids in IDS_BY_BODY_TYPE.items() if ids)

    MAX_PAGES = 2  # without a publication window (the CLI): the first 96 results

    async def search(self, filters: dict) -> list[Listing]:
        if code := _searched_body_type(filters):
            return await self._search_body_type(filters, code)
        if window := PublicationWindow.from_filters(filters):
            return await self._search_recent(filters, window)
        out: list[Listing] = []
        seen_ids: set[str] = set()
        for p in range(1, self.MAX_PAGES + 1):
            if p > 1:
                await _page_pause()
            try:
                cards = _results((await _get(_build_url(filters, page=p), "search")).html)
            except Exception as exc:
                # A wall or a failure on the first page fails the run; later, keep what we have.
                if p == 1:
                    raise
                log.warning("MercadoLibre search stopped at page %d: %s", p, exc)
                break
            for listing in cards:
                if listing.listing_id in seen_ids:
                    continue
                seen_ids.add(listing.listing_id)
                self.annotate_partial_price(listing)
                if self.matches_filters(listing, filters):
                    out.append(listing)
            if len(cards) < PAGE_SIZE:
                break
        return out

    async def _publication_date(self, listing: Listing) -> int | None:
        """Cards omit dates: read the ad instead of using detection time."""
        page = await _get(listing.url, "date", allow_404=True)
        detail = parse_detail(page.html, listing.url, page.status)
        return detail.listing.published_at if detail.listing else None

    async def _search_recent(self, filters: dict, window: PublicationWindow) -> SearchResults:
        """Every result of the window, kept if published inside it.

        A window of up to TODAY_FILTER_SPAN, or a count-only target (2.5), is
        read through "Publicados hoy" (_recency.one_request_read, which
        pipeline/crawl.py also asks): one request, and its results are kept
        as they come, since Mercado Libre's own filter vouches for them while
        an ad's page only says "hace 1 día" (the public pages carry no exact
        date). Without a stored date, detection time stands in, which the
        half-hourly crawl keeps close to publication.

        A longer window (a first run, a gap) reads every result in relevance
        order, dating each from stored listings, the ads already read or the
        ad itself, up to RECENT_ML_MAX_DATE_FETCHES ads per scan."""
        results = SearchResults()
        seen: set[str] = set()
        known = filters.get("known_publication_dates") or {}
        today = _recency.one_request_read(self.name, filters, window)
        fetched = 0
        pages = 0
        try:
            while True:
                if pages >= config.RECENT_ML_MAX_PAGES:
                    results.complete, results.reason = False, "mercadolibre: publication scan page limit reached"
                    break
                if pages:
                    await _page_pause()
                url = _build_url(filters, page=pages + 1, today=today)
                cards = _results((await _get(url, "search")).html)
                if not cards:
                    break
                pages += 1
                fresh = [c for c in cards if c.listing_id not in seen]
                if not fresh:
                    results.complete, results.reason = False, "mercadolibre: pagination repeated a page"
                    break
                for listing in fresh:
                    seen.add(listing.listing_id)
                    self.annotate_partial_price(listing)
                    if not self.matches_filters(listing, filters):
                        continue
                    if listing.published_at is None:
                        listing.published_at = known.get(listing.listing_id)
                    if today:
                        results.append(listing)
                        continue
                    if listing.published_at is None and listing.listing_id in _dates:
                        listing.published_at = _dates[listing.listing_id]
                    elif listing.published_at is None and fetched >= config.RECENT_ML_MAX_DATE_FETCHES:
                        results.complete, results.reason = False, DATE_FETCH_LIMIT
                    elif listing.published_at is None:
                        fetched += 1
                        await asyncio.sleep(config.RECENT_ML_DETAIL_SECONDS)
                        try:
                            listing.published_at = _dates[listing.listing_id] = await self._publication_date(listing)
                        except CollectorBlocked:
                            raise
                        except Exception as exc:
                            results.complete, results.reason = False, f"mercadolibre date fetch failed: {type(exc).__name__}"
                            log.warning("Could not read publication date for %s: %s", listing.listing_id, exc)
                    if listing.published_at is None:
                        results.unknown_dates += 1
                    elif window.contains(listing):
                        results.append(listing)
                if len(cards) < PAGE_SIZE:
                    break
        except Exception as exc:
            if not seen:
                raise
            results.complete, results.reason = False, f"mercadolibre: {type(exc).__name__}: {exc}"
        log.info("mercadolibre publication window: today=%s pages=%d dates_read=%d kept=%d unknown_dates=%d "
                 "complete=%s reason=%s", today, pages, fetched, len(results), results.unknown_dates,
                 results.complete, results.reason)
        return results

    async def _search_body_type(self, filters: dict, code: str) -> SearchResults:
        """A target by body type (docs/CARROCERIA.md): "Publicados hoy" of each
        of the code's VEHICLE_BODY_TYPE ids, whatever the publication window,
        a first run too. A body type is too many listings to date them one by
        one (29,000 SUVs, of which Mercado Libre serves 2,016), while a day of
        them fits (about 600); its searches are backfilled from stored listings.

        The cards say nothing about the body. A page vouches for its cards only
        when its embedded state shows the body type and "today" applied: then
        each card gets the code in Listing.carroceria. A page that doesn't
        fails the run: Mercado Libre ignoring the filter would serve every car
        in the country, all labeled with the code."""
        ids = IDS_BY_BODY_TYPE.get(code)
        if not ids:
            raise ValueError(f"mercadolibre: no VEHICLE_BODY_TYPE for body type {code!r}")
        known = filters.get("known_publication_dates") or {}
        results = SearchResults()
        seen: set[str] = set()
        pages = 0
        try:
            for body_id in ids:
                page, last = 1, None
                while pages < config.RECENT_ML_MAX_PAGES:
                    if pages:
                        await _page_pause()
                    url = _build_url(filters, page, today=True, body_type_id=body_id)
                    html = (await _get(url, "search")).html
                    pages += 1
                    cards = _results(html)
                    if not cards:
                        break
                    state = search_state(html)
                    if not state.applies(body_id):
                        raise BodyTypeNotApplied(
                            f"mercadolibre: page {page} of VEHICLE_BODY_TYPE {body_id} doesn't show it and "
                            f"'Publicados hoy' applied: {_safe_url(url)}")
                    if page == 1:
                        last = state.page_count
                        if state.truncated:
                            results.complete = False
                            results.reason = (f"mercadolibre: VEHICLE_BODY_TYPE {body_id} has {state.total} "
                                              f"results today, more than its {last} pages show")
                    fresh = [c for c in cards if c.listing_id not in seen]
                    if not fresh:
                        results.complete, results.reason = False, "mercadolibre: pagination repeated a page"
                        break
                    for listing in fresh:
                        seen.add(listing.listing_id)
                        listing.carroceria = code
                        self.annotate_partial_price(listing)
                        if not self.matches_filters(listing, filters):
                            continue
                        if listing.published_at is None:
                            listing.published_at = known.get(listing.listing_id)
                        results.append(listing)
                    if len(cards) < PAGE_SIZE or (last is not None and page >= last):
                        break
                    page += 1
                else:
                    results.complete, results.reason = False, "mercadolibre: publication scan page limit reached"
                    break
        except BodyTypeNotApplied:
            raise
        except Exception as exc:
            if not seen:
                raise
            results.complete, results.reason = False, f"mercadolibre: {type(exc).__name__}: {exc}"
        log.info("mercadolibre body type %s: ids=%s pages=%d kept=%d complete=%s reason=%s",
                 code, ",".join(ids), pages, len(results), results.complete, results.reason)
        return results

    parse_detail = staticmethod(parse_detail)

    async def fetch_detail_page(self, url: str) -> Page:
        return await _get(url, "detail", allow_404=True)

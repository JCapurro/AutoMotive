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
from collections import Counter
import json
import logging
import re
import time
import unicodedata
import urllib.parse
from pathlib import Path
from typing import Iterable, NamedTuple

from playwright.async_api import async_playwright

from .base import BaseScraper, CollectorBlocked, Listing, ListingDetail, SearchResults
from ._recency import DateSkip, PublicationWindow, encode_date_skips, parse_date_skips
from ._browser import browser_context
from ._dates import parse_publication_date
from ._http import Page, fetch_rendered, slim_html, soup
from config import FB_STORAGE_STATE
import config
from normalization.geo import nearest_known_location_name
from normalization.money import MIN_ARS_VEHICLE_PRICE, MIN_USD_VEHICLE_PRICE, plain_dollar_currency


_PRICE_RE = re.compile(r"(US\$|u\$s|USD|ARS|\$)\s*([\d\.\,]+)", re.IGNORECASE)
# FB renders kms as "115 km", "115.000 km" or "115 mil km" (= 115.000 km).
_KM_RE = re.compile(r"(\d[\d\.\,]*)\s*(mil\s+)?km", re.IGNORECASE)
_YEAR_RE = re.compile(r"\b(19[8-9]\d|20[0-3]\d)\b")
log = logging.getLogger("collectors.facebook")

# A card shows no age. The search page's own data carries each listing's
# creation_time (FB_FEED_DATES, _FeedProbe.feed_date); a card it doesn't date
# reads its item page, 30 s apart. Past RECENT_FB_MAX_DATE_FETCHES (12) pages
# the scan ends incomplete with what it kept;
# the retry, 180 s later, finds those dates among the stored listings
# (known_publication_dates) and the ads dated out of the window in the
# target's date memory (crawl_targets.prefilter_rejected, collectors/_recency.py),
# and reads the next pages (Ford Ka and Toyota Yaris in Buenos Aires,
# 2026-10-21, ran for over an hour each until a restart threw the scan away).
# No in-memory cache: each search runs in its own child process (ISOLATED).
DATE_FETCH_LIMIT = "facebook: date fetch limit reached"
# A card telling it was just published (they show no other age).
_JUST_LISTED = ("just listed", "publicado recientemente")


# Common AR cities → FB Marketplace location slugs. Each one checked on the VPS
# (2026-10-20): an unknown slug ("santafe", "bahiablanca", "resistencia",
# "posadas") silently redirects to /marketplace/category/ and searches around
# the account's own location instead.
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
    "santa fe":         "santa-fe",
    "corrientes":       "corrientes",
    "formosa":          "formosa",
    "neuquén":          "neuquen",
    "neuquen":          "neuquen",
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
_DATE_LINE_VALUES = {"ayer", "hoy", "anteayer", "just listed", "publicado recientemente",
                     "recién publicado", "recien publicado"}


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

    # Publication cues only; a model year or a price is not a date.
    date_line = next(
        (ln for ln in lines if ln.lower().startswith(("hace ", "publicado ", "publicada "))
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
        published_at=parse_publication_date(date_line),
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


async def _require_session(ctx) -> None:
    """Facebook no longer always redirects a dead session to /login: it serves
    the public Marketplace with a login form, whose cards carry no publication
    date. Only the session cookie proves the visit is logged in."""
    if not any(c.get("name") == "c_user" for c in await ctx.cookies("https://www.facebook.com")):
        raise CollectorBlocked("facebook: session expired (logged out, no c_user cookie)")


_CREATION_RE = re.compile(r'"creation_time":(\d{9,11}),"location_text"')
_STORY_ID_RE = re.compile(r'"id":"(Uzpf[A-Za-z0-9+/=]+)"')


def _own_creation_time(html: str, listing_id: str) -> int | None:
    """The listing's own "creation_time" from the page's data, or None.

    The page also carries the suggested ads' times, so a value counts only
    when its object names this listing (its ID, or a story ID that decodes to
    "...:VK:<id>"), and only when exactly one value does."""
    import base64
    found = set()
    for match in _CREATION_RE.finditer(html):
        before = html[max(0, match.start() - 3_000):match.start()]
        stories = []
        for story in _STORY_ID_RE.findall(before):
            try:
                stories.append(base64.b64decode(story).decode("ascii", "ignore"))
            except ValueError:
                continue
        if f'"{listing_id}"' in before or any(s.endswith(f"VK:{listing_id}") for s in stories):
            found.add(int(match.group(1)))
    if len(found) != 1:
        return None
    value = found.pop()
    return value if 1_000_000_000 < value <= int(time.time()) + 3_600 else None


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

    # "Publicado hace 2 días en Vicente López, BA"; since 2026-10 often just
    # "Listed in Rosario, SF", with the age only in the page's data.
    published_at = location = None
    for i, (ln, pl) in enumerate(zip(lines, plain)):
        if pl.startswith(("publicado ", "publicada ", "listed ")):
            if place := re.match(r"(?:publicad[oa]|listed)\s+(?:en|in)(?:\s+(.+))?$", ln, re.IGNORECASE):
                # The empty age leaves "Listed  in" with the place on the next line.
                location = place.group(1) or (lines[i + 1] if i + 1 < len(lines) else None)
            elif hm := re.match(r"(?:publicad[oa]|listed)\s+(.*?)(?:\s+(?:en|in)\s+(.+))?$", ln, re.IGNORECASE):
                published_at = parse_publication_date(hm.group(1))
                location = hm.group(2)
            break
    if published_at is None:
        published_at = _own_creation_time(html, m.group(1))

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


# ---------- feed dates and probe ----------
# The search page's own data carries each card's creation_time: the JSON in
# the first HTML and the /api/graphql/ answers to the scrolls, which the page
# downloads anyway. A card dated there needs no item page (FB_FEED_DATES,
# phase 2A of docs/RECENT_PUBLICATIONS.md). The probe that found it keeps
# counting, each scan, how the cards got their dates and whether the feed and
# an item page disagree.

_JSON_SCRIPT_RE = re.compile(r'<script type="application/json"[^>]*>(.*?)</script>', re.S)
# What the probe holds of the GraphQL answers not indexed yet, at most.
PROBE_MAX_BYTES = 20_000_000
# A feed time and an item page's creation_time agree within this.
PROBE_AGREE_SECONDS = 120
# The paths a report names, the most frequent first.
PROBE_MAX_PATHS = 8
# The feed time a card is dated by: the one on its own listing object, which
# the probe found on every card (2026-10-22, 19 of 19, each within
# PROBE_AGREE_SECONDS of the stored date).
FEED_DATE_PATH = "own.creation_time"
# A feed time before 2015-01-01 UTC, or after now, is no publication date.
FEED_DATE_FLOOR = 1_420_070_400
# How long a card missing from the data waits, once per answer, for the
# answers still being read.
FEED_WAIT_SECONDS = 3


def _json_documents(text: str) -> Iterable[object]:
    """The JSON in an HTML page's <script type="application/json">, or in a
    GraphQL answer: a "for (;;);" guard, then one document per line."""
    chunks = (_JSON_SCRIPT_RE.findall(text) if "<script" in text
              else text.removeprefix("for (;;);").splitlines())
    for chunk in chunks:
        chunk = chunk.strip()
        if not chunk.startswith(("{", "[")):
            continue
        try:
            yield json.loads(chunk)
        except ValueError:
            continue


def _times(obj: dict, latest: int, depth: int = 2, prefix: str = "") -> Iterable[tuple[str, int]]:
    """(path, value) of the epoch seconds under keys naming a time, down to
    `depth`, without entering another object that has its own "id"."""
    for key, value in obj.items():
        path = f"{prefix}{key}"
        if (isinstance(value, int) and not isinstance(value, bool) and "time" in key.lower()
                and 1_000_000_000 <= value <= latest):
            yield path, value
        elif isinstance(value, dict) and depth > 1 and "id" not in value:
            yield from _times(value, latest, depth - 1, f"{path}.")


class FeedTimes(NamedTuple):
    times: dict[str, dict[str, int]]    # card id → {path: epoch seconds}
    paths: Counter                      # path → how many cards carry it
    present: set[str]                   # card ids found as some object's "id"
    documents: int                      # JSON documents read


class _FeedIndex:
    """The times the page's data ties to each listing ID, built one text at a
    time as the scan reads them: under the object whose "id" is the listing's
    ("own.<path>") or beside it in the object holding it ("edge.<path>"). An
    ID with two values for one path loses that path."""

    def __init__(self, *, now: int | None = None) -> None:
        self.latest = (int(time.time()) if now is None else now) + 3_600
        self.found: dict[str, dict[str, set[int]]] = {}
        self.present: set[str] = set()          # listing IDs found as some object's "id"
        self.documents = 0                      # JSON documents read

    def add(self, text: str) -> None:
        for doc in _json_documents(text):
            self.documents += 1
            stack: list[tuple[object, dict | None, str | None]] = [(doc, None, None)]
            while stack:
                node, parent, key = stack.pop()
                if isinstance(node, list):
                    stack.extend((v, None, None) for v in node if isinstance(v, (dict, list)))
                    continue
                if not isinstance(node, dict):
                    continue
                ident = node.get("id")
                ident = str(ident) if isinstance(ident, (str, int)) and not isinstance(ident, bool) else ""
                if ident.isascii() and ident.isdigit():          # /marketplace/item/<digits>
                    self.present.add(ident)
                    times = [(f"own.{path}", value) for path, value in _times(node, self.latest)]
                    times += [(f"edge.{path}", value) for k, sibling in (parent or {}).items() if k != key
                              for path, value in _times({k: sibling}, self.latest)]
                    for path, value in times:
                        self.found.setdefault(ident, {}).setdefault(path, set()).add(value)
                stack.extend((v, node, k) for k, v in node.items() if isinstance(v, (dict, list)))

    def times(self, ident: str) -> dict[str, int]:
        """The ID's paths that have a single value."""
        return {p: next(iter(v)) for p, v in self.found.get(ident, {}).items() if len(v) == 1}

    def lookup(self, card_ids: Iterable[str]) -> FeedTimes:
        ids = {str(i) for i in card_ids}
        times = {i: t for i in ids if (t := self.times(i))}
        return FeedTimes(times, Counter(p for t in times.values() for p in t), self.present & ids, self.documents)


def _feed_times(texts: Iterable[str], card_ids: Iterable[str], *, now: int | None = None) -> FeedTimes:
    """The times the page's data (`texts`) ties to each card (_FeedIndex)."""
    index = _FeedIndex(now=now)
    for text in texts:
        index.add(text)
    return index.lookup(card_ids)


class _FeedProbe:
    """Collects, during one scan, the page's data (_FeedIndex) and how the scan
    dated each card, and reports counters only: path names, counts and how far
    a feed date is from its item page's, never a date. It makes no request,
    changes the scan's results only through feed_date, and keeps the page's
    data (which carries session tokens) in memory only. Every step swallows
    its own errors."""

    def __init__(self) -> None:
        self.texts: list[str] = []                 # read, not indexed yet
        self.index = _FeedIndex()
        self.graphql = 0
        self.size = 0                              # what self.texts holds
        self.pending: set[asyncio.Future] = set()
        self.waited: set[asyncio.Future] = set()
        self.cards: set[str] = set()
        self.just_listed: set[str] = set()
        self.dates: dict[str, int] = {}
        self.origins: Counter = Counter()          # card, known, feed, page, or none: the dates of the cards
        self.implausible = 0                       # feed dates left out by feed_date
        self.page_times: dict[str, int] = {}       # an item page's own creation_time, this scan

    def listen(self, page) -> None:
        try:
            page.on("response", self._on_response)
        except Exception:
            pass

    def _on_response(self, response) -> None:
        try:
            if (self.size < PROBE_MAX_BYTES and "/api/graphql/" in response.url
                    and response.request.resource_type in ("xhr", "fetch")):
                task = asyncio.ensure_future(self._read(response))
                self.pending.add(task)
                task.add_done_callback(self.pending.discard)
        except Exception:
            pass

    async def _read(self, response) -> None:
        try:
            text = await response.text()
        except Exception:
            return
        if isinstance(text, str) and self.size + len(text) <= PROBE_MAX_BYTES:
            self.size += len(text)
            self.graphql += 1
            self.texts.append(text)

    async def document(self, response) -> None:
        """The search page's first HTML."""
        try:
            text = await asyncio.wait_for(response.text(), 10)
        except Exception:
            return
        if isinstance(text, str):
            self.texts.append(text)

    def _index(self) -> None:
        while self.texts:
            text = self.texts.pop()
            self.size = max(0, self.size - len(text))
            self.index.add(text)

    async def feed_date(self, ident: str) -> int | None:
        """The card's FEED_DATE_PATH in the data read so far, unless it is
        before FEED_DATE_FLOOR or in the future. A card not there yet waits
        for the answers still being read, each answer once."""
        try:
            self._index()
            value = self.index.times(ident).get(FEED_DATE_PATH)
            if value is None and (waiting := self.pending - self.waited):
                self.waited |= waiting
                await asyncio.wait(waiting, timeout=FEED_WAIT_SECONDS)
                self._index()
                value = self.index.times(ident).get(FEED_DATE_PATH)
        except Exception:
            return None
        if value is not None and not FEED_DATE_FLOOR <= value <= int(time.time()):
            self.implausible += 1
            return None
        return value

    def card(self, ident: str, text: str) -> None:
        self.cards.add(ident)
        if any(cue in text.lower() for cue in _JUST_LISTED):
            self.just_listed.add(ident)

    def dated(self, ident: str, published_at: int | None, origin: str) -> None:
        """A card the scan dated from `origin`, or couldn't (published_at None)."""
        self.origins[origin if published_at is not None else "none"] += 1
        if published_at is not None:
            self.dates[ident] = published_at

    def item_page(self, ident: str, html: str) -> None:
        try:
            if (value := _own_creation_time(html, ident)) is not None:
                self.page_times[ident] = value
        except Exception:
            pass

    async def close(self, page) -> None:
        """Stop listening and wait a little for the answers still being read."""
        try:
            page.remove_listener("response", self._on_response)
        except Exception:
            pass
        try:
            if self.pending:
                await asyncio.wait(set(self.pending), timeout=5)
        except Exception:
            pass
        for task in list(self.pending):
            task.cancel()

    def report(self, known: dict[str, int]) -> dict | None:
        try:
            self._index()
            feed = self.index.lookup(self.cards)
            paths = [p for p, _ in feed.paths.most_common(PROBE_MAX_PATHS)]

            def tally(reference: dict[str, int], paths: list[str] = paths) -> dict[str, list[int]]:
                out: dict[str, list[int]] = {}
                for ident, by_path in feed.times.items():
                    if ident in reference:
                        for path in paths:
                            if path in by_path:
                                agree = abs(by_path[path] - reference[ident]) <= PROBE_AGREE_SECONDS
                                out.setdefault(path, [0, 0])[0 if agree else 1] += 1
                return out

            # A card has both when its page was read: the feed had no plausible
            # date yet, or FB_FEED_DATES is off.
            off = {i: t[FEED_DATE_PATH] - self.page_times[i] for i, t in sorted(feed.times.items())
                   if i in self.page_times and FEED_DATE_PATH in t
                   and abs(t[FEED_DATE_PATH] - self.page_times[i]) > PROBE_AGREE_SECONDS}
            now = int(time.time())
            ages = [now - self.dates[i] for i in self.just_listed if i in self.dates]
            report = {"cards": len(self.cards), "json_docs": feed.documents, "graphql_bodies": self.graphql,
                      "ids_in_data": len(feed.present), "time_paths": dict(feed.paths.most_common(PROBE_MAX_PATHS)),
                      # [agree, disagree] against the item pages read in this scan, and apart
                      # against the stored dates.
                      "compared": tally(self.page_times), "vs_known": tally(known),
                      "dated": dict(self.origins), "feed_implausible": self.implausible,
                      "feed_vs_page": tally(self.page_times, [FEED_DATE_PATH]).get(FEED_DATE_PATH, [0, 0]),
                      "just_listed": len(self.just_listed),
                      "just_listed_max_age_h": round(max(ages) / 3600, 1) if ages else None}
            if off:
                # Seconds from the item page's date to the feed's, the first few cards.
                report["feed_page_off_s"] = dict(list(off.items())[:5])
            return report
        except Exception:
            return None
        finally:
            self.texts = []


class FacebookMarketplaceScraper(BaseScraper):
    name = "facebook"
    ISOLATED = True
    # A card without a stored date that the search page's data doesn't date
    # either costs a 30 s item page within the scan's cap
    # (RECENT_FB_MAX_DATE_FETCHES), and every one of them with FB_FEED_DATES
    # off: it reads exactly its searches' years.
    YEAR_BAND = False

    def _build_url(self, f: dict) -> str:
        slug = _city_slug(f.get("ubicacion")) if f.get("ubicacion") else _city_slug_from_origin(f)
        params: dict[str, str] = {}
        params["sortBy"] = "creation_time_descend"
        if window := PublicationWindow.from_filters(f):
            # A count-only target (2.5) reads the last day, also on its first
            # run (a new POLICY_VERSION): mercadolibre.py does the same with
            # "Publicados hoy". After more than a day down it doesn't count
            # what was published before the last 24 hours. Dates are still
            # checked against the window (window.contains).
            params["daysSinceListed"] = "1" if f.get("count_only") is True else str(window.facebook_days)
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

        if window := PublicationWindow.from_filters(filters):
            return await self._search_recent(filters, window)

        url = self._build_url(filters)
        out: list[Listing] = []
        seen: set[str] = set()
        async with browser_context(storage_state=FB_STORAGE_STATE, native=True) as ctx:
            page = await ctx.new_page()
            try:
                await page.goto(url, timeout=45_000, wait_until="domcontentloaded")
                if "/login" in page.url or "checkpoint" in page.url:
                    raise CollectorBlocked("facebook: session expired")
                await _require_session(ctx)
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

    async def _publication_date(self, ctx, listing: Listing) -> int | None:
        page = await ctx.new_page()
        try:
            response = await page.goto(listing.url, timeout=45_000, wait_until="domcontentloaded")
            status = response.status if response else 0
            if "/login" in page.url or "checkpoint" in page.url:
                raise CollectorBlocked("facebook: session expired while reading publication date")
            if status >= 400 and status != 404:
                raise RuntimeError(f"facebook date HTTP {status}")
            if status != 404:
                await page.wait_for_timeout(3_500)
            if "/login" in page.url or "checkpoint" in page.url:
                raise CollectorBlocked("facebook: session expired while reading publication date")
            html = await page.content()
            detail = parse_detail(html, listing.url, status)
            if (probe := getattr(self, "_probe", None)) is not None:
                probe.item_page(listing.listing_id, html)
            return detail.listing.published_at if detail.listing else None
        finally:
            await page.close()

    async def _search_recent(self, filters: dict, window: PublicationWindow) -> SearchResults:
        """The cards of the window, each dated by the card, a stored listing,
        the search page's own data (FB_FEED_DATES) or its item page, up to
        RECENT_FB_MAX_DATE_FETCHES pages a scan.

        With filters["date_skips"] (the target's date memory) a page already
        read is skipped as collectors/_recency.py says, and results.date_skips
        is the memory after this scan: a complete scan keeps only the cards it
        saw, a partial one keeps the rest too. A read that raised is never
        remembered: the next scan reads it again."""
        results = SearchResults()
        seen: set[str] = set()
        known = filters.get("known_publication_dates") or {}
        remembering = "date_skips" in filters
        memory = {i: s for i, s in parse_date_skips(filters.get("date_skips")).items()
                  if s.epoch is None or config.FB_DATE_MEMORY_UNKNOWN}
        # undated: pages read without a date (unknown_dates also counts the cards past the cap).
        stalls = scrolls = fetched = skipped = out_of_window = undated = 0
        self._probe = probe = _FeedProbe()
        async with browser_context(storage_state=FB_STORAGE_STATE, native=True) as ctx:
            page = await ctx.new_page()
            probe.listen(page)
            try:
                response = await page.goto(self._build_url(filters), timeout=45_000, wait_until="domcontentloaded")
                await probe.document(response)
                if response and response.status >= 400:
                    raise RuntimeError(f"facebook search HTTP {response.status}")
                await _require_session(ctx)
                await page.wait_for_timeout(3_500)
                while True:
                    if "/login" in page.url or "checkpoint" in page.url:
                        raise CollectorBlocked("facebook: session expired")
                    before = len(seen)
                    # Read each batch before scrolling; older cards may leave the DOM.
                    for a in await page.locator("a[href*='/marketplace/item/']").all():
                        href = await a.get_attribute("href") or ""
                        match = re.search(r"/marketplace/item/(\d+)", href)
                        if not match or match[1] in seen:
                            continue
                        seen.add(match[1])
                        text = (await a.inner_text()).strip()
                        label = await a.get_attribute("aria-label") or ""
                        if not _matches_query_text(f"{label}\n{text}", filters):
                            continue
                        image = a.locator("img").first
                        img = await image.get_attribute("src") if await image.count() else None
                        listing = parse_card(href, text, label, img)
                        if listing is None:
                            continue
                        self.annotate_partial_price(listing)
                        if not self.matches_filters(listing, filters):
                            continue
                        ident = listing.listing_id
                        probe.card(ident, f"{label}\n{text}")
                        remembered = memory.get(ident)
                        if listing.published_at is not None:
                            origin = "card"
                        elif (stored := known.get(ident)) is not None:
                            listing.published_at, origin = stored, "known"
                        elif config.FB_FEED_DATES and (fed := await probe.feed_date(ident)) is not None:
                            listing.published_at, origin = fed, "feed"
                        else:
                            origin = "page"
                        if listing.published_at is None and remembered and remembered.skips(window.until):
                            skipped += 1
                            continue
                        read = False
                        if listing.published_at is None and fetched >= config.RECENT_FB_MAX_DATE_FETCHES:
                            results.complete, results.reason = False, DATE_FETCH_LIMIT
                        elif listing.published_at is None:
                            fetched += 1
                            await asyncio.sleep(config.RECENT_FB_DETAIL_SECONDS)
                            try:
                                listing.published_at = await self._publication_date(ctx, listing)
                                read = True
                            except CollectorBlocked:
                                raise
                            except Exception as exc:
                                results.complete, results.reason = False, f"facebook date fetch failed: {type(exc).__name__}"
                                log.warning("Could not read publication date for %s: %s", ident, exc)
                        probe.dated(ident, listing.published_at, origin)
                        if listing.published_at is None:
                            results.unknown_dates += 1
                            undated += read
                            if read and config.FB_DATE_MEMORY_UNKNOWN:
                                memory[ident] = DateSkip.undated(remembered, window.until)
                            continue
                        if window.admits(listing, remembered):
                            memory.pop(ident, None)
                            results.append(listing)
                        elif listing.published_at < window.since and (read or remembered):
                            memory[ident] = DateSkip()
                            if read:
                                out_of_window += 1
                    if results.reason == DATE_FETCH_LIMIT:
                        break
                    stalls = stalls + 1 if len(seen) == before else 0
                    if stalls >= 3:
                        body = _plain(await page.locator("body").inner_text())
                        if not seen and not any(s in body for s in (
                                "no se encontraron resultados", "no se encontraron publicaciones",
                                "no hay resultados", "no results found", "no listings found")):
                            raise CollectorBlocked("facebook: empty feed without a confirmed no-results message")
                        break
                    if scrolls >= config.RECENT_FB_MAX_SCROLLS:
                        results.complete, results.reason = False, "facebook: publication scan scroll limit reached"
                        break
                    await page.mouse.wheel(0, 4_000)
                    scrolls += 1
                    await page.wait_for_timeout(1_500)
            except Exception as exc:
                if not seen:
                    raise
                results.complete, results.reason = False, f"facebook: {type(exc).__name__}: {exc}"
            finally:
                self._probe = None
                await probe.close(page)
                await page.close()
        if remembering:
            if results.complete:
                memory = {i: s for i, s in memory.items() if i in seen}
            results.date_skips = encode_date_skips(memory)
        results.probe = probe.report(known)
        # How the cards were dated: feed_dates from the search page's data,
        # page_dates from an item page, unknown_dates not at all.
        log.info("facebook publication window: scrolls=%d kept=%d dates_read=%d feed_dates=%d page_dates=%d "
                 "skipped=%d out_of_window=%d undated=%d unknown_dates=%d feed_page_disagree=%d "
                 "complete=%s reason=%s", scrolls, len(results), fetched, probe.origins["feed"],
                 probe.origins["page"], skipped, out_of_window, undated, results.unknown_dates,
                 (results.probe or {}).get("feed_vs_page", [0, 0])[1], results.complete, results.reason)
        return results

    # 2: "Ver más" is expanded and the description stops before the page around it.
    DETAIL_PARSER_VERSION = 3
    parse_detail = staticmethod(parse_detail)

    async def fetch_detail_page(self, url: str) -> Page:
        if not Path(FB_STORAGE_STATE).exists():
            raise CollectorBlocked(f"facebook: no session at {FB_STORAGE_STATE}")
        page = await fetch_rendered(url, storage_state=FB_STORAGE_STATE, settle_ms=3_500, expand=_EXPAND,
                                    native=True)
        if "/login" in page.url or "checkpoint" in page.url:
            raise CollectorBlocked("facebook: session expired")
        return page

    def slim_page(self, page: Page) -> str:
        return slim_html(page.html, keep="[role='main']")


# ------ Interactive login: `python -m collectors.facebook [--auto]` ------
# Facebook revokes a session the first time it is used from an IP other than
# the one that logged in (2026-10-17: a PC login died on its first VPS
# request). So the VPS session is created on the VPS itself, through
# ops/vps/fb-login.sh, with the same user agent and viewport the worker uses
# for Facebook: the browser's own (native_user_agent), never a disguise.
LOGIN_TIMEOUT_SECONDS = 900


async def _session_ready(ctx, page) -> bool:
    url = page.url
    if "facebook.com" not in url or any(s in url for s in ("/login", "checkpoint", "two_step", "/recover")):
        return False
    return any(c.get("name") == "c_user" for c in await ctx.cookies("https://www.facebook.com"))


def _save_state(state: dict) -> None:
    import json, os
    tmp = f"{FB_STORAGE_STATE}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f)
    os.chmod(tmp, 0o600)
    os.replace(tmp, FB_STORAGE_STATE)


async def _login_and_save(*, auto: bool = False) -> None:
    from ._browser import VIEWPORT, native_user_agent
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False)
        ctx = await browser.new_context(locale="es-AR", user_agent=native_user_agent(browser.version),
                                        viewport=VIEWPORT)
        page = await ctx.new_page()
        await page.goto("https://www.facebook.com/login")
        if auto:
            print("Iniciá sesión en la ventana (y completá cualquier verificación). "
                  "La sesión se guarda sola cuando entres a la home.", flush=True)
            deadline = asyncio.get_running_loop().time() + LOGIN_TIMEOUT_SECONDS
            while not await _session_ready(ctx, page):
                if asyncio.get_running_loop().time() > deadline:
                    raise SystemExit("[facebook] no se completó el login a tiempo; no se guardó nada")
                await asyncio.sleep(2)
            # A session Facebook is about to revoke still has c_user right after
            # login; it only disappears on the next request. Prove it survives one.
            await page.wait_for_timeout(5_000)
            await page.goto("https://www.facebook.com/marketplace/", wait_until="domcontentloaded")
            await page.wait_for_timeout(4_000)
            if not await _session_ready(ctx, page):
                raise SystemExit("[facebook] Facebook cerró la sesión al recargar; no se guardó nada")
        else:
            print("Iniciá sesión en la ventana abierta. Cuando estés en la home, "
                  "volvé a esta consola y presioná Enter.")
            await asyncio.get_running_loop().run_in_executor(None, input, "")
        _save_state(await ctx.storage_state())
        print(f"[facebook] sesión guardada en {FB_STORAGE_STATE}", flush=True)
        await ctx.close()
        await browser.close()


if __name__ == "__main__":
    import sys
    asyncio.run(_login_and_save(auto="--auto" in sys.argv[1:]))

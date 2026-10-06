"""RosarioGarage's public used-vehicle finder and individual ad pages.

Brand IDs and category IDs come from the finder forms. Pagination uses the
advertised ``pagerTo`` offsets (95 ads), keeping the finder filters on every
request. Global premium cards are outside ``#item_results`` and are ignored.
"""
from __future__ import annotations

import asyncio
import logging
import re
import unicodedata
from urllib.parse import parse_qs, urlencode, urljoin, urlparse

import httpx

from ._http import HEADERS, Page, dedupe, multiline_text, soup, text_of, to_int
from .base import BaseScraper, CollectorBlocked, Listing, ListingDetail

log = logging.getLogger("collectors.rosariogarage")


def _norm(value: str) -> str:
    value = unicodedata.normalize("NFKD", value)
    value = "".join(c for c in value if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def _listing_id(url: str) -> str | None:
    values = parse_qs(urlparse(url).query).get("itmId", [])
    return values[0] if values and values[0].isdigit() else None


def _price(value: str | None) -> tuple[float | None, str | None]:
    if not value or not (match := re.search(r"(?:U\$S|US\$|USD|\$)\s*([\d.,]+)", value, re.I)):
        return None, None
    amount = match.group(1).replace(".", "").replace(",", ".")
    currency = "USD" if re.match(r"(?:U\$S|US\$|USD)", match.group(), re.I) else "ARS"
    try:
        return float(amount), currency
    except ValueError:
        return None, None


def _check_page(html: str, url: str, status: int) -> None:
    if status in (401, 403, 429):
        raise CollectorBlocked(f"rosariogarage: HTTP {status} for {url}")
    if status != 200:
        raise RuntimeError(f"rosariogarage: HTTP {status} for {url}")
    lowered = html.lower()
    if any(marker in lowered for marker in (
        "cf-chl-", "verify you are human", "just a moment...", "attention required!",
        "checking your browser", "security challenge",
    )):
        raise CollectorBlocked(f"rosariogarage: security challenge for {url}")
    doc = soup(html)
    # Detail pages contain a legitimate contact reCAPTCHA and a login link.
    # A password form is a wall only when the actual vehicle content is absent.
    if doc.select_one("input[type='password']") and not doc.select_one("#item_results, .box-main-product"):
        raise CollectorBlocked(f"rosariogarage: login wall for {url}")


class RosarioGarageScraper(BaseScraper):
    name = "rosariogarage"
    BASE = "https://www.rosariogarage.com"
    CATEGORIES = ("Autos", "Camionetas", "Utilitarios")
    MAX_PAGES = 20
    PAGE_PAUSE_SECONDS = 1.0
    RETRIES = 2
    RETRY_PAUSE_SECONDS = 2.0
    TIMEOUT = httpx.Timeout(60.0, connect=15.0)
    transport: httpx.AsyncBaseTransport | None = None

    def __init__(self, *, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.transport = transport
        self._forms: dict[str, tuple[str, dict[str, str]]] = {}

    async def _get(self, client: httpx.AsyncClient, url: str) -> httpx.Response:
        for attempt in range(self.RETRIES + 1):
            if attempt:
                await asyncio.sleep(self.RETRY_PAUSE_SECONDS * attempt)
            try:
                response = await client.get(url)
            except httpx.TransportError:
                if attempt == self.RETRIES:
                    raise
                continue
            if response.status_code < 500 or attempt == self.RETRIES:
                return response
        raise AssertionError("unreachable")

    async def _finder_form(self, client: httpx.AsyncClient, category: str) -> tuple[str, dict[str, str]]:
        if category not in self._forms:
            response = await self._get(client, f"{self.BASE}/{category}")
            _check_page(response.text, str(response.url), response.status_code)
            form = soup(response.text).select_one("form:has([name='itmModelDesc'])")
            rubro = form.select_one("input[name='rbrId']") if form else None
            options = form.select("select[name='mrkId'] option[value]") if form else []
            brands = {_norm(text_of(option) or ""): str(option["value"])
                      for option in options if option["value"]}
            if not rubro or not str(rubro.get("value", "")).isdigit() or not brands:
                raise RuntimeError(f"rosariogarage: finder form missing for {category}")
            self._forms[category] = str(rubro["value"]), brands
        return self._forms[category]

    def _build_url(self, filters: dict, rubro: str, brand_id: str | None, offset: int = 0) -> str:
        params = {"action": "finder/search", "o": str(offset), "rbrId": rubro, "optKm": "usados"}
        if brand_id:
            params["mrkId"] = brand_id
        if filters.get("modelo"):
            params["itmModelDesc"] = str(filters["modelo"])
        for field, key in (("anio_min", "year[from]"), ("anio_max", "year[to]"),
                           ("km_min", "km[from]"), ("km_max", "km[to]")):
            if filters.get(field) is not None:
                params[key] = str(int(filters[field]))
        if filters.get("anios"):
            params.setdefault("year[from]", str(min(filters["anios"])))
            params.setdefault("year[to]", str(max(filters["anios"])))
        # Price bounds only have meaning together with a requested currency.
        if filters.get("moneda") in ("ARS", "USD"):
            params["itmClass_price"] = "1" if filters["moneda"] == "ARS" else "2"
            for field, key in (("precio_min", "precio[from]"), ("precio_max", "precio[to]")):
                if filters.get(field) is not None:
                    params[key] = str(int(filters[field]))
        return f"{self.BASE}/index.php?{urlencode(params)}"

    @staticmethod
    def _next_offset(html: str, offset: int) -> int | None:
        doc = soup(html)
        choices = [int(o["value"]) for o in doc.select("select[name='pagerTo'] option[value]")
                   if str(o["value"]).isdigit() and int(o["value"]) > offset]
        if choices:
            return min(choices)
        for link in doc.select(".paginador a.next:not(.last)[href]"):
            if match := re.search(r"jumpToPage\((\d+)\)", str(link["href"])):
                value = int(match.group(1))
                if value > offset:
                    return value
        return None

    @classmethod
    def parse_search(cls, html: str) -> list[Listing]:
        doc = soup(html)
        out: dict[str, Listing] = {}
        for card in doc.select("#item_results .box_aviso_base"):
            title = card.select_one(".list_type_anuncio")
            anchor = title.find_parent("a", href=True) if title else None
            url = urljoin(cls.BASE, str(anchor["href"])) if anchor else ""
            lid = _listing_id(url)
            if not lid or not text_of(title):
                continue
            fields = [text_of(span) or "" for span in anchor.select("span:not(.last):not(.list_type_anuncio)")]
            year = next((int(v) for v in fields if re.fullmatch(r"(?:19|20)\d{2}", v)), None)
            km = next((to_int(v) for v in fields if re.search(r"\bkm\b", v, re.I)), None)
            fuel = next((v for v in fields if _norm(v) in
                         {"nafta", "diesel", "gnc", "electrico", "hibrido", "electrico hibrido"}), None)
            transmission = next((v for v in fields if v in ("MT", "AT")), None)
            dealer = card.select_one(".agencia a[title]:not([href*='wa.me'])")
            image = card.select_one(".carousel-inner img")
            image_url = (image.get("data-src") or image.get("src")) if image else None
            price, currency = _price(text_of(card.select_one(".precio")))
            out.setdefault(lid, Listing(
                source=cls.name, listing_id=lid, titulo=text_of(title)[:200], url=url,
                precio=price, moneda=currency, anio=year, km=km,
                combustible=fuel, transmision=transmission,
                vendedor="concesionaria" if dealer else None,
                vendedor_nombre=text_of(dealer),
                imagenes=[urljoin(cls.BASE, image_url)] if image_url else [],
            ))
        return list(out.values())

    async def search(self, filters: dict) -> list[Listing]:
        out: dict[str, Listing] = {}
        seen: set[str] = set()
        async with httpx.AsyncClient(timeout=self.TIMEOUT, headers=HEADERS, follow_redirects=True,
                                     transport=self.transport) as client:
            for category in self.CATEGORIES:
                rubro, brands = await self._finder_form(client, category)
                brand = _norm(str(filters.get("marca") or ""))
                brand_id = brands.get(brand)
                if brand and not brand_id:
                    continue  # Never replace an unknown brand with an unfiltered crawl.
                offset = 0
                category_seen: set[str] = set()
                for page_number in range(self.MAX_PAGES):
                    if page_number:
                        await asyncio.sleep(self.PAGE_PAUSE_SECONDS)
                    url = self._build_url(filters, rubro, brand_id, offset)
                    response = await self._get(client, url)
                    _check_page(response.text, str(response.url), response.status_code)
                    doc = soup(response.text)
                    if not doc.select_one("#item_results") and not re.search(
                        r"no se encontr(?:aron|o)|sin resultados", _norm(doc.get_text(" "))
                    ):
                        raise RuntimeError("rosariogarage: search results layout missing")
                    listings = self.parse_search(response.text)
                    if doc.select_one("#item_results .box_aviso_base") and not listings:
                        raise RuntimeError("rosariogarage: search cards could not be parsed")
                    fresh = [item for item in listings if item.listing_id not in category_seen]
                    if not fresh:
                        if listings and self._next_offset(response.text, offset) is not None:
                            raise RuntimeError("rosariogarage: pagination repeated a page with more results")
                        break
                    for item in fresh:
                        category_seen.add(item.listing_id)
                        if item.listing_id in seen:
                            continue
                        seen.add(item.listing_id)
                        self.annotate_partial_price(item)
                        if self.matches_filters(item, filters):
                            out[item.listing_id] = item
                    next_offset = self._next_offset(response.text, offset)
                    if next_offset is None:
                        break
                    if page_number + 1 == self.MAX_PAGES:
                        log.warning("rosariogarage: %s reached the %d-page cap with more results",
                                    category, self.MAX_PAGES)
                    offset = next_offset
        return list(out.values())

    async def fetch_detail_page(self, url: str) -> Page:
        async with httpx.AsyncClient(timeout=self.TIMEOUT, headers=HEADERS, follow_redirects=True,
                                     transport=self.transport) as client:
            response = await self._get(client, url)
        if response.status_code not in (404, 410):
            _check_page(response.text, str(response.url), response.status_code)
        return Page(response.status_code, str(response.url), response.text)

    @staticmethod
    def parse_detail(html: str, url: str, status: int = 200) -> ListingDetail:
        if status in (404, 410):
            return ListingDetail(url, gone=True, gone_reason=str(status))
        _check_page(html, url, status)
        doc = soup(html)
        article = doc.select_one(".box-main-product article")
        data = article.select_one(".box-data") if article else None
        title = text_of(article.select_one("h1")) if article else None
        if not article or not data or not title:
            raise RuntimeError("rosariogarage: individual vehicle layout missing")
        requested_id = _listing_id(url)
        canonical = doc.select_one("link[rel='canonical'][href]")
        canonical_id = _listing_id(str(canonical["href"])) if canonical else None
        if not canonical_id:
            raise RuntimeError("rosariogarage: individual vehicle identity missing")
        if requested_id and canonical_id and requested_id != canonical_id:
            return ListingDetail(url, gone=True, gone_reason="different listing")
        lid = requested_id or canonical_id
        if not lid:
            raise RuntimeError("rosariogarage: vehicle ID missing")

        sections = {}
        for heading in data.select(".subtitle"):
            body = heading.find_next_sibling("div", class_="box-text")
            if body:
                sections[_norm(text_of(heading) or "")] = body
        specs: dict[str, str] = {}
        info = sections.get("descripcion del anuncio")
        contact = sections.get("datos de contacto")
        for container in (info, contact):
            if container is None:
                continue
            for label in container.select("span"):
                key = (text_of(label) or "").rstrip(": ")
                values = []
                for sibling in label.next_siblings:
                    if getattr(sibling, "name", None) in ("br", "span", "div"):
                        break
                    values.append(text_of(sibling) if getattr(sibling, "name", None) else str(sibling))
                value = re.sub(r"\s+", " ", " ".join(v for v in values if v)).strip()
                if key and value:
                    specs[key] = value
        attributes = {_norm(key): value for key, value in specs.items()}
        if not attributes.get("marca") or not info:
            raise RuntimeError("rosariogarage: vehicle attributes missing")
        description_heading = article.select_one(".subtitle.first")
        description = description_heading.find_next_sibling("div", class_="box-text") if description_heading else None
        images = [urljoin(url, str(anchor["href"]))
                  for anchor in article.select("#myCarousel2 a[data-fancybox][href]")]
        if not images:
            images = [urljoin(url, str(image["src"])) for image in article.select("#myCarousel2 img[src]")]
        price, currency = _price(text_of(sections.get("precio")))
        seller = _norm(attributes.get("vendedor", ""))
        listing = Listing(
            source="rosariogarage", listing_id=lid, titulo=title[:200], url=url,
            marca=attributes.get("marca"), modelo=attributes.get("modelo"), version=attributes.get("version"),
            anio=to_int(attributes.get("ano")), km=to_int(attributes.get("kilometraje")),
            precio=price, moneda=currency, combustible=attributes.get("combustible"),
            transmision=attributes.get("transmision"),
            vendedor="particular" if seller == "dueno directo" else "concesionaria" if seller == "agencia" else None,
            ubicacion=", ".join(value for value in (attributes.get("ciudad"), attributes.get("provincia")) if value) or None,
            descripcion=multiline_text(description), imagenes=dedupe(images),
            atributos={key: value for key, value in specs.items()
                       if _norm(key) not in {"celular", "telefono", "email", "e mail"}},
        )
        return ListingDetail(url, listing=BaseScraper.annotate_partial_price(listing))

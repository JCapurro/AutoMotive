"""deRuedas (www.deruedas.com.ar): public search pages and each ad's own page.

deruedas.com is a parked domain; the classifieds live at www.deruedas.com.ar.
A search is one segment (cars or pickups/vans) plus the exact `Marca:Modelo`
of that segment's catalog. The site ignores a filter it does not know and
answers with the whole brand, so the first page must prove what was applied.
robots.txt asks for Crawl-delay 5: every request of the process shares one
slot per CRAWL_DELAY seconds, search and detail alike.
"""
from __future__ import annotations

import asyncio
import json
import logging
import math
import re
import threading
import time
from datetime import date
from urllib.parse import parse_qs, quote, unquote, urlencode, urljoin, urlparse

import httpx
from http_clients import async_client

from normalization.normalize import normalize_brand, normalize_text
from ._http import Page, json_ld_of_type, multiline_text, slim_html, soup, text_of, to_int
from ._regional import PublicCatalogScraper
from .base import CollectorBlocked, Listing, ListingDetail, SearchResults


logger = logging.getLogger(__name__)

_CARD = 'div.divVehiculo[itemscope][itemtype$="schema.org/Car"]'
_CHALLENGE = ("Just a moment", "cf-chl", "challenge-platform", "Attention Required")
_PRICE_RE = re.compile(r"(U\$S?|US\$|\$)\s*(\d{1,3}(?:\.\d{3})*|\d+)")
_KM_RE = re.compile(r"(\d+)\s*km", re.I)
# bus.asp also declares `var masContenido = false;` in its header on every page.
_MORE_RE = re.compile(r'<script class="newScript">\s*masContenido\s*=\s*(true|false)')
_UNAVAILABLE_RE = re.compile(r"no est[aá] disponible", re.I)
# Savings plans and paid installments in the seller's text. keyword_partial()
# is too broad here: agencies paste "cuotas" financing under full-price ads.
_PLAN_RE = re.compile(
    r"\bcuotas?\s+(?:pagas|abonadas|pagadas)"
    r"|\bplan\s+(?:de\s+ahorro|adjudicad\w*|ovalo|rombo|nacional)\b"
    r"|\badjudicad[oa]s?\b|\bcirculo\s+cerrado\b|\btransfiero\s+plan\b")
# Only a raw_pages copy starts with it: inside a live page it would be seller text.
_STORED = '<script type="application/json" id="eseauto-deruedas-detail">'
# Site models that vehicle_catalog files under another one (generations,
# Cross versions): a search for the latter walks them too.
_FILED_UNDER = {"fiestakd": "fiesta", "crossfox": "fox", "nuevopalio": "palio", "corsaii": "corsa",
                "golcountry": "gol", "grandsiena": "siena", "unoevo": "uno"}
# Catalog models the site files as a version of another: (brand, site model)
# -> (first word of the version, model). "Joy+" or "AT Plus" stay Onix.
_VARIANTS = {("chevrolet", "onix"): ("plus", "Onix Plus"), ("renault", "sandero"): ("stepway", "Stepway")}

# Crawl and enrichment run concurrently and share the host's crawl delay.
_clock = time.monotonic
_slot_lock = threading.Lock()
_next_slot = 0.0
_catalog_lock = threading.Lock()
_catalogs: dict[tuple[int, str], tuple[float, str | None, list[str]]] = {}


async def _throttle(delay: float) -> None:
    # A slot is taken only once awake: a late wake-up must not shorten the next gap.
    global _next_slot
    while True:
        with _slot_lock:
            now = _clock()
            if now >= _next_slot:
                _next_slot = now + delay
                return
            wait = _next_slot - now
        await asyncio.sleep(wait)


def _hold(delay: float) -> None:
    """The next slot also counts from the end of this request (handshake, slow answer)."""
    global _next_slot
    with _slot_lock:
        _next_slot = max(_next_slot, _clock() + delay)


def _key(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]", "", value or "")


def _tokens(value: str | None) -> list[str]:
    return re.findall(r"[a-z0-9]+", normalize_text(value))


def _model_of(marca: str | None, modelo: str | None, version: str | None) -> str | None:
    """The catalog model of an ad: "Onix" with version "Plus LS ..." is the Onix Plus."""
    variant = _VARIANTS.get((_key(normalize_brand(marca)), _key(normalize_text(modelo))))
    return variant[1] if variant and _tokens(version)[:1] == [variant[0]] else modelo


def _outside(path: str) -> bool:
    # httpx (or the server) drops dot segments: /vendo/../special/ is not /vendo/.
    return bool({".", ".."} & set(unquote(path).split("/")))


def _price(text: str | None) -> tuple[float | None, str | None]:
    """The visible price. Microdata is always ARS, converted by the site for USD ads."""
    match = _PRICE_RE.fullmatch((text or "").strip())
    amount = int(match[2].replace(".", "")) if match else 0
    if amount <= 1:
        return None, None
    return float(amount), "ARS" if match[1] == "$" else "USD"


def _km(text: str | None) -> int | None:
    match = _KM_RE.fullmatch((text or "").strip())
    return int(match[1]) if match and int(match[1]) > 1 else None


def _place(text: str | None) -> tuple[str | None, str | None, str | None]:
    """The site's "Provincia, Localidad" as (location text, province, town)."""
    province, _, town = (text or "").partition(", ")
    province, town = province.strip() or None, town.strip() or None
    return (f"{town}, {province}" if town else province), province, town


class DeRuedasScraper(PublicCatalogScraper):
    name = "deruedas"
    INVENTORY_TARGET = False    # thousands of ads: searched per make/model
    STRICT_DETAIL_ID = True
    DETAIL_PARSER_VERSION = 1
    BASE = "https://www.deruedas.com.ar"
    # 0 includes SUVs; 1 is pickups and vans. No "all" value exists, and the
    # other segments (motorcycles, savings plans, trucks) are never queried.
    SEGMENTS = {0: "Autos", 1: "Utilitarios y Camionetas"}
    CRAWL_DELAY = 6.0           # robots.txt: Crawl-delay 5
    RETRY_PAUSE = 30.0
    PAGE_SIZE = 30
    MAX_PAGES = 60
    CATALOG_TTL = 1800

    @staticmethod
    def _cod(url: str) -> str | None:
        values = parse_qs(urlparse(url).query).get("cod", [])
        return values[0] if len(values) == 1 and re.fullmatch(r"[0-9]+", values[0]) else None

    async def _fetch(self, url: str, *, detail: bool = False) -> Page:
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.hostname != urlparse(self.BASE).hostname:
            raise ValueError("deruedas: URL outside the source")
        if _outside(parsed.path) or not (
                parsed.path.startswith("/vendo/") if detail else parsed.path in ("/bus.asp", "/busCraw.asp")):
            raise ValueError("deruedas: URL outside the public search and detail pages")
        async with async_client(headers=self.HTTP_HEADERS, timeout=35, follow_redirects=False,
                                transport=self.transport) as client:
            for attempt in (1, 2):
                await _throttle(self.CRAWL_DELAY)
                try:
                    response = await client.get(url)
                except httpx.TransportError:
                    if attempt == 2:
                        raise
                    continue
                finally:
                    _hold(self.CRAWL_DELAY)
                status = response.status_code
                if status in (401, 403, 429):
                    raise CollectorBlocked(f"deruedas: HTTP {status}")
                try:
                    # No response declares a charset; every page is UTF-8.
                    html = response.content.decode("utf-8")
                except UnicodeDecodeError as e:
                    raise RuntimeError("deruedas: response is not UTF-8") from e
                if any(mark in html for mark in _CHALLENGE):
                    raise CollectorBlocked("deruedas: security challenge")
                if status < 500 or attempt == 2:
                    break
                logger.warning("deruedas: HTTP %s, retrying once in %ss", status, self.RETRY_PAUSE)
                await asyncio.sleep(self.RETRY_PAUSE)
        if 300 <= status < 400:
            # Never followed: a search redirect drops the order or the model. On a
            # detail, 302 to the home page is how the site answers for a removed ad.
            target = urljoin(url, response.headers.get("location", ""))
            if detail and status == 302 and target == self.BASE + "/" and self._cod(url):
                return Page(status, url, html)
            raise (CollectorBlocked if detail else RuntimeError)("deruedas: unexpected redirect")
        self.check_status(status)
        if status != 200:
            raise RuntimeError(f"deruedas: HTTP {status}")
        return Page(status, url, html)

    def _url(self, path: str, params: dict) -> str:
        return self.BASE + path + "?" + urlencode(params, quote_via=quote)

    @staticmethod
    def _params(segment: int, brand: str, model: str | None, years: dict) -> dict:
        # Never kilometraje (drops ads without km) nor precio_* (slider positions).
        params = {"segmento": segment, "marca": brand}
        if model:
            params["modelo"] = f"{brand}:{model}"
        return {**params, "condicion": "Usados", "order": 6, **years}

    @staticmethod
    def _years(filters: dict) -> dict[str, int]:
        """Year bounds the site can apply: outside its slider they are ignored."""
        top = date.today().year
        low, high = filters.get("anio_min"), filters.get("anio_max")
        years = {}
        if isinstance(low, int) and top - 30 < low <= top:
            years["anio_1"] = low
        if isinstance(high, int) and top - 30 < high < top:
            years["anio_2"] = high
        return years

    async def _catalog(self, segment: int, marca: str) -> tuple[str | None, list[str]]:
        """The segment's own spelling of the brand and its models with used stock."""
        key = (segment, _key(normalize_brand(marca)))
        with _catalog_lock:
            cached = _catalogs.get(key)
        if cached and _clock() - cached[0] < self.CATALOG_TTL:
            return cached[1], cached[2]
        sent, brand, models = marca, None, []
        for attempt in (1, 2):
            page = await self._fetch(self._url("/busCraw.asp", {
                **self._params(segment, sent, None, {}), "weNeed": "divFiltros", "pag": 1}))
            doc = soup(page.html)
            # Without a brand filter the only list holds brands (no "Marca:" prefix).
            brands = [v for i in doc.select("#divMarcasFancy input.fancyCheck") if (v := i.get("value"))] or [
                v for i in doc.select("#divModelosFancy input.fancyCheck") if (v := i.get("value")) and ":" not in v]
            if not brands:
                raise RuntimeError("deruedas: brand catalog missing")
            brand = next((b for b in brands if _key(normalize_brand(b)) == key[1]), None)
            if brand is None:
                break
            checked = [i.get("value") for i in doc.select("#divMarcasFancy input.fancyCheck[checked]")]
            if checked == [brand]:
                listed = [value[len(brand) + 1:] for i in doc.select("#divModelosFancy input.fancyCheck")
                          if (value := i.get("value") or "").startswith(brand + ":")]
                if not listed:
                    # Only brands with used stock are listed, each with its models.
                    raise RuntimeError("deruedas: model catalog missing")
                models = [m for m in listed if m and "," not in m]
                if len(models) != len(listed):
                    logger.info("deruedas: skipped catalog models that cannot be searched alone: %s",
                                [m for m in listed if m not in models])
                break
            # The models are the brand's only once the site recognized the
            # spelling sent, which differs per segment (Kia / KIA).
            if sent == brand or attempt == 2:
                raise RuntimeError("deruedas: brand filter not applied")
            sent = brand
        with _catalog_lock:
            _catalogs[key] = (_clock(), brand, models)
        return brand, models

    @staticmethod
    def _models(wanted: str, catalogs: dict[int, list[str]]) -> dict[int, list[str]]:
        """The catalog spellings to search for a model, per segment."""
        key, tokens = _key(normalize_text(wanted)), _tokens(wanted)
        if not key:
            return {}
        exact = {segment: [m for m in models if _key(normalize_text(m)) == key][:1]
                 + [m for m in models if _FILED_UNDER.get(_key(normalize_text(m))) == key]
                 for segment, models in catalogs.items()}
        if any(exact.values()):
            # Etios is listed in both segments; Hilux must not pull "Hilux SW4",
            # but Fiesta walks "Fiesta KD", which normalization files as Fiesta.
            return {segment: found for segment, found in exact.items() if found}
        loose = {}
        for segment, models in catalogs.items():
            # "Onix Plus" is filed under Onix (Plus is a version) and "SW4" as "Hilux SW4".
            leading = [m for m in models if (t := _tokens(m)) and tokens[:len(t)] == t]
            holding = [m for m in models if set(tokens) <= set(_tokens(m))]
            if leading:
                loose[segment] = [max(leading, key=lambda m: len(_tokens(m)))]
            elif len(holding) > 3:
                logger.info("deruedas: %r is ambiguous in segment %s: %s", wanted, segment, holding)
            elif holding:
                loose[segment] = holding
        if not loose:
            # Stepway is a Sandero version on the site: search the model it is filed under.
            parents = {parent for (_, parent), (_, variant) in _VARIANTS.items()
                       if _key(normalize_text(variant)) == key}
            loose = {segment: found for segment, models in catalogs.items()
                     if (found := [m for m in models if _key(normalize_text(m)) in parents][:1])}
        return loose

    @staticmethod
    def _applied(doc, brand: str, model: str | None, years: dict) -> int:
        """numberOfItems of a first page that proves the filters sent were applied.

        Title, breadcrumb and canonical name the model even when the site
        ignored it; the chip, the model list and the cards do not.
        """
        results = json_ld_of_type(doc, "SearchResultsPage") or {}
        entity = results.get("mainEntity")
        total = entity.get("numberOfItems") if isinstance(entity, dict) else None
        if isinstance(total, bool) or not isinstance(total, int) or total < 0:
            raise RuntimeError("deruedas: result count missing")
        wanted = f"{brand}:{model}" if model else None
        checked = [i.get("value") for i in doc.select("#divMarcasFancy input.fancyCheck[checked]")]
        chips = [(c.get("marcaval"), (c.get("modeloval") or "").casefold())
                 for c in doc.select("div.toggleModeloLink.cerrarItem_4")]
        listed = [i.get("value") for i in doc.select("#divModelosFancy input.fancyCheck")]
        if checked != [brand] or chips != ([(brand, wanted.casefold())] if model else []):
            raise RuntimeError("deruedas: model filter not applied")
        # The model list shrinks to the one searched, or to nothing without results.
        if model and listed != [wanted] and (listed or total):
            raise RuntimeError("deruedas: model filter not applied")
        if years and total:
            chip = doc.select_one('div.refreshLink.cerrarItem_2[refreshparam="anio_1|anio_2"]')
            shown = set(re.findall(r"[0-9]{4}", chip.get_text())) if chip else set()
            if not shown or not shown <= {str(v) for v in years.values()}:
                raise RuntimeError("deruedas: year filter not applied")
        return total

    @staticmethod
    def _more(html: str) -> bool:
        match = _MORE_RE.search(html)
        if not match:
            raise RuntimeError("deruedas: pagination marker missing")
        return match[1] == "true"

    @classmethod
    def _card(cls, card, segment: int | None = None) -> tuple[str, Listing | None]:
        """A result card's cod and listing; None for a card outside used stock."""
        def meta(prop: str) -> str | None:
            el = card.select_one(f'meta[itemprop="{prop}"]')
            return (el.get("content") or "").strip() or None if el else None

        match = re.fullmatch(r"car_([0-9]+)", card.get("id") or "")
        if not match:
            raise RuntimeError("deruedas: card without ID")
        cod = match[1]
        cods = {c for a in card.select("a[href]") for c in parse_qs(urlparse(a["href"]).query).get("cod", [])}
        if cods != {cod}:
            raise RuntimeError("deruedas: card links to another vehicle")
        link = card.select_one('a.versionLink[href], h2[itemprop="name"] a.titulo[href]')
        path = urlparse(link["href"]).path if link else ""
        if not path.startswith("/vendo/") or _outside(path):
            raise RuntimeError("deruedas: card without detail link")
        head = card.select_one('td[align="right"][valign="top"]')
        slot = text_of(head.select_one("span.texto b")) if head else None
        photo = card.select_one("img.imgCar_1")
        src = urljoin(cls.BASE, photo.get("src") or "") if photo else ""
        # New units and savings plans (whose price is a quota value) share the markup.
        if (path.split("/")[-2] not in ("Usados", "Usado") or "/images/vehiculos/" in src
                or re.search(r"\b0\s*km\b|cuota", slot or "", re.I)):
            return cod, None
        precio, moneda = _price(text_of(head.select_one("span.titulo")) if head else None)
        foot = card.select_one('td[colspan="2"][height="35"] span.texto')
        lines = [ln.strip() for ln in foot.get_text("\n").splitlines() if ln.strip()] if foot else []
        km = next((k for ln in lines if (k := _km(ln))), None) or _km(meta("mileageFromOdometer"))
        ubicacion, province, town = _place(lines[-1] if lines and not _KM_RE.fullmatch(lines[-1]) else None)
        marca, modelo, fuel = meta("brand"), meta("model"), meta("fuelType")
        version = text_of(card.select_one("a.versionLink"))
        # Agencies without a logo exist; only the site's clients are certain here.
        # Their link was ?codUsr=N until October 2026, then /@slug (nombreUsuario).
        seller = card.select_one('div.divCar_2 a[refreshparam="codUsr"], div.divCar_2 a[refreshparam="nombreUsuario"]')
        logo = seller.select_one('img[src*="/images/clientes/"]') if seller else None
        # "Entregá $ X y cuotas" is the site's own financing simulator, never a price.
        badge = text_of(card.select_one('td[height="40"] a.texto'))
        deposit = _PRICE_RE.search(badge or "")
        offer = card.select_one('[itemprop="offers"] meta[itemprop="price"]')
        extra = {"segmento": segment, "provincia": province, "localidad": town,
                 **({seller["refreshparam"]: seller.get("refreshvalue")} if seller else {}),
                 "financiable": bool(badge) or None,
                 "entrega_sugerida_ars": int(deposit[2].replace(".", "")) if deposit else None,
                 "precio_ars_sitio": to_int(offer.get("content")) if offer else None}
        item = Listing(source=cls.name, listing_id=cod,
            titulo=" ".join(filter(None, [marca, modelo, version])),
            url=cls.BASE + quote(unquote(path), safe="/-") + "?cod=" + cod,
            precio=precio, moneda=moneda, marca=marca, modelo=_model_of(marca, modelo, version), version=version,
            anio=to_int(meta("vehicleModelDate")), km=km, ubicacion=ubicacion, combustible=fuel,
            vendedor="agencia" if logo else None,
            vendedor_nombre=(logo.get("alt") or "").strip() or None if logo else None,
            atributos={k: v for k, v in {"Combustible": fuel, "Segmento": cls.SEGMENTS.get(segment)}.items() if v},
            imagenes=[src.replace("_1_tr.jpg", "_1_im.jpg")]
                     if re.search(rf"/images/autos/[^/]+/[0-9]+/{cod}_1_tr\.jpg", src) else [],
            extra={k: v for k, v in extra.items() if v is not None})
        return cod, cls.annotate_partial_price(item)

    @classmethod
    def parse_search(cls, html: str, segment: int | None = None) -> list[Listing]:
        return [item for card in soup(html).select(_CARD) if (item := cls._card(card, segment)[1])]

    async def _walk(self, segment: int, brand: str, model: str | None, years: dict,
                    found: dict[str, Listing], seen: set[str]) -> tuple[int, bool]:
        """Read every page of one search; (numberOfItems, cut by MAX_PAGES)."""
        params = self._params(segment, brand, model, years)
        html = (await self._fetch(self._url("/bus.asp", params))).html
        doc = soup(html)
        total = self._applied(doc, brand, model, years)
        pages = math.ceil(total / self.PAGE_SIZE)
        page = 1
        while True:
            cards = doc.select(_CARD)
            kept = 0
            for card in cards:
                names = [(el.get("content") or "").casefold() if (el := card.select_one(f'meta[itemprop="{p}"]'))
                         else "" for p in ("brand", "model")]
                # Later pages carry no chips: each card proves the filter still holds.
                if names[0] != brand.casefold() or (model and names[1] != model.casefold()):
                    raise RuntimeError("deruedas: model filter not applied")
                cod, item = self._card(card, segment)
                seen.add(cod)
                if item:
                    found[cod] = item
                    kept += 1
            if page == 1 and total and not cards:
                raise RuntimeError("deruedas: vehicle cards missing")
            # condicion=Usados never returned a new unit or a plan: a page of
            # nothing else means the filter or the card markup changed.
            if cards and not kept:
                raise RuntimeError("deruedas: cards outside used stock")
            # One page past the count absorbs ads published mid-walk.
            if not self._more(html) or len(cards) < self.PAGE_SIZE or page >= min(pages + 1, self.MAX_PAGES):
                return total, pages > self.MAX_PAGES
            page += 1
            html = (await self._fetch(self._url("/busCraw.asp", {
                **params, "weNeed": "divBusqueda", "pag": page}))).html
            doc = soup(html)

    async def _query(self, segment: int, brand: str, model: str | None,
                     years: dict) -> tuple[list[Listing], str | None]:
        """One search read to its end: its cards and, if any, why it is incomplete."""
        found: dict[str, Listing] = {}
        seen: set[str] = set()

        def short(total: int) -> bool:
            return len(seen) < total - max(2, math.ceil(.02 * total))

        total, capped = await self._walk(segment, brand, model, years, found, seen)
        if total == 0 and years:
            # A year-filtered zero is real while the model itself has stock: the
            # unfiltered first page proves it, the rest would be dropped here.
            page = await self._fetch(self._url("/bus.asp", self._params(segment, brand, model, {})))
            if self._applied(soup(page.html), brand, model, {}):
                return [], None
        if total == 0:
            # The catalog lists only models with stock: forget it and fail this run.
            with _catalog_lock:
                _catalogs.pop((segment, _key(normalize_brand(brand))), None)
            raise RuntimeError("deruedas: catalog lists model but search found 0")
        if not capped and short(total):
            # Ads published or removed mid-walk shift the pages: read them once more.
            total, capped = await self._walk(segment, brand, model, years, found, seen)
        reason = (f"deruedas: {total} resultados superan el tope" if capped else
                  f"deruedas: {len(seen)}/{total} avisos" if short(total) else None)
        return list(found.values()), reason

    async def search(self, filters: dict) -> SearchResults:
        marca = str(filters.get("marca") or "").strip()
        modelo = str(filters.get("modelo") or "").strip()
        if not marca:
            # Without marca the site redirects any modelo to the home page.
            raise ValueError("deruedas: la búsqueda necesita marca")
        brands, catalogs, spelling = {}, {}, marca
        for segment in self.SEGMENTS:
            brand, models = await self._catalog(segment, spelling)
            if brand:
                brands[segment], catalogs[segment], spelling = brand, models, brand
        wanted = self._models(modelo, catalogs) if modelo else {segment: [None] for segment in brands}
        if not wanted:
            logger.info("deruedas: %s %s has no used stock (catalog models per segment: %s)", marca,
                        modelo or "*", {segment: len(catalogs.get(segment, [])) for segment in self.SEGMENTS})
            return SearchResults([], complete=True)
        years = self._years(filters)
        found: dict[str, Listing] = {}
        reasons = []
        for segment, models in wanted.items():
            for model in models:
                items, reason = await self._query(segment, brands[segment], model, years)
                found.update((item.listing_id, item) for item in items if item.listing_id not in found)
                if reason:
                    reasons.append(reason)
        return SearchResults([item for item in found.values() if self.matches_filters(item, filters)],
                             complete=not reasons, reason="; ".join(reasons) or None)

    @classmethod
    def _fields(cls, html: str) -> dict:
        """The ad's own public fields: what parse_detail reads and raw_pages keeps."""
        doc = soup(html)
        stored = doc.select_one("script#eseauto-deruedas-detail") if html.startswith(_STORED) else None
        if stored:
            try:
                fields = json.loads(stored.string or "")
            except ValueError:
                fields = None
            if not isinstance(fields, dict):
                raise RuntimeError("deruedas: malformed stored detail")
            return fields
        vehicle = doc.select_one('[itemtype$="schema.org/Vehicle"]')
        sku = vehicle.select_one(':scope > meta[itemprop="sku"]') if vehicle else None
        cod = (sku.get("content") or "").strip() if sku else ""
        if not cod:
            raise RuntimeError("deruedas: vehicle identity missing")

        def meta(selector: str) -> str | None:
            el = vehicle.select_one(selector)
            return (el.get("content") or "").strip() or None if el else None

        info = doc.select_one("#divInfoPrincipal") or soup("")
        ficha = {}
        for cell in doc.select("#divFicha_1 td, #divFicha_2 td"):
            label, colon, value = (text_of(cell) or "").partition(":")
            # Visitas grows with every fetch, this one included.
            if colon and label.strip() != "Visitas":
                ficha[label.strip()] = value.strip()
        heading = doc.select_one("#equipamientoBase")
        equipment = heading.find_parent("div", class_="recuadro") if heading else None
        boxes = {}
        for box in equipment.select(".box-destacado") if equipment else []:
            label = next((ln.strip() for ln in box.get_text("\n").splitlines() if ln.strip()), None)
            if label and (value := text_of(box.select_one("b"))):
                boxes[label] = value
        row = equipment.select_one(":scope > div.row") if equipment else None
        comments = next((box.select_one(":scope > div.texto") for box in doc.select("#divFichaVehiculo div.recuadro")
                         if text_of(box.select_one(":scope > div.titulo")) == "Comentarios del Vendedor"), None)
        photos = sorted(doc.select("#divFichaVehiculo ul.slides.imgs-zoom li img[data-img]"),
                        key=lambda img: to_int(img.get("data-img")) or 0)
        contact = doc.select_one("#divContactoVehiculo") or soup("")
        client = contact.select_one('a.buscarMas.titulo[href*="codUsr="]')
        places = contact.select("h2")
        # Never kept: seller's name, address, map, hours, contact block, AI
        # blurb, similar ads, simulator.
        return {
            "sku": cod,
            "canonical": (doc.select_one('link[rel="canonical"]') or {}).get("href"),
            "brand": meta('[itemprop="brand"][itemtype$="schema.org/Brand"] meta[itemprop="name"]'),
            "model": meta(':scope > meta[itemprop="model"]'),
            "model_date": meta(':scope > meta[itemprop="modelDate"]'),
            "availability": meta('[itemprop="offers"] meta[itemprop="availability"]'),
            "offer_price": to_int(meta('[itemprop="offers"] meta[itemprop="price"]')),
            "h1": text_of(info.select_one("h1")),
            "version": text_of(info.select_one("h1 + span")),
            "header": [t for s in info.select("span.titulo:not(.resaltar)") if (t := text_of(s))],
            "header_price": text_of(info.select_one("span.texto.resaltar")),
            "ficha": ficha,
            "catalog": {
                "label_present": "Información de catálogo" in (text_of(heading.select_one("span.texto.mini")) or "")
                                 if heading else False,
                "cod_ver": to_int(m[1]) if heading and (m := re.search(r"codVer=([0-9]+)", str(heading))) else None,
                "boxes": boxes,
                "features": text_of(row.find_next_sibling("div", class_="texto")) if row else None,
            },
            "comments": multiline_text(comments),
            "images": [src for img in photos
                       if re.search(rf"/{cod}_[0-9]+_im\.jpg", src := img.get("src") or "")],
            "unavailable_text": next((t for s in contact.select("span.texto.inv")
                                      if _UNAVAILABLE_RE.search(t := text_of(s) or "")), None),
            # Inside the seller's box: without that box nothing about the seller is known.
            "contact_block": contact.select_one("#bloqueContacto") is not None,
            "seller": {
                "client": client is not None,
                "client_name": text_of(client),
                "stats": "Vehículos Vendidos" in contact.get_text(" "),
                "maps": contact.select_one("#linkMapsGoogle") is not None,
                "hours": bool(text_of(contact.select_one("#horariosTodos"))),
                "location_h2": text_of(places[-1]) if places else None,
            },
        }

    @classmethod
    def parse_detail(cls, html: str, url: str, status: int = 200) -> ListingDetail:
        cod = cls._cod(url)
        if status == 302:
            # Any URL without a cod redirects home too: only a numeric one proves removal.
            targets = {urljoin(url, a["href"]) for a in soup(html).select("a[href]")}
            if cod and targets == {cls.BASE + "/"}:
                return ListingDetail(url, gone=True, gone_reason="aviso eliminado (redirige al inicio)")
            raise CollectorBlocked("deruedas: unexpected redirect")
        cls.check_status(status)
        if status != 200:
            # The site never answers 404/410; if it did, it would not prove a removal.
            raise RuntimeError(f"deruedas: HTTP {status}")
        fields = cls._fields(html)
        # The site serves by cod alone and ignores the path: only IDs prove identity.
        if not cod or fields.get("sku") != cod or cls._cod(fields.get("canonical") or "") != cod:
            raise RuntimeError("deruedas: detail belongs to another vehicle")
        availability = (fields.get("availability") or "").rsplit("/", 1)[-1]
        if fields.get("unavailable_text"):
            return ListingDetail(url, gone=True, gone_reason=f"no disponible ({availability or 'sin estado'})")
        # Unavailable ads may still say InStock, so an active one needs both
        # signals; anything else is unknown, never gone.
        if not fields.get("contact_block") or availability != "InStock":
            raise RuntimeError("deruedas: listing state unknown")
        if not fields.get("h1"):
            raise RuntimeError("deruedas: vehicle title missing")
        ficha, catalog, seller = fields.get("ficha") or {}, fields.get("catalog") or {}, fields.get("seller") or {}
        precio, moneda = _price(ficha.get("Precio"))
        if (precio, moneda) != _price(fields.get("header_price")):
            raise RuntimeError("deruedas: header and specification prices differ")
        boxes = catalog.get("boxes") or {}
        attrs = {k: v for k, v in ficha.items() if v and k != "Última actualización"}
        attrs.update({f"Catálogo {k}": v for k, v in boxes.items()})
        if (catalog.get("features") or "No Especificado") != "No Especificado":
            attrs["Catálogo equipamiento"] = catalog["features"]
        comments = fields.get("comments")
        extra = {"ultima_actualizacion": ficha.get("Última actualización"), "codVer": catalog.get("cod_ver"),
                 "precio_ars_sitio": fields.get("offer_price")}
        item = Listing(source=cls.name, listing_id=cod, url=url,
            titulo=" ".join(filter(None, [fields["h1"], fields.get("version")])),
            precio=precio, moneda=moneda, marca=fields.get("brand"),
            modelo=_model_of(fields.get("brand"), fields.get("model"), fields.get("version")),
            version=fields.get("version"), anio=to_int(ficha.get("Año")) or to_int(fields.get("model_date")),
            km=_km(ficha.get("Kilometraje")),
            ubicacion=_place(seller.get("location_h2"))[0] or ficha.get("Ubicación") or None,
            # The ad's own fuel; the catalog box says Nafta for cars converted to GNC.
            combustible=next((h for h in fields.get("header") or [] if not re.fullmatch(r"[0-9]{4}", h)), None),
            transmision=boxes.get("Transmisión") if catalog.get("label_present") else None,
            # Any dealer signal means agency; only the site's clients are named.
            vendedor="agencia" if any(seller.get(k) for k in ("client", "stats", "maps", "hours")) else "particular",
            vendedor_nombre=seller.get("client_name") if seller.get("client") else None,
            descripcion=None if comments == "Ninguno" else comments,
            imagenes=list(dict.fromkeys(fields.get("images") or [])), atributos=attrs,
            extra={k: v for k, v in extra.items() if v is not None})
        cls.annotate_partial_price(item)
        if not item.price_partial and (plan := _PLAN_RE.search(normalize_text(item.descripcion))):
            item.price_partial, item.price_partial_reason = True, f"plan (deruedas): {plan[0]}"
        return ListingDetail(url, listing=item)

    async def fetch_detail_page(self, url: str) -> Page:
        # Without a numeric cod the site redirects home, exactly like a removed ad.
        if not self._cod(url):
            raise ValueError("deruedas: detail URL without a numeric cod")
        return await self._fetch(url, detail=True)

    def slim_page(self, page: Page) -> str:
        if page.status == 302:
            return slim_html(page.html)
        try:
            fields = self._fields(page.html)
        except RuntimeError:
            # Kept for diagnosis, without the seller's box or other people's ads.
            doc = soup(slim_html(page.html))
            for tag in doc.select('#divContactoVehiculo, #divOpinion, #divMail, .similares, [itemprop="review"]'):
                tag.decompose()
            return str(doc)
        return _STORED + json.dumps(fields, ensure_ascii=False).replace("<", "\\u003c") + "</script>"

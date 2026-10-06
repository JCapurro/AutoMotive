"""Usados Santa Fe: public Next.js data and the catalog's 'load more' button."""
from __future__ import annotations

import json
import re
from typing import Awaitable, Callable, Iterator
from urllib.parse import urlparse

import httpx

from normalization.money import parse_number
from ._browser import browser_context
from ._http import Page, dedupe, json_ld_of_type, multiline_text, slim_html, soup, text_of, to_int
from ._regional import PublicCatalogScraper, matches_vehicle, price, timestamp
from .base import Listing, ListingDetail


def _walk(value) -> Iterator[dict]:
    if isinstance(value, dict):
        yield value
        for item in value.values():
            yield from _walk(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk(item)


def _records(doc) -> list[dict]:
    saved = doc.select_one("script#eseauto-vehicles")
    if saved:
        return json.loads(saved.get_text())
    chunks: list[str] = []
    for script in doc.select("script"):
        match = re.search(r"self\.__next_f\.push\((.*)\)", script.get_text(), re.S)
        if match:
            try:
                data = json.loads(match[1])
                if len(data) > 1 and data[0] == 1 and isinstance(data[1], str):
                    chunks.append(data[1])
            except (ValueError, TypeError):
                continue
    # Flight records can be split over scripts, and text records need not end
    # with a newline. Decode JSON, never execute the page's JavaScript.
    stream = "".join(chunks)
    decoder = json.JSONDecoder()
    records: dict[str, dict] = {}
    for match in re.finditer(r"[0-9a-f]+:(?=[\[{])", stream):
        try:
            value, _ = decoder.raw_decode(stream, match.end())
        except ValueError:
            continue
        for record in _walk(value):
            if record.get("id") and record.get("tipo") and record.get("marca"):
                records[str(record["id"])] = record
    return list(records.values())


class UsadosSantaFeScraper(PublicCatalogScraper):
    name = "usadossantafe"
    BASE = "https://usadossantafe.com.ar"
    CATALOGS = ("/autos", "/camionetas")
    TYPES = {"Auto", "Camioneta", "SUV", "Furgón", "Utilitario", "Pickup"}
    # Whitelist public listing facts for retained raw pages, excluding account,
    # moderation and contact fields embedded by the site's frontend.
    FIELDS = {"id", "tipo", "marca", "modelo", "version", "anio", "kilometraje", "precio",
              "moneda", "combustible", "transmision", "transmisión", "ciudad", "provincia",
              "descripcion", "fecha", "fechaCreacion", "imagen1", "imagen2", "imagen3", "imagen4",
              "otrasImagenes", "vendido", "activo", "borrado", "rechazado", "etiqueta"}

    def __init__(self, *, transport: httpx.AsyncBaseTransport | None = None,
                 render_catalog: Callable[[str], Awaitable[Page]] | None = None):
        super().__init__(transport=transport)
        self.render_catalog = render_catalog or self._render_full

    @classmethod
    def _id(cls, url: str) -> str:
        match = re.search(r"(?:^|/|-)(\d{6}-\d{4}-[A-Za-z0-9]+)/?$", urlparse(url).path)
        if not match:
            raise ValueError("usadossantafe: missing ad ID")
        return match[1]

    @classmethod
    def _listing(cls, data: dict) -> Listing:
        title = " ".join(str(data.get(k) or "") for k in ("marca", "modelo", "version")).strip()
        amount = parse_number(str(data.get("precio") or ""))
        currency = {"$$": "ARS", "$": "ARS", "ARS": "ARS", "USD": "USD",
                    "U$S": "USD", "U$D": "USD", "US$": "USD"}.get(str(data.get("moneda", "")).upper())
        description = multiline_text(soup(str(data.get("descripcion") or "")))
        item = Listing(source=cls.name, listing_id=str(data["id"]), titulo=title,
            url=cls.BASE + "/aviso/" + str(data["id"]), marca=data.get("marca") or None,
            modelo=data.get("modelo") or None, version=data.get("version") or None,
            anio=to_int(data.get("anio")), km=to_int(data.get("kilometraje")),
            precio=amount if amount and amount > 1 else None, moneda=currency,
            combustible=data.get("combustible") or None,
            transmision=data.get("transmision") or data.get("transmisión") or None,
            ubicacion=data.get("ciudad") or data.get("provincia") or None,
            vendedor="particular" if str(data.get("etiqueta", "")).upper() == "TITULAR" else None,
            descripcion=description, published_at=timestamp(data.get("fechaCreacion") or data.get("fecha")),
            imagenes=dedupe([data.get(f"imagen{i}") for i in range(1, 5)] +
                            (data.get("otrasImagenes") or [])))
        return cls.annotate_partial_price(item)

    @classmethod
    def parse_search(cls, html: str) -> list[Listing]:
        doc = soup(html)
        records = _records(doc)
        cards = doc.select("[id^='aviso-']")
        if not records and not cards:
            # An explicitly empty structured catalog is healthy; changed markup isn't.
            if not re.search(r'\\?"avisosIniciales\\?"\s*:\s*\[\s*\]', html):
                raise RuntimeError("usadossantafe: catalog data missing")
        seen: dict[str, Listing] = {}
        excluded: set[str] = set()
        for record in records:
            lid = str(record["id"])
            if (record.get("tipo") not in cls.TYPES or record.get("vendido")
                or record.get("activo") is False or record.get("borrado") or record.get("rechazado")):
                excluded.add(lid)
                continue
            seen[lid] = cls._listing(record)
        for card in cards:
            lid = card["id"][6:]
            if lid in seen or lid in excluded or re.search(r"\bvendido\b", text_of(card) or "", re.I):
                continue
            title = text_of(card.select_one("h2"))
            if not title:
                raise RuntimeError("usadossantafe: incomplete rendered card")
            specs = [text_of(el) or "" for el in card.select("[class*='infoItem']")]
            amount, currency = price(text_of(card.select_one("[class*='precionum']")))
            image = card.select_one("img[src]")
            seen[lid] = cls.annotate_partial_price(Listing(source=cls.name, listing_id=lid,
                titulo=title + (" " + v if (v := text_of(card.select_one("h3"))) else ""),
                url=cls.BASE + "/aviso/" + lid, precio=amount, moneda=currency,
                anio=next((int(v) for v in specs if re.fullmatch(r"(?:19|20)\d{2}", v)), None),
                km=next((to_int(v) for v in specs if re.search(r"\bkm\b", v, re.I)), None),
                combustible=next((v for v in specs if re.search(r"nafta|diesel|diésel|gnc|híbr|eléct", v, re.I)), None),
                transmision=next((v for v in specs if re.search(r"manual|autom", v, re.I)), None),
                ubicacion=text_of(card.select_one("[class*='titulo2']")),
                imagenes=[image["src"]] if image else []))
        return list(seen.values())

    @staticmethod
    async def _render_full(url: str) -> Page:
        async with browser_context() as context:
            page = await context.new_page()
            response = await page.goto(url, wait_until="domcontentloaded", timeout=45_000)
            await page.wait_for_timeout(2_000)
            button = page.get_by_role("button", name="Cargar más avisos", exact=True)
            if await button.count():
                await button.click(timeout=5_000)
                # The site's button disappears only on successful completion.
                # A failed Firebase read leaves it present and must fail the run.
                await button.wait_for(state="hidden", timeout=45_000)
                # Allow the concurrent React render to commit the new cards.
                await page.wait_for_timeout(500)
            return Page(response.status if response else 0, page.url, await page.content())

    async def search(self, filters: dict) -> list[Listing]:
        seen: dict[str, Listing] = {}
        for path in self.CATALOGS:
            url = self.BASE + path
            page = await self._get(url)
            if page.status != 200:
                raise RuntimeError(f"usadossantafe catalog HTTP {page.status}")
            if any("Cargar más avisos" == text_of(b) for b in soup(page.html).select("button")):
                page = await self.render_catalog(url)
                self.check_status(page.status)
                if page.status != 200:
                    raise RuntimeError(f"usadossantafe rendered catalog HTTP {page.status}")
                if any("Cargar más avisos" == text_of(b) for b in soup(page.html).select("button")):
                    raise RuntimeError("usadossantafe: additional catalog load did not complete")
            for item in self.parse_search(page.html):
                if matches_vehicle(item, filters):
                    seen[item.listing_id] = item
        return list(seen.values())

    @classmethod
    def parse_detail(cls, html: str, url: str, status: int = 200) -> ListingDetail:
        cls.check_status(status)
        if status in (404, 410):
            return ListingDetail(url, gone=True, gone_reason=f"HTTP {status}")
        lid = cls._id(url)
        doc = soup(html)
        car = json_ld_of_type(doc, "Car", "Vehicle")
        # The primary structured vehicle proves the response's identity.
        car_url = (car or {}).get("url") or (doc.select_one("link[rel='canonical']") or {}).get("href")
        if not car_url or cls._id(car_url) != lid:
            raise RuntimeError("usadossantafe: primary vehicle missing or response ID mismatch")
        record = next((r for r in _records(doc) if str(r.get("id")) == lid), None)
        if record:
            if record.get("vendido") or record.get("activo") is False or record.get("borrado"):
                return ListingDetail(url, gone=True, gone_reason="aviso vendido o desactivado")
            item = cls._listing(record)
            item.url = url
            return ListingDetail(url, listing=item)
        if not car:
            raise RuntimeError("usadossantafe: vehicle facts missing")
        offer = car.get("offers") or {}
        if str(offer.get("availability", "")).endswith(("SoldOut", "Discontinued")):
            return ListingDetail(url, gone=True, gone_reason="vendido")
        address = (offer.get("availableAtOrFrom") or {}).get("address") or {}
        amount = parse_number(str(offer.get("price") or ""))
        item = Listing(source=cls.name, listing_id=lid, titulo=car["name"], url=url,
            marca=(car.get("brand") or {}).get("name"), modelo=car.get("model"),
            anio=to_int(car.get("productionDate")), km=to_int((car.get("mileageFromOdometer") or {}).get("value")),
            precio=amount if amount and amount > 1 else None, moneda=offer.get("priceCurrency"),
            combustible=car.get("fuelType"), transmision=car.get("vehicleTransmission"),
            ubicacion=", ".join(v for k in ("addressLocality", "addressRegion") if (v := address.get(k))) or None,
            descripcion=car.get("description"), published_at=timestamp(car.get("datePublished")),
            imagenes=dedupe(car.get("image") if isinstance(car.get("image"), list) else [car.get("image")]))
        # JSON-LD's seller is the portal itself, not the owner of the vehicle.
        return ListingDetail(url, listing=cls.annotate_partial_price(item))

    def slim_page(self, page: Page) -> str:
        doc = soup(slim_html(page.html))
        records = _records(soup(page.html))
        if records:
            records = [r for r in records if str(r.get("id")) == self._id(page.url)]
            tag = doc.new_tag("script", id="eseauto-vehicles", type="application/json")
            tag.string = json.dumps([{k: v for k, v in r.items() if k in self.FIELDS} for r in records],
                                    ensure_ascii=False).replace("</", "<\\/")
            (doc.body or doc).append(tag)
        return str(doc)

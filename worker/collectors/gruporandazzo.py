"""Grupo Randazzo's public VTEX REST stock and own SSR specifications."""
from __future__ import annotations

import asyncio
import json
import logging
import re
from urllib.parse import urlencode, urlparse

import httpx
from http_clients import async_client

from normalization.money import parse_number
from ._http import HEADERS, Page, dedupe, multiline_text, slim_html, soup, to_int
from ._regional import PublicCatalogScraper, matches_vehicle
from .base import CollectorBlocked, Listing, ListingDetail


logger = logging.getLogger(__name__)


class GrupoRandazzoScraper(PublicCatalogScraper):
    name = "gruporandazzo"
    STRICT_DETAIL_ID = True
    BASE = "https://www.gruporandazzo.com"
    # Exact href published by the Estado=Disponible facet, verified publicly.
    CATALOG = BASE + "/usados/disponible?map=estado"
    API = BASE + "/api/catalog_system/pub/products/search"
    CATEGORY_ID = 40  # /Usados/, stated by the catalog's own Product objects.
    PAGE_SIZE = 50
    MAX_PAGES = 50
    PAGE_DELAY = .2

    @staticmethod
    def _data(html: str) -> tuple[dict, str | None]:
        doc = soup(html)
        stored = doc.select_one("script#eseauto-randazzo-product")
        if stored:
            try:
                return {"storedProduct": json.loads(stored.string or "")}, None
            except ValueError as e:
                raise RuntimeError("gruporandazzo: malformed stored vehicle") from e
        script = next((s.string or "" for s in doc.select("script")
                       if "__STATE__" in (s.string or "")), "")
        match = re.search(r"__STATE__\s*=\s*", script)
        runtime = re.search(r"__RUNTIME__\s*=\s*", script)
        if not match or not runtime:
            raise RuntimeError("gruporandazzo: public catalog state missing")
        try:
            state, _ = json.JSONDecoder().raw_decode(script[match.end():])
            settings, _ = json.JSONDecoder().raw_decode(script[runtime.end():])
        except ValueError as e:
            raise RuntimeError("gruporandazzo: malformed public state") from e
        currency = (settings.get("culture") or {}).get("currency")
        return state, currency if currency in ("ARS", "USD") else None

    @classmethod
    def _resolve(cls, state: dict, value, depth: int = 0):
        if depth > 20:
            raise RuntimeError("gruporandazzo: cyclic product state")
        if isinstance(value, list):
            return [cls._resolve(state, v, depth + 1) for v in value]
        if not isinstance(value, dict):
            return value
        if value.get("type") == "json" and "json" in value:
            return value["json"]
        if value.get("type") == "id" and "id" in value:
            if value["id"] not in state:
                raise RuntimeError("gruporandazzo: incomplete product state")
            return cls._resolve(state, state[value["id"]], depth + 1)
        return {k: cls._resolve(state, v, depth + 1) for k, v in value.items()}

    @classmethod
    def _product(cls, state: dict, reference: dict, currency: str | None) -> dict:
        raw = state.get(reference.get("id"))
        if not isinstance(raw, dict) or raw.get("__typename") != "Product":
            raise RuntimeError("gruporandazzo: own product missing")
        # Only resolve attributes belonging to this Product. The full Apollo
        # state also contains facets, unrelated products and reservation offers.
        keys = ("productId", "productReference", "productName", "description", "linkText", "brand", "categories", "properties")
        product = {k: cls._resolve(state, raw.get(k)) for k in keys}
        sku_key = next((k for k in raw if k == "items" or k.startswith("items(")), None)
        skus = cls._resolve(state, raw.get(sku_key, [])) if sku_key else []
        product["images"] = [image.get("imageUrl") for sku in skus for image in sku.get("images") or []]
        product["currency"] = currency
        return product

    @staticmethod
    def _attributes(product: dict) -> dict[str, str]:
        return {p["name"]: " / ".join(str(v) for v in p.get("values") or [])
                for p in product.get("properties") or [] if p.get("name")}

    @classmethod
    def _listing(cls, product: dict) -> Listing | None:
        attrs = cls._attributes(product)
        # A few new vehicles are incorrectly filed under /Usados/ and have no
        # Estado at all. Explicit zero mileage proves they are outside scope.
        if to_int(attrs.get("Km")) == 0:
            return None
        state = attrs.get("Estado", "").strip().lower()
        if state not in ("disponible", "reservado", "a ingresar", "vendido"):
            raise RuntimeError("gruporandazzo: vehicle state missing or unknown")
        if not product.get("categories"):
            raise RuntimeError("gruporandazzo: vehicle category missing")
        if "/Usados/" not in product.get("categories", []) or state != "disponible":
            return None
        if attrs.get("Tipo de vehículo", "").lower() in ("moto", "motocicleta"):
            return None
        if attrs.get("Tipo plan", "-s/d-").strip().lower() not in ("", "-s/d-", "s/d", "no"):
            return None
        if not product.get("productId") or not product.get("productReference") or not product.get("linkText") or not product.get("productName"):
            raise RuntimeError("gruporandazzo: incomplete vehicle identity")
        if not str(product["linkText"]).lower().startswith(str(product["productReference"]).lower() + "-"):
            raise RuntimeError("gruporandazzo: vehicle link ID mismatch")
        amount = parse_number(attrs.get("Precio") or "")
        amount = amount if amount and amount > 1 else None
        currency = product.get("currency")
        if currency not in ("ARS", "USD"):
            amount, currency = None, None
        item = Listing(source=cls.name, listing_id=str(product["productReference"]),
            titulo=product["productName"], url=cls.BASE + "/" + product["linkText"] + "/p",
            marca=product.get("brand") or None, modelo=attrs.get("Modelo") or None,
            anio=to_int(attrs.get("Año")), km=to_int(attrs.get("Km")),
            precio=amount, moneda=currency, combustible=attrs.get("Combustible") or None,
            transmision=attrs.get("Caja") or None,
            ubicacion=attrs.get("Sucursal") or attrs.get("Ubicación") or None,
            vendedor="agencia", vendedor_nombre="Grupo Randazzo", atributos=attrs,
            descripcion=multiline_text(soup("<div>" + (product.get("description") or "") + "</div>")),
            imagenes=dedupe(product.get("images") or []))
        return cls.annotate_partial_price(item)

    @classmethod
    def _catalog(cls, html: str, *, available_only: bool = False) -> tuple[list[Listing], list[str], int, int]:
        state, currency = cls._data(html)
        entries = [(key, ref) for key, ref in state.get("ROOT_QUERY", {}).items() if key.startswith("productSearch(")]
        if len(entries) != 1:
            raise RuntimeError("gruporandazzo: catalog query missing or ambiguous")
        key, reference = entries[0]
        try:
            args, _ = json.JSONDecoder().raw_decode(key.removeprefix("productSearch("))
        except ValueError as e:
            raise RuntimeError("gruporandazzo: malformed catalog query") from e
        if available_only and (args.get("query") != "usados/disponible" or
                {"key": "estado", "value": "disponible"} not in args.get("selectedFacets", [])):
            raise RuntimeError("gruporandazzo: available stock filter was not applied")
        offset = re.search(r'"from"\s*:\s*(\d+)', key)
        data = state.get(reference.get("id"), {})
        total = data.get("recordsFiltered")
        refs = data.get("products")
        if not offset or not isinstance(total, int) or not isinstance(refs, list):
            raise RuntimeError("gruporandazzo: incomplete catalog metadata")
        if total and not refs:
            raise RuntimeError("gruporandazzo: vehicle cards missing")
        products = [cls._product(state, ref, currency) for ref in refs]
        ids = [str(p["productId"]) for p in products]
        return ([item for p in products if (item := cls._listing(p))], ids, total, int(offset[1]))

    @classmethod
    def parse_search(cls, html: str) -> list[Listing]:
        return cls._catalog(html)[0]

    async def _public_json(self, url: str) -> tuple[httpx.Response, object]:
        if urlparse(url).hostname != urlparse(self.BASE).hostname:
            raise ValueError("gruporandazzo: URL outside the source")
        async with async_client(headers=HEADERS, timeout=45, follow_redirects=False,
                                     transport=self.transport) as client:
            response = await client.get(url)
        if response.is_redirect:
            raise CollectorBlocked("gruporandazzo: unexpected catalog API redirect")
        if response.status_code not in (200, 206):
            self.check_status(response.status_code)
            raise RuntimeError(f"gruporandazzo: catalog API HTTP {response.status_code}")
        try:
            return response, response.json()
        except ValueError as e:
            raise RuntimeError("gruporandazzo: invalid catalog API JSON") from e

    @classmethod
    def _api_product(cls, record: dict, currency: str) -> dict:
        names = record.get("allSpecifications")
        if not isinstance(names, list):
            raise RuntimeError("gruporandazzo: catalog specifications missing")
        product = {k: record.get(k) for k in ("productId", "productReference", "productName",
                   "description", "linkText", "brand", "categories")}
        product["properties"] = [{"name": name, "values": record[name]} for name in names
                                 if isinstance(record.get(name), list)]
        product["images"] = [image.get("imageUrl") for sku in record.get("items") or []
                             for image in sku.get("images") or []]
        product["currency"] = currency
        return product

    async def _api_catalog(self, offset: int, currency: str, state_field: int) -> tuple[list[Listing], list[str], int]:
        params = [("fq", f"C:/{self.CATEGORY_ID}/"),
                  ("fq", f"specificationFilter_{state_field}:Disponible"),
                  ("_from", str(offset)), ("_to", str(offset + self.PAGE_SIZE - 1)),
                  ("O", "OrderByReleaseDateDESC")]
        response, records = await self._public_json(self.API + "?" + urlencode(params))
        interval = re.fullmatch(r"(\d+)-(\d+)/(\d+)", response.headers.get("resources", ""))
        if not interval or not isinstance(records, list):
            raise RuntimeError("gruporandazzo: catalog range metadata missing")
        start, end, total = map(int, interval.groups())
        if start != offset or end not in (offset + self.PAGE_SIZE - 1, min(offset + self.PAGE_SIZE - 1, total - 1)):
            raise RuntimeError("gruporandazzo: incorrect catalog range")
        if len(records) != min(self.PAGE_SIZE, max(0, total - offset)):
            raise RuntimeError("gruporandazzo: incomplete catalog range")
        products = [self._api_product(record, currency) for record in records]
        available = False
        for product in products:
            if "/Usados/" not in (product.get("categories") or []):
                raise RuntimeError("gruporandazzo: available stock filter was not applied")
            state = self._attributes(product).get("Estado")
            if state not in ("Disponible", "Reservado", "A Ingresar", "Vendido"):
                raise RuntimeError("gruporandazzo: vehicle state missing or unknown")
            if state == "Disponible":
                available = True
            else:
                # The search index can lag behind a unit's own specifications.
                # Keep its ID in the complete range, but its current state
                # determines whether it is eligible for the used inventory.
                logger.warning("gruporandazzo: excluded %s with current Estado=%s from Disponible index",
                               product.get("productReference") or product.get("productId"), state)
        if products and not available:
            raise RuntimeError("gruporandazzo: available stock filter was not applied")
        ids = [str(p.get("productId") or "") for p in products]
        if any(not i for i in ids):
            raise RuntimeError("gruporandazzo: incomplete vehicle identity")
        return [item for p in products if (item := self._listing(p))], ids, total

    async def search(self, filters: dict) -> list[Listing]:
        # The page publishes currency and the category; stock is read through
        # the same public REST search used by the site's cross-selling widget.
        # Its Resources header proves each 50-record range and the total.
        page = await self._get(self.CATALOG)
        if page.status != 200:
            raise RuntimeError(f"gruporandazzo: catalog HTTP {page.status}")
        _, currency = self._data(page.html)
        if currency is None:
            raise RuntimeError("gruporandazzo: catalog currency missing")
        _, fields = await self._public_json(self.BASE + f"/api/catalog_system/pub/facets/category/{self.CATEGORY_ID}")
        state_fields = [f.get("Id") for f in fields if isinstance(f, dict) and f.get("Name") == "Estado"] if isinstance(fields, list) else []
        if len(state_fields) != 1 or not isinstance(state_fields[0], int):
            raise RuntimeError("gruporandazzo: public Estado facet missing")
        result, seen, expected = {}, set(), None
        for page_number in range(1, self.MAX_PAGES + 1):
            if page_number > 1:
                await asyncio.sleep(self.PAGE_DELAY)
            offset = (page_number - 1) * self.PAGE_SIZE
            items, ids, total = await self._api_catalog(offset, currency, state_fields[0])
            if expected is None:
                expected = total
            if total != expected or total < 0:
                raise RuntimeError("gruporandazzo: inventory changed during pagination")
            if len(ids) != len(set(ids)) or seen.intersection(ids):
                raise RuntimeError("gruporandazzo: repeated or incorrect pagination page")
            seen.update(ids)
            for item in items:
                if item.listing_id in result:
                    raise RuntimeError("gruporandazzo: vehicle reference shared by different IDs")
                result[item.listing_id] = item
            if len(seen) == expected:
                return [item for item in result.values() if matches_vehicle(item, filters)]
            if len(ids) != self.PAGE_SIZE or len(seen) > expected:
                raise RuntimeError("gruporandazzo: incomplete pagination")
        raise RuntimeError("gruporandazzo: pagination limit reached")

    @classmethod
    def _detail_product(cls, html: str) -> dict:
        state, currency = cls._data(html)
        if "storedProduct" in state:
            return state["storedProduct"]
        references = [v for k, v in state.get("ROOT_QUERY", {}).items() if k.startswith("product(")]
        if len(references) != 1:
            raise RuntimeError("gruporandazzo: own vehicle query missing or ambiguous")
        return cls._product(state, references[0], currency)

    @classmethod
    def parse_detail(cls, html: str, url: str, status: int = 200) -> ListingDetail:
        cls.check_status(status)
        if status in (404, 410):
            return ListingDetail(url, gone=True, gone_reason=f"HTTP {status}")
        product = cls._detail_product(html)
        if urlparse(url).path.rstrip("/") != "/" + str(product.get("linkText")) + "/p":
            raise RuntimeError("gruporandazzo: detail belongs to another vehicle")
        reference = str(product.get("productReference") or "").lower()
        if not reference or not str(product.get("linkText") or "").startswith(reference):
            raise RuntimeError("gruporandazzo: detail ID mismatch")
        item = cls._listing(product)
        if item is None:
            return ListingDetail(url, gone=True, gone_reason="vehicle unavailable or outside used stock")
        item.url = url
        return ListingDetail(url, listing=item)

    def slim_page(self, page: Page) -> str:
        if page.status in (404, 410):
            return slim_html(page.html)
        try:
            product = self._detail_product(page.html)
        except RuntimeError:
            return slim_html(page.html)
        return '<script type="application/json" id="eseauto-randazzo-product">' + json.dumps(product, ensure_ascii=False).replace("<", "\\u003c") + "</script>"

"""Car One's anonymous catalog GraphQL and detail data in Next.js Flight."""
from __future__ import annotations

import asyncio
import json
import math
import re
from urllib.parse import urlparse

import httpx

from ._http import HEADERS, Page, dedupe, multiline_text, slim_html, soup
from ._regional import PublicCatalogScraper, matches_vehicle
from .base import CollectorBlocked, Listing, ListingDetail


class CarOneScraper(PublicCatalogScraper):
    name = "carone"
    STRICT_DETAIL_ID = True
    BASE = "https://carone.com.ar"
    PAGE_SIZE = 50
    MAX_PAGES = 100
    PAGE_DELAY = .2
    # Fields and endpoint are published by the site's GetProductsCard query.
    QUERY = """query GetProductsCard($q:String!,$pageSize:Int!,$currentPage:Int!,
        $filter:ProductAttributeFilterInput,$sort:ProductAttributeSortInput) {
      products(search:$q,pageSize:$pageSize,currentPage:$currentPage,filter:$filter,sort:$sort) {
        total_count items { id sku name url_key stock_status
          carone_marca_data {label} carone_modelo_data {label}
          carone_version_description carone_year carone_mileage carone_dealer_id
          carone_transmission_data {label} carone_fuel_data {label} description {html}
          carone_tags_data {tag_id title}
          price_range {maximum_price {final_price {currency value}}}
          carone_spyne_images {url} carone_type_data {label}
        }
      }
    }"""

    @staticmethod
    def _flight(html: str) -> str:
        parts = []
        for script in soup(html).select("script"):
            match = re.search(r"self\.__next_f\.push\((\[.*\])\)", script.string or "", re.S)
            if match:
                try:
                    payload = json.loads(match[1])
                except ValueError as e:
                    raise RuntimeError("carone: malformed Flight stream") from e
                if len(payload) > 1 and payload[0] == 1 and isinstance(payload[1], str):
                    parts.append(payload[1])
        return "".join(parts)

    @staticmethod
    def _objects(stream: str, key: str) -> list[dict]:
        result = []
        for match in re.finditer(r'"' + re.escape(key) + r'"\s*:\s*(?=\{)', stream):
            try:
                data, _ = json.JSONDecoder().raw_decode(stream[match.end():])
                result.append(data)
            except ValueError as e:
                raise RuntimeError(f"carone: malformed {key} data") from e
        return result

    @staticmethod
    def _label(record: dict, field: str) -> str | None:
        value = record.get(field) or {}
        return value.get("label") if isinstance(value, dict) else None

    @classmethod
    def _listing(cls, record: dict) -> Listing | None:
        tags = record.get("carone_tags_data") or []
        stock = record.get("stock_status")
        if stock not in ("IN_STOCK", "OUT_OF_STOCK"):
            raise RuntimeError("carone: vehicle stock state missing or unknown")
        if stock == "OUT_OF_STOCK":
            return None
        if not isinstance(tags, list) or not tags:
            raise RuntimeError("carone: vehicle condition missing")
        # Tag 2 is the explicitly published "Usados garantizados" option.
        # Mixed catalogs also contain 0km, savings plans and highlight tags.
        titles = " ".join(str(t.get("title") or "") for t in tags).lower()
        if not any(str(t.get("tag_id")) == "2" for t in tags):
            if any(str(t.get("tag_id")) in ("5", "8") for t in tags) or any(
                    word in titles for word in ("0km", "0 km", "plan de ahorro")):
                return None
            raise RuntimeError("carone: vehicle condition unknown")
        if any(word in titles for word in ("0km", "0 km", "plan de ahorro")):
            return None
        if record.get("carone_mileage") == 0:
            return None
        if (cls._label(record, "carone_type_data") or "").lower() in ("moto", "motocicleta"):
            return None
        if not record.get("id") or not record.get("url_key") or not record.get("name"):
            raise RuntimeError("carone: incomplete product identity")
        slug = str(record["url_key"])
        if not re.fullmatch(r"[a-z0-9-]+", slug):
            raise RuntimeError("carone: invalid vehicle slug")
        final = ((record.get("price_range") or {}).get("maximum_price") or {}).get("final_price") or {}
        amount = final.get("value")
        currency = final.get("currency")
        amount = float(amount) if isinstance(amount, (int, float)) and math.isfinite(amount) and amount > 1 else None
        currency = currency if currency in ("ARS", "USD") else None
        if currency is None:
            amount = None
        attrs = {k: v for k, v in {
            "Marca": cls._label(record, "carone_marca_data"),
            "Modelo": cls._label(record, "carone_modelo_data"),
            "Año": str(record["carone_year"]) if record.get("carone_year") else None,
            "Kilómetros": str(record["carone_mileage"]) if record.get("carone_mileage") is not None else None,
            "Sucursal": record.get("carone_dealer_id"),
            "Combustible": cls._label(record, "carone_fuel_data"),
            "Transmisión": cls._label(record, "carone_transmission_data"),
        }.items() if v}
        desc = record.get("description") or {}
        item = Listing(source=cls.name, listing_id=str(record["id"]), titulo=record["name"],
            url=f"{cls.BASE}/comprar/usados/{slug}", precio=amount, moneda=currency,
            marca=attrs.get("Marca"), modelo=attrs.get("Modelo"),
            version=record.get("carone_version_description") or None,
            anio=record.get("carone_year"), km=record.get("carone_mileage"),
            ubicacion=attrs.get("Sucursal"), combustible=attrs.get("Combustible"),
            transmision=attrs.get("Transmisión"), vendedor="agencia", vendedor_nombre="Car One",
            atributos=attrs, descripcion=multiline_text(soup(desc.get("html") or "")),
            imagenes=dedupe([image.get("url") for image in record.get("carone_spyne_images") or []]))
        return cls.annotate_partial_price(item)

    @classmethod
    def parse_search(cls, html: str) -> list[Listing]:
        data = cls._objects(cls._flight(html), "products")
        catalog = next((d for d in data if "total_count" in d and isinstance(d.get("items"), list)), None)
        if catalog is None:
            raise RuntimeError("carone: catalog data missing")
        if catalog.get("total_count") and not catalog["items"]:
            raise RuntimeError("carone: vehicle cards missing")
        return [item for record in catalog["items"] if (item := cls._listing(record))]

    async def _catalog_page(self, page_number: int) -> dict:
        variables = {"q": "", "pageSize": self.PAGE_SIZE, "currentPage": page_number,
                     "sort": {"created_at": "DESC"}, "filter": {"stock_status": {"eq": "IN_STOCK"}}}
        async with httpx.AsyncClient(headers=HEADERS, timeout=45, follow_redirects=False,
                                     transport=self.transport) as client:
            response = await client.post(self.BASE + "/api/graphql",
                                         json={"query": self.QUERY, "variables": variables})
        if response.is_redirect or urlparse(str(response.url)).hostname != urlparse(self.BASE).hostname:
            raise CollectorBlocked("carone: unexpected GraphQL redirect")
        self.check_status(response.status_code)
        if response.status_code != 200:
            raise RuntimeError(f"carone: catalog HTTP {response.status_code}")
        try:
            result = response.json()
        except ValueError as e:
            raise RuntimeError("carone: invalid GraphQL response") from e
        if not isinstance(result, dict):
            raise RuntimeError("carone: invalid GraphQL response shape")
        if result.get("errors"):
            raise RuntimeError("carone: GraphQL returned errors")
        catalog = (result.get("data") or {}).get("products")
        if not isinstance(catalog, dict) or not isinstance(catalog.get("items"), list) or not isinstance(catalog.get("total_count"), int):
            raise RuntimeError("carone: catalog data missing")
        return catalog

    async def search(self, filters: dict) -> list[Listing]:
        result, seen, expected = {}, set(), None
        vehicle_urls = {}
        for page_number in range(1, self.MAX_PAGES + 1):
            if page_number > 1:
                await asyncio.sleep(self.PAGE_DELAY)
            catalog = await self._catalog_page(page_number)
            total = catalog["total_count"]
            if expected is None:
                expected = total
            if total != expected or total < 0:
                raise RuntimeError("carone: inventory changed during pagination")
            records = catalog["items"]
            ids = [str(r.get("id")) for r in records]
            if any(i in ("None", "") for i in ids) or len(set(ids)) != len(ids):
                raise RuntimeError("carone: incomplete product identity")
            if seen.intersection(ids):
                raise RuntimeError("carone: repeated vehicle during pagination")
            seen.update(ids)
            for record in records:
                if item := self._listing(record):
                    if item.url in vehicle_urls and vehicle_urls[item.url] != item.listing_id:
                        raise RuntimeError("carone: vehicle URL shared by different IDs")
                    vehicle_urls[item.url] = item.listing_id
                    result[item.listing_id] = item
            if len(seen) == expected:
                return [item for item in result.values() if matches_vehicle(item, filters)]
            if len(records) != self.PAGE_SIZE or len(seen) > expected:
                raise RuntimeError("carone: incomplete pagination")
        raise RuntimeError("carone: pagination limit reached")

    @classmethod
    def _detail_record(cls, html: str) -> dict:
        doc = soup(html)
        kept = doc.select_one("script#eseauto-carone-product")
        if kept:
            try:
                return json.loads(kept.string or "")
            except ValueError as e:
                raise RuntimeError("carone: malformed stored product") from e
        records = cls._objects(cls._flight(html), "product")
        if len(records) != 1:
            raise RuntimeError("carone: own vehicle data missing or ambiguous")
        return records[0]

    @classmethod
    def parse_detail(cls, html: str, url: str, status: int = 200) -> ListingDetail:
        cls.check_status(status)
        if status in (404, 410):
            return ListingDetail(url, gone=True, gone_reason=f"HTTP {status}")
        record = cls._detail_record(html)
        if urlparse(url).path.rstrip("/") != "/comprar/usados/" + str(record.get("url_key") or ""):
            raise RuntimeError("carone: detail belongs to another vehicle")
        item = cls._listing(record)
        if item is None:
            return ListingDetail(url, gone=True, gone_reason="vehicle unavailable or outside used stock")
        item.url = url
        return ListingDetail(url, listing=item)

    def slim_page(self, page: Page) -> str:
        if page.status in (404, 410):
            return slim_html(page.html)
        try:
            record = self._detail_record(page.html)
        except RuntimeError:
            return slim_html(page.html)
        # Save just the public vehicle fields read by _listing, never the app's
        # Apollo auth, footer or unrelated recommendation state.
        allowed = {"id", "sku", "name", "url_key", "stock_status", "description", "price_range",
                   "carone_marca_data", "carone_modelo_data", "carone_version_description",
                   "carone_year", "carone_mileage", "carone_dealer_id", "carone_tags_data",
                   "carone_transmission_data", "carone_fuel_data", "carone_spyne_images", "carone_type_data"}
        data = {k: v for k, v in record.items() if k in allowed}
        return '<script type="application/json" id="eseauto-carone-product">' + json.dumps(data, ensure_ascii=False).replace("<", "\\u003c") + "</script>"

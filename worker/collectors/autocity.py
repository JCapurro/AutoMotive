"""Autocity's public WooCommerce stock. Official post shortlinks retain identity."""
from __future__ import annotations

import asyncio
import re
from urllib.parse import parse_qs, urljoin, urlparse

from ._http import Page, dedupe, multiline_text, slim_html, soup, text_of, to_int
from ._regional import PublicCatalogScraper, matches_vehicle, price
from .base import Listing, ListingDetail


class AutocityScraper(PublicCatalogScraper):
    name = "autocity"
    STRICT_DETAIL_ID = True
    BASE = "https://autocity.com.ar"
    CATALOG = BASE + "/catalogo/usados/"
    MAX_PAGES = 100
    PAGE_DELAY = .2

    @classmethod
    def _catalog(cls, html: str) -> tuple[list[Listing], set[str], int, str | None]:
        doc = soup(html)
        count = text_of(doc.select_one(".woocommerce-result-count"))
        match = re.search(r"(\d+)\s+resultados?", count or "", re.I)
        if not match:
            raise RuntimeError("autocity: catalog result count missing")
        total = int(match[1])
        # Menus express taxonomy labels and their hierarchy, rather than guesses
        # from a vehicle's unstructured title.
        labels = {e.get("data-slug"): text_of(e) for e in doc.select("[data-slug][data-type]")}
        cars, ids = {}, set()
        urls = {}
        cards = doc.select("ul.products > li.product")
        if total and not cards:
            raise RuntimeError("autocity: vehicle cards missing")
        for card in cards:
            classes = card.get("class", [])
            id_match = next((re.fullmatch(r"post-(\d+)", c) for c in classes
                             if re.fullmatch(r"post-(\d+)", c)), None)
            anchor = card.select_one("a[href][data-id]")
            title = text_of(card.select_one(".carousel-autocity-card-title h3"))
            if not id_match or not anchor or not title:
                raise RuntimeError("autocity: incomplete vehicle card")
            post_id = id_match[1]
            if post_id in ids:
                raise RuntimeError("autocity: repeated vehicle card")
            ids.add(post_id)
            canonical = urljoin(cls.BASE, anchor["href"])
            if urlparse(canonical).hostname != urlparse(cls.BASE).hostname:
                raise RuntimeError("autocity: vehicle link outside source")
            if canonical in urls and urls[canonical] != post_id:
                raise RuntimeError("autocity: vehicle URL shared by different IDs")
            urls[canonical] = post_id
            if "product_cat-usados" not in classes or "outofstock" in classes:
                continue
            description = card.select_one(".carousel-autocity-card-description")
            state = text_of(card.select_one(".carousel-autocity-card-condiciones")) or ""
            specs = text_of(description) or ""
            if re.search(r"\b(vendido|reservado|a ingresar|plan de ahorro|moto)\b", state + " " + specs, re.I):
                continue
            if re.search(r"\b0\s*km\b", specs, re.I):
                continue
            year_km = re.search(r"\b((?:19|20)\d{2})\s*\|\s*([\d.,]+)\s*km\b", specs, re.I)
            categories = {c.removeprefix("product_cat-") for c in classes if c.startswith("product_cat-")}
            make_slug = next((c for c in categories if c in labels and
                              doc.select_one(f'[data-slug="{c}"][data-type="marcas"]') and c.startswith("m-")), None)
            make = labels.get(make_slug)
            model_label = next((labels.get(f"{make_slug}/{c}") for c in categories
                                if labels.get(f"{make_slug}/{c}")), None)
            model = model_label.removeprefix(make + " ") if model_label and make else None
            location = next((labels[c] for c in categories if c in
                             ("cordoba", "rio-cuarto", "san-luis", "villa-maria") and labels.get(c)), None)
            amount, currency = price(text_of(card.select_one(".carousel-autocity-card-precio h2")))
            image = card.select_one(".carousel-autocity-card-image img")
            photo = (image.get("data-src") or image.get("src")) if image else None
            if photo and any(word in photo for word in ("default.jpg", "loading.png", "data:image")):
                photo = None
            version = text_of(description.select_one("p")) if description else None
            fuel = re.search(r"Combustible\s+(.+?)(?=\s+Transmisi[oó]n|$)", specs, re.I)
            gearbox = re.search(r"Transmisi[oó]n\s+(.+)$", specs, re.I)
            item = Listing(source=cls.name, listing_id=post_id,
                titulo=" ".join(v for v in (title, version) if v),
                # WordPress publishes this same stable shortlink on the detail.
                url=f"{cls.BASE}/?p={post_id}", precio=amount, moneda=currency,
                marca=make, modelo=model, version=version,
                anio=int(year_km[1]) if year_km else None,
                km=to_int(year_km[2]) if year_km else None, ubicacion=location,
                combustible=fuel[1] if fuel else None, transmision=gearbox[1] if gearbox else None,
                vendedor="agencia", vendedor_nombre="Autocity",
                imagenes=[urljoin(cls.BASE, photo)] if photo else [],
                extra={"canonical_url": canonical})
            cars[post_id] = cls.annotate_partial_price(item)
        next_link = doc.select_one(".customNavigation a.backtoNext:not(.disabled)[href]")
        following = urljoin(cls.BASE, next_link["href"]) if next_link and next_link["href"] != "#" else None
        if following and not following.startswith(cls.CATALOG + "page/"):
            raise RuntimeError("autocity: unexpected pagination URL")
        return list(cars.values()), ids, total, following

    @classmethod
    def parse_search(cls, html: str) -> list[Listing]:
        return cls._catalog(html)[0]

    async def search(self, filters: dict) -> list[Listing]:
        url, seen_urls, seen_ids, result, expected = self.CATALOG, set(), set(), {}, None
        vehicle_urls = {}
        for page_number in range(self.MAX_PAGES):
            if url in seen_urls:
                raise RuntimeError("autocity: repeated pagination URL")
            seen_urls.add(url)
            if page_number:
                await asyncio.sleep(self.PAGE_DELAY)
            page = await self._get(url)
            if page.status != 200:
                raise RuntimeError(f"autocity: catalog HTTP {page.status}")
            items, ids, total, following = self._catalog(page.html)
            if expected is None:
                expected = total
            if total != expected:
                raise RuntimeError("autocity: inventory changed during pagination")
            if ids and ids & seen_ids:
                raise RuntimeError("autocity: repeated vehicle during pagination")
            seen_ids.update(ids)
            for item in items:
                canonical = item.extra["canonical_url"]
                if canonical in vehicle_urls and vehicle_urls[canonical] != item.listing_id:
                    raise RuntimeError("autocity: vehicle URL shared by different IDs")
                vehicle_urls[canonical] = item.listing_id
                result[item.listing_id] = item
            if not following:
                if len(seen_ids) != expected:
                    raise RuntimeError("autocity: incomplete pagination")
                return [item for item in result.values() if matches_vehicle(item, filters)]
            url = following
        raise RuntimeError("autocity: pagination limit reached")

    async def fetch_detail_page(self, url: str) -> Page:
        requested_id = parse_qs(urlparse(url).query).get("p", [None])[0]
        if requested_id and not re.fullmatch(r"\d+", requested_id):
            raise ValueError("autocity: invalid requested vehicle ID")
        page = await self._get(url)
        if requested_id:
            # raw_pages saves the final URL after the redirect. Carry the
            # requested post ID into replay as well, so a changed redirect
            # cannot transplant another vehicle onto the original listing.
            page.html = (f'<meta name="eseauto-autocity-requested-id" content="{requested_id}">' + page.html)
        return page

    @classmethod
    def parse_detail(cls, html: str, url: str, status: int = 200) -> ListingDetail:
        cls.check_status(status)
        if status in (404, 410):
            return ListingDetail(url, gone=True, gone_reason=f"HTTP {status}")
        doc = soup(html)
        main = doc.select_one("main.ficha-producto-page[data-brand][data-model]")
        title = text_of(main.select_one(".ac-product-title")) if main else None
        body_id = next((m[1] for c in doc.body.get("class", [])
                        if (m := re.fullmatch(r"postid-(\d+)", c))), None) if doc.body else None
        canonical = doc.select_one("link[rel='canonical'][href]")
        if not main or not title or not body_id or not canonical:
            raise RuntimeError("autocity: vehicle detail markup missing")
        requested_ids = {e.get("content") for e in doc.select('meta[name="eseauto-autocity-requested-id"]')}
        if from_url := parse_qs(urlparse(url).query).get("p", [None])[0]:
            requested_ids.add(from_url)
        if len(requested_ids) > 1:
            raise RuntimeError("autocity: conflicting requested vehicle IDs")
        requested_id = next(iter(requested_ids), None)
        if requested_id:
            if requested_id != body_id:
                raise RuntimeError("autocity: detail ID mismatch")
        elif urlparse(url).path.rstrip("/") != urlparse(canonical["href"]).path.rstrip("/"):
            raise RuntimeError("autocity: detail belongs to another vehicle")
        state = main.get("data-estado", "").strip().lower()
        if state != "usado":
            if state not in ("nuevo", "0km", "0 km", "vendido", "reservado", "a ingresar"):
                raise RuntimeError("autocity: vehicle condition missing or unknown")
            return ListingDetail(url, gone=True, gone_reason=f"estado: {state}")
        if to_int(main.get("data-kms")) == 0:
            return ListingDetail(url, gone=True, gone_reason="0 km: outside used stock")
        availability = text_of(main.select_one(".ac-product-status")) or ""
        if re.search(r"\b(vendido|reservado|a ingresar)\b", availability, re.I):
            return ListingDetail(url, gone=True, gone_reason=availability)
        attrs = {text_of(e.select_one(".feature-title")) or "":
                 text_of(e.select_one(".feature-detail")) or "" for e in main.select(".feature-item")}
        summary = text_of(main.select_one(".ac-product-short-desc.firstOne")) or ""
        fuel = next((v.strip() for v in summary.split("|") if re.fullmatch(
                    r"(?i)(nafta|diesel|diésel|gnc|h[ií]brido|el[eé]ctrico)", v.strip())), None)
        amount, currency = price(main.get("data-price"))
        make, model = main.get("data-brand"), main.get("data-model")
        prefix = f"{make} {model} "
        version = title[len(prefix):] if title.startswith(prefix) else None
        item = Listing(source=cls.name, listing_id=body_id, titulo=title, url=url,
            precio=amount, moneda=currency, marca=make, modelo=model, version=version,
            anio=to_int(main.get("data-ano")), km=to_int(main.get("data-kms")),
            ubicacion=main.get("data-sucursal") or None,
            combustible=fuel, transmision=attrs.get("Tipo de transmisión") or None,
            vendedor="agencia", vendedor_nombre="Autocity", atributos=attrs,
            descripcion=multiline_text(main.select_one(".ac-product-heading")),
            imagenes=dedupe([urljoin(cls.BASE, a["href"]) for a in
                            main.select("#ac-product-gallery-wrapper a.e-gallery-item[href]")]))
        return ListingDetail(url, listing=cls.annotate_partial_price(item))

    def slim_page(self, page: Page) -> str:
        doc = soup(page.html)
        # Technical vehicle data are DOM attributes; the large #datos script
        # contains a general brand/model database and is not needed.
        for el in doc.select("header, footer, form, .related, .modal, script"):
            el.decompose()
        return slim_html(str(doc))

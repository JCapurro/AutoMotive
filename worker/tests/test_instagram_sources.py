"""Offline parsing and transport contracts; no accounts or database required.

instagram_sc_detail.html is a scrubbed anonymous public capture. Small mutated
payloads below use its web JSON shapes to exercise identity and failure cases.
"""
from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from collectors import instagram
from collectors._http import Page, soup
from collectors.base import CollectorBlocked
from collectors.instagram import OnlyCarsUsadosScraper as OnlyCars, SCClasificadosScraper as SC


FIXTURES = Path(__file__).parent / "fixtures" / "html"
ONLY_URL = "https://www.instagram.com/onlycarsusados/p/DeISPZ4jh7c/"
SC_URL = "https://www.instagram.com/sc_clasificados/p/Ddtw2eVlgWL/"
ONLY_CAPTION = (
    "Modelo: Peugeot 208 active tiptronic 1.6L\nAño: 2021\nKilómetros: 31.300\n"
    "Transmisión: Automática\nCombustible: Nafta\n\nTodos los papeles al día.\n"
    "Precio: 13200 USD\nUbicación: Monserrat, CABA\nContacto: @haase_motovlog\n"
    "¡VENDEMOS SU VEHÍCULO! Contáctenos por mensaje privado a @onlycarsusados"
)


def web_media(caption=ONLY_CAPTION, *, code="DeISPZ4jh7c", owner="onlycarsusados", **extra):
    return {"__typename": "XIGPolarisCarouselMedia", "code": code,
            "user": {"username": owner}, "caption": {"text": caption},
            "taken_at": 1791220000, "display_uri": "https://scontent.cdninstagram.com/car.jpg", **extra}


def html_media(*media, script_type="application/json"):
    return f'<script type="{script_type}">' + json.dumps({"data": {"items": list(media)}}) + "</script>"


def test_real_sc_public_capture_complete_caption_carousel_and_labels():
    html = (FIXTURES / "instagram_sc_detail.html").read_text(encoding="utf-8")
    detail = SC.parse_detail(html, SC_URL)
    listing = detail.listing
    assert not detail.gone
    assert (listing.titulo, listing.anio, listing.km) == ("Toyota RAV4", 2010, 210000)
    assert (listing.precio, listing.moneda, listing.ubicacion) == (11800, "USD", "Villa María, Córdoba")
    assert listing.transmision == "automatic"
    assert listing.combustible == "nafta"
    assert listing.marca is None and listing.modelo is None
    assert listing.vendedor_nombre is None  # The publishing account is not the car owner.
    assert len(listing.imagenes) == 20
    assert all("thumb" not in url for url in listing.imagenes)
    assert listing.published_at == 1790349469
    assert "alfombras Vapren" in listing.descripcion
    assert listing.descripcion.endswith("@sc_clasificados")
    assert "Comments are outside" not in listing.descripcion
    slim = SC().slim_page(Page(200, SC_URL, html))
    assert SC.parse_detail(slim, SC_URL).listing.to_dict() == listing.to_dict()


def test_onlycars_currency_after_amount_and_explicit_contact():
    listing = OnlyCars.parse_detail(html_media(web_media()), ONLY_URL).listing
    assert (listing.source, listing.listing_id) == ("onlycarsusados", "DeISPZ4jh7c")
    assert (listing.precio, listing.moneda, listing.anio, listing.km) == (13200, "USD", 2021, 31300)
    assert (listing.transmision, listing.combustible) == ("automatic", "nafta")
    assert listing.ubicacion == "Monserrat, CABA"
    assert listing.vendedor_nombre == "@haase_motovlog"
    assert listing.descripcion == ONLY_CAPTION
    assert listing.marca is None and listing.modelo is None


def test_real_onlycars_capture_complete_caption_and_carousel_slim_reparse():
    html = (FIXTURES / "instagram_onlycars_detail.html").read_text(encoding="utf-8")
    listing = OnlyCars.parse_detail(html, ONLY_URL).listing
    assert (listing.precio, listing.moneda, listing.anio, listing.km) == (13200, "USD", 2021, 31300)
    assert listing.vendedor_nombre == "@haase_motovlog" and listing.ubicacion == "Monserrat, CABA"
    assert len(listing.imagenes) == 11
    assert "Un auto moderno, cómodo y muy bien equipado" in listing.descripcion
    assert listing.descripcion.endswith("@onlycarsusados")
    slim = OnlyCars().slim_page(Page(200, ONLY_URL, html))
    assert OnlyCars.parse_detail(slim, ONLY_URL).listing.to_dict() == listing.to_dict()


def test_actual_dom_caption_can_be_read_under_login_modal_without_json():
    doc = soup((FIXTURES / "instagram_sc_detail.html").read_text(encoding="utf-8"))
    for script in doc.select("script"):
        script.decompose()
    doc.body.append(soup('<div role="dialog">Regístrate en Instagram para estar siempre al día.</div>').div)
    listing = SC.parse_detail(str(doc), SC_URL).listing
    assert listing.km == 210000
    assert listing.precio == 11800
    assert listing.descripcion.endswith("@sc_clasificados")
    assert listing.published_at is not None


def test_legacy_json_media_owner_caption_and_sidecar_slim_reparse():
    media = {"shortcode": "DeISPZ4jh7c", "owner": {"username": "onlycarsusados"},
             "edge_media_to_caption": {"edges": [{"node": {"text": ONLY_CAPTION}}]},
             "edge_sidecar_to_children": {"edges": [
                 {"node": {"display_url": "https://scontent.cdninstagram.com/car-a.jpg"}},
                 {"node": {"display_url": "https://scontent.cdninstagram.com/car-b.jpg"}}]},
             "taken_at_timestamp": 1791220000}
    html = '<script>window._sharedData = ' + json.dumps({"graphql": {"shortcode_media": media}}) + ";</script>"
    listing = OnlyCars.parse_detail(html, ONLY_URL).listing
    assert len(listing.imagenes) == 2
    slim = OnlyCars().slim_page(Page(200, ONLY_URL, html))
    assert OnlyCars.parse_detail(slim, ONLY_URL).listing.to_dict() == listing.to_dict()


def test_json_ld_identity_caption_and_structured_vehicle_fields():
    social = {"@type": "SocialMediaPosting", "url": ONLY_URL,
              "author": {"@type": "Person", "url": "https://www.instagram.com/onlycarsusados/"},
              "articleBody": ONLY_CAPTION, "datePublished": "2026-10-05T12:00:00Z",
              "image": ["https://scontent.cdninstagram.com/car.jpg"],
              "about": {"@type": "Car", "brand": {"name": "Peugeot"}, "model": "208"}}
    listing = OnlyCars.parse_detail(html_media(social, script_type="application/ld+json"), ONLY_URL).listing
    assert (listing.marca, listing.modelo) == ("Peugeot", "208")
    assert listing.descripcion == ONLY_CAPTION
    assert listing.published_at is not None


@pytest.mark.parametrize("caption", ["VENDIDO ✅ " + ONLY_CAPTION, ONLY_CAPTION + "\nEstado: vendido", "VENDIDA\nToyota Rav4"])
def test_explicit_sold_caption_is_gone(caption):
    result = OnlyCars.parse_detail(html_media(web_media(caption)), ONLY_URL)
    assert result.gone and result.gone_reason == "vendido" and result.listing is None


@pytest.mark.parametrize("line", ["Si se vende, se entrega transferido", "No vendido", "No está vendido", "Aún no se vendió"])
def test_negotiation_or_negation_does_not_mean_sold(line):
    result = OnlyCars.parse_detail(html_media(web_media(ONLY_CAPTION + "\n" + line)), ONLY_URL)
    assert not result.gone and result.listing is not None


def test_other_media_comments_and_recommendations_are_not_caption():
    target = web_media()
    target["comments_connection"] = {"edges": [{"node": {"text": "Toyota Corolla 2022 10 km USD 3.000"}}]}
    other = web_media("Toyota Corolla\nAño: 2022\nKilómetros: 10\nUSD 3000", code="OtherPost")
    listing = OnlyCars.parse_detail(html_media(other, target), ONLY_URL).listing
    assert listing.descripcion == ONLY_CAPTION and listing.precio == 13200


@pytest.mark.parametrize("media", [web_media(owner="another_account"), web_media(code="AnotherShortcode")])
def test_wrong_owner_or_shortcode_fails_without_removal(media):
    with pytest.raises(RuntimeError):
        OnlyCars.parse_detail(html_media(media), ONLY_URL)


def test_recommendation_of_requested_post_on_another_page_is_rejected():
    html = '<link rel="canonical" href="https://www.instagram.com/p/AnotherPost/">' + html_media(web_media())
    with pytest.raises(RuntimeError):
        OnlyCars.parse_detail(html, ONLY_URL)


@pytest.mark.parametrize("path", ["/accounts/login/", "/challenge/", "/checkpoint/"])
def test_redirected_login_and_challenge_urls_are_blocked(path):
    with pytest.raises(CollectorBlocked):
        OnlyCars.parse_detail("<html></html>", "https://www.instagram.com" + path)


@pytest.mark.parametrize("html", [
    '<script type="application/json">{"data": broken}</script>',
    '<meta property="og:description" content="Peugeot 208 2021 USD 13200 truncated...">',
    "<main>Sorry, this page isn't available.</main>",
    "<main>Unknown page markup</main>",
])
def test_malformed_missing_or_unknown_content_is_error(html):
    with pytest.raises(RuntimeError):
        OnlyCars.parse_detail(html, ONLY_URL)


@pytest.mark.parametrize("status", [401, 403, 429])
def test_blocked_http_is_never_empty_or_gone(status):
    with pytest.raises(CollectorBlocked):
        OnlyCars.parse_detail("", ONLY_URL, status)


@pytest.mark.parametrize("status", [404, 410])
def test_missing_http_proves_gone(status):
    assert OnlyCars.parse_detail("", ONLY_URL, status).gone_reason == str(status)


def test_login_wall_blocks_but_public_caption_under_modal_survives():
    wall = '<main><form action="/accounts/login/"><input name="password"></form></main>'
    with pytest.raises(CollectorBlocked):
        OnlyCars.parse_detail(wall, ONLY_URL)
    assert OnlyCars.parse_detail(wall + html_media(web_media()), ONLY_URL).listing.precio == 13200


@pytest.mark.parametrize("caption", ["😂", "Toyota memes #humor", "Venta de cubiertas Peugeot USD 200", "Peugeot 208 sin datos", "Peugeot 208 2021 USD 13200 #meme"])
def test_non_vehicle_posts_are_skipped_without_marking_gone(caption):
    result = OnlyCars.parse_detail(html_media(web_media(caption)), ONLY_URL)
    assert not result.gone and result.listing is None


def test_title_year_and_mileage_allow_an_ad_without_price_and_location_is_explicit():
    result = OnlyCars.parse_detail(html_media(web_media("Toyota RAV4 2010\n210 mil km\nEn Buenos Aires")), ONLY_URL)
    assert result.listing is not None and result.listing.precio is None
    assert result.listing.ubicacion is None and result.listing.vendedor_nombre is None


class FakePage:
    def __init__(self, pages):
        self.pages = pages
        self.url = ""
        self.scrolls = 0
        self.closed = False

    async def goto(self, url, **kwargs):
        self.url = url
        status, _ = self.pages[url]
        if isinstance(status, Exception):
            raise status
        return SimpleNamespace(status=status)

    async def wait_for_timeout(self, timeout):
        pass

    async def content(self):
        return self.pages[self.url][1]

    async def evaluate(self, script):
        self.scrolls += 1

    async def close(self):
        self.closed = True


def fake_context(pages):
    created = []

    class Context:
        async def new_page(self):
            page = FakePage(pages)
            created.append(page)
            return page

    @asynccontextmanager
    async def context(**kwargs):
        assert kwargs["storage_state"] is None
        yield Context()

    return context, created


def test_search_deduplicates_generic_and_profile_post_links_and_bounds_scroll():
    profile = ('<main><a href="/p/DeISPZ4jh7c/">Car</a><a href="/onlycarsusados/p/DeISPZ4jh7c/?x=1">Duplicate</a>'
               '<a href="/someone_else/p/Other/">Recommendation</a></main>')
    pages = {"https://www.instagram.com/onlycarsusados/": (200, profile), ONLY_URL: (200, html_media(web_media()))}
    context, created = fake_context(pages)
    with patch.object(instagram, "browser_context", context):
        result = asyncio.run(OnlyCars(storage_state="", max_posts=6).search({"marca": "Peugeot", "modelo": "208"}))
    assert len(result) == 1
    assert created[0].scrolls == 2
    assert len(created) == 2 and all(page.closed for page in created)
    assert result[0].extra["discovery_scope"] == "recent_profile_feed"


@pytest.mark.parametrize("status,html,error", [
    (403, "", CollectorBlocked), (200, "<main>Unexpected profile</main>", RuntimeError),
    (200, '<main><form action="/accounts/login/"></form></main>', CollectorBlocked),
    (503, "", RuntimeError), (404, "", RuntimeError),
])
def test_search_failures_propagate_and_close_pages(status, html, error):
    context, created = fake_context({"https://www.instagram.com/onlycarsusados/": (status, html)})
    with patch.object(instagram, "browser_context", context), pytest.raises(error):
        asyncio.run(OnlyCars(storage_state="").search({}))
    assert all(page.closed for page in created)


def test_search_detail_network_failure_is_not_a_successful_empty_run():
    pages = {"https://www.instagram.com/onlycarsusados/": (200, '<main><a href="/p/DeISPZ4jh7c/">Car</a></main>'),
             ONLY_URL: (TimeoutError("network timed out"), "")}
    context, _ = fake_context(pages)
    with patch.object(instagram, "browser_context", context), pytest.raises(TimeoutError):
        asyncio.run(OnlyCars(storage_state="", max_posts=1).search({}))


def test_feed_cap_and_inventory_contract():
    assert OnlyCars(max_posts=10000).max_posts == 60
    assert OnlyCars(max_posts=0).max_posts == 1
    assert OnlyCars.INVENTORY_TARGET and SC.INVENTORY_TARGET
    assert OnlyCars.name == OnlyCars.account == "onlycarsusados"
    assert SC.name == SC.account == "sc_clasificados"


def test_sold_pins_do_not_consume_recent_discovery_budget():
    html = html_media(web_media("VENDIDO\n" + ONLY_CAPTION, code="PinnedSold"), web_media())
    html += '<main><a href="/p/PinnedSold/">Pinned</a><a href="/p/DeISPZ4jh7c/">Current</a></main>'
    assert OnlyCars.profile_post_urls(html) == [ONLY_URL]

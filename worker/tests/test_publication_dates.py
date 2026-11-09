"""Publication evidence, date precision and exclusion of unrelated dates."""
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from collectors._dates import parse_publication_date, publication_date
from collectors._http import Page, soup
from pipeline.ingest import merge
import test_parsers as fixtures
from test_body_type import _stored

DAY = 86_400
ART = timezone(timedelta(hours=-3))
NOW = int(datetime(2026, 10, 5, 12, tzinfo=timezone.utc).timestamp())      # 09:00 in Argentina
TODAY_ART = int(datetime(2026, 10, 5, tzinfo=ART).timestamp())
PUBLISHED = int(datetime(2026, 9, 27, 3, tzinfo=timezone.utc).timestamp())


@pytest.mark.parametrize("value", ["2026-09-27", "27/09/2026", "Publicado el 27-09-2026",
                                  "Fecha de publicación: 27 de septiembre de 2026",
                                  "2026-09-27T00:00:00-03:00", "2026-09-27T03:00:00Z"])
def test_explicit_dates_share_argentine_timezone(value):
    with patch("collectors._dates.time.time", return_value=NOW):
        assert parse_publication_date(value) == PUBLISHED


@pytest.mark.parametrize("value,seconds", [("Hace 2 horas", 2 * 3600), ("hace 1 hora", 3600),
                                         ("Hace 23 horas", 23 * 3600), ("Publicado hace 30 minutos", 1800)])
def test_minutes_and_hours_keep_their_precision(value, seconds):
    with patch("collectors._dates.time.time", return_value=NOW):
        assert parse_publication_date(value) == NOW - seconds


@pytest.mark.parametrize("value,expected", [
    ("Publicado hoy", NOW),
    # Mercado Libre's page of an ad «Publicados hoy» lists, under a day old.
    ("Publicado hace 1 día", NOW),
    ("hace 2 días", NOW - DAY),
    ("3 días", NOW - 2 * DAY),
    ("Ayer", TODAY_ART),
    ("Anteayer", TODAY_ART - DAY),
])
def test_day_level_phrases_give_the_latest_instant_they_allow(value, expected):
    """2026-11-08: "hace 1 día" read as now - 24 h dated every fresh Mercado
    Libre match a day back (23.9 h at p25-p75), and "hace 2 días" two."""
    with patch("collectors._dates.time.time", return_value=NOW):
        assert parse_publication_date(value) == expected


def test_yesterday_is_argentina_s_yesterday_not_the_hosts():
    late = int(datetime(2026, 10, 6, 1, 30, tzinfo=timezone.utc).timestamp())     # 22:30 on 5/10 in Argentina
    with patch("collectors._dates.time.time", return_value=late):
        assert parse_publication_date("ayer") == TODAY_ART
        assert parse_publication_date("hace 1 día") == late


def test_mercado_libre_ad_of_today_keeps_its_hour():
    page = fixtures.html("mercadolibre_detail.html").replace("Publicado hace 7 meses", "Publicado hace 1 día")
    url = "https://auto.mercadolibre.com.ar/MLA-1675249827-toyota-corolla-cross-18-hev-seg-ecvt-_JM"
    with patch("collectors._dates.time.time", return_value=NOW):
        assert fixtures.mercadolibre.parse_detail(page, url).listing.published_at == NOW


def test_a_publication_is_never_stored_after_first_detection():
    seen = datetime(2026, 10, 5, 8, tzinfo=timezone.utc)
    # Enrichment read "hace 1 día" (now) an hour after the crawl first saw the ad.
    values, _ = merge(_stored(first_seen_at=seen), _stored(published_at=seen + timedelta(hours=1)), detail=True)
    assert values["published_at"] == seen
    older = seen - timedelta(days=3)
    values, _ = merge(_stored(first_seen_at=seen), _stored(published_at=older), detail=True)
    assert values["published_at"] == older
    # Stored after its detection before this rule: pulled back on its next sighting.
    values, _ = merge(_stored(first_seen_at=seen, published_at=seen + timedelta(hours=5)), _stored(), detail=False)
    assert values["published_at"] == seen
    # The first date read still wins over a later reading.
    values, _ = merge(_stored(first_seen_at=seen, published_at=older), _stored(published_at=seen), detail=True)
    assert values["published_at"] == older


@pytest.mark.parametrize("value", [None, "", "31/02/2026", "2028-01-01", "modelo 2025",
                                  "2026", "precio válido hasta 27/09/2026", "garantía por 2 años"])
def test_invalid_or_unrelated_dates_remain_unknown(value):
    with patch("collectors._dates.time.time", return_value=NOW):
        assert parse_publication_date(value) is None


def test_json_ld_publication_wins_over_relative_label():
    with patch("collectors._dates.time.time", return_value=NOW):
        assert publication_date(soup("<h1>Auto</h1>"),
                                structured={"datePublished": "2026-09-27"}, text="hoy") == PUBLISHED
        assert publication_date(soup("<h1>Auto</h1>"),
                                structured={"dateModified": "2026-09-27", "vehicleModelDate": "2025",
                                            "offers": {"validFrom": "2026-09-27"}}) is None


def test_related_car_cannot_supply_missing_publication_date():
    doc = soup('<article itemscope itemtype="https://schema.org/Car"><h1>Auto</h1></article>'
               '<article itemscope itemtype="https://schema.org/Car">'
               '<meta itemprop="datePublished" content="2026-09-27"></article>')
    assert publication_date(doc) is None


def test_json_ld_only_ad_does_not_take_date_from_its_only_related_microdata_car():
    doc = soup('<h1>Auto principal</h1><article itemscope itemtype="https://schema.org/Car">'
               '<h3>Otro auto</h3><meta itemprop="datePublished" content="2026-09-27"></article>')
    assert publication_date(doc, structured={"@type": "Car", "name": "Auto principal"}) is None


@pytest.mark.parametrize("cls,name,url", fixtures.RawPageTests.CASES)
def test_every_detail_parser_reads_explicit_date_and_keeps_it_in_raw_page(cls, name, url):
    page = fixtures.html(name)
    metadata = '<meta itemprop="datePublished" content="2026-09-27">'
    if cls.name == "facebook":
        page = page.replace("Publicado hace 2 días", "Publicado el 27/09/2026")
    elif cls.name == "autocosmos":
        doc = soup(page)
        doc.select_one("article[itemscope][itemtype*='Car']").append(soup(metadata).meta)
        page = str(doc)
    else:
        page = metadata + page
    scraper = cls()
    with patch("collectors._dates.time.time", return_value=NOW):
        assert scraper.parse_detail(page, url).listing.published_at == PUBLISHED
        slim = scraper.slim_page(Page(200, url, page))
        assert scraper.parse_detail(slim, url).listing.published_at == PUBLISHED


@pytest.mark.parametrize("module,name,selector", [
    (fixtures.mercadolibre, "mercadolibre_search.html", "li.ui-search-layout__item"),
    (fixtures.v6, "v6_search.html", "a.tc-v2-link"),
    (fixtures.kavak, "kavak_search.html", "a[data-testid][href*='/ar/venta/']"),
    (fixtures.autocosmos.AutoCosmosScraper, "autocosmos_search.html", "article.listing-card"),
])
def test_search_cards_read_their_own_publication_date(module, name, selector):
    doc = soup(fixtures.html(name))
    doc.select_one(selector).append(soup('<meta itemprop="datePublished" content="2026-09-27">').meta)
    with patch("collectors._dates.time.time", return_value=NOW):
        assert module.parse_search(str(doc))[0].published_at == PUBLISHED


def test_facebook_card_reads_labeled_absolute_date():
    with patch("collectors._dates.time.time", return_value=NOW):
        card = fixtures.facebook.parse_card("/marketplace/item/123/",
                                             "$10.000.000\nFord Fiesta 2017\nPublicado el 27/09/2026")
        assert card.published_at == PUBLISHED


def _fb_item_page(listing_id: str, own: int | None, suggested: int = NOW - 86_400) -> str:
    import base64
    story = base64.b64encode(f"S:_I61584079436046:VK:{listing_id}".encode()).decode()
    other = base64.b64encode(b"S:_I1:VK:999").decode()
    own_data = (f'{{"id":"{story}","actors":[],"redacted_description":{{"text":"x"}},'
                f'"creation_time":{own},"location_text":{{"text":"Rosario, SF"}}}}') if own else ""
    return ('<html><body><div role="main"><h1>2012 Volkswagen Gol Trend</h1><span>$6,000,000</span>'
            '<span>Listed  in</span><span>Rosario, SF</span><span>Seller\'s description</span><span>Gol trend 2012</span>'
            '<span>Today\'s picks</span><span>$14,990,000</span><span>Listed 2 days ago in Acassuso</span></div>'
            f'<script>{{"id":"{other}","redacted_description":{{"text":"y"}},'
            f'"creation_time":{suggested},"location_text":{{"text":"Acassuso"}}}}{own_data}</script></body></html>')


def test_facebook_detail_takes_its_own_creation_time_when_the_text_has_no_age():
    from collectors import facebook as fb
    url = "https://www.facebook.com/marketplace/item/1076102611970723/"
    with patch("collectors.facebook.time.time", return_value=NOW):
        detail = fb.parse_detail(_fb_item_page("1076102611970723", NOW - 3_600), url)
        assert detail.listing.published_at == NOW - 3_600
        assert detail.listing.ubicacion == "Rosario, SF"
        # Only suggested ads carry a time: theirs is never borrowed.
        assert fb.parse_detail(_fb_item_page("1076102611970723", None), url).listing.published_at is None

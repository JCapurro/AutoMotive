"""Publication evidence, date precision and exclusion of unrelated dates."""
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from collectors._dates import parse_publication_date, publication_date
from collectors._http import Page, soup
import test_parsers as fixtures

NOW = int(datetime(2026, 10, 5, 12, tzinfo=timezone.utc).timestamp())
PUBLISHED = int(datetime(2026, 9, 27, 3, tzinfo=timezone.utc).timestamp())


@pytest.mark.parametrize("value", ["2026-09-27", "27/09/2026", "Publicado el 27-09-2026",
                                  "Fecha de publicación: 27 de septiembre de 2026",
                                  "2026-09-27T00:00:00-03:00", "2026-09-27T03:00:00Z"])
def test_explicit_dates_share_argentine_timezone(value):
    with patch("collectors._dates.time.time", return_value=NOW):
        assert parse_publication_date(value) == PUBLISHED


@pytest.mark.parametrize("value,seconds", [("Hace 2 horas", 7200), ("Publicado hace 30 minutos", 1800),
                                         ("3 días", 3 * 86400), ("Anteayer", 2 * 86400),
                                         ("Publicado hoy", 0)])
def test_relative_dates(value, seconds):
    with patch("collectors._dates.time.time", return_value=NOW):
        assert parse_publication_date(value) == NOW - seconds


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

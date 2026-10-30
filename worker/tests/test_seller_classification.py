"""F-02 paso 1 (docs/superpowers/specs/2026-10-30-f02-vendedor-design.md): the
seller key and the seller_classification config. No database."""
from __future__ import annotations

import pytest

from intelligence.config import DEFAULT_SELLER_CLASSIFICATION, seller_classification
from normalization.seller import STOPLIST, seller_key


# ---------------------------------------------------------------------------
# seller_key
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("a, b", [
    ("Juan Pérez", "  juan perez "),
    ("JUAN  PÉREZ", "juan perez"),
    ("Autos S.A.", "Autos SA"),
    ("Autos S.A.", "autos s.a"),
    ("Autos S. A.", "Autos S.A."),
    ("Autos S. A.", "Autos SA"),
    ("Motors S. R. L.", "Motors S.R.L."),
    ("Motors S R L", "Motors SRL"),
    ("D'Angelo Autos", "Dangelo autos"),
    ("Peña-Motors", "pena motors"),
    ("🚗 Juan Pérez 🚗", "juan perez"),
    ("Juan Pérez!!!", "juan, perez"),
])
def test_same_seller_same_key(a, b):
    assert seller_key(a) == seller_key(b) is not None


def test_key_keeps_only_letters_digits_and_spaces():
    assert seller_key("Autos S.A.") == "autos sa"
    assert seller_key("Autos S. A.") == "autos sa"
    assert seller_key("Motors S. R. L.") == "motors srl"
    assert seller_key("🚗 Juan Pérez 🚗") == "juan perez"
    assert seller_key("Usados & Cía. (Rosario)") == "usados cia rosario"


def test_different_sellers_different_keys():
    assert seller_key("Juan Pérez") != seller_key("Juana Pérez")


@pytest.mark.parametrize("phone", [
    "+54 9 341 555-1234",
    "341 5551234",
    "0341 15 555-1234",         # leading 0 of the area code and the 15 mobile prefix
    "0341-155551234",
    "(0341) 155-551234",
    "+54 341 555 1234",
    "+54 9 341 15 555-1234",    # both, as some people write it
    "549 3415551234",
    "0054 9 341 5551234",
])
def test_argentine_phone_formats_share_one_key(phone):
    assert seller_key(phone) == "tel:3415551234"


def test_buenos_aires_mobile_with_15():
    assert seller_key("011 15 5555-1234") == seller_key("+54 9 11 5555-1234") == "tel:1155551234"


def test_four_digit_area_code_with_15():
    assert seller_key("02477 15 41-2345") == seller_key("+54 9 2477 41-2345") == "tel:2477412345"


def test_a_landline_is_not_mistaken_for_a_mobile():
    assert seller_key("0341 4555123") == "tel:3414555123"


def test_short_numbers_have_no_key():
    assert seller_key("1234") is None
    assert seller_key("555-123") is None


def test_eight_digits_or_more_is_a_phone():
    assert seller_key("4555-1234") == "tel:45551234"


@pytest.mark.parametrize("word", sorted(STOPLIST))
def test_stoplist_has_no_key(word):
    assert seller_key(word) is None
    assert seller_key(word.upper()) is None


@pytest.mark.parametrize("name", ["Dueño directo", "PARTICULAR", "Información del vendedor",
                                  "Ver perfil", "WhatsApp", "dueño", "Concesionaria."])
def test_generic_labels_have_no_key(name):
    assert seller_key(name) is None


@pytest.mark.parametrize("name", [None, "", "   ", "ab", "🚗🚗", "...", "a.b"])
def test_empty_or_too_short_has_no_key(name):
    assert seller_key(name) is None


def test_the_stoplist_is_matched_whole():
    assert seller_key("Particular Autos") == "particular autos"


# ---------------------------------------------------------------------------
# app_config.seller_classification
# ---------------------------------------------------------------------------

DEFAULTS = {"enabled": True, "min_listings": 6, "window_days": 30}


def test_defaults_mirror_the_migration():
    assert DEFAULT_SELLER_CLASSIFICATION == DEFAULTS


@pytest.mark.parametrize("raw", [None, "x", 6, [], {}])
def test_missing_or_bad_config_gives_the_defaults(raw):
    assert seller_classification(raw) == DEFAULTS


def test_valid_values_are_kept():
    raw = {"enabled": False, "min_listings": 2, "window_days": 180}
    assert seller_classification(raw) == raw
    assert seller_classification({"enabled": True, "min_listings": 100, "window_days": 1}) == \
        {"enabled": True, "min_listings": 100, "window_days": 1}


@pytest.mark.parametrize("enabled", ["true", 1, 0, None, "false"])
def test_enabled_must_be_a_boolean(enabled):
    assert seller_classification({**DEFAULTS, "enabled": enabled, "min_listings": 8})["enabled"] is True


@pytest.mark.parametrize("bad", [1, 101, 0, -6, "6", 6.5, 6.0, True, None])
def test_min_listings_out_of_range_falls_back_to_6(bad):
    out = seller_classification({"enabled": False, "min_listings": bad, "window_days": 20})
    assert out == {"enabled": False, "min_listings": 6, "window_days": 20}


@pytest.mark.parametrize("bad", [0, 181, -1, "30", 7.5, False, None])
def test_window_days_out_of_range_falls_back_to_30(bad):
    out = seller_classification({"enabled": True, "min_listings": 8, "window_days": bad})
    assert out == {"enabled": True, "min_listings": 8, "window_days": 30}


def test_unknown_keys_are_dropped():
    assert seller_classification({**DEFAULTS, "extra": 1}) == DEFAULTS

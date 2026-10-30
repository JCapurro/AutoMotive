"""F-02 (docs/superpowers/specs/2026-10-30-f02-vendedor-design.md): the seller
key and the seller_classification config (paso 1); the effective seller and
the seller preference with «posible agencia» (paso 2). No database."""
from __future__ import annotations

import pytest

from intelligence import copy
from intelligence.config import DEFAULT_SELLER_CLASSIFICATION, IntelligenceConfig, seller_classification
from intelligence.matching import evaluate
from intelligence.scoring import completeness_fields
from intelligence.seller import effective_seller, seller_kind
from normalization.seller import STOPLIST, seller_key
from test_intelligence import fiesta_listing, fiesta_profile


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


# ---------------------------------------------------------------------------
# Paso 2: effective seller («posible agencia»)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("seller_type, inferred, expected", [
    ("dealer", False, "dealer"),
    ("dealer", True, "dealer"),
    ("private", True, "dealer"),      # Juan, 30/10: the inference wins over «particular»
    (None, True, "dealer"),
    ("private", False, "private"),
    (None, False, None),
])
def test_effective_seller(seller_type, inferred, expected):
    assert effective_seller({"seller_type": seller_type, "dealer_inferred": inferred}) == expected


def test_effective_seller_of_a_row_without_the_column_is_the_type():
    """Rows read before the migration, and test fixtures, have no dealer_inferred."""
    assert effective_seller({"seller_type": "private"}) == "private"
    assert effective_seller({}) is None


def test_seller_kind_tells_the_reason():
    assert copy.SELLER_INFERRED == "posible agencia"
    assert copy.REASON["seller_inferred"] == "publica {n} autos"
    assert seller_kind({"seller_type": None, "dealer_inferred": True, "seller_listing_count": 6}) == \
        "posible agencia (publica 6 autos)"
    assert seller_kind({"seller_type": "private", "dealer_inferred": True, "seller_listing_count": 9}) == \
        "posible agencia (publica 9 autos)"
    # Never «publica None autos».
    assert seller_kind({"seller_type": None, "dealer_inferred": True, "seller_listing_count": None}) == \
        "posible agencia"
    assert seller_kind({"seller_type": "dealer", "dealer_inferred": False, "seller_listing_count": 9}) == \
        "concesionaria"
    assert seller_kind({"seller_type": "private", "dealer_inferred": False}) == "particular"
    assert seller_kind({"seller_type": None}) is None


def _seller_reason(listing_kw: dict, wanted: str | None) -> dict:
    profile = fiesta_profile()
    if wanted:
        profile["preferences"]["seller_type"] = wanted
    return evaluate(fiesta_listing(**listing_kw), profile).reasons.get("seller_type")


INFERRED = {"seller_type": "private", "dealer_inferred": True, "seller_listing_count": 6}


def test_matching_an_inferred_dealer_against_a_dealer_preference_is_ok():
    r = _seller_reason(INFERRED, "dealer")
    assert (r.result, r.detail, r.hard) == ("ok", "vendedor posible agencia (publica 6 autos)", False)


def test_matching_an_inferred_dealer_against_a_private_preference_fails():
    r = _seller_reason({**INFERRED, "seller_type": None}, "private")
    assert (r.result, r.detail, r.hard) == ("fail", "vendedor posible agencia (publica 6 autos), se prefiere particular",
                                            False)
    assert "vendedor particular" not in r.detail


def test_matching_without_type_nor_inference_is_unknown():
    r = _seller_reason({"seller_type": None, "dealer_inferred": False, "seller_listing_count": 3}, "private")
    assert (r.result, r.detail) == ("unknown", copy.NOT_INFORMED)


def test_matching_explicit_types_did_not_change():
    assert _seller_reason({"seller_type": "private"}, "private").detail == "vendedor particular"
    r = _seller_reason({"seller_type": "dealer"}, "private")
    assert (r.result, r.detail) == ("fail", "vendedor concesionaria, se prefiere particular")
    assert _seller_reason({"seller_type": "dealer", "dealer_inferred": False}, "dealer").result == "ok"
    assert _seller_reason(INFERRED, None) is None, "no preference: no reason"


def test_completeness_still_reads_the_source_seller_type():
    """The inference is no informed field: an inferred listing with no type
    stays incomplete (design: completitud sin cambio)."""
    cfg = IntelligenceConfig()
    plain = completeness_fields(fiesta_listing(seller_type=None), cfg)
    inferred = completeness_fields(fiesta_listing(seller_type=None, dealer_inferred=True, seller_listing_count=7), cfg)
    assert plain == inferred
    assert inferred["seller_type"] is False


def test_scoring_version_is_the_one_shared_with_pro02():
    """Paso 2 moves scores with a seller preference: one bump, shared with
    PRO-02 in the same deploy (Juan, 30/10/2026). PRO-02 must not bump again."""
    from intelligence.config import SCORING_VERSION
    assert SCORING_VERSION == "f2-v5-seller-margin"

"""The whole catalog (migration 20261102120000_catalog_all_models): titles of
models added in it resolve to them, and the older ones still win their own."""
from __future__ import annotations

import pytest

from normalization.vehicle import resolve_vehicle
from seed_catalog import seed_catalog


@pytest.mark.parametrize("title, make, model", [
    ("Chevrolet Celta 1.4 LT 2010", "Chevrolet", "Celta"),
    ("Renault Kardian Evolution 2025", "Renault", "Kardian"),
    ("Renault Duster Oroch Outsider 2019", "Renault", "Oroch"),
    ("Renault Duster Intens 2020", "Renault", "Duster"),
    ("Fiat Titano Freedom 4x4 2024", "Fiat", "Titano"),
    ("Volkswagen Tiguan Allspace Highline", "Volkswagen", "Tiguan"),
    ("Peugeot 307 XS 2.0 2008", "Peugeot", "307"),
    ("Peugeot 2008 Allure 2020", "Peugeot", "2008"),
    ("Byd Dolphin Mini GL 2025", "BYD", "Dolphin Mini"),
    ("Chery Tiggo 4 Pro Luxury", "Chery", "Tiggo 4"),
    ("Chery Arrizo 8 Luxury PHEV 2026", "Chery", "Arrizo 8"),
    ("Chery Arrizo5 1.5 Confort 2019", "Chery", "Arrizo 5"),
    ("Gwm Haval H6 HEV 2023", "Haval", "H6"),
    ("Nissan Xtrail 2.5 Exclusive", "Nissan", "X-Trail"),
    ("Toyota Rav4 Hybrid 2022", "Toyota", "RAV4"),
    ("Mercedes Benz Ml350 2010", "Mercedes-Benz", "Clase M"),
    ("Ram 1500 Laramie 5.7 2019", "Ram", "1500"),
    ("Chevrolet Trailblazer LTZ 2018", "Chevrolet", "Trailblazer"),
    ("Gol Trend 2015 Pack I", "Volkswagen", "Gol Trend"),
])
def test_title_resolves(title, make, model):
    m = resolve_vehicle(seed_catalog(), title=title)
    assert (m.make, m.model) == (make, model)


def test_no_model_twice():
    keys = [(m.make.lower(), m.model.lower()) for m in seed_catalog()]
    assert len(keys) == len(set(keys))


# Ford F-100 (migration 20270106120000): its spellings resolve to it, never to
# the F-150, with the version the title names.
@pytest.mark.parametrize("title, trim", [
    ("Ford F-100 1985", None),
    ("Ford F100 XL 1994", "XL"),
    ("F 100 XLT diesel 1996", "XLT"),
    ("Ford F-100 Super Duty 4x4 2008", "Super Duty"),
    ("Ford F100 Duty 2005", "Duty"),
    ("Ford F-100 Standard V8 1978", "Standard"),
    # No trim aliases: "Std" names no catalog version.
    ("Ford F100 Std 1979", None),
])
def test_ford_f100(title, trim):
    m = resolve_vehicle(seed_catalog(), title=title)
    assert (m.make, m.model, m.trim) == ("Ford", "F-100", trim)


def test_f150_still_wins_its_titles():
    m = resolve_vehicle(seed_catalog(), title="Ford F-150 Lariat 2019")
    assert (m.model, m.trim) == ("F-150", "Lariat")
    m = resolve_vehicle(seed_catalog(), title="Ford F150 XLT 2015")
    assert (m.model, m.trim) == ("F-150", "XLT")


def test_f100_catalog_years():
    f100 = next(m for m in seed_catalog() if (m.make, m.model) == ("Ford", "F-100"))
    assert (f100.year_from, f100.year_to) == (1959, 2011)
    assert f100.trims == ("Standard", "XL", "XLT", "Duty", "Super Duty")
    # Within its run the year raises no "out of range" flag.
    assert "year_out_of_range" not in resolve_vehicle(seed_catalog(), title="Ford F-100 1965", year=1965).notes

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

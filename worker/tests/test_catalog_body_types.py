"""vehicle_catalog.body_types as seed.sql and its migration carry them (docs/CARROCERIA.md)."""
from __future__ import annotations

import pytest

from normalization.body_type import CODES
from seed_catalog import SEED, body_types_block, seed_catalog

MIGRATION = SEED.parent / "migrations" / "20261030120100_catalog_body_types.sql"


def _by_model() -> dict[tuple[str, str], tuple[str, ...]]:
    return {(m.make.lower(), m.model.lower()): m.body_types for m in seed_catalog()}


def test_every_seed_model_has_known_body_types():
    for (make, model), body_types in _by_model().items():
        assert body_types, f"{make} {model} has no body types"
        assert set(body_types) <= set(CODES), f"{make} {model}: {body_types}"
        assert len(set(body_types)) == len(body_types), f"{make} {model}: {body_types}"


def test_seed_and_migration_carry_the_same_list():
    seed = body_types_block(SEED.read_text(encoding="utf-8"))
    migration = body_types_block(MIGRATION.read_text(encoding="utf-8"))
    assert seed == migration
    # No entry for a model the catalog doesn't have (a typo would update nothing).
    assert set(migration) == set(_by_model())


@pytest.mark.parametrize("make, model, expected", [
    ("Toyota", "Corolla", ("sedan",)),
    ("Toyota", "Corolla Cross", ("suv",)),
    ("Toyota", "Hilux", ("pickup",)),
    ("Toyota", "SW4", ("suv",)),
    ("Toyota", "Etios", ("hatchback", "sedan")),
    # Oroch is caught by name (body_type.py); a plain Duster is certain.
    ("Renault", "Duster", ("suv",)),
    ("Renault", "Sandero", ("hatchback",)),
    ("Renault", "Kangoo", ("utilitario", "monovolumen")),
    ("Chevrolet", "Spin", ("monovolumen",)),
    ("Chevrolet", "Onix", ("hatchback",)),
    ("Chevrolet", "Onix Plus", ("sedan",)),
    ("Ford", "Ka", ("hatchback", "sedan")),
    ("Fiat", "Palio", ("hatchback", "rural")),
    ("Volkswagen", "Suran", ("monovolumen",)),
    ("Mercedes-Benz", "Sprinter", ("utilitario",)),
])
def test_known_models(make, model, expected):
    assert _by_model()[(make.lower(), model.lower())] == expected

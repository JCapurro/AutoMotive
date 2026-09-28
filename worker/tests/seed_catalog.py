"""vehicle_catalog as supabase/seed.sql inserts it, without a database.

The LLM contract tests (and tools/record_llm.py) normalize drafts against the
real seed, so a catalog change that breaks a golden phrase shows up here.
"""
from __future__ import annotations

import re
from functools import cache
from pathlib import Path

from normalization.vehicle import CatalogModel

SEED = Path(__file__).resolve().parents[2] / "supabase" / "seed.sql"

# ('Ford', 'Fiesta', '{fiesta kinetic,…}', null, 2019, '{manual,automatic}', '{nafta,diesel}', '{S,SE,…}'),
_ROW = re.compile(
    r"\(\s*'([^']+)',\s*'([^']+)',\s*'\{([^}]*)\}',\s*(null|\d{4}),\s*(null|\d{4}),"
    r"\s*'\{[^}]*\}',\s*'\{[^}]*\}',\s*'\{([^}]*)\}'\s*\)"
)


def _items(text: str) -> tuple[str, ...]:
    return tuple(x.strip() for x in text.split(",") if x.strip())


def _year(text: str) -> int | None:
    return None if text == "null" else int(text)


@cache
def seed_catalog() -> list[CatalogModel]:
    sql = SEED.read_text(encoding="utf-8")
    block = sql[sql.index("with models ("):sql.index("insert into public.vehicle_catalog")]
    models = [CatalogModel(make, model, _items(aliases), _items(trims), _year(y0), _year(y1))
              for make, model, aliases, y0, y1, trims in _ROW.findall(block)]
    if len(models) < 50:
        raise RuntimeError(f"seed.sql: only {len(models)} catalog rows parsed; did the format change?")
    return models

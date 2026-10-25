"""vehicle_catalog as supabase/seed.sql inserts it, without a database.

The LLM contract tests (and tools/record_llm.py) normalize drafts against the
real seed, so a catalog change that breaks a golden phrase shows up here.
Body types come from the seed's `set body_types` update, which follows the
inserts (the same list as migration 20261030120100_catalog_body_types.sql),
and timing_belt from its `set timing_belt` updates.
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
# ('Volkswagen', 'Gol', true),
_TIMING_ROW = re.compile(r"\(\s*'([^']+)',\s*'([^']+)',\s*(true|false)\s*\)")
_PAIR_ROW = re.compile(r"\(\s*'([^']+)',\s*'([^']+)'\s*\)")
# ('Ford', 'Fiesta', '{hatchback,sedan}'),
_BODY_ROW = re.compile(r"\(\s*'([^']+)',\s*'([^']+)',\s*'\{([^}]*)\}'\s*\)")


def _items(text: str) -> tuple[str, ...]:
    return tuple(x.strip() for x in text.split(",") if x.strip())


def _year(text: str) -> int | None:
    return None if text == "null" else int(text)


def body_types_block(sql: str) -> dict[tuple[str, str], tuple[str, ...]]:
    """(make, model) in lowercase → body types, from the `update … set body_types`
    of seed.sql or of the catalog migration."""
    start = sql.index("set body_types =")
    block = sql[start:sql.index("as v (make, model, body_types)", start)]
    return {(make.lower(), model.lower()): _items(codes)
            for make, model, codes in _BODY_ROW.findall(block)}


def timing_block(sql: str) -> dict[tuple[str, str], bool]:
    """(make, model) in lowercase → timing_belt, from every `set timing_belt`
    update of seed.sql (or of a migration), later ones winning; a
    `set timing_belt = null` one takes the model back to unknown."""
    out: dict[tuple[str, str], bool] = {}
    for m in re.finditer(r"set timing_belt = (v\.belt|null)", sql):
        if m.group(1) == "null":  # back to unknown
            block = sql[m.start():sql.index("as v (make, model)", m.start())]
            for make, model in _PAIR_ROW.findall(block):
                out.pop((make.lower(), model.lower()), None)
            continue
        block = sql[m.start():sql.index("as v (make, model, belt)", m.start())]
        out.update({(make.lower(), model.lower()): belt == "true"
                    for make, model, belt in _TIMING_ROW.findall(block)})
    return out


@cache
def seed_catalog() -> list[CatalogModel]:
    sql = SEED.read_text(encoding="utf-8")
    block = sql[sql.index("with models ("):sql.index("insert into public.vehicle_catalog")]
    bodies = body_types_block(sql)
    timing = timing_block(sql)
    models = [CatalogModel(make, model, _items(aliases), _items(trims), _year(y0), _year(y1),
                           bodies.get((make.lower(), model.lower()), ()),
                           timing.get((make.lower(), model.lower())))
              for make, model, aliases, y0, y1, trims in _ROW.findall(block)]
    if len(models) < 50 or len(bodies) < 50:
        raise RuntimeError(f"seed.sql: only {len(models)} catalog rows and {len(bodies)} body types "
                           "parsed; did the format change?")
    return models

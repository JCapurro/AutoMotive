"""
Recompute the body type of the stored listings (docs/CARROCERIA.md, "Datos existentes").

    python -m tools.backfill_body_type [--dry-run] [--source kavak] [--batch 500]

Reads what each listing already has, without asking the sources: title,
URL, the version and the source's own value kept in attributes (Mercado
Libre's "Tipo de carrocería", Kavak's bodyType, V6's "Categoría", Randazzo's
"Tipo de vehículo") and the catalog. Goes by id in batches and writes
body_type and attributes._body_type only where a body type is found that
differs from the stored one (not knowing never erases one). No snapshot, no
event and no sighting: the body type is not a key attribute.

--dry-run prints what would change, per code and method, and writes nothing.
Afterwards, `python -m tools.reprocess --raw --outdated --source <fuente>`
re-reads the stored pages of the sources whose parser learned the body type.
Run from worker/.
"""
from __future__ import annotations

import argparse
import logging
import sys
from collections import Counter
from typing import Any, Iterable

from psycopg.types.json import Jsonb

import db
from aio import run
from db.repos.catalog import load_models
from normalization.listing import stored_body_type
from normalization.vehicle import CatalogModel

log = logging.getLogger("backfill_body_type")

BATCH = 500
_SELECT = ("SELECT id, source, make, model, trim, title, url, body_type, attributes "
           "  FROM listings WHERE id > %s{source} ORDER BY id LIMIT %s")


def change_for(row: dict[str, Any], catalog: list[CatalogModel]) -> tuple[str, dict[str, Any]] | None:
    """(body_type, attributes._body_type) to write, or None when the stored body
    type stands. As in pipeline/ingest.py's merge, not knowing never erases a
    known one: what decided it may not be stored (a card's title since replaced)."""
    code, how = stored_body_type(row, catalog)
    return None if code is None or code == row.get("body_type") else (code, how)


def plan(rows: Iterable[dict[str, Any]], catalog: list[CatalogModel],
         counts: Counter | None = None) -> list[tuple[int, str, dict[str, Any]]]:
    """The updates of one batch: (id, body_type, attributes._body_type). `counts`
    tallies (new code, method) of each change, plus ('=', '') per row left alone."""
    out = []
    for row in rows:
        change = change_for(row, catalog)
        if change is None:
            if counts is not None:
                counts[("=", "")] += 1
            continue
        code, how = change
        if counts is not None:
            counts[(code, how["method"])] += 1
        out.append((row["id"], code, how))
    return out


def report(counts: Counter, *, dry_run: bool) -> list[str]:
    changed = sum(n for key, n in counts.items() if key != ("=", ""))
    lines = [f"{code:<12} {method:<9} {n:>7}"
             for (code, method), n in sorted(counts.items()) if (code, method) != ("=", "")]
    lines.append(f"{changed} publicación(es) {'cambiarían' if dry_run else 'cambiaron'}; "
                 f"{counts[('=', '')]} sin cambios")
    return lines


async def backfill(*, dry_run: bool, source: str | None = None, batch: int = BATCH) -> Counter:
    async with db.connection() as cx:
        catalog = await load_models(cx)
    counts: Counter = Counter()
    last_id = 0
    sql = _SELECT.format(source=" AND source = %s" if source else "")
    while True:
        params = (last_id, source, batch) if source else (last_id, batch)
        async with db.connection() as cx:
            rows = await (await cx.execute(sql, params)).fetchall()
            if not rows:
                break
            last_id = rows[-1]["id"]
            updates = plan(rows, catalog, counts)
            if updates and not dry_run:
                # jsonb_set: attributes written meanwhile by a crawl are kept.
                async with cx.cursor() as cur:
                    await cur.executemany(
                        "UPDATE listings SET body_type = %s, "
                        "       attributes = jsonb_set(coalesce(attributes, '{}'), '{_body_type}', %s) "
                        " WHERE id = %s",
                        [(code, Jsonb(how), lid) for lid, code, how in updates])
        log.info("hasta #%s: %s cambio(s)", last_id, len(updates))
    return counts


async def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="python -m tools.backfill_body_type", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="solo contar qué cambiaría")
    ap.add_argument("--source", help="una sola fuente")
    ap.add_argument("--batch", type=int, default=BATCH, help=f"avisos por lote (default {BATCH})")
    args = ap.parse_args(argv)

    await db.open_pool()
    try:
        counts = await backfill(dry_run=args.dry_run, source=args.source, batch=max(1, args.batch))
    finally:
        await db.close_pool()
    print("\n".join(report(counts, dry_run=args.dry_run)))
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    sys.exit(run(main(sys.argv[1:])))

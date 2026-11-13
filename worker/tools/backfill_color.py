"""
Fill the color of the stored listings from what they already have (docs/PLAN_FILTRO_COLOR.md, Fase 1).

    python -m tools.backfill_color [--write] [--source kavak] [--batch 500]

Dry run by default: prints what would change, per code and method, and
writes nothing. --write writes.

Reads what each listing already has, without asking the sources: the
source's value kept in attributes (Mercado Libre's and Randazzo's "Color",
Kavak's JSON-LD "color", Autocosmos's "Color" once its parser read it) and,
without one, the title or description with an anchor ("color blanco",
"color: gris", "pintura roja"; never a bare word). Goes by id in batches and
writes color and attributes._color only where normalization/color.py's
precedence lets it (source > text > photos): not knowing never erases a
color, and the text never overwrites the source's. No snapshot, no event and
no sighting: the color is not a key attribute.

Afterwards, `python -m tools.reprocess --raw --outdated --source autocosmos`
re-reads Autocosmos's stored pages (DETAIL_PARSER_VERSION 5 reads
itemprop="color"). Run from worker/.
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
from normalization.listing import stored_color_update

log = logging.getLogger("backfill_color")

BATCH = 500
_SELECT = ("SELECT id, source, title, description, color, attributes "
           "  FROM listings WHERE id > %s{source} ORDER BY id LIMIT %s")


def plan(rows: Iterable[dict[str, Any]], counts: Counter | None = None) -> list[tuple[int, str, dict[str, Any]]]:
    """The updates of one batch: (id, color, attributes._color). `counts`
    tallies (source, new code, method) of each change, plus ('=', '', '') per
    row left alone."""
    out = []
    for row in rows:
        change = stored_color_update(row)
        if change is None:
            if counts is not None:
                counts[("=", "", "")] += 1
            continue
        code, how = change
        if counts is not None:
            counts[(row.get("source") or "?", code, how["method"])] += 1
        out.append((row["id"], code, how))
    return out


def report(counts: Counter, *, dry_run: bool) -> list[str]:
    same = ("=", "", "")
    changed = sum(n for key, n in counts.items() if key != same)
    lines = [f"{source:<14} {code:<8} {method:<7} {n:>7}"
             for (source, code, method), n in sorted(counts.items()) if (source, code, method) != same]
    lines.append(f"{changed} publicación(es) {'cambiarían' if dry_run else 'cambiaron'}; "
                 f"{counts[same]} sin cambios")
    return lines


async def backfill(*, dry_run: bool, source: str | None = None, batch: int = BATCH) -> Counter:
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
            updates = plan(rows, counts)
            if updates and not dry_run:
                # jsonb_set: attributes written meanwhile by a crawl are kept.
                # The method check runs again in SQL: a crawl or the color
                # pass may have written a stronger one since the read.
                async with cx.cursor() as cur:
                    await cur.executemany(
                        "UPDATE listings SET color = %s, "
                        "       attributes = jsonb_set(coalesce(attributes, '{}'), '{_color}', %s) "
                        " WHERE id = %s "
                        "   AND (%s = 'source' OR coalesce(attributes->'_color'->>'method', '') <> 'source')",
                        [(code, Jsonb(how), lid, how["method"]) for lid, code, how in updates])
        log.info("hasta #%s: %s cambio(s)", last_id, len(updates))
    return counts


async def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="python -m tools.backfill_color", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--write", action="store_true", help="escribir (sin esto, solo cuenta qué cambiaría)")
    ap.add_argument("--source", help="una sola fuente")
    ap.add_argument("--batch", type=int, default=BATCH, help=f"avisos por lote (default {BATCH})")
    args = ap.parse_args(argv)

    await db.open_pool()
    try:
        counts = await backfill(dry_run=not args.write, source=args.source, batch=max(1, args.batch))
    finally:
        await db.close_pool()
    print("\n".join(report(counts, dry_run=not args.write)))
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    sys.exit(run(main(sys.argv[1:])))

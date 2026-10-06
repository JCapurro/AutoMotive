"""
Read again what is already stored, without asking the sources (normalization v3).

    python -m tools.reprocess --facts [--dry-run] [--llm] [--source facebook]
        Recompute description_facts and the effective price of every listing
        with a description, from the text already stored: the backfill of the
        listings stored before the description counted (they have no raw
        page). Year, km, transmission and fuel are filled where missing.
        --llm: ask the LLM for the descriptions the rules find ambiguous
        (within app_config.description_facts.llm_daily_cap).

    python -m tools.reprocess --raw [--source facebook] [--outdated] [--dry-run]
        Parse the stored detail pages (raw_pages) again and ingest them like a
        detail pass that saw nothing new. --outdated: only the pages parsed
        with an older DETAIL_PARSER_VERSION of their collector.

Both print what changes and re-score the matches of the listings whose
price changed. Run from worker/.
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timezone
from typing import Any

import db
from aio import run
from collectors import REGISTRY, Listing
from db.repos import listings as repo
from db.repos import raw_pages
from db.repos.catalog import load_models
from db.repos.fx import quote_for_today
from intelligence.copy import money
from normalization.description_facts import DescriptionFacts, parse, resolve_price
from normalization.price_check import keyword_partial
from normalization.vehicle import CatalogModel, resolve_trim
from pipeline.enrich import DescriptionLLM, ingest_detail, rescore_changed
from pipeline.ingest import IngestResult, _published, _same_number, _to_usd, _usd_rate
from pipeline.rescore import rescore_listings

log = logging.getLogger("reprocess")

_PRICE_COLUMNS = ("price", "currency", "price_usd", "price_partial", "price_partial_reason",
                  "price_source", "price_published", "price_published_currency", "description_facts")


def _published_reason(row: dict[str, Any]) -> str | None:
    """Why the title or the page's structure say the published price is
    partial. A reason derived from the description itself is recomputed."""
    reason = row.get("price_partial_reason")
    if row.get("price_partial") and reason and not reason.startswith("descripción"):
        return reason
    return keyword_partial(row.get("title"))


def recompute(row: dict[str, Any], facts: DescriptionFacts | None, *,
              today_rate: float | None, catalog: list[CatalogModel] | None = None) -> dict[str, Any]:
    """The columns that change for a stored row given a reading of its text."""
    pub, pub_cur = _published(row)
    rate = _usd_rate(row) or today_rate
    price = resolve_price(pub, pub_cur, partial_reason=_published_reason(row), facts=facts, usd_rate=rate)
    if facts is not None:
        facts.price_check = price.check()
    same = _same_number(price.price, row.get("price")) and price.currency == row.get("currency")
    new = {
        "price": price.price, "currency": price.currency,
        "price_usd": row.get("price_usd") if same else _to_usd(price.price, price.currency, rate),
        "price_partial": price.partial, "price_partial_reason": price.partial_reason,
        "price_source": price.source, "price_published": pub, "price_published_currency": pub_cur,
        "description_facts": facts.to_json() if facts is not None and not facts.is_empty() else None,
    }
    if facts is not None:
        for column, value in (("year", facts.year), ("mileage_km", facts.mileage_km),
                              ("transmission", facts.transmission), ("fuel", facts.fuel)):
            if row.get(column) is None and value is not None:
                new[column] = value
        if not row.get("trim") and facts.claims.get("trim"):
            model = next((m for m in catalog or [] if m.make == row.get("make") and m.model == row.get("model")), None)
            if model and (trim := resolve_trim(model, facts.claims["trim"])):
                new["trim"] = trim
        filled = [k for k in ("year", "mileage_km", "transmission", "fuel", "trim") if k in new and row.get(k) is None]
        if filled:
            attrs = dict(row.get("attributes") or {})
            attrs["_description_filled"] = list(dict.fromkeys([*attrs.get("_description_filled", []), *filled]))
            new["attributes"] = attrs
    return {k: v for k, v in new.items() if v != row.get(k)}


def _line(row: dict[str, Any], changed: dict[str, Any]) -> str:
    before = money(row.get("price"), row.get("currency"))
    after = money(changed.get("price", row.get("price")), changed.get("currency", row.get("currency")))
    facts = changed.get("description_facts") or row.get("description_facts") or {}
    check = facts.get("price_check") or {}
    notes = [f"precio {before} → {after}" if before != after else f"precio {after}"]
    if "price_partial" in changed:
        notes.append("parcial" if changed["price_partial"] else "ya no es parcial")
    if check.get("effective_kind") == "cash":
        notes.append("contado")
    if (facts.get("financing") or {}).get("offered"):
        notes.append("financiable")
    if check.get("mismatch"):
        m = check["mismatch"]
        notes.append(f"otro precio en la descripción: {money(m['amount'], m['currency'])}")
    filled = [c for c in ("year", "mileage_km", "transmission", "fuel") if c in changed]
    if filled:
        notes.append("completa " + ", ".join(filled))
    return f"#{row['id']:<6} {row['source']:<12} " + " · ".join(notes)


async def reprocess_facts(*, dry_run: bool, llm: bool, source: str | None = None) -> list[int]:
    """--facts. Return every changed id so claims/questions are re-scored too.

    Dry-run never contacts an LLM or reserves a paid attempt.
    """
    async with db.connection() as cx:
        fx = await quote_for_today(cx)
        catalog = await load_models(cx)
        sql = "SELECT * FROM listings WHERE description IS NOT NULL"
        rows = await (await cx.execute(sql + (" AND source = %s" if source else "") + " ORDER BY id",
                                       (source,) if source else ())).fetchall()
    helper = await DescriptionLLM.create() if llm and not dry_run else None
    now_year = datetime.now(timezone.utc).year
    repriced: list[int] = []
    for row in rows:
        row = repo._pythonic(dict(row))
        stored = DescriptionFacts.from_json(row.get("description_facts"))
        if stored is not None and stored.source == "llm":
            facts = stored                          # the LLM already read this text
        else:
            facts = parse(row["description"], row["title"], now_year=now_year)
        if helper is not None:
            item = Listing(source=row["source"], listing_id=row["external_id"], url=row["url"],
                           titulo=row["title"], descripcion=row["description"])
            await helper.refine(row["id"], item)
            if item.extra.get("description_facts"):
                facts = DescriptionFacts.from_json(item.extra["description_facts"])
        elif llm and dry_run:
            print(f"#{row['id']} análisis IA pendiente de aplicar; dry-run no hace llamadas")
        changed = recompute(row, facts, today_rate=fx.rate if fx else None, catalog=catalog)
        if not changed:
            continue
        repriced.append(row["id"])
        print(_line(row, changed))
        if not dry_run:
            async with db.connection() as cx:
                await repo.update_listing(cx, row["id"], changed, seen=False)
    return repriced


async def reprocess_raw(*, dry_run: bool, source: str | None = None, outdated: bool = False) -> IngestResult:
    """--raw. Stored pages → parse_detail() → ingest, without marking anything seen."""
    below = {name: cls.DETAIL_PARSER_VERSION for name, cls in REGISTRY.items()} if outdated else None
    total = IngestResult()
    async for page in raw_pages.iter_for_reparse(source=source, below_version=below):
        if page.source not in REGISTRY:
            continue
        scraper = REGISTRY[page.source]()
        try:
            detail = scraper.parse_detail(page.html, page.url, page.status)
        except Exception as e:
            print(f"#{page.listing_id:<6} {page.source:<12} no se pudo leer: {type(e).__name__}: {e}")
            continue
        async with db.connection() as cx:
            row = await (await cx.execute(
                "SELECT id, source, external_id, url, make, model, status FROM listings WHERE id = %s",
                (page.listing_id,))).fetchone()
        if row is None or row["status"] != "active":
            continue
        if dry_run:
            what = "ya no está" if detail.gone else \
                f"descripción de {len(detail.listing.descripcion or '')} caracteres"
            print(f"#{page.listing_id:<6} {page.source:<12} {what}")
            continue
        result = await ingest_detail(dict(row), detail, stage="reprocess", seen=False)
        total.extend(result)
        await raw_pages.mark_parsed(page.listing_id, scraper.DETAIL_PARSER_VERSION)
        for e in result.events:
            print(f"#{e.listing_id:<6} {page.source:<12} {e.kind}: {', '.join(e.changes) or '—'}")
    return total


async def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="python -m tools.reprocess", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    what = ap.add_mutually_exclusive_group(required=True)
    what.add_argument("--facts", action="store_true", help="desde las descripciones guardadas")
    what.add_argument("--raw", action="store_true", help="desde las páginas guardadas (raw_pages)")
    ap.add_argument("--dry-run", action="store_true", help="solo mostrar qué cambiaría")
    ap.add_argument("--llm", action="store_true", help="--facts: analizar descripciones con IA y caché (sin llamadas en dry-run)")
    ap.add_argument("--outdated", action="store_true", help="--raw: solo las parseadas con una versión vieja")
    ap.add_argument("--source", help="una sola fuente")
    args = ap.parse_args(argv)

    await db.open_pool()
    try:
        if args.facts:
            repriced = await reprocess_facts(dry_run=args.dry_run, llm=args.llm, source=args.source)
            if repriced and not args.dry_run:
                await rescore_listings(repriced)
            print(f"{len(repriced)} publicación(es) {'cambiarían' if args.dry_run else 'cambiaron'}")
        else:
            result = await reprocess_raw(dry_run=args.dry_run, source=args.source, outdated=args.outdated)
            if not args.dry_run:
                await rescore_changed(result)
            print(f"{result.updated} publicación(es) actualizada(s)")
    finally:
        await db.close_pool()
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    sys.exit(run(main(sys.argv[1:])))

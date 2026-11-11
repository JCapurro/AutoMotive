"""
Repair the stored Facebook listings: parts ingested as cars, and bare-"$"
prices read in the wrong currency.

    python -m tools.repair_facebook [--write] [--source facebook] [--examples 5]

Without --write (the default) it only reads, and prints per source how many
active listings would change, with examples. With --write, in one
transaction:

* parts (normalization/not_vehicle.py): ended without an event, out of
  comparables and market stats, and their matches deleted
  (listings.mark_not_vehicle); nobody is notified;
* ads whose stored title carries Facebook's «Sold · »/«Vendido · »
  (collectors.facebook.card_status, read before the crawl ended them):
  status 'gone' as a sold detail page leaves them, after the price fixes
  below (a gone listing still counts among the comparables). No event: the
  end only reaches who saved or follows a listing, so those (the ones the
  watchlist reads, listings.watchlist_queue) are left active for its detail
  read, which tells them. Their matches stay, as a sold listing's do (no
  view shows a gone listing). A sold part counts as a part. A «Pending · »
  one (reserved, it may open again) stays active and loses the mark in its
  title, which the crawl's card can't give it back to an enriched listing
  (ingest.merge keeps its stored title);
* ads whose last item page sent to Marketplace's home («?unavailable_product=1»,
  raw_pages): they no longer exist, and the page read as theirs stored «You»
  as their title (collectors.facebook.fetch_detail_page now reads that as a
  404). Ended as a sold card's are, and the same ones left to the watchlist;
* doubtful prices (money.facebook_currency gives None): a "USD" price written
  with a bare "$" (not «US$», «U$S», «USD») of a car that is not high-end,
  with FB_USD_CEILING <= amount < 1.000.000. Neither dollars nor pesos make it
  a car's price (ARS 100.000-999.999 is USD ~70-700: a part whose title
  doesn't start with it, a down payment, a placeholder). The listing is left
  without a price (price, currency, price_usd, price_published null) and
  flagged partial («precio de Facebook no interpretable: $ 600.000»), which
  keeps it out of matching, comparables, the preview and market stats; what
  was read is kept in attributes._currency_read; its matches are deleted
  without notifying. The same goes for the rows #73 read as pesos from such a
  figure (ARS 100.000-999.999, attributes._currency_read with "as": "ARS"),
  and for the ones it left without a price but not partial
  (attributes._currency_read with "as": null). A row the crawl already
  flagged keeps its matches until the nightly re-score: they are deleted
  here too, in the same category;
* a "USD" bare-"$" price of a million or more (stored before the collector
  read those as ARS) becomes ARS: the effective price is resolved again with
  the stored description facts and today's dollar, and its matches re-scored
  (which never notifies and deletes the ones that no longer fit);
* attributes.moneda that disagrees with the published currency is set to it
  (listing 21327: price in USD, attributes.moneda ARS).

High-end cars (money.HIGH_END_MAKES / HIGH_END_MODELS) and prices written
with a sign that names the dollar keep their USD.

The crawl applies the same rules to every listing it reads from now on
(normalization.listing.facebook_price; a doubtful listing read again with a
credible price gets it back and loses the flag, with no price drop event);
this is for what was stored before. A second run finds nothing. Run from
worker/.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any

from psycopg.types.json import Jsonb

import db
from collectors.facebook import card_status
from aio import run
from db.repos import listings as listings_repo
from db.repos import fx as fx_repo
from db.repos.fx import quote_for_today, today_ar
from normalization import not_vehicle
from normalization.description_facts import DescriptionFacts, resolve_price
from normalization.fx import FxQuote
from normalization.listing import doubtful_price, facebook_price, price_usd
from normalization.price_check import keyword_partial
from pipeline.rescore import rescore_listings

log = logging.getLogger("repair_facebook")

PART = "repuestos a excluir"
CARD_GONE = "vendidos en la tarjeta a terminar"
CARD_WATCHED = "vendidos guardados: los cierra la watchlist"
UNAVAILABLE = "avisos que ya no existen a terminar"
UNAVAILABLE_WATCHED = "avisos que ya no existen guardados: watchlist"
TITLE = "títulos «Pending ·» a limpiar"
PART_MATCHES = "matches de repuestos a borrar"
TO_ARS = "monedas USD -> ARS"
DOUBTFUL = "precios dudosos -> sin precio"
DOUBTFUL_MATCHES = "matches de precios dudosos a borrar"
MONEDA = "attributes.moneda a sincronizar"
RESCORED = "matches re-puntuados"
DELETED = "matches de precios dudosos borrados"

_SELECT = ("SELECT l.id, l.source, l.external_id, l.title, l.description, l.make, l.model, l.year, "
           "       l.mileage_km, l.price, l.currency, l.price_usd, l.price_published, "
           "       l.price_published_currency, l.price_partial, l.price_partial_reason, "
           "       l.description_facts, l.attributes, "
           "       (SELECT count(*) FROM matches m WHERE m.listing_id = l.id)::int AS n_matches, "
           # The watchlist reads it (listings.watchlist_queue), and tells its end.
           "       EXISTS (SELECT 1 FROM user_listing_interactions i "
           "                WHERE i.listing_id = l.id AND public.commercial_access_active(i.user_id) "
           "                  AND (i.saved OR i.status IN ('interested', 'contacted', 'visit_scheduled'))) "
           "         AS watched, "
           # Its last item page sent to Marketplace's home: the ad no longer exists
           # (collectors.facebook.fetch_detail_page, before which it stored «You»).
           "       coalesce((SELECT r.url ~ 'unavailable_product' FROM raw_pages r "
           "                  WHERE r.listing_id = l.id ORDER BY r.fetched_at DESC LIMIT 1), false) "
           "         AS unavailable "
           "  FROM listings l WHERE l.status = 'active' AND l.source = ANY(%s) ORDER BY l.id")


@dataclass
class Plan:
    parts: list[tuple[int, str]] = field(default_factory=list)
    card_gone: list[int] = field(default_factory=list)  # «Sold · ...» titles: status gone
    titles: list[tuple[int, str, str]] = field(default_factory=list)  # «Pending · ...»: (id, stored, bare)
    prices: list[tuple[dict[str, Any], dict[str, Any]]] = field(default_factory=list)  # (row, new values)
    doubtful: list[int] = field(default_factory=list)  # listings left without a price: their matches go
    stale: list[int] = field(default_factory=list)  # already without a price, flagged, still matched
    monedas: list[tuple[int, str]] = field(default_factory=list)
    counts: Counter = field(default_factory=Counter)
    examples: dict[tuple[str, str], list[str]] = field(default_factory=lambda: defaultdict(list))

    def note(self, source: str, what: str, example: str, n: int = 1, *, keep: int) -> None:
        self.counts[(source, what)] += n
        if len(self.examples[(source, what)]) < keep:
            self.examples[(source, what)].append(example)


def _published(row: dict[str, Any]) -> tuple[float | None, str | None]:
    if row.get("price_published") is not None:
        return float(row["price_published"]), row.get("price_published_currency") or row.get("currency")
    return (float(row["price"]) if row.get("price") is not None else None), row.get("currency")


def _money(amount: Any, currency: str | None) -> str:
    return f"{currency or ''} {int(amount):,}".replace(",", ".") if amount else "sin precio"


def _without_price(row: dict[str, Any], note: dict[str, Any], reason: str) -> dict[str, Any]:
    facts_json = row.get("description_facts")
    if facts_json is not None:
        # resolve_price without a published number: nothing else to say.
        check = resolve_price(None, None, partial_reason=reason, facts=None, usd_rate=None).check()
        facts_json = {**facts_json, "price_check": check}
    return {"price_published": None, "price_published_currency": None, "price": None, "currency": None,
            "price_usd": None, "price_source": "published", "price_partial": True,
            "price_partial_reason": reason, "description_facts": facts_json,
            "attributes": {"_currency_read": note}, "_drop_moneda": True}


def reprice(row: dict[str, Any], fx: FxQuote | None) -> dict[str, Any] | None:
    """The price columns of a stored row once facebook_price is applied, or
    None when it doesn't change them."""
    pub, cur = _published(row)
    attrs = row.get("attributes") or {}
    if pub is None:
        # Left without a price by an earlier version, but not flagged.
        note = attrs.get("_currency_read")
        reason = doubtful_price(note)
        if reason is None or (row.get("price_partial") and row.get("price_partial_reason") == reason):
            return None
        return _without_price(row, {**note, "reason": reason}, reason)
    read = attrs.get("_currency_read") or {}
    if cur == "ARS" and read.get("as") == "ARS" and read.get("currency") == "USD" \
            and read.get("amount") is not None and abs(float(read["amount"]) - pub) < 0.5:
        # Read as pesos by #73 from a bare-"$" "USD" figure (ARS 600.000 for
        # «Ford ecosport porton trasero»): what the rule says of that read now.
        amount, currency, note = facebook_price(row["source"], pub, "USD", make=row.get("make"),
                                                model=row.get("model"), sign=attrs.get("_price_sign"))
        if note is None or amount is not None:
            return None                     # still ARS (a million or more), or high-end: as stored
    else:
        amount, currency, note = facebook_price(row["source"], pub, cur, make=row.get("make"),
                                                model=row.get("model"), sign=attrs.get("_price_sign"))
    if note is None:
        return None
    note = {**note, "by": "tools.repair_facebook"}
    if amount is None:
        return _without_price(row, note, doubtful_price(note))
    facts_json = row.get("description_facts")
    facts = DescriptionFacts.from_json(facts_json)
    partial_reason = keyword_partial(row.get("title"))
    rate = fx.rate if fx and fx.rate > 0 else None
    price = resolve_price(amount, currency, partial_reason=partial_reason, facts=facts, usd_rate=rate)
    if facts is not None:
        facts_json = {**(facts_json or {}), "price_check": price.check()}
    return {"price_published": amount, "price_published_currency": currency, "price": price.price,
            "currency": price.currency, "price_usd": price_usd(price.price, price.currency, fx),
            "price_source": price.source, "price_partial": price.partial,
            "price_partial_reason": price.partial_reason, "description_facts": facts_json,
            "attributes": {"_currency_read": note, "moneda": currency}, "_drop_moneda": False}


def plan(rows: list[dict[str, Any]], fx: FxQuote | None, *, examples: int = 5) -> Plan:
    out = Plan()
    for row in rows:
        source, label = row["source"], f"#{row['id']} «{row['title']}»"
        price = _money(*_published(row))
        bare, status = card_status(row.get("title") or "")
        if row["source"] != "facebook":
            bare, status = row.get("title"), None
        if reason := not_vehicle.classify_row({**row, "title": bare} if status else row):
            out.parts.append((row["id"], reason))
            out.note(source, PART, f"{label} {price} — {reason}", keep=examples)
            if row.get("n_matches"):
                out.note(source, PART_MATCHES, f"{label}: {row['n_matches']}", row["n_matches"], keep=examples)
            continue
        if row.get("unavailable") and row.get("watched"):
            # As a sold one: the watchlist's detail read (now a 404) tells its end.
            out.note(source, UNAVAILABLE_WATCHED, label, keep=examples)
        elif row.get("unavailable"):
            out.card_gone.append(row["id"])
            out.note(source, UNAVAILABLE, label, keep=examples)
        elif status == "sold" and row.get("watched"):
            # Left to the watchlist, whose detail read tells its end to who
            # saved or follows it; the repair would end it in silence.
            out.note(source, CARD_WATCHED, label, keep=examples)
        elif status == "sold":
            # It ends after its price is fixed below: a gone listing still
            # counts among the comparables.
            out.card_gone.append(row["id"])
            out.note(source, CARD_GONE, f"{label} — {status}", keep=examples)
        elif status == "pending":
            # Reserved, may open again: it stays, without the mark in its
            # title (an enriched one keeps its stored title, ingest.merge).
            out.titles.append((row["id"], row["title"], bare))
            out.note(source, TITLE, f"{label} -> «{bare}»", keep=examples)
        if (values := reprice(row, fx)) is not None:
            out.prices.append((row, values))
            n = row.get("n_matches") or 0
            if values["price"] is None:
                out.doubtful.append(row["id"])
                read = values["attributes"]["_currency_read"]
                out.note(source, DOUBTFUL, f"{label} USD {_money(read['amount'], '').strip()} leído -> sin precio "
                                           f"({values['price_partial_reason']}; {n} matches)", keep=examples)
                if n:
                    out.note(source, DOUBTFUL_MATCHES, f"{label}: {n}", n, keep=examples)
            else:
                after = _money(values["price"], values["currency"])
                out.note(source, TO_ARS, f"{label} {price} -> {after} ({n} matches)", keep=examples)
            continue
        pub, cur = _published(row)
        if pub is None and row.get("n_matches") and row.get("price_partial") \
                and doubtful_price((row.get("attributes") or {}).get("_currency_read")):
            # Flagged by the crawl, whose matches stay until the nightly re-score.
            out.stale.append(row["id"])
            out.note(source, DOUBTFUL_MATCHES, f"{label}: {row['n_matches']}", row["n_matches"], keep=examples)
            continue
        moneda = (row.get("attributes") or {}).get("moneda")
        if cur and moneda and moneda != cur:
            out.monedas.append((row["id"], cur))
            out.note(source, MONEDA, f"{label} {price}, attributes.moneda {moneda}", keep=examples)
    return out


async def apply(p: Plan) -> tuple[list[int], int]:
    """Write the plan. Returns the listings whose price changed to another
    one (to re-score) and how many matches of the ones left without a price
    were deleted."""
    repriced: list[int] = []
    unpriced: list[int] = []
    async with db.connection() as cx:
        await listings_repo.mark_not_vehicle(cx, p.parts)
        for row, v in p.prices:
            pub, cur = _published(row)
            # Only if no crawl changed the price since it was read.
            cur_ = await cx.execute(
                "UPDATE listings SET price_published = %s, price_published_currency = %s, price = %s, "
                "       currency = %s, price_usd = %s, price_source = %s, price_partial = %s, "
                "       price_partial_reason = %s, description_facts = %s, "
                "       attributes = CASE WHEN %s THEN attributes - 'moneda' ELSE attributes END || %s "
                " WHERE id = %s AND status = 'active' "
                "   AND coalesce(price_published, price) IS NOT DISTINCT FROM %s "
                "   AND coalesce(price_published_currency, currency) IS NOT DISTINCT FROM %s",
                (v["price_published"], v["price_published_currency"], v["price"], v["currency"],
                 v["price_usd"], v["price_source"], v["price_partial"], v["price_partial_reason"],
                 Jsonb(v["description_facts"]) if v["description_facts"] is not None else None,
                 v["_drop_moneda"], Jsonb(v["attributes"]), row["id"], pub, cur))
            if cur_.rowcount:
                (unpriced if v["price"] is None else repriced).append(row["id"])
        # Without a price (partial) they match no search: their matches go
        # now, as a part's do. Deleting a match notifies nobody.
        gone = unpriced + p.stale
        deleted = (await cx.execute(
            "DELETE FROM matches m USING listings l "
            " WHERE m.listing_id = l.id AND l.id = ANY(%s) AND l.price IS NULL AND l.price_partial",
            (gone,))).rowcount if gone else 0
        async with cx.cursor() as cur:
            await cur.executemany(
                "UPDATE listings SET attributes = jsonb_set(attributes, '{moneda}', to_jsonb(%s::text)) "
                " WHERE id = %s", [(currency, lid) for lid, currency in p.monedas])
            # Only if no crawl changed the title since it was read.
            await cur.executemany("UPDATE listings SET title = %s WHERE id = %s AND title = %s",
                                  [(bare, lid, stored) for lid, stored, bare in p.titles])
        # Last: the price updates above only touch active listings.
        if p.card_gone:
            await cx.execute("UPDATE listings SET status = 'gone', detail_checked_at = now() "
                             " WHERE id = ANY(%s) AND status = 'active'", (p.card_gone,))
    return repriced, deleted


async def _stored_or_live_quote(cx) -> FxQuote:
    """Today's quote without storing it (quote_for_today stores the first one):
    a dry run writes nothing."""
    row = await (await cx.execute(
        "SELECT rate, kind, source FROM fx_rates WHERE date = %s ORDER BY kind = 'blue' DESC LIMIT 1",
        (today_ar(),))).fetchone()
    if row:
        return FxQuote(float(row["rate"]), row["kind"], row["source"])
    return await asyncio.to_thread(fx_repo.usd_ars_quote)


async def repair(*, write: bool, sources: list[str], examples: int = 5) -> Plan:
    async with db.connection() as cx:
        rows = await (await cx.execute(_SELECT, (sources,))).fetchall()
        fx = await quote_for_today(cx) if write else await _stored_or_live_quote(cx)
    p = plan(rows, fx, examples=examples)
    if write:
        repriced, deleted = await apply(p)
        if deleted:
            p.counts[("*", DELETED)] = deleted
        if repriced:
            p.counts[("*", RESCORED)] = await rescore_listings(repriced)
    return p


def report(p: Plan, *, write: bool) -> list[str]:
    lines = []
    for (source, what), n in sorted(p.counts.items()):
        lines.append(f"{source:<14} {what:<36} {n:>6}")
        lines += [f"    {e}" for e in p.examples.get((source, what), [])]
    if not p.counts:
        lines.append("nada que reparar")
    lines.append("listo" if write else "(simulación: no se escribió nada; --write para aplicar)")
    return lines


async def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="python -m tools.repair_facebook", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", default=True, help="solo contar (por defecto)")
    mode.add_argument("--write", action="store_true", help="aplicar los cambios")
    ap.add_argument("--source", action="append", help="fuente (repetible; por defecto facebook)")
    ap.add_argument("--examples", type=int, default=5, help="ejemplos por grupo")
    args = ap.parse_args(argv)

    await db.open_pool()
    try:
        p = await repair(write=args.write, sources=args.source or ["facebook"], examples=args.examples)
    finally:
        await db.close_pool()
    print("\n".join(report(p, write=args.write)))
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    sys.exit(run(main(sys.argv[1:])))

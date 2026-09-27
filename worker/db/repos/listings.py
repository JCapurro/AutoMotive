"""listings + listing_snapshots.

F0 keeps the bot's semantics: make/model are normalized like before (so
comparables bucket the same way) and an update refreshes price, km and the
partial-price flag. On top of that, `first_seen_at` is set once and a snapshot
is written when a listing is new or its price/km changed. Catalog-based
normalization, price_usd and the rest of sección 5.3 come in F1.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Iterable

from psycopg import AsyncConnection
from psycopg.types.json import Jsonb

from db.pool import connection
from normalization.normalize import normalize_brand, normalize_model, normalize_text


_CURRENCIES = {"USD", "ARS"}
_SELLER_TYPES = {"particular": "private", "concesionaria": "dealer", "dealer": "dealer"}


def _transmission(raw: str | None) -> str | None:
    t = normalize_text(raw)
    if not t:
        return None
    if "manual" in t:
        return "manual"
    if "autom" in t or "cvt" in t:
        return "automatic"
    return None


def listing_row(it: dict) -> dict[str, Any]:
    """Map a scraper Listing dict onto listings columns. Raw values that don't
    fit a column's domain are kept in `attributes`."""
    attributes = {k: it[k] for k in ("transmision", "vendedor", "moneda") if it.get(k)}
    published = it.get("published_at")
    moneda = (it.get("moneda") or "").upper() or None
    row = {
        "source": it["source"],
        "external_id": str(it["listing_id"]),
        "url": it["url"],
        "title": it["titulo"],
        "make": normalize_brand(it.get("marca")) or None,
        "model": normalize_model(it.get("modelo")) or None,
        "year": it.get("anio"),
        "price": it.get("precio"),
        "currency": moneda if moneda in _CURRENCIES else None,
        "mileage_km": it.get("km"),
        "transmission": _transmission(it.get("transmision")),
        "fuel": it.get("combustible"),
        "location_text": it.get("ubicacion"),
        "seller_type": _SELLER_TYPES.get(normalize_text(it.get("vendedor"))),
        "attributes": attributes,
        # ISO string: rows travel to Postgres as one JSON document.
        "published_at": (datetime.fromtimestamp(published, tz=timezone.utc).isoformat()
                         if published else None),
        "price_partial": bool(it.get("price_partial")),
        "price_partial_reason": it.get("price_partial_reason"),
    }
    key_attrs = {k: row[k] for k in ("title", "year", "fuel", "location_text", "seller_type")}
    key_attrs["raw"] = attributes
    row["attrs_hash"] = hashlib.md5(
        json.dumps(key_attrs, sort_keys=True, default=str).encode()
    ).hexdigest()
    return row


_COLUMNS = ("source", "external_id", "url", "title", "make", "model", "year", "price",
            "currency", "mileage_km", "transmission", "fuel", "location_text", "seller_type",
            "attributes", "published_at", "price_partial", "price_partial_reason", "attrs_hash")

_UPSERT_SQL = f"""
WITH v AS (
    SELECT * FROM jsonb_to_recordset(%s::jsonb) AS v (
        source text, external_id text, url text, title text, make text, model text,
        year int, price numeric, currency text, mileage_km int, transmission text, fuel text,
        location_text text, seller_type text, attributes jsonb, published_at timestamptz,
        price_partial boolean, price_partial_reason text, attrs_hash text)
),
old AS (
    SELECT l.id, l.price, l.currency, l.mileage_km
      FROM listings l JOIN v ON v.source = l.source AND v.external_id = l.external_id
),
up AS (
    INSERT INTO listings ({", ".join(c for c in _COLUMNS if c != "attrs_hash")})
    SELECT {", ".join(c for c in _COLUMNS if c != "attrs_hash")} FROM v
    ON CONFLICT (source, external_id) DO UPDATE SET
        price = excluded.price,
        currency = excluded.currency,
        mileage_km = excluded.mileage_km,
        price_partial = excluded.price_partial,
        price_partial_reason = excluded.price_partial_reason,
        last_seen_at = now(),
        status = 'active'
    RETURNING id, source, external_id, price, currency, mileage_km, (xmax = 0) AS inserted
)
INSERT INTO listing_snapshots (listing_id, price, currency, mileage_km, attrs_hash, change_kind)
SELECT up.id, up.price, up.currency, up.mileage_km, v.attrs_hash,
       CASE WHEN up.inserted THEN 'new'
            WHEN up.price IS DISTINCT FROM old.price
              OR up.currency IS DISTINCT FROM old.currency THEN 'price'
            ELSE 'mileage' END
  FROM up
  JOIN v ON v.source = up.source AND v.external_id = up.external_id
  LEFT JOIN old ON old.id = up.id
 WHERE up.inserted
    OR up.price IS DISTINCT FROM old.price
    OR up.currency IS DISTINCT FROM old.currency
    OR up.mileage_km IS DISTINCT FROM old.mileage_km
"""


async def upsert_listing_rows(cx: AsyncConnection, rows: list[dict[str, Any]]) -> None:
    if rows:
        await cx.execute(_UPSERT_SQL, (Jsonb(rows),))


async def upsert_listings(items: Iterable[dict]) -> None:
    """Upsert scraped listings in one transaction. Duplicates in the batch
    (the same ad returned by two search variants) collapse to the last one."""
    rows = {}
    for it in items:
        row = listing_row(it)
        rows[(row["source"], row["external_id"])] = row
    if not rows:
        return
    async with connection() as cx:
        await upsert_listing_rows(cx, list(rows.values()))


async def comparables(marca: str, modelo: str, anio: int | None,
                      anio_tol: int = 1, km: int | None = None, km_tol_pct: float = 25.0,
                      max_age_days: int = 30) -> list[dict]:
    """Listings comparable to (marca, modelo, anio[, km]) seen in the last
    `max_age_days`, with the keys the opportunity engine reads."""
    if not marca or not modelo:
        return []
    sql = (
        "SELECT source, external_id AS listing_id, make AS marca, model AS modelo, "
        "       year AS anio, mileage_km AS km, price::float AS precio, currency AS moneda, "
        "       title AS titulo, url "
        "  FROM listings "
        " WHERE make = %s AND model = %s "
        "   AND last_seen_at >= now() - make_interval(days => %s) "
        "   AND price > 0 "
        "   AND NOT price_partial"   # never bucket anticipos/cuotas as comparables
    )
    params: list[Any] = [normalize_brand(marca), normalize_model(modelo), max_age_days]
    if anio is not None:
        sql += " AND year BETWEEN %s AND %s"
        params += [anio - anio_tol, anio + anio_tol]
    if km is not None and km > 0:
        sql += " AND (mileage_km IS NULL OR mileage_km BETWEEN %s AND %s)"
        params += [int(km * (1 - km_tol_pct / 100)), int(km * (1 + km_tol_pct / 100))]
    async with connection() as cx:
        return await (await cx.execute(sql, params)).fetchall()

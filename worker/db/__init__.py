import sqlite3
import json
import time
from contextlib import contextmanager
from typing import Any, Iterable

from config import DB_PATH
from normalize import normalize_brand, normalize_model


SCHEMA = """
CREATE TABLE IF NOT EXISTS alerts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL,
    chat_id         INTEGER NOT NULL,
    name            TEXT NOT NULL,
    filters_json    TEXT NOT NULL,
    active          INTEGER NOT NULL DEFAULT 1,
    created_at      INTEGER NOT NULL,
    -- 0 until the alert has run once and seeded seen_listings (silent first run).
    bootstrapped    INTEGER NOT NULL DEFAULT 0,
    -- unix timestamp of the last completed scrape; used to gate the 6h cadence.
    last_scraped_at INTEGER
);

CREATE TABLE IF NOT EXISTS seen_listings (
    alert_id    INTEGER NOT NULL,
    source      TEXT NOT NULL,
    listing_id  TEXT NOT NULL,
    first_seen  INTEGER NOT NULL,
    PRIMARY KEY (alert_id, source, listing_id)
);

CREATE TABLE IF NOT EXISTS listings_cache (
    source                TEXT NOT NULL,
    listing_id            TEXT NOT NULL,
    marca                 TEXT,
    modelo                TEXT,
    anio                  INTEGER,
    km                    INTEGER,
    precio                REAL,
    moneda                TEXT,
    titulo                TEXT,
    url                   TEXT,
    ubicacion             TEXT,
    combustible           TEXT,
    transmision           TEXT,
    vendedor              TEXT,
    price_partial         INTEGER NOT NULL DEFAULT 0,
    price_partial_reason  TEXT,
    scraped_at            INTEGER NOT NULL,
    PRIMARY KEY (source, listing_id)
);

CREATE INDEX IF NOT EXISTS idx_cache_marca_modelo_anio
    ON listings_cache (marca, modelo, anio);
CREATE INDEX IF NOT EXISTS idx_alerts_active ON alerts (active);

CREATE TABLE IF NOT EXISTS geocode_cache (
    query       TEXT PRIMARY KEY,
    lat         REAL NOT NULL,
    lon         REAL NOT NULL,
    source      TEXT NOT NULL,
    updated_at  INTEGER NOT NULL,
    not_found   INTEGER NOT NULL DEFAULT 0
);
"""


def init_db() -> None:
    with connect() as cx:
        cx.executescript(SCHEMA)
        # Lightweight migrations for older DBs
        cols_lc = {r["name"] for r in cx.execute("PRAGMA table_info(listings_cache)").fetchall()}
        if "price_partial" not in cols_lc:
            cx.execute("ALTER TABLE listings_cache ADD COLUMN price_partial INTEGER NOT NULL DEFAULT 0")
        if "price_partial_reason" not in cols_lc:
            cx.execute("ALTER TABLE listings_cache ADD COLUMN price_partial_reason TEXT")
        cols_a = {r["name"] for r in cx.execute("PRAGMA table_info(alerts)").fetchall()}
        if "bootstrapped" not in cols_a:
            cx.execute("ALTER TABLE alerts ADD COLUMN bootstrapped INTEGER NOT NULL DEFAULT 0")
        if "last_scraped_at" not in cols_a:
            cx.execute("ALTER TABLE alerts ADD COLUMN last_scraped_at INTEGER")
        cols_g = {r["name"] for r in cx.execute("PRAGMA table_info(geocode_cache)").fetchall()}
        if "not_found" not in cols_g:
            cx.execute("ALTER TABLE geocode_cache ADD COLUMN not_found INTEGER NOT NULL DEFAULT 0")


@contextmanager
def connect():
    cx = sqlite3.connect(DB_PATH)
    cx.row_factory = sqlite3.Row
    try:
        yield cx
        cx.commit()
    finally:
        cx.close()


# -------- alerts --------

def create_alert(user_id: int, chat_id: int, name: str, filters: dict) -> int:
    with connect() as cx:
        cur = cx.execute(
            "INSERT INTO alerts (user_id, chat_id, name, filters_json, active, created_at) "
            "VALUES (?, ?, ?, ?, 1, ?)",
            (user_id, chat_id, name, json.dumps(filters, ensure_ascii=False), int(time.time())),
        )
        return cur.lastrowid


def list_alerts(user_id: int | None = None, only_active: bool = False) -> list[dict]:
    sql = "SELECT * FROM alerts"
    where, params = [], []
    if user_id is not None:
        where.append("user_id = ?")
        params.append(user_id)
    if only_active:
        where.append("active = 1")
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY id DESC"
    with connect() as cx:
        rows = cx.execute(sql, params).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["filters"] = json.loads(d.pop("filters_json"))
        out.append(d)
    return out


def get_alert(alert_id: int) -> dict | None:
    with connect() as cx:
        r = cx.execute("SELECT * FROM alerts WHERE id = ?", (alert_id,)).fetchone()
    if not r:
        return None
    d = dict(r)
    d["filters"] = json.loads(d.pop("filters_json"))
    return d


def set_alert_active(alert_id: int, active: bool) -> None:
    with connect() as cx:
        cx.execute("UPDATE alerts SET active = ? WHERE id = ?", (1 if active else 0, alert_id))


def delete_alert(alert_id: int) -> None:
    with connect() as cx:
        cx.execute("DELETE FROM alerts WHERE id = ?", (alert_id,))
        cx.execute("DELETE FROM seen_listings WHERE alert_id = ?", (alert_id,))


# -------- geocoding cache --------

def get_geocode_cache(query: str) -> tuple[float, float] | None:
    with connect() as cx:
        row = cx.execute(
            "SELECT lat, lon, not_found FROM geocode_cache WHERE query = ?",
            (query,),
        ).fetchone()
    if not row or row["not_found"]:
        return None
    return float(row["lat"]), float(row["lon"])


def set_geocode_cache(query: str, lat: float, lon: float, source: str) -> None:
    with connect() as cx:
        cx.execute(
            "INSERT INTO geocode_cache (query, lat, lon, source, updated_at, not_found) "
            "VALUES (?, ?, ?, ?, ?, 0) "
            "ON CONFLICT(query) DO UPDATE SET "
            "  lat=excluded.lat, lon=excluded.lon, source=excluded.source, "
            "  updated_at=excluded.updated_at, not_found=0",
            (query, lat, lon, source, int(time.time())),
        )


def set_geocode_cache_failure(query: str, source: str) -> None:
    """Cache that this query failed to geocode, so we don't keep retrying."""
    with connect() as cx:
        cx.execute(
            "INSERT INTO geocode_cache (query, lat, lon, source, updated_at, not_found) "
            "VALUES (?, 0, 0, ?, ?, 1) "
            "ON CONFLICT(query) DO UPDATE SET "
            "  source=excluded.source, updated_at=excluded.updated_at, not_found=1",
            (query, source, int(time.time())),
        )


def has_fresh_geocode_failure(query: str, max_age_days: int = 7) -> bool:
    """True if the query was tried and failed within the past `max_age_days`."""
    cutoff = int(time.time()) - max_age_days * 86400
    with connect() as cx:
        row = cx.execute(
            "SELECT 1 FROM geocode_cache "
            "WHERE query = ? AND not_found = 1 AND updated_at >= ?",
            (query, cutoff),
        ).fetchone()
    return bool(row)


def mark_scraped(alert_id: int, *, bootstrapped: bool | None = None) -> None:
    """Stamp last_scraped_at; optionally flip bootstrapped to True after the
    first silent run."""
    with connect() as cx:
        if bootstrapped is None:
            cx.execute("UPDATE alerts SET last_scraped_at = ? WHERE id = ?",
                       (int(time.time()), alert_id))
        else:
            cx.execute(
                "UPDATE alerts SET last_scraped_at = ?, bootstrapped = ? WHERE id = ?",
                (int(time.time()), 1 if bootstrapped else 0, alert_id),
            )


# -------- seen --------

def filter_unseen(alert_id: int, items: Iterable[dict]) -> list[dict]:
    items = list(items)
    if not items:
        return []
    with connect() as cx:
        keys = [(alert_id, it["source"], it["listing_id"]) for it in items]
        placeholders = ",".join(["(?,?,?)"] * len(keys))
        flat: list[Any] = [v for k in keys for v in k]
        rows = cx.execute(
            f"SELECT alert_id, source, listing_id FROM seen_listings "
            f"WHERE (alert_id, source, listing_id) IN ({placeholders})",
            flat,
        ).fetchall()
        seen = {(r["alert_id"], r["source"], r["listing_id"]) for r in rows}
    return [it for it in items if (alert_id, it["source"], it["listing_id"]) not in seen]


def mark_seen(alert_id: int, items: Iterable[dict]) -> None:
    rows = [(alert_id, it["source"], it["listing_id"], int(time.time())) for it in items]
    if not rows:
        return
    with connect() as cx:
        cx.executemany(
            "INSERT OR IGNORE INTO seen_listings (alert_id, source, listing_id, first_seen) "
            "VALUES (?, ?, ?, ?)",
            rows,
        )


# -------- cache --------

def upsert_listings(items: Iterable[dict]) -> None:
    """Normalize marca/modelo on write so comparables bucket consistently."""
    rows = []
    now = int(time.time())
    for it in items:
        rows.append((
            it["source"], it["listing_id"],
            normalize_brand(it.get("marca")) or None,
            normalize_model(it.get("modelo")) or None,
            it.get("anio"), it.get("km"),
            it.get("precio"), it.get("moneda"),
            it.get("titulo"), it.get("url"),
            it.get("ubicacion"), it.get("combustible"),
            it.get("transmision"), it.get("vendedor"),
            1 if it.get("price_partial") else 0,
            it.get("price_partial_reason"),
            now,
        ))
    if not rows:
        return
    with connect() as cx:
        cx.executemany(
            "INSERT INTO listings_cache "
            "(source, listing_id, marca, modelo, anio, km, precio, moneda, titulo, url, "
            " ubicacion, combustible, transmision, vendedor, price_partial, price_partial_reason, scraped_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT (source, listing_id) DO UPDATE SET "
            "  precio=excluded.precio, km=excluded.km, "
            "  price_partial=excluded.price_partial, "
            "  price_partial_reason=excluded.price_partial_reason, "
            "  scraped_at=excluded.scraped_at",
            rows,
        )


def comparables(marca: str, modelo: str, anio: int | None,
                anio_tol: int = 1, km: int | None = None, km_tol_pct: float = 25.0,
                max_age_days: int = 30) -> list[dict]:
    """Return cached listings comparable to (marca, modelo, anio[, km])."""
    if not marca or not modelo:
        return []
    cutoff = int(time.time()) - max_age_days * 86400
    sql = (
        "SELECT * FROM listings_cache "
        "WHERE marca = ? AND modelo = ? "
        "AND scraped_at >= ? AND precio IS NOT NULL AND precio > 0 "
        "AND price_partial = 0"   # never bucket anticipos/cuotas as comparables
    )
    params: list[Any] = [normalize_brand(marca), normalize_model(modelo), cutoff]
    if anio is not None:
        sql += " AND anio BETWEEN ? AND ?"
        params += [anio - anio_tol, anio + anio_tol]
    if km is not None and km > 0:
        lo = int(km * (1 - km_tol_pct / 100))
        hi = int(km * (1 + km_tol_pct / 100))
        sql += " AND (km IS NULL OR km BETWEEN ? AND ?)"
        params += [lo, hi]
    with connect() as cx:
        rows = cx.execute(sql, params).fetchall()
    return [dict(r) for r in rows]

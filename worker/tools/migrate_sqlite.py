"""
Copy the SQLite bot database into Supabase Postgres (docs/TECHNICAL_PLAN.md, sección 4.5).

Usage:
    python -m tools.migrate_sqlite <automotive.db> [--dry-run] [--database-url URL]
        [--email TELEGRAM_USER_ID=EMAIL ...] [--emails-file FILE] [--include-unknown]

    listings_cache → listings (+ one 'new' snapshot each; first_seen_at from scraped_at)
    alerts         → search_profiles, one per (marca, modelo) found in vehicle_catalog
    seen_listings  → matches with is_backfill = true, so nothing seen is notified again
    geocode_cache  → geocode_cache

Telegram users with an email (--email / --emails-file, CSV `telegram_user_id,email`
or a JSON object) get an auth user through the Supabase Admin API
(SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY). Users without one get the same
anonymous auth user the bot creates for new Telegram users.

Safe to re-run: rows that already exist are left alone. Everything happens in
one transaction; --dry-run runs the whole migration and rolls it back, so the
report shows real counts. (Admin API users are never created on --dry-run.)
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sqlite3
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from psycopg import AsyncConnection
from psycopg.types.json import Jsonb

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import config
from aio import run
from db.pool import connection_kwargs
from collectors.base import Listing
from db.repos.catalog import load_models
from db.repos.listings import COLUMNS
from db.repos.profiles import ensure_telegram_profile, insert_profiles
from normalization.listing import Target, attrs_hash, normalize_listing


def _ts(epoch: int | None) -> str | None:
    return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat() if epoch else None


def load_emails(pairs: list[str], path: str | None) -> dict[int, str]:
    emails: dict[int, str] = {}
    if path:
        text = Path(path).read_text(encoding="utf-8")
        if path.lower().endswith(".json"):
            emails.update({int(k): v for k, v in json.loads(text).items()})
        else:
            for row in csv.reader(text.splitlines()):
                if len(row) >= 2 and row[0].strip().isdigit():
                    emails[int(row[0])] = row[1].strip()
    for pair in pairs:
        tg, _, email = pair.partition("=")
        if not tg.strip().isdigit() or "@" not in email:
            raise SystemExit(f"--email espera TELEGRAM_USER_ID=EMAIL, recibí {pair!r}")
        emails[int(tg)] = email.strip()
    return emails


class Migration:
    def __init__(self, sqlite_path: str, cx: AsyncConnection, *, emails: dict[int, str],
                 dry_run: bool, include_unknown: bool,
                 supabase_url: str | None, service_key: str | None) -> None:
        self.lite = sqlite3.connect(f"file:{sqlite_path}?mode=ro", uri=True)
        self.lite.row_factory = sqlite3.Row
        self.cx = cx
        self.emails = emails
        self.dry_run = dry_run
        self.include_unknown = include_unknown
        self.supabase_url = (supabase_url or "").rstrip("/")
        self.service_key = service_key
        self.stats: Counter[str] = Counter()
        self.notes: list[str] = []

    def _table(self, name: str) -> list[sqlite3.Row]:
        exists = self.lite.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (name,)).fetchone()
        return self.lite.execute(f"SELECT * FROM {name}").fetchall() if exists else []

    async def run(self) -> None:
        await self.listings()
        alert_profiles = await self.alerts()
        await self.seen(alert_profiles)
        await self.geocode()

    def close(self) -> None:
        self.lite.close()

    # 1) listings_cache → listings + snapshot 'new'
    async def listings(self) -> None:
        """Normalized like any crawled listing (sección 5.2). ARS prices keep
        price_usd empty: today's rate would misstate a price seen months ago."""
        known = {r["id"] for r in await (await self.cx.execute("SELECT id FROM sources")).fetchall()}
        catalog = await load_models(self.cx)
        for r in self._table("listings_cache"):
            if r["source"] not in known:
                self.stats["listings_skipped_unknown_source"] += 1
                continue
            if not r["url"]:
                self.stats["listings_skipped_no_url"] += 1
                continue
            item = Listing(
                source=r["source"], listing_id=str(r["listing_id"]), url=r["url"],
                titulo=r["titulo"] or " ".join(filter(None, [r["marca"], r["modelo"]])) or r["listing_id"],
                precio=r["precio"], moneda=r["moneda"], anio=r["anio"], km=r["km"],
                ubicacion=r["ubicacion"], combustible=r["combustible"],
                transmision=r["transmision"], vendedor=r["vendedor"],
                price_partial=bool(r["price_partial"]),
                price_partial_reason=r["price_partial_reason"],
            )
            # The SQLite cache copied make/model from the alert: only a hint.
            row = normalize_listing(item, catalog=catalog, target=Target(r["marca"], r["modelo"]))
            seen_at = _ts(r["scraped_at"])
            cols = [c for c in COLUMNS if c in row]
            stored = await (await self.cx.execute(
                f"INSERT INTO listings ({', '.join(cols)}, first_seen_at, last_seen_at) "
                f"VALUES ({', '.join(['%s'] * len(cols))}, "
                "  coalesce(%s::timestamptz, now()), coalesce(%s::timestamptz, now())) "
                "ON CONFLICT (source, external_id) DO NOTHING RETURNING id",
                [Jsonb(row[c]) if c in ("images", "attributes") else row[c] for c in cols]
                + [seen_at, seen_at])).fetchone()
            if stored is None:
                self.stats["listings_already_present"] += 1
                continue
            await self.cx.execute(
                "INSERT INTO listing_snapshots (listing_id, observed_at, price, currency, price_usd, "
                "  mileage_km, attrs_hash, change_kind) "
                "VALUES (%s, coalesce(%s::timestamptz, now()), %s, %s, %s, %s, %s, 'new')",
                (stored["id"], seen_at, row["price"], row["currency"], row["price_usd"],
                 row["mileage_km"], attrs_hash(row)))
            self.stats["listings_inserted"] += 1

    # 2) alerts → profiles + search_profiles
    async def _user(self, telegram_user_id: int, chat_id: int) -> str:
        row = await (await self.cx.execute(
            "SELECT id FROM profiles WHERE telegram_user_id = %s", (telegram_user_id,))).fetchone()
        if row:
            self.stats["users_reused"] += 1
            return row["id"]
        email = self.emails.get(telegram_user_id)
        if not email:
            self.stats["users_created_anonymous"] += 1
            self.notes.append(f"telegram {telegram_user_id}: sin email, usuario anónimo")
            return await ensure_telegram_profile(self.cx, telegram_user_id, chat_id)

        row = await (await self.cx.execute(
            "SELECT id FROM auth.users WHERE lower(email) = lower(%s)", (email,))).fetchone()
        if row:
            user_id = row["id"]
            self.stats["users_reused"] += 1
        elif self.dry_run:
            self.stats["users_to_create_via_admin_api"] += 1
            self.notes.append(f"telegram {telegram_user_id}: se crearía {email} (Admin API)")
            return await ensure_telegram_profile(self.cx, telegram_user_id, chat_id)
        else:
            user_id = await self._create_auth_user(email, telegram_user_id)
            self.stats["users_created_via_admin_api"] += 1
        await self.cx.execute(
            "UPDATE profiles SET telegram_user_id = %s, telegram_chat_id = %s WHERE id = %s",
            (telegram_user_id, chat_id, user_id))
        return user_id

    async def _create_auth_user(self, email: str, telegram_user_id: int) -> str:
        if not (self.supabase_url and self.service_key):
            raise SystemExit("Crear usuarios con email necesita SUPABASE_URL y "
                             "SUPABASE_SERVICE_ROLE_KEY (o --supabase-url / --service-role-key)")
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.post(
                f"{self.supabase_url}/auth/v1/admin/users",
                headers={"apikey": self.service_key, "Authorization": f"Bearer {self.service_key}"},
                json={"email": email, "email_confirm": True,
                      "user_metadata": {"telegram_user_id": telegram_user_id}},
            )
        if r.status_code >= 400:
            raise SystemExit(f"Admin API rechazó {email}: {r.status_code} {r.text}")
        return r.json()["id"]

    async def alerts(self) -> dict[int, list[int]]:
        """Returns sqlite alert id → search_profile ids (new or from a previous run)."""
        out: dict[int, list[int]] = {}
        for a in self._table("alerts"):
            existing = await (await self.cx.execute(
                "SELECT id FROM search_profiles WHERE (preferences->>'sqlite_alert_id')::bigint = %s "
                "ORDER BY id", (a["id"],))).fetchall()
            if existing:
                out[a["id"]] = [r["id"] for r in existing]
                self.stats["profiles_already_migrated"] += len(existing)
                continue
            user_id = await self._user(a["user_id"], a["chat_id"])
            filters = json.loads(a["filters_json"])
            ids, skipped = await insert_profiles(
                self.cx, user_id, a["name"], filters,
                catalog_only=not self.include_unknown,
                enabled=bool(a["active"]),
                bootstrapped=bool(a["bootstrapped"]),
                extra_preferences={"sqlite_alert_id": a["id"]},
            )
            for make, model in skipped:
                self.notes.append(f"alerta #{a['id']}: {make} {model} no está en vehicle_catalog "
                                  "(usá --include-unknown para migrarla igual)")
            if ids:
                await self.cx.execute(
                    "UPDATE search_profiles SET created_at = coalesce(%s::timestamptz, created_at) "
                    "WHERE id = ANY(%s)",
                    (_ts(a["created_at"]), ids))
            out[a["id"]] = ids
            self.stats["profiles_created"] += len(ids)
            self.stats["profiles_skipped_not_in_catalog"] += len(skipped)
        return out

    # 3) seen_listings → matches (backfill)
    async def seen(self, alert_profiles: dict[int, list[int]]) -> None:
        alert_ids = {a["id"] for a in self._table("alerts")}
        self.stats["seen_of_deleted_alerts"] += sum(
            1 for r in self._table("seen_listings") if r["alert_id"] not in alert_ids)
        for alert_id, profile_ids in alert_profiles.items():
            seen = self.lite.execute(
                "SELECT source, listing_id, first_seen FROM seen_listings WHERE alert_id = ?",
                (alert_id,)).fetchall()
            if not seen or not profile_ids:
                continue
            sources = [r["source"] for r in seen]
            ext_ids = [r["listing_id"] for r in seen]
            seen_at = [_ts(r["first_seen"]) for r in seen]
            found = await (await self.cx.execute(
                "SELECT count(*) AS n FROM unnest(%s::text[], %s::text[]) AS v (source, external_id) "
                "JOIN listings l USING (source, external_id)", (sources, ext_ids))).fetchone()
            self.stats["seen_without_listing"] += len(seen) - found["n"]
            for profile_id in profile_ids:
                cur = await self.cx.execute(
                    "INSERT INTO matches (search_profile_id, listing_id, score, level, "
                    "  score_breakdown, match_reasons, is_backfill, scoring_version, generated_at) "
                    "SELECT %s, l.id, 0, 'low', '{}', '{}', true, 'legacy-v0', v.seen_at "
                    "  FROM unnest(%s::text[], %s::text[], %s::timestamptz[]) AS v (source, external_id, seen_at) "
                    "  JOIN listings l ON l.source = v.source AND l.external_id = v.external_id "
                    "ON CONFLICT (search_profile_id, listing_id) DO NOTHING",
                    (profile_id, sources, ext_ids, seen_at))
                self.stats["matches_inserted"] += cur.rowcount

    # 4) geocode_cache as is
    async def geocode(self) -> None:
        rows = [
            (r["query"], r["lat"], r["lon"], r["source"],
             bool(r["not_found"]) if "not_found" in r.keys() else False, _ts(r["updated_at"]))
            for r in self._table("geocode_cache")
        ]
        async with self.cx.cursor() as cur:
            for row in rows:
                await cur.execute(
                    "INSERT INTO geocode_cache (query, lat, lon, source, not_found, updated_at) "
                    "VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT (query) DO NOTHING", row)
                self.stats["geocode_inserted"] += cur.rowcount
        self.stats["geocode_already_present"] += len(rows) - self.stats["geocode_inserted"]


async def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("sqlite_path")
    ap.add_argument("--database-url", default=config.DATABASE_URL)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--email", action="append", default=[], metavar="TELEGRAM_USER_ID=EMAIL")
    ap.add_argument("--emails-file")
    ap.add_argument("--include-unknown", action="store_true",
                    help="also migrate (marca, modelo) combinations missing from vehicle_catalog")
    ap.add_argument("--supabase-url", default=os.getenv("SUPABASE_URL"))
    ap.add_argument("--service-role-key", default=os.getenv("SUPABASE_SERVICE_ROLE_KEY"))
    args = ap.parse_args()

    if not Path(args.sqlite_path).is_file():
        raise SystemExit(f"No existe {args.sqlite_path}")
    if not args.database_url:
        raise SystemExit("Falta DATABASE_URL (en .env o --database-url)")

    async with await AsyncConnection.connect(args.database_url,
                                             **connection_kwargs(args.database_url)) as cx:
        m = Migration(args.sqlite_path, cx, emails=load_emails(args.email, args.emails_file),
                      dry_run=args.dry_run, include_unknown=args.include_unknown,
                      supabase_url=args.supabase_url, service_key=args.service_role_key)
        try:
            await m.run()
        except BaseException:
            await cx.rollback()
            raise
        finally:
            m.close()
        if args.dry_run:
            await cx.rollback()
        else:
            await cx.commit()

    print("DRY RUN (rolled back)" if args.dry_run else "Migración aplicada")
    for key in sorted(m.stats):
        print(f"  {key:34} {m.stats[key]}")
    for note in m.notes:
        print(f"  · {note}")


if __name__ == "__main__":
    run(main())

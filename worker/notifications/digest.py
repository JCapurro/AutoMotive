"""Daily digest (§32, sección 7.2).

Every day at app_config.digest_hour (ART, default 20:00), per user and
channel, one 'digest' notification carrying:

  * every row waiting for it (status 'digest'): alerts of `daily` profiles,
    alerts degraded by the daily cap, listing_gone;
  * the top app_config.digest_top_n new matches of the last 24 h by score,
    whatever their level (below notify_min_level they are only seen in the
    web and here), skipping listings already alerted on that channel.

The rows it carries point to it (digested_in). Its dedupe key is
digest:<YYYY-MM-DD>, so running twice the same day (a restart) sends nothing
new; what arrives after it waits for the next one.
"""
from __future__ import annotations

import asyncio
import logging
import traceback
from datetime import datetime, timedelta, timezone
from typing import Any

import db
from db.repos import listings as listings_repo
from db.repos import notifications as repo
from db.repos.runs import log_error
from notifications.service import AR, Notifier, _min_n, deliverable, payload
from pipeline.rescore import seconds_until


log = logging.getLogger("digest")

SECTION = {"new_match": "matches", "opportunity": "matches", "price_drop": "price_drops",
           "listing_gone": "gone"}
WINDOW = timedelta(hours=24)


def build_items(pending: list[dict[str, Any]], top: list[dict[str, Any]], top_n: int) -> list[dict[str, Any]]:
    """Digest items from waiting rows and the day's top matches: waiting
    rows always go in; top matches fill up to `top_n` matches; a listing
    appears once per section. Highest score first."""
    items: list[dict[str, Any]] = []
    seen: set[tuple[str, int]] = set()
    for row in pending:
        section = SECTION.get(row["kind"])
        key = (section, row["listing_id"])
        if section is None or key in seen:
            continue
        seen.add(key)
        p = row["payload"] or {}
        items.append({"section": section, "listing_id": row["listing_id"], "kind": row["kind"],
                      "listing": p.get("listing"), "match": p.get("match"),
                      "price_drop": p.get("price_drop"), "degraded": p.get("degraded")})
    matches = [i for i in items if i["section"] == "matches"]
    for t in top:
        if len(matches) >= top_n:
            break
        key = ("matches", t["listing_id"])
        if key in seen:
            continue
        seen.add(key)
        item = {"section": "matches", "listing_id": t["listing_id"], "kind": "match",
                "listing": t["listing"], "match": t["match"]}
        items.append(item)
        matches.append(item)
    return sorted(items, key=lambda i: -((i.get("match") or {}).get("score") or 0))


async def run_digest(notifier: Notifier, now: datetime | None = None) -> int:
    """Build today's digests. Returns how many were created (then delivered)."""
    now = now or datetime.now(timezone.utc)
    day = now.astimezone(AR).date().isoformat()
    top_n = int(await db.get_config("digest_top_n", 10))
    min_n = await _min_n()
    created = 0
    for user in await repo.digest_users(now - WINDOW):
        for channel in deliverable(user["channels"] or (), user, notifier.available):
            try:
                pending = await repo.pending_digest(user["user_id"], channel)
                top = await repo.top_matches(user["user_id"], channel, now - WINDOW, top_n)
                if top:
                    async with db.connection() as cx:
                        rows = await listings_repo.rows_for_scoring(cx, [t["listing_id"] for t in top])
                    top = [{"listing_id": t["listing_id"],
                            **payload(rows[t["listing_id"]], t, min_n=min_n)} for t in top
                           if t["listing_id"] in rows]
                items = build_items(pending, top, top_n)
                if not items:
                    continue
                degraded = sum(1 for i in items if i.get("degraded"))
                digest_id = await repo.insert_digest(
                    user["user_id"], channel, day, {"date": day, "items": items, "degraded": degraded},
                    attach=[p["id"] for p in pending])
                if digest_id is not None:
                    created += 1
            except Exception:
                await log_error("digest", f"user:{user['user_id']}:{channel}", traceback.format_exc())
    if created:
        log.info("digest %s: %d created", day, created)
        await notifier.deliver()
    return created


async def digest_loop(notifier: Notifier, stop: asyncio.Event) -> None:
    """Run the digest every day at digest_hour. At startup, if today's hour
    already passed, catch up (a digest that was already sent is not repeated)."""
    first = True
    while not stop.is_set():
        hour = str(await db.get_config("digest_hour", "20:00"))
        now = datetime.now(AR)
        hh, mm = (int(x) for x in hour.split(":"))
        if not (first and now >= now.replace(hour=hh, minute=mm, second=0, microsecond=0)):
            try:
                await asyncio.wait_for(stop.wait(), timeout=seconds_until(hour, now))
                return
            except asyncio.TimeoutError:
                pass
        first = False
        try:
            await run_digest(notifier)
        except Exception:
            await log_error("digest", "loop", traceback.format_exc())

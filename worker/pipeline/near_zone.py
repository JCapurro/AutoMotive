"""Aviso de auto cerca de la zona (docs/AVISO_CERCA_DE_ZONA.md).

    searches with one zone, ≤ max_results results and no notice in cooldown_days
      → their make/model's recent listings (intelligence/near_zone.pick)
      → one email with the closest car that only the zone leaves out
        (notifications/near_zone.py), once per search and listing

Runs every NEAR_ZONE_TICK_SECONDS, inside send_from..send_until (Argentina);
app_config.near_zone rules the rest and ships off. Nothing for a zone its
owner kept with the zone notice's «Dejar así» (docs/AVISO_ZONA.md).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Mapping

import db
from db.repos import near_zone as repo
from db.repos.config import get_config
from db.repos.fx import quote_for_today
from db.repos.listings import recent_active
from intelligence import near_zone as nz
from notifications import near_zone as notice
from notifications.links import Links
from notifications.service import AR
from pipeline.low_results import zone_kept

log = logging.getLogger("near_zone")


def _profile(row: Mapping[str, Any]) -> dict[str, Any]:
    return {k: row.get(k) for k in ("id", "filters", "preferences", "origin_lat", "origin_lon", "radius_km",
                                     "seller_filter")}


async def run_near_zone(channel: Any, links: Links, *, now: datetime | None = None) -> int:
    """One pass. Returns how many emails went out. `channel` is the email channel or None."""
    cfg = nz.settings(await get_config("near_zone", {}))
    if not cfg["enabled"] or channel is None or not hasattr(channel, "send_message"):
        return 0
    now = now or datetime.now(timezone.utc)
    if not cfg["send_from"] <= now.astimezone(AR).time() < cfg["send_until"]:
        return 0
    rows = await repo.candidates(max_results=int(cfg["max_results"]), cooldown_days=cfg["cooldown_days"])
    rows = [r for r in rows if nz.eligible(_profile(r))]
    if not rows:
        return 0
    async with db.connection() as cx:
        fx_rate = (await quote_for_today(cx)).rate
    sent = 0
    for row in rows:
        if sent >= cfg["max_per_tick"]:
            break
        try:
            if await zone_kept(row):
                continue
            profile, f = _profile(row), row["filters"] or {}
            market = await recent_active(f.get("make"), f.get("model"), days=max(1, int(cfg["max_age_days"])))
            found = nz.pick(market, profile, created_at=row["created_at"], now=now, cfg=cfg, fx_rate=fx_rate,
                            seen=await repo.told(row["id"]))
            if found is None:
                continue
            listing, dist = found
            notice_id = await repo.claim(row["id"], row["user_id"], listing["id"], dist, row["radius_km"])
            if notice_id is None:
                continue
            result = await channel.send_message(row["email"], notice.email_message(row, listing, dist, links, now),
                                                idempotency_key=f"near-zone-{notice_id}",
                                                unsubscribe_token=row.get("unsubscribe_token"))
            await repo.mark(notice_id, sent=result.ok, error=result.error)
            if result.ok:
                sent += 1
                log.info("near_zone: profile=%s listing=%s a %.0f km (radio %.0f)", row["id"], listing["id"],
                         dist, row["radius_km"])
            else:
                log.warning("near_zone: email profile=%s: %s", row["id"], result.error)
        except Exception:
            log.exception("near_zone: profile=%s", row["id"])
    return sent

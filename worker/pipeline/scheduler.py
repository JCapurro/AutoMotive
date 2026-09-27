from __future__ import annotations
import asyncio
import logging
import time
import traceback

from html import escape as _html_escape

from telegram import Bot
from telegram.constants import ParseMode

import db
from config import (
    TICK_INTERVAL_SECONDS,
    ALERT_RESCRAPE_INTERVAL_SECONDS,
    RECOMMENDED_MAX_AGE_DAYS,
    SOURCES,
)
from collectors import REGISTRY
from collectors._loop import run_collector
from intelligence.opportunity import evaluate
from normalization.geo import filter_listings_by_radius

log = logging.getLogger("scheduler")


def _format_notification(alert_name: str, listing, score) -> str:
    """Build an HTML-formatted notification.

    HTML parse mode is used (not Markdown) because Mercado Libre URLs end in
    underscores like `_JM` which break legacy Markdown italics parsing.
    """
    e = _html_escape  # only <, >, & need escaping in HTML mode
    header = "⚠️ <b>Oportunidad sospechosa</b>" if score.suspect_partial else "🚨 <b>Oportunidad</b>"
    parts = [f"{header} — <i>{e(alert_name)}</i>", ""]
    if score.suspect_partial:
        parts.append("<i>Verificá que no sea anticipo / plan antes de contactar.</i>")
        parts.append("")
    parts.append(f"<b>{e(listing.titulo)}</b>")
    if listing.precio:
        parts.append(f"💰 {e(listing.moneda or '')} {int(listing.precio):,}".replace(",", "."))
    if listing.anio:
        parts.append(f"📅 {listing.anio}")
    if listing.km:
        parts.append(f"🛣 {listing.km:,} km".replace(",", "."))
    if listing.ubicacion:
        parts.append(f"📍 {e(listing.ubicacion)}")
    parts.append(f"🏷 {e(listing.source)}")
    if score.median and score.discount_pct is not None:
        parts.append(
            f"📉 {score.discount_pct:.1f}% bajo mediana "
            f"(USD {int(score.median):,} · n={score.sample_size})".replace(",", ".")
        )
    parts.append("")
    parts.append(f'🔗 <a href="{e(listing.url)}">{e(listing.url)}</a>')
    return "\n".join(parts)


def _price_ref(score) -> dict:
    """What the legacy engine concluded, kept on the match for later inspection."""
    return {
        "legacy": True,
        "is_opportunity": score.is_opportunity,
        "median_usd": score.median,
        "n": score.sample_size,
        "diff_pct": score.discount_pct,
        "reason": score.reason,
        "suspect_partial": score.suspect_partial,
    }


def _is_recent(listing, max_age_days: int) -> bool:
    """Drop listings published more than `max_age_days` ago.
    If the scraper couldn't infer a date, accept it — the seen_listings
    table + the per-alert bootstrap flag handle freshness for those."""
    if listing.published_at is None:
        return True
    return (int(time.time()) - listing.published_at) <= max_age_days * 86_400


def _expand_filters(f: dict) -> list[dict]:
    """Expand a multi-value alert filter into single-vehicle filter dicts.

    Cartesian product of `marcas` × `modelos`. The rest of the filters
    (km/precio/años/etc.) are copied to each variant. Falls back to the
    legacy singular `marca`/`modelo` keys for backward compat.
    """
    marcas = f.get("marcas") or ([f["marca"]] if f.get("marca") else [None])
    modelos = f.get("modelos") or ([f["modelo"]] if f.get("modelo") else [None])
    base = {k: v for k, v in f.items() if k not in ("marcas", "modelos", "marca", "modelo")}

    # If the user picked specific years, narrow the URL with min/max so the
    # source returns a tight superset; client-side matches_filters then
    # enforces exact membership in `anios`.
    anios = f.get("anios") or []
    if anios and not (base.get("anio_min") or base.get("anio_max")):
        base["anio_min"] = min(anios)
        base["anio_max"] = max(anios)

    out: list[dict] = []
    for marca in marcas:
        for modelo in modelos:
            v = dict(base)
            if marca: v["marca"] = marca
            if modelo: v["modelo"] = modelo
            out.append(v)
    return out or [dict(f)]


async def _run_one_source(alert_id: int, src: str, filters: dict) -> list:
    cls = REGISTRY.get(src)
    if not cls:
        return []
    variants = _expand_filters(filters)
    scraper = cls()
    out = []
    for v in variants:
        try:
            items = await run_collector(scraper.search(v))
            log.info("alert=%s src=%s variant=%s found=%d",
                     alert_id, src, f"{v.get('marca','*')}/{v.get('modelo','*')}", len(items))
            out.extend(items)
        except Exception:
            log.error("scraper %s failed: %s", src, traceback.format_exc())
    return out


async def _run_alert(bot: Bot, alert: dict) -> None:
    f = alert["filters"]
    sources = f.get("sources") or SOURCES
    bootstrapped = bool(alert.get("bootstrapped"))
    # All sources in parallel — different hosts so no contention.
    results = await asyncio.gather(
        *[_run_one_source(alert["id"], s, f) for s in sources],
        return_exceptions=False,
    )
    all_listings = [item for batch in results for item in batch]
    all_listings = await filter_listings_by_radius(all_listings, f)

    # 1) Cache everything (feeds the median for future opportunity calcs).
    if all_listings:
        await db.upsert_listings([l.to_dict() for l in all_listings])

    # 2) Find which of these are NEW for this alert.
    fresh = await db.filter_unseen(alert["id"], [l.to_dict() for l in all_listings])
    fresh_keys = {(x["source"], x["listing_id"]) for x in fresh}
    fresh_listings = [l for l in all_listings if (l.source, l.listing_id) in fresh_keys]

    # 3) On bootstrap (first run for this alert), mark all as seen and skip
    #    notifications — prevents flooding when the alert is created.
    if not bootstrapped:
        if fresh_listings:
            await db.mark_seen(alert["id"], [l.to_dict() for l in fresh_listings], backfill=True)
        await db.mark_scraped(alert["id"], bootstrapped=True)
        log.info("alert=%s BOOTSTRAP: marked %d as seen, no notifications",
                 alert["id"], len(fresh_listings))
        return

    # 4) Drop listings published outside the freshness window (when known).
    max_age_days = int(await db.get_config("recommended_max_age_days", RECOMMENDED_MAX_AGE_DAYS))
    recent_listings = [l for l in fresh_listings if _is_recent(l, max_age_days)]

    # 5) Score and notify. A listing another profile of this user already has
    #    (the same wizard alert split per model) is not notified twice.
    already_matched = await db.matched_by_other_profiles(
        alert["id"], [l.to_dict() for l in recent_listings])
    price_refs: dict[tuple[str, str], dict] = {}
    sent = 0
    for l in recent_listings:
        score = await evaluate(l, f)
        price_refs[(l.source, l.listing_id)] = _price_ref(score)
        if not score.is_opportunity or (l.source, l.listing_id) in already_matched:
            continue
        try:
            await bot.send_message(
                chat_id=alert["chat_id"],
                text=_format_notification(alert["name"], l, score),
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=False,
            )
            sent += 1
        except Exception as e:
            log.warning("send_message failed: %s", e)

    # 6) Mark all fresh as seen (even non-recent / non-opportunities) so we
    #    don't reconsider them next tick.
    if fresh_listings:
        await db.mark_seen(alert["id"], [l.to_dict() for l in fresh_listings],
                           price_refs=price_refs)
    await db.mark_scraped(alert["id"])
    log.info("alert=%s fresh=%d recent=%d notified=%d",
             alert["id"], len(fresh_listings), len(recent_listings), sent)


def _alert_is_due(alert: dict) -> bool:
    last = alert.get("last_scraped_at")
    if not last:
        return True   # never scraped → run now (covers fresh alerts)
    return (int(time.time()) - int(last)) >= ALERT_RESCRAPE_INTERVAL_SECONDS


async def run_loop(bot: Bot, stop_event: asyncio.Event) -> None:
    while not stop_event.is_set():
        try:
            alerts = await db.list_alerts(only_active=True)
            due = [a for a in alerts if _alert_is_due(a)]
            log.info("scheduler tick: %d active alerts, %d due", len(alerts), len(due))
            for a in due:
                if stop_event.is_set():
                    break
                try:
                    await _run_alert(bot, a)
                except Exception:
                    log.error("alert run failed: %s", traceback.format_exc())
        except Exception:
            log.error("scheduler tick failed: %s", traceback.format_exc())
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=TICK_INTERVAL_SECONDS)
        except asyncio.TimeoutError:
            pass

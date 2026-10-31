"""fx_rates: the day's USD/ARS quote, frozen so price_usd can be reproduced (sección 14)."""
from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta, timezone

from psycopg import AsyncConnection

from normalization.fx import FxQuote, usd_ars_quote


# America/Argentina/Buenos_Aires without depending on tzdata (no DST since 2009).
_AR = timezone(timedelta(hours=-3))


def today_ar() -> date:
    return datetime.now(_AR).date()


async def quote_for_today(cx: AsyncConnection) -> FxQuote:
    """The quote stored for today (blue, else oficial), fetching and storing it
    on first use. The hardcoded fallback is used but never stored, so a later
    call the same day can still freeze the real quote."""
    day = today_ar()
    row = await (await cx.execute(
        "SELECT rate, kind, source FROM fx_rates WHERE date = %s "
        "ORDER BY kind = 'blue' DESC LIMIT 1", (day,))).fetchone()
    if row:
        return FxQuote(float(row["rate"]), row["kind"], row["source"])
    quote = await asyncio.to_thread(usd_ars_quote)
    if quote.kind:
        await cx.execute(
            "INSERT INTO fx_rates (date, kind, rate, source) VALUES (%s, %s, %s, %s) "
            "ON CONFLICT (date, kind) DO NOTHING",
            (day, quote.kind, quote.rate, quote.source))
    return quote


async def latest_stored(cx: AsyncConnection) -> dict | None:
    """PAR-01: the latest stored quote, {rate, kind, date}: the most recent
    blue row, else the most recent oficial one (never "date desc, blue
    first", which lets today's oficial beat yesterday's blue). No network and
    never the hardcoded fallback; the age limit (cost_estimator.fx.max_age_days)
    is cost_estimator.build_input's."""
    for kind in ("blue", "oficial"):
        row = await (await cx.execute(
            "SELECT rate, kind, date FROM fx_rates WHERE kind = %s ORDER BY date DESC LIMIT 1", (kind,))).fetchone()
        if row and row["rate"] and float(row["rate"]) > 0:
            return {"rate": float(row["rate"]), "kind": row["kind"], "date": row["date"].isoformat()}
    return None


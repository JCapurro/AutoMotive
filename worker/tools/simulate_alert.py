"""
Simulate the arrival of a listing: what the crawl does with a new listing of
a target's batch, from matching on (sección 6 → sección 7).

The listing must already be in `listings`. Every enabled search of its make
and model scores it; the new matches go through the notification engine
(decision, dedupe, daily cap) and are delivered. Only the web inbox by
default, so nothing leaves the machine; the web shows it through Realtime.
Used by the web's e2e tests ("llega una alerta simulada") and for QA.

Usage (from worker/):
    python -m tools.simulate_alert <listing_id>
    python -m tools.simulate_alert <listing_id> --json
"""
from __future__ import annotations

import argparse
import json
import logging
import sys

import db
from aio import run
from config import WEB_BASE_URL
from notifications.channels.web import WebChannel
from notifications.links import Links
from notifications.service import Notifier
from pipeline.scheduler import process_batch


async def simulate(listing_id: int) -> list[dict]:
    """Returns the notifications the listing produced."""
    async with db.connection() as cx:
        listing = await (await cx.execute(
            "SELECT id, source, make, model FROM listings WHERE id = %s", (listing_id,))).fetchone()
    if listing is None:
        raise SystemExit(f"listing {listing_id} no existe")
    target = {"id": None, "source": listing["source"], "make": listing["make"], "model": listing["model"]}
    notifier = Notifier({"web": WebChannel(Links(WEB_BASE_URL))})
    await process_batch(notifier, target, [listing_id], first_run=False)
    async with db.connection() as cx:
        return await (await cx.execute(
            "SELECT id, user_id::text AS user_id, kind::text AS kind, channel::text AS channel, "
            "       status::text AS status FROM notifications WHERE listing_id = %s ORDER BY id",
            (listing_id,))).fetchall()


async def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("listing_id", type=int)
    p.add_argument("--json", action="store_true", help="imprimir las notificaciones como JSON")
    args = p.parse_args(argv)

    await db.open_pool()
    try:
        rows = await simulate(args.listing_id)
    finally:
        await db.close_pool()

    if args.json:
        print(json.dumps(rows, ensure_ascii=False))
    elif not rows:
        print("ninguna notificación (¿no matchea ninguna búsqueda, ya se avisó o está debajo del nivel mínimo?)")
    else:
        for r in rows:
            print(f"#{r['id']} {r['kind']} · {r['channel']} · {r['status']} · user {r['user_id']}")
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    sys.exit(run(main()))

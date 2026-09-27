"""Minimal /r/<notification_id> endpoint (sección 7.3) until the web exists.

    python -m tools.redirect_server            # REDIRECT_HOST:REDIRECT_PORT (127.0.0.1:8787)

GET /r/<id>?to=listing|detail[&l=<listing_id>] records the click through
public.track_notification_click (clicked_at, opened_at if empty, event
alert_clicked) and answers 302 to the listing at its source, or to
WEB_DETAIL_URL for to=detail once the web has a detail page. The Next.js
route handler of F4 replaces it calling the same SQL function.

It runs apart from the worker (the worker only makes outbound connections,
sección 2): expose it behind a tunnel or a reverse proxy and set
WEB_BASE_URL to its public URL.

Link-preview crawlers (Telegram fetches the first link of a message to draw
its preview) and HEAD requests are redirected without counting as a click.
"""
from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from urllib.parse import parse_qs, urlsplit

import db
from aio import run
from config import REDIRECT_HOST, REDIRECT_PORT, WEB_DETAIL_URL
from db.repos import notifications as repo


log = logging.getLogger("redirect")

_PATH = re.compile(r"/r/(\d+)/?")
_BOTS = re.compile(r"telegrambot|twitterbot|facebookexternalhit|slackbot|whatsapp|discordbot|"
                   r"googlebot|bingbot|linkedinbot|preview", re.I)


@dataclass(frozen=True)
class Response:
    status: int
    location: str | None = None


def is_preview(user_agent: str | None) -> bool:
    return bool(user_agent and _BOTS.search(user_agent))


def destination(row: dict, to: str, detail_url: str = WEB_DETAIL_URL) -> str:
    if to == "detail" and detail_url:
        return detail_url.format(listing_id=row["listing_id"])
    return row["url"]


async def resolve(method: str, target: str, user_agent: str | None = None, *,
                  detail_url: str = WEB_DETAIL_URL) -> Response:
    if method not in ("GET", "HEAD"):
        return Response(405)
    parts = urlsplit(target)
    if parts.path in ("/", "/healthz"):
        return Response(200)
    m = _PATH.fullmatch(parts.path)
    if not m:
        return Response(404)
    q = parse_qs(parts.query)
    to = q.get("to", ["listing"])[0]
    to = to if to in ("listing", "detail") else "listing"
    listing = q.get("l", [""])[0]
    listing_id = int(listing) if listing.isdigit() else None
    if method == "HEAD" or is_preview(user_agent):
        row = await repo.peek_click(int(m.group(1)), listing_id)
    else:
        row = await repo.track_click(int(m.group(1)), to, listing_id)
    if row is None:
        return Response(404)
    return Response(302, destination(row, to, detail_url))


_REASON = {200: "OK", 302: "Found", 400: "Bad Request", 404: "Not Found",
           405: "Method Not Allowed", 500: "Internal Server Error"}


async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    try:
        request_line = (await reader.readline()).decode("latin-1").strip()
        headers: dict[str, str] = {}
        while (line := await reader.readline()) not in (b"\r\n", b"\n", b""):
            name, _, value = line.decode("latin-1").partition(":")
            headers[name.strip().lower()] = value.strip()
        parts = request_line.split(" ")
        if len(parts) != 3:
            response = Response(400)
        else:
            try:
                response = await resolve(parts[0], parts[1], headers.get("user-agent"))
            except Exception:
                log.exception("redirect %s failed", parts[1])
                response = Response(500)
        head = [f"HTTP/1.1 {response.status} {_REASON[response.status]}",
                "Content-Length: 0", "Connection: close", "Cache-Control: no-store"]
        if response.location:
            head.append(f"Location: {response.location}")
        writer.write(("\r\n".join(head) + "\r\n\r\n").encode("latin-1", "replace"))
        await writer.drain()
    finally:
        writer.close()


async def serve(host: str = REDIRECT_HOST, port: int = REDIRECT_PORT) -> None:
    await db.open_pool()
    server = await asyncio.start_server(handle, host, port)
    log.info("redirect server on http://%s:%s/r/<id>", host, port)
    try:
        async with server:
            await server.serve_forever()
    finally:
        await db.close_pool()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    run(serve())

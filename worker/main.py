from __future__ import annotations
import asyncio
import logging
import signal

from telegram.ext import Application

from config import (EMAIL_FROM, ENRICH_TICK_SECONDS, HEARTBEAT_SECONDS, LOG_FILE, LOG_KEEP_DAYS,
                    NOTIFY_TICK_SECONDS, RESEND_API_KEY, TELEGRAM_ADMIN_CHAT_ID, TELEGRAM_ENABLED, TELEGRAM_TOKEN,
                    WATCHLIST_TICK_SECONDS, WEB_BASE_URL, startup_warnings)
import db
from bot.handlers import register
from llm import build_provider
from notifications.channels.email import ResendEmailChannel
from notifications.channels.telegram import TelegramChannel
from notifications.digest import digest_loop
from notifications.links import Links
from notifications.ops import SourceAlerts
from notifications.service import Notifier
from pipeline import heartbeat
from pipeline.enrich import enrich_pass
from pipeline.llm_jobs import llm_jobs_loop
from pipeline.rescore import nightly_loop
from pipeline.scheduler import run_loop
from pipeline.watchlist import refresh_watchlist
from collectors._browser import shutdown as browser_shutdown
from collectors._loop import run_collector
from aio import run


def setup_logging() -> None:
    """stdout, plus LOG_FILE (UTF-8, rotated at midnight, LOG_KEEP_DAYS kept)."""
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    if LOG_FILE:
        from logging.handlers import TimedRotatingFileHandler
        from pathlib import Path

        Path(LOG_FILE).parent.mkdir(parents=True, exist_ok=True)
        handlers.append(TimedRotatingFileHandler(LOG_FILE, when="midnight", backupCount=LOG_KEEP_DAYS,
                                                 encoding="utf-8"))
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s",
                        handlers=handlers)


setup_logging()
# At INFO httpx logs every request URL, and Telegram's include the bot token.
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("main")


async def _every(name: str, seconds: int, job, stop: asyncio.Event) -> None:
    """Run `job(stop)` now and then every `seconds` until stopped; errors are logged."""
    while not stop.is_set():
        try:
            await job(stop)
        except Exception:
            log.exception("%s failed", name)
        try:
            await asyncio.wait_for(stop.wait(), timeout=seconds)
        except asyncio.TimeoutError:
            pass


def build_notifier(bot, links: Links) -> Notifier:
    """The channels this worker can deliver on (sección 7.2)."""
    channels = {}
    if bot is not None:
        channels["telegram"] = TelegramChannel(bot, links)
    if RESEND_API_KEY and EMAIL_FROM:
        channels["email"] = ResendEmailChannel(RESEND_API_KEY, EMAIL_FROM, links)
    return Notifier(channels)


def notifying(job, notifier: Notifier):
    """A refresh pass whose price_drop / listing_gone events go to the engine."""
    async def run(stop: asyncio.Event) -> None:
        result = await job(stop)
        await notifier.on_listing_events(result.events)
        await notifier.deliver()
    return run


async def amain() -> None:
    if TELEGRAM_ENABLED and not TELEGRAM_TOKEN:
        raise SystemExit("TELEGRAM_TOKEN no está seteado en .env")

    await db.open_pool()

    links = Links(WEB_BASE_URL)
    app = Application.builder().token(TELEGRAM_TOKEN).build() if TELEGRAM_ENABLED else None
    if app is not None:
        register(app, links)
    notifier = build_notifier(app.bot if app else None, links)
    source_alerts = SourceAlerts(app.bot, TELEGRAM_ADMIN_CHAT_ID, WEB_BASE_URL) if app else None
    for warning in startup_warnings():
        log.warning(warning)

    if app is not None:
        await app.initialize()
        await app.start()
        await app.updater.start_polling(drop_pending_updates=True)
        log.info("bot iniciado")
    else:
        log.info("worker iniciado: alertas por email")

    stop = asyncio.Event()

    def _stop(*_):
        log.info("apagando…")
        stop.set()

    try:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, _stop)
            except NotImplementedError:
                # Windows: signals don't bind to event loop, fallback below
                signal.signal(sig, lambda *_: _stop())
    except Exception:
        pass

    started_at = heartbeat.started_now()
    tasks = [
        asyncio.create_task(_every("heartbeat", HEARTBEAT_SECONDS,
                                   lambda _stop: heartbeat.beat(started_at), stop)),
        asyncio.create_task(run_loop(notifier, stop, source_alerts.on_health if source_alerts else None)),
        asyncio.create_task(_every("enrichment", ENRICH_TICK_SECONDS,
                                   notifying(enrich_pass, notifier), stop)),
        asyncio.create_task(_every("watchlist", WATCHLIST_TICK_SECONDS,
                                   notifying(refresh_watchlist, notifier), stop)),
        asyncio.create_task(_every("notifications", NOTIFY_TICK_SECONDS,
                                   lambda _stop: notifier.deliver(), stop)),
        asyncio.create_task(digest_loop(notifier, stop)),
        asyncio.create_task(nightly_loop(stop)),
        asyncio.create_task(llm_jobs_loop(build_provider(), stop)),
    ]

    try:
        await stop.wait()
    finally:
        for task in tasks:
            task.cancel()
        for task in tasks:
            try:
                await task
            except asyncio.CancelledError:
                pass
        if app is not None:
            await app.updater.stop()
            await app.stop()
            await app.shutdown()
        await run_collector(browser_shutdown())
        await db.close_pool()
        log.info("bye")


if __name__ == "__main__":
    run(amain())

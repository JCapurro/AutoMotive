from __future__ import annotations
import asyncio
import logging
import signal

from telegram.ext import Application

from config import TELEGRAM_TOKEN
import db
from bot.handlers import register
from scheduler import run_loop


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("main")


async def amain() -> None:
    if not TELEGRAM_TOKEN:
        raise SystemExit("TELEGRAM_TOKEN no está seteado en .env")

    db.init_db()

    app = Application.builder().token(TELEGRAM_TOKEN).build()
    register(app)

    await app.initialize()
    await app.start()
    await app.updater.start_polling(drop_pending_updates=True)
    log.info("bot iniciado")

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

    scheduler_task = asyncio.create_task(run_loop(app.bot, stop))

    try:
        await stop.wait()
    finally:
        scheduler_task.cancel()
        try:
            await scheduler_task
        except asyncio.CancelledError:
            pass
        await app.updater.stop()
        await app.stop()
        await app.shutdown()
        log.info("bye")


if __name__ == "__main__":
    asyncio.run(amain())

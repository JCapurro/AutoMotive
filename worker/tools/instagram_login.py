"""Save a manually authenticated Instagram session for the two collectors.

From worker/: python -m tools.instagram_login
Login in the opened browser yourself, then press Enter here. No password is
read or stored by this script. The session file is a secret; keep it local.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

from playwright.async_api import async_playwright
from config import INSTAGRAM_STORAGE_STATE, ROOT


async def main() -> None:
    path = Path(INSTAGRAM_STORAGE_STATE or ROOT / "ig_state.json")
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=False)
        try:
            context = await browser.new_context(locale="es-AR")
            page = await context.new_page()
            await page.goto("https://www.instagram.com/accounts/login/", wait_until="domcontentloaded")
            await asyncio.to_thread(input, "Iniciá sesión en el navegador y presioná Enter para guardar: ")
            if not any(c["name"] == "sessionid" for c in await context.cookies("https://www.instagram.com")):
                raise SystemExit("No hay una sesión autenticada; no se guardó ningún archivo.")
            path.parent.mkdir(parents=True, exist_ok=True)
            await context.storage_state(path=str(path))
            print(f"Sesión local guardada en {path}. Configurá INSTAGRAM_STORAGE_STATE y probá ambos collectors.")
        finally:
            await browser.close()


if __name__ == "__main__":
    asyncio.run(main())

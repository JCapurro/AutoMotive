"""Save a manually authenticated Instagram session for the two collectors.

From worker/: python -m tools.instagram_login
Login in installed Chrome yourself, then press Enter here. Chrome keeps a
dedicated profile between attempts. Playwright connects only after the manual
login to export the session. No password is read or stored by this script.
The session file is a secret; keep it local.
"""
from __future__ import annotations

import asyncio
import os
import shutil
import socket
import subprocess
from pathlib import Path
from urllib.parse import urlparse

from playwright.async_api import async_playwright
from config import INSTAGRAM_STORAGE_STATE, ROOT


PROFILE = ROOT / ".ig_chrome_profile"


def chrome_executable() -> str:
    for name in ("google-chrome", "google-chrome-stable", "chrome"):
        if executable := shutil.which(name):
            return executable
    for base in (os.getenv("PROGRAMFILES"), os.getenv("PROGRAMFILES(X86)"), os.getenv("LOCALAPPDATA")):
        if base:
            executable = Path(base) / "Google" / "Chrome" / "Application" / "chrome.exe"
            if executable.is_file():
                return str(executable)
    raise SystemExit("No se encontró Google Chrome instalado para abrir el login manual.")


def launch_chrome(profile: Path, url: str) -> tuple[subprocess.Popen, str]:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    process = subprocess.Popen([
        chrome_executable(), f"--user-data-dir={profile.resolve()}",
        f"--remote-debugging-port={port}", "--remote-debugging-address=127.0.0.1",
        "--no-first-run", "--no-default-browser-check", url,
    ])
    return process, f"http://127.0.0.1:{port}"


async def save_session(context, path: Path) -> None:
    instagram_pages = [page for page in context.pages
                       if urlparse(page.url).hostname in {"instagram.com", "www.instagram.com"}]
    if not instagram_pages or any(
        part in urlparse(page.url).path for page in instagram_pages
        for part in ("/accounts/login", "/challenge", "/checkpoint")
    ):
        raise SystemExit("El login o la verificación siguen pendientes; no se guardó la sesión.")
    if not any(c["name"] == "sessionid" and c.get("value")
               for c in await context.cookies("https://www.instagram.com")):
        raise SystemExit("No hay una sesión autenticada; no se guardó ningún archivo.")
    path.parent.mkdir(parents=True, exist_ok=True)
    await context.storage_state(path=str(path))


async def main() -> None:
    path = Path(INSTAGRAM_STORAGE_STATE or ROOT / "ig_state.json")
    process, endpoint = launch_chrome(PROFILE, "https://www.instagram.com/accounts/login/")
    try:
        await asyncio.to_thread(input, "Iniciá sesión en Chrome y completá la verificación manual. "
                                "Cuando veas tu inicio de Instagram, presioná Enter para guardar: ")
        async with async_playwright() as playwright:
            try:
                browser = await playwright.chromium.connect_over_cdp(endpoint, timeout=15_000)
            except Exception as exc:
                raise SystemExit("No se pudo conectar al Chrome de login. Cerrá la ventana anterior "
                                 "del helper y ejecutá el comando nuevamente.") from exc
            try:
                await save_session(browser.contexts[0], path)
                print(f"Sesión local guardada en {path}. Configurá INSTAGRAM_STORAGE_STATE y probá ambos collectors.")
            finally:
                await browser.close()
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


if __name__ == "__main__":
    asyncio.run(main())

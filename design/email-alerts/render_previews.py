"""Build local HTML examples without credentials, database reads or email sends.

From the repository root (worker requirements + Playwright Chromium installed):
  python design/email-alerts/render_previews.py

Photos come from public URLs already recorded in parser fixtures. Sample prices,
km and scores below are illustrative; they are not current offers. Network access
is only needed for the preview photos, never by the production email renderer.
"""
from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "worker"))

from notifications.channels.base import Notification
from notifications.email_assets import LOGO_CONTENT_ID, logo_attachment
from notifications.links import Links
from notifications.templates import email
from playwright.sync_api import sync_playwright

OUT = Path(__file__).resolve().parent
NOW = datetime(2026, 10, 9, 15, 30, tzinfo=timezone.utc)
LINKS = Links("https://eseauto.example")  # Never link sample notification IDs to live users.
PHOTOS = [
    "https://www.rosariogarage.com/resources_production/gallery//uploads_files/2026/05/08/5645199/5645199-20260508080535.jpeg",
    "https://www.rosariogarage.com/resources_production/gallery//uploads_files/2026/05/08/5645199/5645199-20260508080537.jpeg",
    "https://www.rosariogarage.com/resources_production/gallery//uploads_files/2026/05/08/5645199/5645199-20260508080539.jpeg",
]
ECOSPORT = "https://acroadtrip.blob.core.windows.net/publicaciones-imagenes/Small/ford/ecosport/ar/RT_PU_c273b5c3c5b24c0c916875b9546f9e15.webp"
CAR = {"id": 501, "title": "Ford Fiesta SE", "make": "Ford", "model": "Fiesta", "trim": "SE",
       "year": 2018, "mileage_km": 98000, "price": 10900, "currency": "USD",
       "location_text": "Rosario, Santa Fe", "source": "rosariogarage", "url": "https://source.example/501",
       "published_at": (NOW - timedelta(minutes=8)).isoformat(), "images": PHOTOS}


def preview(kind, payload, *, id=42, listing_id=501):
    n = Notification(id=id, user_id="example", kind=kind, channel="email", payload=payload,
                     listing_id=listing_id, unsubscribe_token="example-token")
    return email(n, LINKS, NOW)


def main():
    with tempfile.TemporaryDirectory() as temp:
        embedded = {}
        for i, url in enumerate([*PHOTOS, ECOSPORT]):
            path = Path(temp) / f"photo-{i}"
            subprocess.run(["curl", "--fail", "--location", "--silent", "--show-error", "--max-time", "30",
                            url, "-o", str(path)], check=True)
            mime = "image/webp" if url.endswith("webp") else "image/jpeg"
            embedded[url] = f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode()
    opportunity = preview("opportunity", {"listing": CAR, "profile_name": "Mi próximo auto",
                          "match": {"score": 88, "level": "high", "diff_pct": 8.2}})
    digest = preview("digest", {"date": "2026-10-09", "items": [
        {"section": "matches", "listing_id": 501, "listing": CAR, "match": {"score": 88, "level": "high"}},
        {"section": "price_drops", "listing_id": 502, "listing": {
            **CAR, "id": 502, "model": "EcoSport", "trim": "S 1.5", "year": 2019,
            "mileage_km": 82000, "price": 13500, "location_text": "Córdoba, Córdoba",
            "source": "autocosmos", "images": [ECOSPORT]},
         "price_drop": {"old_price": 14500, "new_price": 13500, "currency": "USD", "drop_pct": 6.9}},
    ]}, id=43, listing_id=None)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        for name, message in (("oportunidad", opportunity), ("resumen-diario", digest)):
            html = message.html.replace(f"cid:{LOGO_CONTENT_ID}", "data:image/png;base64," + logo_attachment()["content"])
            for url, image in embedded.items():
                html = html.replace(url, image)
            path = OUT / f"{name}.html"
            path.write_text(html, encoding="utf-8")
            for width in (390, 800):
                page = browser.new_page(viewport={"width": width, "height": 900}, device_scale_factor=1)
                page.goto(path.as_uri())
                page.evaluate("Promise.all([...document.images].map(i => i.decode().catch(() => {})))")
                state = page.evaluate("({width:innerWidth, content:document.documentElement.scrollWidth, images:[...document.images].every(i=>i.naturalWidth>0)})")
                assert state["images"] and state["content"] <= width, state
                page.screenshot(path=str(OUT / f"{name}-{width}.png"), full_page=True)
                print(name, width, state)
                page.close()
        browser.close()


if __name__ == "__main__":
    main()

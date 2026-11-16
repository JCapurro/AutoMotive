"""Finding a prospect's WhatsApp when it is not in the listing's text.

* RosarioGarage: the listing page shows the seller's own WhatsApp link.
* A business (kind 'agencia'): its public WhatsApp, from its own site,
  Instagram, Facebook page or Google Maps, through `claude -p` with web search.
* A person without a business: never. Only the number they wrote in their own
  listing counts (sellers.phone_from_listings).

deRuedas hides the number behind a code sent to the visitor's phone, so its
page is not read.
"""
from __future__ import annotations

import json
import re
import time
from typing import Any, Callable

import httpx

from prospector import claude, phones
from prospector.sellers import SOURCE_LABEL, Prospect

LOOKUP_MODEL = "claude-sonnet-5-5"
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/130.0 Safari/537.36",
    "Accept-Language": "es-AR,es;q=0.9",
}


def rosariogarage(prospect: Prospect, *, get=None) -> tuple[str, str] | None:
    """(number, page URL) from the first RosarioGarage listing page that shows it."""
    get = get or (lambda url: httpx.get(url, headers=_HEADERS, timeout=30, follow_redirects=True))
    urls = [r["url"] for r in prospect.listings if r["source"] == "rosariogarage" and r.get("url")]
    for url in urls[:2]:
        try:
            resp = get(url)
        except httpx.HTTPError:
            continue
        if resp.status_code == 200:
            number = phones.from_rosariogarage_page(resp.text)
            if number:
                return number, url
    return None


# Mercado Libre's item page says whether the seller turned on its WhatsApp button
# («"action_type":"WHATSAPP"» in the page state). The number only comes out when a person
# taps it (a call guarded by reCAPTCHA), so the bot never asks for it: Juan opens the
# listing on his phone, taps WhatsApp and pastes the message. The button is the seller's
# own channel, so it counts for a person too.
_ML_WHATSAPP = re.compile(r'"action_type"\s*:\s*"WHATSAPP"')
_ML_AVAILABLE = re.compile(r'"whatsapp_available"\s*:\s*true')


def ml_button_page(html: str, url: str, status: int) -> bool:
    """Whether this ML item page is live and shows the seller's WhatsApp button."""
    from collectors.mercadolibre import parse_detail
    try:
        if parse_detail(html, url, status).gone:
            return False
    except Exception:
        return False
    return bool(_ML_WHATSAPP.search(html) and _ML_AVAILABLE.search(html))


def ml_button(prospect: Prospect, *, get=None, sleep=time.sleep, pause_s: float = 3.0) -> str | None:
    """The URL of one of the seller's live Mercado Libre listings with the WhatsApp button,
    the freshest first; at most 2 pages read."""
    get = get or (lambda url: httpx.get(url, headers=_HEADERS, timeout=30, follow_redirects=True))
    rows = sorted((r for r in prospect.listings if r["source"] == "mercadolibre" and r.get("url")),
                  key=lambda r: r.get("last_seen_at") or r.get("first_seen_at") or 0, reverse=True)
    for i, r in enumerate(rows[:2]):
        if i:
            sleep(pause_s)
        try:
            resp = get(r["url"])
        except httpx.HTTPError:
            continue
        if ml_button_page(resp.text, str(getattr(resp, "url", r["url"])), resp.status_code):
            return r["url"]
    return None


LOOKUP_SYSTEM = """Buscás el WhatsApp o celular PÚBLICO de agencias de autos usados de Argentina, para que su dueño reciba un mensaje comercial de una persona. Solo negocios: nunca busques el teléfono de una persona particular.

Por cada agencia recibís el nombre con el que publica, la zona, los portales y algunos de sus autos. Buscá en la web su canal de contacto público: su propio sitio, su Instagram o página de Facebook, su ficha de Google Maps, o el perfil de la agencia en un portal de autos. Reglas:
- Tiene que ser claramente ESA agencia: mismo nombre (o uno equivalente), misma ciudad o zona, y que venda autos usados. Si hay dudas entre dos negocios parecidos, no devuelvas nada.
- Solo números que la agencia publica para que la contacten (WhatsApp, celular de ventas, el de un botón de WhatsApp). Nada de teléfonos de empleados sacados de otros lados, ni de directorios de datos personales, ni de reseñas.
- Devolvé el número tal como lo encontraste y la URL de la página donde está publicado.
- Si no lo encontrás con seguridad, devolvé telefono null. Mejor nada que un número equivocado.
Respondé solo con el JSON del esquema."""

LOOKUP_SCHEMA = {
    "type": "object",
    "properties": {"agencias": {"type": "array", "items": {
        "type": "object",
        "properties": {
            "id": {"type": "string"},
            "telefono": {"type": ["string", "null"]},
            "url_fuente": {"type": ["string", "null"]},
            "confianza": {"type": "string", "enum": ["alta", "media", "baja"]},
            "nota": {"type": "string"},
        },
        "required": ["id", "telefono", "url_fuente", "confianza", "nota"], "additionalProperties": False}}},
    "required": ["agencias"], "additionalProperties": False,
}


def web(prospects: dict[str, tuple[Prospect, str | None]], *, call: Callable[[claude.Call], dict],
        model: str = LOOKUP_MODEL) -> dict[str, tuple[str, str]]:
    """{id: (number, url)} for the agencies found with high confidence.
    `prospects`: id → (prospect, zone label). Persons are refused here too."""
    items = []
    for pid, (p, zone) in prospects.items():
        if p.kind != "agencia":
            continue
        cars = [f"{r.get('make')} {r.get('model')} {r.get('year') or ''}".strip() for r in p.listings[:5]]
        items.append({"id": pid, "nombre": p.display_name, "otros_perfiles": [s.name for s in p.sellers][1:],
                      "zona": zone, "portales": [SOURCE_LABEL.get(s, s) for s in p.sources], "autos": cars})
    if not items:
        return {}
    out = call(claude.Call(system=LOOKUP_SYSTEM, user=json.dumps({"agencias": items}, ensure_ascii=False),
                           schema=LOOKUP_SCHEMA, model=model, effort="medium",
                           tools=("WebSearch", "WebFetch"), timeout_s=1200, max_turns=60))
    found: dict[str, tuple[str, str]] = {}
    for a in out.get("agencias", []):
        number = phones.normalize(a.get("telefono"))
        if number and a.get("confianza") == "alta" and a.get("url_fuente"):
            found[a["id"]] = (number, a["url_fuente"])
    return found

"""The email of the aviso de auto cerca de la zona (pipeline/near_zone.py).

One car, with its photo and price: a new listing that passes every filter of
the search but its zone. The button opens the listing; a text link under it
opens the search, where its owner can widen the zone.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Mapping

from intelligence import copy
from notifications.email_html import render as render_email_html
from notifications.links import Links
from notifications.low_results import search_url
from notifications.media import image_urls
from notifications.templates import UNSUBSCRIBE, Content, EmailMessage, Link, km, price, vehicle

TITLE = "Un auto cerca de tu zona"
SUBJECT = "Apareció un {car} a {dist} km de {place}"
PLACE_ANY = "tu zona"
WHERE = "Está a {dist} km de {place}. Tu búsqueda llega hasta {radius} km, por eso no aparece entre tus resultados."
FITS = "Cumple el resto de tus filtros."
WIDEN = "Si te sirve, ampliá la zona de tu búsqueda y te avisamos de los próximos."
CTA = "Ver la publicación"
WIDEN_CTA = "Ampliar la zona de mi búsqueda"
EYEBROW = "TU BÚSQUEDA"
FOOTER = "Recibís este email porque tenés una búsqueda activa en Ese Auto con avisos por email."


# What the web adds to a place it guessed («La Plata (zona aproximada)», «Morón (GBA)»),
# and its label for the browser's location, which names no place.
_PLACE_NOTE = re.compile(r"\s*\([^)]*\)\s*$")
_PLACE_UNNAMED = "mi ubicación actual"


def place(row: Mapping[str, Any]) -> str:
    """The search's place as a sentence can say it: «La Plata», or «tu zona»."""
    label = (row.get("filters") or {}).get("location_label")
    label = _PLACE_NOTE.sub("", label).strip() if isinstance(label, str) else ""
    return label if label and label.lower() != _PLACE_UNNAMED else PLACE_ANY


def email_message(row: Mapping[str, Any], listing: Mapping[str, Any], distance_km: float, links: Links,
                  now: datetime) -> EmailMessage:
    """`row` is the search (db/repos/near_zone.candidates), `listing` the car."""
    car, where = vehicle(listing), place(row)
    dist, radius = copy.number(round(distance_km)), copy.number(round(row["radius_km"]))
    subject = SUBJECT.format(car=car, dist=dist, place=where)
    spot = " · ".join(str(x) for x in (km(listing), listing.get("location_text")) if x)
    lines = [*([spot] if spot else []), WHERE.format(dist=dist, place=where, radius=radius), FITS, WIDEN]
    url, search = listing.get("url") or "", search_url(links, row["id"])
    widen = Link(WIDEN_CTA, search) if search else None
    c = Content(TITLE, subject, vehicle=car, lines=lines, link=Link(CTA, url) if url else widen,
                images=image_urls(listing.get("images")), price=price(listing))
    unsubscribe = links.unsubscribe(row.get("unsubscribe_token"))
    text = [TITLE, car, c.price, *lines, *([f"{CTA}: {url}"] if url else []),
            *([f"{WIDEN_CTA}: {search}"] if search else []), "", "—", FOOTER]
    if unsubscribe:
        text.append(f"{UNSUBSCRIBE}: {unsubscribe}")
    html = render_email_html(c, kind="near_zone", now=now, day=None, detail_url=None, app_url=None,
                             unsubscribe_url=unsubscribe, footer=FOOTER, unsubscribe_label=UNSUBSCRIBE,
                             eyebrow=EYEBROW, title=TITLE, preheader=f"{car}, {c.price}. {lines[-3]}",
                             secondary=widen if url else None)
    return EmailMessage(subject, "\n".join(text), html)

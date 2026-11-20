"""Agencias, fase 1: the summary email of a dealer's alerts.

Same channel and look as notifications/dealer_leads.py: one email per dealer
with every alert waiting (at most one every dealer_program.alerts_every_hours),
to dealers.contact_email or its owner's email, with a button to /agencia/stock
and how to turn the alerts off (/agencia/datos). Demand only as counts of at
least demand_min_count people (intelligence/dealer_alerts.py); never a
buyer's data. Logs carry dealer and alert ids only.
"""
from __future__ import annotations

import logging
from html import escape
from typing import Any, Mapping

from config import WEB_BASE_URL
from intelligence import copy
from notifications.links import Links
from notifications.templates import EmailMessage

log = logging.getLogger("dealer_alerts")

MAX_LINES = 20
SUBJECT = ("Una novedad de tu stock en Ese Auto", "{n} novedades de tu stock en Ese Auto")
INTRO = "Esto cambió desde el último aviso. Son precios publicados de autos parecidos, no valuaciones."
CTA = "Ver tu stock"
FOOTER = "Recibís estos avisos porque tu agencia está en Ese Auto. Si no los querés, apagalos en Datos de tu agencia:"
ORDER = {"cheaper_nearby": 0, "market_moved": 1, "new_demand": 2, "slow": 3}


def base_url(links: Links | None) -> str:
    return (links.base_url if links is not None and links.base_url else WEB_BASE_URL).rstrip("/")


def usd(value: Any) -> str:
    return copy.money(value, "USD")


def line(kind: str, p: Mapping[str, Any]) -> str | None:
    """One alert in words; None for an alert we can't phrase (it is still marked sent)."""
    car = p.get("car") or "tu auto"
    if kind == "market_moved":
        verb = "Bajó" if p.get("direction") == "down" else "Subió"
        return (f"{verb} el mercado del {car}: la mediana pasó de {usd(p.get('before_usd'))} a "
                f"{usd(p.get('now_usd'))} ({p.get('pct')} %).")
    if kind == "cheaper_nearby":
        where = f" a {p['distance_km']} km" if isinstance(p.get("distance_km"), int) else " cerca"
        site = f", en {p['source_name']}" if p.get("source_name") else ""
        return f"Apareció uno como tu {car} {p.get('pct')} % más barato{where}: {usd(p.get('price_usd'))}{site}."
    if kind == "slow":
        days = p.get("days")
        if isinstance(p.get("model_days"), int):
            return f"Tu {car} lleva {days} días en stock. El modelo se vende en unos {p['model_days']}."
        return f"Tu {car} lleva {days} días en stock."
    if kind == "new_demand":
        n = p.get("searches")
        return f"Entraron {n} búsquedas nuevas que aceptan tu {car} en tu zona."
    return None


def message(alerts: list[Mapping[str, Any]], links: Links | None) -> EmailMessage:
    ordered = sorted(alerts, key=lambda a: (ORDER.get(a["kind"], 9), a["id"]))
    lines = [t for a in ordered if (t := line(a["kind"], a.get("payload") or {}))]
    shown, rest = lines[:MAX_LINES], len(lines) - MAX_LINES
    n = len(lines)
    subject = SUBJECT[n != 1].format(n=n)
    base = base_url(links)
    stock, settings = f"{base}/agencia/stock", f"{base}/agencia/datos#avisos"
    more = f"Y {rest} más en tu panel." if rest > 0 else None
    text = "\n".join([subject, "", INTRO, "", *(f"• {t}" for t in shown), *([more] if more else []), "",
                      f"{CTA}: {stock}", "", "—", f"{FOOTER} {settings}"])
    items = "".join(f'<li style="margin:0 0 8px">{escape(t)}</li>' for t in shown)
    html = ('<div style="font-family:Arial,Helvetica,sans-serif;max-width:580px;margin:auto;color:#14213d;padding:28px">'
            '<p style="font-size:12px;color:#4e5a73">ESE AUTO · TU AGENCIA</p>'
            f'<h1 style="font-size:22px">{escape(subject)}</h1>'
            f'<p style="font-size:15px;line-height:1.6">{escape(INTRO)}</p>'
            f'<ul style="font-size:15px;line-height:1.5;padding-left:20px">{items}</ul>'
            + (f'<p style="font-size:15px">{escape(more)}</p>' if more else "")
            + f'<p><a href="{escape(stock, quote=True)}" style="display:inline-block;background:#14213d;color:#ffffff;'
            f'padding:12px 20px;border-radius:6px;text-decoration:none">{escape(CTA)}</a></p>'
            f'<p style="font-size:12px;color:#4e5a73">{escape(FOOTER)} '
            f'<a href="{escape(settings, quote=True)}" style="color:#4e5a73">{escape(settings)}</a></p></div>')
    return EmailMessage(subject, text, html)

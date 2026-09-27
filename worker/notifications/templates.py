"""Alert copy (§22, sección 7.2) and its three renderings: Telegram HTML,
email (subject, text, HTML) and the web inbox.

Each alert starts with the lines of §22, in order:

    new_match     🚗 Nuevo vehículo encontrado · vehículo · km · precio
    opportunity   🔥 Nueva oportunidad · vehículo · km · precio · Opportunity Score ·
                  "% debajo de publicaciones comparables" · "Publicado hace X" · Ver publicación
    price_drop    📉 Bajó de precio · vehículo · Antes · Ahora · -X,X%

and then what explains it (the search, place, source, red flags). Without a
published_at the alert says "Detectado hace X", never "Publicado hace X"
(§11, principio 5). Prices are always "publicados" (§19); the copy lint
(tests/test_notifications_templates.py) checks FORBIDDEN_TERMS here too.

Rendering is pure: payload + links + now → text. Telegram uses HTML parse
mode because Mercado Libre URLs end in underscores (`_JM`) that break
Markdown.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from html import escape
from typing import Any, Mapping

from intelligence import copy
from notifications.channels.base import Notification
from notifications.links import Links


HEADER = {
    "new_match": "🚗 Nuevo vehículo encontrado",
    "opportunity": "🔥 Nueva oportunidad",
    "price_drop": "📉 Bajó de precio",
    "listing_gone": "🚫 Ya no está disponible",
    "digest": "🗓 Tu resumen del día",
}
REPOST = "🔁 Re-publicado"
VIEW_LISTING = "Ver publicación"
VIEW_IN_APP = "🔎 Ver en Automotive"
INTERESTED, DISCARD = "⭐ Me interesa", "✖ Descartar"
INTERESTED_DONE, DISCARD_DONE = "✅ Te interesa", "✖ Descartada"
DIGEST_SECTIONS = {
    "matches": "Publicaciones nuevas",
    "price_drops": "Bajaron de precio",
    "gone": "Ya no están disponibles",
}
DIGEST_DEGRADED = ("1 alerta superó el tope diario de avisos inmediatos y quedó en este resumen.",
                   "{n} alertas superaron el tope diario de avisos inmediatos y quedaron en este resumen.")
EMAIL_FOOTER = "Recibís este correo porque tenés búsquedas activas en Automotive."
# Red flags shown in an alert, warnings first.
MAX_FLAGS = 2


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------

def vehicle(listing: Mapping[str, Any]) -> str:
    """Ford Fiesta Titanium 2017; the title when make/model aren't known."""
    if listing.get("make") and listing.get("model"):
        parts = [listing["make"], listing["model"], listing.get("trim"), listing.get("year")]
        return " ".join(str(p) for p in parts if p)
    return str(listing.get("title") or "Vehículo")


def ago_long(since: datetime, now: datetime) -> str:
    minutes = max(int((now - since).total_seconds() // 60), 1)
    if minutes < 60:
        return f"{minutes} minuto" + ("s" if minutes != 1 else "")
    hours = minutes // 60
    if hours < 48:
        return f"{hours} hora" + ("s" if hours != 1 else "")
    return f"{hours // 24} días"


def age_line(listing: Mapping[str, Any], now: datetime) -> str | None:
    published, seen = _ts(listing.get("published_at")), _ts(listing.get("first_seen_at"))
    if published:
        return f"Publicado hace {ago_long(published, now)}."
    if seen:
        return f"Detectado hace {ago_long(seen, now)}."
    return None


def pct(value: float, decimals: int = 1) -> str:
    return f"{value:.{decimals}f}".replace(".", ",")


def km(listing: Mapping[str, Any]) -> str | None:
    value = listing.get("mileage_km")
    return None if value is None else f"{copy.number(value)} km"


def _ts(value: Any) -> datetime | None:
    if value is None or isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))


def before_after(drop: Mapping[str, Any], listing: Mapping[str, Any]) -> tuple[str, str]:
    """Old and new published price, each in its own currency (a listing can
    move from ARS to USD; the drop is then measured in USD)."""
    currency = drop.get("currency") or listing.get("currency")
    return (copy.money(drop.get("old_price"), drop.get("old_currency") or currency),
            copy.money(drop.get("new_price"), currency))


def _level_emoji(level: str | None) -> str:
    return copy.LEVEL_LABEL[level].split()[0] if level in copy.LEVEL_LABEL else "•"


# ---------------------------------------------------------------------------
# Content: what an alert says, independent of the channel
# ---------------------------------------------------------------------------

@dataclass
class Link:
    label: str
    url: str


@dataclass
class DigestItem:
    text: str                 # vehicle line, linked
    url: str
    prefix: str = ""
    suffix: str = ""


@dataclass
class Content:
    header: str
    subject: str
    vehicle: str | None = None
    lines: list[str] = field(default_factory=list)       # §22 body, in order
    link: Link | None = None
    notes: list[str] = field(default_factory=list)       # what explains it
    sections: list[tuple[str, list[DigestItem]]] = field(default_factory=list)   # digest


def _notes(p: Mapping[str, Any], listing: Mapping[str, Any]) -> list[str]:
    where = [x for x in (f"🔎 {p['profile_name']}" if p.get("profile_name") else None,
                         f"📍 {listing['location_text']}" if listing.get("location_text") else None,
                         f"🏷 {listing['source']}" if listing.get("source") else None) if x]
    notes = [" · ".join(where)] if where else []
    notes += [f"⚠️ {t}" for t in (p.get("red_flags") or [])[:MAX_FLAGS]]
    return notes


def content(n: Notification, links: Links, now: datetime) -> Content:
    p = n.payload
    if n.kind == "digest":
        return _digest(n, links)
    listing = p.get("listing") or {}
    match = p.get("match") or {}
    car = vehicle(listing)
    link = Link(VIEW_LISTING, links.listing(n.id, listing.get("url") or ""))
    c = Content(HEADER[n.kind], f"{HEADER[n.kind]}: {car}", vehicle=car, link=link,
                notes=_notes(p, listing))

    if n.kind in ("new_match", "opportunity"):
        c.lines += [x for x in (km(listing), copy.money(listing.get("price"), listing.get("currency"))) if x]
        if n.kind == "opportunity":
            c.subject += f" · {match.get('score')}/100"
            c.lines.append(f"Opportunity Score {match.get('score')}/100")
            diff = match.get("diff_pct")
            if diff is not None and round(diff) > 0:
                c.lines.append(f"{round(diff)}% debajo de publicaciones comparables.")
            if age := age_line(listing, now):
                c.lines.append(age)
        else:
            if p.get("repost"):
                c.lines.insert(0, REPOST)
            if match.get("level"):
                c.notes.insert(0, f"{copy.LEVEL_LABEL[match['level']]} · {match.get('score')}/100")
    elif n.kind == "price_drop":
        drop = p.get("price_drop") or {}
        before, after = before_after(drop, listing)
        c.lines += [f"Antes: {before}", f"Ahora: {after}", f"-{pct(drop.get('drop_pct') or 0)}%"]
        c.subject += f" (-{pct(drop.get('drop_pct') or 0)}%)"
        if match.get("score") is not None:
            c.notes.insert(0, f"Opportunity Score {match['score']}/100")
    elif n.kind == "listing_gone":
        c.lines.append("La publicación que seguías se pausó, se vendió o se dio de baja.")
    return c


def _digest(n: Notification, links: Links) -> Content:
    p = n.payload
    items = p.get("items") or []

    def item(it: Mapping[str, Any]) -> DigestItem:
        listing = it.get("listing") or {}
        url = links.listing(n.id, listing.get("url") or "", it.get("listing_id"))
        match = it.get("match") or {}
        if it["section"] == "price_drops":
            drop = it.get("price_drop") or {}
            before, after = before_after(drop, listing)
            return DigestItem(vehicle(listing), url, "📉 ",
                              f" · {before} → {after} (-{pct(drop.get('drop_pct') or 0)}%)")
        if it["section"] == "gone":
            return DigestItem(vehicle(listing), url, "🚫 ")
        extra = [x for x in (km(listing), copy.money(listing.get("price"), listing.get("currency"))) if x]
        prefix = f"{_level_emoji(match.get('level'))} {match.get('score')} · " if match else ""
        return DigestItem(vehicle(listing), url, prefix, "".join(f" · {x}" for x in extra))

    sections = [(DIGEST_SECTIONS[s], [item(it) for it in items if it["section"] == s])
                for s in DIGEST_SECTIONS]
    sections = [(title, rows) for title, rows in sections if rows]
    count = sum(len(rows) for _, rows in sections)
    c = Content(HEADER["digest"], f"{HEADER['digest']} en Automotive: {count} novedad"
                + ("es" if count != 1 else ""), sections=sections)
    if p.get("degraded"):
        c.lines.append(DIGEST_DEGRADED[p["degraded"] != 1].format(n=p["degraded"]))
    return c


# ---------------------------------------------------------------------------
# Renderings
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Button:
    text: str
    callback_data: str | None = None
    url: str | None = None


@dataclass(frozen=True)
class TelegramMessage:
    text: str
    buttons: tuple[tuple[Button, ...], ...] = ()


def telegram_buttons(n: Notification, links: Links, *, chosen: str | None = None) -> tuple[tuple[Button, ...], ...]:
    """⭐ Me interesa · ✖ Descartar · 🔎 Ver en Automotive (sección 7.2).
    Callback data: nt:<action>:<notification_id> (bot/notification_actions.py)."""
    if n.kind == "digest" or n.listing_id is None:
        return ()
    rows: list[tuple[Button, ...]] = [(
        Button(INTERESTED_DONE if chosen == "interested" else INTERESTED, callback_data=f"nt:interested:{n.id}"),
        Button(DISCARD_DONE if chosen == "discarded" else DISCARD, callback_data=f"nt:discarded:{n.id}"),
    )]
    if links.buttons_allowed and (detail := links.detail(n.id)):
        rows.append((Button(VIEW_IN_APP, url=detail),))
    return tuple(rows)


def telegram(n: Notification, links: Links, now: datetime) -> TelegramMessage:
    c = content(n, links, now)
    e = escape
    out = [f"<b>{e(c.header)}</b>"]
    if c.vehicle:
        out.append(f"<b>{e(c.vehicle)}</b>")
    out += [e(x) for x in c.lines]
    if c.link:
        out.append(f'<a href="{e(c.link.url)}">{e(c.link.label)}</a>')
    for title, rows in c.sections:
        out += ["", f"<b>{e(title)}</b>"]
        out += [f'{e(r.prefix)}<a href="{e(r.url)}">{e(r.text)}</a>{e(r.suffix)}' for r in rows]
    if c.notes:
        out += [""] + [e(x) for x in c.notes]
    return TelegramMessage("\n".join(out), telegram_buttons(n, links))


@dataclass(frozen=True)
class EmailMessage:
    subject: str
    text: str
    html: str


def email(n: Notification, links: Links, now: datetime) -> EmailMessage:
    c = content(n, links, now)
    detail = links.detail(n.id) if n.kind != "digest" and n.listing_id is not None else None

    text = [c.header]
    if c.vehicle:
        text.append(c.vehicle)
    text += c.lines
    if c.link:
        text.append(f"{c.link.label}: {c.link.url}")
    if detail:
        text.append(f"{VIEW_IN_APP}: {detail}")
    for title, rows in c.sections:
        text += ["", title]
        text += [f"{r.prefix}{r.text}{r.suffix}\n  {r.url}" for r in rows]
    if c.notes:
        text += [""] + c.notes
    text += ["", "—", EMAIL_FOOTER]

    e = escape
    html = ['<div style="font-family:Arial,Helvetica,sans-serif;font-size:15px;line-height:1.5;color:#1a1a1a">',
            f'<p style="font-size:18px;margin:0 0 8px"><strong>{e(c.header)}</strong></p>']
    if c.vehicle:
        html.append(f'<p style="font-size:17px;margin:0 0 4px"><strong>{e(c.vehicle)}</strong></p>')
    html += [f'<p style="margin:0">{e(x)}</p>' for x in c.lines]
    buttons = [(c.link.label, c.link.url)] if c.link else []
    if detail:
        buttons.append((VIEW_IN_APP, detail))
    if buttons:
        html.append('<p style="margin:16px 0">' + " ".join(
            f'<a href="{e(url)}" style="display:inline-block;padding:10px 16px;margin-right:8px;'
            f'background:#1a1a1a;color:#ffffff;text-decoration:none;border-radius:6px">{e(label)}</a>'
            for label, url in buttons) + "</p>")
    for title, rows in c.sections:
        html.append(f'<p style="margin:16px 0 4px"><strong>{e(title)}</strong></p><ul style="margin:0;padding-left:20px">')
        html += [f'<li>{e(r.prefix)}<a href="{e(r.url)}">{e(r.text)}</a>{e(r.suffix)}</li>' for r in rows]
        html.append("</ul>")
    if c.notes:
        html += [f'<p style="margin:0;color:#555555">{e(x)}</p>' for x in c.notes]
    html.append(f'<p style="margin:24px 0 0;font-size:12px;color:#888888">{e(EMAIL_FOOTER)}</p></div>')
    return EmailMessage(c.subject, "\n".join(text), "\n".join(html))


def web(n: Notification, links: Links, now: datetime) -> dict[str, Any]:
    """Title and body lines for the web inbox (F4 renders the row itself)."""
    c = content(n, links, now)
    return {"title": c.header, "vehicle": c.vehicle, "lines": c.lines, "notes": c.notes}

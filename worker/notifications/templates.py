"""Alert copy (§22, sección 7.2) and its three renderings: Telegram HTML,
email (subject, text, HTML) and the web inbox.

Each alert starts with the lines of §22, in order:

    new_match     🚗 Nuevo vehículo encontrado · vehículo · km · precio
    opportunity   🔥 Nueva oportunidad · vehículo · km · precio · Opportunity Score ·
                  "% debajo de publicaciones comparables" · "Publicado hace X" · Ver publicación
    price_drop    📉 Bajó de precio · vehículo · Antes · Ahora · -X,X%

and then what explains it (the search, place, source, red flags). Without a
published_at the alert uses first_seen_at and says "Detectado hace X"
(§11, principio 5). Prices are always "publicados" (§19); the copy lint
(tests/test_notifications_templates.py) checks FORBIDDEN_TERMS here too.

Rendering is pure: payload + links + now → text. Telegram uses HTML parse
mode because Mercado Libre URLs end in underscores (`_JM`) that break
Markdown.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from html import escape
from typing import Any, Mapping

from intelligence import copy
from notifications.channels.base import Notification
from notifications.email_html import AR, MONTHS, render as render_email_html
from notifications.links import Links
from notifications.media import image_urls


HEADER = {
    "new_match": "🚗 Nuevo vehículo encontrado",
    "opportunity": "🔥 Nueva oportunidad",
    "price_drop": "📉 Bajó de precio",
    "listing_gone": "🚫 Ya no está disponible",
    "digest": "🗓 Tu resumen del día",
}
REPOST = "🔁 Re-publicado"
VIEW_LISTING = "Ver publicación"
VIEW_IN_APP = "🔎 Ver en Ese Auto"
INTERESTED, DISCARD = "⭐ Me interesa", "✖ Descartar"
INTERESTED_DONE, DISCARD_DONE = "✅ Te interesa", "✖ Descartada"
DIGEST_SECTIONS = {
    "matches": "Publicaciones nuevas",
    "price_drops": "Bajaron de precio",
    "gone": "Ya no están disponibles",
}
DIGEST_DEGRADED = ("1 alerta superó el tope diario de avisos inmediatos y quedó en este resumen.",
                   "{n} alertas superaron el tope diario de avisos inmediatos y quedaron en este resumen.")
EMAIL_FOOTER = "Recibís este correo porque tenés búsquedas activas en Ese Auto."
UNSUBSCRIBE = "Dejar de recibir estos emails"
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
    published = _ts(listing.get("published_at"))
    if published:
        return f"Publicado hace {ago_long(published, now)}."
    detected = _ts(listing.get("first_seen_at"))
    if detected:
        return f"Detectado hace {ago_long(detected, now)}."
    return "Fecha de publicación no informada."


def pct(value: float, decimals: int = 1) -> str:
    return f"{value:.{decimals}f}".replace(".", ",")


def km(listing: Mapping[str, Any]) -> str | None:
    value = listing.get("mileage_km")
    return None if value is None else f"{copy.number(value)} km"


CASH, FINANCEABLE = "de contado", "💳 También se puede financiar."


def price(listing: Mapping[str, Any]) -> str:
    """USD 10.900, or "USD 10.900 de contado" when the description says so."""
    text = copy.money(listing.get("price"), listing.get("currency"))
    cash = listing.get("price") is not None and listing.get("price_kind") == "cash"
    return f"{text} {CASH}" if cash else text


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
    details: list[str] = field(default_factory=list)
    price: str | None = None
    previous_price: str | None = None
    badge: str | None = None
    highlighted: bool = False
    score: int | float | None = None
    images: list[str] = field(default_factory=list)
    detail_url: str | None = None


@dataclass
class Content:
    header: str
    subject: str
    vehicle: str | None = None
    lines: list[str] = field(default_factory=list)       # §22 body, in order
    link: Link | None = None
    notes: list[str] = field(default_factory=list)       # what explains it
    sections: list[tuple[str, list[DigestItem]]] = field(default_factory=list)   # digest
    images: list[str] = field(default_factory=list)
    price: str | None = None
    previous_price: str | None = None


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
                notes=_notes(p, listing), images=image_urls(listing.get("images")))

    if n.kind in ("new_match", "opportunity"):
        c.price = price(listing)
        c.lines += [x for x in (km(listing), price(listing)) if x]
        if listing.get("financing"):
            c.notes.append(FINANCEABLE)
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
        c.price, c.previous_price = after, before
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
        visual = {"images": image_urls(listing.get("images")),
                  "detail_url": links.detail(n.id, it["listing_id"]) if it.get("listing_id") is not None else None}
        match = it.get("match") or {}
        details = [str(x) for x in (km(listing), listing.get("location_text")) if x]
        if it["section"] == "price_drops":
            drop = it.get("price_drop") or {}
            before, after = before_after(drop, listing)
            return DigestItem(vehicle(listing), url, "📉 ",
                              f" · {before} → {after} (-{pct(drop.get('drop_pct') or 0)}%)",
                              details=details, price=after, previous_price=before,
                              badge=f"Bajó {pct(drop.get('drop_pct') or 0)}%", **visual)
        if it["section"] == "gone":
            return DigestItem(vehicle(listing), url, "🚫 ", details=details,
                              badge="Ya no está disponible", **visual)
        extra = [x for x in (km(listing), price(listing)) if x]
        prefix = f"{_level_emoji(match.get('level'))} {match.get('score')} · " if match else ""
        label = copy.LEVEL_LABEL.get(match.get("level"))
        return DigestItem(vehicle(listing), url, prefix, "".join(f" · {x}" for x in extra),
                          details=details, price=price(listing),
                          badge=label.split(" ", 1)[1] if label else None,
                          highlighted=match.get("level") == "high", score=match.get("score"), **visual)

    sections = [(DIGEST_SECTIONS[s], [item(it) for it in items if it["section"] == s])
                for s in DIGEST_SECTIONS]
    sections = [(title, rows) for title, rows in sections if rows]
    count = sum(len(rows) for _, rows in sections)
    c = Content(HEADER["digest"], f"{HEADER['digest']} en Ese Auto: {count} novedad"
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
    """⭐ Me interesa · ✖ Descartar · 🔎 Ver en Ese Auto (sección 7.2).
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
    # Keep Telegram/source links as they are. Email's main action brings people
    # to the analysis in Ese Auto, using the existing click-tracking route.
    if detail:
        c.link = Link("Ver auto en Ese Auto", detail)
    if n.kind != "digest":
        c.subject += " · Ese Auto"
    app_url = f"{links.base_url.rstrip('/')}/app" if links.tracked else None

    text = [c.header]
    if c.vehicle:
        text.append(c.vehicle)
    text += c.lines
    if c.link:
        text.append(f"{c.link.label}: {c.link.url}")
    for title, rows in c.sections:
        text += ["", title]
        text += [f"{r.prefix}{r.text}{r.suffix}\n  {r.detail_url or r.url}" for r in rows]
    if app_url:
        text += ["", f"Ver mis búsquedas: {app_url}"]
    if c.notes:
        text += [""] + c.notes
    unsubscribe = links.unsubscribe(n.unsubscribe_token)
    text += ["", "—", EMAIL_FOOTER]
    if unsubscribe:
        text.append(f"{UNSUBSCRIBE}: {unsubscribe}")

    html = render_email_html(c, kind=n.kind, now=now, day=n.payload.get("date"),
                             detail_url=detail, app_url=app_url,
                             unsubscribe_url=unsubscribe, footer=EMAIL_FOOTER,
                             unsubscribe_label=UNSUBSCRIBE)
    return EmailMessage(c.subject, "\n".join(text), html)


def web(n: Notification, links: Links, now: datetime) -> dict[str, Any]:
    """Title and body lines for the web inbox (F4 renders the row itself)."""
    c = content(n, links, now)
    return {"title": c.header, "vehicle": c.vehicle, "lines": c.lines, "notes": c.notes}


# ---------------------------------------------------------------------------
# Free-trial reminder (docs/RECORDATORIO_PRUEBA.md): one email per account
# when the 72 h trial ends without a plan. Not an alert: no listing, no /r/
# link, its own footer (the account no longer has active searches).
# ---------------------------------------------------------------------------

TRIAL_REMINDER_SUBJECT = "Terminó tu prueba gratis en Ese Auto"
TRIAL_REMINDER_EYEBROW = "TU PRUEBA GRATIS"
TRIAL_REMINDER_TITLE = "Terminó tu prueba de 3 días"
TRIAL_REMINDER_PREHEADER = ("Tus resultados y favoritos siguen guardados. "
                            "Elegí un plan para volver a recibir alertas.")
TRIAL_REMINDER_ENDED = "Tu prueba gratis venció el {date} a las {time} (hora de Argentina)."
TRIAL_REMINDER_PAUSED = ("Pausamos tu búsqueda y dejamos de mandarte alertas. "
                         "Conservamos tus resultados y favoritos.")
TRIAL_REMINDER_PLANS = ("Para volver a monitorear, elegí Particular ({particular} por {days} días, "
                        "pago único) o Agencia ({agencia} por mes).")
TRIAL_REMINDER_PLANS_FALLBACK = "Para volver a monitorear, elegí Particular o Agencia."
TRIAL_REMINDER_AFTER = "Después de pagar, reactivás tu búsqueda desde Ese Auto."
TRIAL_REMINDER_CTA = "Ver planes"
TRIAL_REMINDER_NOTE = "La prueba gratis no genera cobros: solo pagás si elegís un plan."
TRIAL_REMINDER_FOOTER = ("Recibís este email porque activaste una búsqueda gratis en Ese Auto. "
                         "Es el único aviso que te mandamos sobre el fin de la prueba.")
# Plain UTM link: /r/ only tracks listings.
TRIAL_REMINDER_PATH = "/app/pro?utm_source=email&utm_medium=email&utm_campaign=trial_reminder"


def _offer_price(offer: Mapping[str, Any], plan: str) -> tuple[str, int | None] | None:
    """("ARS 15.000", 30) from app_config.pro_offer[plan]; None if it isn't usable."""
    price = offer.get(plan)
    if not isinstance(price, Mapping):
        return None
    amount, currency, days = price.get("amount"), price.get("currency"), price.get("days")
    if isinstance(amount, bool) or not isinstance(currency, str) or not currency.strip():
        return None
    try:
        amount = float(amount)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(amount) or amount <= 0:
        return None
    if isinstance(days, bool) or not isinstance(days, int) or days <= 0:
        days = None
    return copy.money(amount, currency.strip()), days


def trial_reminder_plans(offer: Mapping[str, Any] | None) -> str:
    """The plan line with the current prices, or without them if pro_offer is
    missing or invalid (never a wrong price)."""
    if isinstance(offer, Mapping):
        particular, agencia = _offer_price(offer, "pass_30"), _offer_price(offer, "pro_monthly")
        if particular and agencia and particular[1]:
            return TRIAL_REMINDER_PLANS.format(particular=particular[0], days=particular[1],
                                               agencia=agencia[0])
    return TRIAL_REMINDER_PLANS_FALLBACK


def trial_reminder_email(trial_expires_at: datetime, links: Links, unsubscribe_token: str | None,
                         now: datetime, offer: Mapping[str, Any] | None) -> EmailMessage:
    """The free-trial reminder: subject, text and HTML. Dates in Argentina's time."""
    if trial_expires_at.tzinfo is None:
        trial_expires_at = trial_expires_at.replace(tzinfo=timezone.utc)
    ended = trial_expires_at.astimezone(AR)
    plans_url = f"{links.base_url}{TRIAL_REMINDER_PATH}"
    c = Content(TRIAL_REMINDER_TITLE, TRIAL_REMINDER_SUBJECT,
                lines=[TRIAL_REMINDER_ENDED.format(date=f"{ended.day} de {MONTHS[ended.month - 1]}",
                                                   time=f"{ended:%H:%M}"),
                       TRIAL_REMINDER_PAUSED, trial_reminder_plans(offer), TRIAL_REMINDER_AFTER],
                link=Link(TRIAL_REMINDER_CTA, plans_url), notes=[TRIAL_REMINDER_NOTE])
    unsubscribe = links.unsubscribe(unsubscribe_token)

    text = [c.header, *c.lines, f"{c.link.label}: {c.link.url}", "", *c.notes,
            "", "—", TRIAL_REMINDER_FOOTER]
    if unsubscribe:
        text.append(f"{UNSUBSCRIBE}: {unsubscribe}")

    html = render_email_html(c, kind="trial_reminder", now=now, day=None, detail_url=None, app_url=None,
                             unsubscribe_url=unsubscribe, footer=TRIAL_REMINDER_FOOTER,
                             unsubscribe_label=UNSUBSCRIBE, eyebrow=TRIAL_REMINDER_EYEBROW,
                             title=TRIAL_REMINDER_TITLE, preheader=TRIAL_REMINDER_PREHEADER)
    return EmailMessage(c.subject, "\n".join(text), html)

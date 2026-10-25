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
from datetime import datetime, timedelta, timezone
from html import escape
from typing import Any, Mapping

from intelligence import copy
from notifications.channels.base import Notification
from notifications.email_html import render as render_email_html
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
# Free searches only ask for an email, with no confirmation (no double
# opt-in): the alert footer works for whoever typed the address and for whoever
# owns it. "¿No fuiste vos?" only goes with the unsubscribe link right below it.
EMAIL_FOOTER = "Recibís este email porque se creó una búsqueda en Ese Auto con esta dirección."
EMAIL_NOT_YOU = "¿No fuiste vos?"
UNSUBSCRIBE_ALERTS = "Dejá de recibirlos"
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


def content(n: Notification, links: Links, now: datetime, *, owner: str | None = None) -> Content:
    """`owner` signs the links into the app (emails only, notifications/links.py)."""
    p = n.payload
    if n.kind == "digest":
        return _digest(n, links, owner)
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


def _digest(n: Notification, links: Links, owner: str | None = None) -> Content:
    p = n.payload
    items = p.get("items") or []

    def item(it: Mapping[str, Any]) -> DigestItem:
        listing = it.get("listing") or {}
        url = links.listing(n.id, listing.get("url") or "", it.get("listing_id"))
        visual = {"images": image_urls(listing.get("images")),
                  "detail_url": links.detail(n.id, it["listing_id"], owner=owner) if it.get("listing_id") is not None else None}
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
    # The remarketing emails go out in a person's name, with no inline logo,
    # and replies reach someone who reads them.
    from_name: str | None = None
    reply_to: str | None = None
    logo: bool = True


def email(n: Notification, links: Links, now: datetime) -> EmailMessage:
    c = content(n, links, now, owner=n.user_id)
    detail = links.detail(n.id, owner=n.user_id) if n.kind != "digest" and n.listing_id is not None else None
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
    footer = f"{EMAIL_FOOTER} {EMAIL_NOT_YOU}" if unsubscribe else EMAIL_FOOTER
    text += ["", "—", footer]
    if unsubscribe:
        text.append(f"{UNSUBSCRIBE_ALERTS}: {unsubscribe}")

    html = render_email_html(c, kind=n.kind, now=now, day=n.payload.get("date"),
                             detail_url=detail, app_url=app_url,
                             unsubscribe_url=unsubscribe, footer=footer,
                             unsubscribe_label=UNSUBSCRIBE_ALERTS,
                             open_pixel_url=links.open_pixel("n", n.id))
    return EmailMessage(c.subject, "\n".join(text), html)


def web(n: Notification, links: Links, now: datetime) -> dict[str, Any]:
    """Title and body lines for the web inbox (F4 renders the row itself)."""
    c = content(n, links, now)
    return {"title": c.header, "vehicle": c.vehicle, "lines": c.lines, "notes": c.notes}


# ---------------------------------------------------------------------------
# Plan emails (docs/MAILS_DE_PLAN.md): one per account and event, sent by
# notifications/lifecycle.py from the lifecycle_emails ledger. Not alerts: no
# listing and no /r/ link; the button goes through /m/<id>, which records
# lifecycle_email_clicked. The copy is the plans document's (fase 2): de vos,
# never «en tiempo real», «todos los portales» or «el más barato», and a
# sentence whose number is 0 is left out.
# ---------------------------------------------------------------------------

LIFECYCLE_EYEBROW = {"trial_no_matches": "TU PRUEBA GRATIS", "trial_ended": "TU PRUEBA GRATIS",
                     "pass_expiring": "TU PLAN PARTICULAR", "pass_expires_today": "TU PLAN PARTICULAR",
                     "count_after_expiry": "TU BÚSQUEDA", "search_activated": "TU BÚSQUEDA",
                     "bonus_trial_offer": "7 DÍAS GRATIS", "bonus_trial_ending": "TUS 7 DÍAS GRATIS",
                     "bonus_trial_ended": "TUS 7 DÍAS GRATIS"}
# The free-trial ones reach email-only accounts too (nobody confirmed the
# address), so they don't say the reader created the search.
LIFECYCLE_FOOTER = {
    "trial_no_matches": "Recibís este email porque se activó una búsqueda gratis en Ese Auto con esta dirección.",
    "trial_ended": "Recibís este email porque se activó una búsqueda gratis en Ese Auto con esta dirección.",
    "pass_expiring": "Recibís este email porque tenés Particular en Ese Auto.",
    "pass_expires_today": "Recibís este email porque tenés Particular en Ese Auto.",
    "count_after_expiry": "Recibís este email porque hubo una búsqueda activa en Ese Auto con esta dirección.",
    "search_activated": "Recibís este email porque se activó una búsqueda gratis en Ese Auto con esta dirección.",
    "bonus_trial_offer": "Recibís este email porque hubo una búsqueda activa en Ese Auto con esta dirección.",
    "bonus_trial_ending": "Recibís este email porque se activaron 7 días gratis en Ese Auto con esta dirección.",
    "bonus_trial_ended": "Recibís este email porque se activaron 7 días gratis en Ese Auto con esta dirección.",
}

# search_activated: the first email an account gets, 45 minutes after its first search.
WELCOME_SUBJECT = "Tu búsqueda de {model} ya está activa"
WELCOME_SUBJECT_ANY = "Tu búsqueda ya está activa"
WELCOME_FOUND = {1: "Ya encontramos 1 auto que coincide con tu búsqueda{model}{below}. Te avisamos de los nuevos apenas aparezcan.",
                 "n": "Ya encontramos {n} autos que coinciden con tu búsqueda{model}{below}. Te avisamos de los nuevos apenas aparezcan."}
WELCOME_BELOW = {1: ", y 1 está por debajo de publicaciones comparables",
                 "n": ", y {n} están por debajo de publicaciones comparables"}
WELCOME_NONE = ("Ya estamos revisando las publicaciones{model}. Todavía no apareció ninguno que coincida: "
                "te avisamos apenas aparezca.")
WELCOME_INBOX = ("Para que nuestras alertas no terminen en Spam o Promociones, agregá este remitente a tus "
                 "contactos o mové este email a Principal.")
WELCOME_CTA = "Ver mis resultados"

NO_MATCHES_SUBJECT = "Tu búsqueda de {model} todavía no tuvo coincidencias nuevas"
NO_MATCHES_SUBJECT_ANY = "Tu búsqueda todavía no tuvo coincidencias nuevas"
NO_MATCHES_BODY = ("En las primeras 24 horas no apareció ningún auto nuevo con tus filtros. "
                   "Si ampliás años, kilómetros o zona, vas a ver más opciones en lo que queda de la prueba.")
NO_MATCHES_CTA = "Ajustar filtros"

TRIAL_ENDED_SUBJECT = "Terminó tu prueba: encontramos {found} para tu búsqueda"
TRIAL_ENDED_TITLE = "Terminó tu prueba"
TRIAL_ENDED_FOUND = "En 3 días encontramos {found} para tu búsqueda{model}{below}."
TRIAL_ENDED_BELOW = ", y {n} {verb} por debajo de publicaciones comparables"
TRIAL_ENDED_OFFER = ("Para seguir recibiendo avisos, Particular sale {price} por {days} días, "
                     "con {searches} búsquedas y pago único.")
TRIAL_ENDED_OFFER_FALLBACK = "Para seguir recibiendo avisos, elegí Particular."
TRIAL_ENDED_KEEP = "Tu historial y tus favoritos quedan guardados."
TRIAL_ENDED_CTA = "Seguir con Particular"

PASS_SUBJECT = {"pass_expiring": "Te quedan 5 días de Ese Auto",
                "pass_expires_today": "Hoy vence tu acceso a Ese Auto"}
PASS_FOUND = "Desde que activaste Particular encontramos {found}{below}."
PASS_BELOW = ", {n} por debajo de comparables"
PASS_EXTEND = "Si todavía no lo encontraste, extendé 30 días más: se suman a tu vencimiento."
# A pass that already ended (early on its last day) restarts from the payment.
PASS_EXTEND_ENDED = "Si todavía no lo encontraste, extendé 30 días más."
PASS_LAST_DAY = "Desde mañana dejamos de buscar y de avisarte. Tu historial y tus favoritos quedan guardados."
PASS_KEEP = "Tu historial y tus favoritos quedan guardados."
PASS_CTA = "Extender 30 días"

# 2.5: the count, never the cars. N is never 0 (no email then).
COUNT_SUBJECT = {1: "Apareció 1 auto nuevo para tu búsqueda{model}",
                 "n": "Aparecieron {n} autos nuevos para tu búsqueda{model}"}
COUNT_FOUND = {1: "Desde que venció tu acceso apareció 1 auto nuevo que coincide con tu búsqueda{below}.",
               "n": "Desde que venció tu acceso aparecieron {n} autos nuevos que coinciden con tu búsqueda{below}."}
COUNT_BELOW = {1: ", y 1 está por debajo de comparables", "n": ", y {n} están por debajo de comparables"}
COUNT_REACTIVATE = {1: "Reactivá para verlo.", "n": "Reactivá para verlos."}
COUNT_CTA = "Reactivar por {price}"
COUNT_CTA_FALLBACK = "Reactivar"

# The extra 7-day trial: once per account, on day 7 after the 72 h trial ended.
BONUS_SUBJECT = "Te damos 7 días más para tu búsqueda de {model}"
BONUS_SUBJECT_ANY = "Te damos 7 días más para tu búsqueda"
BONUS_NEW = {1: "Desde que pausamos tu búsqueda apareció 1 auto nuevo que coincide{below}.",
             "n": "Desde que pausamos tu búsqueda aparecieron {n} autos nuevos que coinciden{below}."}
BONUS_NEW_BELOW = {1: ", y 1 está por debajo de publicaciones comparables",
                   "n": ", y {n} están por debajo de publicaciones comparables"}
BONUS_FOUND = {1: "En tu prueba encontramos 1 auto para tu búsqueda{model}.",
               "n": "En tu prueba encontramos {n} autos para tu búsqueda{model}."}
BONUS_BODY = ("Te damos 7 días gratis para que la veas funcionar: la reactivamos tal como estaba, con los "
              "avisos por email. Sin tarjeta, y al terminar se pausa sola.")
BONUS_CARS = "Algunos de los que encontramos:"
BONUS_CAR_BELOW = "por debajo de comparables"
BONUS_CTA = "Activar mis 7 días"

BONUS_ENDING_SUBJECT = "Te quedan 2 días gratis para tu búsqueda{model}"
BONUS_ENDING_FOUND = "En estos días encontramos {found}{below}."
BONUS_ENDING_LAST = "El {day} tu búsqueda se pausa sola. Si querés seguir, {offer}"
BONUS_ENDING_CTA = "Ver mis resultados"

BONUS_ENDED_TITLE = "Terminaron tus 7 días"
BONUS_ENDED_SUBJECT = "Terminaron tus 7 días: encontramos {found} para tu búsqueda"
BONUS_ENDED_FOUND = "En 7 días encontramos {found} para tu búsqueda{model}{below}."


def _count(value: Any) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else 0


def _cars(n: int) -> str:
    return f"{n} auto" if n == 1 else f"{n} autos"


def _pesos(amount: Any) -> str | None:
    """$15.000, as the plans document writes prices; None if the amount isn't usable."""
    if isinstance(amount, bool):
        return None
    try:
        value = float(amount)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(value) or value <= 0:
        return None
    return "$" + f"{value:,.0f}".replace(",", ".")


def _plural(texts: Mapping[Any, str], n: int, **kw: Any) -> str:
    return texts[1].format(**kw) if n == 1 else texts["n"].format(n=n, **kw)


def _day_month(value: Any) -> str | None:
    """An ISO timestamp as 31/10, in Argentina; None if it isn't one."""
    if not isinstance(value, str):
        return None
    try:
        when = datetime.fromisoformat(value)
    except ValueError:
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return when.astimezone(_AR).strftime("%d/%m").lstrip("0")


def _car(car: Mapping[str, Any]) -> str | None:
    """«Toyota Hilux 2015 · USD 21.500 · 140.000 km · por debajo de comparables»; None without a title."""
    title = car.get("title").strip() if isinstance(car.get("title"), str) else ""
    if not title:
        return None
    year = car.get("year")
    if isinstance(year, int) and not isinstance(year, bool) and str(year) not in title:
        title = f"{title} {year}"
    parts = [title]
    price, currency = car.get("price"), car.get("currency")
    if currency in ("USD", "ARS") and (amount := _pesos(price)):
        parts.append(f"USD {amount[1:]}" if currency == "USD" else amount)
    km = car.get("km")
    if isinstance(km, int) and not isinstance(km, bool) and km >= 0:
        parts.append(f"{km:,} km".replace(",", "."))
    if car.get("below") is True:
        parts.append(BONUS_CAR_BELOW)
    return " · ".join(parts)


def particular_price(offer: Mapping[str, Any] | None) -> str | None:
    """Particular's price from app_config.pro_offer ("$15.000"), or None if it isn't usable."""
    price = offer.get("pass_30") if isinstance(offer, Mapping) else None
    if isinstance(price, Mapping) and price.get("currency") == "ARS":
        return _pesos(price.get("amount"))
    return None


def particular_offer(offer: Mapping[str, Any] | None, limits: Mapping[str, Any] | None) -> str:
    """Particular's price, days and searches from app_config (pro_offer,
    plan_limits); without a usable price, the plan without numbers (never a wrong one)."""
    price = offer.get("pass_30") if isinstance(offer, Mapping) else None
    amount = particular_price(offer)
    if amount:
        days = price.get("days")
        if isinstance(days, int) and not isinstance(days, bool) and days > 0:
            pass_limits = limits.get("pass") if isinstance(limits, Mapping) else None
            searches = pass_limits.get("max_profiles") if isinstance(pass_limits, Mapping) else None
            if not (isinstance(searches, int) and not isinstance(searches, bool) and searches > 0):
                searches = 3
            return TRIAL_ENDED_OFFER.format(price=amount, days=days, searches=searches)
    return TRIAL_ENDED_OFFER_FALLBACK


def lifecycle_content(kind: str, payload: Mapping[str, Any], url: str, *,
                      offer: Mapping[str, Any] | None = None,
                      limits: Mapping[str, Any] | None = None) -> tuple[Content, str]:
    """The email of one ledger row: its Content and its title."""
    model = payload.get("model") if isinstance(payload.get("model"), str) and payload["model"].strip() else None
    if kind == "search_activated":
        found, below = _count(payload.get("found")), _count(payload.get("below"))
        subject = WELCOME_SUBJECT.format(model=model) if model else WELCOME_SUBJECT_ANY
        of_model = f" de {model}" if model else ""
        first = (_plural(WELCOME_FOUND, found, model=of_model, below=_plural(WELCOME_BELOW, below) if below else "")
                 if found else WELCOME_NONE.format(model=f" para tu búsqueda{of_model}"))
        return Content(subject, subject, lines=[first, WELCOME_INBOX], link=Link(WELCOME_CTA, url)), subject
    if kind == "trial_no_matches":
        subject = NO_MATCHES_SUBJECT.format(model=model) if model else NO_MATCHES_SUBJECT_ANY
        return Content(subject, subject, lines=[NO_MATCHES_BODY], link=Link(NO_MATCHES_CTA, url)), subject
    if kind == "trial_ended":
        found, below = _count(payload.get("found")), _count(payload.get("below"))
        lines = []
        if found:
            below_text = (TRIAL_ENDED_BELOW.format(n=below, verb="estaba" if below == 1 else "estaban")
                          if below else "")
            lines.append(TRIAL_ENDED_FOUND.format(found=_cars(found), model=f" de {model}" if model else "",
                                                  below=below_text))
        lines += [particular_offer(offer, limits), TRIAL_ENDED_KEEP]
        subject = TRIAL_ENDED_SUBJECT.format(found=_cars(found)) if found else TRIAL_ENDED_TITLE
        return Content(TRIAL_ENDED_TITLE, subject, lines=lines, link=Link(TRIAL_ENDED_CTA, url)), TRIAL_ENDED_TITLE
    if kind in PASS_SUBJECT:
        found, below = _count(payload.get("found")), _count(payload.get("below"))
        ended = payload.get("ended") is True
        lines = [PASS_FOUND.format(found=_cars(found), below=PASS_BELOW.format(n=below) if below else "")] if found else []
        lines.append(PASS_EXTEND_ENDED if ended else PASS_EXTEND)
        if kind == "pass_expires_today":
            lines.append(PASS_KEEP if ended else PASS_LAST_DAY)
        subject = PASS_SUBJECT[kind]
        return Content(subject, subject, lines=lines, link=Link(PASS_CTA, url)), subject
    if kind == "count_after_expiry":
        found, below = _count(payload.get("found")), _count(payload.get("below"))
        if not found:
            raise ValueError("count_after_expiry without new listings")
        subject = _plural(COUNT_SUBJECT, found, model=f" de {model}" if model else "")
        lines = [_plural(COUNT_FOUND, found, below=_plural(COUNT_BELOW, below) if below else ""),
                 _plural(COUNT_REACTIVATE, found)]
        price = particular_price(offer)
        cta = COUNT_CTA.format(price=price) if price else COUNT_CTA_FALLBACK
        return Content(subject, subject, lines=lines, link=Link(cta, url)), subject
    if kind == "bonus_trial_offer":
        found, new, below = (_count(payload.get(k)) for k in ("found", "new", "below"))
        of_model = f" de {model}" if model else ""
        subject = BONUS_SUBJECT.format(model=model) if model else BONUS_SUBJECT_ANY
        lines = []
        if new:
            lines.append(_plural(BONUS_NEW, new, below=_plural(BONUS_NEW_BELOW, below) if below else ""))
        elif found:
            lines.append(_plural(BONUS_FOUND, found, model=of_model))
        lines.append(BONUS_BODY)
        cars = [c for c in (_car(x) for x in payload.get("cars") or [] if isinstance(x, Mapping)) if c][:3]
        if cars:
            lines += [BONUS_CARS, *cars]
        return Content(subject, subject, lines=lines, link=Link(BONUS_CTA, url)), subject
    if kind == "bonus_trial_ending":
        found, below = _count(payload.get("found")), _count(payload.get("below"))
        subject = BONUS_ENDING_SUBJECT.format(model=f" de {model}" if model else "")
        lines = [BONUS_ENDING_FOUND.format(found=_cars(found), below=PASS_BELOW.format(n=below) if below else "")
                 ] if found else []
        day = _day_month(payload.get("ends_at"))
        offer_text = particular_offer(offer, limits).removeprefix("Para seguir recibiendo avisos, ")
        lines.append(BONUS_ENDING_LAST.format(day=day, offer=offer_text) if day
                     else particular_offer(offer, limits))
        return Content(subject, subject, lines=lines, link=Link(BONUS_ENDING_CTA, url)), subject
    if kind == "bonus_trial_ended":
        found, below = _count(payload.get("found")), _count(payload.get("below"))
        lines = []
        if found:
            below_text = (TRIAL_ENDED_BELOW.format(n=below, verb="estaba" if below == 1 else "estaban")
                          if below else "")
            lines.append(BONUS_ENDED_FOUND.format(found=_cars(found), model=f" de {model}" if model else "",
                                                  below=below_text))
        lines += [particular_offer(offer, limits), TRIAL_ENDED_KEEP]
        subject = BONUS_ENDED_SUBJECT.format(found=_cars(found)) if found else BONUS_ENDED_TITLE
        return Content(BONUS_ENDED_TITLE, subject, lines=lines, link=Link(TRIAL_ENDED_CTA, url)), BONUS_ENDED_TITLE
    raise ValueError(f"unknown plan email kind: {kind}")


def lifecycle_email(row: Mapping[str, Any], links: Links, now: datetime, *,
                    offer: Mapping[str, Any] | None = None,
                    limits: Mapping[str, Any] | None = None,
                    remarketing: Mapping[str, Any] | None = None) -> EmailMessage:
    """A plan email for a lifecycle_emails row (id, kind, payload, unsubscribe_token)."""
    kind = row["kind"]
    if kind in REMARKETING_KINDS:
        return remarketing_email(row, links, remarketing=remarketing)
    c, title = lifecycle_content(kind, row.get("payload") or {}, links.lifecycle(row["id"], owner=row.get("user_id")),
                                 offer=offer, limits=limits)
    footer = LIFECYCLE_FOOTER[kind]
    unsubscribe = links.unsubscribe(row.get("unsubscribe_token"))

    text = [c.header, *c.lines, f"{c.link.label}: {c.link.url}", "", "—", footer]
    if unsubscribe:
        text.append(f"{UNSUBSCRIBE}: {unsubscribe}")

    html = render_email_html(c, kind=kind, now=now, day=None, detail_url=None, app_url=None,
                             unsubscribe_url=unsubscribe, footer=footer, unsubscribe_label=UNSUBSCRIBE,
                             eyebrow=LIFECYCLE_EYEBROW[kind], title=title, preheader=c.lines[0],
                             open_pixel_url=links.open_pixel("m", row["id"]))
    return EmailMessage(c.subject, "\n".join(text), html)


# ---------------------------------------------------------------------------
# Remarketing (docs/MAILS_DE_PLAN.md, «Remarketing»): accounts without a
# search. A person writes them (app_config.remarketing: sender_name, signer,
# reply_to), in nearly plain text: one action link, the reason links and a
# signature, no logo or brand template. The reason links lead to /f/<id>,
# which asks to confirm before recording (mail scanners open every link).
# ---------------------------------------------------------------------------

REMARKETING_KINDS = ("search_abandoned", "search_not_started", "search_feedback")
REMARKETING_DEFAULTS = {"sender_name": "Juan de Ese Auto", "signer": "Juan", "reply_to": None}
_AR = timezone(timedelta(hours=-3))

# (reason, label), in the order the email lists them. wrong_search only after an assisted request.
FEEDBACK_REASONS = (("browsing", "Solo estaba mirando"),
                    ("missing_model", "No encontré mi modelo o versión"),
                    ("wrong_search", "La búsqueda que armaron no era lo que pedí"),
                    ("unclear", "No entendí qué hace Ese Auto"),
                    ("bought", "Ya compré un auto"),
                    ("other", "Otro motivo"))

ABANDONED_SUBJECT = "Tu búsqueda de {model} quedó sin activar"
ABANDONED_SUBJECT_ANY = "Tu búsqueda quedó sin activar"
ABANDONED_ASKED = "El {day} nos escribiste: «{text}»."
ABANDONED_BODY = ("La dejamos lista: con un clic empezamos a revisar las publicaciones y te avisamos cuando "
                  "aparezca un auto que coincida. La prueba gratis arranca recién cuando la activás.")
ABANDONED_CTA = "Activar mi búsqueda"

NOT_STARTED_SUBJECT = "¿Qué auto estás buscando?"
NOT_STARTED_BODY = ("Te sumaste a Ese Auto pero todavía no nos contaste qué auto buscás. Escribilo como se lo "
                    "dirías a un amigo, por ejemplo «Gol Trend 2015 a 2018 hasta 120.000 km» o «algo automático "
                    "hasta USD 12.000», y revisamos las publicaciones por vos.")
NOT_STARTED_CTA = "Empezar mi búsqueda"

FEEDBACK_SUBJECT = "¿Qué te frenó?"
FEEDBACK_INTRO = "Soy {signer}, hago Ese Auto."
FEEDBACK_SAW = {"model": "Vi que empezaste a buscar un {model} y no seguiste.",
                "asked": "Vi que empezaste a armar una búsqueda y no seguiste.",
                "none": "Vi que te sumaste a Ese Auto y no llegaste a armar una búsqueda."}
FEEDBACK_ASK = "¿Me contás qué pasó? Con un clic alcanza."
FEEDBACK_STILL = {"search_abandoned": "Si todavía la querés, sigue lista para activar:",
                  "search_not_started": "Si todavía estás buscando, empezá acá:"}

REASONS_ASK = {"search_abandoned": "¿No la activaste por algo? Contanos con un clic:",
               "search_not_started": "¿Algo te frenó? Contanos con un clic:"}
REPLY_LINE = "O respondé este email: lo leo yo."
REMARKETING_FOOTER = "Recibís este email porque se creó una cuenta en Ese Auto con esta dirección."


def remarketing_settings(raw: Any) -> dict[str, Any]:
    """app_config.remarketing over REMARKETING_DEFAULTS; a blank or bad value falls back."""
    cfg = raw if isinstance(raw, Mapping) else {}
    out = {}
    for key, default in REMARKETING_DEFAULTS.items():
        value = cfg.get(key)
        out[key] = value.strip() if isinstance(value, str) and value.strip() else default
    reply_to = out["reply_to"]
    out["reply_to"] = reply_to if isinstance(reply_to, str) and "@" in reply_to and "\n" not in reply_to else None
    return out


def _asked_day(value: Any) -> str | None:
    """'2026-10-24T15:02:00+00:00' → '24/10', in Argentina."""
    if not isinstance(value, str):
        return None
    try:
        when = datetime.fromisoformat(value)
    except ValueError:
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return when.astimezone(_AR).strftime("%d/%m").lstrip("0")


def remarketing_email(row: Mapping[str, Any], links: Links, *, remarketing: Mapping[str, Any] | None = None
                      ) -> EmailMessage:
    """One remarketing email for a lifecycle_emails row (id, kind, payload, user_id, unsubscribe_token)."""
    kind, payload = row["kind"], row.get("payload") or {}
    cfg = remarketing_settings(remarketing)
    owner = row.get("user_id")
    action = links.lifecycle(row["id"], owner=owner)
    model = payload.get("model") if isinstance(payload.get("model"), str) and payload["model"].strip() else None
    first = payload.get("after") if kind == "search_feedback" else kind
    if first not in FEEDBACK_STILL:
        first = "search_not_started"

    paragraphs: list[str] = []
    if kind == "search_abandoned":
        subject = ABANDONED_SUBJECT.format(model=model) if model else ABANDONED_SUBJECT_ANY
        asked = payload.get("text").strip() if isinstance(payload.get("text"), str) else ""
        day = _asked_day(payload.get("asked_at"))
        if asked and day:
            paragraphs.append(ABANDONED_ASKED.format(day=day, text=asked))
        paragraphs.append(ABANDONED_BODY)
        cta, ask = ABANDONED_CTA, REASONS_ASK[kind]
    elif kind == "search_not_started":
        subject, cta, ask = NOT_STARTED_SUBJECT, NOT_STARTED_CTA, REASONS_ASK[kind]
        paragraphs.append(NOT_STARTED_BODY)
    elif kind == "search_feedback":
        subject, ask = FEEDBACK_SUBJECT, None
        saw = (FEEDBACK_SAW["model"].format(model=model) if model
               else FEEDBACK_SAW["asked" if first == "search_abandoned" else "none"])
        paragraphs.append(f"{FEEDBACK_INTRO.format(signer=cfg['signer'])} {saw} {FEEDBACK_ASK}")
        cta = ABANDONED_CTA if first == "search_abandoned" else NOT_STARTED_CTA
    else:
        raise ValueError(f"unknown remarketing kind: {kind}")

    reasons = [(label, links.feedback(row["id"], reason, owner=owner)) for reason, label in FEEDBACK_REASONS
               if reason != "wrong_search" or first == "search_abandoned"]
    reply = REPLY_LINE if cfg["reply_to"] else None
    unsubscribe = links.unsubscribe(row.get("unsubscribe_token"))
    signature = f"{cfg['signer']}, de Ese Auto"

    # The action comes first in the first email; in the follow-up, the question does.
    text: list[str] = ["Hola,", ""]
    for p in paragraphs:
        text += [p, ""]
    if kind != "search_feedback":
        text += [f"{cta}: {action}", "", ask]
    text += [f"- {label}: {url}" for label, url in reasons]
    if reply:
        text += ["", reply]
    if kind == "search_feedback":
        text += ["", FEEDBACK_STILL[first], action]
    text += ["", signature, "", "—", REMARKETING_FOOTER]
    if unsubscribe:
        text.append(f"{UNSUBSCRIBE}: {unsubscribe}")

    e = escape
    link = f'<a href="{e(action)}">{e(cta)}</a>'
    html: list[str] = ['<div style="font-family:Arial,Helvetica,sans-serif;font-size:15px;line-height:1.5;color:#222">',
                       "<p>Hola,</p>"]
    html += [f"<p>{e(p)}</p>" for p in paragraphs]
    if kind != "search_feedback":
        html += [f"<p>{link}</p>", f"<p>{e(ask)}</p>"]
    html.append("<ul>" + "".join(f'<li><a href="{e(url)}">{e(label)}</a></li>' for label, url in reasons) + "</ul>")
    if reply:
        html.append(f"<p>{e(reply)}</p>")
    if kind == "search_feedback":
        html.append(f"<p>{e(FEEDBACK_STILL[first])} {link}</p>")
    html.append(f"<p>{e(signature)}</p>")
    footer = e(REMARKETING_FOOTER)
    if unsubscribe:
        footer += f' <a href="{e(unsubscribe)}" style="color:#888">{e(UNSUBSCRIBE)}</a>'
    html.append(f'<p style="font-size:12px;color:#888">{footer}</p>')
    if pixel := links.open_pixel("m", row["id"]):
        html.append(f'<img src="{e(pixel)}" width="1" height="1" alt="" style="display:block;border:0">')
    html.append("</div>")
    return EmailMessage(subject, "\n".join(text), "\n".join(html), from_name=cfg["sender_name"],
                        reply_to=cfg["reply_to"], logo=False)

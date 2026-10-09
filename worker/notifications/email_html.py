"""Branded, photo-led email using inline styles and presentation tables.

Listing photos are public URLs; the small wordmark is a bundled CID attachment.
All essential information and calls to action remain text when images are off.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from html import escape
from typing import TYPE_CHECKING

from notifications.email_assets import LOGO_CONTENT_ID

if TYPE_CHECKING:
    from notifications.templates import Content, DigestItem


INK = "#14213d"
MUTED = "#4e5a73"
BORDER = "#d8dde6"
PANEL = "#f1f3f7"
YELLOW = "#ffe14d"
FONT = "Arial,Helvetica,sans-serif"
MAX_DIGEST_CARDS = 5
MONTHS = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
          "septiembre", "octubre", "noviembre", "diciembre")
AR = timezone(timedelta(hours=-3))


def _table(body: str, *, style: str = "", width: str = "100%") -> str:
    return (f'<table role="presentation" width="{width}" cellpadding="0" cellspacing="0" border="0" '
            f'style="border-collapse:collapse;font-family:{FONT};{style}">{body}</table>')


def _p(text: str, *, style: str = "") -> str:
    return f'<p style="margin:0;{style}">{escape(text)}</p>'


def _button(label: str, url: str) -> str:
    # Table and cell background remain usable in Outlook without modern CSS.
    return _table(
        f'<tr><td bgcolor="{YELLOW}" style="padding:16px 18px;border-radius:5px;text-align:center">'
        f'<a href="{escape(url)}" style="color:{INK};text-decoration:none;font-size:15px;line-height:22px;'
        f'font-weight:bold;display:block">{escape(label)} &rarr;</a></td></tr>')


def _badge(text: str, *, highlighted: bool = False, drop: bool = False) -> str:
    color = "#176344" if drop else INK
    background = "#edf7f1" if drop else YELLOW if highlighted else PANEL
    return (f'<span style="display:inline-block;padding:5px 9px;background:{background};color:{color};'
            f'border-radius:3px;font-size:11px;line-height:16px;font-weight:bold">{escape(text)}</span>')


def _photo(src: str, alt: str, url: str | None, *, width: int = 542) -> str:
    photo = (f'<img src="{escape(src)}" alt="{escape(alt)}" width="{width}" border="0" '
             f'style="display:block;width:100%;max-width:{width}px;height:auto;border:0;'
             f'background:{PANEL};color:{MUTED};font-size:13px;line-height:22px">')
    return f'<a href="{escape(url)}" style="text-decoration:none">{photo}</a>' if url else photo


def _thumbnails(images: list[str], name: str, url: str | None) -> str:
    cells = []
    for i, src in enumerate(images[:2]):
        if i:
            cells.append('<td width="8" style="font-size:0">&nbsp;</td>')
        cells.append('<td width="50%" valign="top">'
                     + _photo(src, f"Otra vista de {name}", url, width=267) + '</td>')
    return _table('<tr>' + ''.join(cells) + '</tr>', style="margin-top:10px;table-layout:fixed")


def _gallery(images: list[str], name: str, url: str | None) -> str:
    if not images:
        return _table(f'<tr><td bgcolor="{PANEL}" style="padding:26px 16px;text-align:center;'
                      f'color:{MUTED};font-size:13px;line-height:20px">Foto no disponible</td></tr>')
    return _photo(images[0], f"Foto de {name}", url)


def _digest_card(item: DigestItem) -> str:
    url = item.detail_url or item.url
    out = []
    out.append(f'<h3 style="margin:0;font-size:18px;line-height:24px;font-weight:bold">'
               f'<a href="{escape(url)}" style="color:{INK};text-decoration:none">'
               f'{escape(item.text)}</a></h3>')
    if item.previous_price:
        out.append(_p(f"Antes: {item.previous_price}",
                      style=f"margin-top:12px;color:{MUTED};font-size:13px;text-decoration:line-through"))
    if item.price:
        out.append(_p(item.price, style=f"margin-top:8px;font-size:24px;line-height:31px;font-weight:bold;color:{INK}"))
        out.append(_p("Precio publicado", style=f"font-size:11px;line-height:18px;color:{MUTED}"))
    for detail in item.details:
        out.append(_p(detail, style=f"margin-top:6px;color:{MUTED};font-size:12px;line-height:19px"))
    if item.score is not None:
        out.append(_p(f"Puntaje de oportunidad: {item.score}/100",
                      style=f"margin-top:8px;font-size:12px;line-height:19px;color:{MUTED}"))
    label = "Ver auto en Ese Auto" if item.detail_url else "Ver publicación"
    photo = _gallery(item.images[:1], item.text, url)
    badge = (_badge(item.badge, highlighted=item.highlighted, drop=bool(item.previous_price))
             if item.badge else "")
    card = _table('<tr><td width="34%" valign="top">' + photo
                  + '</td><td width="16" style="font-size:0">&nbsp;</td>'
                  + '<td valign="top">' + "\n".join(out) + '</td></tr>',
                  style="margin-top:12px;table-layout:fixed")
    return _table(
        '<tr><td style="padding:18px;border:1px solid ' + BORDER + '">' + badge + card
        + '<div style="margin-top:18px">' + _button(label, url) + '</div>'
        + '</td></tr><tr><td height="16" style="font-size:0;line-height:0">&nbsp;</td></tr>')


def _email_note(note: str) -> str:
    # The information remains legible in mail clients without an emoji font.
    for old, new in (("🔎 ", "Búsqueda: "), ("📍 ", ""), ("🏷 ", "Fuente: "),
                     ("⚠️ ", "A tener en cuenta: "), ("💳 ", ""),
                     ("Opportunity Score ", "Puntaje de oportunidad: ")):
        note = note.replace(old, new)
    return note


def render(c: Content, *, kind: str, now: datetime, day: str | None,
           detail_url: str | None, app_url: str | None, unsubscribe_url: str | None,
           footer: str, unsubscribe_label: str) -> str:
    try:
        when = date.fromisoformat(day) if day else now.astimezone(AR).date()
    except (TypeError, ValueError):
        when = now.astimezone(AR).date()
    date_label = f"{when.day} de {MONTHS[when.month - 1]} de {when.year}"
    digest = kind == "digest"
    count = sum(len(rows) for _, rows in c.sections)
    title = "Tu resumen del día" if digest else c.header.split(" ", 1)[-1]
    intro = {
        "opportunity": "Encontramos una oportunidad para tu búsqueda.",
        "new_match": "Apareció un auto que coincide con tu búsqueda.",
        "price_drop": "Un auto que seguís tiene un nuevo precio publicado.",
        "listing_gone": "Hay un cambio en una publicación que seguías.",
    }.get(kind, "Las novedades de tus búsquedas, en un solo lugar.")
    preheader = (f"{count} novedad{'es' if count != 1 else ''} en tus búsquedas. Mirá las fotos y revisá los cambios en Ese Auto."
                 if digest else f"{c.vehicle or ''}. {c.price or ''}. Mirá las fotos y el análisis en Ese Auto.")
    logo = (f'<img src="cid:{LOGO_CONTENT_ID}" alt="S Auto" width="132" height="38" border="0" '
            f'style="display:block;width:132px;height:38px;border:0;font-size:26px;font-weight:bold;color:{INK}">')
    if app_url:
        logo = f'<a href="{escape(app_url)}" style="text-decoration:none">{logo}</a>'
    header = _table(
        f'<tr><td bgcolor="{YELLOW}" height="5" style="font-size:0;line-height:0">&nbsp;</td></tr>'
        f'<tr><td class="pad" style="padding:22px 28px;border-bottom:1px solid {BORDER}">'
        + logo + _p("Decinos cuál. Te avisamos cuando aparezca.",
                    style=f"margin-top:8px;font-size:12px;line-height:19px;color:{MUTED}")
        + '</td></tr>')

    body = [_p("RESUMEN DIARIO" if digest else "TU BÚSQUEDA, AL DÍA",
               style=f"font-size:10px;line-height:16px;letter-spacing:2px;font-weight:bold;color:{MUTED}"),
            _p(date_label, style=f"margin-top:6px;font-size:12px;line-height:18px;color:{MUTED}"),
            f'<h1 style="margin:16px 0 0;font-size:30px;line-height:36px;letter-spacing:-1px;'
            f'font-weight:bold;color:{INK}">{escape(title)}</h1>']
    if digest:
        body.append(_p(f"{count} novedad{'es' if count != 1 else ''} para revisar.",
                       style=f"margin-top:12px;font-size:17px;line-height:25px;font-weight:bold;color:{INK}"))
    body.append(_p(intro, style=f"margin-top:10px;font-size:14px;line-height:22px;color:{MUTED}"))
    if digest and app_url:
        body.append(f'<p style="margin:16px 0 0;font-size:14px;line-height:22px"><a href="{escape(app_url)}" '
                    f'style="color:{INK};font-weight:bold;text-decoration:underline">Abrir mis búsquedas &rarr;</a></p>')
    if c.vehicle:
        url = detail_url or (c.link.url if c.link else None)
        body.append('<div style="margin-top:24px">' + _gallery(c.images, c.vehicle, url) + '</div>')
        body.append(_p(c.vehicle, style="margin-top:20px;font-size:23px;line-height:30px;font-weight:bold"))
        if c.previous_price:
            body.append(_p(f"Antes: {c.previous_price}",
                           style=f"margin-top:14px;color:{MUTED};font-size:14px;text-decoration:line-through"))
        if c.price:
            body.append(_p(c.price, style=f"margin-top:10px;font-size:32px;line-height:40px;font-weight:bold;color:{INK}"))
            body.append(_p("Precio publicado", style=f"font-size:11px;line-height:18px;color:{MUTED}"))
    price_lines = {c.price, f"Ahora: {c.price}", f"Antes: {c.previous_price}"}
    for line in c.lines:
        if line in price_lines:
            continue
        if line.startswith("Opportunity Score "):
            line = line.replace("Opportunity Score ", "Puntaje de oportunidad: ", 1)
        emphasis = f"padding:10px 12px;background:{YELLOW};font-weight:bold;color:{INK};" if "debajo de publicaciones comparables" in line else ""
        body.append(_p(line, style=f"margin-top:10px;font-size:14px;line-height:22px;color:{MUTED};{emphasis}"))
    if c.link:
        body.append('<div style="margin-top:24px">' + _button(c.link.label, c.link.url) + '</div>')
        if detail_url:
            body.append(_p("Mirá el análisis, guardá el auto y accedé a la publicación original.",
                           style=f"margin-top:10px;font-size:12px;line-height:19px;color:{MUTED}"))
    if c.vehicle and len(c.images) > 1:
        body.append(_p("Otras fotos de la publicación", style=f"margin-top:24px;font-size:12px;color:{MUTED}"))
        body.append(_thumbnails(c.images[1:], c.vehicle, detail_url or (c.link.url if c.link else None)))
    # Bound long digests only when the app gives access to the rest. The text
    # alternative always includes every item and its tracked detail link.
    remaining = MAX_DIGEST_CARDS if app_url else count
    for section, rows in c.sections:
        visible = rows[:remaining]
        if not visible:
            continue
        body.append(_table(
            f'<tr><td style="padding:28px 0 12px;font-size:16px;line-height:23px;font-weight:bold;color:{INK}">'
            f'{escape(section)} <span style="font-size:12px;color:{MUTED};font-weight:normal">'
            f'({len(rows)})</span></td></tr>'))
        body.extend(_digest_card(row) for row in visible)
        remaining -= len(visible)
    if digest and app_url and count > MAX_DIGEST_CARDS:
        body.append(_p(f"Mostramos {MAX_DIGEST_CARDS} de {count} novedades. Revisá todas en tus búsquedas.",
                       style=f"margin-top:10px;font-size:14px;line-height:22px;color:{MUTED}"))
    if c.notes:
        notes = "\n".join(_p(_email_note(x), style=f"margin-top:8px;font-size:12px;line-height:20px;color:{MUTED}")
                          for x in c.notes)
        body.append('<div style="margin-top:22px;padding-top:12px;border-top:1px solid '
                    f'{BORDER}">' + notes + '</div>')
    if digest and app_url:
        body.append('<div style="margin-top:18px">' + _button("Ver mis búsquedas en Ese Auto", app_url) + '</div>')
    elif app_url:
        body.append(f'<p style="margin:20px 0 0;font-size:12px;line-height:20px"><a href="{escape(app_url)}" '
                    f'style="color:{MUTED};text-decoration:underline">Ver mis búsquedas</a></p>')

    foot = [_p("Menos buscar. Más encontrar.",
               style=f"font-size:16px;line-height:23px;font-weight:bold;color:{INK}"),
            _p(footer, style=f"margin-top:10px;font-size:11px;line-height:18px;color:{MUTED}")]
    if unsubscribe_url:
        foot.append(f'<p style="margin:12px 0 0"><a href="{escape(unsubscribe_url)}" '
                    f'style="color:{MUTED};font-size:11px;line-height:18px;text-decoration:underline">'
                    f'{escape(unsubscribe_label)}</a></p>')
    inner = header + _table('<tr><td class="pad" style="padding:28px;overflow-wrap:anywhere;word-break:break-word">'
                            + "\n".join(body) + '</td></tr>')
    inner += _table(f'<tr><td class="pad" bgcolor="{PANEL}" style="padding:22px 28px;border-top:1px solid {BORDER}">'
                    + "\n".join(foot) + '</td></tr>')
    wrapper = _table('<tr><td class="outer" align="center" style="padding:24px 12px">'
                     '<!--[if mso]><table role="presentation" width="600"><tr><td><![endif]-->'
                     '<div style="max-width:600px;margin:0 auto">'
                     + _table(f'<tr><td bgcolor="#ffffff" style="border:1px solid {BORDER}">{inner}</td></tr>')
                     + '</div><!--[if mso]></td></tr></table><![endif]--></td></tr>',
                     style=f"background:{PANEL};")
    return "\n".join([
        '<!doctype html><html lang="es"><head><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width,initial-scale=1">',
        '<meta name="color-scheme" content="light"><meta name="supported-color-schemes" content="light">',
        f'<title>{escape(c.subject)}</title>',
        '<style>@media only screen and (max-width:480px){.pad{padding-left:20px!important;'
        'padding-right:20px!important}.outer{padding:12px 6px!important}}</style></head>',
        f'<body style="margin:0;padding:0;background:{PANEL};font-family:{FONT};color:{INK};'
        '-webkit-text-size-adjust:100%;-ms-text-size-adjust:100%">',
        '<div style="display:none;font-size:1px;color:#f1f3f7;line-height:1px;max-height:0;max-width:0;'
        f'opacity:0;overflow:hidden;mso-hide:all" aria-hidden="true">{escape(preheader)}</div>',
        wrapper, '</body></html>',
    ])

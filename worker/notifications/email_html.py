"""Guía email layout: inline styles and presentation tables for mail clients.

The content, tracked URLs and plain-text alternative belong to templates.py.
This renderer only adds visual hierarchy; it needs no remote fonts or images.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from html import escape
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from notifications.templates import Content, DigestItem


INK = "#14213d"
MUTED = "#4e5a73"
BORDER = "#d8dde6"
PANEL = "#f1f3f7"
YELLOW = "#ffe14d"
FONT = "Arial,Helvetica,sans-serif"
MONTHS = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
          "septiembre", "octubre", "noviembre", "diciembre")
AR = timezone(timedelta(hours=-3))


def _table(body: str, *, style: str = "", width: str = "100%") -> str:
    return (f'<table role="presentation" width="{width}" cellpadding="0" cellspacing="0" border="0" '
            f'style="border-collapse:collapse;font-family:{FONT};{style}">{body}</table>')


def _p(text: str, *, style: str = "") -> str:
    return f'<p style="margin:0;{style}">{escape(text)}</p>'


def _button(label: str, url: str) -> str:
    # Cell background/padding also survive clients that ignore anchor padding.
    return _table(
        f'<tr><td bgcolor="{INK}" style="padding:13px 20px;border-radius:4px;text-align:center">'
        f'<a href="{escape(url)}" style="color:#ffffff;text-decoration:none;font-size:14px;'
        f'font-weight:bold;display:block">{escape(label)}</a></td></tr>', width="auto")


def _badge(text: str, *, highlighted: bool = False, drop: bool = False) -> str:
    color = "#176344" if drop else INK
    background = "#edf7f1" if drop else YELLOW if highlighted else PANEL
    return (f'<span style="display:inline-block;padding:5px 9px;background:{background};color:{color};'
            f'border-radius:3px;font-size:11px;line-height:16px;font-weight:bold">{escape(text)}</span>')


def _digest_card(item: DigestItem) -> str:
    out = []
    if item.badge:
        out.append(_badge(item.badge, highlighted=item.highlighted, drop=bool(item.previous_price)))
    out.append(f'<p style="margin:12px 0 0;font-size:18px;line-height:25px;font-weight:bold">'
               f'<a href="{escape(item.url)}" style="color:{INK};text-decoration:none">'
               f'{escape(item.text)}</a></p>')
    if item.previous_price:
        out.append(_p(f"Antes: {item.previous_price}",
                      style=f"margin-top:12px;color:{MUTED};font-size:13px;text-decoration:line-through"))
    if item.price:
        out.append(_p(item.price, style=f"margin-top:6px;font-size:25px;line-height:32px;font-weight:bold;color:{INK}"))
        out.append(_p("Precio publicado", style=f"font-size:11px;color:{MUTED}"))
    for detail in item.details:
        out.append(_p(detail, style=f"margin-top:8px;color:{MUTED};font-size:13px;line-height:20px"))
    if item.score is not None:
        out.append(_p(f"Puntaje: {item.score}/100", style=f"margin-top:8px;font-size:11px;color:{MUTED}"))
    out.append(f'<p style="margin:16px 0 0"><a href="{escape(item.url)}" '
               f'style="display:inline-block;padding:4px 0;color:{INK};font-size:13px;'
               'font-weight:bold;text-decoration:underline">Ver publicación &rarr;</a></p>')
    return _table('<tr><td bgcolor="#ffffff" style="padding:18px;border:1px solid '
                  f'{BORDER};border-left:3px solid {YELLOW if item.highlighted else BORDER}">'
                  + "\n".join(out) + '</td></tr><tr><td height="12" style="font-size:0;line-height:0">&nbsp;</td></tr>')


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
    preheader = (f"{count} novedad{'es' if count != 1 else ''} en tus búsquedas. "
                 "Publicaciones nuevas, cambios de precio y avisos que ya no están disponibles."
                 if digest else c.subject)
    header = _table(
        f'<tr><td style="padding:24px 28px;border-bottom:1px solid {BORDER}">'
        f'<p style="margin:0;font-size:24px;line-height:30px;font-weight:bold;letter-spacing:-1px;color:{INK}">'
        'ese auto<span style="color:#75809a">.</span></p>'
        f'<p style="margin:4px 0 0;font-size:12px;color:{MUTED}">Tu búsqueda, al día.</p></td></tr>')

    body = [_p("RESUMEN DIARIO" if digest else "TUS ALERTAS",
               style=f"font-size:10px;letter-spacing:2px;font-weight:bold;color:{MUTED}"),
            _p(date_label, style=f"margin-top:8px;font-size:12px;color:{MUTED}"),
            f'<h1 style="margin:16px 0 0;font-size:30px;line-height:36px;letter-spacing:-1px;'
            f'font-weight:bold;color:{INK}">{escape(title)}</h1>']
    if digest:
        body.append(_p(f"{count} novedad{'es' if count != 1 else ''} para revisar.",
                       style=f"margin-top:12px;font-size:16px;color:{MUTED}"))
        body.append(_p("Reunimos los cambios de tus búsquedas para que puedas verlos de un vistazo.",
                       style=f"margin-top:8px;font-size:14px;line-height:22px;color:{MUTED}"))
    if c.vehicle:
        body.append(_p(c.vehicle, style="margin-top:24px;font-size:22px;line-height:29px;font-weight:bold"))
    if c.lines:
        for line in c.lines:
            body.append(_p(line, style=f"margin-top:12px;font-size:14px;line-height:22px;color:{MUTED}"))
    if c.link:
        body.append('<div style="margin-top:22px">' + _button(c.link.label, c.link.url) + '</div>')
    if detail_url:
        body.append(f'<p style="margin:14px 0 0;font-size:13px"><a href="{escape(detail_url)}" '
                    f'style="color:{INK};text-decoration:underline">Ver en Ese Auto &rarr;</a></p>')
    for section, rows in c.sections:
        body.append(_table(
            f'<tr><td style="padding:28px 0 12px;font-size:16px;line-height:23px;font-weight:bold;color:{INK}">'
            f'{escape(section)} <span style="font-size:12px;color:{MUTED};font-weight:normal">'
            f'({len(rows)})</span></td></tr>'))
        body.extend(_digest_card(row) for row in rows)
    if c.notes:
        notes = "\n".join(_p(x, style=f"margin-top:8px;font-size:13px;line-height:20px;color:{MUTED}")
                          for x in c.notes)
        body.append('<div style="margin-top:24px;padding-top:16px;border-top:1px solid '
                    f'{BORDER}">' + notes + '</div>')
    if digest and app_url:
        body.append('<div style="margin-top:18px">' + _button("Ver mis búsquedas", app_url) + '</div>')

    foot = [_p(footer, style=f"font-size:12px;line-height:19px;color:{MUTED}")]
    if unsubscribe_url:
        foot.append(f'<p style="margin:12px 0 0"><a href="{escape(unsubscribe_url)}" '
                    f'style="color:{MUTED};font-size:12px;text-decoration:underline">'
                    f'{escape(unsubscribe_label)}</a></p>')
    inner = header + _table('<tr><td style="padding:28px;overflow-wrap:anywhere;word-break:break-word">'
                            + "\n".join(body) + '</td></tr>')
    inner += _table(f'<tr><td bgcolor="{PANEL}" style="padding:22px 28px;border-top:1px solid {BORDER}">'
                    + "\n".join(foot) + '</td></tr>')
    wrapper = _table('<tr><td align="center" style="padding:24px 12px">'
                     '<!--[if mso]><table role="presentation" width="600"><tr><td><![endif]-->'
                     '<div style="max-width:600px;margin:0 auto">'
                     + _table(f'<tr><td bgcolor="#ffffff" style="border:1px solid {BORDER}">{inner}</td></tr>')
                     + '</div><!--[if mso]></td></tr></table><![endif]--></td></tr>',
                     style=f"background:{PANEL};")
    return "\n".join([
        '<!doctype html><html lang="es"><head><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width,initial-scale=1">',
        '<meta name="color-scheme" content="light"><meta name="supported-color-schemes" content="light">',
        f'<title>{escape(c.subject)}</title></head>',
        f'<body style="margin:0;padding:0;background:{PANEL};font-family:{FONT};color:{INK};'
        '-webkit-text-size-adjust:100%;-ms-text-size-adjust:100%">',
        '<div style="display:none;font-size:1px;color:#f1f3f7;line-height:1px;max-height:0;max-width:0;'
        f'opacity:0;overflow:hidden;mso-hide:all" aria-hidden="true">{escape(preheader)}</div>',
        wrapper, '</body></html>',
    ])

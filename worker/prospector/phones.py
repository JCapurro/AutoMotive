"""Argentine WhatsApp numbers: finding them in a listing's text and normalizing
them to the wa.me form (549 + area code + number, 13 digits). Pure.

Only numbers the seller wrote in their own listing (or, for a business, its
public channels, see lookup.py). The text is full of prices, years and
mileages, so a run of digits is a phone only when it normalizes to a valid
Argentine number AND either a contact word is next to it or it carries the
+54 / 9 / 15 shape of a phone.
"""
from __future__ import annotations

import re
from collections import Counter
from typing import Iterable

_RUN = re.compile(r"\+?\d[\d \t().\-/]{6,22}\d")
_CONTACT = re.compile(
    r"(whats\s*app|whatsapp|wsp|wpp|wapp|watsap|wasap|what|cel(?:ular)?|tel(?:[eé]fono)?|llam[aá]|"
    r"contacto|comunicate|comunicarse|escrib[ií]|mensaje|consultas?|inbox|📱|📞|☎|wa\.me)",
    re.IGNORECASE)
_MONEY_BEFORE = re.compile(r"(\$|u\$s|us\$|usd|ars|pesos|d[oó]lares)\s*$", re.IGNORECASE)
_AFTER_NOT_PHONE = re.compile(r"^\s*(km|kms|kil[oó]metros|cc|hp|cv|mil\b|millones|usd|u\$s|pesos)", re.IGNORECASE)
_THOUSANDS = re.compile(r"^\d{1,3}(\.\d{3})+$")
_WA_LINK = re.compile(r"(?:wa\.me/|api\.whatsapp\.com/send\?phone=|whatsapp\.com/send/?\?phone=)\+?(\d{10,15})")


def normalize(raw: str | None) -> str | None:
    """'549' + 10 digits, or None when it is not an Argentine number.
    Same rules as the manual generator: drops 00, 54, the mobile 9, the trunk
    0 and the 15 after the area code."""
    d = re.sub(r"\D", "", raw or "")
    if not d:
        return None
    if d.startswith("00"):
        d = d[2:]
    if d.startswith("54"):
        d = d[2:]
    if d.startswith("9") and len(d) == 11:
        d = d[1:]
    if d.startswith("0"):
        d = d[1:]
    if len(d) == 12:
        d = re.sub(r"^(\d{2,4}?)15", r"\1", d, count=1)
    if len(d) != 10 or d[0] not in "123":
        return None
    # Area code 11 (AMBA) is followed by 8 digits that never start with 0 or 1.
    if d.startswith("11") and d[2] in "01":
        return None
    if len(set(d)) <= 2:          # 1111111111, 1212121212
        return None
    return "549" + d


def _phone_shaped(chunk: str) -> bool:
    compact = re.sub(r"[\s().\-/]", "", chunk)
    return compact.startswith(("+54", "54", "0")) or bool(re.search(r"(^|\D)15[\s.\-]?\d{3,4}[\s.\-]?\d{4}", chunk))


def find_in_text(text: str | None) -> list[str]:
    """Every phone written in a listing's text, normalized, in order, without repeats."""
    if not text:
        return []
    out: list[str] = []
    for m in _WA_LINK.finditer(text):
        n = normalize(m.group(1))
        if n and n not in out:
            out.append(n)
    for m in _RUN.finditer(text):
        chunk = m.group(0).strip()
        if _THOUSANDS.fullmatch(chunk):
            continue
        before = text[max(0, m.start() - 40):m.start()]
        after = text[m.end():m.end() + 14]
        if _MONEY_BEFORE.search(before[-8:]) or _AFTER_NOT_PHONE.match(after):
            continue
        n = normalize(chunk)
        if not n:
            continue
        if not (_CONTACT.search(before) or _CONTACT.search(after) or _phone_shaped(chunk)):
            continue
        if n not in out:
            out.append(n)
    return out


def best_of(texts: Iterable[str | None], *, banned: frozenset[str] = frozenset()) -> str | None:
    """The number a seller repeats the most across their listings (first seen wins a tie)."""
    counts: Counter[str] = Counter()
    order: list[str] = []
    for text in texts:
        for n in find_in_text(text):
            if n in banned:
                continue
            counts[n] += 1
            if n not in order:
                order.append(n)
    if not counts:
        return None
    return max(order, key=lambda n: (counts[n], -order.index(n)))


# RosarioGarage shows the seller's WhatsApp on the listing page as a wa.me link
# whose text greets the seller («Hola *Nombre*, te contacto por...»); the
# site's own numbers are other wa.me links on every page.
_RG_SELLER_LINK = re.compile(r"wa\.me/(\d{10,15})\?text=Hola[^\"'<>]{0,200}?te contacto", re.IGNORECASE)


def from_rosariogarage_page(html: str) -> str | None:
    for m in _RG_SELLER_LINK.finditer(html or ""):
        n = normalize(m.group(1))
        if n:
            return n
    return None


def wa_link(number: str, text: str) -> str:
    from urllib.parse import quote
    return f"https://wa.me/{number}?text={quote(text)}"

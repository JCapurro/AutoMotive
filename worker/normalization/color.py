"""Color of a listing (docs/PLAN_FILTRO_COLOR.md, sección 8).

One list of codes, in the same order everywhere: the database's check, the
worker, the LLM schema and the web form. Gris and plata are one group:
sellers don't tell them apart either.

How a listing's color is decided, first source that has one:

1. **source**: the value the page declares (Mercado Libre's "Color", Kavak's
   JSON-LD `color`, Randazzo's "Color", Autocosmos's `itemprop="color"` and
   the "… color Negro Vulcano precio …" of its cards), mapped by `canonical`.
2. **text**: the title or the description, only with an anchor ("color
   blanco", "color: gris", "pintura roja"), never a bare word: "interior
   negro" or "llantas negras" say nothing about the paint. Two anchored
   colors that disagree say nothing either.
3. **vision**: the AI looks at the photos (pipeline's color pass, not here).

The result goes to `listings.color` (a code or null) and how it was decided
to `listings.attributes._color` (`build`). Precedence is source > text >
vision: the photos never overwrite what the ad says, and a source value that
arrives later does overwrite the photos (`merge_color`). Filling the color is
no news about the car: it is not a key attribute (normalization/listing.py).
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping

from normalization.normalize import normalize_text


CODES = ("blanco", "negro", "gris", "azul", "rojo", "verde", "beige", "otro")
# What the search form shows, in CODES order.
LABELS = {
    "blanco": "Blanco", "negro": "Negro", "gris": "Gris o plata", "azul": "Azul o celeste",
    "rojo": "Rojo o bordó", "verde": "Verde", "beige": "Beige o marrón", "otro": "Otro color",
}
# The color inside a sentence: «blanco · dato del aviso», «puede ser verde».
NAMES = {
    "blanco": "blanco", "negro": "negro", "gris": "gris", "azul": "azul", "rojo": "rojo",
    "verde": "verde", "beige": "beige", "otro": "otro color",
}

# attributes._color.method, strongest first.
METHODS = ("source", "text", "vision")
_RANK = {"source": 3, "text": 2, "vision": 1}
CONFIDENCES = ("alta", "media", "baja")
# attributes._color.v: bump when the shape of _color changes.
VERSION = 1
# A vision candidate counts for a search when its probability is at least
# this (Fase 0, variante multi3b: docs/COLOR.md).
CANDIDATE_MIN_PROB = 30

# Raw attributes that carry the source's color, as the collectors store them
# (Listing.atributos, listings.attributes): Mercado Libre's spec table,
# Randazzo's properties and Autocosmos ("Color"), Kavak's JSON-LD ("color").
SOURCE_ATTRIBUTE_KEYS = ("Color", "color", "Color exterior")


# ---------------------------------------------------------------------------
# Raw values → codes
# ---------------------------------------------------------------------------

# One word, accents off and lower case. Manufacturer names put the color word
# first («Blanco Oxford», «Plata Sirius», «Gris Plata», «Azul Mónaco»), or a
# known word somewhere («Metalizado Gris», «Summit White»).
WORDS = {
    # blanco
    "blanco": "blanco", "blanca": "blanco", "blancos": "blanco", "blancas": "blanco",
    "white": "blanco", "branco": "blanco", "branca": "blanco", "bianco": "blanco",
    "marfil": "blanco", "perla": "blanco", "perlado": "blanco", "perlada": "blanco",
    "banquise": "blanco", "nieve": "blanco",
    # negro
    "negro": "negro", "negra": "negro", "negros": "negro", "negras": "negro",
    "black": "negro", "noir": "negro", "nero": "negro", "nera": "negro", "preto": "negro",
    "vulcano": "negro",
    # gris o plata
    "gris": "gris", "girs": "gris", "grises": "gris", "grey": "gris", "gray": "gris",
    "plata": "gris", "plateado": "gris", "plateada": "gris", "plateados": "gris",
    "silver": "gris", "prata": "gris", "cinza": "gris", "grafito": "gris", "graphite": "gris",
    "plomo": "gris", "titanio": "gris", "acero": "gris", "aluminio": "gris", "aluminium": "gris",
    "silverstone": "gris", "chumbo": "gris", "platino": "gris",
    # azul o celeste
    "azul": "azul", "azules": "azul", "azulado": "azul", "azulada": "azul", "celeste": "azul",
    "blue": "azul", "petroleo": "azul", "turquesa": "azul", "marino": "azul",
    # rojo o bordó
    "rojo": "rojo", "roja": "rojo", "rojos": "rojo", "red": "rojo", "rosso": "rojo",
    "vermelho": "rojo", "bordo": "rojo", "bordeaux": "rojo", "burdeos": "rojo",
    "granate": "rojo", "vino": "rojo",
    # verde
    "verde": "verde", "verdes": "verde", "green": "verde", "oliva": "verde",
    # beige o marrón
    "beige": "beige", "bege": "beige", "marron": "beige", "brown": "beige", "cafe": "beige",
    "champagne": "beige", "champan": "beige", "dorado": "beige", "dorada": "beige",
    "oro": "beige", "bronce": "beige", "cobre": "beige", "ocre": "beige", "arena": "beige",
    "crema": "beige", "habano": "beige", "chocolate": "beige", "tostado": "beige",
    # otro
    "amarillo": "otro", "amarilla": "otro", "naranja": "otro", "violeta": "otro",
    "rosa": "otro", "rosado": "otro", "lila": "otro", "fucsia": "otro", "purpura": "otro",
    "yellow": "otro", "orange": "otro", "bicolor": "otro", "multicolor": "otro", "otro": "otro",
}
# Two words that say otherwise than their first one.
PHRASES = {
    "perla nera": "negro", "nero perla": "negro", "negro perla": "negro",
    "verde petroleo": "verde", "azul petroleo": "azul",
}


def _words(raw: str | None) -> list[str]:
    return re.sub(r"[^a-z]+", " ", normalize_text(raw)).split()


def _code(words: list[str], *, anywhere: bool) -> str | None:
    if not words:
        return None
    if len(words) > 1 and (code := PHRASES.get(" ".join(words[:2]))):
        return code
    if words[0] in WORDS:
        return WORDS[words[0]]
    if anywhere:
        for w in words[1:]:
            if w in WORDS:
                return WORDS[w]
            if "blue" in w:          # «Bluemoon», «Deepblue»
                return "azul"
    return None


def canonical(raw: Any) -> str | None:
    """A source's color value («Blanco Oxford», «Plata Sirius», «Bordó»,
    «Champagne», a code already) as a code; None when it names no color."""
    if raw is None or isinstance(raw, bool):
        return None
    return _code(_words(str(raw)), anywhere=True)


def is_code(value: Any) -> bool:
    return isinstance(value, str) and value in CODES


# ---------------------------------------------------------------------------
# The source's value and the text
# ---------------------------------------------------------------------------

def source_color(attrs: Mapping[str, Any] | None) -> tuple[str, str] | None:
    """(code, raw) of the color the page declares, among a listing's raw
    attributes (Listing.atributos or listings.attributes), or None."""
    for key in SOURCE_ATTRIBUTE_KEYS:
        value = (attrs or {}).get(key)
        if value in (None, "") or isinstance(value, (dict, list)):
            continue
        if code := canonical(value):
            return code, str(value).strip()
    return None


# An anchor, maybe "exterior" and a separator, then the words after it.
# The words are a lookahead: «color blanco, techo color negro» has two anchors.
_ANCHOR = re.compile(r"(?<![a-z])(?:color|pintura)(?![a-z])(?:\s+exterior(?![a-z]))?\s*[:=\-]?\s*"
                     r"(?:(?:es|en)\s+)?(?=([a-z]+(?:\s+[a-z]+)?))")
# Words right before the anchor that make it about something else than the
# paint: «interior color negro», «llantas color negro», «cámara color».
_OTHER_PART = frozenset({
    "interior", "interiores", "tapizado", "tapizados", "tapiceria", "tapizada", "cuero", "tela",
    "butaca", "butacas", "asiento", "asientos", "alfombra", "alfombras", "volante", "techo",
    "llanta", "llantas", "rueda", "ruedas", "espejo", "espejos", "manija", "manijas",
    "paragolpe", "paragolpes", "detalle", "detalles", "vinilo", "ploteo", "ploteado", "capota",
    "lona", "camara", "pantalla", "display", "radio", "multimedia", "luz", "luces", "faros",
    "tablero", "consola", "cinturones", "funda", "fundas", "cubre",
})
# The first word after the anchor that sends it elsewhere: «color interior».
_OTHER_AFTER = frozenset({"interior", "interiores", "de", "del", "tapizado", "a"})


def from_text(*texts: str | None) -> tuple[str, str] | None:
    """(code, the anchored words) when the title or description state the
    paint with an anchor: «color blanco», «color: gris», «pintura roja».
    A bare word never counts, nor an anchor about another part (interior,
    tapizado, llantas, techo…). Two anchored colors that disagree: None."""
    found: dict[str, str] = {}
    for text in texts:
        plain = re.sub(r"[^a-z:=\-]+", " ", normalize_text(text))
        for m in _ANCHOR.finditer(plain):
            after = m.group(1).split()
            if not after or after[0] in _OTHER_AFTER:
                continue
            before = plain[max(0, m.start() - 40):m.start()].split()[-3:]
            if any(w.strip(":=-") in _OTHER_PART for w in before):
                continue
            if code := _code(after, anywhere=False):
                found.setdefault(code, f"{m.group(0).strip()} {' '.join(after)}")
    if len(found) != 1:
        return None
    (code, raw), = found.items()
    return code, raw


# ---------------------------------------------------------------------------
# attributes._color
# ---------------------------------------------------------------------------

def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def build(method: str, raw: str | None = None, *, confidence: str | None = None,
          model: str | None = None, candidates: Iterable[Mapping[str, Any]] | None = None,
          photos: int | None = None, result: str | None = None, at: str | None = None) -> dict[str, Any]:
    """attributes._color as the contract has it. `candidates` is the AI's
    whole list ({"color", "prob"}); `result` is "no_visible" when the photos
    don't show the car (color null)."""
    if method not in METHODS:
        raise ValueError(f"unknown color method {method!r}")
    out: dict[str, Any] = {
        "method": method, "raw": raw, "confidence": confidence, "model": model, "v": VERSION,
        "candidates": [{"color": c["color"], "prob": c["prob"]} for c in candidates] if candidates else None,
        "photos": photos, "at": at or _now(),
    }
    if result is not None:
        out["result"] = result
    return out


def rank(attrs_color: Mapping[str, Any] | None) -> int:
    """Precedence of a _color: source 3 > text 2 > vision 1; none or unknown 0."""
    return _RANK.get((attrs_color or {}).get("method"), 0) if isinstance(attrs_color, Mapping) else 0


def merge_color(current_attrs_color: Mapping[str, Any] | None,
                new: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """The _color that stands when `new` arrives over `current_attrs_color`:
    `new` itself, or None when it must not overwrite (a weaker method: the
    photos never overwrite the source or the text, the text never the
    source). An equal method overwrites: a new reading of the same kind is
    newer (the detail page corrected the card, the photos changed)."""
    if not new or rank(new) == 0:
        return None
    if rank(new) < rank(current_attrs_color):
        return None
    return dict(new)


def resolve(attrs: Mapping[str, Any] | None, *texts: str | None) -> tuple[str | None, dict[str, Any] | None]:
    """The listing's color without the photos: the source's value, else the
    anchored text of `texts` (title, description). (code, _color) or (None, None)."""
    if found := source_color(attrs):
        return found[0], build("source", found[1])
    if found := from_text(*texts):
        return found[0], build("text", found[1])
    return None, None


# ---------------------------------------------------------------------------
# Searches
# ---------------------------------------------------------------------------

def wanted_colors(filters: Mapping[str, Any] | None) -> list[str]:
    """search_profiles.filters.colors, the known codes in it (CODES order);
    empty is no filter. search_filters_problem rejects anything else."""
    wanted = (filters or {}).get("colors")
    if isinstance(wanted, str):
        wanted = [wanted]
    if not isinstance(wanted, list):
        return []
    return [c for c in CODES if c in wanted]


def candidates(attrs_color: Mapping[str, Any] | None) -> list[tuple[str, int]]:
    """The vision candidates that count (prob >= CANDIDATE_MIN_PROB), most
    probable first: [(code, prob)]."""
    raw = (attrs_color or {}).get("candidates") if isinstance(attrs_color, Mapping) else None
    out: list[tuple[str, int]] = []
    for c in raw or []:
        if not isinstance(c, Mapping):
            continue
        code, prob = c.get("color"), c.get("prob")
        if is_code(code) and isinstance(prob, (int, float)) and not isinstance(prob, bool) \
                and prob >= CANDIDATE_MIN_PROB:
            out.append((code, int(prob)))
    return sorted(out, key=lambda cp: -cp[1])


def fits(color: str | None, attrs: Mapping[str, Any] | None, wanted: Iterable[str] | None) -> bool:
    """public.listing_color_fits: no filter, no color, the color wanted, or a
    candidate >= CANDIDATE_MIN_PROB wanted. What does not fail the rule."""
    wanted = set(wanted or ())
    if not wanted or not color:
        return True
    if color in wanted:
        return True
    return any(code in wanted for code, _ in candidates((attrs or {}).get("_color")))

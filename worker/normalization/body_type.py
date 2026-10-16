"""Body type of a listing (docs/CARROCERIA.md).

One list of codes, in the same order everywhere: the database's check, the
worker, the LLM schema and the web. No code is part of another, because
intelligence/matching.py's `_choice` compares with `in`.

How a listing's body type is decided (`resolve`), first rule that settles it:

1. Explicit words in the version or the title ("sedán", "pick up", "SW" but
   not "SW4", "weekend"…) and the submodel rules (Duster Oroch, Gol Country,
   Onix Plus…). They always win: the catalog resolves those submodels to the
   parent model.
2. The source's structured value (Listing.carroceria, raw or already a code;
   on Kavak the label its titles end in, "… Hatchback 2023", and a body word
   in the card's URL slug when it says nothing). Taken when the catalog
   doesn't know the model or lists the value among the model's body types.
   When the model has a single one, the catalog wins: sources are noisy
   (Mercado Libre labels the Spin an SUV, Kavak a hatchback). Randazzo's
   "Sedan" (hatches too) and "Wagon (obsoleta)" (SUVs) say nothing.
3. Doors (3p/5p hatchback, 4p sedán), only to choose among the model's body types.
4. The catalog, when the model has a single body type.
5. Otherwise, none.

"Camioneta", "4x4", "jeep", "familiar" and a lone "CD" (the radio) say nothing.
Only Autocosmos's "Familiar" segment is a rural. Only Kavak's URL slugs are
structured (Mercado Libre's are SEO keyword lists), and Autocity's carry the
doors: other URLs are not read.
"""
from __future__ import annotations

import re
from typing import Any, Iterable, Mapping
from urllib.parse import unquote, urlparse

from normalization.normalize import normalize_brand, normalize_text


CODES = ("sedan", "hatchback", "suv", "pickup", "rural", "monovolumen", "coupe", "convertible",
         "utilitario")
LABELS = {
    "sedan": "Sedán", "hatchback": "Hatchback", "suv": "SUV", "pickup": "Pick-up",
    "rural": "Rural", "monovolumen": "Monovolumen", "coupe": "Coupé",
    "convertible": "Convertible", "utilitario": "Utilitario",
}

# How resolve() settled it, stored in listings.attributes._body_type.method.
METHODS = ("keyword", "submodel", "source", "url", "doors", "catalog", "none")

# Raw attributes that carry the source's body type, when the collector
# didn't map it to Listing.carroceria: Mercado Libre's spec table, Kavak's
# JSON-LD, V6's "Categoría" and Randazzo's "Tipo de vehículo".
RAW_ATTRIBUTE_KEYS = ("Tipo de carrocería", "bodyType", "Categoría", "Tipo de vehículo")


# ---------------------------------------------------------------------------
# Structured values of each source
# ---------------------------------------------------------------------------

_SOURCE: dict[str, str | None] = {
    **{code: code for code in CODES},
    # Mercado Libre names (also V6's "Categoría", Kavak's JSON-LD bodyType).
    "hatch": "hatchback", "crossover": "suv", "off road": "suv", "offroad": "suv",
    "todoterreno": "suv", "todo terreno": "suv", "pick up": "pickup", "minivan": "monovolumen",
    "mono volumen": "monovolumen", "cabriolet": "convertible", "cabrio": "convertible",
    "roadster": "convertible", "furgon": "utilitario", "furgoneta": "utilitario", "van": "utilitario",
    "light truck": None,
    # Mercado Libre's VEHICLE_BODY_TYPE ids.
    "452758": "sedan", "479344": "hatchback", "452759": "suv", "452761": "suv", "452754": "suv",
    "452756": "pickup", "452760": "rural", "452752": "monovolumen", "452753": "monovolumen",
    "452749": "coupe", "452748": "convertible", "452757": "convertible", "452750": "utilitario",
    "452755": "utilitario", "452751": None,
    # Kavak slugs (card URL, /ar/usados/{carroceria}).
    "wagon": "rural", "station wagon": "rural", "camioneta": None, "comercial todoterreno": None,
    "lado de caida": None,
    # Autocosmos segments (?s=N and dfp_segmentoNick); 9 is "Familiar", which
    # only Autocosmos means as a rural (_BY_SOURCE).
    "1": "hatchback", "2": "sedan", "3": "utilitario", "4": "monovolumen", "5": "convertible",
    "6": "suv", "7": "pickup", "8": "coupe", "9": "rural",
    # Usados Santa Fe's tipo, Mardel's data-tipo: coarse groups say nothing.
    "auto": None, "autos": None, "automovil": None, "camionetas": None, "moto": None,
    "motos": None, "otro": None, "otros": None,
}
# Randazzo's "Pick-up B", "Sedan C": a tax/insurance segment after the body.
_SEGMENT_SUFFIX = re.compile(r"\s+[a-e]$")
# One source's own meaning of a value (the _source_key, also without the
# segment suffix), over _SOURCE; None says nothing. Randazzo files passenger
# hatchbacks (Argo, 208, Onix) under "Sedan" and SUVs (Kardian) under
# "Wagon (obsoleta)"; Car One's "Familiar" is no body type, Autocosmos's is.
_BY_SOURCE: dict[str, dict[str, str | None]] = {
    "autocosmos": {"familiar": "rural"},
    "gruporandazzo": {"sedan": None},
}
_OBSOLETE = re.compile(r"(?<![a-z])obsoleta(?![a-z])")


def _source_key(raw: Any) -> str:
    text = normalize_text(str(raw)) if raw is not None else ""
    return re.sub(r"[\s_/-]+", " ", text).strip()


def from_source(raw: Any, listing_source: str | None = None) -> str | None:
    """The code for a source's structured value (a name, a Mercado Libre id,
    a Kavak slug, an Autocosmos segment, a code), or None when it's unknown or
    only a coarse group ("Auto", "Camioneta", "Light Truck"). Labels outside
    the table (Car One, Randazzo, Autocity) go through the body words.
    `listing_source` (listings.source) applies that source's own meanings."""
    key = _source_key(raw)
    if not key:
        return None
    if listing_source == "gruporandazzo" and _OBSOLETE.search(key):
        return None
    own = _BY_SOURCE.get(listing_source or "", {})
    for candidate in (key, _SEGMENT_SUFFIX.sub("", key)):
        if candidate in own:
            return own[candidate]
    for candidate in (key, _SEGMENT_SUFFIX.sub("", key)):
        if candidate in _SOURCE:
            return _SOURCE[candidate]
    hit = _keyword(key)
    return hit[0] if hit else None


def raw_from_attributes(attributes: Mapping[str, Any] | None) -> str | None:
    """The source's body type as the page labels it, among a listing's raw
    attributes (Listing.atributos, or listings.attributes)."""
    for key in RAW_ATTRIBUTE_KEYS:
        value = (attributes or {}).get(key)
        if value not in (None, ""):
            return str(value)
    return None


# ---------------------------------------------------------------------------
# Words in the version, the title and the URL
# ---------------------------------------------------------------------------

def _words(pattern: str) -> re.Pattern[str]:
    return re.compile(rf"(?<![a-z0-9])(?:{pattern})(?![a-z0-9])")


# Order matters within one text: convertible > coupé (but "SUV coupé" is an
# SUV) > pick-up > utilitario > monovolumen > rural > SUV > sedán > hatchback.
# "Cross" is not an SUV (Etios Cross, Suran Cross; Corolla Cross is its own
# model), "HB" inside HB20 is not a hatch, and "van" is left to the catalog
# and the sources: it collides with model names. The coupé versions of SUVs
# (BMW X6, Mercedes GLC, Audi Q3 Sportback, Q4 e-tron Sportback, Cayenne
# Coupé) are SUVs: the model, at most two words that are not another model
# code ("a7", "q8"), then "coupé"/"sportback". Anything else would let a
# title's list of models through ("… Q5 Q8 A7 Sportback").
_SUV_COUPE_MODELS = r"x2|x4|x6|gla|gle|glc|q3|q4|q5|q8|e ?-?tron|cayenne|xc40|ex30"
_SUV_COUPE_WORD = r"(?: (?![a-z]{1,2}[0-9]{1,2}(?![a-z0-9]))[^ ]+){0,2}"
_KEYWORDS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("suv", _words(rf"suv coupe|coupe suv|(?:{_SUV_COUPE_MODELS}){_SUV_COUPE_WORD} (?:coupe|sportback)")),
    ("convertible", _words(r"cabrio|cabriolet|convertible|descapotable|roadster|spider|spyder")),
    ("coupe", _words(r"coupe|cupe|koup")),
    ("pickup", _words(r"pick ?-?up|doble cabina|cabina doble|cabina simple|cabina extendida|d/c|c/d|c/s"
                      r"|oroch")),
    ("utilitario", _words(r"furgon|furgoneta|utilitario|mini ?bus|combi|kombi")),
    ("monovolumen", _words(r"mono ?volumen|minivan|mpv|picasso|multispace|patagonica")),
    ("rural", _words(r"(?<!uso )(?<!zona )rural|wagon(?! r(?![a-z0-9]))|sw(?! ?4(?![a-z0-9]))"
                     r"|weekend|variant|sportwagen|cw")),
    ("suv", _words(r"suv|crossover|todo ?terreno")),
    ("sedan", _words(r"sedan")),
    ("hatchback", _words(r"hatchback|hatch|sportback|hb(?! ?20)")),
)

# Submodels the catalog resolves to the parent model: (make, model or None
# for any model of the make, words, code).
_SUBMODELS: tuple[tuple[str, str | None, re.Pattern[str], str], ...] = (
    ("renault", "duster", _words(r"oroch"), "pickup"),
    # A Palio Adventure is a Weekend that rarely says so.
    ("fiat", "palio", _words(r"weekend|adventure"), "rural"),
    ("fiat", "uno", _words(r"cargo"), "utilitario"),
    ("volkswagen", "gol", _words(r"country"), "rural"),
    ("volkswagen", "vento", _words(r"variant"), "rural"),
    ("volkswagen", "golf", _words(r"variant"), "rural"),
    ("citroen", "c4", _words(r"(?:grand )?picasso"), "monovolumen"),
    ("chevrolet", "onix", _words(r"plus"), "sedan"),
    ("chevrolet", "corsa", _words(r"classic"), "sedan"),
    # The Ka+ is the sedán, also titled "Ka S Plus 4p".
    ("ford", "ka", _words(r"ka ?\+|plus"), "sedan"),
    ("toyota", "etios", _words(r"cross"), "hatchback"),
    ("toyota", "hilux", _words(r"sw ?4"), "suv"),
    ("hyundai", "hb20", _words(r"hb ?20 ?s"), "sedan"),
    ("renault", "kangoo", _words(r"express|cargo"), "utilitario"),
    ("bmw", None, _words(r"touring"), "rural"),
    ("audi", None, _words(r"avant"), "rural"),
    # 206 CC, 207 CC, 307 CC: coupé-cabriolets ("1600 cc", "1600cc" are the engine).
    ("peugeot", None, _words(r"(?<![0-9]{4} )cc"), "convertible"),
)


def _keyword(text: str) -> tuple[str, str] | None:
    for code, pattern in _KEYWORDS:
        if m := pattern.search(text):
            if code == "sedan" and doors(text) in (3, 5):
                # "Sedán 5 puertas" is old Argentine for a 5-door car: the doors decide.
                continue
            return code, m.group(0)
    return None


def _submodel(make: str | None, model: str | None, text: str) -> tuple[str, str] | None:
    if not make:
        return None
    brand, name = normalize_brand(make), normalize_text(model)
    for rule_make, rule_model, pattern, code in _SUBMODELS:
        if brand == rule_make and (rule_model is None or name == rule_model):
            if m := pattern.search(text):
                return code, m.group(0)
    return None


def explicit(make: str | None, model: str | None, *texts: str | None) -> tuple[str, str, str] | None:
    """(code, method, words) from the first text that names a body type:
    a body word ('keyword') or a submodel rule ('submodel')."""
    for raw in texts:
        text = normalize_text(raw)
        if not text:
            continue
        if hit := _keyword(text):
            return hit[0], "keyword", hit[1]
        if hit := _submodel(make, model, text):
            return hit[0], "submodel", hit[1]
    return None


# The label Kavak ends its titles with, before the year ("Chevrolet Spin 18
# Activ 7S Auto Hatchback 2023"): the source's value, not the seller's words.
_KAVAK_LABEL = re.compile(
    r"\s+(sedan|sedán|hatchback|suv|pick ?-?up|minivan|monovolumen|wagon|rural|coup[eé]|cabriolet"
    r"|convertible|furg[oó]n|van|camioneta)\s+((?:19|20)[0-9]{2})\s*$", re.IGNORECASE)
# Sources whose URL path is structured: Kavak's card slug ends in its body
# type, Autocity's in its doors.
_SLUG_SOURCES = frozenset({"kavak", "autocity"})


def source_label(title: str | None, listing_source: str | None) -> tuple[str | None, str | None]:
    """(the title without the source's own body label, that label): Kavak's
    "… Hatchback 2023" becomes ("… 2023", "Hatchback"). Other sources' titles
    are the seller's words and stay whole."""
    if listing_source != "kavak" or not title or not (m := _KAVAK_LABEL.search(title)):
        return title, None
    return f"{title[:m.start()]} {m.group(2)}", m.group(1)


def url_words(url: str | None) -> str:
    """The URL's path as words: Kavak's card slug ends in its body type
    ("…-16_se-hatchback-2018") and Autocity's in its doors ("…-3p")."""
    if not url:
        return ""
    try:
        path = unquote(urlparse(url).path)
    except ValueError:
        return ""
    return re.sub(r"[^a-z0-9]+", " ", normalize_text(path)).strip()


# ---------------------------------------------------------------------------
# Doors
# ---------------------------------------------------------------------------

_DOORS = re.compile(r"(?<![a-z0-9.,])([345]) ?(?:p|ptas?|pts|puertas)(?![a-z0-9])")


def doors(*texts: str | None) -> int | None:
    """3, 4 or 5 from the first text that states the doors ("5p", "4ptas", "3 puertas")."""
    for raw in texts:
        if m := _DOORS.search(normalize_text(raw)):
            return int(m.group(1))
    return None


def _doors_value(value: Any) -> int | None:
    """A spec table's "Puertas" (Mercado Libre: "5")."""
    m = re.search(r"\d+", str(value)) if value not in (None, "") else None
    n = int(m.group(0)) if m else None
    return n if n in (3, 4, 5) else None


# ---------------------------------------------------------------------------
# The decision
# ---------------------------------------------------------------------------

def resolve(make: str | None, model: str | None, catalog_body_types: Iterable[str] | None = (),
            source_value: Any = None, trim: str | None = None, title: str | None = None,
            url: str | None = None, *, doors_value: Any = None,
            listing_source: str | None = None) -> tuple[str | None, str, str | None]:
    """(code or None, method, raw) for one listing; see the module docstring.

    `make`/`model` are the catalog's (normalization/vehicle.py) and
    `catalog_body_types` that model's vehicle_catalog.body_types, most
    common first (empty when the catalog doesn't know it). `source_value` is
    Listing.carroceria or a raw attribute; `doors_value` a spec table's
    "Puertas"; `listing_source` the listing's source (Kavak's title label,
    the URLs of Kavak and Autocity, each source's own values). `raw` is what
    decided: the words, the source's value, the doors; for 'catalog' and
    'none', the source value that was set aside.
    """
    title, label = source_label(title, listing_source)
    if source_value in (None, "") and label:
        source_value = label
    if hit := explicit(make, model, trim, title):
        return hit
    allowed = tuple(dict.fromkeys(c for c in (catalog_body_types or ()) if c in LABELS))

    def fits(code: str | None) -> bool:
        return code is not None and (not allowed or code in allowed)

    raw = None if source_value in (None, "") else str(source_value).strip() or None
    code = from_source(raw, listing_source)
    if fits(code):
        return code, "source", raw
    slug = url_words(url) if listing_source in _SLUG_SOURCES else ""
    if listing_source == "kavak" and code is None and slug \
            and (hit := explicit(make, model, slug)) and fits(hit[0]):
        return hit[0], "url", hit[2]

    n = _doors_value(doors_value) or doors(trim, title, slug)
    if n and len(allowed) > 1:
        code = "hatchback" if n in (3, 5) else "sedan"
        if code in allowed:
            return code, "doors", f"{n}p"
    if len(allowed) == 1:
        return allowed[0], "catalog", raw
    return None, "none", raw

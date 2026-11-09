"""Listings that are not a car: parts, accessories, a car taken apart.

Facebook Marketplace searches ("peugeot 206") bring back whatever mentions
the model, and in AR that is mostly parts: «Cremallera Peugeot 206-207-307»,
«Butacas Ford Ecosport», «Desarme de Chevrolet prisma 2017». Ingested as
cars they matched searches and, priced in pesos but read as dollars
(normalization/money.facebook_currency), skewed the comparables.

The rule is conservative on purpose: letting a part through costs one bad
row, while hiding a real car costs a user an opportunity. A listing is a
part only when

* its title *starts* with a part's name («Paragolpe trasero de Ford
  Ecosport», «Kit Embrague Valeo», «Vendo frente de Chevrolet prisma»): car
  titles start with the year, the make or a word like «Oportunidad», never
  with «Faro» or «Puerta»; with a piece of equipment a car's title may lead
  with too («Caja automática», «Techo solar», «Llantas», «Alarma») only when
  it names no single model year, or is «para» a car; or the title says
  «desarme», «autopartes», «repuestos de/para» or a body part with its side
  («óptica derecha», «puerta trasera izquierda») anywhere, not negated («no
  es desarme»); or it is a toy, a scale model or a collection without a
  model year («HOTWHEELS», «Salvat 1:43», «fascículos»);
* and nothing says it is a whole car: the source's own mileage together with
  a year (Facebook only shows «Conducido 112.000 km» on vehicles), a title
  that starts with the year (Facebook's own vehicle titles: «2017 Ford ka
  se»), a mileage in the title, or words only a car's seller uses («vendo mi»,
  «permuto», «titular», «papeles al día», «VTV», «formulario 08», «único
  dueño», «km reales»), in the title or the description.

A wanted post («Busco Gol Trend», «2012 Busco tapa ciega») is no car for sale
either, unless the source gives it a year and a mileage.

Pure: no I/O.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any

# Sources whose listings are checked. Facebook is the only general
# marketplace; the others are vehicle classifieds.
SOURCES = frozenset({"facebook"})

# A part's name, as the first word(s) of a title (accents stripped, lowercase).
_PARTS = (
    r"paragolpes?", r"butacas?", r"asientos?", r"cremalleras?", r"caja (?:de )?(?:velocidad|cambio)\w*",
    r"faros?", r"farol\w*", r"faritos?", r"opticas?", r"lentes?",
    # «Bomba» alone is also slang for a car in great shape («BOMBA Gol Trend»).
    r"bombas? (?:de|nafta|inyector\w*|electrica|hidraulica|combustible|centrifuga)",
    r"burros?(?: de arranque)?", r"tapas?(?: de cilindro\w*)?", r"tableros?", r"puertas?", r"porton\w*",
    r"embragues?", r"espejos?", r"retrovisor\w*",
    r"ciguenal\w*", r"ecu", r"modulos?", r"computadora", r"centralita",
    r"capot\w*", r"capo", r"aleron?\w*", r"suspension\w*", r"amortiguador\w*", r"espirales?",
    r"puesta (?:a )?punto", r"parrillas?", r"rejillas?", r"molduras?", r"zocalos?", r"guardaplast\w*",
    r"guardabarros?", r"compresor\w*", r"condensador\w*", r"evaporador\w*", r"radiador\w*",
    r"electroventilador\w*", r"barras?", r"sensor\w*", r"spoiler\w*", r"deflector\w*", r"guias?",
    r"motor (?:de arranque|limpia\w*|levanta\w*|electroventilador|completo|para|de)",
    r"limpiaparabrisas", r"parabrisas", r"lunetas?", r"vidrios?", r"desarmes?", r"volantes?",
    r"radiadores?", r"frentes?", r"trompas?", r"cosas de", r"alternador\w*", r"inyector\w*",
    r"bobinas?", r"semiej\w*", r"homocinetic\w*", r"diferencial\w*", r"cardan\w*",
    r"silenciador\w*", r"catalizador\w*", r"multiple", r"carter\w*", r"culatas?", r"juntas?",
    r"pistones?", r"arbol de levas", r"correas?", r"tensor\w*", r"bujias?",
    r"discos? de freno", r"pastillas?", r"calipers?", r"mazas?", r"rodamientos?", r"bujes?",
    r"rotulas?", r"parantes?", r"elasticos?", r"tanques?", r"manijas?", r"cerraduras?", r"bocinas?",
    r"parlantes?", r"antenas?", r"cinturon\w*",
    r"palancas?", r"pedaler\w*", r"tapizad\w*", r"tapiceria", r"fundas?", r"alfombras?",
    r"cubre\w*", r"portaequipaje\w*", r"enganches?", r"emblemas?", r"calcos?",
    r"termostato\w*", r"turbocompresor\w*", r"repuestos?", r"autopartes?",
    r"guardafangos?", r"baul", r"estribos?", r"barral\w*",
    # Matched as cars in the week of 02/11/2026 (the audit of 07/11/2026).
    # The lookaheads keep car titles that open with the same word: «Comandos al
    # volante Fiat Cronos 2021», «Llave x llave Corsa 2009» (a swap), «Caja de 6
    # marchas Focus 2015», «Luces led Amarok 2017», «Marco Polo T5», «Panel Fiat
    # Fiorino 2014» (the van), «Todo de serie Fiesta 2012».
    r"comandos?(?! al volante)", r"torpedos?", r"cuerpos? (?:de )?mariposa", r"porta ?(?:masas?|filtros?)\w*",
    r"soportes?", r"pedal\w*", r"llaves?(?! en mano| (?:x|por) llave)", r"patas? (?:de|del|motor)", r"cables?",
    r"panel(?:es)? (?:de|del|tapizad\w*|traser\w*|delanter\w*|interior\w*|difusor\w*|lateral\w*)",
    r"caja de(?! \d+ marchas)", r"cilindros?", r"deposito\w*", r"mangueras?", r"canos?", r"marcos?(?! polo)",
    r"ruedas?", r"tazas?", r"resortes?", r"pomos?", r"bajadas?", r"electros?", r"teclas?",
    r"luz", r"luces(?! led)", r"bielas?", r"lonas?", r"asesori\w*", r"octicas?",
    # «Todo de Peugeot 307 HDI diesel modelo 2006»: every part of one car.
    r"todo de(?! (?:serie|fabrica))",
)
# Words a part's title may open with before the part («Vendo frente de...»,
# «Kit faros auxiliares», «Juego de llantas», «Base Moldura»).
_LEAD = (r"vendo", r"venta(?: de)?", r"se vende", r"liquido", r"oferta", r"kit(?: de)?", r"juego(?: de)?",
         r"par(?: de)?", r"set(?: de)?", r"base", r"originale?s?", r"nuevos?", r"nuevas?", r"usados?",
         r"usadas?", r"repuesto", r"x\d+", r"tengo",
         # «4 llantas», «Tengo 2 puertas»; never «5 puertas Gol», «7 asientos Spin».
         r"\d(?! (?:puertas|asientos|plazas|cilindros|marchas|velocidades)\b)")
# Equipment a car's own title may open with as well as a part's («Caja
# automática Peugeot 208 Allure 2020», «Techo solar Jeep Compass Limited 2018»,
# «Llantas de aleación, Gol Trend 2013 full», «Radio taxi Chevrolet Spin»): a
# part only when the title names no single model year (a part's names a range,
# «2008 al 2012», or none).
_EQUIPMENT = (
    r"caja automatica", r"techo solar", r"llantas?", r"cubiertas?", r"neumaticos?", r"estereos?",
    r"stereos?", r"pantallas?", r"radios?(?! (?:taxi|llamada|remis))", r"alarmas?", r"airbags?",
    r"accesorios?",
)
_LEADS = rf"^(?:(?:{'|'.join(_LEAD)})\b[\s,/:-]*){{0,3}}"
_PART_START = re.compile(rf"{_LEADS}(?:{'|'.join(_PARTS)})\b")
_EQUIPMENT_START = re.compile(rf"{_LEADS}(?:{'|'.join(_EQUIPMENT)})\b")
_PART_ANYWHERE = re.compile(
    r"\b(?:desarmes?|autopartes?|repuestos (?:de|para))\b"
    # «Ford ecosport kinetic ... pata soporte de motor p703».
    r"|\b(?:soportes? (?:de )?motor|patas? (?:soporte )?de motor|cuerpos? (?:de )?mariposa)\b")
# A body part with its side: «Gol power 2006/14 óptica derecha» is one piece;
# unless the title tells a car's damage («Peugeot 207 con detalle en puerta
# delantera izquierda», «Gol 2008 faro izquierdo roto»).
_SIDED_PART = re.compile(
    r"\b(?:opticas?|faros?|paragolpes?|puertas?|espejos?|guardabarros?|guardaplast\w*|zocalos?)"
    r" (?:(?:delanter|traser)\w* )?(?:derech|izquierd)\w*\b")
_DAMAGE_BEFORE = re.compile(r"\b(?:con|detalles?|rot[oa]s?|choque|chocad\w*|abollad\w*|falta|rayad\w*"
                            r"|golpe\w*|sin)\b")
# Only right after the piece: «óptica derecha con detalle» is a damaged part.
_DAMAGE_AFTER = re.compile(r"^\W*(?:rot[oa]s?|abollad\w*|rayad\w*|golpead\w*|chocad\w*)\b")
# A toy, a scale model or a collection of magazines: «HONDA CIVIC CUSTOM
# HOTWHEELS», «FASCICULOS DE FORD MAVERICK».
_TOY = re.compile(r"\b(?:hot ?wheels?|escala 1 ?[:/ ] ?\d+|1 ?[:/] ?(?:8|18|24|32|36|43|64|87)\b|fascicul\w+"
                  r"|salvat|miniaturas?|maquetas?|juguetes?|diecast|a escala|welly|majorette|bburago|maisto"
                  r"|matchbox|motormax|hongwell)\b")
# «Honda civic colección rápido y furioso»: a collection with a film's name.
# «Fiat 600 de colección» alone is a classic car.
_COLLECTION = re.compile(r"\bcoleccion\w*\b")
_COLLECTION_HINT = re.compile(r"\b(?:rapido y furioso|fast (?:and|&) furious|revistas?|album)\b")
# Someone who wants to buy («Busco Gol Trend», «2012 Busco tapa ciega»):
# there is no car for sale behind it. Not «Busco permuta Ford Ka 2014», «Busco
# nuevo dueño», «Compro, vendo, permuto» (a dealer): those offer a car.
_WANTED = re.compile(r"^(?:(?:19[89]\d|20[0-3]\d)\s+)?(?:busco|compro|buscamos|compramos)\b"
                     r"(?![\s,]*(?:permut\w*|cambio|canje|nuevos? duen\w*|nuevas? duen\w*|comprador\w*"
                     r"|interesad\w*)\b)")
_OFFER = re.compile(r"\b(?:vend\w*|permut\w*)\b")
# «Ford Ka 2012 no es desarme», «no es para repuestos».
_NEGATED = re.compile(r"\bno (?:es )?(?:(?:un|para|de) )?(?:desarmes?|autopartes?|repuestos?)\b(?: (?:de|para))?")
_YEAR = re.compile(r"(?<![\d/-])(?:19[89]\d|20[0-3]\d)(?![\d/-])")
_YEAR_RANGE = re.compile(r"(?:19[89]\d|20[0-3]\d)\s*(?:(?:/|-|al|a|hasta)\s*(?:19[89]\d|20[0-3]\d|\d\d)\b"
                         r"|en adelante\b)")
# «Estéreo impecable para Ford focus 2012»: equipment *for* a car, «para» at
# most two words after it (not «Caja automática ... 2020 listo para transferir»).
_FOR = re.compile(r"^\W*(?:\w+\W+){0,2}?para\b")

# Whole-car evidence (title or description).
_CAR_WORDS = re.compile(
    r"\bvendo mi\b|\bpermut\w*|\btitular\b|\bpapeles al dia\b|\bvtv\b|\bformulario 08\b|\b08 firmado\b"
    r"|\bunico dueno\b|\bkm reales\b|\bkilometros reales\b|\bdueno directo\b")
_YEAR_FIRST = re.compile(r"^(?:19[89]\d|20[0-3]\d)\s+\S")
_KM_IN_TITLE = re.compile(r"\b\d[\d.,]*\s*(?:mil\s*)?(?:km|kms|kilometros)\b")


def _plain(text: str | None) -> str:
    text = "".join(c for c in unicodedata.normalize("NFD", (text or "").lower())
                   if unicodedata.category(c) != "Mn")
    # Emoji, «‼️», quotes and the like become spaces.
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s,./:-]", " ", text)).strip()


def part_reason(title: str | None) -> str | None:
    """Why the title names a part, or None."""
    t = _NEGATED.sub(" ", _plain(title)).strip()
    if m := _PART_START.match(t):
        return f"título: «{m.group(0).strip()}»"
    if (m := _EQUIPMENT_START.match(t)) and (not _single_year(t) or _FOR.match(t[m.end():])):
        return f"título: «{m.group(0).strip()}»"
    if m := _PART_ANYWHERE.search(t):
        return f"título: «{m.group(0)}»"
    if (m := _SIDED_PART.search(t)) and not _DAMAGE_BEFORE.search(t[:m.start()]) \
            and not _DAMAGE_AFTER.match(t[m.end():]):
        return f"título: «{m.group(0)}»"
    if m := _TOY.search(t):
        return f"juguete o colección: «{m.group(0)}»"
    if (m := _COLLECTION.search(t)) and _COLLECTION_HINT.search(t):
        return f"juguete o colección: «{m.group(0)}»"
    return None


def wanted_reason(title: str | None) -> str | None:
    """Why the title asks to buy rather than sells («Busco Gol Trend»), or None."""
    t = _plain(title)
    if (m := _WANTED.match(t)) and not _OFFER.search(t):
        return f"pedido de compra: «{m.group(0).strip()}»"
    return None


def _single_year(t: str) -> bool:
    """Whether the (plain) title names one model year, not a range."""
    return len(_YEAR.findall(t)) == 1 and not _YEAR_RANGE.search(t)


def car_evidence(title: str | None, description: str | None = None, *,
                 year: int | None = None, mileage_km: int | None = None) -> str | None:
    """Why the listing is a whole car, or None. `mileage_km` and `year` only
    from the source itself, never read from the description."""
    t = _plain(title)
    if year and mileage_km:
        return "año y kilometraje"
    if _YEAR_FIRST.match(t):
        return "el título empieza con el año"
    if _KM_IN_TITLE.search(t):
        return "kilometraje en el título"
    if m := _CAR_WORDS.search(f"{t} {_plain(description)}"):
        return f"«{m.group(0)}»"
    return None


def classify(title: str | None, description: str | None = None, *,
             year: int | None = None, mileage_km: int | None = None) -> str | None:
    """The reason a listing is not a car (a part, an accessory, a car taken
    apart), or None when it may be one."""
    if (reason := wanted_reason(title)) and not (year and mileage_km):
        # «2012 Busco tapa ciega»: the year a wanted post opens with is no car.
        return reason
    reason = part_reason(title)
    if reason is None or car_evidence(title, description, year=year, mileage_km=mileage_km):
        return None
    return reason


def classify_row(row: dict[str, Any]) -> str | None:
    """classify() for a `listings` row (normalized or stored), only for SOURCES.
    The year and mileage count as the source's only when the description did
    not fill them (attributes._description_filled)."""
    if row.get("source") not in SOURCES:
        return None
    filled = set((row.get("attributes") or {}).get("_description_filled") or ())
    return classify(row.get("title"), row.get("description"),
                    year=None if "year" in filled else row.get("year"),
                    mileage_km=None if "mileage_km" in filled else row.get("mileage_km"))


def _source_facts(row: dict[str, Any]) -> dict[str, Any]:
    """The year and mileage the source itself gave a row (not the description's)."""
    filled = set((row.get("attributes") or {}).get("_description_filled") or ())
    return {k: None if k in filled else row.get(k) for k in ("year", "mileage_km")}


def classify_update(row: dict[str, Any], stored: dict[str, Any] | None) -> str | None:
    """classify_row() for an incoming row with what the stored listing already
    knows: a card brings no description and often no mileage, while the
    listing it updates may have both (an enriched «Frente impecable Peugeot
    206», «Vendo mi auto, titular»). The incoming title with the description
    and the source's year and mileage of either side, so the crawl does not
    end a listing tools.repair_facebook would keep."""
    reason = row.get("not_vehicle") if "not_vehicle" in row else classify_row(row)
    if reason is None or stored is None:
        return reason
    new, old = _source_facts(row), _source_facts(stored)
    if classify(row.get("title"), row.get("description") or stored.get("description"),
                year=new["year"] or old["year"],
                mileage_km=new["mileage_km"] or old["mileage_km"]) is None:
        return None
    return reason


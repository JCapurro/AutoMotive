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
  with too («Caja automática», «Techo solar», «Llantas», «Alarma»), or a word
  that may be something else («Insignia», «Campana»), only when it names no
  single model year; or the title says «desarme», «autopartes» or
  «repuestos de/para» anywhere, not negated («no es desarme»);
* and nothing says it is a whole car: the source's own mileage together with
  a year (Facebook only shows «Conducido 112.000 km» on vehicles), a title
  that starts with the year (Facebook's own vehicle titles: «2017 Ford ka
  se»), a mileage in the title, or words only a car's seller uses («vendo mi»,
  «permuto», «titular», «papeles al día», «VTV», «formulario 08», «único
  dueño», «km reales»), in the title or the description.

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
    # «Parqgolpe delantero de Citroën C4».
    r"par[aq]golpes?", r"parachoques?", r"butacas?", r"asientos?", r"cremalleras?",
    r"caja (?:de )?(?:velocidad|cambio|fusible|filtr|porta|evapora|completa)\w*",
    # «Octicas de Peugeot 307».
    r"faros?", r"farol\w*", r"faritos?", r"o[cp]ticas?", r"lentes?",
    # «Bomba» alone is also slang for a car in great shape («BOMBA Gol Trend»).
    r"bombas? (?:de|nafta|inyector\w*|electrica|hidraulica|combustible|centrifuga)",
    r"burros?(?: de arranque)?", r"tapas?(?: de cilindro\w*)?", r"tableros?", r"puertas?", r"porton\w*",
    r"embragues?", r"espejos?", r"retrovisor\w*",
    r"ciguenal\w*", r"ecu", r"modulos?", r"computadora", r"centralita",
    r"capot\w*", r"capo", r"aleron?\w*", r"suspension\w*", r"amortiguador\w*", r"espirales?",
    r"puesta (?:a )?punto", r"parrillas?", r"rejillas?", r"molduras?", r"zocalos?", r"guardapla\w*",
    r"guardabarros?", r"compresor\w*", r"condensador\w*", r"evaporador\w*", r"radiador\w*",
    r"electroventilador\w*", r"barras?", r"sensor\w*", r"spoiler\w*", r"deflector\w*", r"guias?",
    r"motor (?:de arranque|limpia\w*|levanta\w*|electroventilador|completo|para|de|y caja|calefac\w*"
    r"|forzador\w*|soplador\w*)",
    r"limpiaparabrisas", r"parabrisas", r"lunetas?", r"vidrios?", r"desarmes?", r"volantes?",
    r"radiadores?", r"frentes?", r"trompas?", r"cosas de", r"alternador\w*", r"inyector\w*",
    r"bobinas?", r"semiej\w*", r"homocinetic\w*", r"diferencial\w*", r"cardan\w*",
    r"silenciador\w*", r"catalizador\w*", r"multiple", r"carter\w*", r"culatas?", r"juntas?",
    r"pistones?", r"arbol de levas", r"correas?", r"tensor\w*", r"bujias?",
    r"discos? de freno", r"pastillas?", r"calipers?", r"ma[sz]as?", r"rodamientos?", r"bujes?",
    r"rotulas?", r"parantes?", r"elasticos?", r"tanques?", r"manijas?", r"cerraduras?", r"bocinas?",
    r"parlantes?", r"antenas?", r"cinturon\w*",
    r"palancas?", r"pedaler\w*", r"tapizad\w*", r"tapiceria", r"fundas?", r"alfombras?",
    r"cubre\w*", r"portaequipaje\w*", r"enganches?", r"emblemas?", r"calcos?",
    r"termostato\w*", r"turbocompresor\w*", r"repuestos?", r"autopartes?",
    r"guardafangos?", r"baul(?:es)?", r"estribos?", r"barral\w*",
    # Matched as cars in production (11/2026), often with no price or year:
    # «Comando calefacción Peugeot 207», «Polea Chevrolet Corsa motor 1.4»,
    # «Depósito de líquido de freno», «Soporte para llaves».
    r"comandos?", r"poleas?", r"soportes?", r"encendidos?", r"arranques?", r"bielas?", r"caballetes?",
    r"cables?", r"canos?", r"tubos?", r"mangueras?", r"servo\w*", r"resortes?", r"progresivos?",
    r"selector\w*", r"pedal(?:es)?", r"teclas?", r"torpedos?", r"consolas?", r"carcasas?", r"ceniceros?",
    r"viseras?", r"chapon\w*", r"difusor\w*", r"forzador\w*", r"resonador\w*", r"limitador\w*",
    r"laterale?s?", r"logos?", r"lonas?", r"pomos?", r"tazas?", r"aranas?", r"kits?",
    r"almas? (?:de )?(?:par[aq]golpes?|parachoques?)", r"bajadas? (?:de )?(?:motor|escape)",
    r"centros? (?:de )?(?:llantas?|volante)", r"columnas? (?:de )?direccion",
    r"cuerpos? (?:de )?(?:mariposa|marisopa|acelerador|amortiguador\w*|porta\w*)",
    r"depositos? (?:de )?(?:agua|liquido|anticongelante|refrigerante|combustible|aceite|expansion"
    r"|limpia\w*|freno)",
    r"(?:levanta|alza) ?(?:cristal|vidrio)\w*", r"maquinas? (?:de )?(?:levanta|alza|motor)\w*",
    r"(?:pata|p4t4)s? (?:de )?(?:motor|caja)", r"rampas? (?:de )?inyec\w*",
    r"porta ?(?:filtro|ma[sz]a|lampara|fusible|vaso|llave|escalera|equipaje|placa)\w*",
    r"manual(?:es)? (?:del? )?(?:propietario|usuario|taller|servicio|instrucciones)",
    # Not «Llave en mano» (a new car's price); «Luz» and «Marco» are names.
    r"llaves?(?! en mano)",
    r"luz (?:de |del )?(?:auxiliar|stop|giro|freno|patente|posicion|alta|baja|trasera|delantera|interior"
    r"|cortesia|cortecia|techo|faro)\w*",
    r"marcos? (?:de |del )?(?:climatiz|estereo|radio|espejo|optica|faro|puerta|tablero|parrilla|palanca"
    r"|cromado|consola)\w*",
)
# Words a part's title may open with before the part («Vendo frente de...»,
# «Kit faros auxiliares», «Juego de llantas», «Base Moldura», and Facebook's
# «Sold · » on a listing that sold).
_LEAD = (r"vendo", r"venta(?: de)?", r"se vende", r"liquido", r"oferta", r"kit(?: de)?", r"juego(?: de)?",
         r"par(?: de)?", r"set(?: de)?", r"base", r"originale?s?", r"nuevos?", r"nuevas?", r"usados?",
         r"usadas?", r"repuesto", r"x\d+", r"sold")
# Equipment a car's own title may open with as well as a part's («Caja
# automática Peugeot 208 Allure 2020», «Techo solar Jeep Compass Limited 2018»,
# «Llantas de aleación, Gol Trend 2013 full», «Radio taxi Chevrolet Spin»), and
# words that may be something else («Insignia» is an Opel, «Campana» a town):
# a part only when the title names no single model year (a part's names a
# range, «2008 al 2012», or none).
_EQUIPMENT = (
    r"cajas?", r"techo solar", r"llantas?", r"ruedas?", r"cubiertas?", r"neumaticos?", r"estereos?",
    r"e?sterios?", r"stereos?", r"pantallas?", r"displays?", r"radios?(?! (?:taxi|llamada|remis))",
    r"alarmas?", r"airbags?", r"accesorios?", r"asesorios?", r"luces", r"leds?", r"insignias?",
    r"campanas?",
)
_LEADS = rf"^(?:(?:{'|'.join(_LEAD)})\b[\s,/:-]*){{0,3}}"
_PART_START = re.compile(rf"{_LEADS}(?:{'|'.join(_PARTS)})\b")
_EQUIPMENT_START = re.compile(rf"{_LEADS}(?:{'|'.join(_EQUIPMENT)})\b")
_PART_ANYWHERE = re.compile(r"\b(?:desarmes?|autopartes?|repuestos (?:de|para))\b")
# «Ford Ka 2012 no es desarme», «no es para repuestos».
_NEGATED = re.compile(r"\bno (?:es )?(?:(?:un|para|de) )?(?:desarmes?|autopartes?|repuestos?)\b(?: (?:de|para))?")
_YEAR = re.compile(r"(?<![\d/-])(?:19[89]\d|20[0-3]\d)(?![\d/-])")
_YEAR_RANGE = re.compile(r"(?:19[89]\d|20[0-3]\d)\s*(?:/|-|al|a|hasta)\s*(?:19[89]\d|20[0-3]\d|\d\d)\b")

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
    if (m := _EQUIPMENT_START.match(t)) and not _single_year(t):
        return f"título: «{m.group(0).strip()}»"
    if m := _PART_ANYWHERE.search(t):
        return f"título: «{m.group(0)}»"
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


"""What a listing's description says: prices, vehicle facts and seller claims.

In AR classifieds the published number is often not the deal; the seller
explains it in the text:

    PRECIO CONTADO U$S 10.990 .-
    PRECIO PERMUTA U$S 12.500 .-
    O FINANCIALO CON UN ANTICIPO MINIMO DESDE U$S 6.000.- Y CUOTAS.

parse() reads those statements with rules. Every amount gets a kind from
the words around it: cash (contado, efectivo), list (lista, permuta,
financiado), down_payment (anticipo, entrega, "retirá con"), installment
(cuota, por mes) or generic (precio, valor, nothing). A text the rules
can't settle is marked `ambiguous`; the LLM refines those (pipeline/enrich.py).

resolve_price() then decides the listing's effective price, the one
matching, comparables and the score use: the cash price when the
description gives a cheaper one, the total when the published number is a
down payment. The published number itself is kept apart (listings.price_published).

Pure: no I/O.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import asdict, dataclass, field
from typing import Any, Mapping

from normalization import transmission as tx
from normalization.description_claims import CLAIM_FIELDS, grounded_values, input_hash, quote_contexts
from normalization.money import (MIN_ARS_VEHICLE_PRICE, MIN_USD_VEHICLE_PRICE, parse_number,
                                 plain_dollar_currency, plausible_vehicle_price)

VERSION = 2

TOTAL_KINDS = ("cash", "list", "generic")
PARTIAL_KINDS = ("down_payment", "installment")

# Two amounts within this share of each other are the same price.
SAME_PRICE_TOL = 0.005
# A cash price read from the text is never taken below this share of the
# published one (unless the published one is a down payment): below it the
# rules probably misread an anticipo.
MIN_CASH_SHARE = 0.5
# A published number this many times below the price the text gives is a
# down payment, whatever the title says.
DOWN_PAYMENT_RATIO = 1.6
# In descriptions a bare "$" above this is ARS: nobody sells a used car for
# USD 200.000, but ARS installments of "$ 603.000" are everywhere.
_PLAIN_DOLLAR_ARS_FROM = 200_000


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Amount:
    kind: str           # cash | list | down_payment | installment | generic
    amount: float
    currency: str       # USD | ARS
    text: str = ""      # the words it was read from, for the inspector

    def money(self) -> dict[str, Any]:
        return {"amount": self.amount, "currency": self.currency}


@dataclass
class Financing:
    offered: bool = False
    down_payment: dict[str, Any] | None = None       # {"amount", "currency"}
    installment: dict[str, Any] | None = None
    min_down_payment_pct: int | None = None           # "entrega mínima 50%"
    max_financed_pct: int | None = None               # "financiamos hasta el 70%"
    max_installments: int | None = None               # "hasta 36 cuotas"


@dataclass
class DescriptionFacts:
    amounts: list[Amount] = field(default_factory=list)
    published_is: str | None = None                  # the text says the published price is cash | list
    financing: Financing = field(default_factory=Financing)
    mileage_km: int | None = None
    year: int | None = None
    transmission: str | None = None
    fuel: str | None = None
    gnc: bool = False
    ambiguous: bool = False
    source: str = "rules"                            # rules | llm
    llm_at: str | None = None
    # Filled by resolve_price() when the facts are stored with a listing.
    price_check: dict[str, Any] | None = None
    claims: dict[str, Any] = field(default_factory=dict)
    evidence: list[dict[str, str]] = field(default_factory=list)
    input_hash: str | None = None

    def of_kind(self, *kinds: str) -> list[Amount]:
        return [a for a in self.amounts if a.kind in kinds]

    def is_empty(self) -> bool:
        return not (self.amounts or self.published_is or self.financing.offered or self.mileage_km
                    or self.year or self.transmission or self.fuel or self.gnc or self.ambiguous
                    or self.source == "llm" or self.claims)

    def to_json(self) -> dict[str, Any]:
        out = asdict(self)
        out["v"] = VERSION
        return out

    @classmethod
    def from_json(cls, data: Mapping[str, Any] | None) -> "DescriptionFacts | None":
        if not data:
            return None
        fin = data.get("financing") or {}
        return cls(
            amounts=[Amount(a["kind"], float(a["amount"]), a["currency"], a.get("text") or "")
                     for a in data.get("amounts") or [] if a.get("amount") and a.get("currency")],
            published_is=data.get("published_is"),
            financing=Financing(**{k: fin.get(k) for k in Financing.__dataclass_fields__ if k in fin}),
            mileage_km=data.get("mileage_km"),
            year=data.get("year"),
            transmission=data.get("transmission"),
            fuel=data.get("fuel"),
            gnc=bool(data.get("gnc")),
            ambiguous=bool(data.get("ambiguous")),
            source=data.get("source") or "rules",
            llm_at=data.get("llm_at"),
            price_check=data.get("price_check"),
            claims=dict(data.get("claims") or {}),
            evidence=list(data.get("evidence") or []),
            input_hash=data.get("input_hash"),
        )


# ---------------------------------------------------------------------------
# Text
# ---------------------------------------------------------------------------

def _plain(text: str) -> str:
    """Lowercase, no accents, no invisible characters; line breaks kept."""
    out = []
    for c in unicodedata.normalize("NFD", text):
        if unicodedata.category(c) not in ("Mn", "Cf"):
            out.append(c)
    s = "".join(out).lower()
    s = re.sub(r"[ \t  -​ ]+", " ", s)
    return s


_NUM = r"\d{1,3}(?:[.,]\d{3})+(?:,\d{1,2})?|\d+(?:[.,]\d+)?"
_MULT = r"millones|millon|palos|mil|lucas|k"
_CUR_BEFORE = r"(?:ars|pesos)\s*\$|u\$s|u\$d|us\$|usd|u\.s\.d\.?|us|dolares|dls|ars|\$"
_CUR_AFTER = r"u\$s|u\$d|us\$|usd|dolares|dolar|dls|verdes|pesos|ars"
_AMOUNT = re.compile(
    rf"(?:(?<![a-z])(?P<cur1>{_CUR_BEFORE})\s*:?\s*(?P<num1>{_NUM})(?![\d])"
    rf"(?:\s*(?P<mult1>{_MULT})\b)?(?:\s*(?P<cur1b>{_CUR_AFTER})\b)?"
    rf"|(?<![\d.,])(?P<num2>{_NUM})\s*(?:(?P<mult2>{_MULT})\s*)?(?:de\s+)?(?P<cur2>{_CUR_AFTER})\b(?!\s*\d)"
    rf"|(?<![\d.,])(?P<num3>{_NUM})\s*(?P<mult3>millones|millon|palos)\b)"
)
_USD_WORDS = ("u$s", "u$d", "us$", "usd", "u.s.d", "us", "dolares", "dolar", "dls", "verdes")

# Words before an amount: the closest one wins.
_BEFORE = [
    ("cash", re.compile(r"contado|efectivo|precio final|valor final|cash|pago unico")),
    ("list", re.compile(r"\blista\b(?! para)|permuta\b|financiad[oa]|financiacion|financiando|con tarjeta")),
    ("down_payment", re.compile(r"anticipo|(?<!mas )entrega(?!s? inmediata)s?(?: minima)?|"
                                r"retir\w*|llevatelo|llevalo|te lo llevas|subite|sena\b")),
    ("installment", re.compile(r"cuotas?|mensual\w*|x mes|por mes")),
    ("generic", re.compile(r"precio|valor|vendo|oferta|sale\b")),
    # Money that isn't the car's price: transfer costs, taxes, debts.
    ("other", re.compile(r"transferencia|gastos|patentes?|seguro|multas?|deudas?|impuestos?|"
                         r"infracciones|service|reparaci\w*|descuento|bonificaci\w*|ahorr\w*")),
]
# Words right after an amount ("u$s11.500 en efectivo", "$5.000.000 y cuotas").
# They are specific enough to win over the words before it.
_AFTER = [
    # "+ cuotas" is looked at, not consumed: it labels the installment that may follow.
    ("down_payment", re.compile(r"^\s*(?:(?:y|\+|mas)\s*(?=(?:\d+\s*)?cuotas)|(?:de|como) (?:anticipo|entrega)|"
                                r"y (?:el )?(?:saldo|resto))")),
    ("cash", re.compile(r"^\W{0,3}(?:en |de |al )?(?:efectivo|contado|cash)\b")),
    ("installment", re.compile(r"^\W{0,3}(?:(?:por|x|al) mes|/ ?mes|mensual\w*|(?:de |por )?cuota)")),
    ("list", re.compile(r"^\W{0,3}(?:financiado|con financiacion|en cuotas|(?:de|en) permuta|de lista)\b")),
    ("other", re.compile(r"^\W{0,3}(?:de|en|por) (?:patente|transferencia|gastos|deuda|multas|seguro|"
                         r"descuento|bonificacion|ahorro)")),
]
_BOUNDARY = re.compile(r"\n|[!?;|•]|\.\s|\s/\s")
_WINDOW = 45

_PUBLISHED_CASH = re.compile(
    r"(?:precio|valor)(?:es)? publicados? (?:es |son )?(?:de |al |el de )?contado|"
    r"(?:precio|valor)(?:es)? (?:es |son )?de contado (?:el )?publicado")
_PUBLISHED_LIST = re.compile(
    r"(?:precio|valor)(?:es)? publicados? (?:es |son )?(?:el |los )?(?:de )?lista|"
    r"(?:precio|valor)(?:es)? de lista (?:el )?publicado")

_FINANCING = re.compile(r"financ\w*|cuotas?\b|credito|prendari\w*|leasing|anticipo|entrega minima|"
                        r"retir\w* con|subite con|llevatelo con")
_NEGATION = re.compile(r"\b(?:no|sin|ni)\b[^.\n]{0,12}$")
_DOWN_PCT = re.compile(r"(?:entrega\w*|anticipo|retir\w*|llevatelo|subite|con solo|con el)\D{0,15}?(\d{1,2})\s*%")
_FINANCED_PCT = re.compile(r"financ\w*[^%\n]{0,25}?(\d{1,3})\s*%")
_INSTALLMENTS = re.compile(r"(\d{1,3})\s*cuotas")

# km: "Km: 110.000", "Kilometraje: 117.000", "con 105.000 km", "98.000 km reales".
_KM_LABELED = re.compile(rf"\b(?:km|kms|kilometraje|kilometros)\s*[:=]?\s*({_NUM})(?:\s*(mil)\b)?")
_KM_SUFFIX = re.compile(rf"(?<![\d.,])({_NUM})\s*(mil\s*)?(?:km|kms|kilometros)\b(\s*reales|\s*recorridos)?")
_KM_SHORT_EXCLUDE = re.compile(r"(?:a los|hace|cada|proxim\w*|hasta los|los|antes de|dentro de|ruta)\s*$")
_KM_LONG_EXCLUDE = re.compile(r"cubierta|neumatic|distribuc|correa|bateria|garantia|aceite|embrague|"
                              r"service|servicio|amortiguador|motor (?:hecho|nuevo)|cambi|adquiri|compr")
_KM_STRONG_PREFIX = re.compile(r"(?:con|tiene|kilometraje|mecanica|recorrido|marca)\s*:?\s*$")

_YEAR = re.compile(r"\b(?:ano|anio|modelo|mod\.?)\s*[:=]?\s*(19[89]\d|20[0-3]\d)\b|"
                   r"\b(19[89]\d|20[0-3]\d)\s+con\s+[\d.,]+\s*(?:km|kms|kilometros)\b")
_GNC = re.compile(r"\bgnc\b")
_NO_GNC = re.compile(r"\bsin gnc\b")


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def _currency(cur: str | None, amount: float) -> str | None:
    if cur is None:
        return "ARS"        # "5 millones"
    cur = cur.replace(" ", "")
    if cur.startswith(_USD_WORDS):
        return "USD"
    if "ars" in cur or "pesos" in cur:
        return "ARS"
    if cur == "$":
        return plain_dollar_currency(amount, ars_from=_PLAIN_DOLLAR_ARS_FROM)
    return None


def _plausible(kind: str, amount: float, currency: str) -> bool:
    if kind in PARTIAL_KINDS:
        # Installments and down payments are smaller than a car.
        return amount >= (50 if currency == "USD" else 10_000) and (
            currency != "USD" or amount <= 1_000_000)
    return plausible_vehicle_price(amount, currency)


def _before_label(window: str) -> str | None:
    best: tuple[int, int, str] | None = None
    for kind, pattern in _BEFORE:
        for m in pattern.finditer(window):
            key = (m.end(), m.end() - m.start(), kind)
            if best is None or key[:2] > best[:2]:
                best = key
    return best[2] if best else None


def _after_label(text: str) -> tuple[str, int] | None:
    for kind, pattern in _AFTER:
        if m := pattern.search(text):
            return kind, m.end()
    return None


def _window_start(text: str, start: int, floor: int) -> int:
    """Where the words that label the amount at `start` begin: the last
    sentence boundary, or the previous line when the amount opens its line
    ("PRECIO DE LISTA/PERMUTA\\nU$S 11.500")."""
    lo = max(floor, start - _WINDOW)
    cut = lo
    for m in _BOUNDARY.finditer(text, lo, start):
        cut = m.end()
    prefix = text[cut:start]
    if cut > floor and not re.search(r"[a-z]", prefix) and text[cut - 1:cut] == "\n":
        prev = text.rfind("\n", floor, cut - 1)
        cut = max(floor, prev + 1, start - _WINDOW - 20)
    return cut


def _amounts(text: str) -> list[Amount]:
    out: list[Amount] = []
    floor = 0
    for m in _AMOUNT.finditer(text):
        num = m.group("num1") or m.group("num2") or m.group("num3")
        mult = m.group("mult1") or m.group("mult2") or m.group("mult3")
        cur = m.group("cur1b") or m.group("cur1") or m.group("cur2")
        value = parse_number(num, mult)
        if value is None:
            floor = m.end()
            continue
        currency = _currency(cur, value)
        after = _after_label(text[m.end():m.end() + 30])
        if after:
            kind, after_end = after[0], m.end() + after[1]
        else:
            start = _window_start(text, m.start(), floor)
            kind, after_end = _before_label(text[start:m.start()]) or "generic", m.end()
        if kind == "other":
            floor = after_end
            continue
        if mult in ("millones", "millon") and re.match(r"\s*(?:y\s+)?(?:quinientos|500 mil|medio)\b",
                                                        text[m.end():m.end() + 16]):
            value += 500_000        # "18 millones quinientos"
        if currency and _plausible(kind, value, currency):
            snippet = text[max(0, m.start() - 30):m.end() + 12].replace("\n", " / ").strip()
            out.append(Amount(kind, value, currency, snippet[:80]))
        floor = after_end
    return out


def _published_is(text: str) -> str | None:
    if _PUBLISHED_CASH.search(text):
        return "cash"
    if _PUBLISHED_LIST.search(text):
        return "list"
    return None


def _financing(text: str, amounts: list[Amount]) -> Financing:
    offered = any(not _NEGATION.search(text[max(0, m.start() - 16):m.start()])
                  for m in _FINANCING.finditer(text))
    down = next((a.money() for a in amounts if a.kind == "down_payment"), None)
    inst = next((a.money() for a in amounts if a.kind == "installment"), None)
    down_pct = next((int(m.group(1)) for m in _DOWN_PCT.finditer(text) if 0 < int(m.group(1)) < 100), None)
    financed_pct = max((int(m.group(1)) for m in _FINANCED_PCT.finditer(text)
                        if 0 < int(m.group(1)) <= 100), default=None)
    installments = max((int(m.group(1)) for m in _INSTALLMENTS.finditer(text)
                        if 2 <= int(m.group(1)) <= 120), default=None)
    offered = offered or bool(down or inst or down_pct or financed_pct or installments)
    return Financing(offered, down, inst, down_pct, financed_pct, installments)


def _km(text: str) -> tuple[int | None, bool]:
    """(km, ambiguous)."""
    strong: list[int] = []
    weak: list[int] = []
    for m in _KM_LABELED.finditer(text):
        if re.search(r"ruta\s*\d*\s*$", text[max(0, m.start() - 12):m.start()]):
            continue        # "Ruta 178 km:200" is an address
        value = parse_number(m.group(1), m.group(2))
        if value and 100 <= value < 1_000_000:
            strong.append(int(value))
    for m in _KM_SUFFIX.finditer(text):
        value = parse_number(m.group(1), (m.group(2) or "").strip() or None)
        if not value or not 100 <= value < 1_000_000:
            continue
        before = text[max(0, m.start() - 45):m.start()]
        if _KM_SHORT_EXCLUDE.search(before[-16:]):
            continue
        if m.group(3):
            strong.append(int(value))            # "98.000 km reales"
        elif _KM_LONG_EXCLUDE.search(before[-30:] if _KM_STRONG_PREFIX.search(before[-16:]) else before):
            continue                             # "neumáticos con 20 mil km", "service a los..."
        elif _KM_STRONG_PREFIX.search(before[-16:]):
            strong.append(int(value))
        else:
            weak.append(int(value))
    pool = strong or weak
    distinct = _distinct(pool, tol=0.02)
    if not distinct:
        return None, False
    if len(distinct) > 1:
        return (pool[0] if strong else None), True
    return pool[0], False


def _year(text: str, now_year: int | None) -> int | None:
    years = {int(m.group(1) or m.group(2)) for m in _YEAR.finditer(text)}
    if now_year:
        years = {y for y in years if y <= now_year + 1}
    return years.pop() if len(years) == 1 else None


def _distinct(values: list[float], tol: float = SAME_PRICE_TOL) -> list[float]:
    out: list[float] = []
    for v in values:
        if not any(_close(v, o, tol) for o in out):
            out.append(v)
    return out


def _close(a: float, b: float, tol: float = SAME_PRICE_TOL) -> bool:
    return abs(a - b) <= tol * max(abs(a), abs(b))


# A description read with the page around it (Facebook before the detail
# parser stopped there): what follows is the map and other ads, with prices.
_PAGE_NOISE = re.compile(r"\n[·•\s]*(?:ver más|ver mas|see more|sugerencias de hoy|today's picks|"
                         r"la ubicación es aproximada|enviar mensaje)\s*(?:\n|$)", re.IGNORECASE)


def trim_page_noise(description: str | None) -> str | None:
    if not description:
        return description
    m = _PAGE_NOISE.search("\n" + description)
    return description[:max(m.start() - 1, 0)].rstrip() if m else description


def parse(description: str | None, title: str | None = None, *,
          now_year: int | None = None) -> DescriptionFacts | None:
    """The facts a listing's title and description state. None without text.

    The title goes first: "Polo 2025 $12.000.000 y cuotas" says what the
    published number is as clearly as any description.
    """
    description = trim_page_noise(description)
    raw = "\n".join(t for t in (title, description) if t and t.strip())
    if not raw:
        return None
    text = _plain(raw)
    body = _plain(description or "")
    amounts = _amounts(text)
    km, km_ambiguous = _km(body)
    cash = _distinct([a.amount for a in amounts if a.kind == "cash"])
    generic_by_currency: dict[str, list[float]] = {}
    for a in amounts:
        if a.kind == "generic":
            generic_by_currency.setdefault(a.currency, []).append(a.amount)
    many_generic = any(len(_distinct(v)) > 1 for v in generic_by_currency.values())
    ambiguous = len(cash) > 1 or (not cash and many_generic) or km_ambiguous
    return DescriptionFacts(
        amounts=amounts,
        published_is=_published_is(text),
        financing=_financing(text, amounts),
        mileage_km=km,
        year=_year(body, now_year),
        transmission=tx.transmission(body),
        fuel=tx.fuel(body),
        gnc=bool(_GNC.search(body)) and not _NO_GNC.search(body),
        ambiguous=ambiguous,
    )


# ---------------------------------------------------------------------------
# The effective price
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PriceResolution:
    price: float | None
    currency: str | None
    source: str                      # published | description
    partial: bool
    partial_reason: str | None
    published_kind: str | None = None
    mismatch: Amount | None = None   # a total the text gives that disagrees with the published one
    effective_kind: str | None = None  # what the effective price is: cash | list | generic | …

    def check(self) -> dict[str, Any]:
        """What resolve_price() concluded, stored in description_facts.price_check.
        The web and the notifications say "de contado" when effective_kind is cash."""
        return {"published_kind": self.published_kind, "effective_kind": self.effective_kind,
                "source": self.source,
                "mismatch": ({"amount": self.mismatch.amount, "currency": self.mismatch.currency}
                             if self.mismatch else None)}


def _usd(amount: float, currency: str | None, usd_rate: float | None) -> float | None:
    if currency == "USD":
        return amount
    if currency == "ARS" and usd_rate and usd_rate > 0:
        return amount / usd_rate
    return None


_KIND_WORDS = {"down_payment": "anticipo", "installment": "cuota"}


def resolve_price(published: float | None, currency: str | None, *,
                  partial_reason: str | None, facts: DescriptionFacts | None,
                  usd_rate: float | None) -> PriceResolution:
    """The listing's effective price (sección 5.2, v3).

    `published`/`currency`: the number the source shows. `partial_reason`:
    why the title or the page's structure already say it's a down payment
    or an installment (price_check.keyword_partial, Autocosmos' blocks).
    `usd_rate`: ARS per USD, to compare amounts in different currencies.
    """
    as_published = PriceResolution(published, currency, "published", bool(partial_reason), partial_reason)
    if not published or not currency or facts is None:
        return as_published
    pub_usd = _usd(published, currency, usd_rate)

    def usd(a: Amount) -> float | None:
        return _usd(a.amount, a.currency, usd_rate)

    def same(a: Amount) -> bool:
        if a.currency == currency:
            return _close(a.amount, published)
        u = usd(a)
        return u is not None and pub_usd is not None and _close(u, pub_usd, 0.03)

    kind = facts.published_is or next((a.kind for a in facts.amounts if same(a)), None)
    comparable = [a for a in facts.amounts if usd(a) is not None and pub_usd is not None]

    def from_text(a: Amount) -> PriceResolution:
        return PriceResolution(a.amount, a.currency, "description", False, None, kind, effective_kind=a.kind)

    def cheaper_cash() -> Amount | None:
        # A cash price below the published one, within reason: the published
        # number was the list/permuta/financed price.
        return min((a for a in comparable if a.kind == "cash" and not same(a)
                    and MIN_CASH_SHARE * pub_usd <= usd(a) < pub_usd), key=usd, default=None)

    if kind in PARTIAL_KINDS or (partial_reason and kind not in TOTAL_KINDS):
        # The published number is a down payment or an installment: the total,
        # if the text gives one, is the cheapest cash price above it, else the
        # largest other total.
        above = [a for a in comparable if a.kind in TOTAL_KINDS and not same(a) and usd(a) > pub_usd]
        cash = [a for a in above if a.kind == "cash"]
        if cash or above:
            return from_text(min(cash, key=usd) if cash else max(above, key=usd))
        if kind not in PARTIAL_KINDS and (c := cheaper_cash()):
            # Only the title said "cuotas"; the text prices it cash below the published number.
            return from_text(c)
        reason = partial_reason or f"descripción: {_KIND_WORDS.get(kind, kind)}"
        return PriceResolution(published, currency, "published", True, reason, kind, effective_kind=kind)

    if kind != "cash" and (c := cheaper_cash()):
        return from_text(c)
    if kind is None:
        # The text prices the car at well over the published number, which
        # then is most likely a down payment ("financiable", "retirá con").
        way_above = [a for a in comparable if a.kind in ("cash", "generic")
                     and usd(a) >= DOWN_PAYMENT_RATIO * pub_usd]
        if way_above:
            cash = [a for a in way_above if a.kind == "cash"]
            return from_text(min(cash or way_above, key=usd))
    # The published number stands. When the text states it's a total, that
    # also clears a partial suspicion from the title. A cash or plain price in
    # the text that isn't the published one (the description may be outdated)
    # is kept as a mismatch to verify.
    partial = as_published.partial and kind not in TOTAL_KINDS
    mismatch = next((a for a in comparable if a.kind in ("cash", "generic") and not same(a)), None)
    return PriceResolution(published, currency, "published", partial,
                           partial_reason if partial else None, kind, mismatch, effective_kind=kind)


def from_llm(llm: Any, rules: DescriptionFacts | None, *, llm_at: str,
             title: str = "", description: str | None = None) -> DescriptionFacts:
    """Facts from the LLM's ListingFacts (llm/schemas.py), on top of the rules'.

    The LLM only fills what the text states explicitly; amounts it gives are
    checked with the same bounds as the rules' and replace them.
    """
    base = rules or DescriptionFacts()
    text = "\n".join((title, trim_page_noise(description) or ""))
    values, evidence = grounded_values(llm, text) if description is not None else ({}, [])

    def value(name: str) -> Any:
        # Compatibility for recorded legacy responses; live callers always supply text.
        return values.get(name) if description is not None else getattr(llm, name, None)

    currency = value("price_currency")
    amounts: list[Amount] = []
    for kind, attr in (("cash", "cash_price"), ("list", "list_price"),
                       ("down_payment", "down_payment"), ("installment", "installment_amount")):
        amount = value(attr)
        if not amount or amount <= 0:
            continue
        cur = currency or plain_dollar_currency(float(amount), ars_from=_PLAIN_DOLLAR_ARS_FROM)
        quotes = [e["quote"] for e in evidence if e["field"] == attr]
        supported = description is None or any(
            abs(float(amount) - a.amount) < 0.000001 and a.currency == cur and a.kind in (kind, "generic")
            and all(any(abs(float(amount) - found.amount) < 0.000001 and found.currency == cur
                        and found.kind in (kind, "generic") for found in _amounts(_plain(context)))
                    for context in quote_contexts(q, text))
            for q in quotes for a in _amounts(_plain(q)))
        if supported and _plausible(kind, float(amount), cur):
            amounts.append(Amount(kind, float(amount), cur, quotes[0] if quotes else "llm"))
        else:
            values.pop(attr, None)
    fin = Financing(**asdict(base.financing))
    down = next((a.money() for a in amounts if a.kind == "down_payment"), None)
    inst = next((a.money() for a in amounts if a.kind == "installment"), None)
    fin.down_payment = down or fin.down_payment
    fin.installment = inst or fin.installment
    count = value("installment_count")
    count_supported = description is None or any(
        _financing(_plain(e["quote"]), _amounts(_plain(e["quote"]))).max_installments == count
        for e in evidence if e["field"] == "installment_count")
    if count and 2 <= count <= 120 and count_supported:
        fin.max_installments = count
    elif count:
        values.pop("installment_count", None)
    fin.offered = fin.offered or bool(value("financing") or down or inst)
    km = value("mileage_km")
    year = value("year")
    if description is not None:
        if km and not any(_km(_plain(e["quote"]))[0] == km and all(
                _km(_plain(context))[0] == km for context in quote_contexts(e["quote"], text))
                for e in evidence if e["field"] == "mileage_km"):
            km = None
            values.pop("mileage_km", None)
        if year and not any(_year(_plain(e["quote"]), None) == year for e in evidence if e["field"] == "year"):
            year = None
            values.pop("year", None)
    kind = value("published_price_kind")
    if description is not None:
        if kind and not any(_published_is(_plain(e["quote"])) == kind for e in evidence if e["field"] == "published_price_kind"):
            kind = None
            values.pop("published_price_kind", None)
        for field_name, parser in (("transmission", tx.transmission), ("fuel", tx.fuel)):
            result = values.get(field_name)
            if result and not any(parser(e["quote"]) == result for e in evidence if e["field"] == field_name):
                values.pop(field_name, None)
    return DescriptionFacts(
        amounts=amounts or base.amounts,
        published_is=kind if kind in ("cash", "list") else base.published_is,
        financing=fin,
        mileage_km=km if km and 100 <= km < 1_000_000 else base.mileage_km,
        year=year if year and 1980 <= year <= 2040 else base.year,
        transmission=value("transmission") or base.transmission,
        fuel=value("fuel") or base.fuel,
        gnc=base.gnc or value("fuel") == "gnc",
        ambiguous=base.ambiguous and not (amounts or km),
        source="llm",
        llm_at=llm_at,
        claims={k: v for k, v in values.items() if k in CLAIM_FIELDS},
        evidence=[e for e in evidence if e["field"] in values],
        input_hash=input_hash(title, trim_page_noise(description)) if description is not None else None,
    )


__all__ = ["Amount", "DescriptionFacts", "Financing", "PriceResolution", "from_llm", "parse",
           "resolve_price", "MIN_ARS_VEHICLE_PRICE", "MIN_USD_VEHICLE_PRICE"]

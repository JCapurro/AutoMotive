"""Money amounts as Argentine listings write them (cards and descriptions).

"$" alone is ambiguous in AR classifieds: Facebook renders USD cars as
"$ 11,900" and ARS ones as "$ 11,900,000", sellers write "$15.000.000" or
"U$S 10.900", and thousands separators are dots or commas.
"""
from __future__ import annotations

import os
import re

from normalization.normalize import normalize_text

MIN_USD_VEHICLE_PRICE = 1_000
MIN_ARS_VEHICLE_PRICE = 500_000
# Above this a "USD" figure is a typo or an ARS amount written with the wrong sign.
MAX_USD_VEHICLE_PRICE = 1_000_000

_THOUSANDS = re.compile(r"\d+(?:[.,]\d{3})+")
_THOUSANDS_CENTS = re.compile(r"(\d{1,3}(?:\.\d{3})+),\d{1,2}")
_MULTIPLIERS = {"millones": 1e6, "millon": 1e6, "palos": 1e6,
                "mil": 1e3, "lucas": 1e3, "k": 1e3}


def plain_dollar_currency(amount: float, *, ars_from: float = 1_000_000) -> str:
    """The currency of an amount written with a bare "$": ARS from `ars_from` up."""
    return "ARS" if amount >= ars_from else "USD"


# Facebook Marketplace (AR) shows almost every price with a bare "$": sellers
# type dollars ("$ 11.900") or pesos ("$ 11.900.000"), and parts in pesos
# ("$ 350.000" a pair of seats). The collector reads "$" below a million as
# USD; at or above this a bare-"$" Facebook price is an ARS amount (a used
# car is rarely sold for USD 100.000; FB_USD_CEILING). A sign that says
# dollars («US$», «U$S», «USD») is not ambiguous and is never reinterpreted.
FACEBOOK_USD_CEILING = float(os.getenv("FB_USD_CEILING", "100000"))
# ... except for these, which do cost that much in dollars in Argentina: whole
# premium makes (an X5, a GLE, a Defender, a Q8 or an XC90 is sold above USD
# 100.000), and the big pickups and SUVs of the mainstream ones.
HIGH_END_MAKES = frozenset({"porsche", "ferrari", "lamborghini", "maserati", "bentley", "rolls-royce",
                            "mclaren", "aston martin", "lotus", "bmw", "mercedes-benz", "audi",
                            "land rover", "lexus", "volvo", "jaguar", "alfa romeo", "cadillac",
                            "lincoln", "genesis", "infiniti"})
HIGH_END_MODELS = frozenset({("toyota", "land cruiser"), ("toyota", "tundra"), ("toyota", "sequoia"),
                             ("chevrolet", "corvette"), ("chevrolet", "camaro"), ("chevrolet", "tahoe"),
                             ("chevrolet", "silverado"), ("chevrolet", "suburban"),
                             ("ford", "mustang"), ("ford", "f-150"), ("ford", "f-250"), ("ford", "bronco"),
                             ("ford", "raptor"), ("ford", "expedition"),
                             ("ram", "1500"), ("ram", "2500"), ("ram", "3500"), ("ram", "trx"),
                             ("jeep", "grand cherokee"), ("jeep", "wrangler"), ("jeep", "gladiator"),
                             ("volkswagen", "touareg"), ("nissan", "patrol"), ("dodge", "challenger"),
                             ("dodge", "charger"), ("dodge", "durango")})
# Signs that name the dollar: the amount is in USD whatever its size.
_EXPLICIT_USD = re.compile(r"^(?:us\$|u\$s|usd|u\$d)$", re.IGNORECASE)


def explicit_usd(sign: str | None) -> bool:
    """Whether a price's sign names the dollar («US$», «U$S», «USD»), unlike a bare "$"."""
    return bool(sign and _EXPLICIT_USD.match(sign.strip()))


def high_end(make: str | None, model: str | None = None) -> bool:
    make, model = normalize_text(make), normalize_text(model)
    return make in HIGH_END_MAKES or any(
        make == m and (model == mo or model.startswith(mo + " ")) for m, mo in HIGH_END_MODELS)


def facebook_currency(amount: float | None, currency: str | None, *, make: str | None = None,
                      model: str | None = None, ceiling: float | None = None,
                      sign: str | None = None) -> str | None:
    """The currency of a Facebook price: a "USD" amount read from a bare "$"
    at or above `ceiling` (FACEBOOK_USD_CEILING) is ARS, unless the car is a
    high-end one. `sign` is the symbol the price was written with (None when
    unknown: Facebook AR writes a bare "$"); one that names the dollar keeps USD."""
    ceiling = FACEBOOK_USD_CEILING if ceiling is None else ceiling
    if currency == "USD" and amount and amount >= ceiling and not explicit_usd(sign) \
            and not high_end(make, model):
        return "ARS"
    return currency


def plausible_vehicle_price(amount: float | None, currency: str | None) -> bool:
    if not amount or amount <= 0:
        return False
    if currency == "USD":
        return MIN_USD_VEHICLE_PRICE <= amount <= MAX_USD_VEHICLE_PRICE
    if currency == "ARS":
        return amount >= MIN_ARS_VEHICLE_PRICE
    return False


def parse_number(num: str, multiplier: str | None = None) -> float | None:
    """ "10.900" → 10900, "16.500.000" → 16500000, "11,900" → 11900,
    "1.234.567,50" → 1234567, "5" + "millones" → 5000000, "11,5" + "millones" → 11500000."""
    num = num.strip()
    if not num:
        return None
    if _THOUSANDS.fullmatch(num):
        value = float(re.sub(r"\D", "", num))
    elif m := _THOUSANDS_CENTS.fullmatch(num):
        value = float(re.sub(r"\D", "", m.group(1)))
    else:
        try:
            value = float(num.replace(",", "."))
        except ValueError:
            return None
    if multiplier:
        value *= _MULTIPLIERS.get(multiplier.lower(), 1)
    return value

"""Detect listings whose advertised price isn't the real total.

In AR auto classifieds it's very common to publish:
  - the down payment ("anticipo")
  - a monthly installment ("cuota")
  - a savings plan slot ("plan adjudicado", "plan rombo", "círculo cerrado")
  - permuta-only listings (trade only, not for sale)

These poison the median and trigger fake "opportunities". We filter them
both at scrape time (keyword check on title) and at scoring time
(statistical sanity vs comparables).
"""
from __future__ import annotations
import re
import unicodedata


# Substrings (case-insensitive, accents stripped) that almost always indicate
# a partial / non-real price. Conservative on purpose — false positives hide
# real listings, false negatives only delay an opportunity.
_KEYWORD_PATTERNS = [
    r"\banticipo\b",
    r"\banticip\w*",                     # anticipos, anticipa
    r"\bcuota[s]?\b",
    r"\b\d+\s*cuota",                    # "12 cuotas"
    r"\b\d+\s*x\s*\$",                   # "12 x $50.000"
    r"/mes\b",
    r"\bx\s*mes\b",
    r"\bplan\s+(adjudicad|oficial|rombo|ovalo|fiat|peugeot|chevrolet|vw|ford|gm|nacional|de\s+ahorro)",
    r"\bplan\s+\w+",                     # generic "plan algo" — caught after specifics so it's broader
    r"\badjudicad",                      # "adjudicado", "adjudicada"
    r"\bcirculo\s+cerrado",
    r"\bsuscripcion\b",
    r"\bsuscribirse\b",
    r"\bahorro\s+previo",
    r"\bsolo\s+permuta\b",
    r"\bpermuto\s+por\b",
    r"\bsenia\b",                        # "seña" with seña/senia variations
    r"\bsen[ñn]a\b",
    r"\bentrega\s+inmediata\s+\$\s*\d",  # "Entrega inmediata $5.000.000" pattern
    r"\bentrega\s+y\s+cuotas",
    r"\bsin\s+entrega",
    r"\bfinanci\w+\s+(100|total)",
    r"\bplanes?\s+de\s+ahorro",
    r"\bcredito\s+\w*\s*aprobado",
]

_KW_RE = re.compile("|".join(_KEYWORD_PATTERNS), re.IGNORECASE)


def _strip_accents(s: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", s)
        if unicodedata.category(c) != "Mn"
    )


def keyword_partial(title: str | None, description: str | None = None) -> str | None:
    """Return a reason string if title/description looks like an anticipo/plan,
    else None."""
    haystack = " ".join(filter(None, [title, description]))
    if not haystack:
        return None
    norm = _strip_accents(haystack).lower()
    m = _KW_RE.search(norm)
    if m:
        return f"keyword: {m.group(0).strip()}"
    return None


# Statistical thresholds (used at scoring time, not scrape time)
SUSPICIOUS_BELOW_MEDIAN_PCT = 50.0   # below this, flag as suspicious unless explicitly priced
ALMOST_CERTAIN_BELOW_MEDIAN_PCT = 65.0  # below this, virtually never a real total price


def statistical_partial(price_usd: float, median_usd: float) -> str | None:
    """Return a reason if the price is implausibly low relative to median."""
    if not price_usd or not median_usd or median_usd <= 0:
        return None
    discount = (1 - price_usd / median_usd) * 100
    if discount >= ALMOST_CERTAIN_BELOW_MEDIAN_PCT:
        return f"precio {discount:.0f}% bajo mediana — casi seguro anticipo/plan"
    return None


def is_suspicious_discount(price_usd: float, median_usd: float) -> str | None:
    """Discount > SUSPICIOUS but < ALMOST_CERTAIN — worth flagging in the
    notification but not auto-hiding."""
    if not price_usd or not median_usd or median_usd <= 0:
        return None
    discount = (1 - price_usd / median_usd) * 100
    if SUSPICIOUS_BELOW_MEDIAN_PCT <= discount < ALMOST_CERTAIN_BELOW_MEDIAN_PCT:
        return f"descuento {discount:.0f}% es alto — verificar que no sea anticipo"
    return None

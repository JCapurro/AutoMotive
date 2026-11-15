"""From active listings to prospects. Pure: the rows come from db.py.

* A seller is (source, seller_name) with MIN to MAX active listings, the same
  base as the manual batches.
* Sellers that publish the same cars are one prospect: two or more identical
  listings (make, model, year, price) join them, as a phone they share does.
  On Facebook one agency often posts with 2 to 5 profiles.
* Official dealers, chains and savings plans are left out, and so is anyone
  already contacted (ya-contactados.json and the prospects table).
"""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping

from intelligence.seller import agency_voice
from prospector import phones
from prospector.rules import fold

MIN_LISTINGS = 3
MAX_LISTINGS = 60

SOURCE_LABEL = {
    "mercadolibre": "Mercado Libre", "facebook": "Marketplace", "deruedas": "deRuedas",
    "rosariogarage": "RosarioGarage", "autocosmos": "Autocosmos",
}
_LABEL_TO_SOURCE = {fold(v): k for k, v in SOURCE_LABEL.items()}

# Official dealers, chains and savings plans (Juan, 15/11/2026).
_EXCLUDED_NAME = re.compile(
    r"\b(kavak|car ?one|autocity|randazzo|car ?cash|san jorge|tienda oficial|concesionari[oa] oficial|"
    r"plan(es)? de ahorro|autoahorro|plan rombo|plan ovalo|circulo cerrado|ahorro previo|chevrolet plan|"
    r"fiat plan|plan nacional|"
    # Official dealer groups, chains in all but name.
    r"taraborelli|dietrich|fortecar|espasa|derka y vargas)\b")
_PLAN_TEXT = re.compile(r"\b(plan(es)? de ahorro|adjudicad[oa]|suscripcion|cuota ?1 ?\$|plan ovalo|plan rombo|"
                        r"autoahorro|circulo cerrado|licitacion)\b")
_BUSINESS_NAME = re.compile(
    r"\b(automotores|automotriz|autos|automoviles|motors?|cars?|agencia|multimarcas?|usados|concesionari[ao]|"
    r"garage|garaje|rodados|s\.?a\.?|s\.?r\.?l\.?|group|grupo|car ?center|autoplan|vehiculos|"
    r"compra ?venta|consignaciones|importados)\b")


@dataclass
class Seller:
    source: str
    name: str
    listings: list[dict[str, Any]] = field(default_factory=list)

    @property
    def key(self) -> str:
        return f"{self.source}|{self.name}"


@dataclass
class Prospect:
    sellers: list[Seller]
    kind: str = "persona"               # 'agencia' | 'persona'
    phone: str | None = None
    phone_source: str | None = None     # 'aviso' | 'pagina_aviso' | 'web'
    phone_evidence: str | None = None   # where it was read (listing URL or public page)

    @property
    def keys(self) -> list[str]:
        return sorted(s.key for s in self.sellers)

    @property
    def key(self) -> str:
        return self.keys[0]

    @property
    def listings(self) -> list[dict[str, Any]]:
        seen: dict[Any, dict[str, Any]] = {}
        for s in self.sellers:
            for row in s.listings:
                seen.setdefault(row["id"], row)
        return list(seen.values())

    @property
    def sources(self) -> list[str]:
        return sorted({s.source for s in self.sellers})

    @property
    def display_name(self) -> str:
        """The name of the profile with the most listings."""
        return max(self.sellers, key=lambda s: (len(s.listings), s.name)).name


def group_sellers(rows: Iterable[Mapping[str, Any]]) -> list[Seller]:
    by: dict[tuple[str, str], Seller] = {}
    for row in rows:
        name = (row.get("seller_name") or "").strip()
        if not name:
            continue
        key = (row["source"], name)
        by.setdefault(key, Seller(row["source"], name)).listings.append(dict(row))
    return [s for s in by.values() if MIN_LISTINGS <= len(s.listings) <= MAX_LISTINGS]


def _signature(row: Mapping[str, Any]) -> tuple | None:
    if not (row.get("make") and row.get("model") and row.get("year") and row.get("price")):
        return None
    return (fold(row["make"]), fold(row["model"]), int(row["year"]), round(float(row["price"])))


class _Union:
    def __init__(self, n: int):
        self.parent = list(range(n))

    def find(self, i: int) -> int:
        while self.parent[i] != i:
            self.parent[i] = self.parent[self.parent[i]]
            i = self.parent[i]
        return i

    def join(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[max(ra, rb)] = min(ra, rb)


def merge_duplicates(sellers: list[Seller], *, min_shared: int = 2,
                     phone_of: Mapping[str, str | None] | None = None) -> list[list[Seller]]:
    """Groups of sellers that are the same business: two or more identical
    listings in common, or the same phone (phone_of: seller key → number)."""
    sellers = sorted(sellers, key=lambda s: s.key)
    union = _Union(len(sellers))
    owners: dict[tuple, set[int]] = defaultdict(set)
    for i, s in enumerate(sellers):
        for row in s.listings:
            sig = _signature(row)
            if sig:
                owners[sig].add(i)
    shared: Counter[tuple[int, int]] = Counter()
    for idx in owners.values():
        if 1 < len(idx) <= 6:      # a very common car at a round price is not a signal
            ordered = sorted(idx)
            for a in range(len(ordered)):
                for b in range(a + 1, len(ordered)):
                    shared[(ordered[a], ordered[b])] += 1
    for (a, b), n in shared.items():
        if n >= min_shared:
            union.join(a, b)
    if phone_of:
        by_phone: dict[str, int] = {}
        for i, s in enumerate(sellers):
            number = phone_of.get(s.key)
            if number:
                if number in by_phone:
                    union.join(by_phone[number], i)
                else:
                    by_phone[number] = i
    groups: dict[int, list[Seller]] = defaultdict(list)
    for i, s in enumerate(sellers):
        groups[union.find(i)].append(s)
    return list(groups.values())


def exclusion_reason(prospect: Prospect) -> str | None:
    for s in prospect.sellers:
        if _EXCLUDED_NAME.search(fold(s.name)):
            return "cadena u oficial"
    rows = prospect.listings
    plan = sum(1 for r in rows if _PLAN_TEXT.search(fold((r.get("title") or "") + " " + (r.get("description") or ""))))
    if rows and plan * 2 > len(rows):
        return "plan de ahorro"
    return None


def classify(prospect: Prospect) -> str:
    """'agencia' or 'persona' (someone who buys and sells without a business name)."""
    if any(_BUSINESS_NAME.search(fold(s.name)) for s in prospect.sellers):
        return "agencia"
    rows = prospect.listings
    dealer = sum(1 for r in rows if r.get("seller_type") == "dealer")
    if rows and dealer * 2 >= len(rows):
        return "agencia"
    voiced = sum(1 for r in rows if agency_voice(r.get("description")))
    if voiced >= 2:
        return "agencia"
    if len(prospect.sellers) > 1:      # several profiles with the same cars
        return "agencia"
    return "persona"


def phone_from_listings(prospect: Prospect, *, banned: frozenset[str] = frozenset()) -> tuple[str, str] | None:
    """(number, listing URL) the seller wrote in their own listings, the one repeated the most."""
    rows = prospect.listings
    number = phones.best_of((r.get("description") for r in rows), banned=banned)
    if not number:
        return None
    url = next((r.get("url") for r in rows if number in phones.find_in_text(r.get("description"))), None)
    return number, url or ""


def first_name(prospect: Prospect) -> str | None:
    """A person's first name, only when the profile looks like «Nombre Apellido»."""
    if prospect.kind != "persona":
        return None
    name = prospect.display_name.strip()
    parts = name.split()
    if 2 <= len(parts) <= 4 and all(re.fullmatch(r"[A-ZÁÉÍÓÚÑ][a-záéíóúñü]+", p) for p in parts[:2]):
        return parts[0]
    return None


# ----------------------------------------------------------------------------
# Already contacted
# ----------------------------------------------------------------------------

@dataclass(frozen=True)
class Contacted:
    names: frozenset[str]                 # folded names, any source
    pairs: frozenset[tuple[str, str]]     # (source, folded name)
    urls: frozenset[str]


def _clean_url(url: str) -> str:
    return (url or "").split("#")[0].rstrip("/").lower()


def load_contacted(path: Path) -> Contacted:
    if not path.exists():
        return Contacted(frozenset(), frozenset(), frozenset())
    data = json.loads(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    pairs: set[tuple[str, str]] = set()
    urls: set[str] = set()
    for item in data:
        source = _LABEL_TO_SOURCE.get(fold(item.get("source") or ""), fold(item.get("source") or ""))
        for name in [item.get("name") or ""] + [n for n in (item.get("also") or "").split(",")]:
            n = fold(name).strip()
            if n:
                names.add(n)
                pairs.add((source, n))
        if item.get("url"):
            urls.add(_clean_url(item["url"]))
    return Contacted(frozenset(names), frozenset(pairs), frozenset(urls))


def already_contacted(prospect: Prospect, contacted: Contacted) -> bool:
    for s in prospect.sellers:
        n = fold(s.name).strip()
        if (s.source, n) in contacted.pairs:
            return True
        # A business name (not a person's) contacted on another portal is the same business.
        if n in contacted.names and _BUSINESS_NAME.search(n):
            return True
    return any(_clean_url(r.get("url") or "") in contacted.urls for r in prospect.listings)


def build_prospects(rows: Iterable[Mapping[str, Any]], *, contacted: Contacted,
                    banned_phones: frozenset[str] = frozenset()) -> tuple[list[Prospect], Counter]:
    """Every prospect of today's base, with its phone when one is in its listings,
    and how many were left out and why."""
    sellers = group_sellers(rows)
    seller_phone: dict[str, str | None] = {}
    for s in sellers:
        found = phones.best_of((r.get("description") for r in s.listings), banned=banned_phones)
        seller_phone[s.key] = found
    out: list[Prospect] = []
    dropped: Counter = Counter()
    for group in merge_duplicates(sellers, phone_of=seller_phone):
        p = Prospect(sellers=group)
        reason = exclusion_reason(p)
        if reason:
            dropped[reason] += 1
            continue
        if already_contacted(p, contacted):
            dropped["ya contactado a mano"] += 1
            continue
        p.kind = classify(p)
        found = phone_from_listings(p, banned=banned_phones)
        if found:
            p.phone, p.phone_evidence = found
            p.phone_source = "aviso"
        out.append(p)
    return out, dropped


def shared_phones(rows: Iterable[Mapping[str, Any]], *, max_sellers: int = 3) -> frozenset[str]:
    """Numbers written by more sellers than one business has profiles: a portal's,
    a garage's or a gestor's, never the seller's own."""
    owners: dict[str, set[str]] = defaultdict(set)
    for r in rows:
        for n in phones.find_in_text(r.get("description")):
            owners[n].add(f"{r['source']}|{r.get('seller_name')}")
    return frozenset(n for n, who in owners.items() if len(who) > max_sellers)

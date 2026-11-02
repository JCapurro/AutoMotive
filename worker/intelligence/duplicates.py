"""Which listings look like the same car (PAR-02 resto,
docs/superpowers/specs/2026-11-02-par02-resto-design.md, decisions 3, 4 and 6).
Pure: rows of one (make, model) group in, pairs out; pipeline/risk_duplicates.py
does the I/O and db/repos/duplicates.py the SQL.

A row: id, source, year, mileage_km, price_usd, price_partial,
probable_repost_of, trim, transmission, fuel, seller_type, dealer_inferred,
seller_key and `zone` ({province_id, department, precision, lat, lon} or None)
and `hashes` (the hex photo hashes, attributes._photo_hashes, or []).

Per pair, at most one kind (decision 3, precedence):

* cross_source_photos: different sources, the data match (same year, km within
  km_tol_pct, price_usd within price_tol_pct, neither partial, not linked as a
  repost) and a shared photo (hash distance <= phash_max_distance).
* duplicate_photos: a shared photo and either another source or the same
  source in another zone (locality precision on both, another department or
  farther than data_max_dist_km), and not the case above. Not between two
  listings of the same seller (same source and seller_key: a re-publication,
  the repost flag's) nor linked as a repost. The year is not compared: a copied
  photo can come with another year.
* cross_source_data: no shared photo, the data match, and every guard of
  decision 4: km >= data_min_km on both; trim, transmission and fuel equal
  when both state them; both zones at locality precision, same province and
  (same department or <= data_max_dist_km); neither seller an effective dealer
  (intelligence/seller.py); and mutual uniqueness: each is the other's only
  data candidate in the other's source, and neither has a data twin in its
  own source (a twin means a common configuration, e.g. a dealer's stock).

A hash found (within phash_max_distance) on listings of common_min_sellers or
more distinct sellers is a catalog photo, a logo or a placeholder: it counts
for no pair. Nor do near-flat hashes (intelligence/photo_hash.is_flat).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

from intelligence.photo_hash import best_match, distance, is_flat, valid
from intelligence.seller import effective_seller

KINDS = ("duplicate_photos", "cross_source_photos", "cross_source_data")
# Bump when a rule changes: stored in evidence.rule_v.
RULE_VERSION = 1


@dataclass(frozen=True)
class Pair:
    a: int
    b: int
    kind: str
    distance: int | None
    evidence: dict[str, Any] = field(default_factory=dict)


def _pct(x: float, y: float) -> float:
    """|x - y| as a % of the larger one."""
    top = max(abs(x), abs(y))
    return 0.0 if top == 0 else abs(x - y) * 100 / top


def haversine_km(a: Mapping[str, Any], b: Mapping[str, Any]) -> float | None:
    if None in (a.get("lat"), a.get("lon"), b.get("lat"), b.get("lon")):
        return None
    la1, lo1, la2, lo2 = map(math.radians, (a["lat"], a["lon"], b["lat"], b["lon"]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 6371.0 * 2 * math.asin(math.sqrt(min(1.0, h)))


def _repost_linked(a: Mapping[str, Any], b: Mapping[str, Any]) -> bool:
    ra, rb = a.get("probable_repost_of"), b.get("probable_repost_of")
    return ra == b["id"] or rb == a["id"] or (ra is not None and ra == rb)


def data_match(a: Mapping[str, Any], b: Mapping[str, Any], cs: Mapping[str, Any]) -> dict[str, float] | None:
    """The data both levels of cross_source_duplicate share (not the source
    check): {km_pct, price_pct} or None."""
    if a.get("price_partial") or b.get("price_partial") or _repost_linked(a, b):
        return None
    if a.get("year") is None or a.get("year") != b.get("year"):
        return None
    km_a, km_b, pa, pb = a.get("mileage_km"), b.get("mileage_km"), a.get("price_usd"), b.get("price_usd")
    if km_a is None or km_b is None or not pa or not pb:
        return None
    km_pct, price_pct = _pct(km_a, km_b), _pct(float(pa), float(pb))
    if km_pct > cs["km_tol_pct"] or price_pct > cs["price_tol_pct"]:
        return None
    return {"km_pct": round(km_pct, 2), "price_pct": round(price_pct, 2)}


def _same_text(x: Any, y: Any) -> bool:
    """Equal when both are stated; an unstated one never blocks."""
    if not x or not y:
        return True
    return str(x).strip().lower() == str(y).strip().lower()


def zone_relation(a: Mapping[str, Any], b: Mapping[str, Any], max_km: float) -> dict[str, Any] | None:
    """For two locality-precision zones: {near, dist_km, same_department}; None
    when either lacks a fine zone (then nothing is said about the place)."""
    za, zb = a.get("zone") or {}, b.get("zone") or {}
    if za.get("precision") != "locality" or zb.get("precision") != "locality":
        return None
    dist = haversine_km(za, zb)
    same_dep = (za.get("province_id") is not None and za.get("province_id") == zb.get("province_id")
                and za.get("department") is not None and za.get("department") == zb.get("department"))
    near = za.get("province_id") == zb.get("province_id") and (same_dep or (dist is not None and dist <= max_km))
    return {"near": bool(near), "dist_km": None if dist is None else round(dist, 1), "same_department": same_dep}


def _seller(row: Mapping[str, Any]) -> tuple[str, str]:
    return (row["source"], row["seller_key"]) if row.get("seller_key") else ("id", str(row["id"]))


def common_hashes(rows: Iterable[Mapping[str, Any]], max_d: int, min_sellers: int) -> set[str]:
    """Hashes that appear (within max_d) on listings of min_sellers or more sellers."""
    owners: list[tuple[str, tuple[str, str]]] = []
    for r in rows:
        for h in r.get("hashes") or ():
            if valid(h) and not is_flat(h):
                owners.append((h, _seller(r)))
    common = set()
    for h, _ in owners:
        sellers = {s for other, s in owners if distance(h, other) <= max_d}
        if len(sellers) >= min_sellers:
            common.add(h)
    return common


def _data_guards(a: Mapping[str, Any], b: Mapping[str, Any], cs: Mapping[str, Any]) -> dict[str, Any] | None:
    if min(a["mileage_km"], b["mileage_km"]) < cs["data_min_km"]:
        return None
    if not all(_same_text(a.get(k), b.get(k)) for k in ("trim", "transmission", "fuel")):
        return None
    if effective_seller(a) == "dealer" or effective_seller(b) == "dealer":
        return None
    zone = zone_relation(a, b, cs["data_max_dist_km"])
    if zone is None or not zone["near"]:
        return None
    return zone


def detect(rows: list[Mapping[str, Any]], risk: Mapping[str, Any]) -> list[Pair]:
    """Every pair of one (make, model) group, a < b, with its kind."""
    cs, ph = risk["cross_source"], risk["photo_hash"]
    max_d = risk["phash_max_distance"]
    common = common_hashes(rows, max_d, ph["common_min_sellers"])
    by_id = {r["id"]: r for r in rows}
    ids = sorted(by_id)
    pairs: dict[tuple[int, int], Pair] = {}

    # Photos: only the hashed ones, all against all.
    hashed = [i for i in ids if any(valid(h) for h in by_id[i].get("hashes") or ())]
    for x, ia in enumerate(hashed):
        a = by_id[ia]
        for ib in hashed[x + 1:]:
            b = by_id[ib]
            match = best_match(a["hashes"], b["hashes"], ignore=common)
            if match is None or match[2] > max_d:
                continue
            evidence: dict[str, Any] = {"matched": [list(match)], "rule_v": RULE_VERSION}
            data = data_match(a, b, cs) if a["source"] != b["source"] else None
            if data is not None:
                pairs[(ia, ib)] = Pair(ia, ib, "cross_source_photos", match[2], {**evidence, **data})
                continue
            if _repost_linked(a, b) or (a.get("seller_key") and _seller(a) == _seller(b)):
                continue
            zone = zone_relation(a, b, cs["data_max_dist_km"])
            if a["source"] == b["source"] and (zone is None or zone["near"]):
                continue           # the same source and place: a re-publication (repost)
            if zone is not None:
                evidence["zone"] = zone
            pairs[(ia, ib)] = Pair(ia, ib, "duplicate_photos", match[2], evidence)

    # Data only: candidates by the shared data rules, across sources and within.
    by_year: dict[int, list[int]] = {}
    for i in ids:
        r = by_id[i]
        if r.get("year") is not None and r.get("mileage_km") is not None and r.get("price_usd"):
            by_year.setdefault(r["year"], []).append(i)
    other_source: dict[int, dict[str, list[int]]] = {}
    twins: set[int] = set()
    matched: dict[tuple[int, int], dict[str, float]] = {}
    for group in by_year.values():
        for x, ia in enumerate(group):
            for ib in group[x + 1:]:
                data = data_match(by_id[ia], by_id[ib], cs)
                if data is None:
                    continue
                sa, sb = by_id[ia]["source"], by_id[ib]["source"]
                if sa == sb:
                    twins.update((ia, ib))
                    continue
                matched[(ia, ib)] = data
                other_source.setdefault(ia, {}).setdefault(sb, []).append(ib)
                other_source.setdefault(ib, {}).setdefault(sa, []).append(ia)
    for (ia, ib), data in matched.items():
        if (ia, ib) in pairs:
            continue
        a, b = by_id[ia], by_id[ib]
        if ia in twins or ib in twins:
            continue
        if other_source[ia][b["source"]] != [ib] or other_source[ib][a["source"]] != [ia]:
            continue
        zone = _data_guards(a, b, cs)
        if zone is None:
            continue
        pairs[(ia, ib)] = Pair(ia, ib, "cross_source_data", None,
                               {**data, "zone": zone, "rule_v": RULE_VERSION})
    return [pairs[k] for k in sorted(pairs)]


def rows_out(pairs: Iterable[Pair], risk: Mapping[str, Any]) -> dict[tuple[int, int], dict[str, Any]]:
    """The listing_duplicates rows the pairs make, both ways, by the signal
    modes: "off" stores nothing, "shadow" stores shown = false."""
    out: dict[tuple[int, int], dict[str, Any]] = {}
    for p in pairs:
        mode = risk["signals"].get(p.kind, "off")
        if mode == "off":
            continue
        for x, y in ((p.a, p.b), (p.b, p.a)):
            out[(x, y)] = {"listing_id": x, "other_id": y, "kind": p.kind, "shown": mode == "on",
                           "photo_distance": p.distance, "evidence": p.evidence}
    return out

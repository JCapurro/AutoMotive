"""The facts JSON of one prospect: everything a message may say, already
computed and formatted, so the writer copies numbers and never makes them up.

Pure except `Facts.build`, which takes the db module's functions as arguments
(tests pass fakes).
"""
from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from statistics import median
from typing import Any, Callable, Iterable, Mapping

from intelligence.red_flags import title_damage
from intelligence.seller import agency_voice
from normalization.price_check import keyword_partial
from normalization.geo import haversine_km
from normalization.zone import DEFAULT_ZONE_MAP, _GBA_PARTIDOS, derive_zone, resolve_region
from prospector.rules import fold
from prospector.sellers import SOURCE_LABEL, Prospect

PROVINCES = {
    "02": "CABA", "06": "Buenos Aires", "10": "Catamarca", "14": "Córdoba", "18": "Corrientes", "22": "Chaco",
    "26": "Chubut", "30": "Entre Ríos", "34": "Formosa", "38": "Jujuy", "42": "La Pampa", "46": "La Rioja",
    "50": "Mendoza", "54": "Misiones", "58": "Neuquén", "62": "Río Negro", "66": "Salta", "70": "San Juan",
    "74": "San Luis", "78": "Santa Cruz", "82": "Santa Fe", "86": "Santiago del Estero", "90": "Tucumán",
    "94": "Tierra del Fuego",
}
REGION_LABEL = {"amba": "AMBA", "buenos_aires_resto": "interior de Buenos Aires", "cordoba": "Córdoba",
                "litoral": "Litoral", "nea": "NEA", "cuyo": "Cuyo", "noa": "NOA", "patagonia": "Patagonia"}

OLD_DAYS = 45
HOOK_HOURS = 72
HOOK_MIN_PCT = 10.0       # «high» in the worker: 10 % or more below the comparables
HOOK_MAX_PCT = 35.0       # the worker flags 50 % as suspicious; past 35 % a hook is more often a typo than a deal
HOOK_MIN_N = 8            # fewer comparables than this is not a credible «X % abajo de N parecidos»
# Past 25 % a discount needs more proof before Juan offers the car (15/11/2026).
HOOK_DEEP_PCT = 25.0
HOOK_DEEP_MIN_N = 20
HOOK_DEEP_MIN_PHOTOS = 4
HOOK_MIN_PHOTOS = 2
HOOK_CHECKS_PER_PROSPECT = 5    # listing pages read to find 2 hooks still published
DEMAND_RADIUS_KM = 60
HOOK_RADIUS_KM = DEMAND_RADIUS_KM   # a hook outside their partido must be this close, like a search's radius
DEMAND_MIN = 3            # below this a count could point at a person
POSITION_MIN_N = 5
PRODUCT = {
    "que_hace": ("Ese Auto lee los avisos nuevos de Mercado Libre, Marketplace, deRuedas, RosarioGarage, "
                 "Autocosmos y sitios de agencias, los compara con autos parecidos y avisa cuando aparece uno "
                 "por debajo del resto."),
    "prueba_sin_costo_dias": 7,
}


def money(value: float | None, currency: str | None) -> str | None:
    if value is None:
        return None
    n = f"{int(round(float(value))):,}".replace(",", ".")
    return f"US$ {n}" if (currency or "").upper() == "USD" else f"${n}"


def car_name(row: Mapping[str, Any], *, trim: bool = True) -> str:
    parts = [row.get("make"), row.get("model")]
    if trim and row.get("trim"):
        parts.append(row["trim"])
    if row.get("year"):
        parts.append(str(row["year"]))
    return " ".join(str(p) for p in parts if p)


def _days(row: Mapping[str, Any], now: datetime) -> int | None:
    start = row.get("published_at") or row.get("first_seen_at")
    if not start:
        return None
    return max(0, (now - start).days)


@dataclass(frozen=True)
class Zone:
    province_id: str | None
    department: str | None
    region: str | None

    @property
    def amba(self) -> bool:
        return self.region == "amba" or self.province_id == "02"

    def label(self) -> str | None:
        if self.province_id == "02":
            return "CABA"
        prov = PROVINCES.get(self.province_id or "")
        if self.department and prov:
            return f"{self.department}, {prov}"
        return prov

    def area_label(self) -> str | None:
        """Where the comparables of the price position come from."""
        if self.amba:
            return "AMBA"
        return PROVINCES.get(self.province_id or "")


def with_zone(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Fills province_id/department/precision from lat/lon where listing_zones has no row."""
    for r in rows:
        if r.get("province_id") is None and r.get("lat") is not None and r.get("lon") is not None:
            z = derive_zone(r["lat"], r["lon"], r.get("location_text"), r.get("source"))
            if z:
                r["province_id"], r["department"], r["precision"] = z.province_id, z.department, z.precision
    return rows


def in_zone(row: Mapping[str, Any], zone: "Zone") -> bool:
    if zone.amba:
        return _in_amba(row)
    return bool(zone.province_id) and row.get("province_id") == zone.province_id


def position(pool: Iterable[Mapping[str, Any]], price_usd: float, zone: "Zone") -> dict[str, Any]:
    prices = [float(r["price_usd"]) for r in pool if r.get("price_usd") and in_zone(r, zone)]
    return {"n": len(prices), "cheaper": sum(1 for p in prices if p < price_usd)}


def zone_of(rows: Iterable[Mapping[str, Any]], zone_map: Mapping[str, Any] | None) -> Zone:
    places = Counter((r.get("province_id"), r.get("department"), r.get("precision")) for r in rows if r.get("province_id"))
    if not places:
        return Zone(None, None, None)
    (province, department, precision), _ = places.most_common(1)[0]
    region = resolve_region(dict(zone_map or DEFAULT_ZONE_MAP), province, department, precision)
    if province == "02":
        region = "amba"
    return Zone(province, department if precision == "locality" else None, region)


def place_of(row: Mapping[str, Any]) -> str | None:
    if row.get("province_id") == "02":
        return "CABA"
    prov = PROVINCES.get(row.get("province_id") or "")
    if row.get("department") and row.get("precision") == "locality":
        return f"{row['department']}, {prov}" if prov else row["department"]
    return prov


def stock_facts(prospect: Prospect, now: datetime) -> dict[str, Any]:
    rows = prospect.listings
    models = Counter(f"{r['make']} {r['model']}" for r in rows if r.get("make") and r.get("model"))
    years = [r["year"] for r in rows if r.get("year")]
    by_cur: dict[str, list[float]] = {}
    for r in rows:
        if r.get("price"):
            by_cur.setdefault((r.get("currency") or "ARS").upper(), []).append(float(r["price"]))
    prices = {cur: {"desde": money(min(v), cur), "hasta": money(max(v), cur), "avisos": len(v)}
              for cur, v in by_cur.items()}
    ages = [(d, r) for r in rows if (d := _days(r, now)) is not None]
    old = sorted([(d, r) for d, r in ages if d > OLD_DAYS], key=lambda x: -x[0])
    return {
        "avisos_activos": len(rows),
        "fuentes": [SOURCE_LABEL.get(s, s) for s in prospect.sources],
        "modelos_principales": [{"modelo": m, "avisos": n} for m, n in models.most_common(5)],
        # The stock fact of a message: the total, or the models they have several of. One car of a model is not one.
        "modelos_con_varios": [{"modelo": m, "avisos": n} for m, n in models.most_common(5) if n >= 2],
        "anios": {"desde": min(years), "hasta": max(years)} if years else None,
        "precios_publicados": prices,
        "antiguedad": {
            "aclaracion": "días desde que el aviso apareció publicado (o desde que Ese Auto lo vio por primera vez)",
            "mediana_dias": int(median(d for d, _ in ages)) if ages else None,
            "avisos_con_mas_de_45_dias": len(old),
            "los_mas_viejos": [{"auto": car_name(r), "dias": d} for d, r in old[:3]],
        },
    }


def centre(prospect: Prospect, zone: "Zone") -> tuple[float, float] | None:
    """Where the seller is: the median point of their located listings in their zone."""
    located = [r for r in prospect.listings if r.get("lat") is not None and r.get("lon") is not None]
    local = [r for r in located if in_zone(r, zone)] or located
    if not local:
        return None
    return median(r["lat"] for r in local), median(r["lon"] for r in local)


def hook_candidates(pool: Iterable[Mapping[str, Any]], prospect: Prospect, zone: Zone,
                    zone_map: Mapping[str, Any] | None, *, exclude: Iterable[int] = ()) -> list[dict[str, Any]]:
    """Fresh private listings of the prospect's models in its zone, ≥10 % below
    the worker's comparables, best first."""
    mine = Counter((r["make"], r["model"]) for r in prospect.listings if r.get("make") and r.get("model"))
    own_ids = {r["id"] for r in prospect.listings}
    skip = set(exclude) | own_ids
    here = centre(prospect, zone)
    out = []
    for row in pool:
        if row["id"] in skip or (row.get("make"), row.get("model")) not in mine:
            continue
        ref = row.get("ref") or {}
        n, diff = ref.get("n") or 0, ref.get("diff_pct")
        if diff is None or n < HOOK_MIN_N or not (HOOK_MIN_PCT <= diff < HOOK_MAX_PCT):
            continue
        if placeholder_price(row.get("price")) or hook_risk(row, ref):
            continue
        if agency_voice(row.get("description")):
            continue          # a «particular» that writes like an agency (seller_for_preference)
        if zone.province_id and row.get("province_id"):
            if zone.department and row.get("department") == zone.department and row.get("province_id") == zone.province_id:
                tier = 3
            elif row.get("province_id") == zone.province_id or (zone.amba and row.get("province_id") in ("02", "06")
                                                                and _in_amba(row)):
                tier = 2
            elif zone.region and resolve_region(dict(zone_map or DEFAULT_ZONE_MAP), row["province_id"],
                                                row.get("department"), row.get("precision")) == zone.region:
                tier = 1
            else:
                continue
        else:
            continue
        km = (haversine_km(here[0], here[1], row["lat"], row["lon"])
              if here and row.get("lat") is not None and row.get("lon") is not None else None)
        if tier < 3 and (km is None or km > HOOK_RADIUS_KM):
            continue          # Tandil is not San Isidro: outside their partido, only within the radius
        own = mine[(row["make"], row["model"])]
        # Closer first; then a model they have several of, so the message's stock fact and hook match.
        rank = tier * 100 + min(own, 5) * 4 + min(diff, 30) + min(n, 40) / 4
        out.append({"row": row, "tier": tier, "rank": rank, "own": own,
                    "km": None if km is None else round(km)})
    return sorted(out, key=lambda c: -c["rank"])


# The published price is not the total: down payment, installments, «entrega».
_PARTIAL_TEXT = re.compile(r"\b(anticip\w*|financiad[oa]s?|financiacion|financio|cuotas?|entrega|"
                           r"tomo (?:tu )?usado|permuta mas|saldo)\b")
_PARTIAL_DESC = re.compile(r"\b(anticipo|entrega de \$|entrega minima|\d+ cuotas|cuotas fijas|saldo en cuotas|"
                           r"financiado en|precio de contado)\b")
# Damaged or not runnable: what the worker reads in titles plus the usual phrasings in descriptions.
_DAMAGE_TEXT = re.compile(r"\b(chocad[oa]s?|siniestrad[oa]s?|granizad[oa]s?|volcad[oa]s?|incendiad[oa]s?|"
                          r"para repuestos?|por partes|sin motor|motor fundido|a reparar|para reparar|para arreglar|"
                          r"con detalles|no arranca|sin papeles|baja definitiva|desarme)\b")
_NEGATED = re.compile(r"\b(no|sin|nunca|jamas|cero)\s+(?:\w+\s+)?$")


def _photos(row: Mapping[str, Any]) -> int:
    images = row.get("images")
    return len(images) if isinstance(images, list) else 0


def _damaged(text: str) -> bool:
    return any(not _NEGATED.search(text[:m.start()]) for m in _DAMAGE_TEXT.finditer(text))


def hook_risk(row: Mapping[str, Any], ref: Mapping[str, Any]) -> str | None:
    """Why the discount of a hook candidate may not be real, or None."""
    title, desc = fold(row.get("title") or ""), fold(row.get("description") or "")
    if keyword_partial(row.get("title"), row.get("description")) or _PARTIAL_TEXT.search(title) \
            or _PARTIAL_DESC.search(desc):
        return "anticipo o cuotas"
    if title_damage(row.get("title")) or _damaged(title) or _damaged(desc):
        return "daño"
    photos = _photos(row)
    if photos < HOOK_MIN_PHOTOS:
        return "una sola foto"
    price, cur = float(row.get("price") or 0), (row.get("currency") or "").upper()
    if (cur == "ARS" and price < 1_000_000) or (cur == "USD" and not 1_000 <= price <= 200_000):
        return "precio que no cierra con la moneda"
    published, pub_cur = row.get("price_published"), (row.get("price_published_currency") or "").upper()
    if published and pub_cur and (pub_cur != cur or abs(float(published) - price) > 0.05 * price):
        return "el precio publicado y el de la descripción no coinciden"
    if (ref.get("diff_pct") or 0) >= HOOK_DEEP_PCT:
        if (ref.get("n") or 0) < HOOK_DEEP_MIN_N or photos < HOOK_DEEP_MIN_PHOTOS \
                or len(desc) < 40 or not row.get("mileage_km"):
            return "descuento de más del 25 % sin respaldo suficiente"
    return None


def placeholder_price(price) -> bool:
    """1.111.111, 12.345.678, 9.999.999: a price nobody means."""
    if not price:
        return True
    digits = str(int(float(price)))
    if len(set(digits)) == 1 or digits in "1234567890" or digits in "9876543210":
        return True
    return bool(re.fullmatch(r"(\d)\1{4,}0*", digits))      # 7.777.700, 99.999.000


def _in_amba(row: Mapping[str, Any]) -> bool:
    return row.get("province_id") == "02" or (row.get("province_id") == "06" and row.get("department") in _GBA_PARTIDOS)


def when_published(seen: datetime, now: datetime) -> str:
    """«hoy», «ayer» or «anteayer», in Argentine days."""
    art = timezone(timedelta(hours=-3))
    days = (now.astimezone(art).date() - seen.astimezone(art).date()).days
    return {0: "hoy", 1: "ayer"}.get(days, "anteayer" if days == 2 else "en los últimos días")


def hook_fact(candidate: Mapping[str, Any], now: datetime, slot: str) -> dict[str, Any]:
    row, ref = candidate["row"], candidate["row"]["ref"]
    hours = max(1, int((now - row["first_seen_at"]).total_seconds() // 3600))
    return {
        "id": slot,
        "tipo": "oportunidad",
        "listing_id": row["id"],
        "auto": car_name(row),
        "lugar": place_of(row),
        "precio_publicado": money(row.get("price"), row.get("currency")),
        "porcentaje_abajo_de_comparables": int(math.floor(ref["diff_pct"])),
        "cantidad_de_comparables": int(ref["n"]),
        "publicado": when_published(row["first_seen_at"], now),
        "publicado_hace_horas": hours,
        "vendedor": "particular",
        "fuente": SOURCE_LABEL.get(row["source"], row["source"]),
        "km": row.get("mileage_km"),
        "url": row.get("url"),
        "cercania": "mismo partido o ciudad" if candidate["tier"] == 3 else f"a {candidate.get('km')} km",
        **({"distancia_km": candidate["km"]} if candidate.get("km") is not None else {}),
        "avisos_suyos_de_ese_modelo": candidate.get("own"),
        **({"verificado": candidate["verified"]} if candidate.get("verified") else {}),
    }


@dataclass
class Lookups:
    """The database reads `build` needs (db.py in production, fakes in tests)."""
    pool: Callable[[int], list[Mapping[str, Any]]]       # the worker's comparable pool of a listing
    demand: Callable[[str, str, float, float], int]
    stopped: Callable[[list[tuple[str, str]]], int]


def price_positions(prospect: Prospect, zone: Zone, lookups: Lookups, *, limit: int = 3) -> list[dict[str, Any]]:
    """Where 2 or 3 of their cars stand among the comparables published in their zone."""
    rows = [r for r in prospect.listings if r.get("price_usd") and r.get("year") and r.get("make")
            and not r.get("price_partial") and not placeholder_price(r.get("price"))]
    models = Counter((r["make"], r["model"]) for r in rows)
    rows.sort(key=lambda r: (-models[(r["make"], r["model"])], -(r.get("year") or 0)))
    out, seen = [], set()
    for r in rows:
        key = (r["make"], r["model"])
        if key in seen:
            continue
        pos = position(lookups.pool(r["id"]), float(r["price_usd"]), zone)
        if pos["n"] < POSITION_MIN_N:
            continue
        if pos["cheaper"] * 100 < 3 * pos["n"]:
            continue      # cheaper than 97 % of its peers: a down payment or a typo, not a fact to quote
        seen.add(key)
        n, cheaper = int(pos["n"]), int(pos["cheaper"])
        out.append({
            "auto": car_name(r),
            "precio_publicado": money(r.get("price"), r.get("currency")),
            "comparables_publicados_en_zona": n,
            "zona_de_comparacion": zone.area_label(),
            "comparables_mas_baratos": cheaper,
            "percentil": int(round(100 * cheaper / n)),
            "lectura": ("entre los más baratos" if cheaper * 4 <= n else
                        "entre los más caros" if cheaper * 4 >= 3 * n else "en la mitad"),
            "url": r.get("url"),
        })
        if len(out) >= limit:
            break
    return out


def demand_facts(prospect: Prospect, zone_rows: list[Mapping[str, Any]], lookups: Lookups) -> list[dict[str, Any]]:
    located = [r for r in zone_rows if r.get("lat") is not None and r.get("lon") is not None]
    if not located:
        return []
    lat = median(r["lat"] for r in located)
    lon = median(r["lon"] for r in located)
    models = Counter((r["make"], r["model"]) for r in prospect.listings if r.get("make") and r.get("model"))
    out = []
    for (make, model), _ in models.most_common(4):
        n = lookups.demand(make, model, lat, lon)
        if n >= DEMAND_MIN:
            out.append({"modelo": f"{make} {model}", "busquedas_activas_en_ese_auto": n,
                        "radio_km": DEMAND_RADIUS_KM})
    return out


def build(prospect: Prospect, *, pool: list[Mapping[str, Any]], zone_map: Mapping[str, Any] | None,
          lookups: Lookups, now: datetime | None = None, step: str = "primero",
          exclude_hooks: Iterable[int] = (), previous: list[dict[str, Any]] | None = None,
          first_name: str | None = None, alive: Callable[[Mapping[str, Any]], Any] | None = None) -> dict[str, Any]:
    """alive(row) gives a prospector.alive.Check: with it, only hooks whose listing is still
    published (read now, or seen by the collector lately) are kept."""
    now = now or datetime.now(timezone.utc)
    rows = prospect.listings
    zone = zone_of(rows, zone_map)
    hooks = live_hooks(hook_candidates(pool, prospect, zone, zone_map, exclude=exclude_hooks), alive)
    stopped = lookups.stopped([(s.source, s.name) for s in prospect.sellers])
    facts: dict[str, Any] = {
        "paso": step,
        "saludo": greeting(prospect, first_name),
        "prospecto": {
            "tipo": prospect.kind,
            "nombre_del_perfil": prospect.display_name,
            "nombre_de_pila": first_name,
            "zona": zone.label(),
            "region": REGION_LABEL.get(zone.region or "", zone.region),
        },
        "stock": stock_facts(prospect, now),
        "dejaron_de_publicarse": {"avisos": stopped, "en_los_ultimos_dias": 30},
        "posicion_de_precios": price_positions(prospect, zone, lookups),
        "ganchos": [hook_fact(c, now, f"oportunidad_{i + 1}") for i, c in enumerate(hooks[:2])],
        "demanda_agregada": demand_facts(prospect, rows, lookups),
        "producto": PRODUCT,
    }
    if previous:
        facts["mensajes_anteriores"] = previous
    return facts


def live_hooks(candidates: list[dict[str, Any]], alive: Callable[[Mapping[str, Any]], Any] | None,
               *, keep: int = 2) -> list[dict[str, Any]]:
    """The best `keep` candidates whose listing is still published, each with when and how
    that was checked. Without `alive` (tests, reports) the first `keep` as they are."""
    if alive is None:
        return candidates[:keep]
    out: list[dict[str, Any]] = []
    for c in candidates[:HOOK_CHECKS_PER_PROSPECT]:
        check = alive(c["row"])
        if check.state != "online":
            continue
        out.append({**c, "verified": {"como": check.how, "en": check.at.isoformat()}})
        if len(out) == keep:
            break
    return out


# Common Argentine first names: a business named «Julio Quiroga Automotores» is greeted
# «Hola, Julio»; «Favale Motors» is a surname, so it gets a plain greeting.
GIVEN_NAMES = frozenset("""
adrian agustin alberto alejandro alejandra alfredo alicia ana andrea andres angel antonio ariel armando
beatriz bernardo carina carla carlos carolina cecilia cesar claudia claudio cristian cristina damian
daniel daniela dario david diego eduardo elena emanuel emiliano enrique ernesto esteban eugenia ezequiel
fabian fabio facundo federico fernanda fernando florencia franco gabriel gabriela gaston gerardo german
gisela gonzalo graciela guillermo gustavo hector hernan horacio hugo ignacio ivan javier jesus jonathan jorge
jose juan julian juliana julio laura leandro leonardo lorena lucas lucia luciano luis luisa marcela marcelo
marcos maria mariana mariano mario martin matias mauricio maximiliano melina miguel milagros mirta monica
nahuel natalia nestor nicolas norberto oscar osvaldo pablo patricia patricio paula pedro raul ramiro ramon
ricardo roberto rodolfo rodrigo romina ruben sandra santiago sebastian sergio silvana silvia sofia susana
tomas valeria vanesa veronica victor walter
""".split())
_CAPITALIZED = re.compile(r"[A-ZÁÉÍÓÚÑ][a-záéíóúñü]+")


def greeting(prospect: Prospect, first_name: str | None) -> str:
    """The message's first line, fixed in code so it never sounds like a mail merge."""
    if prospect.kind == "persona":
        return f"Hola, {first_name}." if first_name else "Hola, ¿cómo estás?"
    words = prospect.display_name.split()
    if len(words) >= 2 and fold(words[0]) in GIVEN_NAMES and _CAPITALIZED.fullmatch(words[0]) \
            and _CAPITALIZED.fullmatch(words[1]):
        return f"Hola, {words[0]}."
    return "Hola, ¿cómo andan?"


def has_hook(facts: Mapping[str, Any]) -> bool:
    return bool(facts.get("ganchos"))


def zone_for(prospect: Prospect, zone_map: Mapping[str, Any] | None) -> Zone:
    return zone_of(prospect.listings, zone_map)

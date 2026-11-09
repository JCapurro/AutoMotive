"""
Shadow report of the score recalibration f3 «precio × encaje» (read-only).

Reads public.match_decisions (migration 20261212120000_score_f3_shadow) and prints,
in Spanish markdown, the go-live criteria of the spec
(docs/superpowers/specs/2026-11-08-recalibracion-score-design.md §11.4), measured
per search over the fresh decisions of the period with what was known when deciding:
price, title, seller and price reference of that moment, not today's listing. f2
decides every alert; f3 is what it would have done.

Usage (from worker/):
    python -m tools.shadow_report [--since AAAA-MM-DD] [--until AAAA-MM-DD]
                                  [--search ID ...] [--params HASH] [--out ARCHIVO.md]

Dates are Argentina days (--until included). --params keeps the decisions made with one
score_model_f3 (its hash): if a parameter moved, the measurement starts again that day.
It only reads: one READ ONLY transaction on DATABASE_URL, safe against production.
"""
from __future__ import annotations

import argparse
import math
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

# Force UTF-8 stdout on Windows consoles (cp1252 default chokes on emoji/arrows)
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import db
from aio import run
from db.repos import match_decisions as repo

# America/Argentina/Buenos_Aires (no DST since 2009).
_AR = timezone(timedelta(hours=-3))

# The spec's fixed definitions (§11.4), independent of score_model_f3: the criteria
# must not move when a parameter does.
ALERT = ("queued", "digest")              # «alerta»: before the daily cap, like the backtest
OPPORTUNITY = "opportunity"               # «🔥»
KAVAK_OFFSET = 9
CRED_MIN, CRED_MAX = 5, 35                # «creíble»: % below the median, with Kavak's −9
N_MIN_HIGH = 10
SUSPICIOUS_PCT = 50
FAIR_MIN_D = -2                           # «más de 2 % sobre la mediana»
RATIO_MIN, RATIO_MAX = 0.85, 1.10
FIRE_RATIO_MIN = 0.6
CARD_DETAIL_MAX = 0.05
CONCENTRATION_MIN_CARS = 20
CONCENTRATION_MAX_SHARE = 0.40
# The card row is written right after the notifications it decided (same batch).
NOTIFICATION_SLACK = timedelta(minutes=10)
_PLACEHOLDER = re.compile(r"^([1-8])\1{3,}$")

MISSING_TABLE = "Todavía no hay registro de decisiones (falta la migración 20261212120000)."


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------

@dataclass
class Data:
    """What load() reads: decision rows (model f2) of the period's candidates, and around them."""
    rows: list[dict[str, Any]]
    notifications: list[dict[str, Any]] = field(default_factory=list)   # new_match / opportunity
    outbound: list[dict[str, Any]] = field(default_factory=list)        # listing_outbound_clicked
    listings: dict[int, dict[str, Any]] = field(default_factory=dict)   # today: status, enriched_at
    searches: dict[int, dict[str, Any]] = field(default_factory=dict)   # id, name, notify_min_level
    concentration: list[dict[str, Any]] = field(default_factory=list)   # search_id, cars, fire
    since: datetime | None = None
    until: datetime | None = None
    params: str | None = None


async def read_only(cx) -> None:
    """First statements of the report's transaction: nothing it runs can write."""
    await cx.execute("SET TRANSACTION READ ONLY")
    await cx.execute("SET LOCAL statement_timeout = '120s'")


_COLUMNS = ", ".join("d.user_id::text AS user_id" if c == "user_id" else f"d.{c}" for c in ("id", *repo.COLUMNS))


async def load(cx, since: datetime | None, until: datetime, searches: list[int] | None = None,
               params: str | None = None) -> Data:
    rows = await (await cx.execute(
        f"SELECT {_COLUMNS} FROM match_decisions d "
        " WHERE d.model = 'f2' AND d.match_id IN ("
        "   SELECT c.match_id FROM match_decisions c "
        "    WHERE c.model = 'f2' AND c.phase = 'card' "
        "      AND (%(since)s::timestamptz IS NULL OR c.decided_at >= %(since)s::timestamptz) "
        "      AND c.decided_at < %(until)s::timestamptz "
        "      AND (%(searches)s::bigint[] IS NULL OR c.search_profile_id = ANY(%(searches)s::bigint[])) "
        "      AND (%(params)s::text IS NULL OR c.f3_params = %(params)s::text)) "
        " ORDER BY d.decided_at, d.id",
        {"since": since, "until": until, "searches": searches or None, "params": params})).fetchall()
    data = Data(rows=rows, since=since, until=until, params=params)
    cards = [r for r in rows if r["phase"] == "card"]
    if cards:
        match_ids = sorted({r["match_id"] for r in cards})
        listing_ids = sorted({r["listing_id"] for r in cards})
        profile_ids = sorted({r["search_profile_id"] for r in cards})
        first = min(r["decided_at"] for r in cards) - NOTIFICATION_SLACK
        data.notifications = await (await cx.execute(
            "SELECT n.id, n.match_id, n.listing_id, n.search_profile_id, n.user_id::text AS user_id, "
            "       n.kind::text AS kind, n.status::text AS status, n.created_at, n.clicked_at "
            "  FROM notifications n "
            " WHERE n.kind IN ('new_match', 'opportunity') AND n.created_at >= %s "
            "   AND (n.match_id = ANY(%s::bigint[]) "
            "        OR (n.search_profile_id = ANY(%s::bigint[]) AND n.listing_id = ANY(%s::bigint[])))",
            (first, match_ids, profile_ids, listing_ids))).fetchall()
        data.outbound = await (await cx.execute(
            "SELECT e.user_id::text AS user_id, e.props->>'listing_id' AS listing_id, e.created_at "
            "  FROM events e "
            " WHERE e.name = 'listing_outbound_clicked' AND e.created_at >= %s "
            "   AND e.props->>'listing_id' = ANY(%s::text[])",
            (first, [str(i) for i in listing_ids]))).fetchall()
        data.listings = {r["id"]: r for r in await (await cx.execute(
            "SELECT id, status::text AS status, enriched_at FROM listings WHERE id = ANY(%s::bigint[])",
            (listing_ids,))).fetchall()}
    else:
        profile_ids = []
    # Criterion 6 reads today's lists: the current f3 view of each live match, one car per repost family.
    data.concentration = await (await cx.execute(
        "SELECT m.search_profile_id AS search_id, "
        "       count(DISTINCT coalesce(l.probable_repost_of, l.id)) AS cars, "
        "       count(DISTINCT coalesce(l.probable_repost_of, l.id)) "
        "         FILTER (WHERE m.score_breakdown->'shadow_f3'->>'level' = 'high') AS fire "
        "  FROM matches m JOIN listings l ON l.id = m.listing_id "
        "  JOIN search_profiles sp ON sp.id = m.search_profile_id "
        " WHERE l.status = 'active' AND m.score_breakdown ? 'shadow_f3' "
        "   AND sp.enabled AND public.search_access_active(sp.id) "
        "   AND (%(searches)s::bigint[] IS NULL OR sp.id = ANY(%(searches)s::bigint[])) "
        " GROUP BY 1 ORDER BY 1",
        {"searches": searches or None})).fetchall()
    ids = sorted(set(profile_ids) | {r["search_id"] for r in data.concentration})
    if ids:
        data.searches = {r["id"]: r for r in await (await cx.execute(
            "SELECT id, name, notify_min_level::text AS notify_min_level, enabled "
            "  FROM search_profiles WHERE id = ANY(%s::bigint[])", (ids,))).fetchall()}
    return data


async def read(*, since: datetime | None, until: datetime, searches: list[int] | None = None,
               params: str | None = None) -> Data | None:
    """Data of the period, or None when the table does not exist yet."""
    async with db.connection() as cx:
        await read_only(cx)
        if not await repo.available(cx):
            return None
        return await load(cx, since, until, searches, params)


# ---------------------------------------------------------------------------
# Decisions (pure)
# ---------------------------------------------------------------------------

def _num(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def is_placeholder(price: Any) -> bool:
    """4 or more equal digits from 1 to 8 (USD 11.111, ARS 1.111.111): spec §3.5. 9.999 is not."""
    p = _num(price)
    if p is None or p <= 0:
        return False
    return bool(_PLACEHOLDER.match(str(int(round(p)))))


def _ref(row: Mapping[str, Any]) -> Mapping[str, Any]:
    return row.get("price_ref") or {}


def diff_pct(row: Mapping[str, Any]) -> float | None:
    """d at that decision: % below the median of the reference used (positive = cheaper)."""
    return _num(_ref(row).get("diff_pct"))


def d_eff(row: Mapping[str, Any]) -> float | None:
    d = diff_pct(row)
    if d is None:
        return None
    return d - KAVAK_OFFSET if row.get("source") == "kavak" else d


def comparables(row: Mapping[str, Any]) -> int:
    n = _num(_ref(row).get("n"))
    return int(n) if n is not None else 0


def has_price(row: Mapping[str, Any]) -> bool:
    p = _num(row.get("price"))
    return p is not None and p > 0 and not row.get("price_partial")


def credible_at_decision(row: Mapping[str, Any]) -> bool:
    """§11.4 criterion 1: the card's price 5–35 % below with Kavak's −9, 10 or more
    comparables, a known year, a price that is not a placeholder and a live listing."""
    de = d_eff(row)
    return (has_price(row) and not is_placeholder(row.get("price")) and de is not None
            and CRED_MIN <= de <= CRED_MAX and comparables(row) >= N_MIN_HIGH
            and row.get("year") is not None and row.get("listing_status") == "active")


def other_version(row: Mapping[str, Any]) -> bool:
    """The search prefers a trim and f3 saw another one (not an unknown one)."""
    f3 = row.get("f3") or {}
    trim = _num(((f3.get("fit") or {}).get("prefs") or {}).get("trim"))
    unknown = set(row.get("f3_a_verificar") or f3.get("a_verificar") or [])
    return trim is not None and trim < 1 and "trim" not in unknown


def _alert(decision: Any) -> bool:
    return decision in ALERT


def _key(row: Mapping[str, Any]) -> tuple:
    return (row["decided_at"], row.get("id") or 0)


@dataclass
class Candidate:
    """One fresh alert candidate: its card row, the later phases, and f3's deciding row."""
    card: dict[str, Any]
    later: list[dict[str, Any]]
    deciding: dict[str, Any] | None           # None: f3 still waits for the detail («pendiente»)
    notifications: list[dict[str, Any]]
    outbound: bool
    listing_now: dict[str, Any] | None

    @property
    def match_id(self) -> int:
        return self.card["match_id"]

    @property
    def search_id(self) -> int:
        return self.card["search_profile_id"]

    @property
    def listing_id(self) -> int:
        return self.card["listing_id"]

    @property
    def pending(self) -> bool:
        return self.deciding is None

    @property
    def deferred(self) -> dict[str, Any] | None:
        return next((r for r in self.later if r["phase"] == "deferred"), None)

    @property
    def f2_alert(self) -> bool:
        return _alert(self.card.get("f2_decision"))

    @property
    def f2_fire(self) -> bool:
        return self.f2_alert and self.card.get("f2_kind") == OPPORTUNITY

    @property
    def f2_sent(self) -> bool:
        """f2 sent it: its notification exists (skipped = refused at delivery: never reached the user)."""
        return any(n.get("status") != "skipped" for n in self.notifications)

    @property
    def f3_alert(self) -> bool:
        return self.deciding is not None and _alert(self.deciding.get("f3_decision"))

    @property
    def f3_fire(self) -> bool:
        return self.f3_alert and self.deciding.get("f3_kind") == OPPORTUNITY

    @property
    def credible(self) -> bool:
        return credible_at_decision(self.card)

    @property
    def lost(self) -> bool:
        """f2 sent it and f3, having decided, would not have."""
        return self.f2_sent and not self.pending and not self.f3_alert

    @property
    def gained(self) -> bool:
        return self.f3_alert and not self.f2_alert

    @property
    def clicked(self) -> bool:
        return any(n.get("clicked_at") is not None for n in self.notifications)

    @property
    def f3_level(self) -> str | None:
        return (self.deciding or {}).get("f3_level")

    def card_detail_changed(self) -> bool:
        """The detail changed f3's alert decision (no deferred row: the detail changed nothing)."""
        d = self.deferred
        return d is not None and _alert(d.get("f3_decision")) != _alert(self.card.get("f3_decision"))

    def card_detail_level_changed(self) -> bool:
        d = self.deferred
        return d is not None and d.get("f3_level") != self.card.get("f3_level")


def deciding_row(card: Mapping[str, Any], later: Iterable[Mapping[str, Any]]) -> dict[str, Any] | None:
    """f3's decision in live semantics: the card row when it decides (no wait for the
    detail); else the earliest deferred or sweeper row that does; else still pending."""
    if card.get("f3_decides"):
        return dict(card)
    for row in sorted(later, key=_key):
        if row.get("f3_decides"):
            return dict(row)
    return None


def decisions(data: Data) -> list[Candidate]:
    """One Candidate per card row of the period (later rows without a card are ignored)."""
    by_match: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in data.rows:
        by_match[row["match_id"]].append(row)
    by_match_id: dict[int, list[dict]] = defaultdict(list)
    by_pair: dict[tuple[int, int], list[dict]] = defaultdict(list)
    for n in data.notifications:
        if n.get("match_id") is not None:
            by_match_id[n["match_id"]].append(n)
        if n.get("search_profile_id") is not None and n.get("listing_id") is not None:
            by_pair[(n["search_profile_id"], n["listing_id"])].append(n)
    outbound: dict[tuple[str, str], list[datetime]] = defaultdict(list)
    for e in data.outbound:
        outbound[(str(e.get("user_id")), str(e.get("listing_id")))].append(e["created_at"])

    out: list[Candidate] = []
    for rows in by_match.values():
        cards = sorted((r for r in rows if r["phase"] == "card"), key=_key)
        if not cards:
            continue
        card = cards[0]
        later = sorted((r for r in rows if r["phase"] != "card"), key=_key)
        start = card["decided_at"] - NOTIFICATION_SLACK
        seen: dict[int, dict] = {}
        for n in by_match_id.get(card["match_id"], []) + by_pair.get((card["search_profile_id"], card["listing_id"]), []):
            if n["created_at"] >= start and n["created_at"] <= card["decided_at"] + NOTIFICATION_SLACK:
                seen[n["id"]] = n
        clicks = outbound.get((str(card.get("user_id")), str(card["listing_id"])), [])
        out.append(Candidate(card=card, later=later, deciding=deciding_row(card, later),
                             notifications=list(seen.values()),
                             outbound=any(at >= start for at in clicks),
                             listing_now=data.listings.get(card["listing_id"])))
    out.sort(key=lambda c: (c.search_id, _key(c.card)))
    return out


# ---------------------------------------------------------------------------
# Criteria (pure)
# ---------------------------------------------------------------------------

@dataclass
class Criterion:
    number: int
    title: str
    measured: str
    passed: bool | None            # None: no data, or informative
    blocking: bool = True
    details: list[str] = field(default_factory=list)


def silence_reasons(c: Candidate) -> list[str]:
    """Why a lost alert of a silent search is accepted (§11.4 criterion 2), read from the
    row f3 decided with; empty: not accepted."""
    row = c.deciding or c.card
    reasons: list[str] = []
    if not has_price(row):
        reasons.append("sin precio")
    elif is_placeholder(row.get("price")) or row.get("placeholder"):
        reasons.append("precio de relleno")
    if row.get("year") is None:
        reasons.append("sin año")
    d, de = diff_pct(row), d_eff(row)
    if d is not None and d >= SUSPICIOUS_PCT:
        reasons.append(f"{_pct(d)} debajo (≥ {SUSPICIOUS_PCT} %)")
    if de is not None and de < FAIR_MIN_D:
        reasons.append(f"{_pct(-de)} sobre la mediana")
    if other_version(row):
        reasons.append("otra versión")
    if comparables(row) < N_MIN_HIGH:
        reasons.append(f"menos de {N_MIN_HIGH} comparables (n={comparables(row)})")
    if (c.listing_now or {}).get("status") == "gone":
        reasons.append("aviso ya vendido o terminado")
    return reasons


def _ratio(num: int, den: int) -> float | None:
    return num / den if den else None


def _by_search(cands: Iterable[Candidate]) -> dict[int, list[Candidate]]:
    out: dict[int, list[Candidate]] = defaultdict(list)
    for c in cands:
        out[c.search_id].append(c)
    return out


def criteria(data: Data, cands: list[Candidate] | None = None) -> list[Criterion]:
    cands = decisions(data) if cands is None else cands
    decided = [c for c in cands if not c.pending]
    out: list[Criterion] = []

    # 1. No credible alert that f2 sent is lost.
    sent_credible = [c for c in cands if c.f2_sent and c.credible]
    lost_credible = [c for c in sent_credible if c.lost]
    out.append(Criterion(
        1, "Ninguna búsqueda pierde una alerta que f2 envió y que era creíble al decidir",
        f"{_count(len(lost_credible), 'perdida', 'perdidas')} de {_count(len(sent_credible), 'creíble enviada', 'creíbles enviadas')}",
        not lost_credible,
        details=[_line(c) for c in lost_credible]))

    # 2. Silent searches only when every lost alert is explained.
    details2: list[str] = []
    n_silent = accepted = 0
    for sid, group in sorted(_by_search(cands).items()):
        if not any(c.f2_sent for c in group) or any(c.f3_alert for c in group):
            continue
        lost = [c for c in group if c.lost]
        if not lost:          # what f2 sent, f3 has not decided yet
            continue
        ok = all(silence_reasons(c) for c in lost)
        n_silent += 1
        accepted += ok
        details2.append(f"Búsqueda {_search(data, sid)}: {_count(len(lost), 'perdida', 'perdidas')} · "
                        + ("aceptada" if ok else "**no aceptada**"))
        for c in lost:
            reasons = silence_reasons(c)
            details2.append(f"  - {_line(c)} · motivo: " + (", ".join(reasons) if reasons else "**ninguno aceptado**"))
    out.append(Criterion(
        2, "Una búsqueda que f3 deja en silencio solo se acepta si cada alerta perdida tiene un motivo de la lista",
        f"{_int(n_silent)} en silencio, {_count(accepted, 'aceptada', 'aceptadas')}", accepted == n_silent, details=details2))

    # 3. Volume.
    f2a, f3a = sum(c.f2_alert for c in decided), sum(c.f3_alert for c in decided)
    f2f, f3f = sum(c.f2_fire for c in decided), sum(c.f3_fire for c in decided)
    f2f_cred = sum(c.f2_fire and c.credible for c in decided)
    ratio, fire = _ratio(f3a, f2a), _ratio(f3f, f2f)
    passed3: bool | None
    if ratio is None:
        passed3 = None
    else:
        passed3 = RATIO_MIN <= ratio <= RATIO_MAX and (f2f == 0 or f3f >= FIRE_RATIO_MIN * f2f)
    out.append(Criterion(
        3, f"Alertas f3/f2 entre {_dec(RATIO_MIN)} y {_dec(RATIO_MAX)}; 🔥 f3 ≥ {_dec(FIRE_RATIO_MIN, 1)} × 🔥 f2",
        f"alertas {_int(f3a)}/{_int(f2a)} = {_dec(ratio)} · 🔥 {_int(f3f)}/{_int(f2f)} = {_dec(fire)}",
        passed3,
        details=[f"🔥 de f3 contra las 🔥 creíbles de f2 (informativo): {_int(f3f)}/{_int(f2f_cred)} = "
                 f"{_dec(_ratio(f3f, f2f_cred))}",
                 f"Sin contar {_count(len(cands) - len(decided), 'candidato', 'candidatos')} que f3 todavía no decidió."]))

    # 4. No bad f3 alert at «buena» or above.
    bad = []
    for c in decided:
        row = c.deciding
        if not c.f3_alert or row.get("f3_level") not in ("high", "good"):
            continue
        why = []
        if row.get("year") is None:
            why.append("sin año")
        if not has_price(row) or is_placeholder(row.get("price")) or row.get("placeholder"):
            why.append("sin precio o de relleno")
        d_card, d_row = diff_pct(c.card), diff_pct(row)
        if (d_card is not None and d_card >= SUSPICIOUS_PCT) or (d_row is not None and d_row >= SUSPICIOUS_PCT):
            why.append(f"≥ {SUSPICIOUS_PCT} % debajo")
        if why:
            bad.append(f"{_line(c)} · " + ", ".join(why))
    out.append(Criterion(
        4, "0 alertas de f3 a «buena» o más sin año, sin precio (o de relleno) o con el precio de la tarjeta ≥ 50 % debajo",
        _int(len(bad)), not bad, details=bad))

    # 5. Card ≠ detail: over every fresh decision of the period, as the spec fixed it (§11.4.5, like the
    # backtest's 2.7 % and 1.2 %); the share among the cards whose detail was read since is informative.
    changed = [c for c in cands if c.card_detail_changed()]
    levels = [c for c in cands if c.card_detail_level_changed()]
    share = _ratio(len(changed), len(cands))
    read = [c for c in cands if not c.card.get("enriched") and (c.listing_now or {}).get("enriched_at") is not None]
    read_changed = sum(c.card_detail_changed() for c in read)
    read_share = _ratio(read_changed, len(read))
    out.append(Criterion(
        5, f"Tarjeta ≠ detalle en f3 en no más del {_pct(CARD_DETAIL_MAX * 100, 0)} de las decisiones frescas",
        f"{_pct(share * 100) if share is not None else '—'} ({_int(len(changed))} de {_int(len(cands))})",
        share is None or share <= CARD_DETAIL_MAX,
        details=["Denominador: todas las decisiones frescas del período, como en el spec y el backtest. "
                 "Sin fila «deferred» el detalle no cambió nada.",
                 f"Nivel de f3 distinto entre tarjeta y detalle: {_int(len(levels))}.",
                 f"Solo entre las tarjetas sin leer cuyo aviso hoy está leído (informativo): {_int(read_changed)} de "
                 f"{_int(len(read))} = {_pct(read_share * 100) if read_share is not None else '—'}."]
        + [f"{_line(c)} · tarjeta {c.card.get('f3_level')}/{c.card.get('f3_decision')} → detalle "
           f"{c.deferred.get('f3_level')}/{c.deferred.get('f3_decision')}" for c in changed]))

    # 6. Concentration (decision 6c: a list to review the pool, not blocking).
    hot = [r for r in data.concentration
           if (r.get("cars") or 0) >= CONCENTRATION_MIN_CARS and (r.get("fire") or 0) / r["cars"] > CONCENTRATION_MAX_SHARE]
    out.append(Criterion(
        6, f"Concentración: búsquedas con {CONCENTRATION_MIN_CARS} o más autos vivos y más de "
           f"{_pct(CONCENTRATION_MAX_SHARE * 100, 0)} de 🔥 (f3 de hoy, autos distintos)",
        f"{_count(len(hot), 'búsqueda', 'búsquedas')} para revisar el pool", None, blocking=False,
        details=[f"Búsqueda {_search(data, r['search_id'])}: {_int(r['fire'])} 🔥 de {_int(r['cars'])} autos "
                 f"({_pct(100 * r['fire'] / r['cars'])})" for r in hot]))

    # 7. Clicks and outbound of what f2 sent, by f3 level (informative).
    rows7 = []
    groups: dict[str, list[Candidate]] = defaultdict(list)
    for c in cands:
        if c.f2_sent:
            groups["pendiente" if c.pending else (c.f3_level or "sin f3")].append(c)
    for level in ("high", "good", "match", "low", "excluded", "sin f3", "pendiente"):
        g = groups.get(level)
        if g:
            rows7.append(f"| {_LEVEL.get(level, level)} | {_int(len(g))} | {_int(sum(c.clicked for c in g))} | "
                         f"{_int(sum(c.outbound for c in g))} |")
    details7 = (["| nivel f3 | alertas que f2 mandó | con clic | con salida al aviso |", "|---|---|---|---|"] + rows7
                if rows7 else [])
    out.append(Criterion(7, "Clics y salidas de las alertas que mandó f2, por nivel de f3",
                         f"{_count(sum(len(g) for g in groups.values()), 'alerta', 'alertas')}", None, blocking=False,
                         details=details7 + (["Con ~100 alertas no alcanza para decidir: solo se informa."]
                                             if rows7 else [])))
    return out


# ---------------------------------------------------------------------------
# Per search (pure)
# ---------------------------------------------------------------------------

@dataclass
class SearchRow:
    search_id: int
    name: str | None
    candidates: int = 0
    f2_alerts: int = 0
    f3_alerts: int = 0
    f2_fire: int = 0
    f3_fire: int = 0
    lost_credible: int = 0
    gained: int = 0
    pending: int = 0
    card_detail: int = 0


def per_search(data: Data, cands: list[Candidate] | None = None) -> list[SearchRow]:
    cands = decisions(data) if cands is None else cands
    rows: dict[int, SearchRow] = {}
    for c in cands:
        r = rows.setdefault(c.search_id, SearchRow(c.search_id, (data.searches.get(c.search_id) or {}).get("name")))
        r.candidates += 1
        r.pending += c.pending
        if not c.pending:
            r.f2_alerts += c.f2_alert
            r.f3_alerts += c.f3_alert
            r.f2_fire += c.f2_fire
            r.f3_fire += c.f3_fire
            r.gained += c.gained
        r.lost_credible += c.lost and c.credible
        r.card_detail += c.card_detail_changed()
    return [rows[k] for k in sorted(rows)]


def params_changes(data: Data) -> list[tuple[datetime, str | None, str]]:
    """(when, from, to) each time the f3 parameters hash changed between card rows."""
    out = []
    last: str | None = None
    for row in sorted((r for r in data.rows if r["phase"] == "card"), key=_key):
        p = row.get("f3_params")
        if p is None:
            continue
        if last is not None and p != last:
            out.append((row["decided_at"], last, p))
        last = p
    return out


# Decisions Juan has not taken (§14): the shadow runs the recommended option; each of these
# is the other option, recomputed from what the row logged.
ALTERNATIVES = (
    ("seller_cap_off", "Sin tope de vendedor (decisión 2)"),
    ("seller_cap_good", "Tope de vendedor en «buena» (decisión 2b)"),
    ("seller_cap_pro_only", "Tope de vendedor solo con el filtro Pro (decisión 2c)"),
    ("agency_voice_off", "Sin voz de agencia (decisión 2)"),
    ("placeholder_off", "Sin la regla del precio de relleno (decisión 3)"),
    ("kavak_offset_0", "Kavak sin el −9 (decisión 4c)"),
    # The same switches the other way, when someone turned a rule off during the shadow.
    ("seller_cap_on", "Con tope de vendedor (decisión 2a)"),
    ("agency_voice_on", "Con voz de agencia (decisión 2a)"),
    ("placeholder_on", "Con la regla del precio de relleno (decisión 3a)"),
)
_RANK = {"high": 3, "good": 2, "match": 1, "low": 0}
# f3 reasons of decisions that only the level drove (a Pro threshold reached or a level-independent
# drop like dedupe_existing would stay as they are with another level).
_LEVEL_REASONS = (None, "below_min_level", "frequency", "threshold_not_reached")


@dataclass
class Alternative:
    key: str
    label: str
    applies: int = 0          # decided candidates the option would change something for
    level_changes: int = 0
    alerts: int = 0           # f3 alerts with the option (the rest as decided)
    fire: int = 0


def alternative_level(row: Mapping[str, Any], key: str) -> str | None:
    """f3's level under the other option of a §14 decision, or None when it does not apply."""
    f3 = row.get("f3") or {}
    if key in ("seller_cap_good", "seller_cap_pro_only"):
        if not row.get("f3_seller_capped"):
            return None
        uncapped = row.get("f3_level_uncapped")
        if key == "seller_cap_good":
            return "good" if uncapped in ("high", "good") else uncapped
        return row.get("f3_level") if (f3.get("seller") or {}).get("strict") else uncapped
    alt = (f3.get("alternatives") or {}).get(key)
    return alt.get("level") if isinstance(alt, Mapping) else None


def _alerts_at(row: Mapping[str, Any], level: str | None) -> tuple[bool, bool]:
    """(alert, 🔥) the same classify would give with `level`, for a row whose f3 decision only
    depended on the level. Approximation: the search's min_level; no Pro threshold."""
    if level not in _RANK:
        return False, False
    audience = row.get("audience") or {}
    minimum = _RANK.get(audience.get("min_level") or "good", 2)
    alert = _RANK[level] >= minimum
    return alert, alert and level == "high" and not audience.get("repost")


def alternatives(cands: list[Candidate]) -> list[Alternative]:
    out = []
    for key, label in ALTERNATIVES:
        alt = Alternative(key, label)
        for c in cands:
            if c.pending:
                continue
            row = c.deciding
            level = alternative_level(row, key)
            alert, fire = c.f3_alert, c.f3_fire
            if level is not None:
                alt.applies += 1
                alt.level_changes += level != row.get("f3_level")
                if row.get("f3_reason") in _LEVEL_REASONS and row.get("f3_level") is not None:
                    alert, fire = _alerts_at(row, level)
            alt.alerts += alert
            alt.fire += fire
        out.append(alt)
    return out


# ---------------------------------------------------------------------------
# Rendering (Spanish)
# ---------------------------------------------------------------------------

_LEVEL = {"high": "🔥 oportunidad", "good": "🟢 buena", "match": "🟡 coincidencia", "low": "⚪ baja",
          "excluded": "excluido", "sin f3": "sin f3", "pendiente": "pendiente"}


def _int(n: int | float | None) -> str:
    if n is None:
        return "—"
    return f"{int(n):,}".replace(",", ".")


def _count(n: int, one: str, many: str) -> str:
    return f"{_int(n)} {one if n == 1 else many}"


def _dec(x: float | None, digits: int = 2) -> str:
    if x is None:
        return "—"
    return f"{x:.{digits}f}".replace(".", ",")


def _pct(x: float | None, digits: int = 1) -> str:
    return "—" if x is None else f"{_dec(x, digits)} %"


def _money(price: Any, currency: Any) -> str:
    p = _num(price)
    if p is None:
        return "sin precio"
    return f"{currency or ''} {_int(round(p))}".strip()


def _when(at: datetime | None) -> str:
    return "—" if at is None else at.astimezone(_AR).strftime("%Y-%m-%d %H:%M")


def _cell(text: Any) -> str:
    return str(text or "").replace("|", "\\|")


def _search(data: Data, sid: int) -> str:
    name = (data.searches.get(sid) or {}).get("name")
    return f"{sid} «{name}»" if name else str(sid)


def _decision(level: Any, score: Any, decision: Any, kind: Any, reason: Any) -> str:
    what = decision or "—"
    if decision in ALERT and kind:
        what = f"{kind} ({decision})"
    elif reason:
        what = f"{what} ({reason})"
    return f"{level or '—'} {score if score is not None else '—'} → {what}"


def _line(c: Candidate) -> str:
    card, row = c.card, c.deciding or c.card
    d, n = diff_pct(card), comparables(card)
    ref = f"{_pct(d)} debajo de {n} comparables" if d is not None else "sin comparables"
    if card.get("source") == "kavak" and d is not None:
        ref += f" (Kavak: {_pct(d - KAVAK_OFFSET)})"
    f3 = "pendiente" if c.pending else _decision(row.get("f3_level"), row.get("f3_score"), row.get("f3_decision"),
                                                 row.get("f3_kind"), row.get("f3_reason"))
    phase = "" if c.pending or row["phase"] == "card" else f" [{row['phase']}]"
    return (f"aviso {c.listing_id} ({card.get('source') or '?'}, match {c.match_id}) «{card.get('title') or ''}» · "
            f"{_money(card.get('price'), card.get('currency'))} · {card.get('year') or 'sin año'} · {ref} · "
            f"f2: {_decision(card.get('f2_level'), card.get('f2_score'), card.get('f2_decision'), card.get('f2_kind'), card.get('f2_reason'))} · "
            f"f3{phase}: {f3}")


def _period(data: Data) -> str:
    since = _when(data.since)[:10] if data.since else "el comienzo del registro"
    until = _when(data.until - timedelta(seconds=1))[:10] if data.until else "hoy"
    return f"desde {since} hasta {until} (días de Argentina)"


def render(data: Data, *, now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    cands = decisions(data)
    lines = ["# Modo sombra f3 · «precio × encaje»", "",
             f"Período: {_period(data)}" + (f" · parámetros {data.params}" if data.params else "") + ".",
             f"Generado el {_when(now)} (hora de Argentina). f2 decide todas las alertas; f3 es lo que habría hecho, "
             "leído de `match_decisions` con el precio, el título, el vendedor y la referencia del momento de decidir.",
             ""]
    if not cands:
        lines.append("Todavía no hay decisiones frescas registradas en el período.")
        return "\n".join(lines) + "\n"

    pending = [c for c in cands if c.pending]
    hashes = sorted({r.get("f3_params") for r in data.rows if r["phase"] == "card" and r.get("f3_params")})
    lines.append(f"Candidatos frescos: {_int(len(cands))} en {_int(len({c.search_id for c in cands}))} búsquedas · "
                 f"pendientes de f3 (esperan el detalle): {_int(len(pending))} · "
                 f"parámetros de f3: {', '.join(hashes) if hashes else '—'}.")
    for at, old, new in params_changes(data):
        lines.append(f"\n⚠️ Se movió un parámetro el {_when(at)} ({old} → {new}): la medición vuelve a empezar desde ahí. "
                     f"Para medir solo desde ese día: `--params {new}`.")
    lines += ["", "## Criterios para pasar a real (spec §11.4)", "",
              "| # | criterio | medido | resultado |", "|---|---|---|---|"]
    crits = criteria(data, cands)
    for cr in crits:
        if not cr.blocking:
            mark = "ℹ️ no bloquea" if cr.number == 6 else "ℹ️ informativo"
        elif cr.passed is None:
            mark = "sin datos"
        else:
            mark = "✅" if cr.passed else "❌"
        lines.append(f"| {cr.number} | {cr.title} | {cr.measured} | {mark} |")
    for cr in crits:
        if cr.details:
            lines += ["", f"### {cr.number}. {cr.title}", ""]
            for i, d in enumerate(cr.details):
                if i and cr.details[i - 1].startswith("|") and not d.startswith("|"):
                    lines.append("")          # a list right after a table needs a blank line
                lines.append(d if d.startswith(("|", "  -")) else f"- {d}")

    lines += ["", "## Por búsqueda", "",
              "| búsqueda | nombre | candidatos | alertas f2 → f3 | 🔥 f2 → f3 | perdidas creíbles | ganadas | "
              "pendientes | tarjeta ≠ detalle |",
              "|---|---|---|---|---|---|---|---|---|"]
    for r in per_search(data, cands):
        lines.append(f"| {r.search_id} | {_cell(r.name)} | {_int(r.candidates)} | {_int(r.f2_alerts)} → {_int(r.f3_alerts)} | "
                     f"{_int(r.f2_fire)} → {_int(r.f3_fire)} | {_int(r.lost_credible)} | {_int(r.gained)} | "
                     f"{_int(r.pending)} | {_int(r.card_detail)} |")

    lines += ["", "## Detalle"]
    lines += _section("Degradadas por el tope diario (f2)",
                      [c for c in cands if c.card.get("f2_decision") == "digest" and c.card.get("f2_reason") == "daily_cap"],
                      "f2 las pasó al resumen por el tope diario; f3 no simula el tope.")
    seller = [c for c in cands if (c.deciding or c.card).get("f3_seller_capped") or (c.deciding or c.card).get("agency_voice")]
    lines += _section("Tope de vendedor y voz de agencia (f3)", seller, None,
                      extra=lambda c: _seller_note(c.deciding or c.card))
    lines += _section("Precio de relleno",
                      [c for c in cands if is_placeholder(c.card.get("price")) or (c.deciding or c.card).get("placeholder")],
                      "4 o más cifras iguales del 1 al 8: f3 lo trata como sin precio.")
    kavak = [c for c in cands if c.card.get("source") == "kavak"]
    if kavak:
        dec = [c for c in kavak if not c.pending]
        lines += ["", "### Kavak", "",
                  f"{_count(len(kavak), 'candidato', 'candidatos')} · alertas f2 {_int(sum(c.f2_alert for c in dec))} → f3 "
                  f"{_int(sum(c.f3_alert for c in dec))} · 🔥 f2 {_int(sum(c.f2_fire for c in dec))} → f3 "
                  f"{_int(sum(c.f3_fire for c in dec))}. f3 compara Kavak con {KAVAK_OFFSET} puntos menos "
                  "(sin ese ajuste, ver `f3.alternatives.kavak_offset_0` de cada fila)."]
    lines += _section("Dedupe entre búsquedas del mismo usuario (no simulado en f3)",
                      [c for c in cands if c.card.get("f2_reason") == "dedupe_batch" and c.f3_alert],
                      "f2 no la mandó porque otra búsqueda del mismo usuario ganó el lote; f3 la cuenta como alerta.")
    lines += _section("f3 no disponible",
                      [c for c in cands if not c.pending and c.deciding.get("f3_level") is None],
                      "f3 no se pudo calcular (o el match ya no existía): no cuentan como alerta de f3.")
    alts = [a for a in alternatives(cands) if a.applies]
    if alts:
        decided = [c for c in cands if not c.pending]
        lines += ["", "### Decisiones pendientes (§14): la otra opción", "",
                  "La sombra corre la opción recomendada. Con la otra, recalculada desde lo registrado "
                  "(alertas aproximadas con el nivel mínimo de cada búsqueda, sin umbral Pro):", "",
                  "| opción | avisos donde cambia algo | nivel distinto | alertas f3 → con la opción | 🔥 f3 → con la opción |",
                  "|---|---|---|---|---|"]
        f3a, f3f = sum(c.f3_alert for c in decided), sum(c.f3_fire for c in decided)
        for a in alts:
            lines.append(f"| {a.label} | {_int(a.applies)} | {_int(a.level_changes)} | {_int(f3a)} → {_int(a.alerts)} | "
                         f"{_int(f3f)} → {_int(a.fire)} |")
    lines += _section("Pendientes (f3 espera el detalle)", pending,
                      "Tarjetas de FB o ML sin vendedor, de búsquedas con preferencia de vendedor: el barrido las decide "
                      "a los 20 minutos.")
    wide = [c for c in cands if not c.card.get("would_defer") and _wide_defer(c.card)]
    lines += _section("Esperarían el detalle con la regla amplia (otras fuentes)", wide,
                      "Tarjetas sin vendedor de otras fuentes, de búsquedas con preferencia de vendedor: con la regla "
                      "del spec (§4.1, solo FB y ML) decide la tarjeta; se listan para evaluar la regla amplia.")
    return "\n".join(lines) + "\n"


def _wide_defer(row: Mapping[str, Any]) -> bool:
    """shadow_f3.would_defer_any_source of a logged row (absent on rows logged before it existed)."""
    f3 = row.get("f3")
    return isinstance(f3, Mapping) and bool(f3.get("would_defer_any_source"))


def _seller_note(row: Mapping[str, Any]) -> str:
    parts = []
    if row.get("f3_seller_capped"):
        parts.append(f"tope de vendedor: {row.get('f3_level_uncapped') or '—'} → {row.get('f3_level') or '—'}")
    if row.get("agency_voice"):
        parts.append(f"voz de agencia: «{row['agency_voice']}»")
    return " · ".join(parts)


def _section(title: str, items: list[Candidate], note: str | None, *, extra=None, limit: int = 50) -> list[str]:
    if not items:
        return []
    out = ["", f"### {title} ({_int(len(items))})", ""]
    if note:
        out += [note, ""]
    for c in items[:limit]:
        out.append(f"- búsqueda {c.search_id} · {_line(c)}" + (f" · {extra(c)}" if extra else ""))
    if len(items) > limit:
        out.append(f"- … y {_int(len(items) - limit)} más.")
    return out


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _day(text: str) -> date:
    try:
        return date.fromisoformat(text)
    except ValueError:
        raise argparse.ArgumentTypeError("usá AAAA-MM-DD")


def day_bounds(since: date | None, until: date | None, *, now: datetime) -> tuple[datetime | None, datetime]:
    """Argentina days → [since 00:00, the day after until 00:00) in absolute time; until defaults to now."""
    start = datetime.combine(since, datetime.min.time(), _AR) if since else None
    end = datetime.combine(until + timedelta(days=1), datetime.min.time(), _AR) if until else now
    return start, end


async def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m tools.shadow_report", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--since", type=_day, help="primer día (AAAA-MM-DD, hora de Argentina)")
    p.add_argument("--until", type=_day, help="último día, incluido (AAAA-MM-DD)")
    p.add_argument("--search", type=int, nargs="+", help="solo estas búsquedas")
    p.add_argument("--params", help="solo las decisiones con este hash de score_model_f3")
    p.add_argument("--out", type=Path, help="escribir el informe en este archivo (markdown)")
    args = p.parse_args(argv)
    now = datetime.now(timezone.utc)
    since, until = day_bounds(args.since, args.until, now=now)
    if since is not None and since >= until:
        p.error("--since tiene que ser anterior a --until")

    await db.open_pool(max_size=1)
    try:
        data = await read(since=since, until=until, searches=args.search, params=args.params)
    finally:
        await db.close_pool()
    text = MISSING_TABLE + "\n" if data is None else render(data, now=now)
    if args.out:
        args.out.write_text(text, encoding="utf-8")
        print(f"Informe escrito en {args.out}.")
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    sys.exit(run(main()))

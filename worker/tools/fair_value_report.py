"""
Shadow report of «valor justo» (read-only), docs/superpowers/specs/2026-11-20-valor-justo-design.md §7.

Prints, in Spanish markdown, the go-live criteria fixed before measuring (§7) and the budget table (§6.2):

  1-3  coverage and biases: matches as the re-score left them (score_breakdown.shadow_fair_value);
  4    stability: fair_value_runs.stats, consecutive days, models with 400 listings or more;
  5    volume: match_decisions, the row that decides each match (f3_decides), f2's alert again with
       notifications.engine.classify and the stored audience, today's reference against the hybrid rule;
  6    Juan's review: 20 alerts that would go and 20 that would appear, at random (seeded);
  plus the enabled models and their errors (model_price_curves) and guard_flips of the last run.

Usage (from worker/):
    python -m tools.fair_value_report [--since AAAA-MM-DD] [--until AAAA-MM-DD] [--params HASH]
                                      [--seed N] [--out ARCHIVO.md]

Dates are Argentina days (--until included). --params keeps one app_config.fair_value (its hash): if a
parameter moved, the measurement starts again that day. It only reads: one READ ONLY transaction on
DATABASE_URL, safe against production.
"""
from __future__ import annotations

import argparse
import math
import random
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import db
from aio import run
from notifications import decision_log
from notifications.engine import Rules, classify

_AR = timezone(timedelta(hours=-3))

# §7, fixed before measuring: they must not move when a parameter does.
MIN_DAYS = 14
COVERAGE_MIN = 0.80
BIAS_MAX = 0.10
STABILITY_MAX = 0.015
STABILITY_MIN_N = 400
VOLUME_MIN, VOLUME_MAX = 0.85, 1.10
REVIEW_N = 20
ALERT = ("queued", "digest")
TWINS = "trim_transmission"
MIN_N = 5
# §6.2: value of the car against the budget, and price against it.
VALUE_BUCKETS = ((0.6, "< 60 %"), (0.8, "60–80 %"), (0.95, "80–95 %"), (1.1, "95–110 %"), (math.inf, "> 110 %"))
PRICE_BUCKETS = ((0.5, "< 50 %"), (0.7, "50–70 %"), (0.85, "70–85 %"), (math.inf, "85–100 %"))
OPEN_EVENTS = ("listing_detail_viewed", "listing_outbound_clicked", "alert_clicked")


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------

@dataclass
class Data:
    since: datetime | None
    until: datetime
    params: str | None
    matches: list[dict[str, Any]] = field(default_factory=list)
    curves: list[dict[str, Any]] = field(default_factory=list)
    runs: list[dict[str, Any]] = field(default_factory=list)
    decisions: list[dict[str, Any]] = field(default_factory=list)
    opens: set[tuple[str, int]] = field(default_factory=set)
    available: bool = True


async def read_only(cx) -> None:
    await cx.execute("SET TRANSACTION READ ONLY")
    await cx.execute("SET LOCAL statement_timeout = '120s'")


async def load(cx, since: datetime | None, until: datetime, params: str | None) -> Data:
    data = Data(since=since, until=until, params=params)
    if (await (await cx.execute("SELECT to_regclass('public.model_price_curves') IS NOT NULL AS ok")).fetchone())["ok"] is False:
        data.available = False
        return data
    data.curves = [dict(r) for r in await (await cx.execute(
        "SELECT make, model, n, cv_err, cohort_err, enabled, params_hash, fitted_at, curve "
        "  FROM model_price_curves ORDER BY n DESC")).fetchall()]
    data.runs = [dict(r) for r in await (await cx.execute(
        "SELECT id, started_at, status, trigger, params_hash, models_enabled, stats FROM fair_value_runs "
        " WHERE status = 'ok' AND (%(since)s::timestamptz IS NULL OR started_at >= %(since)s::timestamptz - interval '1 day') "
        "   AND started_at < %(until)s::timestamptz ORDER BY started_at",
        {"since": since, "until": until})).fetchall()]
    # Today's state of every re-scored match of the period (criteria 1-3 and §6.2).
    data.matches = [dict(r) for r in await (await cx.execute(
        "SELECT m.id, m.search_profile_id, sp.user_id::text AS user_id, m.listing_id, m.score, m.price_ref, "
        "       m.score_breakdown->'shadow_fair_value' AS fv, lower(l.make) AS make, lower(l.model) AS model, "
        "       l.trim, l.year, l.mileage_km, l.price_usd, l.title "
        "  FROM matches m JOIN listings l ON l.id = m.listing_id "
        "  JOIN search_profiles sp ON sp.id = m.search_profile_id "
        " WHERE (%(since)s::timestamptz IS NULL OR m.updated_at >= %(since)s::timestamptz) "
        "   AND m.updated_at < %(until)s::timestamptz",
        {"since": since, "until": until})).fetchall()]
    if params:
        data.matches = [m for m in data.matches
                        if not isinstance(m.get("fv"), Mapping) or m["fv"].get("params") == params]
    if (await (await cx.execute("SELECT to_regclass('public.match_decisions') IS NOT NULL AS ok")).fetchone())["ok"]:
        data.decisions = [dict(r) for r in await (await cx.execute(
            "SELECT d.id, d.match_id, d.search_profile_id, d.listing_id, d.user_id::text AS user_id, d.phase, "
            "       d.decided_at, d.f3_decides, d.f2_score, d.f2_level, d.f2_breakdown, d.price_ref, d.audience, "
            "       d.title, d.price, d.currency, d.price_usd, d.year "
            "  FROM match_decisions d WHERE d.model = 'f2' "
            "   AND (%(since)s::timestamptz IS NULL OR d.decided_at >= %(since)s::timestamptz) "
            "   AND d.decided_at < %(until)s::timestamptz ORDER BY d.decided_at, d.id",
            {"since": since, "until": until})).fetchall()]
    users = sorted({m["user_id"] for m in data.matches if m.get("user_id")})
    if users:
        data.opens = {(r["user_id"], int(r["listing_id"])) for r in await (await cx.execute(
            "SELECT DISTINCT e.user_id::text AS user_id, (e.props->>'listing_id')::bigint AS listing_id "
            "  FROM events e WHERE e.name = ANY(%s) AND e.props->>'listing_id' ~ '^[0-9]+$' "
            "   AND e.user_id::text = ANY(%s)", (list(OPEN_EVENTS), users))).fetchall()}
    return data


async def read(*, since: datetime | None, until: datetime, params: str | None) -> Data:
    async with db.connection() as cx:
        await read_only(cx)
        return await load(cx, since, until, params)


# ---------------------------------------------------------------------------
# Pure pieces
# ---------------------------------------------------------------------------

def _num(x: Any) -> float | None:
    if isinstance(x, bool) or x is None:
        return None
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def corr(xs: list[float], ys: list[float]) -> float | None:
    """Pearson's correlation; None under 3 pairs or without variance."""
    n = len(xs)
    if n < 3:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    vx = sum((x - mx) ** 2 for x in xs)
    vy = sum((y - my) ** 2 for y in ys)
    if vx <= 0 or vy <= 0:
        return None
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / math.sqrt(vx * vy)


def has_twins(price_ref: Any) -> bool:
    if not isinstance(price_ref, Mapping):
        return False
    return price_ref.get("level_used") == TWINS and (_num(price_ref.get("n")) or 0) >= MIN_N


def curve_index(curves: Iterable[Mapping[str, Any]]) -> dict[tuple[str, str], Mapping[str, Any]]:
    return {(c["make"], c["model"]): (c.get("curve") or {}) for c in curves}


def coverage(matches: list[Mapping[str, Any]]) -> tuple[int, int]:
    """(matches without twins, of them with a fair value) among the ones today's reference was fetched for."""
    base = [m for m in matches if not has_twins(m.get("price_ref"))
            and not (isinstance(m.get("fv"), Mapping) and not (m["fv"].get("ref") or {}).get("fetched", True))]
    return len(base), sum(1 for m in base if isinstance(m.get("fv"), Mapping))


def biases(matches: list[Mapping[str, Any]], curves: Mapping[tuple[str, str], Mapping[str, Any]]
           ) -> tuple[tuple[float | None, int], tuple[float | None, int]]:
    """((corr(d, G[trim]), n), (corr(d, ln km − ln KM[year]), n)) over the matches with rule_h true."""
    dg, g, dk, k = [], [], [], []
    for m in matches:
        fv = m.get("fv")
        if not isinstance(fv, Mapping) or not fv.get("rule_h") or (fv.get("ref") or {}).get("fetched") is False:
            continue
        d = _num(fv.get("d"))
        curve = curves.get((m.get("make"), m.get("model"))) or {}
        if d is None:
            continue
        trim = m.get("trim").lower() if isinstance(m.get("trim"), str) and m["trim"].strip() else None
        premium = ((curve.get("trims") or {}).get(trim) or {}).get("g") if trim else None
        if premium is not None and (fv.get("known") or {}).get("trim"):
            dg.append(d)
            g.append(float(premium))
        year = (curve.get("years") or {}).get(str(m.get("year"))) or {}
        km, typical = _num(m.get("mileage_km")), _num(year.get("km"))
        if (fv.get("known") or {}).get("km") and km and typical and km > 0 and typical > 0:
            dk.append(d)
            k.append(math.log(km) - math.log(typical))
    return (corr(dg, g), len(g)), (corr(dk, k), len(k))


def stability(runs: list[Mapping[str, Any]], params: str | None = None) -> tuple[float | None, int]:
    """(median |exp(ΔA[year]) − 1| between the last ok runs of consecutive Argentina days, pairs), for
    the models with STABILITY_MIN_N listings or more in both runs, years in both."""
    by_day: dict[date, Mapping[str, Any]] = {}
    for r in sorted(runs, key=lambda r: r["started_at"]):
        if params and r.get("params_hash") != params:
            continue
        by_day[r["started_at"].astimezone(_AR).date()] = r
    days = sorted(by_day)
    moves: list[float] = []
    for a, b in zip(days, days[1:]):
        if (b - a).days != 1:
            continue
        old = {(m["make"], m["model"]): m for m in (by_day[a].get("stats") or {}).get("models", [])}
        for m in (by_day[b].get("stats") or {}).get("models", []):
            o = old.get((m["make"], m["model"]))
            if not o or min(m.get("n") or 0, o.get("n") or 0) < STABILITY_MIN_N:
                continue
            for y, v in (m.get("a") or {}).items():
                if y in (o.get("a") or {}) and v is not None and o["a"][y] is not None:
                    moves.append(abs(math.exp(v - o["a"][y]) - 1))
    if not moves:
        return None, 0
    moves.sort()
    mid = len(moves) // 2
    return (moves[mid] if len(moves) % 2 else (moves[mid - 1] + moves[mid]) / 2), len(moves)


def deciding_rows(rows: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Per match, the row that decides (f3_decides): the card, or the later row when the card waited."""
    by_match: dict[int, list[Mapping[str, Any]]] = defaultdict(list)
    for r in rows:
        by_match[r["match_id"]].append(r)
    out = []
    for group in by_match.values():
        group = sorted(group, key=lambda r: (r["decided_at"], r.get("id") or 0))
        if not any(r["phase"] == "card" for r in group):
            continue
        row = next((r for r in group if r.get("f3_decides")), None)
        if row is not None:
            out.append(dict(row))
    return out


def _decision(row: Mapping[str, Any], *, level: Any, score: Any, diff_pct: Any) -> str:
    audience = row.get("audience")
    if not isinstance(audience, Mapping):
        return "none"
    event = decision_log.event_from(row, audience, level=level, score=score, diff_pct=_num(diff_pct))
    plan = classify(event, Rules())
    return plan.status if plan is not None else "none"


@dataclass
class Decision:
    row: dict[str, Any]
    today: str
    hybrid: str
    fv: Mapping[str, Any] | None

    @property
    def lost(self) -> bool:
        return self.today in ALERT and self.hybrid not in ALERT

    @property
    def gained(self) -> bool:
        return self.hybrid in ALERT and self.today not in ALERT


def decide(rows: list[Mapping[str, Any]], params: str | None = None) -> list[Decision]:
    """f2's alert decision again (classify, no daily cap) with today's reference and with the hybrid rule."""
    out = []
    for row in deciding_rows(rows):
        breakdown = row.get("f2_breakdown") if isinstance(row.get("f2_breakdown"), Mapping) else {}
        fv = breakdown.get("shadow_fair_value")
        fv = fv if isinstance(fv, Mapping) and (params is None or fv.get("params") == params) else None
        ref = row.get("price_ref") if isinstance(row.get("price_ref"), Mapping) else {}
        today = _decision(row, level=row.get("f2_level"), score=row.get("f2_score"), diff_pct=ref.get("diff_pct"))
        hybrid = today
        if fv is not None and fv.get("rule_h") and isinstance(fv.get("f2"), Mapping):
            alt = fv["f2"]
            hybrid = ("none" if alt.get("excluded") else
                      _decision(row, level=alt.get("level"), score=alt.get("score"), diff_pct=fv.get("d")))
        out.append(Decision(dict(row), today, hybrid, fv))
    return out


def _bucket(x: float, buckets) -> str:
    for hi, label in buckets:
        if x < hi:
            return label
    return buckets[-1][1]


def _band(score: Any) -> str:
    s = _num(score) or 0
    return "a" if s < 60 else "b" if s < 70 else "c" if s < 80 else "d"


def budget_table(matches: list[Mapping[str, Any]], opens: set[tuple[str, int]], key: str,
                 buckets) -> list[tuple[str, int, float, float | None]]:
    """Annex B with the fair value: per bucket, (label, opened, expected, opened / expected), comparing
    inside the same search and score band («1» = no preference)."""
    rows = []
    for m in matches:
        fv = m.get("fv")
        b = fv.get("budget") if isinstance(fv, Mapping) else None
        ratio = _num(b.get(key)) if isinstance(b, Mapping) else None
        price, usd = _num(m.get("price_usd")), _num(b.get("usd")) if isinstance(b, Mapping) else None
        if ratio is None or not price or not usd or price > 1.02 * usd:
            continue
        rows.append((m["search_profile_id"], _band(m.get("score")), _bucket(ratio, buckets),
                     (m.get("user_id"), int(m["listing_id"])) in opens))
    cell: dict[tuple, list[int]] = defaultdict(lambda: [0, 0])
    for sid, band, _, opened in rows:
        cell[(sid, band)][0] += 1
        cell[(sid, band)][1] += opened
    got: dict[str, list[float]] = defaultdict(lambda: [0, 0.0])
    for sid, band, bucket, opened in rows:
        n, o = cell[(sid, band)]
        if o == 0:
            continue
        got[bucket][0] += opened
        got[bucket][1] += o / n
    return [(label, int(got[label][0]), round(got[label][1], 1),
             round(got[label][0] / got[label][1], 2) if got[label][1] else None) for _, label in buckets]


# ---------------------------------------------------------------------------
# Rendering (Spanish)
# ---------------------------------------------------------------------------

def _pct(x: float | None, digits: int = 1) -> str:
    return "—" if x is None else f"{100 * x:.{digits}f} %".replace(".", ",")


def _dec(x: float | None, digits: int = 2) -> str:
    return "—" if x is None else f"{x:.{digits}f}".replace(".", ",")


def _ok(passed: bool | None) -> str:
    return "sin datos" if passed is None else "✅ pasa" if passed else "❌ no pasa"


def _money(x: Any) -> str:
    v = _num(x)
    return "—" if v is None else f"USD {int(round(v)):,}".replace(",", ".")


def _cell(x: Any) -> str:
    return str(x if x is not None else "—").replace("|", "/").replace("\n", " ")


def render(data: Data, *, seed: int = 20261120) -> str:
    since = data.since.astimezone(_AR).date().isoformat() if data.since else "el principio"
    until = (data.until.astimezone(_AR) - timedelta(seconds=1)).date().isoformat()
    lines = ["# Valor justo · informe de la sombra", "",
             f"Período: {since} a {until} (días de Argentina)."
             + (f" Solo params `{data.params}`." if data.params else ""), ""]
    if not data.available:
        lines.append("La migración del valor justo no está aplicada: no hay nada que medir.")
        return "\n".join(lines)
    days = len({r["started_at"].astimezone(_AR).date() for r in data.runs})
    hashes = sorted({r.get("params_hash") for r in data.runs if r.get("params_hash")})
    lines.append(f"Corridas ok: {len(data.runs)} en {days} días. Params vistos: "
                 + (", ".join(f"`{h}`" for h in hashes) or "ninguno") + ".")
    if days < MIN_DAYS:
        lines.append(f"Menos de {MIN_DAYS} días de sombra: los criterios se leen, no deciden.")
    if len(hashes) > 1 and not data.params:
        lines.append("Hay más de un params: pasar `--params` para medir uno solo.")
    lines.append("")

    curves = curve_index(data.curves)
    base, covered = coverage(data.matches)
    c1 = covered / base if base else None
    (g_corr, g_n), (k_corr, k_n) = biases(data.matches, curves)
    s_move, s_n = stability(data.runs, data.params)
    decisions = decide(data.decisions, data.params)
    today = sum(d.today in ALERT for d in decisions)
    hybrid = sum(d.hybrid in ALERT for d in decisions)
    ratio = hybrid / today if today else None

    lines += ["## Criterios (§7)", "", "| # | criterio | medido | umbral | resultado |", "|---|---|---|---|---|"]
    lines.append(f"| 1 | Cobertura: matches sin gemelos con valor justo | {_pct(c1)} ({covered} de {base}) | "
                 f"80 % o más | {_ok(None if c1 is None else c1 >= COVERAGE_MIN)} |")
    lines.append(f"| 2 | Sesgo de versión: corr(d, prima), con regla híbrida | {_dec(g_corr)} (n {g_n}) | "
                 f"entre −0,10 y 0,10 | {_ok(None if g_corr is None else abs(g_corr) <= BIAS_MAX)} |")
    lines.append(f"| 3 | Sesgo de km: corr(d, km relativo al de su año) | {_dec(k_corr)} (n {k_n}) | "
                 f"entre −0,10 y 0,10 | {_ok(None if k_corr is None else abs(k_corr) <= BIAS_MAX)} |")
    lines.append(f"| 4 | Estabilidad: cambio mediano de A[año], días seguidos, modelos con {STABILITY_MIN_N}+ | "
                 f"{_pct(s_move, 2)} ({s_n} pares) | 1,5 % o menos | "
                 f"{_ok(None if s_move is None else s_move <= STABILITY_MAX)} |")
    lines.append(f"| 5 | Volumen: alertas con la regla híbrida / alertas de hoy | {_dec(ratio)} ({hybrid} / {today}) | "
                 f"entre 0,85 y 1,10 | {_ok(None if ratio is None else VOLUME_MIN <= ratio <= VOLUME_MAX)} |")
    lines.append(f"| 6 | Revisión de Juan: {REVIEW_N} que se caen y {REVIEW_N} que aparecen | abajo | "
                 "14 o más de cada grupo | a revisar |")
    lines.append("")
    lines.append("Las alertas se recalculan con `notifications.engine.classify` y la audiencia guardada, sin el tope "
                 "diario. Decisiones de la bitácora: solo mientras la sombra de f3 está prendida.")
    lines.append("")

    enabled = [c for c in data.curves if c.get("enabled")]
    lines += ["## Modelos", "", f"{len(enabled)} habilitados de {len(data.curves)} con curva.", "",
              "| modelo | avisos | error valor justo | error hoy | habilitada |", "|---|---|---|---|---|"]
    for c in data.curves[:40]:
        lines.append(f"| {_cell(c['make'])} {_cell(c['model'])} | {c['n']} | {_pct(_num(c.get('cv_err')))} | "
                     f"{_pct(_num(c.get('cohort_err')))} | {'sí' if c.get('enabled') else 'no'} |")
    if data.runs:
        last = data.runs[-1].get("stats") or {}
        flips = sum(int(m.get("guard_flips") or 0) for m in last.get("models", []))
        lines += ["", f"Avisos de la muestra que cruzan el 65 % con una referencia y no con la otra "
                      f"(`guard_flips`, última corrida): {flips}. Aproximado: usa la referencia «todo el modelo»."]
    lines.append("")

    lines += ["## Presupuesto (§6.2)", "",
              "Dentro de la misma búsqueda y banda de score, 1 = sin preferencia.", "",
              "| valor del auto contra el tope | abiertos | esperados | veces lo esperado |", "|---|---|---|---|"]
    for label, opened, expected, times in budget_table(data.matches, data.opens, "value_ratio", VALUE_BUCKETS):
        lines.append(f"| {label} | {opened} | {_dec(expected, 1)} | {_dec(times)} |")
    lines += ["", "| precio contra el tope | abiertos | esperados | veces lo esperado |", "|---|---|---|---|"]
    for label, opened, expected, times in budget_table(data.matches, data.opens, "price_ratio", PRICE_BUCKETS):
        lines.append(f"| {label} | {opened} | {_dec(expected, 1)} | {_dec(times)} |")
    lines.append("")

    rng = random.Random(seed)
    for title, group in (("Alertas que se caerían", [d for d in decisions if d.lost]),
                         ("Alertas que aparecerían", [d for d in decisions if d.gained])):
        pick = sorted(rng.sample(group, min(REVIEW_N, len(group))), key=lambda d: d.row["decided_at"])
        lines += [f"## {title} ({len(pick)} de {len(group)}, al azar)", ""]
        if not pick:
            lines += ["Ninguna.", ""]
            continue
        lines += ["| match | aviso | precio | hoy | valor justo | f2 hoy → con valor justo |", "|---|---|---|---|---|---|"]
        for d in pick:
            r, fv = d.row, d.fv or {}
            ref = r.get("price_ref") or {}
            alt = fv.get("f2") or {}
            lines.append(f"| {r['match_id']} | {_cell(r.get('title'))[:60]} | {_money(r.get('price_usd'))} | "
                         f"{_money(ref.get('median'))} ({_cell(ref.get('level_used'))}, n {_cell(ref.get('n'))}) | "
                         f"{_money(fv.get('value'))} ({_cell(fv.get('level'))}) | "
                         f"{r.get('f2_score')} {r.get('f2_level')} → {alt.get('score')} {alt.get('level')} |")
        lines.append("")
    return "\n".join(lines)


def _day(text: str) -> datetime:
    return datetime.combine(date.fromisoformat(text), datetime.min.time(), tzinfo=_AR)


async def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--since", help="desde este día (incluido)")
    p.add_argument("--until", help="hasta este día (incluido); por defecto hoy")
    p.add_argument("--params", help="solo este hash de app_config.fair_value")
    p.add_argument("--seed", type=int, default=20261120, help="semilla de la muestra al azar del criterio 6")
    p.add_argument("--out", help="escribir el markdown en este archivo")
    args = p.parse_args(argv)
    since = _day(args.since) if args.since else None
    until = (_day(args.until) if args.until else datetime.now(_AR).replace(hour=0, minute=0, second=0,
                                                                            microsecond=0)) + timedelta(days=1)
    await db.open_pool()
    try:
        data = await read(since=since, until=until, params=args.params)
    finally:
        await db.close_pool()
    text = render(data, seed=args.seed)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(run(main()))

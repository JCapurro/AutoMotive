"""
Explain why a listing matches (or not) a search profile, and its score.

Recomputes everything with today's config, comparables and fx (sección 6) and,
if a match row exists, shows what is stored next to it.

Usage (from worker/):
    python -m tools.explain_match <match_id>
    python -m tools.explain_match --profile <search_profile_id> --listing <listing_id>
    python -m tools.explain_match <match_id> --json
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Any

# Force UTF-8 stdout on Windows consoles (cp1252 default chokes on emoji/arrows)
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import db
from aio import run
from db.repos.profiles import profiles_by_ids
from intelligence import copy
from intelligence.config import COMPONENTS
from intelligence.engine import assess
from intelligence.matching import FAIL, OK
from pipeline.scoring import Scorer


_ICON = {OK: "✅", FAIL: "❌", "unknown": "❔"}


async def load(match_id: int | None, profile_id: int | None,
               listing_id: int | None) -> tuple[dict | None, int, int]:
    stored = None
    async with db.connection() as cx:
        if match_id is not None:
            stored = await (await cx.execute("SELECT * FROM matches WHERE id = %s", (match_id,))).fetchone()
            if stored is None:
                raise SystemExit(f"match {match_id} no existe")
            profile_id, listing_id = stored["search_profile_id"], stored["listing_id"]
        else:
            stored = await (await cx.execute(
                "SELECT * FROM matches WHERE search_profile_id = %s AND listing_id = %s",
                (profile_id, listing_id))).fetchone()
    return stored, profile_id, listing_id


def explain(listing: dict, profile: dict, scorer: Scorer) -> dict[str, Any]:
    """Everything the tool prints, as data (also the --json output)."""
    result, score, ev = assess(listing, profile, price_ref=scorer.refs.get(listing["id"]),
                               cfg=scorer.cfg, now=scorer.now, fx_rate=scorer.fx_rate,
                               timing_belt=listing.get("timing_belt"))
    return {
        "listing": {k: listing.get(k) for k in ("id", "source", "external_id", "title", "url", "make",
                                                "model", "trim", "year", "price", "currency",
                                                "price_usd", "mileage_km", "transmission", "body_type")},
        "profile": {"id": profile["id"], "filters": profile["filters"],
                    "preferences": profile["preferences"],
                    # PRO-01: whether filters.seller_types is a hard filter (the plan's).
                    "seller_filter": bool(profile.get("seller_filter"))},
        "is_match": result.is_match and not score.excluded,
        "failed": result.failed,
        "excluded": score.excluded,
        "fx_rate": scorer.fx_rate,
        **ev.row(),
        "questions": ev.questions,
    }


def render(data: dict[str, Any], stored: dict | None) -> str:
    l, lines = data["listing"], []
    lines.append(f"Listing #{l['id']} · {l['source']} · {l['title']}")
    lines.append(f"  {l['url']}")
    lines.append(f"  {l['make']} {l['model']} {l['trim'] or '(versión ?)'} · {l['year']} · "
                 f"{copy.money(l['price'], l['currency'])} (USD {copy.number(l['price_usd'])}) · "
                 f"{copy.number(l['mileage_km'])} km · {l['transmission'] or 'transmisión ?'} · "
                 f"{copy.BODY_TYPE.get(l.get('body_type'), l.get('body_type')) or 'carrocería ?'}")
    lines.append(f"Profile #{data['profile']['id']}: {json.dumps(data['profile']['filters'], ensure_ascii=False)}")
    if data["profile"]["preferences"]:
        lines.append(f"  preferencias: {json.dumps(data['profile']['preferences'], ensure_ascii=False)}")
    lines.append("")

    if data["is_match"]:
        verdict = "MATCH"
    elif data["excluded"]:
        verdict = f"NO MATCH — excluido: {data['excluded']}"
    else:
        verdict = f"NO MATCH — falla: {', '.join(data['failed'])}"
    lines.append(verdict)
    lines.append("")
    lines.append("Razones")
    for name, r in data["match_reasons"].items():
        lines.append(f"  {_ICON[r['result']]} {name:<16} {r['kind']:<4}  {r['detail']}")

    ref = data["price_ref"]
    lines.append("")
    if ref:
        lines.append(f"Comparables ({ref['level_used']}, n={ref['n']}): mediana USD {copy.number(ref['median'])} · "
                     f"p25 {copy.number(ref['p25'])} · p75 {copy.number(ref['p75'])} · "
                     f"km mediana {copy.number(ref['median_km'])} · diff {ref['diff_pct']}%")
    else:
        lines.append("Comparables: sin datos")

    b = data["score_breakdown"]
    lines.append("")
    lines.append(f"Opportunity Score {data['score']} → {copy.LEVEL_LABEL[data['level']]}"
                 + (f"  (guarda: {b['guard']})" if b.get("guard") else ""))
    lines.append(f"  {'componente':<13} {'c':>6} {'w':>5} {'aporte':>7}  explicación")
    for name in COMPONENTS:
        c = b[name]
        lines.append(f"  {name:<13} {c['c']:>6.2f} {c['w']:>5g} {c['contribution']:>7.2f}  {c['explanation']}")

    shadow = b.get("shadow_f3") if isinstance(b, dict) else None
    if isinstance(shadow, dict):
        lines.append("")
        lines += shadow_lines(shadow)

    lines.append("")
    lines.append("Red flags" if data["red_flags"] else "Red flags: ninguna")
    for f in data["red_flags"]:
        lines.append(f"  ⚠️ [{f['severity']}] {f['id']}: {f['text']}")
    lines.append("")
    lines.append("Preguntas al vendedor")
    lines.append(f"  {data['questions']}")

    lines.append("")
    if stored:
        lines.append(f"Guardado (match #{stored['id']}): score {stored['score']} · {stored['level']} · "
                     f"{stored['scoring_version']} · backfill={stored['is_backfill']} · "
                     f"actualizado {stored['updated_at']:%Y-%m-%d %H:%M}")
        if stored["score"] != data["score"] or stored["scoring_version"] != data["scoring_version"]:
            lines.append("  ↳ difiere del cálculo de hoy: el re-score nocturno lo actualiza")
    else:
        lines.append("Sin match guardado para este par.")
    return "\n".join(lines)


_F3_LEVEL = {**copy.LEVEL_LABEL, "excluded": "excluido"}


def _f(x: Any, digits: int = 2) -> str:
    return "—" if not isinstance(x, (int, float)) or isinstance(x, bool) else f"{x:.{digits}f}"


def _pct(x: Any) -> str:
    return "—" if not isinstance(x, (int, float)) or isinstance(x, bool) else f"{x:.1f}%"


def shadow_lines(s: dict[str, Any]) -> list[str]:
    """The «Sombra f3» block: f3 «precio × encaje» as the shadow computed it (score_breakdown.shadow_f3).
    f2 decides everything; this is what f3 would say
    (docs/superpowers/specs/2026-11-08-recalibracion-score-design.md)."""
    deal, fit, seller = s.get("deal") or {}, s.get("fit") or {}, s.get("seller") or {}
    out = [f"Sombra f3 ({s.get('v')} · params {s.get('params')} · modo {s.get('mode')}): "
           "no decide, f2 sigue decidiendo"]
    level = f"  nivel {_F3_LEVEL.get(s.get('level'), s.get('level'))} · score {s.get('score')}"
    if s.get("level_uncapped") != s.get("level"):
        uncapped = s.get("level_uncapped")
        level += f"  (sin el tope de vendedor: {_F3_LEVEL.get(uncapped, uncapped)})"
    out.append(level)
    ref = f"n={deal.get('n')}, {deal.get('level_used')}" if deal.get("n") is not None else "sin comparables"
    d = f"d {_pct(deal.get('d'))}"
    if deal.get("d_eff") != deal.get("d"):
        d += f" · d_eff {_pct(deal.get('d_eff'))}"
    if deal.get("diff_pct") != deal.get("d"):
        d += f" · publicado {_pct(deal.get('diff_pct'))}"
    notes = ((" · creíble" if deal.get("credible") else "")
             + (" · precio de relleno" if deal.get("placeholder") else ""))
    out.append(f"  precio {_f(deal.get('value'))} (crudo {_f(deal.get('raw'))} · confianza {_f(deal.get('r'))} · "
               f"{d} · pleno desde {_pct(deal.get('d_full'))} · {ref} · {deal.get('tier')}{notes})")
    prefs = ", ".join(f"{k} {_f(v)}" for k, v in (fit.get("prefs") or {}).items()) or "sin preferencias"
    out.append(f"  encaje {_f(fit.get('level'))} (en el score {_f(fit.get('score'))}) · {prefs}")
    out.append(f"  flags: {', '.join(s.get('flags') or []) or 'ninguna'}")
    if s.get("a_verificar"):
        out.append(f"  a verificar: {', '.join(s['a_verificar'])}")
    if seller.get("wanted") or seller.get("agency_voice"):
        parts = []
        if seller.get("wanted"):
            how = "filtro estricto" if seller.get("strict") else "preferencia"
            parts.append(f"busca {'/'.join(seller['wanted'])} ({how})")
        parts.append(f"efectivo {seller.get('effective') or 'sin dato'}")
        parts.append(f"para la preferencia {seller.get('for_preference') or 'sin dato'}")
        if seller.get("agency_voice"):
            parts.append(f"voz de agencia «{seller['agency_voice']}»")
        if seller.get("capped"):
            parts.append("tope aplicado")
        out.append(f"  vendedor: {' · '.join(parts)}")
    if s.get("would_defer"):
        out.append("  esperaría al detalle (la tarjeta no trae vendedor)")
    alts = s.get("alternatives") or {}
    if alts:
        out.append("  alternativas: " + ", ".join(
            f"{k} → {_F3_LEVEL.get(a.get('level'), a.get('level'))} {a.get('score')}" for k, a in alts.items()))
    return out


async def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("match_id", nargs="?", type=int)
    p.add_argument("--profile", type=int)
    p.add_argument("--listing", type=int)
    p.add_argument("--json", action="store_true", help="imprimir el detalle como JSON")
    args = p.parse_args(argv)
    if args.match_id is None and (args.profile is None or args.listing is None):
        p.error("indicá un match_id, o --profile y --listing")

    await db.open_pool()
    try:
        stored, profile_id, listing_id = await load(args.match_id, args.profile, args.listing)
        [alert] = await profiles_by_ids([profile_id]) or [None]
        if alert is None:
            raise SystemExit(f"search profile {profile_id} no existe")
        scorer = await Scorer.create()
        rows = await scorer.prepare([listing_id])
        if listing_id not in rows:
            raise SystemExit(f"listing {listing_id} no existe")
        data = explain(rows[listing_id], alert["profile"], scorer)
    finally:
        await db.close_pool()

    if args.json:
        print(json.dumps({**data, "stored": stored}, ensure_ascii=False, indent=2, default=str))
    else:
        print(render(data, stored))
    return 0


if __name__ == "__main__":
    sys.exit(run(main()))

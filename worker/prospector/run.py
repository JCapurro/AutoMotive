"""One day's run: pick, find the phone, build the facts, write, check, store.

    python -m prospector                      # the day's batch (live once the tables exist)
    python -m prospector --dry-run --new 5    # read-only: a report in %LOCALAPPDATA%\\EseAuto\\prospeccion\\corridas

Writes only the bot's own tables, and nothing at all with --dry-run (or while
the migration is not applied). Never prints a secret.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from prospector import alive, claude, db, facts as F, lookup, sellers, writer
from prospector.sellers import Prospect

ROOT = Path(__file__).resolve().parents[2]
STATE_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "EseAuto" / "prospeccion"
ART = timezone(timedelta(hours=-3))
NEW_PER_DAY = 30
BUFFER = 1.3                   # candidates per slot: some messages do not pass the review
MAX_WEB_LOOKUPS = 40
LOOKUP_BATCH = 5
NO_CONTACT_RETRY_DAYS = 21
STALE_KEEP_DAYS = 1            # a ready message not sent by the day after expires


@dataclass
class Candidate:
    prospect: Prospect
    zone: F.Zone
    hooks: list[dict[str, Any]]
    score: float
    db_id: int | None = None
    prior: dict[str, Any] | None = None


def today_art() -> str:
    return datetime.now(ART).date().isoformat()


def log(message: str) -> None:
    print(f"[{datetime.now(ART):%H:%M:%S}] {message}", flush=True)


def _load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def score(p: Prospect, hooks: list[dict[str, Any]], now: datetime) -> float:
    s = 0.0
    if hooks:
        s += 100 + 15 * (hooks[0]["tier"] - 1)
    if p.phone:
        s += 40
    elif p.kind == "persona" and not {"rosariogarage", "mercadolibre"} & set(p.sources):
        s -= 200        # a person without a number in their listing or a page that shows it: nothing to do
    n = len(p.listings)
    s += 10 if 5 <= n <= 30 else 0
    old = sum(1 for r in p.listings if (d := F._days(r, now)) is not None and d > F.OLD_DAYS)
    s += 4 * min(old, 5)
    return s


def known_index(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out = {}
    for r in rows:
        for key in r.get("seller_keys") or []:
            out[key] = r
    return out


def candidates(conn, prospects: list[Prospect], *, known: dict[str, dict[str, Any]], zone_map, now: datetime
               ) -> tuple[list[Candidate], list[dict[str, Any]]]:
    models = {(r["make"], r["model"]) for p in prospects for r in p.listings if r.get("make") and r.get("model")}
    log(f"buscando ganchos de {len(models)} modelos (últimas {F.HOOK_HOURS} h)")
    pool = db.hook_pool(conn, models, F.HOOK_HOURS)
    out = []
    for p in prospects:
        prior = next((known[k] for k in p.keys if k in known), None)
        if prior:
            if prior["status"] not in ("new", "no_contact"):
                continue
            checked = prior.get("phone_checked_at")
            if prior["status"] == "no_contact" and checked and now - checked < timedelta(days=NO_CONTACT_RETRY_DAYS):
                continue
            if prior.get("phone") and not p.phone:
                p.phone, p.phone_source = prior["phone"], "guardado"
        zone = F.zone_of(p.listings, zone_map)
        hooks = F.hook_candidates(pool, p, zone, zone_map)
        out.append(Candidate(p, zone, hooks, score(p, hooks, now), prior["id"] if prior else None, prior))
    out.sort(key=lambda c: -c.score)
    return out, pool


def diversify(ranked: list[Candidate], need: int, share: float = 0.4) -> list[Candidate]:
    """The ranking reordered so that no region takes more than `share` of the
    first `need` places (AMBA alone would fill the whole batch)."""
    cap = max(2, math.ceil(need * share))
    first, rest, seen = [], [], {}
    for c in ranked:
        region = c.zone.region or c.zone.province_id or "?"
        if seen.get(region, 0) < cap:
            seen[region] = seen.get(region, 0) + 1
            first.append(c)
        else:
            rest.append(c)
    return first + rest


def reachable(p: Prospect) -> bool:
    """A number to open wa.me with, or the WhatsApp button of their own ML listing."""
    return bool(p.phone) or p.phone_source == "boton_ml"


def find_phones(ranked: list[Candidate], need: int, *, cache: dict[str, Any], call, dry: bool,
                max_lookups: int = MAX_WEB_LOOKUPS, ml_button: bool = True,
                ml_check=None) -> tuple[list[Candidate], list[Candidate]]:
    """Walks the ranking until `need` candidates can be reached on WhatsApp. Returns (reachable, not).
    ml_button: whether a seller reachable only through their ML listing's button counts
    (the table takes phone_source 'boton_ml' only after 20261226120000)."""
    ml_check = ml_check or lookup.ml_button
    ready: list[Candidate] = []
    missing: list[Candidate] = []
    queue: list[Candidate] = []
    lookups = 0

    def flush() -> None:
        nonlocal lookups
        if not queue:
            return
        batch = {f"a{i}": (c.prospect, c.zone.label()) for i, c in enumerate(queue)}
        log(f"buscando el WhatsApp público de {len(batch)} agencias en la web")
        try:
            found = lookup.web(batch, call=call)
        except claude.ClaudeError as error:
            log(f"  la búsqueda web falló: {error}")
            found = {}
        lookups += len(batch)
        for i, c in enumerate(queue):
            hit = found.get(f"a{i}")
            if hit:
                c.prospect.phone, c.prospect.phone_evidence = hit
                c.prospect.phone_source = "web"
                ready.append(c)
            else:
                missing.append(c)
            cache[c.prospect.key] = {"phone": c.prospect.phone, "source": c.prospect.phone_source,
                                     "evidence": c.prospect.phone_evidence, "checked": today_art()}
        queue.clear()

    for c in diversify(ranked, need):
        if len(ready) >= need:
            break
        p = c.prospect
        cached = cache.get(p.key)
        if not p.phone and cached and cached.get("phone"):
            p.phone, p.phone_source, p.phone_evidence = cached["phone"], cached.get("source"), cached.get("evidence")
        if p.phone:
            ready.append(c)
            continue
        recent_miss = cached and cached.get("checked") and (
            datetime.fromisoformat(cached["checked"]).date()
            > (datetime.now(ART) - timedelta(days=NO_CONTACT_RETRY_DAYS)).date())
        if recent_miss and not (ml_button and "mercadolibre" in p.sources):
            missing.append(c)
            continue
        if "rosariogarage" in p.sources:
            hit = lookup.rosariogarage(p)
            time.sleep(1.0)
            if hit:
                p.phone, p.phone_evidence = hit
                p.phone_source = "pagina_aviso"
                cache[p.key] = {"phone": p.phone, "source": p.phone_source, "evidence": p.phone_evidence,
                                "checked": today_art()}
                ready.append(c)
                continue
        if ml_button and "mercadolibre" in p.sources:
            # Read every run: the listing must be live today for Juan to open it.
            url = ml_check(p)
            time.sleep(1.0)
            if url:
                p.phone_source, p.phone_evidence = "boton_ml", url
                ready.append(c)
                continue
        if p.kind == "agencia" and lookups + len(queue) < max_lookups:
            queue.append(c)
            if len(queue) >= LOOKUP_BATCH:
                flush()
            continue
        cache[p.key] = {"phone": None, "checked": today_art()}
        missing.append(c)
    flush()
    return ready[:need] if len(ready) > need else ready, missing


def lookups_for(conn) -> F.Lookups:
    pool_cache: dict[int, list] = {}

    def pool(listing_id: int):
        if listing_id not in pool_cache:
            pool_cache[listing_id] = db.comparable_pool(conn, listing_id)
        return pool_cache[listing_id]

    return F.Lookups(
        pool=pool,
        demand=lambda make, model, lat, lon: db.demand(conn, make, model, lat, lon, F.DEMAND_RADIUS_KM),
        stopped=lambda keys: db.stopped_listings(conn, keys, 30),
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m prospector", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="no escribe en la base: deja un informe local")
    ap.add_argument("--new", type=int, default=NEW_PER_DAY, help="contactos nuevos de hoy (30)")
    ap.add_argument("--env-file", type=Path, default=ROOT / ".env")
    ap.add_argument("--no-followups", action="store_true")
    ap.add_argument("--max-lookups", type=int, default=MAX_WEB_LOOKUPS)
    ap.add_argument("--solo-boton-ml", action="store_true",
                    help="prueba: solo vendedores de ML sin número en sus avisos (los del botón de WhatsApp)")
    args = ap.parse_args(argv)

    db.load_env(args.env_file)
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    lock = STATE_DIR / "corriendo.lock"
    if lock.exists() and time.time() - lock.stat().st_mtime < 3 * 3600:
        log("ya hay una corrida en marcha: salgo")
        return 0
    lock.write_text(str(os.getpid()), encoding="utf-8")
    try:
        return _run(args)
    finally:
        lock.unlink(missing_ok=True)


def _run(args) -> int:
    now = datetime.now(timezone.utc)
    day = today_art()
    conn = db.connect()
    live = db.tables_exist(conn) and not args.dry_run
    if not live and not args.dry_run:
        log("las tablas de prospección no existen todavía (migración sin aplicar): corro en modo lectura")
    done_marker = STATE_DIR / "ultima-corrida.txt"
    if live and done_marker.exists() and done_marker.read_text(encoding="utf-8").strip() == day:
        log(f"la tanda de hoy ({day}) ya salió")
        return 0

    zone_map = db.config(conn, "market_zones")
    rows = db.base_rows(conn)
    banned = sellers.shared_phones(rows) | db.paid_phones(conn)
    contacted = sellers.load_contacted(STATE_DIR / "ya-contactados.json")
    prospects, dropped = sellers.build_prospects(rows, contacted=contacted, banned_phones=banned)
    log(f"{len(prospects)} prospectos en la base; fuera: {dict(dropped)}")

    # Read in a dry run too, so a test batch never shows someone already contacted.
    known = known_index(db.known_prospects(conn)) if db.tables_exist(conn) else {}
    target = args.new
    if live:
        expired = db.expire_stale(conn, STALE_KEEP_DAYS)
        if expired:
            log(f"{expired} mensajes de días anteriores vencieron sin enviarse")
        pending = db.pending_counts(conn).get("first", 0)
        target = max(0, args.new - pending)
        log(f"{pending} primeros mensajes siguen listos sin enviar: hoy se escriben {target}")

    ranked, pool = candidates(conn, prospects, known=known, zone_map=zone_map, now=now)
    cache_path = STATE_DIR / "telefonos.json"
    cache = _load_json(cache_path, {})
    call = claude.run
    need = int(round(target * BUFFER))
    ml_ok = args.dry_run or db.accepts_ml_button(conn)
    if not ml_ok:
        log("la migración 20261226120000 no está aplicada: los vendedores del botón de WhatsApp de ML quedan para otro día")
    if args.solo_boton_ml:
        ranked = [c for c in ranked if not c.prospect.phone and "mercadolibre" in c.prospect.sources]
    ready, missing = find_phones(ranked, need, cache=cache, call=call, dry=args.dry_run, max_lookups=args.max_lookups,
                                 ml_button=ml_ok)
    cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")
    log(f"{len(ready)} con WhatsApp, {len(missing)} sin contacto")

    looks = lookups_for(conn)
    checker = alive.Checker()          # each hook's listing page, read once, a few seconds apart
    examples = [dict(r) for r in db.replied_examples(conn)] if live else []
    jobs: list[writer.Job] = []
    meta: dict[str, dict[str, Any]] = {}
    taken: set[int] = set()          # one hook car per batch: two dealers never get the same one
    for i, c in enumerate(ready):
        fact = F.build(c.prospect, pool=pool, zone_map=zone_map, lookups=looks, now=now,
                       first_name=sellers.first_name(c.prospect), exclude_hooks=taken, alive=checker.check)
        taken.update(h["listing_id"] for h in fact["ganchos"])   # the writer may use either
        pid = f"p{i + 1}"
        jobs.append(writer.Job(pid, fact))
        meta[pid] = {"candidate": c, "step": "first"}

    if live and not args.no_followups:
        by_key = {k: p for p in prospects for k in p.keys}
        for row in db.due_prospects(conn):
            p = next((by_key[k] for k in row["seller_keys"] if k in by_key), None)
            if not p:
                log(f"seguimiento de {row['id']}: ya no tiene avisos en la base, queda para mañana")
                continue
            step = "followup" if row["step_sent"] == 1 else "last"
            previous = [r["final_text"] for r in conn.execute(
                "select final_text from public.prospect_messages where prospect_id = %s and status = 'sent' "
                "order by sent_at", (row["id"],)).fetchall()]
            fact = F.build(p, pool=pool, zone_map=zone_map, lookups=looks, now=now,
                           step="seguimiento" if step == "followup" else "ultimo",
                           exclude_hooks=db.used_hooks(conn, row["id"]), previous=previous,
                           first_name=row.get("first_name"), alive=checker.check)
            pid = f"s{len(jobs) + 1}"
            jobs.append(writer.Job(pid, fact))
            p.phone = row["phone"]
            p.phone_source, p.phone_evidence = row.get("phone_source"), row.get("phone_evidence")
            meta[pid] = {"candidate": Candidate(p, F.zone_of(p.listings, zone_map), [], 0, row["id"], row),
                         "step": step}

    log(f"escribiendo {len(jobs)} mensajes con {writer.WRITER_MODEL}")
    writer.write_all(jobs, examples=examples, call=call, log=log)
    passed = [j for j in jobs if j.chosen is not None]
    firsts = [j for j in passed if meta[j.pid]["step"] == "first"][:target]
    keep = set(id(j) for j in firsts) | {id(j) for j in passed if meta[j.pid]["step"] != "first"}
    log(f"pasaron {len(passed)} de {len(jobs)}; quedan {len(firsts)} nuevos")

    report = _report(jobs, meta, missing, keep, day)
    out_dir = STATE_DIR / "corridas"
    out_dir.mkdir(exist_ok=True)
    stamp = datetime.now(ART).strftime("%Y-%m-%d_%H%M")
    (out_dir / f"{stamp}.json").write_text(json.dumps(report, ensure_ascii=False, indent=1, default=str),
                                           encoding="utf-8")
    (out_dir / f"{stamp}.md").write_text(_markdown(report), encoding="utf-8")
    log(f"informe: {out_dir / (stamp + '.md')}")

    if live:
        _store(conn, jobs, meta, missing, keep, day)
        done_marker.write_text(day, encoding="utf-8")
    return 0


def _prospect_row(c: Candidate, status: str) -> dict[str, Any]:
    p = c.prospect
    return {
        "prospect_key": p.key, "seller_keys": p.keys, "kind": p.kind, "display_name": p.display_name,
        "first_name": sellers.first_name(p), "sources": p.sources, "province_id": c.zone.province_id,
        "region": c.zone.region, "locality": c.zone.label(), "phone": p.phone, "phone_source": p.phone_source,
        "phone_evidence": p.phone_evidence, "status": status, "listing_count": len(p.listings),
    }


def _store(conn, jobs, meta, missing, keep, day) -> None:
    for c in missing:
        db.upsert_prospect(conn, _prospect_row(c, "no_contact"))
    for j in jobs:
        m = meta[j.pid]
        c = m["candidate"]
        passed = id(j) in keep
        if m["step"] == "first":
            if not passed:
                continue        # back to the pool tomorrow: nothing stored about a message that did not pass
            pid = db.upsert_prospect(conn, _prospect_row(c, "queued"))
        else:
            pid = c.db_id
        hook = j.hook if passed else None
        db.insert_message(conn, {
            "prospect_id": pid, "step": m["step"], "batch_date": day,
            "status": "ready" if passed else "rejected", "facts": j.facts,
            "variants": [{"hook_type": v["tipo_gancho"], "text": v["texto"],
                          "problems": v.get("problemas_automaticos", [])} for v in j.variants],
            "chosen_index": j.chosen, "final_text": j.text, "hook_type": j.hook_type,
            "hook_listing_id": hook["listing_id"] if hook else None, "hook_url": hook["url"] if hook else None,
            "review": {"decision": j.review, "history": j.history, "dropped": j.dropped},
            "model": writer.WRITER_MODEL,
        })


def _report(jobs, meta, missing, keep, day) -> dict[str, Any]:
    items = []
    for j in jobs:
        c = meta[j.pid]["candidate"]
        items.append({
            "id": j.pid, "paso": meta[j.pid]["step"], "queda": id(j) in keep,
            "nombre": c.prospect.display_name, "perfiles": c.prospect.keys, "tipo": c.prospect.kind,
            "zona": c.zone.label(), "telefono": c.prospect.phone, "telefono_de": c.prospect.phone_source,
            "telefono_evidencia": c.prospect.phone_evidence, "hechos": j.facts,
            "variantes": j.variants, "elegida": j.chosen, "revision": j.review, "historial": j.history,
            "descartado": j.dropped,
        })
    return {"dia": day, "mensajes": items,
            "sin_contacto": [{"nombre": c.prospect.display_name, "tipo": c.prospect.kind, "zona": c.zone.label()}
                             for c in missing]}


def _markdown(report: dict[str, Any]) -> str:
    lines = [f"# Prospección {report['dia']}", ""]
    for m in report["mensajes"]:
        mark = "✅" if m["queda"] else "❌"
        lines += [f"## {mark} {m['nombre']} · {m['tipo']} · {m['zona'] or 'sin zona'}",
                  f"WhatsApp: {m['telefono']} ({m['telefono_de']}: {m['telefono_evidencia']})", ""]
        for i, v in enumerate(m["variantes"]):
            star = " ← elegida" if i == m["elegida"] else ""
            lines += [f"**Variante {i + 1} · {v['tipo_gancho']}{star}**", "", v["texto"], ""]
            if v.get("problemas_automaticos"):
                lines += ["Control automático: " + "; ".join(v["problemas_automaticos"]), ""]
        r = m["revision"] or {}
        lines += [f"Revisión: {r.get('decision')} · {r.get('por_que') or ''} {'; '.join(r.get('problemas') or [])}"]
        if m["descartado"]:
            lines += [f"Descartado: {m['descartado']}"]
        g = writer.hook_used(m["variantes"][m["elegida"]]["texto"] if m["elegida"] is not None else None,
                             m["hechos"].get("ganchos") or [])
        if g:
            lines += [f"Gancho: {g['auto']} en {g['lugar']} a {g['precio_publicado']}, "
                      f"{g['porcentaje_abajo_de_comparables']} % abajo de {g['cantidad_de_comparables']} "
                      f"({g['url']})"]
        lines += ["", "<details><summary>Hechos</summary>", "", "```json",
                  json.dumps(m["hechos"], ensure_ascii=False, indent=1, default=str), "```", "</details>", ""]
    lines += [f"Sin contacto: {len(report['sin_contacto'])}"]
    return "\n".join(lines)


if __name__ == "__main__":
    sys.exit(main())

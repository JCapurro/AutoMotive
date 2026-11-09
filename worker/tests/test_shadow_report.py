"""tools/shadow_report: the f3 shadow criteria (spec 2026-11-08 §11.4) over decision rows. Pure."""
from __future__ import annotations

import io
import unittest
from contextlib import redirect_stdout
from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

from tools import shadow_report as rep

T0 = datetime(2026, 11, 12, 15, 0, tzinfo=timezone.utc)
_ids = iter(range(1, 10_000))


def card(match_id: int, search: int = 1, *, f2_dec: str | None = "queued", f2_kind: str | None = "new_match",
         f3_dec: str | None = "queued", f3_kind: str | None = "new_match", f2_level: str = "good",
         f3_level: str | None = "good", d: float | None = 12.0, n: int = 20, year: int | None = 2017,
         price: float | None = 10_000, source: str = "mercadolibre", status: str = "active",
         would_defer: bool = False, enriched: bool = True, at: datetime = T0, f2_reason: str | None = None,
         **kw) -> dict:
    row = {"id": next(_ids), "match_id": match_id, "search_profile_id": search, "listing_id": 1000 + match_id,
           "user_id": f"u{search}", "model": "f2", "phase": "card", "decided_at": at,
           "f3_decides": not would_defer, "f2_version": "f2-v5-seller-margin", "f2_score": 75,
           "f2_level": f2_level, "f2_decision": f2_dec, "f2_kind": f2_kind if f2_dec in ("queued", "digest") else None,
           "f2_reason": f2_reason, "f3_params": "aaaaaaaaaaaa", "f3_score": 75, "f3_level": f3_level,
           "f3_level_uncapped": f3_level, "f3_decision": f3_dec,
           "f3_kind": f3_kind if f3_dec in ("queued", "digest") else None, "f3_reason": None,
           "f3_flags": [], "f3_a_verificar": [], "f3_seller_capped": False, "agency_voice": None,
           "placeholder": False, "would_defer": would_defer, "f3": {"fit": {"prefs": {}}},
           "price_ref": {"n": n, "level_used": "trim", "median": 11_000, "p25": 10_000, "p75": 12_000,
                         "diff_pct": d} if n else None,
           "price": price, "currency": "USD", "price_usd": price, "price_partial": False,
           "title": f"Auto {match_id}", "source": source, "year": year, "seller_type": None,
           "dealer_inferred": False, "enriched": enriched, "listing_status": status, "audience": {}}
    row.update(kw)
    return row


def later(of: dict, phase: str, *, f3_dec: str | None = "queued", f3_kind: str | None = "new_match",
          f3_level: str | None = "good", f3_decides: bool = True, minutes: int = 5, **kw) -> dict:
    row = {**of, "id": next(_ids), "phase": phase, "decided_at": of["decided_at"] + timedelta(minutes=minutes),
           "f2_decision": None, "f2_kind": None, "f2_reason": "f2_card_only", "f3_decides": f3_decides,
           "f3_decision": f3_dec, "f3_kind": f3_kind if f3_dec in ("queued", "digest") else None, "f3_level": f3_level}
    row.update(kw)
    return row


def sent(row: dict, *, status: str = "sent", clicked: bool = False, by_pair: bool = False) -> dict:
    return {"id": next(_ids), "match_id": None if by_pair else row["match_id"], "listing_id": row["listing_id"],
            "search_profile_id": row["search_profile_id"], "user_id": row["user_id"],
            "kind": row["f2_kind"] or "new_match", "status": status,
            "created_at": row["decided_at"] - timedelta(seconds=2),
            "clicked_at": row["decided_at"] + timedelta(hours=1) if clicked else None}


def data(rows, notifications=(), **kw) -> rep.Data:
    return rep.Data(rows=list(rows), notifications=list(notifications), **kw)


def crit(d: rep.Data, number: int) -> rep.Criterion:
    return next(c for c in rep.criteria(d) if c.number == number)


class DefinitionTests(unittest.TestCase):
    def test_placeholder(self):
        for p in (1111, 11_111, 1_111_111, 88_888, 11_111.0):
            self.assertTrue(rep.is_placeholder(p), p)
        for p in (111, 9999, 99_999, 11_112, 10_000, None, 0, -1111, float("nan"), "x"):
            self.assertFalse(rep.is_placeholder(p), p)

    def test_credible_at_decision(self):
        self.assertTrue(rep.credible_at_decision(card(1, d=12)))
        self.assertTrue(rep.credible_at_decision(card(1, d=5)))
        self.assertTrue(rep.credible_at_decision(card(1, d=35)))
        self.assertFalse(rep.credible_at_decision(card(1, d=4.9)))
        self.assertFalse(rep.credible_at_decision(card(1, d=35.1)))
        # Kavak's −9: 12 % below is 3 % for Kavak; 40 % is 31 %.
        self.assertFalse(rep.credible_at_decision(card(1, d=12, source="kavak")))
        self.assertTrue(rep.credible_at_decision(card(1, d=40, source="kavak")))
        self.assertFalse(rep.credible_at_decision(card(1, n=9)))
        self.assertFalse(rep.credible_at_decision(card(1, n=0)))
        self.assertFalse(rep.credible_at_decision(card(1, year=None)))
        self.assertFalse(rep.credible_at_decision(card(1, price=11_111)))
        self.assertTrue(rep.credible_at_decision(card(1, price=9_999)))
        self.assertFalse(rep.credible_at_decision(card(1, price=None)))
        self.assertFalse(rep.credible_at_decision(card(1, price_partial=True)))
        self.assertFalse(rep.credible_at_decision(card(1, status="gone")))
        self.assertFalse(rep.credible_at_decision(card(1, d=None)))

    def test_other_version_is_a_known_other_trim(self):
        self.assertTrue(rep.other_version(card(1, f3={"fit": {"prefs": {"trim": 0.5}}})))
        self.assertFalse(rep.other_version(card(1, f3={"fit": {"prefs": {"trim": 1.0}}})))
        self.assertFalse(rep.other_version(card(1, f3={"fit": {"prefs": {"trim": 0.75}}}, f3_a_verificar=["trim"])))
        self.assertFalse(rep.other_version(card(1, f3=None)))

    def test_day_bounds_are_argentina_days(self):
        now = datetime(2026, 11, 20, tzinfo=timezone.utc)
        since, until = rep.day_bounds(date(2026, 11, 12), date(2026, 11, 13), now=now)
        self.assertEqual(since, datetime(2026, 11, 12, 3, 0, tzinfo=timezone.utc))
        self.assertEqual(until, datetime(2026, 11, 14, 3, 0, tzinfo=timezone.utc))
        self.assertEqual(rep.day_bounds(None, None, now=now), (None, now))


class DecidingRowTests(unittest.TestCase):
    def test_the_card_decides_unless_it_waits_for_the_detail(self):
        c = card(1)
        [cand] = rep.decisions(data([c, later(c, "deferred", f3_decides=False, f3_dec="none")]))
        self.assertEqual(cand.deciding["phase"], "card")
        self.assertTrue(cand.f3_alert)

    def test_a_waiting_card_is_decided_by_the_deferred_row(self):
        c = card(1, would_defer=True)
        [cand] = rep.decisions(data([c, later(c, "deferred", f3_dec="none", f3_level="match")]))
        self.assertEqual(cand.deciding["phase"], "deferred")
        self.assertFalse(cand.f3_alert)

    def test_by_the_sweeper_when_it_came_first(self):
        c = card(1, would_defer=True)
        rows = [c, later(c, "sweeper", minutes=20), later(c, "deferred", f3_decides=False, f3_dec="none", minutes=30)]
        [cand] = rep.decisions(data(rows))
        self.assertEqual(cand.deciding["phase"], "sweeper")
        self.assertTrue(cand.f3_alert)
        # The earliest deciding row wins even if both say they decide (a race).
        rows[2]["f3_decides"] = True
        [cand] = rep.decisions(data(rows))
        self.assertEqual(cand.deciding["phase"], "sweeper")

    def test_still_pending(self):
        [cand] = rep.decisions(data([card(1, would_defer=True)]))
        self.assertTrue(cand.pending)
        self.assertFalse(cand.f3_alert)
        self.assertFalse(cand.lost)

    def test_later_rows_without_a_card_are_ignored(self):
        c = card(1)
        self.assertEqual(rep.decisions(data([later(c, "deferred")])), [])

    def test_f2_sent_comes_from_notifications(self):
        c = card(1)
        [cand] = rep.decisions(data([c]))
        self.assertFalse(cand.f2_sent)       # the trace says queued, but no notification row
        [cand] = rep.decisions(data([c], [sent(c, by_pair=True)]))
        self.assertTrue(cand.f2_sent)        # found by (search, listing) after the match was deleted
        [cand] = rep.decisions(data([c], [sent(c, status="skipped")]))
        self.assertFalse(cand.f2_sent)
        old = sent(c, by_pair=True)
        old["created_at"] = c["decided_at"] - timedelta(days=3)
        [cand] = rep.decisions(data([c], [old]))
        self.assertFalse(cand.f2_sent)       # an older alert of the same pair is not this decision


class CriteriaTests(unittest.TestCase):
    def test_1_a_lost_credible_alert_fails(self):
        ok, lost = card(1), card(2, f3_dec="none", f3_level="match")
        d = data([ok, lost], [sent(ok), sent(lost)])
        c1 = crit(d, 1)
        self.assertFalse(c1.passed)
        self.assertIn("1 perdida de 2", c1.measured)
        self.assertIn("aviso 1002", c1.details[0])

    def test_1_losses_that_were_not_credible_or_not_sent_pass(self):
        no_year = card(1, year=None, f3_dec="none", f3_level="match")
        kavak = card(2, d=12, source="kavak", f3_dec="none", f3_level="match")
        unsent = card(3, f3_dec="none", f3_level="match")
        pending = card(4, would_defer=True)
        d = data([no_year, kavak, unsent, pending], [sent(no_year), sent(kavak), sent(pending)])
        self.assertTrue(crit(d, 1).passed)

    def test_2_a_silent_search_needs_a_reason_for_every_loss(self):
        a1 = card(1, search=10, year=None, f3_dec="none", f3_level="match")
        a2 = card(2, search=10, d=-5, f3_dec="none", f3_level="low")
        b1 = card(3, search=20, f3_dec="none", f3_level="match")
        c1 = card(4, search=30)                   # f3 also alerts: not silent
        d = data([a1, a2, b1, c1], [sent(a1), sent(a2), sent(b1), sent(c1)])
        c2 = crit(d, 2)
        self.assertFalse(c2.passed)
        self.assertEqual(c2.measured, "2 en silencio, 1 aceptada")
        text = "\n".join(c2.details)
        self.assertIn("Búsqueda 10: 2 perdidas · aceptada", text)
        self.assertIn("sin año", text)
        self.assertIn("5,0 % sobre la mediana", text)
        self.assertIn("Búsqueda 20: 1 perdida · **no aceptada**", text)
        self.assertIn("**ninguno aceptado**", text)

    def test_2_reasons(self):
        def reasons(**kw):
            [c] = rep.decisions(data([card(1, f3_dec="none", **kw)], listings={1001: {"status": kw.pop("now", "active")}}))
            return rep.silence_reasons(c)
        self.assertEqual(reasons(price=None), ["sin precio"])
        self.assertEqual(reasons(price=11_111), ["precio de relleno"])
        self.assertEqual(reasons(d=55), ["55,0 % debajo (≥ 50 %)"])
        self.assertEqual(reasons(n=7), ["menos de 10 comparables (n=7)"])
        self.assertEqual(reasons(f3={"fit": {"prefs": {"trim": 0.5}}}), ["otra versión"])
        self.assertEqual(reasons(d=5, source="kavak"), ["4,0 % sobre la mediana"])
        self.assertEqual(reasons(), [])
        [c] = rep.decisions(data([card(1, f3_dec="none")], listings={1001: {"status": "gone"}}))
        self.assertEqual(rep.silence_reasons(c), ["aviso ya vendido o terminado"])

    def test_3_volume_ratios(self):
        def run(f3_alerts: int, f3_fire: int):
            rows = []
            for i in range(10):
                rows.append(card(i + 1, f2_kind="opportunity" if i < 5 else "new_match",
                                 f3_dec="queued" if i < f3_alerts else "none",
                                 f3_kind="opportunity" if i < f3_fire else "new_match"))
            return crit(data(rows), 3)
        self.assertTrue(run(9, 3).passed)          # 0,90 and 3 ≥ 0,6 × 5
        self.assertFalse(run(8, 3).passed)         # 0,80
        self.assertFalse(run(9, 2).passed)         # 🔥 2 < 3
        self.assertIn("alertas 9/10 = 0,90 · 🔥 3/5 = 0,60", run(9, 3).measured)
        self.assertIsNone(crit(data([card(1, f2_dec="none", f2_reason="below_min_level")]), 3).passed)

    def test_3_pending_candidates_are_left_out(self):
        rows = [card(1), card(2, would_defer=True)]
        c3 = crit(data(rows), 3)
        self.assertIn("alertas 1/1", c3.measured)
        self.assertIn("Sin contar 1 candidato", c3.details[1])

    def test_4_no_bad_alert_at_good_or_above(self):
        d = data([card(1, year=None), card(2, f3_level="match", year=None)])
        c4 = crit(d, 4)
        self.assertFalse(c4.passed)
        self.assertEqual(len(c4.details), 1)
        self.assertIn("sin año", c4.details[0])
        self.assertTrue(crit(data([card(1), card(2, d=55, f3_dec="none")]), 4).passed)
        self.assertFalse(crit(data([card(1, d=55)]), 4).passed)
        self.assertFalse(crit(data([card(1, price=11_111)]), 4).passed)

    def test_5_card_against_detail(self):
        a = card(1, enriched=False)
        b = card(2, enriched=False)
        c = card(3, enriched=False)                 # not read yet today: only out of the informative share
        e = card(4, enriched=True)
        rows = [a, later(a, "deferred", f3_dec="none", f3_level="match", f3_decides=False), b, c, e]
        listings = {1001: {"status": "active", "enriched_at": T0}, 1002: {"status": "active", "enriched_at": T0},
                    1003: {"status": "active", "enriched_at": None}, 1004: {"status": "active", "enriched_at": T0}}
        c5 = crit(data(rows, listings=listings), 5)
        self.assertFalse(c5.passed)
        self.assertEqual(c5.measured, "25,0 % (1 de 4)")     # spec §11.4.5: over every fresh decision
        self.assertIn("1 de 2 = 50,0 %", c5.details[2])     # the cards read since: informative
        rows[1]["f3_decision"] = "digest"           # same alert decision, other level only
        c5 = crit(data(rows, listings=listings), 5)
        self.assertTrue(c5.passed)
        self.assertIn("Nivel de f3 distinto entre tarjeta y detalle: 1.", c5.details[1])

    def test_5_is_measured_over_every_fresh_decision(self):
        """100 fresh decisions, 40 unread at the card and read since, 3 changed by the detail: 3 % passes
        (the spec's denominator), although it is 7.5 % of the 40."""
        rows, listings = [], {}
        for m in range(1, 101):
            unread = m <= 40
            row = card(m, enriched=not unread)
            rows.append(row)
            listings[row["listing_id"]] = {"status": "active", "enriched_at": T0}
            if m <= 3:
                rows.append(later(row, "deferred", f3_dec="none", f3_level="match", f3_decides=False))
        c5 = crit(data(rows, listings=listings), 5)
        self.assertTrue(c5.passed)
        self.assertEqual(c5.measured, "3,0 % (3 de 100)")
        self.assertIn("3 de 40 = 7,5 %", c5.details[2])

    def test_6_concentration_lists_without_blocking(self):
        conc = [{"search_id": 7, "cars": 30, "fire": 13}, {"search_id": 8, "cars": 30, "fire": 12},
                {"search_id": 9, "cars": 19, "fire": 19}]
        c6 = crit(data([card(1)], concentration=conc, searches={7: {"name": "Gol"}}), 6)
        self.assertFalse(c6.blocking)
        self.assertEqual(c6.measured, "1 búsqueda para revisar el pool")
        self.assertEqual(c6.details, ["Búsqueda 7 «Gol»: 13 🔥 de 30 autos (43,3 %)"])

    def test_7_clicks_and_outbound_by_f3_level(self):
        a, b, c = card(1), card(2, f3_dec="none", f3_level="match"), card(3)
        out = [{"user_id": "u1", "listing_id": "1002", "created_at": T0 + timedelta(hours=2)}]
        d = data([a, b, c], [sent(a, clicked=True), sent(b)], outbound=out)
        c7 = crit(d, 7)
        self.assertEqual(c7.measured, "2 alertas")
        self.assertIn("| 🟢 buena | 1 | 1 | 0 |", c7.details)
        self.assertIn("| 🟡 coincidencia | 1 | 0 | 1 |", c7.details)


class AlternativeTests(unittest.TestCase):
    def test_the_other_option_of_each_pending_decision(self):
        capped = card(1, f3_dec="none", f3_reason="below_min_level", f3_level="match", f3_level_uncapped="high",
                      f3_seller_capped=True, audience={"min_level": "good"},
                      f3={"seller": {"strict": False}, "alternatives": {"seller_cap_off": {"level": "high", "score": 90}}})
        strict = card(2, f3_dec="none", f3_reason="below_min_level", f3_level="match", f3_level_uncapped="good",
                      f3_seller_capped=True, audience={"min_level": "good"},
                      f3={"seller": {"strict": True}, "alternatives": {"seller_cap_off": {"level": "good", "score": 80}}})
        kavak = card(3, source="kavak", f3_level="good", audience={"min_level": "good"},
                     f3={"alternatives": {"kavak_offset_0": {"level": "high", "score": 88}}})
        deduped = card(4, f3_dec="none", f3_reason="dedupe_existing", f3_level="match", audience={"min_level": "good"},
                       f3={"alternatives": {"placeholder_off": {"level": "good", "score": 75}}})
        alts = {a.key: a for a in rep.alternatives(rep.decisions(data([capped, strict, kavak, deduped])))}
        off = alts["seller_cap_off"]
        self.assertEqual((off.applies, off.level_changes, off.alerts, off.fire), (2, 2, 3, 1))
        good = alts["seller_cap_good"]
        self.assertEqual((good.applies, good.alerts, good.fire), (2, 3, 0))
        pro = alts["seller_cap_pro_only"]          # the strict search keeps its cap
        self.assertEqual((pro.applies, pro.level_changes, pro.alerts), (2, 1, 2))
        k = alts["kavak_offset_0"]
        self.assertEqual((k.applies, k.alerts, k.fire), (1, 1, 1))
        # A level-independent drop stays a drop with another level.
        p = alts["placeholder_off"]
        self.assertEqual((p.applies, p.level_changes, p.alerts), (1, 1, 1))
        self.assertEqual(alts["agency_voice_off"].applies, 0)

    def test_rendered_only_when_some_option_applies(self):
        kavak = card(1, source="kavak", audience={"min_level": "good"},
                     f3={"alternatives": {"kavak_offset_0": {"level": "high", "score": 88}}})
        text = rep.render(data([kavak]), now=T0)
        self.assertIn("### Decisiones pendientes (§14): la otra opción", text)
        self.assertIn("| Kavak sin el −9 (decisión 4c) | 1 | 1 | 1 → 1 | 0 → 1 |", text)
        self.assertNotIn("Decisiones pendientes", rep.render(data([card(1)]), now=T0))


class RenderTests(unittest.TestCase):
    def rows(self):
        a = card(1, search=5, f2_kind="opportunity", f3_kind="opportunity", f3_level="high")
        b = card(2, search=5, f3_dec="none", f3_level="match", f3_seller_capped=True, f3_level_uncapped="good",
                 agency_voice="recibimos tu usado", at=T0 + timedelta(days=2), f3_params="bbbbbbbbbbbb")
        k = card(3, search=6, source="kavak", d=20, f2_dec="digest", f2_reason="daily_cap")
        return [a, b, k], [sent(a), sent(b), sent(k, status="digest")]

    def test_render_in_spanish(self):
        rows, notes = self.rows()
        text = rep.render(data(rows, notes, searches={5: {"name": "Corsa"}}, since=T0, until=T0 + timedelta(days=7)),
                          now=T0 + timedelta(days=7))
        for heading in ("# Modo sombra f3 · «precio × encaje»", "## Criterios para pasar a real (spec §11.4)",
                        "## Por búsqueda", "## Detalle", "### Degradadas por el tope diario (f2) (1)",
                        "### Tope de vendedor y voz de agencia (f3) (1)", "### Kavak"):
            self.assertIn(heading, text)
        self.assertIn("Período: desde 2026-11-12 hasta 2026-11-19 (días de Argentina).", text)
        self.assertIn("| 5 | Corsa | 2 | 2 → 1 | 1 → 1 | 1 | 0 | 0 | 0 |", text)
        self.assertIn("voz de agencia: «recibimos tu usado»", text)
        self.assertIn("tope de vendedor: good → match", text)
        self.assertIn("| 1 | Ninguna búsqueda pierde una alerta que f2 envió y que era creíble al decidir | "
                      "1 perdida de 3 creíbles enviadas | ❌ |", text)
        self.assertIn("ℹ️ no bloquea", text)
        # The f3 parameters moved during the period.
        self.assertIn("⚠️ Se movió un parámetro el 2026-11-14 12:00 (aaaaaaaaaaaa → bbbbbbbbbbbb)", text)
        self.assertIn("`--params bbbbbbbbbbbb`", text)

    def test_cards_the_broader_defer_rule_would_hold(self):
        """would_defer is FB/ML only (§4.1); other sources' seller-less cards are listed for the broader rule."""
        wide = card(1, source="deruedas", f3={"fit": {"prefs": {}}, "would_defer_any_source": True})
        fb = card(2, source="facebook", would_defer=True,
                  f3={"fit": {"prefs": {}}, "would_defer": True, "would_defer_any_source": True})
        old = card(3, f3={"fit": {"prefs": {}}})                     # logged before the key existed
        text = rep.render(data([wide, fb, old]), now=T0)
        self.assertIn("### Esperarían el detalle con la regla amplia (otras fuentes) (1)", text)
        self.assertIn("### Pendientes (f3 espera el detalle) (1)", text)

    def test_per_search(self):
        rows, notes = self.rows()
        [s5, s6] = rep.per_search(data(rows, notes))
        self.assertEqual((s5.search_id, s5.candidates, s5.f2_alerts, s5.f3_alerts, s5.f2_fire, s5.f3_fire,
                          s5.lost_credible, s5.gained), (5, 2, 2, 1, 1, 1, 1, 0))
        self.assertEqual((s6.f2_alerts, s6.f3_alerts), (1, 1))

    def test_empty_period(self):
        text = rep.render(data([]), now=T0)
        self.assertIn("Todavía no hay decisiones frescas registradas en el período.", text)

    def test_params_changes(self):
        a = card(1, f3_params="p1")
        b = card(2, f3_params=None, at=T0 + timedelta(hours=1))
        c = card(3, f3_params="p2", at=T0 + timedelta(hours=2))
        self.assertEqual(rep.params_changes(data([a, b, c])), [(T0 + timedelta(hours=2), "p1", "p2")])


class MainTests(unittest.IsolatedAsyncioTestCase):
    async def test_missing_table(self):
        out = io.StringIO()
        with patch("tools.shadow_report.db.open_pool", AsyncMock()), \
                patch("tools.shadow_report.db.close_pool", AsyncMock()), \
                patch("tools.shadow_report.read", AsyncMock(return_value=None)) as read, redirect_stdout(out):
            self.assertEqual(await rep.main(["--since", "2026-11-01", "--search", "5", "6"]), 0)
        self.assertEqual(out.getvalue(), rep.MISSING_TABLE + "\n")
        kw = read.await_args.kwargs
        self.assertEqual(kw["since"], datetime(2026, 11, 1, 3, 0, tzinfo=timezone.utc))
        self.assertEqual(kw["searches"], [5, 6])
        self.assertIsNone(kw["params"])

    async def test_writes_the_file(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sombra.md"
            out = io.StringIO()
            with patch("tools.shadow_report.db.open_pool", AsyncMock()), \
                    patch("tools.shadow_report.db.close_pool", AsyncMock()), \
                    patch("tools.shadow_report.read", AsyncMock(return_value=data([card(1)]))), redirect_stdout(out):
                await rep.main(["--out", str(path)])
            self.assertIn("## Criterios para pasar a real", path.read_text(encoding="utf-8"))
            self.assertIn("Informe escrito en", out.getvalue())

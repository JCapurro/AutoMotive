"""Agencias (spec §4.3, C1 and C4): a dealer's car is matched and scored with
the same algorithm as any listing, and never reaches a private-only search."""
from __future__ import annotations

import unittest
from datetime import timedelta

from intelligence import copy
from intelligence.config import dealer_program
from intelligence.engine import evaluate
from intelligence.matching import evaluate as filters, match
from pipeline.scoring import Scorer

from test_intelligence import CFG, FX, MARKET, NOW, fiesta_listing, fiesta_profile

ON = dealer_program({"enabled": True, "channel_enabled": True})


def dealer_car(**kw) -> dict:
    row = fiesta_listing(seller_type="dealer", **kw)
    row.update(dealer_id=4, dealer_status="available", dealer_confirmed_at=NOW - timedelta(days=1),
               dealer_approved=True, dealer_active=True, dealer_name="TT Autos")
    return row


def profile(*, seller_types=None, plan_flag=False):
    p = fiesta_profile(**({"seller_types": seller_types} if seller_types is not None else {}))
    p["seller_filter"] = plan_flag
    return p


class PrivateOnlyTests(unittest.TestCase):
    """C4: filters.seller_types = ['private'] never gets a car with dealer_id, Free or Pro."""

    def test_private_only_fails_for_any_plan(self):
        for flag in (False, True):
            for source in ("directo", "mercadolibre"):
                with self.subTest(pro=flag, source=source):
                    row = dealer_car(source=source)
                    self.assertIsNone(match(row, profile(seller_types=["private"], plan_flag=flag), fx_rate=FX))
                    r = filters(row, profile(seller_types=["private"], plan_flag=flag), fx_rate=FX).reasons["seller"]
                    self.assertEqual((r.result, r.hard), ("fail", True))
                    self.assertEqual(r.detail, "auto de agencia, se busca solo particulares")
                    self.assertIsNone(evaluate(row, profile(seller_types=["private"], plan_flag=flag),
                                               price_ref=MARKET, cfg=CFG, now=NOW, fx_rate=FX))

    def test_even_a_private_seller_type_fails_with_dealer_id(self):
        row = dealer_car()
        row["seller_type"] = "private"
        self.assertIsNone(match(row, profile(seller_types=["private"]), fx_rate=FX))

    def test_dealer_or_empty_seller_types_pass(self):
        for types in (["dealer"], [], None, ["private", "dealer"]):
            for flag in (False, True):
                with self.subTest(types=types, pro=flag):
                    self.assertIsNotNone(match(dealer_car(), profile(seller_types=types, plan_flag=flag),
                                               fx_rate=FX))

    def test_without_dealer_id_nothing_changes(self):
        """A private-only search and an ordinary dealer listing: what PRO-01 did before."""
        for flag in (False, True):
            row = fiesta_listing(seller_type="dealer")
            before = filters(row, profile(seller_types=["private"], plan_flag=flag), fx_rate=FX)
            seller = before.reasons.get("seller")
            if flag:
                self.assertEqual(seller.detail, "vendedor concesionaria, se busca solo particulares")
            else:
                self.assertIsNone(seller)          # Free: a soft preference, not the hard check

    def test_copy(self):
        self.assertEqual(copy.DEALER_LABEL, "Promocionado")
        self.assertIn("{wanted}", copy.REASON["seller_dealer_stock"])


class NeutralityTests(unittest.TestCase):
    """C1: the same listing with and without dealer_id (gate open) scores the same."""

    def test_same_score_level_and_breakdown(self):
        for types in (None, ["dealer"]):
            with self.subTest(types=types):
                plain = fiesta_listing(seller_type="dealer")
                mine = dealer_car()
                a = evaluate(plain, profile(seller_types=types), price_ref=MARKET, cfg=CFG, now=NOW, fx_rate=FX)
                b = evaluate(mine, profile(seller_types=types), price_ref=MARKET, cfg=CFG, now=NOW, fx_rate=FX)
                self.assertIsNotNone(a)
                self.assertEqual((a.score.score, a.level), (b.score.score, b.level))
                self.assertEqual(a.row()["score_breakdown"], b.row()["score_breakdown"])
                self.assertEqual(a.row()["match_reasons"], b.row()["match_reasons"])


def scorer(rows: dict, program) -> Scorer:
    s = Scorer(CFG, FX, NOW, program=program)
    s.rows.update(rows)
    s.refs.update({k: MARKET for k in rows})
    return s


class ScorerGateTests(unittest.TestCase):
    def test_evaluate_returns_none_for_every_hidden_reason(self):
        cases = {
            "no_dealer": (dict(source="directo", dealer_id=None), ON),
            "channel_off": (dict(source="directo"), dealer_program(None)),
            "not_approved": (dict(source="directo", dealer_approved=False), ON),
            "not_available": (dict(source="directo", dealer_status="reserved"), ON),
            "unconfirmed": (dict(source="directo", dealer_confirmed_at=NOW - timedelta(days=8)), ON),
            "synced sold": (dict(source="mercadolibre", dealer_status="sold"), dealer_program(None)),
        }
        for name, (change, program) in cases.items():
            with self.subTest(name):
                row = dealer_car()
                row.update(change)
                self.assertIsNone(scorer({1: row}, program).evaluate(1, profile()))

    def test_visible_dealer_car_scores_like_the_same_listing(self):
        visible = scorer({1: dealer_car(source="directo")}, ON).evaluate(1, profile())
        plain = scorer({1: fiesta_listing(seller_type="dealer")}, dealer_program(None)).evaluate(1, profile())
        self.assertIsNotNone(visible)
        self.assertEqual((visible.score.score, visible.level), (plain.score.score, plain.level))

    def test_default_program_lets_ordinary_listings_through(self):
        s = Scorer(CFG, FX, NOW)
        s.rows[1] = fiesta_listing()
        s.refs[1] = MARKET
        self.assertIsNotNone(s.evaluate(1, profile()))
        self.assertFalse(s.program["channel"])


if __name__ == "__main__":
    unittest.main()

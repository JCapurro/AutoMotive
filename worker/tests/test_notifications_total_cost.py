"""PAR-01: the total cost estimate in the opportunity alert
(docs/superpowers/specs/2026-10-30-par01-costo-total-design.md, «Email de oportunidad»).
The payload keeps the rounded totals (service.total_cost_payload); the
template only formats them (templates.total_cost_line)."""
from __future__ import annotations

import json
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

from intelligence import copy
from intelligence import cost_estimator
from normalization.normalize import normalize_text
from notification_fixtures import (LINKS, NOW, OPPORTUNITY, OPPORTUNITY_TOTAL_COST, OPPORTUNITY_TOTAL_COST_NO_CONFIG,
                                   TOTAL_COST_CABA, TOTAL_COST_NO_ZONE, notification)
from notifications import service, templates

GOLDEN = json.loads((Path(__file__).parent / "fixtures" / "cost_estimator" / "golden.json").read_text(encoding="utf-8"))
CFG = cost_estimator.parse_config(GOLDEN["config"])
PALERMO = {"origin_lat": -34.5875, "origin_lon": -58.42, "location_label": "Palermo, CABA", "extra_locations": None}


class TotalCostLineTests(unittest.TestCase):
    def test_nothing_without_the_key(self):
        for cost in (None, {}):
            self.assertIsNone(templates.total_cost_line(cost))

    def test_the_line_with_the_parameters_date(self):
        self.assertEqual(templates.total_cost_line(TOTAL_COST_CABA),
                         "Costo total estimado: USD 16.290 – 16.560 (ARS 21.188.000 – 21.518.000). Parámetros al 30/10.")

    def test_missing_terms_use_missing_suffix(self):
        cases = {("patente",): "Costo total estimado (sin patente): USD 16.290 – 16.560 (ARS 21.188.000 – 21.518.000). Parámetros al 30/10.",
                 ("sellos", "patente"): "Costo total estimado (sin sellos ni patente): USD 16.290 – 16.560 (ARS 21.188.000 – 21.518.000). Parámetros al 30/10.",
                 ("formularios",): "Costo total estimado (sin formularios): USD 16.290 – 16.560 (ARS 21.188.000 – 21.518.000). Parámetros al 30/10."}
        for codes, line in cases.items():
            with self.subTest(codes):
                self.assertEqual(templates.total_cost_line({**TOTAL_COST_CABA, "missing": list(codes)}), line)
        self.assertEqual(templates.total_cost_line(TOTAL_COST_NO_ZONE),
                         "Costo total estimado (sin sellos ni patente): USD 15.540 – 15.560 (ARS 20.208.000 – 20.219.000). Parámetros al 30/10.")

    def test_without_the_dollar(self):
        ars = {**TOTAL_COST_CABA, "usd_min": None, "usd_max": None, "missing": ["fx"]}
        self.assertEqual(templates.total_cost_line(ars),
                         "Costo total estimado: ARS 21.188.000 – 21.518.000 (sin dólar del día). Parámetros al 30/10.")
        usd = {"ars_min": None, "ars_max": None, "usd_min": None, "usd_max": None, "missing": ["fx"],
               "jurisdiction": ["caba"], "as_of": "2026-10-30"}
        self.assertEqual(templates.total_cost_line(usd), "Costo total estimado: sin dólar del día, no se puede estimar.")

    def test_copy_has_no_forbidden_or_absolute_wording(self):
        texts = [templates.total_cost_line(TOTAL_COST_CABA), templates.total_cost_line(TOTAL_COST_NO_ZONE),
                 copy.TOTAL_COST["email"], copy.TOTAL_COST["email_no_fx"]]
        for text in texts:
            folded = normalize_text(text)
            for term in (*copy.FORBIDDEN_TERMS, "precio final", "costo real", "costo exacto", "total real"):
                with self.subTest(text=text, term=term):
                    self.assertNotIn(normalize_text(term), folded)
        for text in texts[:2]:
            self.assertIn("estimado", text)


class OpportunityEmailTests(unittest.TestCase):
    def test_the_line_goes_after_the_drops_on_every_channel(self):
        n = notification("opportunity", {**OPPORTUNITY_TOTAL_COST.payload,
                                         "price_track": {"drops": 1, "cum_pct": 6.3, "cum_usd": 1500.0, "currency": "USD"}})
        lines = templates.email(n, LINKS, NOW).text.splitlines()
        i = lines.index("Bajó 1 vez desde que la vimos: -USD 1.500 (-6,3%).")
        self.assertEqual(lines[i + 1], templates.total_cost_line(TOTAL_COST_CABA))
        self.assertIn("Costo total estimado", templates.email(n, LINKS, NOW).html)
        self.assertIn("Costo total estimado", templates.telegram(n, LINKS, NOW).text)
        self.assertIn("Costo total estimado", "\n".join(templates.content(n, LINKS, NOW).lines))

    def test_an_old_payload_renders_as_before(self):
        n = notification("opportunity", {**OPPORTUNITY.payload, "total_cost": None})
        for render in (templates.email, templates.telegram):
            self.assertEqual(render(n, LINKS, NOW), render(OPPORTUNITY, LINKS, NOW))
            self.assertEqual(render(OPPORTUNITY_TOTAL_COST_NO_CONFIG, LINKS, NOW), render(OPPORTUNITY, LINKS, NOW))

    def test_new_match_ignores_it(self):
        base = notification("new_match", {"listing": OPPORTUNITY.payload["listing"], "match": {"score": 74, "level": "good"}})
        n = notification("new_match", {**base.payload, "total_cost": TOTAL_COST_CABA})
        self.assertEqual(templates.email(n, LINKS, NOW), templates.email(base, LINKS, NOW))


def listing(listing_id, **kw):
    """A rows_for_scoring() row: golden case 1's listing."""
    return {"id": listing_id, "title": "Toyota Corolla XEI 2017", "make": "Toyota", "model": "Corolla", "trim": "XEI",
            "year": 2017, "mileage_km": 90000, "price": 20000000.0, "currency": "ARS", "price_usd": 15384.62,
            "url": "https://example.test/c", "source": "mercadolibre", "transmission": "manual", "price_partial": False,
            "timing_belt": False, "description": "x" * 200, "description_facts": {}, "seller_type": "private",
            "dealer_inferred": False, "body_type": "sedan", **kw}


def cand(listing_id, profile_id=7, level="high", repost=False):
    return service.MatchCandidate(profile_id=profile_id, listing_id=listing_id, match_id=listing_id, repost=repost,
                                  evaluation={"level": level, "score": 88, "price_ref": None, "red_flags": []})


class OnMatchesTotalCostTests(unittest.IsolatedAsyncioTestCase):
    async def payloads(self, candidates, rows, audiences, *, cfg=CFG, fx=None):
        notifier = service.Notifier({})
        base = {"user_id": "u1", "profile_name": "Corolla", "channels": ["email"], "email": "a@b.test"}
        audiences = {pid: {**base, "profile_id": pid, **a} for pid, a in audiences.items()}
        with patch.object(service.repo, "profile_audiences", AsyncMock(return_value=audiences)), \
             patch.object(service.repo, "interactions", AsyncMock(return_value={})), \
             patch.object(service.repo, "price_tracks", AsyncMock(return_value={})), \
             patch.object(service, "_min_n", AsyncMock(return_value=5)), \
             patch.object(service, "_cost_config", AsyncMock(return_value=cfg)) as config, \
             patch.object(service, "_latest_fx", AsyncMock(return_value=fx)) as latest_fx, \
             patch.object(notifier, "_commit", AsyncMock(return_value=[])) as commit:
            await notifier.on_matches(candidates, rows, now=NOW)
        events = commit.await_args.args[0]
        return {(e.audience.profile_id, e.listing_id): e.payload for e in events}, config, latest_fx

    async def test_without_the_flag_no_key_and_no_reads(self):
        payloads, config, fx = await self.payloads([cand(501)], {501: listing(501)}, {7: {**PALERMO, "total_cost": False}})
        self.assertNotIn("total_cost", payloads[(7, 501)])
        config.assert_not_awaited()
        fx.assert_not_awaited()

    async def test_with_the_flag_only_opportunities_carry_it(self):
        payloads, config, fx = await self.payloads(
            [cand(501), cand(502, level="good"), cand(503, repost=True)],
            {i: listing(i) for i in (501, 502, 503)}, {7: {**PALERMO, "total_cost": True}})
        self.assertEqual(payloads[(7, 501)]["total_cost"], TOTAL_COST_CABA)
        self.assertNotIn("total_cost", payloads[(7, 502)])
        self.assertNotIn("total_cost", payloads[(7, 503)])
        config.assert_awaited_once()
        fx.assert_not_awaited()                                  # ARS listings: their own dollar

    async def test_each_search_its_own_jurisdiction(self):
        cordoba = {"label": "Córdoba", "lat": -31.4201, "lon": -64.1888, "radius_km": 40}
        payloads, _, _ = await self.payloads(
            [cand(501, profile_id=7), cand(501, profile_id=8), cand(501, profile_id=9)], {501: listing(501)},
            {7: {**PALERMO, "total_cost": True},
             8: {**PALERMO, "extra_locations": [cordoba], "total_cost": True},
             9: {"origin_lat": None, "origin_lon": None, "location_label": None, "extra_locations": None, "total_cost": True}})
        self.assertEqual(payloads[(7, 501)]["total_cost"]["jurisdiction"], ["caba"])
        self.assertEqual(payloads[(8, 501)]["total_cost"]["jurisdiction"], ["caba", "rest"])
        # golden case 28: 20.527.000 – 21.517.532,5
        self.assertEqual((payloads[(8, 501)]["total_cost"]["ars_min"], payloads[(8, 501)]["total_cost"]["ars_max"]),
                         (20527000, 21518000))
        self.assertEqual(payloads[(9, 501)]["total_cost"], TOTAL_COST_NO_ZONE)

    async def test_without_parameters_no_key_and_the_email_as_before(self):
        # The backlog's «sin parámetros cargados»: no cost_estimator, or one without a valid as_of.
        for cfg in (None, cost_estimator.parse_config({**GOLDEN["config"], "as_of": "30/10/2026"})):
            with self.subTest(cfg=cfg):
                payloads, _, fx = await self.payloads([cand(501)], {501: listing(501)}, {7: {**PALERMO, "total_cost": True}},
                                                      cfg=cfg)
                self.assertNotIn("total_cost", payloads[(7, 501)])
                fx.assert_not_awaited()
                n = notification("opportunity", payloads[(7, 501)])
                self.assertNotIn("Costo total", templates.email(n, LINKS, NOW).text)

    async def test_a_partial_price_gets_no_estimate(self):
        rows = {501: listing(501, price_partial=True),
                502: listing(502, description_facts={"price_check": {"published_partial": True}})}
        payloads, _, _ = await self.payloads([cand(501), cand(502)], rows, {7: {**PALERMO, "total_cost": True}})
        self.assertNotIn("total_cost", payloads[(7, 501)])
        self.assertNotIn("total_cost", payloads[(7, 502)])

    async def test_a_usd_listing_with_a_stale_quote_says_so_never_the_fallback(self):
        usd = listing(501, price=15000.0, currency="USD", price_usd=15000.0)
        # NOW is 2026-09-27: 2026-09-23 is 4 days old (fx.max_age_days = 3).
        stale = {"rate": 1300.0, "kind": "blue", "date": "2026-09-23"}
        payloads, _, fx = await self.payloads([cand(501), cand(502)], {501: usd, 502: {**usd, "id": 502}},
                                              {7: {**PALERMO, "total_cost": True}}, fx=stale)
        fx.assert_awaited_once()                                 # once for the batch
        self.assertEqual(payloads[(7, 501)]["total_cost"],
                         {"ars_min": None, "ars_max": None, "usd_min": None, "usd_max": None, "missing": ["fx"],
                          "jurisdiction": ["caba"], "as_of": "2026-10-30"})
        fresh = {**stale, "date": "2026-09-26"}
        payloads, _, _ = await self.payloads([cand(501)], {501: usd}, {7: {**PALERMO, "total_cost": True}}, fx=fresh)
        # golden case 7: P = 15.000 x 1.300
        self.assertEqual(payloads[(7, 501)]["total_cost"]["ars_min"], 20654000)
        self.assertEqual(payloads[(7, 501)]["total_cost"]["usd_max"], 16140)

    def test_now_is_argentina_s_day(self):
        self.assertEqual(NOW.tzinfo, timezone.utc)
        late = datetime(2026, 9, 27, 2, 0, tzinfo=timezone.utc)      # still the 26th in Buenos Aires
        p = service.total_cost_payload(listing(501, price=15000.0, currency="USD", price_usd=15000.0),
                                       {**PALERMO}, CFG, {"rate": 1300.0, "kind": "blue", "date": "2026-09-23"}, late)
        self.assertEqual(p["ars_min"], 20654000)


if __name__ == "__main__":
    unittest.main()

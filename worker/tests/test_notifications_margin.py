"""PRO-02 in the alerts: the threshold in USD (notifications/engine.py), the
margin payload only with the plan's dealer_margin (service.margin_payload)
and the margin line of the Pro emails (templates.margin_line; snapshots
opportunity_margin, opportunity_margin_no_zone and price_drop_margin in
test_notifications_templates.py)."""
from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

from intelligence import copy
from notification_fixtures import (LINKS, MARGIN_CABA, MARGIN_NO_ZONE, NOW, OPPORTUNITY, OPPORTUNITY_MARGIN,
                                   PRICE_DROP, PRICE_DROP_MARGIN, notification)
from notifications import service, templates
from notifications.engine import MATCH, PRICE_DROP as DROP, Audience, Event, Rules, decide, decide_all
from test_margin import MarginCopyLint, compute

RULES = Rules(alerts_max_per_user_day=10, price_drop_min_pct=3)


def pro(pct=None, usd=None, **kw) -> Audience:
    return Audience("u1", ("web",), kw.get("frequency", "immediate"), kw.get("min_level", "good"),
                    kw.get("profile_id", 1), pct, usd)


def event(level="high", *, audience, diff=None, usd_min=None, usd_low=None, listing=10, kind=MATCH, **kw) -> Event:
    payload = {"match": {"score": 80, "level": level, "diff_pct": diff}}
    if usd_min is not None:
        payload["margin"] = {**MARGIN_CABA, "usd_min": usd_min, "usd_low": usd_min if usd_low is None else usd_low}
    extra = {"snapshot_id": 7, "drop_pct": 6} if kind == DROP else {}
    return Event(kind, listing, audience, level=level, score=80, match_id=100 + listing, payload=payload,
                 **extra, **kw)


def kinds(decisions):
    return sorted({(d.kind, d.status) for d in decisions})


class UsdThresholdTests(unittest.TestCase):
    def test_reaching_it_is_immediate_without_the_cap_and_not_counted(self):
        events = [event(audience=pro(usd=500), usd_min=500 + i, listing=i) for i in range(60)]
        out = decide_all(events, RULES, caps={"u1": 50}, sent_today={"u1": 50})
        self.assertEqual(len(out), 60)
        self.assertEqual({d.status for d in out}, {"queued"})
        self.assertEqual({d.payload["threshold_usd"] for d in out}, {500})
        self.assertNotIn("threshold_pct", out[0].payload)
        self.assertNotIn("degraded", out[0].payload)

    def test_threshold_alerts_do_not_use_up_the_cap_of_the_other_searches(self):
        usd = [event(audience=pro(usd=500, profile_id=1), usd_min=900, listing=i) for i in range(1, 61)]
        plain = [event(audience=Audience("u1", ("web",), "immediate", "good", 2), listing=i) for i in range(100, 160)]
        out = decide_all(usd + plain, RULES, caps={"u1": 50})
        queued = [d for d in out if d.status == "queued"]
        self.assertEqual(len([d for d in queued if d.profile_id == 1]), 60)
        self.assertEqual(len([d for d in queued if d.profile_id == 2]), 50)

    def test_below_it_or_without_a_margin_goes_to_the_digest(self):
        for e in (event(audience=pro(usd=500), usd_min=490), event(audience=pro(usd=500))):
            with self.subTest(e=e.payload):
                out = decide(e, RULES)
                self.assertEqual(kinds(out), [("opportunity", "digest")])
                self.assertNotIn("threshold_usd", out[0].payload)

    def test_the_low_end_of_the_range_decides(self):
        e = event(audience=pro(usd=1220), usd_min=1210)            # usd_max 1230 would reach it
        self.assertEqual(kinds(decide(e, RULES)), [("opportunity", "digest")])

    def test_the_unrounded_low_end_decides_not_the_shown_one(self):
        e = event(audience=pro(usd=500), usd_min=500, usd_low=495.0)   # shown as USD 500
        self.assertEqual(kinds(decide(e, RULES)), [("opportunity", "digest")])

    def test_reaching_it_alerts_even_below_the_minimum_level(self):
        e = event("match", audience=pro(usd=500, min_level="high"), usd_min=800)
        self.assertEqual(kinds(decide(e, RULES)), [("new_match", "queued")])
        self.assertEqual(decide(event("match", audience=pro(usd=500, min_level="high"), usd_min=100), RULES), [])

    def test_either_threshold_is_enough(self):
        both = pro(pct=10, usd=500)
        by_pct = decide(event(audience=both, diff=15, usd_min=100), RULES)
        self.assertEqual(kinds(by_pct), [("opportunity", "queued")])
        self.assertEqual((by_pct[0].payload.get("threshold_pct"), by_pct[0].payload.get("threshold_usd")), (10, None))
        by_usd = decide(event(audience=both, diff=2, usd_min=900), RULES)
        self.assertEqual((by_usd[0].payload.get("threshold_pct"), by_usd[0].payload.get("threshold_usd")), (None, 500))
        by_both = decide(event(audience=both, diff=15, usd_min=900), RULES)
        self.assertEqual((by_both[0].payload["threshold_pct"], by_both[0].payload["threshold_usd"]), (10, 500))
        self.assertEqual(kinds(decide(event(audience=both, diff=2, usd_min=100), RULES)), [("opportunity", "digest")])

    def test_price_drops_follow_it_and_saved_ones_stay_immediate(self):
        a = pro(usd=500)
        self.assertEqual(kinds(decide(event("good", audience=a, usd_min=700, kind=DROP), RULES, sent_today=99, cap=50)),
                         [("price_drop", "queued")])
        self.assertEqual(kinds(decide(event("good", audience=a, usd_min=100, kind=DROP), RULES)), [("price_drop", "digest")])
        self.assertEqual(kinds(decide(event("good", audience=a, usd_min=100, kind=DROP, saved=True), RULES)),
                         [("price_drop", "queued")])

    def test_without_a_threshold_nothing_changes(self):
        out = decide(event(audience=pro(), usd_min=5000), RULES)
        self.assertEqual(kinds(out), [("opportunity", "queued")])
        self.assertNotIn("threshold_usd", out[0].payload)


def listing(listing_id, **kw):
    return {"id": listing_id, "title": "Toyota Corolla XEI 2017", "make": "Toyota", "model": "Corolla", "trim": "XEI",
            "year": 2017, "mileage_km": 90000, "price": 20000000.0, "currency": "ARS", "price_usd": 15384.62,
            "url": "https://example.test/c", "source": "mercadolibre", "transmission": "manual", "price_partial": False,
            "timing_belt": False, "description": "x" * 200, "description_facts": {}, "seller_type": "private",
            "dealer_inferred": False, "body_type": "sedan", **kw}


class PayloadGatingTests(unittest.IsolatedAsyncioTestCase):
    async def payloads(self, audience_extra, *, level="high"):
        notifier = service.Notifier({})
        a = {"user_id": "u1", "profile_id": 7, "profile_name": "Corolla", "channels": ["email"], "email": "a@b.test",
             **audience_extra}
        cand = service.MatchCandidate(profile_id=7, listing_id=501, match_id=501,
                                      evaluation={"level": level, "score": 88, "price_ref": None, "red_flags": [],
                                                  "margin_ref": compute()})
        with patch.object(service.repo, "profile_audiences", AsyncMock(return_value={7: a})), \
             patch.object(service.repo, "interactions", AsyncMock(return_value={})), \
             patch.object(service.repo, "price_tracks", AsyncMock(return_value={})), \
             patch.object(service, "_min_n", AsyncMock(return_value=5)), \
             patch.object(service, "_cost_config", AsyncMock(return_value=None)), \
             patch.object(notifier, "_commit", AsyncMock(return_value=[])) as commit:
            await notifier.on_matches([cand], {501: listing(501)}, now=NOW)
        [e] = commit.await_args.args[0]
        return e

    async def test_only_with_dealer_margin(self):
        e = await self.payloads({"dealer_margin": True, "threshold_usd": 500})
        self.assertEqual(e.payload["margin"], {**MARGIN_CABA, "usd_low": 1216.27})
        self.assertEqual(e.audience.threshold_usd, 500)
        for extra in ({"dealer_margin": False}, {}):
            with self.subTest(extra=extra):
                self.assertNotIn("margin", (await self.payloads(extra)).payload)

    async def test_new_matches_carry_it_too(self):
        e = await self.payloads({"dealer_margin": True}, level="good")
        self.assertEqual(e.payload["margin"]["usd_min"], 1210)

    def test_margin_payload(self):
        self.assertIsNone(service.margin_payload(None, {"dealer_margin": True}))
        self.assertIsNone(service.margin_payload(compute(), {"dealer_margin": False}))
        self.assertEqual(service.margin_payload(compute(), {"dealer_margin": True}), {**MARGIN_CABA, "usd_low": 1216.27})

    def test_the_threshold_compares_the_unrounded_low_end(self):
        """A single USD 495 (no transfer subtracted) shows as USD 500 but does
        not reach a USD 500 threshold; USD 500.00 does."""
        for low, reached in ((495.0, False), (499.99, False), (500.0, True)):
            ref = {**compute(), "gross_margin_usd": {"min": low, "max": low}}
            p = service.margin_payload(ref, {"dealer_margin": True})
            with self.subTest(low=low):
                self.assertEqual((p["usd_min"], p["usd_max"], p["usd_low"]), (500, 500, low))
                e = Event(MATCH, 10, pro(usd=500), level="high", score=80, match_id=110,
                          payload={"match": {"score": 80, "level": "high", "diff_pct": None}, "margin": p})
                out = decide(e, RULES)
                self.assertEqual(kinds(out), [("opportunity", "queued" if reached else "digest")])
                self.assertEqual(out[0].payload.get("threshold_usd"), 500 if reached else None)

    def test_a_payload_without_usd_low_does_not_reach_it(self):
        payload = {"match": {"score": 80, "level": "high", "diff_pct": None},
                   "margin": {k: v for k, v in MARGIN_CABA.items()}}
        e = Event(MATCH, 10, pro(usd=500), level="high", score=80, match_id=110, payload=payload)
        self.assertEqual(kinds(decide(e, RULES)), [("opportunity", "digest")])


class MarginLineTests(unittest.TestCase):
    def test_nothing_without_the_key(self):
        for m in (None, {}, {"usd_min": 1}):
            self.assertIsNone(templates.margin_line(m))

    def test_the_line(self):
        self.assertEqual(templates.margin_line(MARGIN_CABA),
                         "Margen bruto estimado: USD 1.210 a 1.230 (contra la mediana de USD 18.000 a la que publican "
                         "las agencias este modelo, n = 6; descuenta acondicionamiento del 5 % y transferencia; "
                         "sin impuestos). Parámetros al 30/10.")
        self.assertIn("no descuenta la transferencia porque tu búsqueda no tiene localidad",
                      templates.margin_line(MARGIN_NO_ZONE))

    def test_every_channel_and_kind(self):
        line = templates.margin_line(MARGIN_CABA)
        for n in (OPPORTUNITY_MARGIN, PRICE_DROP_MARGIN,
                  notification("new_match", {"listing": OPPORTUNITY.payload["listing"],
                                             "match": {"score": 74, "level": "good"}, "margin": MARGIN_CABA})):
            with self.subTest(kind=n.kind):
                self.assertIn(line, templates.email(n, LINKS, NOW).text.splitlines())
                self.assertIn("Margen bruto estimado", templates.email(n, LINKS, NOW).html)
                self.assertIn("Margen bruto estimado", templates.telegram(n, LINKS, NOW).text)

    def test_an_old_payload_renders_as_before(self):
        for base in (OPPORTUNITY, PRICE_DROP):
            n = notification(base.kind, {**base.payload, "margin": None})
            self.assertEqual(templates.email(n, LINKS, NOW), templates.email(base, LINKS, NOW))

    def test_the_rendered_copy_is_prudent(self):
        for m in (MARGIN_CABA, MARGIN_NO_ZONE, {**MARGIN_CABA, "reconditioning_pct": None, "transfer_status": "no_fx"}):
            with self.subTest(m=m):
                self.assertEqual(MarginCopyLint.offenders(templates.margin_line(m)), [])
        self.assertEqual(MarginCopyLint.offenders(copy.MARGIN["email"]), [])


if __name__ == "__main__":
    unittest.main()

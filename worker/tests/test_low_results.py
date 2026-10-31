"""Bot de pocos resultados: the funnel, the hints, the LLM fallback and the notice
(intelligence/low_results.py, pipeline/low_results.py, notifications/low_results.py)."""
from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from intelligence import low_results as lr
from llm.provider import LLMError
from llm.schemas import LowResultsExplanation
from notifications import low_results as notice
from notifications.links import Links
from pipeline import low_results as job

NOW = datetime(2026, 10, 30, 12, tzinfo=timezone.utc)


def listing(year: int, *, price: float = 10_000, km: int = 80_000, source: str = "mercadolibre",
            transmission: str = "manual") -> dict:
    return {"make": "Ford", "model": "Focus", "year": year, "price": price, "currency": "USD",
            "price_usd": price, "mileage_km": km, "source": source, "transmission": transmission}


def profile(**filters) -> dict:
    return {"id": 7, "filters": {"make": "Ford", "model": "Focus", **filters}, "preferences": {},
            "origin_lat": None, "origin_lon": None, "radius_km": None}


MARKET = [listing(2014), listing(2015), listing(2015, price=14_000), listing(2016), listing(2016),
          listing(2017, transmission="automatic")]


class FunnelTest(unittest.TestCase):
    def test_single_year_is_the_blocker(self):
        fun = lr.funnel(MARKET, profile(year_min=2015, year_max=2015, price_max=12_000))
        self.assertEqual(fun.market, 6)
        self.assertEqual(fun.matched, 1)
        self.assertEqual(fun.fails, {"year": 4, "price": 1})
        self.assertEqual(fun.only, {"year": 4, "price": 1})
        self.assertEqual(fun.main_blocker, "year")
        self.assertEqual(fun.years, {2014: 1, 2015: 2, 2016: 2, 2017: 1})
        self.assertEqual(fun.price_usd, {"min": 10_000, "median": 10_000, "max": 14_000})

    def test_listing_failing_two_filters_is_not_only(self):
        fun = lr.funnel([listing(2017, transmission="automatic")],
                        profile(year_min=2015, year_max=2016, transmission="manual"))
        self.assertEqual(fun.fails, {"year": 1, "transmission": 1})
        self.assertEqual(fun.only, {})
        self.assertIsNone(fun.main_blocker)

    def test_hints_name_the_single_year(self):
        p = profile(year_min=2015, year_max=2015)
        hints = lr.hints(lr.funnel(MARKET, p), p)
        self.assertIn("Elegiste un solo año (2015): de ese año hubo 2; sumando un año para cada lado serían 5.", hints)
        self.assertTrue(any("año deja afuera 4" in h for h in hints))
        self.assertTrue(any("se publican pocos autos" in h for h in hints))

    def test_empty_market(self):
        p = profile()
        text = lr.fallback_text(lr.funnel([], p), p)
        self.assertIn("no vimos publicaciones de Ford Focus", text)
        self.assertIn("te avisamos", text)

    def test_fingerprint_follows_filters_and_place(self):
        a = profile(year_min=2015)
        self.assertEqual(lr.fingerprint(a), lr.fingerprint(profile(year_min=2015)))
        self.assertNotEqual(lr.fingerprint(a), lr.fingerprint(profile(year_min=2014)))
        self.assertNotEqual(lr.fingerprint(a), lr.fingerprint({**a, "radius_km": 50}))

    def test_settings(self):
        cfg = lr.settings({"max_results": 5, "notify": False, "min_age_hours": "x", "enabled": 1})
        self.assertEqual(cfg["max_results"], 5)
        self.assertFalse(cfg["notify"])
        self.assertEqual(cfg["min_age_hours"], lr.DEFAULTS["min_age_hours"])
        self.assertTrue(cfg["enabled"])
        self.assertEqual(lr.settings(None), lr.DEFAULTS)

    def test_model_less_search_is_not_eligible(self):
        self.assertFalse(lr.eligible({"body_types": ["suv"]}))
        self.assertTrue(lr.eligible({"make": "Ford", "model": "Focus"}))

    def test_llm_context_carries_only_the_search(self):
        p = profile(year_min=2015, year_max=2015, transmission="automatic")
        ctx = lr.llm_context(lr.funnel(MARKET, p), p, 1)
        self.assertEqual(ctx["busqueda"]["transmission"], "automática")
        self.assertEqual(ctx["resultados_actuales"], 1)
        self.assertEqual(ctx["embudo"]["main_blocker"], "transmission")   # the 2015s are manual
        self.assertNotIn("id", ctx["busqueda"])


class DueTest(unittest.TestCase):
    cfg = lr.settings({})

    def row(self, **kw) -> dict:
        return {"filters": {"make": "Ford", "model": "Focus"}, "fingerprint": "abc",
                "diagnosed_at": NOW - timedelta(days=1), **kw}

    def test_never_diagnosed(self):
        self.assertTrue(job.due(self.row(fingerprint=None, diagnosed_at=None), "abc", self.cfg, NOW))

    def test_filters_changed(self):
        self.assertTrue(job.due(self.row(), "new", self.cfg, NOW))

    def test_recent_same_filters(self):
        self.assertFalse(job.due(self.row(), "abc", self.cfg, NOW))

    def test_recheck_after_days(self):
        self.assertTrue(job.due(self.row(diagnosed_at=NOW - timedelta(days=8)), "abc", self.cfg, NOW))

    def test_model_less(self):
        self.assertFalse(job.due(self.row(filters={"body_types": ["suv"]}, fingerprint=None), "abc", self.cfg, NOW))


class FakeProvider:
    name = "fake:test"

    def __init__(self, answer=None, error: Exception | None = None):
        self.answer, self.error, self.context = answer, error, None

    async def explain_low_results(self, context):
        self.context = context
        if self.error:
            raise self.error
        return self.answer


class ExplainTest(unittest.IsolatedAsyncioTestCase):
    p = profile(year_min=2015, year_max=2015)

    async def test_llm_answer(self):
        fun = lr.funnel(MARKET, self.p)
        provider = FakeProvider(LowResultsExplanation(explanation=" Elegiste solo 2015. ",
                                                      suggestions=["Sumá 2014 y 2016 (+3)", " "]))
        text, suggestions, name, error = await job.explain(provider, lr.llm_context(fun, self.p, 2), fun, self.p)
        self.assertEqual(text, "Elegiste solo 2015.")
        self.assertEqual(suggestions, ["Sumá 2014 y 2016 (+3)"])
        self.assertEqual((name, error), ("fake:test", None))
        self.assertEqual(provider.context["embudo"]["market"], 6)

    async def test_llm_error_falls_back(self):
        fun = lr.funnel(MARKET, self.p)
        text, suggestions, name, error = await job.explain(FakeProvider(error=LLMError("429")), {}, fun, self.p)
        self.assertIn("Elegiste un solo año (2015)", text)
        self.assertEqual((suggestions, name, error), ([], None, "429"))

    async def test_no_provider(self):
        fun = lr.funnel(MARKET, self.p)
        _, _, name, error = await job.explain(None, {}, fun, self.p)
        self.assertIsNone(name)
        self.assertEqual(error, "sin proveedor LLM")


class FakeBot:
    def __init__(self):
        self.sent = []

    async def send_message(self, **kw):
        self.sent.append(kw)


class FakeTelegram:
    def __init__(self):
        self.bot = FakeBot()


class FakeEmail:
    def __init__(self):
        self.sent = []

    async def send_message(self, to, msg, *, idempotency_key, unsubscribe_token):
        from notifications.channels.base import SendResult
        self.sent.append((to, msg, idempotency_key))
        return SendResult(True, provider_id="x")


class NoticeTest(unittest.IsolatedAsyncioTestCase):
    row = {"id": 7, "filters": {"make": "Ford", "model": "Focus"}, "channels": ["telegram", "email", "web"],
           "telegram_chat_id": 123, "email": "a@b.test", "unsubscribe_token": "tok"}
    diagnosis = {"explanation": "Elegiste solo 2015 <y> hubo 2.", "suggestions": ["Sumá 2014 (+1)"],
                 "fingerprint": "abc"}
    links = Links("https://ese.auto", "")

    async def test_both_channels(self):
        tg, mail = FakeTelegram(), FakeEmail()
        sent = await notice.notify(self.row, self.diagnosis, {"telegram": tg, "email": mail}, self.links, NOW)
        self.assertEqual(sent, ["telegram", "email"])
        text = tg.bot.sent[0]["text"]
        self.assertIn("Ford Focus", text)
        self.assertIn("&lt;y&gt;", text)
        self.assertIn("https://ese.auto/app/searches/7", text)
        to, msg, key = mail.sent[0]
        self.assertEqual((to, key), ("a@b.test", "low-results-7-abc"))
        self.assertEqual(msg.subject, "Por qué tu búsqueda de Ford Focus trae pocos resultados")
        self.assertIn("Sumá 2014 (+1)", msg.text)
        self.assertIn("Elegiste solo 2015 &lt;y&gt; hubo 2.", msg.html)

    async def test_only_the_search_channels(self):
        tg, mail = FakeTelegram(), FakeEmail()
        sent = await notice.notify({**self.row, "channels": ["web"]}, self.diagnosis,
                                   {"telegram": tg, "email": mail}, self.links, NOW)
        self.assertEqual(sent, [])
        self.assertEqual((tg.bot.sent, mail.sent), ([], []))


if __name__ == "__main__":
    unittest.main()

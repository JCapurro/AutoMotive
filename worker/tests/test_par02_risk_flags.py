"""PAR-02 resto (docs/superpowers/specs/2026-11-02-par02-resto-design.md):
private_many_listings, the duplicate flags read from risk_duplicates, the
configurable order (app_config.red_flags.order), the email's cut at two
flags, the seller question and the copy lint of the new texts."""
from __future__ import annotations

import unittest
from dataclasses import replace

from intelligence import copy
from intelligence.config import DEFAULT_FLAG_ORDER, IntelligenceConfig, flag_order, risk
from intelligence.engine import assess
from intelligence.red_flags import RedFlag, ordered, red_flags
from intelligence.seller_questions import question_keys, question_texts
from normalization.normalize import normalize_text
from notifications.service import flag_texts
from test_intelligence import CFG, MARKET, NOW, fiesta_listing, fiesta_profile


def flags_of(listing, cfg=CFG, **kw):
    kw.setdefault("diff_pct", None)
    return red_flags(listing, guard=None, timing_belt=None, cfg=cfg, now=NOW, **kw)


def ids(flags):
    return [f.id for f in flags]


def many(**kw):
    """F-02 marked the seller a «posible agencia» with 6 cars; the source says «particular»."""
    return fiesta_listing(**{"seller_type": "private", "dealer_inferred": True, "seller_listing_count": 6, **kw})


def with_risk(**raw) -> IntelligenceConfig:
    return replace(CFG, risk=risk(raw))


PAIR_ML = {"other_id": 77, "kind": "cross_source_data", "source": "mercadolibre",
           "source_name": "Mercado Libre", "url": "https://auto.mercadolibre.com.ar/MLA-1", "distance": None}


class PrivateManyListingsTests(unittest.TestCase):
    def test_a_private_seller_with_six_listings_gets_it_with_n(self):
        f = {x.id: x for x in flags_of(many())}["private_many_listings"]
        self.assertEqual(f.text, "El vendedor tiene 6 publicaciones activas: conviene preguntar si es titular.")
        self.assertEqual(f.severity, "info")
        self.assertIsNone(f.link)

    def test_not_without_the_inference_nor_for_dealers_nor_unknown_sellers(self):
        for listing in (fiesta_listing(seller_type="private", dealer_inferred=False, seller_listing_count=6),
                        fiesta_listing(seller_type=None, dealer_inferred=True, seller_listing_count=7),
                        fiesta_listing(seller_type="dealer", dealer_inferred=False, seller_listing_count=9),
                        fiesta_listing(seller_type="private", dealer_inferred=True, seller_listing_count=None)):
            with self.subTest(listing=(listing.get("seller_type"), listing.get("dealer_inferred"))):
                self.assertNotIn("private_many_listings", ids(flags_of(listing)))

    def test_the_f02_switch_off_clears_dealer_inferred_and_so_the_flag(self):
        # seller_classification.enabled = false: the job sets dealer_inferred = false everywhere.
        self.assertNotIn("private_many_listings", ids(flags_of(many(dealer_inferred=False))))

    def test_its_own_signal_switch(self):
        cfg = with_risk(signals={"private_many_listings": "off"})
        self.assertNotIn("private_many_listings", ids(flags_of(many(), cfg)))
        cfg = with_risk(signals={"private_many_listings": "shadow"})
        self.assertNotIn("private_many_listings", ids(flags_of(many(), cfg)))

    def test_score_level_and_the_other_flags_do_not_move(self):
        base = fiesta_listing(seller_type="private", dealer_inferred=True, seller_listing_count=None)
        _, s0, e0 = assess(base, fiesta_profile(), price_ref=MARKET, cfg=CFG, now=NOW)
        _, s1, e1 = assess(many(), fiesta_profile(), price_ref=MARKET, cfg=CFG, now=NOW)
        self.assertEqual((s0.score, s0.level, s0.breakdown()), (s1.score, s1.level, s1.breakdown()))
        self.assertEqual([f for f in e1.red_flags if f.id != "private_many_listings"], e0.red_flags)

    def test_the_seller_question_asks_who_the_holder_is(self):
        flags = flags_of(many())
        keys = question_keys(many(), flags, timing_belt=None, now=NOW)
        self.assertIn("holder_detail", keys)
        self.assertNotIn("holder", keys)
        self.assertIn(copy.QUESTION["holder_detail"], question_texts(many(), flags, timing_belt=None, now=NOW,
                                                                    limit=10))
        plain = fiesta_listing(seller_type="private")
        self.assertIn("holder", question_keys(plain, flags_of(plain), timing_belt=None, now=NOW))


class DuplicateFlagTests(unittest.TestCase):
    def test_a_data_pair_is_an_info_flag_with_its_link(self):
        f = {x.id: x for x in flags_of(fiesta_listing(risk_duplicates=[PAIR_ML]), with_risk(
            signals={"cross_source_data": "on"}))}["cross_source_duplicate"]
        self.assertEqual(f.severity, "info")
        self.assertEqual(f.text, copy.RED_FLAG["cross_source_data"].format(source="Mercado Libre"))
        self.assertEqual(f.link, {"listing_id": 77, "url": "https://auto.mercadolibre.com.ar/MLA-1",
                                  "source_name": "Mercado Libre"})
        self.assertEqual(f.to_json()["link"]["listing_id"], 77)

    def test_the_default_shadow_never_shows_the_data_level(self):
        self.assertNotIn("cross_source_duplicate", ids(flags_of(fiesta_listing(risk_duplicates=[PAIR_ML]))))

    def test_photos_beat_data_and_the_rest_is_counted(self):
        photos = {**PAIR_ML, "other_id": 78, "kind": "cross_source_photos", "source_name": "Rosario Garage",
                  "distance": 2}
        f = {x.id: x for x in flags_of(fiesta_listing(risk_duplicates=[PAIR_ML, photos]), with_risk(
            signals={"cross_source_data": "on"}))}["cross_source_duplicate"]
        self.assertEqual(f.text, copy.RED_FLAG["cross_source_photos"].format(source="Rosario Garage y 1 más"))
        self.assertEqual(f.link["listing_id"], 78)

    def test_duplicate_photos_is_a_warning_and_coexists_with_a_cross_source_pair(self):
        stolen = {**PAIR_ML, "other_id": 79, "kind": "duplicate_photos", "source_name": "V6", "distance": 0}
        photos = {**PAIR_ML, "other_id": 78, "kind": "cross_source_photos", "source_name": "Rosario Garage"}
        flags = flags_of(fiesta_listing(risk_duplicates=[stolen, photos]))
        by_id = {f.id: f for f in flags}
        self.assertEqual(by_id["duplicate_photos"].severity, "warning")
        self.assertIn("(V6)", by_id["duplicate_photos"].text)
        self.assertEqual(by_id["cross_source_duplicate"].link["listing_id"], 78)
        self.assertEqual(ids(flags)[0], "duplicate_photos")

    def test_a_kind_turned_off_drops_its_flag_at_the_next_rescore(self):
        stolen = {**PAIR_ML, "kind": "duplicate_photos"}
        self.assertNotIn("duplicate_photos", ids(flags_of(fiesta_listing(risk_duplicates=[stolen]),
                                                          with_risk(signals={"duplicate_photos": "off"}))))

    def test_malformed_pairs_are_ignored(self):
        self.assertEqual(ids(flags_of(fiesta_listing(risk_duplicates=[None, "x", {"kind": "nope"}]))),
                         ids(flags_of(fiesta_listing())))

    def test_a_flag_without_link_keeps_the_old_json(self):
        self.assertEqual(RedFlag("repost", "t", "info").to_json(), {"id": "repost", "text": "t", "severity": "info"})


ALL_OLD = ["no_owners", "service_unavailable", "no_service", "timing_pending", "no_timing_belt",
           "short_description", "damage_mentioned", "commercial_use", "vtv_pending", "much_cheaper",
           "low_km_for_age", "partial_price_suspect", "repost", "price_mismatch", "year_mismatch", "km_mismatch"]


def flag(i, severity=None):
    return {"id": i, "text": i, "severity": severity or ("warning" if i in (
        "much_cheaper", "partial_price_suspect", "duplicate_photos") else "info")}


class OrderTests(unittest.TestCase):
    def test_without_order_the_email_is_as_before_for_every_existing_flag(self):
        # The emission order of red_flags() before PAR-02 resto; the old cut: warnings first, stable.
        stored = [flag(i) for i in ALL_OLD]
        before = [f["text"] for f in sorted(stored, key=lambda f: f["severity"] != "warning")][:2]
        self.assertEqual(flag_texts(stored, DEFAULT_FLAG_ORDER), before)
        self.assertEqual(flag_texts(stored), before)
        for a in ALL_OLD:
            for b in ALL_OLD:
                if a == b:
                    continue
                pair = [flag(a), flag(b)] if ALL_OLD.index(a) < ALL_OLD.index(b) else [flag(b), flag(a)]
                old = [f["text"] for f in sorted(pair, key=lambda f: f["severity"] != "warning")]
                with self.subTest(pair=(a, b)):
                    self.assertEqual(flag_texts(pair, DEFAULT_FLAG_ORDER), old)

    def test_combinations_with_the_new_flags(self):
        table = [
            (["no_owners", "much_cheaper", "private_many_listings"], ["much_cheaper", "private_many_listings"]),
            (["short_description", "much_cheaper", "duplicate_photos"], ["duplicate_photos", "much_cheaper"]),
            (["cross_source_duplicate", "no_owners", "repost"], ["cross_source_duplicate", "no_owners"]),
            (["partial_price_suspect", "private_many_listings", "cross_source_duplicate"],
             ["partial_price_suspect", "private_many_listings"]),
            (["repost", "unknown_future_flag"], ["repost", "unknown_future_flag"]),
        ]
        for stored, shown in table:
            with self.subTest(stored=stored):
                self.assertEqual(flag_texts([flag(i) for i in stored], DEFAULT_FLAG_ORDER), shown)

    def test_a_tuned_order_moves_an_info_above_a_warning(self):
        order = flag_order(["no_owners", "much_cheaper"])
        self.assertEqual(flag_texts([flag("much_cheaper"), flag("repost"), flag("no_owners")], order),
                         ["no_owners", "much_cheaper"])

    def test_a_bad_order_falls_back_to_the_default(self):
        for raw in (None, "x", [1, 2], {"a": 1}):
            self.assertEqual(flag_order(raw), DEFAULT_FLAG_ORDER)
        self.assertEqual(flag_order(["a", "a", "b"]), ("a", "b"))

    def test_the_worker_stores_them_ordered(self):
        listing = many(description="Ford Fiesta.", risk_duplicates=[{**PAIR_ML, "kind": "duplicate_photos"}])
        got = ids(flags_of(listing, diff_pct=30.0))
        self.assertEqual(got[:3], ["duplicate_photos", "much_cheaper", "private_many_listings"])
        self.assertEqual(got, sorted(got, key=DEFAULT_FLAG_ORDER.index))
        custom = replace(CFG, red_flags={**CFG.red_flags, "order": ["private_many_listings"]})
        self.assertEqual(ids(flags_of(listing, custom, diff_pct=30.0))[0], "private_many_listings")

    def test_ordered_keeps_unknown_ids_last_in_emission_order(self):
        fl = [RedFlag("z", "", "info"), RedFlag("much_cheaper", "", "warning"), RedFlag("y", "", "info")]
        self.assertEqual(ids(ordered(fl, DEFAULT_FLAG_ORDER)), ["much_cheaper", "z", "y"])

    def test_the_default_order_matches_the_migration_and_lists_every_flag(self):
        self.assertEqual(len(DEFAULT_FLAG_ORDER), 19)
        self.assertEqual(set(ALL_OLD) | {"duplicate_photos", "private_many_listings", "cross_source_duplicate"},
                         set(DEFAULT_FLAG_ORDER))


class RiskConfigTests(unittest.TestCase):
    def test_defaults_are_off_and_shadow(self):
        cfg = risk(None)
        self.assertFalse(cfg["photo_hash"]["enabled"])
        self.assertEqual(cfg["photo_hash"]["skip_sources"], ["facebook", "instagram"])
        self.assertEqual(cfg["signals"]["cross_source_data"], "shadow")
        self.assertEqual((cfg["photo_hash_count"], cfg["phash_max_distance"]), (3, 6))

    def test_bad_values_fall_back_key_by_key(self):
        cfg = risk({"photo_hash_count": 9, "phash_max_distance": 4, "photo_hash": {"enabled": "yes",
                    "daily_image_cap": -1, "max_attempts": 3, "skip_sources": "facebook"},
                    "cross_source": {"km_tol_pct": 50, "price_tol_pct": 4}, "signals": {"cross_source_data": "maybe",
                    "duplicate_photos": "shadow"}, "checklist_enabled": False})
        self.assertEqual((cfg["photo_hash_count"], cfg["phash_max_distance"]), (3, 4))
        self.assertEqual((cfg["photo_hash"]["enabled"], cfg["photo_hash"]["daily_image_cap"],
                          cfg["photo_hash"]["max_attempts"]), (False, 600, 3))
        self.assertEqual(cfg["photo_hash"]["skip_sources"], ["facebook", "instagram"])
        self.assertEqual((cfg["cross_source"]["km_tol_pct"], cfg["cross_source"]["price_tol_pct"]), (3, 4))
        self.assertEqual(cfg["signals"]["cross_source_data"], "shadow")
        self.assertEqual(cfg["signals"]["duplicate_photos"], "shadow")
        self.assertIsNot(risk(None)["photo_hash"], risk(None)["photo_hash"])


NEW_TEXTS = {"private_many_listings": copy.RED_FLAG["private_many_listings"].format(n="7"),
             "duplicate_photos": copy.RED_FLAG["duplicate_photos"].format(source="V6 y 2 más"),
             "cross_source_photos": copy.RED_FLAG["cross_source_photos"].format(source="Mercado Libre"),
             "cross_source_data": copy.RED_FLAG["cross_source_data"].format(source="Mercado Libre"),
             "holder_detail": copy.QUESTION["holder_detail"]}


class RiskCopyLintTests(unittest.TestCase):
    """Never claim what Ese Auto only suspects: no fraud, no theft, nothing «verificado» or «certificado»,
    no «agencia» (F-02 only infers it)."""

    def test_the_lint_catches_what_it_should(self):
        self.assertTrue(any(normalize_text(t) in normalize_text("Fotos robadas: estafa") for t in copy.RISK_FORBIDDEN))

    def test_no_forbidden_word_in_the_new_texts(self):
        for key, text in NEW_TEXTS.items():
            folded = normalize_text(text)
            for term in copy.RISK_FORBIDDEN:
                with self.subTest(key=key, term=term):
                    self.assertNotIn(normalize_text(term), folded)

    def test_every_flag_text_reads_as_something_to_check(self):
        for key in ("private_many_listings", "duplicate_photos", "cross_source_photos", "cross_source_data"):
            with self.subTest(key):
                self.assertIn("conviene", NEW_TEXTS[key])


if __name__ == "__main__":
    unittest.main()

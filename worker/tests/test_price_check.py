"""normalization/price_check.keyword_partial: the title's keywords and the
description's phrasings that leave the published number as a down payment."""
from __future__ import annotations

import unittest

from normalization.description_facts import parse, resolve_price
from normalization.price_check import keyword_partial

TEMPLATE = ("LLEVATE este Volkswagen Amarok DC 4x2 Trendline (2024) por . Solo $4.999.999. "
            "Tomamos TU USADO en parte de pago, CONSULTANOS.")


class KeywordPartialTests(unittest.TestCase):
    def test_the_title_keywords(self):
        self.assertEqual(keyword_partial("Fiat Cronos anticipo y cuotas"), "keyword: anticipo")
        self.assertIsNone(keyword_partial("Fiat Cronos 1.3 Drive 2021"))

    def test_the_dealer_template_with_a_blank_total(self):
        self.assertEqual(keyword_partial("Volkswagen Amarok DC 4x2 Trendline", TEMPLATE),
                         "keyword: precio total en blanco")
        self.assertIsNotNone(keyword_partial(None, "Polo (2024) por. Solo U$S 4.000"))

    def test_the_template_leaves_the_stored_price_partial(self):
        # The «Solo» amount reads as a plain price; it must not clear the flag.
        title = "Volkswagen Amarok DC 4x2 Trendline"
        facts = parse(TEMPLATE, title, now_year=2026)
        self.assertEqual(facts.published_is, "down_payment")
        price = resolve_price(4_999_999, "ARS", partial_reason=keyword_partial(title, TEMPLATE),
                              facts=facts, usd_rate=1_550)
        self.assertTrue(price.partial)
        self.assertEqual(price.partial_reason, "keyword: precio total en blanco")

    def test_the_same_template_with_its_total_is_a_price(self):
        self.assertIsNone(keyword_partial("Chery QQ", "LLEVATE este Chery QQ (2018) por $11.500.000. "
                                                      "Tomamos TU USADO en parte de pago."))

    def test_the_title_keywords_do_not_apply_to_the_description(self):
        # Dealers offer cuotas and planes next to a real total.
        self.assertIsNone(keyword_partial("Ford Ka 2017 1.5 Sel",
                                          "Precio $8.900.000. También financiamos en cuotas, plan canje."))


if __name__ == "__main__":
    unittest.main()

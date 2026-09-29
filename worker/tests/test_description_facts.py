"""The description as a source of facts: price kinds, financing, km, year (pure)."""
from __future__ import annotations

import unittest

from normalization.description_facts import (Amount, DescriptionFacts, parse, resolve_price,
                                             trim_page_noise)
from normalization.money import parse_number


def _kinds(text: str, title: str | None = None) -> list[tuple[str, float, str]]:
    facts = parse(text, title)
    return [(a.kind, a.amount, a.currency) for a in facts.amounts] if facts else []


def _resolve(published: float, currency: str, text: str | None, *, partial: str | None = None,
             rate: float = 1_000.0, title: str | None = None):
    return resolve_price(published, currency, partial_reason=partial,
                         facts=parse(text, title), usd_rate=rate)


class NumberTests(unittest.TestCase):
    def test_separators_and_multipliers(self):
        self.assertEqual(parse_number("10.900"), 10_900)
        self.assertEqual(parse_number("16.500.000"), 16_500_000)
        self.assertEqual(parse_number("11,900"), 11_900)
        self.assertEqual(parse_number("1.234.567,50"), 1_234_567)
        self.assertEqual(parse_number("5", "millones"), 5_000_000)
        self.assertEqual(parse_number("11,5", "millones"), 11_500_000)
        self.assertEqual(parse_number("10", "mil"), 10_000)


class AmountTests(unittest.TestCase):
    def test_cash_list_and_down_payment_on_their_own_lines(self):
        text = ("PRECIO CONTADO U$s 10.990 .-\nPRECIO PERMUTA U$S 12.500 .-\n"
                "O FINANCIALO CON UN ANTICIPO MINIMO DESDE U$S 6.000.- Y CUOTAS.")
        self.assertEqual(_kinds(text), [("cash", 10_990, "USD"), ("list", 12_500, "USD"),
                                        ("down_payment", 6_000, "USD")])

    def test_label_on_the_previous_line(self):
        text = "- PRECIO DE CONTADO U$S 10.900\n- APTO CREDITO\n- PRECIO DE LISTA/PERMUTA\nU$S 11.500"
        self.assertEqual(_kinds(text), [("cash", 10_900, "USD"), ("list", 11_500, "USD")])

    def test_currency_spellings(self):
        self.assertEqual(_kinds("💵 Us 11.200"), [("generic", 11_200, "USD")])
        self.assertEqual(_kinds("VALOR:10.000usd"), [("generic", 10_000, "USD")])
        self.assertEqual(_kinds("Precio : ARS $ 13.500.000 (sujeto a revisión)"),
                         [("generic", 13_500_000, "ARS")])
        self.assertEqual(_kinds("10 mil dls"), [("generic", 10_000, "USD")])
        self.assertEqual(_kinds("PROMOCION DE CONTADO HASTA 30/9 U$s10.900 DOLARES"),
                         [("cash", 10_900, "USD")])

    def test_words_after_the_amount_win(self):
        self.assertEqual(_kinds("💸 u$s11.500 en efectivo, consultame"), [("cash", 11_500, "USD")])
        self.assertEqual(_kinds("Anticipo de $12.500.000 + cuotas de $400.000"),
                         [("down_payment", 12_500_000, "ARS"), ("installment", 400_000, "ARS")])
        self.assertEqual(_kinds("Precio: $5.000.000 y cuotas fijas"), [("down_payment", 5_000_000, "ARS")])
        self.assertEqual(_kinds("SE ENCUENTRA EN PERFECTAS CONDICIONES ANTICIPO 5 MILLONES Y CUOTAS"),
                         [("down_payment", 5_000_000, "ARS")])

    def test_installments_and_down_payments_may_be_small(self):
        text = ("Precio US$ 10.800 Retiralo con tu usado o con un anticipo desde US$ 4.800 y el saldo "
                "en cuotas a tasa fija desde $ 603.000 (Los valores quedan sujetos a aprobación)")
        self.assertEqual(_kinds(text), [("generic", 10_800, "USD"), ("down_payment", 4_800, "USD"),
                                        ("installment", 603_000, "ARS")])

    def test_money_that_is_not_the_price(self):
        self.assertEqual(_kinds("El total de transferencia es de $1.551.000 e incluye el 08"), [])
        self.assertEqual(_kinds("🔥 $500.000 de descuento"), [])
        self.assertEqual(_kinds("Lista para transferir\n*** u$s 13.000.- ***"), [("generic", 13_000, "USD")])

    def test_spelled_out_half_million(self):
        self.assertEqual(_kinds("18 millones quinientos mil (pesos)"), [("generic", 18_500_000, "ARS")])

    def test_title_amounts_count(self):
        facts = parse(None, "2025 Volkswagen polo $12.000.000 y cuotas")
        self.assertEqual([(a.kind, a.amount) for a in facts.amounts], [("down_payment", 12_000_000)])

    def test_the_page_around_a_description_is_not_read(self):
        text = ("Vendo Fiesta 2016. Precio en dólares.\nVer más\nMunro, BA\n· La ubicación es aproximada\n"
                "Enviar mensaje\nSugerencias de hoy\n$13.900\n$7.500.000\nBerazategui Oeste, BA")
        self.assertEqual(_kinds(text), [])
        self.assertEqual(trim_page_noise(text), "Vendo Fiesta 2016. Precio en dólares.")
        self.assertEqual(trim_page_noise("Ver más\nSugerencias de hoy"), "")

    def test_nothing_to_read(self):
        self.assertIsNone(parse(None, None))
        self.assertIsNone(parse("  ", ""))


class FinancingTests(unittest.TestCase):
    def test_dealer_terms(self):
        fin = parse("Entrega mínima 50% o tu usado, Saldo financiado hasta 36 cuotas fijas en Pesos!!!").financing
        self.assertTrue(fin.offered)
        self.assertEqual((fin.min_down_payment_pct, fin.max_installments), (50, 36))
        fin = parse("Financiación: te financiamos hasta el 50% solo con DNI.").financing
        self.assertEqual(fin.max_financed_pct, 50)
        fin = parse("Precio de contado $16.500.000-.\n... o retirá con $10.000.000 y cuotas fijas.").financing
        self.assertEqual(fin.down_payment, {"amount": 10_000_000, "currency": "ARS"})

    def test_no_financing(self):
        self.assertFalse(parse("Único dueño, papeles al día. No financio.").financing.offered)
        self.assertFalse(parse("Impecable, service oficial").financing.offered)


class KmAndYearTests(unittest.TestCase):
    def test_labeled_km(self):
        self.assertEqual(parse("🛞 KM: 121.000\ncambio de aceite a los 120.0000").mileage_km, 121_000)
        self.assertEqual(parse("Ford Fiesta 1.6 5p Se (Kd) 2018 con 75500 km. Excelente").mileage_km, 75_500)
        self.assertEqual(parse("Mecánica: 126.000 km.").mileage_km, 126_000)

    def test_service_tires_and_history_are_not_the_mileage(self):
        text = "Distribución realizada a los 90.000 km. Neumáticos con 20 mil km. Lo adquirí con 55.000 kms."
        self.assertIsNone(parse(text).mileage_km)
        self.assertIsNone(parse("Visitanos en Ruta 178 km:200 (Las Rosas)").mileage_km)

    def test_two_different_mileages_are_ambiguous(self):
        facts = parse("Km: 110.000\nTiene 150.000 km reales")
        self.assertTrue(facts.ambiguous)

    def test_year_only_when_labeled(self):
        self.assertEqual(parse("Año: 2017 Nafta Km: 110.000").year, 2017)
        self.assertEqual(parse("Ford Fiesta 2017 con 110.000 km").year, 2017)
        self.assertIsNone(parse("VTV vigente hasta 2027, oblea GNC 05/2026").year)
        self.assertIsNone(parse("Año 2017 ... modelo 2018").year)

    def test_transmission_fuel_gnc(self):
        facts = parse("Ford Fiesta 1.6 Titanium c/GNC, caja manual. Nafta/GNC.")
        self.assertEqual((facts.transmission, facts.fuel, facts.gnc), ("manual", "gnc", True))


class ResolvePriceTests(unittest.TestCase):
    def test_published_cash_is_confirmed(self):
        r = _resolve(10_990, "USD", "PRECIO CONTADO U$s 10.990\nPRECIO PERMUTA U$S 12.500")
        self.assertEqual((r.price, r.source, r.published_kind, r.partial, r.mismatch),
                         (10_990, "published", "cash", False, None))

    def test_list_price_published_cash_in_the_text(self):
        r = _resolve(11_500, "USD", "- PRECIO DE CONTADO U$S 10.900\n- PRECIO DE LISTA/PERMUTA U$S 11.500")
        self.assertEqual((r.price, r.currency, r.source, r.published_kind), (10_900, "USD", "description", "list"))

    def test_the_text_says_the_published_price_is_the_list_one(self):
        r = _resolve(14_500_000, "ARS", "El precio publicado es el de lista. Contado $13.900.000")
        self.assertEqual((r.price, r.source), (13_900_000, "description"))

    def test_cash_below_half_is_not_taken(self):
        r = _resolve(11_500, "USD", "Contado U$S 5.000")
        self.assertEqual((r.price, r.source), (11_500, "published"))

    def test_down_payment_published_with_a_total_in_the_text(self):
        r = _resolve(5_000_000, "ARS", "Precio final $15.000.000. Retirá con $5.000.000 y cuotas.")
        self.assertEqual((r.price, r.partial, r.source, r.published_kind),
                         (15_000_000, False, "description", "down_payment"))

    def test_down_payment_without_a_total_stays_partial(self):
        r = _resolve(13_700_000, "ARS", "Polo 1.6 MSI\nSe retira con $13.700.000\nVendo o permuto")
        self.assertEqual((r.price, r.partial, r.partial_reason), (13_700_000, True, "descripción: anticipo"))

    def test_title_partial_cleared_when_the_text_confirms_a_total(self):
        r = _resolve(17_900_000, "ARS", "Precio: $17.900.000. Financio 100% con Banco Nación",
                     partial="keyword: financio 100")
        self.assertEqual((r.partial, r.partial_reason, r.published_kind), (False, None, "generic"))

    def test_title_partial_resolved_by_a_total_in_other_currency(self):
        r = _resolve(9_000_000, "ARS", "Precio total USD 15.000", partial="keyword: cuotas", rate=1_000)
        self.assertEqual((r.price, r.currency, r.partial), (15_000, "USD", False))

    def test_title_partial_without_a_total_stays(self):
        r = _resolve(9_986, "USD", "Impecable", partial="keyword: cuotas")
        self.assertEqual((r.partial, r.partial_reason), (True, "keyword: cuotas"))

    def test_hidden_down_payment(self):
        r = _resolve(7_900_000, "ARS", "💰 PRECIO DE REMATE: $16.500.000\n❌ Precio : $16.900.000")
        self.assertEqual((r.price, r.source), (16_500_000, "description"))

    def test_outdated_description_is_a_mismatch(self):
        r = _resolve(10_900, "USD", "💸 u$s11.500 en efectivo, consultame por permutas")
        self.assertEqual((r.price, r.source), (10_900, "published"))
        self.assertEqual((r.mismatch.amount, r.mismatch.currency), (11_500, "USD"))
        self.assertEqual(r.check()["mismatch"], {"amount": 11_500, "currency": "USD"})

    def test_same_price_in_the_other_currency_is_not_a_mismatch(self):
        r = _resolve(11_490_000, "ARS", "Precio: USD 11.490", rate=1_000)
        self.assertIsNone(r.mismatch)

    def test_without_facts_nothing_changes(self):
        r = resolve_price(10_000, "USD", partial_reason=None, facts=None, usd_rate=None)
        self.assertEqual((r.price, r.source, r.partial), (10_000, "published", False))


class JsonTests(unittest.TestCase):
    def test_round_trip(self):
        facts = parse("PRECIO CONTADO U$S 10.990\nAnticipo U$S 6.000 y cuotas. Km: 90.000. Año 2017")
        again = DescriptionFacts.from_json(facts.to_json())
        self.assertEqual(again.amounts, facts.amounts)
        self.assertEqual((again.mileage_km, again.year, again.financing), (90_000, 2017, facts.financing))
        self.assertIsNone(DescriptionFacts.from_json(None))
        self.assertEqual(DescriptionFacts.from_json({"amounts": [{"kind": "cash", "amount": 1, "currency": "USD"}]})
                         .amounts, [Amount("cash", 1.0, "USD", "")])


if __name__ == "__main__":
    unittest.main()

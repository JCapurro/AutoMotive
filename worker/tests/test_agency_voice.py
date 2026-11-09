"""The agency voice (intelligence/seller.agency_voice, seller_for_preference; spec §3.2, §4.7). Pure.

A «particular» whose description reads like an agency's counts as one only for f3's seller preference and
seller cap. effective_seller, PRO-01's strict filter, matching and the duplicates never see it.
"""
from __future__ import annotations

import unittest

from intelligence import duplicates, matching
from intelligence.config import risk
from intelligence.seller import agency_voice, effective_seller, seller_for_preference
from test_intelligence import FX, fiesta_listing, fiesta_profile


class PhraseTests(unittest.TestCase):
    def test_strong_phrases(self):
        """Los casos positivos: «recibimos tu usado», «financiamos»… (una frase en plural basta)."""
        cases = {
            "Recibimos tu usado como parte de pago": "recibimos tu usado",
            "FINANCIAMOS!!": "financiamos",
            "Tomamos su auto": "tomamos su auto",
            "aceptamos vehículo": "aceptamos vehiculo",
            "Te lo compramos al contado": "te lo compramos",
            "Compramos tu usado": "compramos tu usado",
            "Somos agencia con 20 años": "somos agencia",
            "somos una concesionaria oficial": "somos una concesionaria",
            "Visitá nuestro salón": "nuestro salon",
            "en nuestra agencia de Lanús": "nuestra agencia",
            "Nuestros showroom": "nuestros showroom",
        }
        for text, phrase in cases.items():
            with self.subTest(text=text):
                self.assertEqual(agency_voice(text), phrase)

    def test_plural_objects_and_places(self):
        """«tomamos usados», «recibimos autos», «nuestros locales»: the plural is the typical agency phrase
        (the measured regex had no trailing boundary and matched them)."""
        cases = {
            "Tomamos usados": "tomamos usados",
            "Recibimos autos en parte de pago": "recibimos autos",
            "Aceptamos vehículos usados como parte de pago": "aceptamos vehiculos",
            "aceptamos unidades usadas": "aceptamos unidades",
            "Recibimos tus usados": "recibimos tus usados",
            "Compramos tus autos": "compramos tus autos",
            "Somos concesionarios oficiales": "somos concesionarios",
            "Visitá nuestros locales": "nuestros locales",
            "en nuestras agencias de zona norte": "nuestras agencias",
            "nuestros salones": "nuestros salones",
        }
        for text, phrase in cases.items():
            with self.subTest(text=text):
                self.assertEqual(agency_voice(text), phrase)
        self.assertEqual(agency_voice("Consignaciones. Cuotas fijas"), "consignaciones · cuotas fijas")

    def test_a_negated_phrase_does_not_fire(self):
        """Lo que dice que NO hace una agencia lo escribe un particular: «no financiamos», «no tomamos tu auto»."""
        for text in ("No financiamos", "no financiamos, tomo permuta", "No tomamos tu auto", "no recibimos usados",
                     "No te lo compramos", "No somos concesionarios"):
            with self.subTest(text=text):
                self.assertIsNone(agency_voice(text))
        # Only the negated phrase is skipped: another one in the same text still fires.
        self.assertEqual(agency_voice("No financiamos pero recibimos tu usado"), "recibimos tu usado")
        # «sino», «no,»: not a negation of the phrase.
        self.assertEqual(agency_voice("Contado sino financiamos"), "financiamos")
        self.assertEqual(agency_voice("¿Financian? No, financiamos solo con DNI"), "financiamos")

    def test_what_a_private_seller_also_writes_does_not_fire(self):
        """Los negativos: «services en concesionario oficial», «financio», «no somos agencia»."""
        for text in ("Services en concesionario oficial, todos al día", "Financio una parte", "No somos agencia",
                     "no somos concesionaria, vendo mi auto", "Recibo permuta", "tomo tu auto", "Concesionario lider",
                     "Solo DNI", "cuotas fijas", "Horario de atención: de 9 a 18", "", None,
                     "Financiación propia y planes de financiación"):     # one signal, twice
            with self.subTest(text=text):
                self.assertIsNone(agency_voice(text))

    def test_two_distinct_weak_signals(self):
        self.assertEqual(agency_voice("Solo DNI y cuotas fijas"), "solo dni · cuotas fijas")
        self.assertEqual(agency_voice("Cuotas en pesos. Horario de atención 9 a 18"),
                         "cuotas en pesos · horario de atencion")
        self.assertEqual(agency_voice("Consignación. Crédito prendario"), "consignacion · credito prendario")
        # In the order they appear in the text.
        self.assertEqual(agency_voice("Horario de atención 9-18, solo con el DNI"),
                         "horario de atencion · solo con el dni")

    def test_a_strong_phrase_wins_over_weak_ones(self):
        self.assertEqual(agency_voice("Solo DNI, cuotas fijas, recibimos tu usado"), "recibimos tu usado")

    def test_accents_case_and_spaces(self):
        self.assertEqual(agency_voice("RECIBIMOS   TU\nUSADO"), "recibimos tu usado")
        self.assertEqual(agency_voice("Nuestro Salón"), "nuestro salon")

    def test_whole_words_only(self):
        self.assertIsNone(agency_voice("refinanciamosx"))
        self.assertIsNone(agency_voice("recibimos tu usadote"))


class SellerForPreferenceTests(unittest.TestCase):
    VOICE = "Recibimos tu usado. Financiación propia."

    def test_only_a_listing_the_source_calls_private(self):
        self.assertEqual(seller_for_preference({"seller_type": "private", "description": self.VOICE}), "dealer")
        self.assertEqual(seller_for_preference({"seller_type": "private", "description": "Vendo mi auto"}), "private")
        self.assertIsNone(seller_for_preference({"seller_type": None, "description": self.VOICE}))
        self.assertEqual(seller_for_preference({"seller_type": "dealer", "description": None}), "dealer")
        self.assertEqual(seller_for_preference({"seller_type": "private", "dealer_inferred": True}), "dealer")
        self.assertEqual(seller_for_preference({"seller_type": "private", "description": None}), "private")

    def test_effective_seller_does_not_change(self):
        """El predicado no cambia effective_seller."""
        self.assertEqual(effective_seller({"seller_type": "private", "description": self.VOICE}), "private")

    def test_strict_filter_and_matching_do_not_change(self):
        """…ni el filtro estricto (PRO-01), ni la preferencia de f2."""
        voiced = fiesta_listing(seller_type="private", description=self.VOICE)
        plain = fiesta_listing(seller_type="private", description="Vendo mi auto, único dueño")
        strict = fiesta_profile(seller_types=["private"]) | {"seller_filter": True}
        soft = fiesta_profile()
        soft["preferences"]["seller_type"] = "private"
        for profile in (strict, soft):
            with self.subTest(strict=profile is strict):
                a = matching.evaluate(voiced, profile, fx_rate=FX)
                b = matching.evaluate(plain, profile, fx_rate=FX)
                self.assertTrue(a.is_match)
                self.assertEqual(a.to_json(), b.to_json())
        self.assertEqual(matching.evaluate(voiced, strict, fx_rate=FX).reasons["seller"].result, "ok")

    def test_duplicates_do_not_change(self):
        """…ni los duplicados (PAR-02 resto: two agencies' cars are never one car by data)."""
        cs = risk(None)["cross_source"]
        zone = {"precision": "locality", "lat": -34.526, "lon": -58.479, "province_id": "06", "department": "VL"}
        a = fiesta_listing(id=1, seller_type="private", mileage_km=80_000, description=self.VOICE, zone=zone)
        b = fiesta_listing(id=2, seller_type="private", mileage_km=80_000, source="facebook",
                           description=self.VOICE, zone=zone)
        plain_a, plain_b = dict(a, description=None), dict(b, description=None)
        self.assertEqual(duplicates._data_guards(a, b, cs), duplicates._data_guards(plain_a, plain_b, cs))
        self.assertIsNotNone(duplicates._data_guards(a, b, cs))


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx

from collectors._http import Page, soup
from collectors.base import CollectorBlocked
from collectors.mardelusados import MardelUsadosScraper as Mardel
from collectors.usadossantafe import UsadosSantaFeScraper as SantaFe
from pipeline.crawl import derive_targets, scraper_filters

FIXTURES = Path(__file__).parent / "fixtures" / "html"
M_URL = "https://mardelusados.com/vehiculo/fiat-punto-2012-vh-0576/"
S_URL = "https://usadossantafe.com.ar/aviso/260922-0841-48K68"


def fixture(name):
    return (FIXTURES / name).read_text(encoding="utf-8")


def flight(records):
    payload = '2d:' + json.dumps(['$', '$L2e', None, {'avisosIniciales': records}])
    return '<script>self.__next_f.push(' + json.dumps([1, payload]) + ')</script>'


class RegionalParserTests(unittest.TestCase):
    def test_mardel_structured_catalog_and_discount(self):
        items = Mardel.parse_search(fixture("mardelusados_search.html"))
        self.assertEqual(len(items), 3)  # fourth card is a motorcycle
        self.assertEqual((items[0].listing_id, items[0].marca, items[0].modelo),
                         ("VH-0629", "Volkswagen", "Gol Trend"))
        self.assertEqual((items[0].anio, items[0].km, items[0].precio, items[0].moneda),
                         (2012, 179_000, 7_000, "USD"))
        self.assertEqual(items[0].ubicacion, "Mar del Plata")
        # The data attribute is current; the crossed-out old price is ignored.
        card = soup(fixture("mardelusados_search.html")).select('[data-veh]')[2]
        self.assertEqual(items[2].precio, float(card['data-precio']))
        self.assertNotEqual(items[2].precio, float(''.join(filter(str.isdigit,
                                             card.select_one('.line-through').get_text()))))
        self.assertIsNotNone(items[0].published_at)

    def test_mardel_detail_gallery_specs_and_own_description(self):
        item = Mardel.parse_detail(fixture("mardelusados_detail.html"), M_URL).listing
        self.assertEqual((item.precio, item.moneda, item.anio, item.km), (8000, "USD", 2012, 93000))
        self.assertEqual(len(item.imagenes), 6)
        self.assertIn("febrero de 2026", item.descripcion)
        self.assertEqual(item.atributos["Motor"], "1.4")
        self.assertEqual(item.vendedor_nombre, "@vendedor_ejemplo")

    def test_mardel_recommended_ad_cannot_replace_requested_vehicle(self):
        with self.assertRaisesRegex(RuntimeError, "another vehicle"):
            Mardel.parse_detail(fixture("mardelusados_detail.html"), M_URL.replace('0576', '9999'))

    def test_santafe_structured_price_placeholder_and_known_fields(self):
        items = SantaFe.parse_search(fixture("usadossantafe_search.html"))
        first = items[0]
        self.assertEqual((first.listing_id, first.marca, first.modelo, first.anio, first.km),
                         ('260922-0841-48K68', 'Chevrolet', 'Agile', 2012, 140000))
        self.assertEqual((first.precio, first.moneda, first.vendedor), (11000000, 'ARS', 'particular'))
        self.assertIsNone(items[-1].precio)
        self.assertEqual(first.url, S_URL)  # ID-only route verified with HTTP 200

    def test_santafe_excludes_sold_inactive_and_other_categories(self):
        base = {'id': '261001-0001-AAAA', 'tipo': 'Auto', 'marca': 'Ford', 'modelo': 'Ka',
                'precio': '11000', 'moneda': 'USD', 'activo': True}
        for change in ({'vendido': True}, {'activo': False}, {'borrado': True},
                       {'rechazado': True}, {'tipo': 'Moto'}, {'tipo': 'Lancha'}):
            with self.subTest(change=change):
                self.assertEqual(SantaFe.parse_search(flight([{**base, **change}])), [])
        item = SantaFe.parse_search(flight([base]))[0]
        self.assertEqual((item.precio, item.moneda, item.km, item.vendedor_nombre), (11000, 'USD', None, None))

    def test_santafe_rendered_cards_after_load_more(self):
        items = SantaFe.parse_search(fixture('usadossantafe_render.html'))
        self.assertEqual(len(items), 2)
        self.assertEqual((items[1].anio, items[1].km, items[1].moneda), (2018, 110000, 'ARS'))
        self.assertTrue(items[1].imagenes)

    def test_santafe_fragmented_flight_stream_is_decoded_without_eval(self):
        payload = '2d:' + json.dumps(['$', '$L2e', None, {'avisosIniciales': [
            {'id': '261001-0001-AAAA', 'tipo': 'Auto', 'marca': 'Ford', 'modelo': 'Ka'}]}])
        html = ''.join('<script>self.__next_f.push(' + json.dumps([1, part]) + ')</script>'
                       for part in (payload[:27], payload[27:]))
        self.assertEqual(SantaFe.parse_search(html)[0].titulo, 'Ford Ka')

    def test_santafe_detail_and_slim_reparse(self):
        raw = fixture('usadossantafe_detail.html')
        item = SantaFe.parse_detail(raw, S_URL).listing
        self.assertEqual((item.precio, item.moneda, item.anio, item.km), (11000000, 'ARS', 2012, 140000))
        self.assertEqual(len(item.imagenes), 8)
        slim = SantaFe().slim_page(Page(200, S_URL, raw))
        self.assertEqual(SantaFe.parse_detail(slim, S_URL).listing.to_dict(), item.to_dict())
        self.assertNotIn('userUID', slim)
        self.assertNotIn('notasAprobacion', slim)

    def test_santafe_json_ld_fallback_does_not_attribute_seller_to_portal(self):
        doc = soup(fixture('usadossantafe_detail.html'))
        doc.select_one('#eseauto-vehicles').decompose()
        item = SantaFe.parse_detail(str(doc), S_URL).listing
        self.assertEqual(item.precio, 11000000)
        self.assertIsNone(item.vendedor_nombre)
        self.assertIsNone(item.vendedor)

    def test_santafe_requested_identity_is_required(self):
        with self.assertRaisesRegex(RuntimeError, 'ID mismatch'):
            SantaFe.parse_detail(fixture('usadossantafe_detail.html'), S_URL.replace('48K68', 'AAAA'))

    def test_explicit_empty_catalog_is_healthy(self):
        self.assertEqual(SantaFe.parse_search(flight([])), [])

    def test_blocks_errors_and_unknown_html_never_prove_removal(self):
        for cls, url in ((Mardel, M_URL), (SantaFe, S_URL)):
            for status in (401, 403, 429):
                with self.subTest(cls=cls, status=status), self.assertRaises(CollectorBlocked):
                    cls.parse_detail('', url, status)
            for status in (500, 502):
                with self.subTest(cls=cls, status=status), self.assertRaises(RuntimeError):
                    cls.parse_detail('', url, status)
            self.assertTrue(cls.parse_detail('', url, 404).gone)
            with self.assertRaises(RuntimeError):
                cls.parse_detail('<h1>New layout</h1>', url)
            with self.assertRaises(RuntimeError):
                cls.parse_search('<h1>New layout</h1>')


class RegionalTransportTests(unittest.IsolatedAsyncioTestCase):
    async def test_mardel_search_filters_and_http_failures(self):
        collector = Mardel(transport=httpx.MockTransport(lambda request:
                   httpx.Response(200, text=fixture('mardelusados_search.html'))))
        items = await collector.search({'marca': 'Volkswagen', 'modelo': 'Gol Trend'})
        self.assertEqual([v.listing_id for v in items], ['VH-0629'])
        collector = Mardel(transport=httpx.MockTransport(lambda request: httpx.Response(503)))
        with self.assertRaises(RuntimeError):
            await collector.search({})

    async def test_catalog_render_loads_additional_cards_and_deduplicates_categories(self):
        initial = fixture('usadossantafe_search.html').replace('</body>', '<button>Cargar más avisos</button></body>')
        rendered = fixture('usadossantafe_render.html')
        renderer = AsyncMock(return_value=Page(200, SantaFe.BASE + '/autos', rendered))
        collector = SantaFe(transport=httpx.MockTransport(lambda request: httpx.Response(200, text=initial)),
                            render_catalog=renderer)
        items = await collector.search({})
        self.assertEqual(len(items), 2)
        self.assertEqual(renderer.await_count, 2)

    async def test_failed_extra_load_is_reported(self):
        initial = fixture('usadossantafe_search.html').replace('</body>', '<button>Cargar más avisos</button></body>')
        collector = SantaFe(transport=httpx.MockTransport(lambda request: httpx.Response(200, text=initial)),
                            render_catalog=AsyncMock(return_value=Page(200, SantaFe.BASE + '/autos', initial)))
        with self.assertRaisesRegex(RuntimeError, 'did not complete'):
            await collector.search({})

    async def test_detail_cannot_fetch_unrelated_host(self):
        for cls in (Mardel, SantaFe):
            with self.subTest(cls=cls), self.assertRaises(ValueError):
                await cls().fetch_detail_page('https://example.org/vehicle')


class InventoryTargetTests(unittest.TestCase):
    def test_inventory_is_one_unbounded_target_for_different_models_and_locations(self):
        from collectors import REGISTRY
        with patch.dict(REGISTRY, {'mardelusados': Mardel}):
            specs = derive_targets([
                {'id': 1, 'filters': {'make': 'Ford', 'model': 'Fiesta', 'year_min': 2018, 'km_max': 80000},
                 'origin_lat': -34.6, 'origin_lon': -58.4},
                {'id': 2, 'filters': {'make': 'Fiat', 'model': 'Punto', 'year_max': 2012, 'km_max': 180000}},
            ], ['mercadolibre', 'mardelusados'])
        inv = next(s for s in specs if s.source == 'mardelusados')
        self.assertIsNone(inv.make)
        self.assertIsNone(inv.model)
        self.assertEqual(inv.query, {'inventory': True, 'profile_ids': [1, 2]})
        self.assertEqual(scraper_filters({'make': None, 'model': None, 'query': inv.query}), {})
        self.assertEqual(len([s for s in specs if s.source == 'mercadolibre']), 2)

    def test_inventory_respects_source_opt_out_and_vehicle_free_profiles(self):
        from collectors import REGISTRY
        with patch.dict(REGISTRY, {'usadossantafe': SantaFe}):
            specs = derive_targets([{'id': 1, 'filters': {'sources': ['mercadolibre']}},
                                    {'id': 2, 'filters': {'sources': ['usadossantafe'], 'year_min': 2019}}],
                                   ['mercadolibre', 'usadossantafe'])
        self.assertEqual([(s.source, s.query['profile_ids']) for s in specs], [('usadossantafe', [2])])


if __name__ == '__main__':
    unittest.main()

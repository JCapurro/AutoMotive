from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path
from urllib.parse import parse_qs

import httpx

from collectors._http import Page, soup
from collectors.autocity import AutocityScraper as Autocity
from collectors.carone import CarOneScraper as CarOne
from collectors.gruporandazzo import GrupoRandazzoScraper as Randazzo
from collectors.base import CollectorBlocked


FIXTURES = Path(__file__).parent / "fixtures" / "html"
A_URL = "https://autocity.com.ar/?p=95281"
C_URL = "https://carone.com.ar/comprar/usados/ford-ka-1-5-s-plus-4p-l18-1"
R_URL = "https://www.gruporandazzo.com/ae074xf_8091-renault-sandero-stepway-ph2-1-6-zen----l19-2020/p"


def fixture(name):
    return (FIXTURES / name).read_text(encoding="utf-8")


def flight(data, *, fragment=False):
    stream = '1:' + json.dumps(data) + '\n'
    pieces = (stream[:25], stream[25:]) if fragment else (stream,)
    return ''.join('<script>self.__next_f.push(' + json.dumps([1, p]) + ')</script>' for p in pieces)


def carone_record(**changes):
    return {**copy.deepcopy(CarOne._detail_record(fixture('carone_detail.html'))), **changes}


def autocity_page(ids, total, *, following=None):
    doc = soup(fixture('autocity_search.html'))
    for count in doc.select('.woocommerce-result-count'):
        count.string = f'{total} resultados'
    cards = doc.select('ul.products>li.product')
    for card, new_id in zip(cards, ids):
        original_id = next(c[5:] for c in card['class'] if c.startswith('post-'))
        card['class'] = [c.replace('post-' + original_id, 'post-' + new_id) for c in card['class']]
        card.select_one('a[href]')['href'] = f'https://autocity.com.ar/catalogo/usados/vehicle-{new_id}/'
    for card in cards[len(ids):]:
        card.decompose()
    if following:
        nav = doc.new_tag('div', attrs={'class': 'customNavigation'})
        anchor = doc.new_tag('a', attrs={'class': 'backtoNext', 'href': following})
        nav.append(anchor)
        doc.body.append(nav)
    return str(doc)


def randazzo_page(ids, total, offset=0, *, state='Disponible'):
    base, _ = Randazzo._data(fixture('randazzo_search.html'))
    original_key, original = next((k, v) for k, v in base.items()
                                  if isinstance(v, dict) and v.get('__typename') == 'Product')
    props = Randazzo._resolve(base, original['properties'])
    for prop in props:
        if prop['name'] == 'Estado':
            prop['values'] = [state]
    refs = []
    for product_id in ids:
        key = f'Product:fake-{product_id}'
        record = {**copy.deepcopy(original), 'productId': product_id,
                  'productReference': f'FAKE{product_id}_UNIT',
                  'linkText': f'fake{product_id}_unit-vehicle', 'properties': props}
        base[key] = record
        refs.append({'type': 'id', 'id': key})
    query = 'productSearch(' + json.dumps({'from': offset, 'to': offset + 11,
             'query': 'usados/disponible', 'selectedFacets': [{'key': 'c', 'value': 'usados'},
             {'key': 'estado', 'value': 'disponible'}]}) + ')'
    base['ROOT_QUERY'] = {query: {'type': 'id', 'id': 'Search:fake'}}
    base['Search:fake'] = {'products': refs, 'recordsFiltered': total}
    return '<script>__RUNTIME__ = {"culture":{"currency":"ARS"}}; __STATE__ = ' + json.dumps(base) + '</script>'


def stored_randazzo(**changes):
    product = copy.deepcopy(Randazzo._detail_product(fixture('randazzo_detail.html')))
    product.update(changes)
    return '<script id="eseauto-randazzo-product" type="application/json">' + json.dumps(product) + '</script>'


def randazzo_api_record(product_id, **changes):
    record = json.loads(fixture('randazzo_api_product.json'))
    record.update(productId=product_id, productReference=f'FAKE{product_id}_UNIT',
                  linkText=f'fake{product_id}_unit-vehicle')
    record.update(changes)
    return record


def randazzo_api_transport(handler):
    def handle(request):
        if request.url.path.startswith('/usados'):
            return httpx.Response(200, text=fixture('randazzo_search.html'))
        if '/facets/category/' in request.url.path:
            return httpx.Response(200, json=[{'Name': 'Estado', 'Id': 74}])
        query = parse_qs(request.url.query.decode())
        if query.get('fq') != ['C:/40/', 'specificationFilter_74:Disponible']:
            raise AssertionError('Missing public category / available stock filter')
        if query.get('O') != ['OrderByReleaseDateDESC']:
            raise AssertionError('Missing stable catalog sort')
        return handler(request, int(query['_from'][0]), int(query['_to'][0]))
    return httpx.MockTransport(handle)


class AgencyParserTests(unittest.TestCase):
    def test_autocity_structured_taxonomy_price_mileage_and_branch(self):
        items = Autocity.parse_search(fixture('autocity_search.html'))
        self.assertEqual(len(items), 2)
        first = items[0]
        self.assertEqual((first.listing_id, first.url), ('95276', 'https://autocity.com.ar/?p=95276'))
        self.assertEqual((first.marca, first.modelo, first.anio, first.km), ('Volkswagen', 'Up!', 2015, 82500))
        self.assertEqual((first.precio, first.moneda, first.ubicacion), (13400000, 'ARS', 'Río Cuarto'))
        self.assertEqual(first.imagenes, [])  # Loading/default icons are not vehicle photos.
        self.assertTrue(items[1].imagenes)
        self.assertEqual((first.vendedor, first.vendedor_nombre), ('agencia', 'Autocity'))

    def test_autocity_no_make_model_guess_without_taxonomy(self):
        doc = soup(fixture('autocity_search.html'))
        for el in doc.select('[data-slug][data-type]'):
            el.decompose()
        first = Autocity.parse_search(str(doc))[0]
        self.assertIsNone(first.marca)
        self.assertIsNone(first.modelo)
        self.assertIsNone(first.ubicacion)

    def test_autocity_excludes_unavailable_new_and_other_categories(self):
        raw = fixture('autocity_search.html')
        for change in ('VendIdo', 'Reservado', 'A ingresar', 'Plan de ahorro', 'Moto'):
            with self.subTest(change=change):
                doc = soup(raw)
                for card in doc.select('li.product'):
                    card.select_one('.carousel-autocity-card-condiciones').string = change
                self.assertEqual(Autocity.parse_search(str(doc)), [])
        self.assertEqual(Autocity.parse_search(raw.replace('product_cat-usados', 'product_cat-0km')), [])
        self.assertEqual(Autocity.parse_search(raw.replace('instock', 'outofstock')), [])

    def test_autocity_detail_shortlink_identity_photos_specs_and_financing(self):
        item = Autocity.parse_detail(fixture('autocity_detail.html'), A_URL).listing
        self.assertEqual((item.listing_id, item.precio, item.moneda, item.anio, item.km),
                         ('95281', 13900000, 'ARS', 2018, 76800))
        self.assertEqual((item.marca, item.modelo, item.transmision), ('Chery', 'Fulwin', 'Manual'))
        self.assertTrue(item.imagenes)
        self.assertIsNone(item.ubicacion)  # Contact form's four choices cannot locate this unit.
        with self.assertRaisesRegex(RuntimeError, 'ID mismatch'):
            Autocity.parse_detail(fixture('autocity_detail.html'), A_URL.replace('95281', '99999'))
        with self.assertRaisesRegex(RuntimeError, 'another vehicle'):
            Autocity.parse_detail(fixture('autocity_detail.html'), Autocity.CATALOG + 'another-car/')

    def test_autocity_missing_condition_does_not_prove_gone(self):
        raw = fixture('autocity_detail.html').replace('data-estado="Usado"', '')
        with self.assertRaisesRegex(RuntimeError, 'condition'):
            Autocity.parse_detail(raw, A_URL)

    def test_autocity_duplicate_card_identity_is_not_a_complete_catalog(self):
        doc = soup(fixture('autocity_search.html'))
        card = copy.copy(doc.select_one('li.product'))
        doc.select_one('ul.products').append(card)
        with self.assertRaisesRegex(RuntimeError, 'repeated vehicle card'):
            Autocity.parse_search(str(doc))

    def test_carone_price_final_over_regular_taxfree_and_reservation(self):
        record = carone_record(carone_reserve_price=471250, carone_tax_free_price=15578512)
        record['price_range']['maximum_price']['regular_price']['value'] = 22000000
        item = CarOne.parse_detail(flight({'product': record}), C_URL).listing
        self.assertEqual((item.precio, item.moneda), (18850000, 'ARS'))
        self.assertEqual((item.marca, item.modelo, item.anio, item.km), ('Ford', 'KA', 2021, 88000))
        self.assertEqual((item.ubicacion, item.vendedor, item.vendedor_nombre), ('Tortuguitas', 'agencia', 'Car One'))

    def test_carone_flight_fragmented_catalog_and_empty(self):
        data = {'data': {'products': {'items': [carone_record()], 'total_count': 1}}}
        self.assertEqual(CarOne.parse_search(flight(data, fragment=True))[0].listing_id, '62441')
        self.assertEqual(CarOne.parse_search(flight({'products': {'items': [], 'total_count': 0}})), [])

    def test_carone_excludes_new_plans_sold_and_motos(self):
        for changes in ({'carone_tags_data': [{'tag_id': 5, 'title': 'Vehículos 0km'}]},
                        {'carone_tags_data': [{'tag_id': 8, 'title': 'Plan de ahorro'}]},
                        {'stock_status': 'OUT_OF_STOCK'}, {'carone_type_data': {'label': 'Moto'}},
                        {'carone_mileage': 0}):
            with self.subTest(changes=changes):
                data = {'products': {'items': [carone_record(**changes)], 'total_count': 1}}
                self.assertEqual(CarOne.parse_search(flight(data)), [])
                self.assertTrue(CarOne.parse_detail(flight({'product': carone_record(**changes)}), C_URL).gone)

    def test_carone_missing_state_or_condition_cannot_prove_gone(self):
        for field in ('stock_status', 'carone_tags_data'):
            record = carone_record()
            record.pop(field)
            with self.subTest(field=field), self.assertRaises(RuntimeError):
                CarOne.parse_detail(flight({'product': record}), C_URL)
        with self.assertRaisesRegex(RuntimeError, 'condition unknown'):
            CarOne.parse_detail(flight({'product': carone_record(carone_tags_data=[{'tag_id': 11, 'title': 'Destacados'}])}), C_URL)

    def test_carone_placeholder_price_and_identity(self):
        record = carone_record()
        record['price_range']['maximum_price']['final_price']['value'] = 1
        self.assertIsNone(CarOne.parse_detail(flight({'product': record}), C_URL).listing.precio)
        with self.assertRaisesRegex(RuntimeError, 'another vehicle'):
            CarOne.parse_detail(fixture('carone_detail.html'), C_URL + '-other')
        with self.assertRaisesRegex(RuntimeError, 'ambiguous'):
            CarOne.parse_detail(flight({'product': record, 'related': {'product': record}}), C_URL)

    def test_randazzo_structured_specs_total_price_not_reservation(self):
        item = Randazzo.parse_search(fixture('randazzo_search.html'))[0]
        self.assertEqual((item.listing_id, item.precio, item.moneda, item.anio, item.km),
                         ('AE074XF_8091', 20000000, 'ARS', 2020, 132476))
        self.assertEqual((item.marca, item.modelo, item.vendedor_nombre), ('RENAULT', 'SANDERO', 'Grupo Randazzo'))
        self.assertIsNone(item.ubicacion)
        self.assertNotEqual(item.precio, 400000)  # Real VTEX commerce offer is only the reservation.
        self.assertIn('"Price": 400000', fixture('randazzo_detail.html'))

    def test_randazzo_live_api_contract_uses_specs_not_reservation(self):
        record = json.loads(fixture('randazzo_api_product.json'))
        item = Randazzo._listing(Randazzo._api_product(record, 'ARS'))
        self.assertEqual((item.listing_id, item.precio, item.moneda, item.anio, item.km),
                         ('AH251JH_8339', 43800000, 'ARS', 2025, 39674))
        self.assertEqual(item.modelo, 'HILUX')
        self.assertTrue(item.imagenes)
        self.assertIsNone(item.ubicacion)
        record.pop('Precio')
        self.assertIsNone(Randazzo._listing(Randazzo._api_product(record, 'ARS')).precio)
        record['productReference'] = 'DIFFERENT_UNIT'
        with self.assertRaisesRegex(RuntimeError, 'link ID mismatch'):
            Randazzo._listing(Randazzo._api_product(record, 'ARS'))

    def test_randazzo_only_available_stock_and_not_0km(self):
        for state in ('Reservado', 'A Ingresar', 'Vendido'):
            with self.subTest(state=state):
                self.assertEqual(Randazzo.parse_search(randazzo_page(['1'], 1, state=state)), [])
        product = Randazzo._detail_product(fixture('randazzo_detail.html'))
        for prop in product['properties']:
            if prop['name'] == 'Km':
                prop['values'] = ['0']
        product['properties'] = [p for p in product['properties'] if p['name'] != 'Estado']
        self.assertTrue(Randazzo.parse_detail(stored_randazzo(**product), R_URL).gone)

    def test_randazzo_placeholder_missing_state_and_id_mismatch(self):
        product = Randazzo._detail_product(fixture('randazzo_detail.html'))
        for prop in product['properties']:
            if prop['name'] == 'Precio':
                prop['values'] = ['1']
        self.assertIsNone(Randazzo.parse_detail(stored_randazzo(**product), R_URL).listing.precio)
        product['properties'] = [p for p in product['properties'] if p['name'] != 'Estado']
        with self.assertRaisesRegex(RuntimeError, 'state missing'):
            Randazzo.parse_detail(stored_randazzo(**product), R_URL)
        with self.assertRaisesRegex(RuntimeError, 'category missing'):
            Randazzo.parse_detail(stored_randazzo(categories=[]), R_URL)
        with self.assertRaisesRegex(RuntimeError, 'another vehicle'):
            Randazzo.parse_detail(fixture('randazzo_detail.html'), R_URL.replace('ae074xf', 'fake'))
        with self.assertRaisesRegex(RuntimeError, 'ID mismatch'):
            Randazzo.parse_detail(stored_randazzo(productReference='DIFFERENT'), R_URL)
        product = Randazzo._detail_product(fixture('randazzo_detail.html'))
        product['properties'] = [p for p in product['properties'] if p['name'] != 'Precio']
        self.assertIsNone(Randazzo.parse_detail(stored_randazzo(**product), R_URL).listing.precio)

    def test_all_detail_slim_roundtrips_preserve_identity_and_own_data(self):
        for cls, name, url in ((Autocity, 'autocity', A_URL), (CarOne, 'carone', C_URL), (Randazzo, 'randazzo', R_URL)):
            with self.subTest(source=cls.name):
                raw = fixture(name + '_detail.html')
                expected = cls.parse_detail(raw, url).listing.to_dict()
                slim = cls().slim_page(Page(200, url, raw))
                self.assertEqual(cls.parse_detail(slim, url).listing.to_dict(), expected)
                self.assertNotIn('addToCartLink', slim)

    def test_gone_and_invalid_pages_remain_reprocessable_diagnostics(self):
        for cls, url in ((Autocity, A_URL), (CarOne, C_URL), (Randazzo, R_URL)):
            for status in (404, 410):
                raw = '<h1>Unidad no disponible</h1><script>unrelatedState={};</script>'
                slim = cls().slim_page(Page(status, url, raw))
                self.assertTrue(cls.parse_detail(slim, url, status).gone)
                self.assertIn('Unidad no disponible', slim)
                self.assertNotIn('unrelatedState', slim)
            raw = '<h1>Detalle incompleto</h1><script>self.__next_f.push([1,"private app state"])</script>'
            slim = cls().slim_page(Page(200, url, raw))
            self.assertIn('Detalle incompleto', slim)
            self.assertNotIn('private app state', slim)
            with self.assertRaises(RuntimeError):
                cls.parse_detail(slim, url)

    def test_only_explicit_empty_catalog_is_healthy(self):
        self.assertEqual(Autocity.parse_search(autocity_page([], 0)), [])
        self.assertEqual(Randazzo.parse_search(randazzo_page([], 0)), [])
        self.assertEqual(CarOne.parse_search(flight({'products': {'items': [], 'total_count': 0}})), [])
        for cls, html in ((Autocity, autocity_page([], 1)), (Randazzo, randazzo_page([], 1)),
                          (CarOne, flight({'products': {'items': [], 'total_count': 1}}))):
            with self.subTest(source=cls.name), self.assertRaises(RuntimeError):
                cls.parse_search(html)

    def test_http_blocks_errors_and_unknown_html_are_never_false_zero_or_gone(self):
        for cls, url in ((Autocity, A_URL), (CarOne, C_URL), (Randazzo, R_URL)):
            for status in (401, 403, 429):
                with self.subTest(source=cls.name, status=status), self.assertRaises(CollectorBlocked):
                    cls.parse_detail('', url, status)
            for status in (500, 502):
                with self.subTest(source=cls.name, status=status), self.assertRaises(RuntimeError):
                    cls.parse_detail('', url, status)
            for status in (404, 410):
                self.assertTrue(cls.parse_detail('', url, status).gone)
            with self.assertRaises(RuntimeError):
                cls.parse_detail('<h1>Layout changed</h1>', url)
            with self.assertRaises(RuntimeError):
                cls.parse_search('<h1>Layout changed</h1>')


class AgencyTransportTests(unittest.IsolatedAsyncioTestCase):
    async def test_autocity_complete_pagination_and_filters(self):
        calls = []
        def handler(request):
            calls.append(str(request.url))
            second = '/page/2/' in request.url.path
            return httpx.Response(200, text=autocity_page(['3'] if second else ['1', '2'], 3,
                   following=None if second else Autocity.CATALOG + 'page/2/'))
        items = await Autocity(transport=httpx.MockTransport(handler)).search({'marca': 'Chery'})
        self.assertEqual([v.listing_id for v in items], ['2'])
        self.assertEqual(len(calls), 2)

    async def test_autocity_repetition_missing_page_and_limit_fail(self):
        pages = [autocity_page(['1', '2'], 3, following=Autocity.CATALOG + 'page/2/'),
                 autocity_page(['1'], 3)]
        for second in (pages[1], '<h1>Broken page</h1>', autocity_page([], 3)):
            with self.subTest(second=second[:25]):
                collector = Autocity(transport=httpx.MockTransport(lambda req: httpx.Response(
                    200, text=second if '/page/2/' in req.url.path else pages[0])))
                with self.assertRaises(RuntimeError):
                    await collector.search({})
        collector = Autocity(transport=httpx.MockTransport(lambda req: httpx.Response(200, text=pages[0])))
        collector.MAX_PAGES = 1
        with self.assertRaisesRegex(RuntimeError, 'limit'):
            await collector.search({})

    async def test_carone_all_stock_pages_then_only_used_and_filters(self):
        calls = []
        def handler(request):
            self.assertEqual((request.method, request.url.path), ('POST', '/api/graphql'))
            variables = json.loads(request.content)['variables']
            page = variables['currentPage']
            calls.append(page)
            self.assertEqual(variables['filter'], {'stock_status': {'eq': 'IN_STOCK'}})
            records = [carone_record(id=1, url_key='vehicle-1'), carone_record(id=2, url_key='vehicle-2',
                       carone_tags_data=[{'tag_id': 5, 'title': 'Vehículos 0km'}])] if page == 1 else [
                       carone_record(id=3, url_key='vehicle-3', carone_dealer_id='San Martín')]
            return httpx.Response(200, json={'data': {'products': {'items': records, 'total_count': 3}}})
        collector = CarOne(transport=httpx.MockTransport(handler))
        collector.PAGE_SIZE = 2
        items = await collector.search({'ubicacion': 'San Martín'})
        self.assertEqual([v.listing_id for v in items], ['3'])
        self.assertEqual(calls, [1, 2])

    async def test_carone_graphql_errors_repetition_short_page_and_limit_fail(self):
        first = {'data': {'products': {'items': [carone_record(id=1, url_key='vehicle-1')], 'total_count': 2}}}
        for response in (first, {'errors': [{'message': 'upstream unavailable'}], **first},
                         {'data': {'products': {'items': [], 'total_count': 2}}},
                         {'data': {'products': {'items': [carone_record(id=2, url_key='vehicle-2')], 'total_count': 3}}}):
            def handler(req):
                page = json.loads(req.content)['variables']['currentPage']
                return httpx.Response(200, json=first if page == 1 else response)
            collector = CarOne(transport=httpx.MockTransport(handler))
            collector.PAGE_SIZE = 1
            with self.subTest(response=response.keys()), self.assertRaises(RuntimeError):
                await collector.search({})
        collector = CarOne(transport=httpx.MockTransport(lambda req: httpx.Response(200, json=first)))
        collector.PAGE_SIZE = 1
        collector.MAX_PAGES = 1
        with self.assertRaisesRegex(RuntimeError, 'limit'):
            await collector.search({})

    async def test_randazzo_complete_api_ranges_excludes_zero_mileage_and_filters(self):
        calls = []
        def handler(request, offset, end):
            calls.append(offset)
            records = [randazzo_api_record('1'), randazzo_api_record('2')] if offset == 0 else [
                       randazzo_api_record('3', Km=['0'])]
            return httpx.Response(206 if offset == 0 else 200, json=records,
                                  headers={'resources': f'{offset}-{end}/3'})
        collector = Randazzo(transport=randazzo_api_transport(handler))
        collector.PAGE_SIZE = 2
        items = await collector.search({'marca': 'Toyota', 'anio_min': 2020})
        self.assertEqual([v.listing_id for v in items], ['FAKE1_UNIT', 'FAKE2_UNIT'])
        self.assertEqual(calls, [0, 2])

    async def test_randazzo_repetition_incomplete_page_and_limit_fail(self):
        first = [randazzo_api_record('1'), randazzo_api_record('2')]
        for second, interval in (([randazzo_api_record('1')], '2-3/3'), ([], '2-3/3'),
                                 ([randazzo_api_record('3')], '0-1/3'),
                                 ([randazzo_api_record('3')], ''),
                                 ([randazzo_api_record('3')], '2-3/4')):
            def handler(request, offset, end):
                return httpx.Response(200, json=second if offset else first,
                       headers={'resources': interval if offset else '0-1/3'})
            collector = Randazzo(transport=randazzo_api_transport(handler))
            collector.PAGE_SIZE = 2
            with self.subTest(interval=interval), self.assertRaises(RuntimeError):
                await collector.search({})
        collector = Randazzo(transport=randazzo_api_transport(lambda req, offset, end:
                    httpx.Response(206, json=first, headers={'resources': '0-1/3'})))
        collector.PAGE_SIZE = 2
        collector.MAX_PAGES = 1
        with self.assertRaisesRegex(RuntimeError, 'limit'):
            await collector.search({})

    async def test_http_error_on_any_page_fails_entire_collection(self):
        for cls in (Autocity, CarOne, Randazzo):
            for status in (403, 503):
                collector = cls(transport=httpx.MockTransport(lambda req: httpx.Response(status)))
                with self.subTest(source=cls.name, status=status), self.assertRaises(RuntimeError):
                    await collector.search({})

    async def test_error_after_first_page_never_returns_partial_stock(self):
        def autocity(request):
            if '/page/2/' in request.url.path:
                return httpx.Response(503)
            return httpx.Response(200, text=autocity_page(['1', '2'], 3,
                   following=Autocity.CATALOG + 'page/2/'))
        def carone(request):
            if json.loads(request.content)['variables']['currentPage'] == 2:
                return httpx.Response(503)
            return httpx.Response(200, json={'data': {'products': {
                'items': [carone_record(id=1, url_key='vehicle-1')], 'total_count': 2}}})
        def randazzo(request, offset, end):
            if offset:
                return httpx.Response(503)
            return httpx.Response(206, json=[randazzo_api_record('1')],
                                  headers={'resources': '0-0/2'})
        collectors = [Autocity(transport=httpx.MockTransport(autocity)),
                      CarOne(transport=httpx.MockTransport(carone)),
                      Randazzo(transport=randazzo_api_transport(randazzo))]
        for collector in collectors:
            collector.PAGE_SIZE = 1
            collector.PAGE_DELAY = 0
            with self.subTest(source=collector.name), self.assertRaisesRegex(RuntimeError, '503'):
                await collector.search({})

    async def test_sources_reject_unrelated_detail_host(self):
        for cls in (Autocity, CarOne, Randazzo):
            with self.subTest(source=cls.name), self.assertRaises(ValueError):
                await cls().fetch_detail_page('https://example.org/product')

    async def test_carone_api_redirect_never_requests_redirect_destination(self):
        calls = []
        def handler(request):
            calls.append(str(request.url))
            return httpx.Response(302, headers={'Location': 'https://example.org/graphql'})
        with self.assertRaises(CollectorBlocked):
            await CarOne(transport=httpx.MockTransport(handler)).search({})
        self.assertEqual(calls, [CarOne.BASE + '/api/graphql'])

    async def test_autocity_redirect_identity_survives_final_url_raw_replay(self):
        final = 'https://autocity.com.ar/catalogo/usados/m-chery/m-fulwin/1-5-5p-l15/'
        def handler(request):
            if request.url.query:
                return httpx.Response(302, headers={'Location': final})
            return httpx.Response(200, text=fixture('autocity_detail.html'))
        collector = Autocity(transport=httpx.MockTransport(handler))
        page = await collector.fetch_detail_page(A_URL)
        self.assertEqual(page.url, final)
        slim = collector.slim_page(page)
        expected = collector.parse_detail(page.html, page.url).listing.to_dict()
        self.assertEqual(collector.parse_detail(slim, page.url).listing.to_dict(), expected)
        wrong = await collector.fetch_detail_page(A_URL.replace('95281', '95276'))
        with self.assertRaisesRegex(RuntimeError, 'ID mismatch'):
            collector.parse_detail(wrong.html, A_URL.replace('95281', '95276'))
        with self.assertRaisesRegex(RuntimeError, 'ID mismatch'):
            collector.parse_detail(collector.slim_page(wrong), wrong.url)

    async def test_randazzo_filtered_catalog_must_prove_filter_applied(self):
        collector = Randazzo(transport=randazzo_api_transport(lambda req, offset, end: httpx.Response(
            200, json=[randazzo_api_record('1', Estado=['Reservado'])], headers={'resources': f'{offset}-{end}/1'})))
        with self.assertRaisesRegex(RuntimeError, 'filter was not applied'):
            await collector.search({})

    async def test_randazzo_stale_available_index_counts_but_excludes_reserved_unit(self):
        collector = Randazzo(transport=randazzo_api_transport(lambda req, offset, end: httpx.Response(
            206, json=[randazzo_api_record('1'), randazzo_api_record('2', Estado=['Reservado'])],
            headers={'resources': f'{offset}-{end}/2'})))
        with self.assertLogs('collectors.gruporandazzo', level='WARNING') as logs:
            items = await collector.search({})
        self.assertEqual([v.listing_id for v in items], ['FAKE1_UNIT'])
        self.assertIn('FAKE2_UNIT', logs.output[0])
        self.assertIn('Reservado', logs.output[0])

    async def test_randazzo_api_missing_state_or_category_cannot_be_skipped(self):
        for changes in ({'Estado': []}, {'categories': []}, {'categories': ['/0km/']}):
            collector = Randazzo(transport=randazzo_api_transport(lambda req, offset, end: httpx.Response(
                200, json=[randazzo_api_record('1'), randazzo_api_record('2', **changes)],
                headers={'resources': f'{offset}-{end}/2'})))
            with self.subTest(changes=changes), self.assertRaises(RuntimeError):
                await collector.search({})

    async def test_randazzo_empty_api_and_upstream_errors(self):
        collector = Randazzo(transport=randazzo_api_transport(lambda req, offset, end: httpx.Response(
            200, json=[], headers={'resources': f'{offset}-{end}/0'})))
        self.assertEqual(await collector.search({}), [])
        for response in (httpx.Response(503), httpx.Response(403),
                         httpx.Response(200, text='not json'),
                         httpx.Response(302, headers={'Location': 'https://example.org/catalog'})):
            collector = Randazzo(transport=randazzo_api_transport(lambda req, offset, end: response))
            with self.subTest(status=response.status_code), self.assertRaises(RuntimeError):
                await collector.search({})


if __name__ == '__main__':
    unittest.main()

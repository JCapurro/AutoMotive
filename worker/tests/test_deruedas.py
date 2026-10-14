"""deRuedas: search contract, cards, detail pages and wiring (offline fixtures)."""
from __future__ import annotations

import asyncio
import copy
import functools
import json
import re
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
import pytest

import collectors
import config
from collectors import deruedas
from collectors._http import Page, soup
from collectors.base import CollectorBlocked, SearchResults
from collectors.deruedas import DeRuedasScraper as D
from normalization.vehicle import resolve_vehicle
from pipeline import enrich
from pipeline.crawl import derive_targets, scraper_filters
from pipeline.ingest import IngestResult
from seed_catalog import seed_catalog
from tools import collector_repairs
from tools.scraper_cli import _source_of


ROOT = Path(__file__).resolve().parents[2]
FIXTURES = Path(__file__).parent / 'fixtures' / 'html'
BASE = 'https://www.deruedas.com.ar'
SEARCH = BASE + '/bus.asp?segmento=0&marca=Chevrolet&modelo=Chevrolet%3AOnix&condicion=Usados&order=6'
# Every active detail fixture and the cod of its ad.
ACTIVE = {'deruedas_detail.html': '830433', 'deruedas_detail_usd.html': '828256',
          'deruedas_detail_particular.html': '807381', 'deruedas_detail_nonclient.html': '824503',
          'deruedas_detail_gnc.html': '725808', 'deruedas_detail_partial.html': '822494'}


@functools.lru_cache(maxsize=None)
def fixture(name):
    return (FIXTURES / name).read_text(encoding='utf-8')


def page(html, status=200, **headers):
    # Like the site: text/html without a charset.
    return httpx.Response(status, content=html.encode('utf-8'), headers={'content-type': 'text/html', **headers})


def detail_url(cod, path='/vendo/Toyota/Corolla/Usados/Mendoza'):
    return f'{BASE}{path}?cod={cod}'


@functools.lru_cache(maxsize=None)
def _onix_card():
    return str(soup(fixture('deruedas_search.html')).select_one('div#car_830458'))


def card(cod, brand='Chevrolet', model='Onix'):
    """The fixture's first Onix card (2019, 115000 km) as another ad, and optionally another vehicle."""
    html = _onix_card().replace('830458', str(cod))
    for prop, old, new in (('brand', 'Chevrolet', brand), ('model', 'Onix', model)):
        tag = f'<meta content="{old}" itemprop="{prop}"/>'
        assert tag in html
        html = html.replace(tag, f'<meta content="{new}" itemprop="{prop}"/>')
    return html


def cards(start, count, brand='Chevrolet', model='Onix'):
    return [card(cod, brand, model) for cod in range(start, start + count)]


def fragment(items, more):
    """busCraw.asp?weNeed=divBusqueda: the result list and its marker."""
    return ('<div id="divBusqueda" class="divBusqueda"><div itemscope itemtype="https://schema.org/ItemList">'
            '<div itemprop="itemListElement">' + ''.join(items) + '</div></div></div>\n'
            '<script class="newScript">\n\t\tmasContenido = ' + ('true' if more else 'false') + ';\n</script>')


def onix_page(items, *, total, more):
    """The real bus.asp fixture (JSON-LD, chips, filters) with other cards."""
    html = fixture('deruedas_search.html')
    html = html.replace('"numberOfItems":161', f'"numberOfItems":{total}')
    return html[:html.index('<div id="divBusqueda"')] + fragment(items, more) + '</body></html>'


def bus_page(brand, model=None, items=(), *, total=None, more=False, years=None, listed=None):
    """A bus.asp first page as the site writes it when the filters were applied."""
    total = len(items) if total is None else total
    wanted = f'{brand}:{model}'
    if listed is None:
        listed = ([wanted] if total else []) if model else [f'{brand}:Otro', f'{brand}:Modelo']
    chips = f'<div class="toggleMarcaLink cerrarItem_4" marcaval="{brand}">{brand}</div>'
    if model:
        chips += f'<div class="toggleModeloLink cerrarItem_4" marcaval="{brand}" modeloval="{wanted}">{model}</div>'
    if years:
        chips += f'<div class="refreshLink cerrarItem_2" refreshparam="anio_1|anio_2">{years}</div>'
    ld = json.dumps({'@type': 'SearchResultsPage', 'mainEntity': {'@type': 'ItemList', 'numberOfItems': total}})
    return (f'<html><head><script type="application/ld+json">{ld}</script>'
            '<script>var masContenido = false;</script></head><body><div id="divFiltros">' + chips
            + f'<div id="divMarcasFancy"><input class="fancyCheck" type="checkbox" value="{brand}" checked/></div>'
            + '<div id="divModelosFancy">'
            + ''.join(f'<input class="fancyCheck" type="checkbox" value="{value}"/>' for value in listed)
            + '</div></div>' + fragment(items, more) + '</body></html>')


class Site:
    """A scripted deRuedas behind MockTransport: a catalog per segment and pages per search."""

    def __init__(self, models=None, pages=None):
        self.models = models or {}      # (segment, exact brand) -> its models
        self.pages = pages or {}        # (segment, 'Marca:Modelo' or 'Marca', page) -> html, Response or a list of them
        self.requests = []

    @staticmethod
    def brands(segment):
        doc = soup(fixture(f'deruedas_catalog_s{segment}.html'))
        return [i['value'] for i in doc.select('#divMarcasFancy input.fancyCheck')]

    def catalog(self, segment, sent):
        if sent == 'Toyota' and (segment, sent) not in self.models:
            return fixture(f'deruedas_catalog_s{segment}.html')      # the real page
        # Like the site, a brand without models here (no used stock) is not listed.
        brands = [b for b in self.brands(segment) if b != sent or self.models.get((segment, b))]
        known = sent in brands
        return ('<div id="divFiltros"><div id="divMarcasFancy">'
                + ''.join(f'<input class="fancyCheck" type="checkbox" value="{b}"{" checked" if b == sent else ""}/>'
                          for b in brands)
                + '</div><div id="divModelosFancy">'
                + ''.join(f'<input class="fancyCheck" type="checkbox" value="{sent}:{m}"/>'
                          for m in (self.models.get((segment, sent), []) if known else []))
                + '</div></div>')

    def __call__(self, request):
        self.requests.append(request)
        query = dict(request.url.params)
        segment = int(query['segmento'])
        if query.get('weNeed') == 'divFiltros':
            return page(self.catalog(segment, query['marca']))
        answer = self.pages[segment, query.get('modelo') or query['marca'], int(query.get('pag', 1))]
        if isinstance(answer, list):
            answer = answer.pop(0) if len(answer) > 1 else answer[0]
        return answer if isinstance(answer, httpx.Response) else page(answer)

    @property
    def urls(self):
        return [str(r.url) for r in self.requests]

    def searched(self):
        """(path, segment, model or brand, page) of every request that was not a catalog."""
        out = []
        for request in self.requests:
            query = dict(request.url.params)
            if query.get('weNeed') != 'divFiltros':
                out.append((request.url.path, int(query['segmento']), query.get('modelo') or query['marca'],
                            int(query.get('pag', 1))))
        return out


class DeRuedasCase(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        # No waiting, and no slot or catalog shared between tests.
        for target, name, value in ((D, 'CRAWL_DELAY', 0), (D, 'RETRY_PAUSE', 0), (deruedas, '_next_slot', 0.0)):
            patcher = patch.object(target, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        deruedas._catalogs.clear()
        self.addCleanup(deruedas._catalogs.clear)

    def onix_site(self, pages):
        return Site({(0, 'Chevrolet'): ['Onix', 'Prisma']},
                    {(0, 'Chevrolet:Onix', number): html for number, html in pages.items()})

    async def onix(self, pages, **filters):
        site = self.onix_site(pages)
        result = await D(transport=httpx.MockTransport(site)).search({'marca': 'Chevrolet', 'modelo': 'Onix', **filters})
        return site, result


class SearchContractTests(DeRuedasCase):
    async def test_walks_161_results_and_trusts_only_the_page_marker(self):
        real = [str(c) + str(c.find_next_sibling()) for c in soup(fixture('deruedas_search.html')).select('div.divVehiculo')]
        everything = real + cards(900000, 155)
        chunks = [everything[i:i + 30] for i in range(0, 161, 30)]
        first = onix_page(chunks[0], total=161, more=True)
        # bus.asp declares the variable false in its header on every page.
        self.assertIn('var masContenido = false;', first)
        pages = {1: first, **{n: fragment(chunks[n - 1], more=n < 6) for n in range(2, 7)}}
        site, result = await self.onix(pages)

        self.assertIsInstance(result, SearchResults)
        self.assertTrue(result.complete)
        self.assertEqual(len(result), 161)
        self.assertEqual(len({item.listing_id for item in result}), 161)
        self.assertEqual([len(c) for c in chunks], [30, 30, 30, 30, 30, 11])
        self.assertEqual(site.urls, [
            BASE + '/busCraw.asp?segmento=0&marca=Chevrolet&condicion=Usados&order=6&weNeed=divFiltros&pag=1',
            BASE + '/busCraw.asp?segmento=1&marca=Chevrolet&condicion=Usados&order=6&weNeed=divFiltros&pag=1',
            SEARCH,
            *[SEARCH.replace('/bus.asp', '/busCraw.asp') + f'&weNeed=divBusqueda&pag={n}' for n in range(2, 7)]])
        self.assertTrue(all(item.atributos['Segmento'] == 'Autos' for item in result))

    async def test_urls_use_the_segment_spelling_and_percent_encoding(self):
        site = Site({(0, 'Mercedes Benz'): ['Clase A'], (0, 'Ford'): ['Coupé']}, {
            (0, 'Mercedes Benz:Clase A', 1): bus_page('Mercedes Benz', 'Clase A', cards(1, 2, 'Mercedes Benz', 'Clase A')),
            (0, 'Ford:Coupé', 1): bus_page('Ford', 'Coupé', cards(5, 1, 'Ford', 'Coupé'))})
        scraper = D(transport=httpx.MockTransport(site))
        benz = await scraper.search({'marca': 'Mercedes-Benz', 'modelo': 'clase a', 'km_max': 200000,
                                     'precio_max': 99000000})
        self.assertEqual([item.listing_id for item in benz], ['1', '2'])
        # The brand as the target writes it is not recognized: asked again with the catalog's own.
        self.assertEqual(site.urls[:2], [
            BASE + '/busCraw.asp?segmento=0&marca=Mercedes-Benz&condicion=Usados&order=6&weNeed=divFiltros&pag=1',
            BASE + '/busCraw.asp?segmento=0&marca=Mercedes%20Benz&condicion=Usados&order=6&weNeed=divFiltros&pag=1'])
        self.assertEqual(site.urls[-1], BASE + '/bus.asp?segmento=0&marca=Mercedes%20Benz'
                         '&modelo=Mercedes%20Benz%3AClase%20A&condicion=Usados&order=6')
        await scraper.search({'marca': 'Ford', 'modelo': 'Coupe'})
        self.assertEqual(site.urls[-1], BASE + '/bus.asp?segmento=0&marca=Ford&modelo=Ford%3ACoup%C3%A9'
                         '&condicion=Usados&order=6')
        for url in site.urls:
            self.assertNotRegex(url, r'kilometraje|precio|\+|,')

    async def test_year_bounds_are_sent_only_inside_the_site_slider(self):
        with patch('collectors.deruedas.date') as clock:
            clock.today.return_value = date(2026, 10, 13)
            for filters, sent in (({'anio_min': 2015, 'anio_max': 2018}, '&anio_1=2015&anio_2=2018'),
                                  ({'anio_min': 1997}, '&anio_1=1997'), ({'anio_max': 2025}, '&anio_2=2025'),
                                  ({'anio_min': 1996, 'anio_max': 2026}, ''), ({'anio_min': 1990, 'anio_max': 1993}, ''),
                                  ({'anio_min': 2026}, '&anio_1=2026'), ({'anio_min': 2027}, ''),
                                  ({'anio_max': 1996}, ''), ({'anio_max': 1997}, '&anio_2=1997'), ({}, '')):
                with self.subTest(filters=filters):
                    self.assertEqual(D()._url('/bus.asp', D._params(0, 'Fiat', '147', D._years(filters))),
                                     BASE + '/bus.asp?segmento=0&marca=Fiat&modelo=Fiat%3A147&condicion=Usados&order=6' + sent)

    async def test_year_filter_must_be_echoed_and_is_checked_again_on_each_card(self):
        items = cards(1, 3)
        old = soup(items[2])
        old.select_one('meta[itemprop="vehicleModelDate"]')['content'] = '2012'
        items[2] = str(old)
        with patch('collectors.deruedas.date') as clock:
            clock.today.return_value = date(2026, 10, 13)
            site, result = await self.onix({1: bus_page('Chevrolet', 'Onix', items, years='Desde 2015 hasta 2020')},
                                           anio_min=2015, anio_max=2020)
            self.assertEqual(site.urls[-1], SEARCH + '&anio_1=2015&anio_2=2020')
            self.assertEqual([item.listing_id for item in result], ['1', '2'])
            for chip in (None, 'Desde 2010 hasta 2020'):
                deruedas._catalogs.clear()
                with self.subTest(chip=chip), self.assertRaisesRegex(RuntimeError, 'year filter not applied'):
                    await self.onix({1: bus_page('Chevrolet', 'Onix', items, years=chip)}, anio_min=2015, anio_max=2020)

    async def test_year_bounds_are_sent_on_every_page(self):
        with patch('collectors.deruedas.date') as clock:
            clock.today.return_value = date(2026, 10, 13)
            site, result = await self.onix({
                1: bus_page('Chevrolet', 'Onix', cards(1, 30), total=31, more=True, years='Desde 2015 hasta 2020'),
                2: fragment(cards(31, 1), more=False)}, anio_min=2015, anio_max=2020)
        self.assertTrue(result.complete)
        self.assertEqual(len(result), 31)
        self.assertEqual(site.urls[-2:], [SEARCH + '&anio_1=2015&anio_2=2020',
                                          SEARCH.replace('/bus.asp', '/busCraw.asp')
                                          + '&anio_1=2015&anio_2=2020&weNeed=divBusqueda&pag=2'])

    async def test_year_filtered_zero_checks_only_the_unfiltered_first_page(self):
        unfiltered = bus_page('Chevrolet', 'Onix', cards(1, 30), total=45, more=True)
        with patch('collectors.deruedas.date') as clock:
            clock.today.return_value = date(2026, 10, 13)
            site, result = await self.onix({1: [bus_page('Chevrolet', 'Onix', total=0), unfiltered]}, anio_min=2024)
        # The model has stock: the zero is real and the other pages are never read.
        self.assertEqual(site.urls[-2:], [SEARCH + '&anio_1=2024', SEARCH])
        self.assertEqual(site.searched(), [('/bus.asp', 0, 'Chevrolet:Onix', 1)] * 2)
        self.assertEqual((list(result), result.complete), ([], True))
        # Without stock at all it is the catalog's zero.
        deruedas._catalogs.clear()
        with self.assertRaisesRegex(RuntimeError, 'catalog lists model but search found 0'):
            with patch('collectors.deruedas.date') as clock:
                clock.today.return_value = date(2026, 10, 13)
                await self.onix({1: bus_page('Chevrolet', 'Onix', total=0)}, anio_min=2024)

    async def test_search_redirects_are_never_followed(self):
        for status, location in ((301, 'bus.asp?segmento=0&marca=Chevrolet&modelo=Chevrolet%3AOnix&condicion=Usados'),
                                 (302, BASE + '/')):
            deruedas._catalogs.clear()
            with self.subTest(status=status), self.assertRaisesRegex(RuntimeError, 'unexpected redirect') as raised:
                site, _ = await self.onix({1: httpx.Response(status, headers={'location': location})})
            self.assertNotIsInstance(raised.exception, CollectorBlocked)
        site = self.onix_site({1: httpx.Response(302, headers={'location': BASE + '/'})})
        with self.assertRaises(RuntimeError):
            await D(transport=httpx.MockTransport(site)).search({'marca': 'Chevrolet', 'modelo': 'Onix'})
        self.assertEqual(site.searched(), [('/bus.asp', 0, 'Chevrolet:Onix', 1)])

    async def test_server_error_is_retried_once(self):
        good = bus_page('Chevrolet', 'Onix', cards(1, 2))
        site, result = await self.onix({1: [httpx.Response(500), good]})
        self.assertEqual(len(result), 2)
        self.assertEqual(len(site.searched()), 2)
        deruedas._catalogs.clear()
        site = self.onix_site({1: httpx.Response(500)})
        with self.assertRaisesRegex(RuntimeError, 'HTTP 500'):
            await D(transport=httpx.MockTransport(site)).search({'marca': 'Chevrolet', 'modelo': 'Onix'})
        self.assertEqual(len(site.searched()), 2)

    async def test_retry_waits_and_transport_errors_are_retried_once(self):
        calls = []

        def flaky(request):
            calls.append(request)
            if len(calls) == 1:
                raise httpx.ConnectError('reset', request=request)
            return page(fixture('deruedas_detail.html'))
        fetched = await D(transport=httpx.MockTransport(flaky)).fetch_detail_page(detail_url('830433'))
        self.assertEqual((fetched.status, len(calls)), (200, 2))

        def down(request):
            raise httpx.ConnectError('reset', request=request)
        with self.assertRaises(httpx.TransportError):
            await D(transport=httpx.MockTransport(down)).fetch_detail_page(detail_url('830433'))
        answers = [httpx.Response(503), page(fixture('deruedas_detail.html'))]
        with patch.object(D, 'RETRY_PAUSE', 30), \
                patch('collectors.deruedas.asyncio.sleep', new_callable=AsyncMock) as sleep:
            await D(transport=httpx.MockTransport(lambda request: answers.pop(0))).fetch_detail_page(detail_url('830433'))
        sleep.assert_awaited_once_with(30)

    async def test_blocks_and_challenges_fail_as_blocked_without_retry(self):
        challenge = '<html><title>Just a moment...</title><script src="/cdn-cgi/challenge-platform/x.js"></script></html>'
        for answer in (httpx.Response(403), httpx.Response(429), httpx.Response(401), page(challenge),
                       page(challenge, 503), page('<title>Attention Required! | Cloudflare</title>', 500)):
            deruedas._catalogs.clear()
            site = self.onix_site({1: answer})
            with self.subTest(status=answer.status_code), self.assertRaises(CollectorBlocked):
                await D(transport=httpx.MockTransport(site)).search({'marca': 'Chevrolet', 'modelo': 'Onix'})
            self.assertEqual(len(site.searched()), 1)

    async def test_static_block_notice_of_every_detail_page_is_not_a_challenge(self):
        html = fixture('deruedas_detail.html')
        self.assertIn('Hemos bloqueado las posibilidad de seguir consultando', html)
        fetched = await D(transport=httpx.MockTransport(lambda request: page(html))).fetch_detail_page(detail_url('830433'))
        self.assertFalse(D.parse_detail(fetched.html, fetched.url, fetched.status).gone)

    async def test_bytes_that_are_not_utf8_fail_instead_of_becoming_mojibake(self):
        latin = httpx.Response(200, content='<p>Córdoba, Luján</p>'.encode('latin-1'), headers={'content-type': 'text/html'})
        with self.assertRaisesRegex(RuntimeError, 'UTF-8'):
            await D(transport=httpx.MockTransport(lambda request: latin)).fetch_detail_page(detail_url('830433'))
        declared = httpx.Response(200, content=fixture('deruedas_detail.html').encode('utf-8'),
                                  headers={'content-type': 'text/html; charset=iso-8859-1'})
        fetched = await D(transport=httpx.MockTransport(lambda request: declared)).fetch_detail_page(detail_url('830433'))
        self.assertIn('Guaymallén', fetched.html)

    async def test_catalog_brand_is_resolved_per_segment_and_cached(self):
        site = Site({(0, 'Kia'): ['Rio', 'Sportage'], (1, 'KIA'): ['K2700']}, {
            (1, 'KIA:K2700', 1): bus_page('KIA', 'K2700', cards(1, 1, 'KIA', 'K2700')),
            (0, 'Kia:Rio', 1): bus_page('Kia', 'Rio', cards(2, 1, 'Kia', 'Rio'))})
        scraper = D(transport=httpx.MockTransport(site))
        truck = await scraper.search({'marca': 'Kia', 'modelo': 'K2700'})
        self.assertEqual([(item.listing_id, item.marca, item.atributos['Segmento']) for item in truck],
                         [('1', 'KIA', 'Utilitarios y Camionetas')])
        catalogs = [u for u in site.urls if 'divFiltros' in u]
        self.assertEqual([re.search(r'segmento=(\d)&marca=(\w+)', u).groups() for u in catalogs],
                         [('0', 'Kia'), ('1', 'Kia'), ('1', 'KIA')])
        # Another scraper within the half hour reuses both catalogs.
        car = await D(transport=httpx.MockTransport(site)).search({'marca': 'KIA', 'modelo': 'rio'})
        self.assertEqual([item.listing_id for item in car], ['2'])
        self.assertEqual(len([u for u in site.urls if 'divFiltros' in u]), 3)
        later = deruedas.time.monotonic() + D.CATALOG_TTL + 1
        with patch.object(deruedas, '_clock', lambda: later):
            await D(transport=httpx.MockTransport(site)).search({'marca': 'Kia', 'modelo': 'Rio'})
        self.assertEqual(len([u for u in site.urls if 'divFiltros' in u]), 6)

    async def test_brand_is_resolved_from_the_single_list_of_a_page_without_brand_filter(self):
        # The saved bus.asp without marca has no #divMarcasFancy: its brands are in #divModelosFancy.
        site = Site({(0, 'Kia'): ['Rio'], (1, 'KIA'): ['K2700']},
                    {(1, 'KIA:K2700', 1): bus_page('KIA', 'K2700', cards(1, 1, 'KIA', 'K2700'))})
        normal = site.catalog
        site.catalog = lambda segment, sent: normal(segment, sent) if sent in Site.brands(segment) else (
            '<div id="divFiltros"><div id="divModelosFancy">' + ''.join(
                f'<input class="fancyCheck" type="checkbox" value="{b}"/>' for b in Site.brands(segment)) + '</div></div>')
        result = await D(transport=httpx.MockTransport(site)).search({'marca': 'kia', 'modelo': 'K2700'})
        self.assertEqual([item.listing_id for item in result], ['1'])
        self.assertEqual(re.findall(r'segmento=(\d)&marca=(\w+)&condicion=Usados&order=6&weNeed=divFiltros', ' '.join(site.urls)),
                         [('0', 'kia'), ('0', 'Kia'), ('1', 'Kia'), ('1', 'KIA')])

    async def test_unrecognized_brand_filter_and_missing_brand_list_fail(self):
        echo = Site({(0, 'Fiat'): ['Cronos']})
        echo.catalog = lambda segment, sent: Site.catalog(echo, segment, sent).replace(' checked', '')
        with self.assertRaisesRegex(RuntimeError, 'brand filter not applied'):
            await D(transport=httpx.MockTransport(echo)).search({'marca': 'Fiat', 'modelo': 'Cronos'})
        with self.assertRaisesRegex(RuntimeError, 'brand catalog missing'):
            await D(transport=httpx.MockTransport(lambda request: page('<div id="divFiltros"></div>'))).search(
                {'marca': 'Fiat', 'modelo': 'Cronos'})

    async def test_recognized_brand_without_any_model_is_drift_not_an_empty_stock(self):
        real = fixture('deruedas_catalog_s0.html')
        site = Site({(0, 'Chevrolet'): ['Onix']})
        normal = site.catalog
        site.catalog = lambda segment, sent: normal(segment, sent).replace('divModelosFancy', 'divModelosFancyV2')
        drifted = {'model prefix lowercased': real.replace('value="Toyota:', 'value="toyota:'),
                   'model class renamed': real.replace('fancyCheck" type="checkbox" value="Toyota:',
                                                       'fancy" type="checkbox" value="Toyota:'),
                   'model list renamed': site}
        for name, answer in drifted.items():
            self.assertNotEqual(answer, real, name)
            deruedas._catalogs.clear()
            transport = httpx.MockTransport(site if answer is site else lambda request, html=answer: page(html))
            marca, modelo = ('Chevrolet', 'Onix') if answer is site else ('Toyota', 'Hilux')
            with self.subTest(name=name), self.assertRaisesRegex(RuntimeError, 'model catalog missing'):
                await D(transport=transport).search({'marca': marca, 'modelo': modelo})
            # Never cached as "no used stock".
            self.assertEqual(deruedas._catalogs, {})

    def test_model_resolution_against_the_segment_catalogs(self):
        toyota = {0: ['Corolla', 'Corolla Cross', 'Etios', 'Hilux SW4', 'RAV4'], 1: ['Dyna', 'Etios', 'Hiace', 'Hilux']}
        # The real Ford and Volkswagen car catalogs (samples of 2026-10-09).
        ford = {0: ['Bronco', 'EcoSport', 'Fiesta', 'Fiesta KD', 'Focus', 'Ka', 'Kuga', 'Territory']}
        vw = {0: ['CrossFox', 'Fox', 'Gol', 'Gol Country', 'Gol Trend', 'Golf']}
        for wanted, catalogs, expected in (
                ('CR-V', {0: ['Civic', 'CRV', 'HR-V']}, {0: ['CRV']}),
                ('Onix Plus', {0: ['Onix', 'Prisma'], 1: ['Montana']}, {0: ['Onix']}),
                ('Corolla Cross', toyota, {0: ['Corolla Cross']}),
                ('Corolla', toyota, {0: ['Corolla']}),
                ('Corolla Cross XEI', toyota, {0: ['Corolla Cross']}),     # longest leading model, not "Corolla"
                ('Gol Trend Highline', vw, {0: ['Gol Trend']}),
                ('SW4', toyota, {0: ['Hilux SW4']}),
                ('Hilux', toyota, {1: ['Hilux']}),              # never the SUV "Hilux SW4"
                ('Hilux SW4', toyota, {0: ['Hilux SW4']}),      # never every pickup
                ('etios', toyota, {0: ['Etios'], 1: ['Etios']}),
                # Generations the site lists apart and normalization files under the model.
                ('Fiesta', ford, {0: ['Fiesta', 'Fiesta KD']}),
                ('Fiesta KD', ford, {0: ['Fiesta KD']}),
                ('Fox', vw, {0: ['Fox', 'CrossFox']}),
                ('Gol', vw, {0: ['Gol', 'Gol Country']}),       # never "Gol Trend" or "Golf"
                ('Gol', {0: ['CrossFox', 'Fox', 'Gol', 'Gol Trend']}, {0: ['Gol']}),
                ('Palio', {0: ['Cronos', 'Nuevo Palio', 'Palio']}, {0: ['Palio', 'Nuevo Palio']}),
                ('Palio', {0: ['Cronos', 'Nuevo Palio']}, {0: ['Nuevo Palio']}),
                ('Corsa', {0: ['Classic', 'Corsa', 'Corsa II', 'Onix']}, {0: ['Corsa', 'Corsa II']}),
                ('Siena', {0: ['Cronos', 'Grand Siena', 'Siena']}, {0: ['Siena', 'Grand Siena']}),
                # A version on the site: searched under its model.
                ('Stepway', {0: ['Sandero', 'Logan'], 1: ['Kangoo']}, {0: ['Sandero']}),
                ('Onix', {0: ['Onix', 'Prisma']}, {0: ['Onix']}),
                ('Clase', {0: ['Clase A', 'Clase B', 'Clase C', 'Clase E']}, {}),   # too ambiguous
                ('Supra', toyota, {}), ('--', toyota, {})):
            with self.subTest(wanted=wanted):
                self.assertEqual(D._models(wanted, catalogs), expected)

    async def test_hilux_only_among_pickups_and_etios_in_both_segments_merged_by_cod(self):
        site = Site(pages={
            (1, 'Toyota:Hilux', 1): bus_page('Toyota', 'Hilux', cards(10, 2, 'Toyota', 'Hilux')),
            (0, 'Toyota:Etios', 1): bus_page('Toyota', 'Etios', cards(20, 2, 'Toyota', 'Etios')),
            (1, 'Toyota:Etios', 1): bus_page('Toyota', 'Etios', cards(21, 2, 'Toyota', 'Etios'))})
        scraper = D(transport=httpx.MockTransport(site))
        hilux = await scraper.search({'marca': 'Toyota', 'modelo': 'Hilux'})
        self.assertEqual([item.listing_id for item in hilux], ['10', '11'])
        self.assertEqual(site.searched(), [('/bus.asp', 1, 'Toyota:Hilux', 1)])
        etios = await scraper.search({'marca': 'Toyota', 'modelo': 'Etios'})
        self.assertEqual([(item.listing_id, item.extra['segmento']) for item in etios], [('20', 0), ('21', 0), ('22', 1)])
        self.assertEqual(site.searched()[1:], [('/bus.asp', 0, 'Toyota:Etios', 1), ('/bus.asp', 1, 'Toyota:Etios', 1)])

    async def test_fiesta_also_walks_the_fiesta_kd_the_site_lists_apart(self):
        site = Site({(0, 'Ford'): ['EcoSport', 'Fiesta', 'Fiesta KD', 'Ka'], (1, 'Ford'): ['Ranger']}, {
            (0, 'Ford:Fiesta', 1): bus_page('Ford', 'Fiesta', cards(1, 2, 'Ford', 'Fiesta')),
            (0, 'Ford:Fiesta KD', 1): bus_page('Ford', 'Fiesta KD', cards(2, 2, 'Ford', 'Fiesta KD'))})
        result = await D(transport=httpx.MockTransport(site)).search({'marca': 'Ford', 'modelo': 'Fiesta'})
        self.assertEqual(site.searched(), [('/bus.asp', 0, 'Ford:Fiesta', 1), ('/bus.asp', 0, 'Ford:Fiesta KD', 1)])
        self.assertEqual([(item.listing_id, item.modelo) for item in result], [('1', 'Fiesta'), ('2', 'Fiesta'), ('3', 'Fiesta KD')])
        self.assertTrue(result.complete)

    async def test_brand_only_target_searches_each_segment_that_lists_the_brand(self):
        site = Site(pages={(0, 'Toyota', 1): bus_page('Toyota', None, cards(1, 1, 'Toyota', 'Corolla') + cards(2, 1, 'Toyota', 'Yaris')),
                           (1, 'Toyota', 1): bus_page('Toyota', None, cards(3, 1, 'Toyota', 'Hilux'))})
        result = await D(transport=httpx.MockTransport(site)).search({'marca': 'toyota'})
        self.assertEqual([(item.listing_id, item.modelo) for item in result], [('1', 'Corolla'), ('2', 'Yaris'), ('3', 'Hilux')])
        self.assertEqual([u.replace(BASE, '') for u in site.urls], [
            '/busCraw.asp?segmento=0&marca=toyota&condicion=Usados&order=6&weNeed=divFiltros&pag=1',
            '/busCraw.asp?segmento=0&marca=Toyota&condicion=Usados&order=6&weNeed=divFiltros&pag=1',
            '/busCraw.asp?segmento=1&marca=Toyota&condicion=Usados&order=6&weNeed=divFiltros&pag=1',
            '/bus.asp?segmento=0&marca=Toyota&condicion=Usados&order=6',
            '/bus.asp?segmento=1&marca=Toyota&condicion=Usados&order=6'])
        deruedas._catalogs.clear()
        site.pages[0, 'Toyota', 1] = bus_page('Toyota', None, cards(1, 1, 'Toyota', 'Corolla') + cards(2, 1, 'Ford', 'Ka'))
        with self.assertRaisesRegex(RuntimeError, 'filter not applied'):
            await D(transport=httpx.MockTransport(site)).search({'marca': 'Toyota'})

    async def test_silently_ignored_model_filter_is_never_read_as_results(self):
        # The real page: title and JSON-LD name "Gol Trend", the cards are the whole brand.
        ignored = fixture('deruedas_ignored.html')
        self.assertIn('Volkswagen Gol Trend Usados', ignored)
        self.assertEqual(len(soup(ignored).select('#divModelosFancy input')), 26)
        site = Site({(0, 'Volkswagen'): ['Gol', 'Gol Trend']}, {(0, 'Volkswagen:Gol Trend', 1): ignored})
        with self.assertRaisesRegex(RuntimeError, 'model filter not applied'):
            await D(transport=httpx.MockTransport(site)).search({'marca': 'Volkswagen', 'modelo': 'Gol Trend'})

        good = onix_page(cards(1, 30), total=31, more=True)
        broken = {
            'another chip': good.replace('modeloval="Chevrolet:Onix"', 'modeloval="Chevrolet:Prisma"'),
            'no chip': re.sub(r'<div class="toggleModeloLink cerrarItem_4"[^>]*>[^<]*</div>', '', good),
            'brand not checked': re.sub(r'<input checked="" (class="fancyCheck" type="checkbox" value="Chevrolet"/>)', r'<input \1', good),
            'two models listed': good.replace('<div id="divModelosFancy" class="recuadro">',
                                              '<div id="divModelosFancy" class="recuadro"><input class="fancyCheck" value="Chevrolet:Prisma"/>'),
            'card of another model': onix_page(cards(1, 29) + [card(30, model='Prisma')], total=31, more=True),
            'card of another brand': onix_page(cards(1, 29) + [card(30, brand='Fiat')], total=31, more=True),
        }
        for name, first in broken.items():
            self.assertNotEqual(first, good, name)
            deruedas._catalogs.clear()
            with self.subTest(name=name), self.assertRaisesRegex(RuntimeError, 'model filter not applied'):
                await self.onix({1: first, 2: fragment(cards(31, 1), more=False)})
        # Later pages carry no chips: every card is the proof.
        deruedas._catalogs.clear()
        with self.assertRaisesRegex(RuntimeError, 'model filter not applied'):
            await self.onix({1: good, 2: fragment([card(31, model='Prisma')], more=False)})
        deruedas._catalogs.clear()
        _, result = await self.onix({1: good, 2: fragment(cards(31, 1), more=False)})
        self.assertEqual(len(result), 31)

    async def test_zero_results_for_a_catalog_model_fail_and_forget_the_catalog(self):
        zero = fixture('deruedas_zero.html')
        self.assertIn('"numberOfItems":0', zero)
        site = Site({(0, 'Toyota'): ['Corolla', 'Corolla-Cross']}, {(0, 'Toyota:Corolla-Cross', 1): zero})
        with self.assertRaisesRegex(RuntimeError, 'catalog lists model but search found 0'):
            await D(transport=httpx.MockTransport(site)).search({'marca': 'Toyota', 'modelo': 'Corolla-Cross'})
        self.assertNotIn((0, 'toyota'), deruedas._catalogs)
        self.assertIn((1, 'toyota'), deruedas._catalogs)

    async def test_model_or_brand_without_stock_is_an_empty_complete_result(self):
        site = Site()
        for filters in ({'marca': 'Toyota', 'modelo': 'Supra'}, {'marca': 'Tesla', 'modelo': 'Model 3'}, {'marca': 'Tesla'}):
            with self.subTest(filters=filters), self.assertLogs('collectors.deruedas', level='INFO') as logs:
                result = await D(transport=httpx.MockTransport(site)).search(filters)
                self.assertIsInstance(result, SearchResults)
                self.assertEqual((list(result), result.complete), ([], True))
                self.assertIn('no used stock', logs.output[-1])
        self.assertEqual(site.searched(), [])

    async def test_search_needs_marca_before_any_request(self):
        site = Site()
        for filters in ({}, {'modelo': 'Corolla'}, {'marca': '  ', 'modelo': 'Corolla'}):
            with self.subTest(filters=filters), self.assertRaisesRegex(ValueError, 'necesita marca'):
                await D(transport=httpx.MockTransport(site)).search(filters)
        self.assertEqual(site.requests, [])

    async def test_missing_count_marker_or_cards_fail(self):
        good = onix_page(cards(1, 3), total=3, more=False)
        broken = {
            'result count missing': good.replace('"@type":"SearchResultsPage"', '"@type":"WebPage"'),
            'result count missing ': good.replace('"numberOfItems":3', '"numberOfItems":"3"'),
            'pagination marker missing': good.replace('<script class="newScript">', '<script>'),
            'vehicle cards missing': onix_page([], total=3, more=False),
        }
        for message, first in broken.items():
            self.assertNotEqual(first, good, message)
            deruedas._catalogs.clear()
            with self.subTest(message=message), self.assertRaisesRegex(RuntimeError, message.strip()):
                await self.onix({1: first})
        deruedas._catalogs.clear()
        with self.assertRaisesRegex(RuntimeError, 'pagination marker missing'):
            await self.onix({1: onix_page(cards(1, 30), total=40, more=True), 2: '<div id="divBusqueda"></div>'})

    async def test_a_page_without_any_used_card_is_drift_not_an_empty_result(self):
        for old, new in (('/Usados/', '/usados/'), ('/images/autos/', '/images/vehiculos/')):
            drifted = [c.replace(old, new) for c in cards(1, 30)]
            self.assertNotEqual(drifted, cards(1, 30))
            for pages in ({1: onix_page(drifted, total=30, more=False)},
                          {1: onix_page(cards(1, 30), total=60, more=True), 2: fragment(drifted, more=False)}):
                deruedas._catalogs.clear()
                with self.subTest(old=old, pages=len(pages)), \
                        self.assertRaisesRegex(RuntimeError, 'cards outside used stock'):
                    await self.onix(pages)
        # One misfiled new unit among used cards is still dropped quietly.
        deruedas._catalogs.clear()
        _, result = await self.onix({1: onix_page(cards(1, 2) + [card(3).replace('/Usados/', '/Nuevos/')], total=3, more=False)})
        self.assertEqual([item.listing_id for item in result], ['1', '2'])

    async def test_walk_stops_on_marker_short_page_empty_shell_or_one_page_past_the_count(self):
        shell = fixture('deruedas_past_end.html')
        self.assertEqual(D.parse_search(shell), [])
        scenarios = {
            'marker says no more': ({1: onix_page(cards(1, 30), total=60, more=True), 2: fragment(cards(31, 30), more=False)}, 60, 2),
            'short page': ({1: onix_page(cards(1, 30), total=45, more=True), 2: fragment(cards(31, 15), more=True)}, 45, 2),
            'empty shell past the end': ({1: onix_page(cards(1, 30), total=60, more=True), 2: fragment(cards(31, 30), more=True),
                                          3: shell}, 60, 3),
            'ad published mid-walk': ({1: onix_page(cards(1, 30), total=60, more=True), 2: fragment(cards(31, 30), more=True),
                                       3: fragment(cards(61, 1), more=False)}, 61, 3),
            'never beyond one extra page': ({1: onix_page(cards(1, 30), total=30, more=True),
                                             2: fragment(cards(31, 30), more=True)}, 60, 2),
        }
        for name, (pages, found, requested) in scenarios.items():
            deruedas._catalogs.clear()
            with self.subTest(name=name):
                site, result = await self.onix(pages)
                self.assertEqual((len(result), result.complete), (found, True))
                self.assertEqual([p[3] for p in site.searched()], list(range(1, requested + 1)))

    async def test_repeated_cards_count_once_and_a_shortfall_is_walked_again(self):
        # An ad published at the top repeats the last five of page 1 on page 2.
        pages = {1: onix_page(cards(1, 30), total=65, more=True), 2: fragment(cards(26, 30), more=True),
                 3: fragment(cards(56, 5), more=False)}
        site, result = await self.onix(pages)
        self.assertEqual(len(result), 60)
        self.assertEqual((result.complete, result.reason), (False, 'deruedas: 60/65 avisos'))
        self.assertEqual([p[3] for p in site.searched()], [1, 2, 3, 1, 2, 3])
        # Two missing of 62 are within tolerance: one walk.
        deruedas._catalogs.clear()
        pages[1] = onix_page(cards(1, 30), total=62, more=True)
        site, result = await self.onix(pages)
        self.assertEqual((len(result), result.complete, len(site.searched())), (60, True, 3))
        # The second walk finds what the first one lost.
        deruedas._catalogs.clear()
        pages = {1: onix_page(cards(1, 30), total=65, more=True), 2: fragment(cards(31, 30), more=True),
                 3: [fixture('deruedas_past_end.html'), fragment(cards(61, 5), more=False)]}
        site, result = await self.onix(pages)
        self.assertEqual((len(result), result.complete, result.reason), (65, True, None))

    async def test_results_beyond_the_page_cap_are_kept_as_incomplete(self):
        self.assertEqual(D.MAX_PAGES * D.PAGE_SIZE, 1800)
        with patch.object(D, 'MAX_PAGES', 2):
            site, result = await self.onix({1: onix_page(cards(1, 30), total=200, more=True),
                                            2: fragment(cards(31, 30), more=True)})
        self.assertEqual((len(result), result.complete), (60, False))
        self.assertEqual(result.reason, 'deruedas: 200 resultados superan el tope')
        self.assertEqual([p[3] for p in site.searched()], [1, 2])

    async def test_km_is_filtered_here_and_unknown_km_is_kept(self):
        real = [str(c) for c in soup(fixture('deruedas_search.html')).select('div.divVehiculo')]
        site, result = await self.onix({1: onix_page(real, total=6, more=False)}, km_max=90000)
        # 85000 km and the two without a stated or plausible limit breach; 92000+ are out.
        self.assertEqual({item.listing_id: item.km for item in result}, {'829671': 85000, '775675': None, '806046': 67000})

    async def test_requests_of_the_whole_process_share_one_slot_per_crawl_delay(self):
        now, slept = [1000.0], []

        async def sleep(seconds):
            if seconds:
                slept.append(seconds)
                now[0] += seconds
        html = fixture('deruedas_detail.html')
        with patch.object(D, 'CRAWL_DELAY', 6.0), patch.object(deruedas, '_clock', lambda: now[0]), \
                patch.object(deruedas, '_next_slot', 0.0), patch('collectors.deruedas.asyncio.sleep', sleep):
            await D(transport=httpx.MockTransport(lambda request: page(html))).fetch_detail_page(detail_url('830433'))
            # Another collector instance (enrichment next to a crawl) waits for the same slot.
            await D(transport=httpx.MockTransport(lambda request: page(html))).fetch_detail_page(detail_url('830433'))
            now[0] += 2.5
            await D(transport=httpx.MockTransport(lambda request: page(html))).fetch_detail_page(detail_url('830433'))
            now[0] += 60
            await D(transport=httpx.MockTransport(lambda request: page(html))).fetch_detail_page(detail_url('830433'))
        self.assertEqual(slept, [6.0, 3.5])

    async def test_a_late_wake_up_never_shortens_the_next_gap(self):
        now, sent, stalls = [1000.0], [], [1.5]

        async def sleep(seconds):
            # The shared loop stalls 1.5 s on the first wake-up.
            now[0] += seconds + (stalls.pop() if stalls else 0)

        def answer(request):
            sent.append(now[0])
            return page(fixture('deruedas_detail.html'))
        with patch.object(D, 'CRAWL_DELAY', 6.0), patch.object(deruedas, '_clock', lambda: now[0]), \
                patch('collectors.deruedas.asyncio.sleep', sleep):
            for _ in range(3):
                await D(transport=httpx.MockTransport(answer)).fetch_detail_page(detail_url('830433'))
        self.assertEqual([b - a for a, b in zip(sent, sent[1:])], [7.5, 6.0])

        # Two requests already waiting: the second must not keep a slot booked by the clock.
        now[0], sent[:], stalls[:], real_sleep = 2000.0, [], [1.5], asyncio.sleep

        async def stalled(seconds):
            wake = now[0] + seconds
            await real_sleep(0)         # both waiters sleep before the first one wakes
            now[0] = max(now[0], wake) + (stalls.pop() if stalls else 0)
        with patch.object(D, 'CRAWL_DELAY', 6.0), patch.object(deruedas, '_clock', lambda: now[0]), \
                patch('collectors.deruedas.asyncio.sleep', stalled):
            await asyncio.gather(*(D(transport=httpx.MockTransport(answer)).fetch_detail_page(detail_url('830433'))
                                   for _ in range(3)))
        self.assertEqual([b - a for a, b in zip(sent, sent[1:])], [7.5, 6.0])

    async def test_concurrent_crawl_and_enrichment_requests_each_wait_their_own_slot(self):
        now, starts, real_sleep = [1000.0], [], asyncio.sleep

        async def sleep(seconds):
            wake = now[0] + seconds
            await real_sleep(0)         # lets the other requests reach the throttle meanwhile
            now[0] = max(now[0], wake)

        def at_start(handler):
            def record(request):
                starts.append(now[0])
                return handler(request)
            return record
        html = fixture('deruedas_detail.html')
        site = self.onix_site({1: onix_page(cards(1, 3), total=3, more=False)})

        def detail():
            transport = httpx.MockTransport(at_start(lambda request: page(html)))
            return D(transport=transport).fetch_detail_page(detail_url('830433'))
        with patch.object(D, 'CRAWL_DELAY', 6.0), patch.object(deruedas, '_clock', lambda: now[0]), \
                patch('collectors.deruedas.asyncio.sleep', sleep):
            await asyncio.gather(detail(), detail(),
                                 D(transport=httpx.MockTransport(at_start(site))).search({'marca': 'Chevrolet', 'modelo': 'Onix'}))
        self.assertEqual(len(starts), 5)
        self.assertEqual([b - a for a, b in zip(starts, starts[1:])], [6.0] * 4)

    async def test_every_request_and_retry_goes_out_one_crawl_delay_after_the_previous(self):
        now, sent = [1000.0], []

        async def sleep(seconds):
            now[0] += seconds

        def stamped(handler):
            def answer(request):
                sent.append(now[0])
                return handler(request)
            return answer
        site = self.onix_site({1: onix_page(cards(1, 30), total=40, more=True), 2: fragment(cards(31, 10), more=False)})
        failures = [httpx.ConnectError('reset')]

        def flaky(request):
            if failures:
                raise failures.pop()
            return page(fixture('deruedas_detail.html'))
        with patch.object(D, 'CRAWL_DELAY', 6.0), patch.object(deruedas, '_clock', lambda: now[0]), \
                patch('collectors.deruedas.asyncio.sleep', sleep):
            result = await D(transport=httpx.MockTransport(stamped(site))).search({'marca': 'Chevrolet', 'modelo': 'Onix'})
            # Enrichment on another instance, retrying a reset connection.
            await D(transport=httpx.MockTransport(stamped(flaky))).fetch_detail_page(detail_url('830433'))
        self.assertEqual(len(result), 40)
        # Two catalogs, bus.asp, busCraw page 2, then the detail and its retry.
        self.assertEqual(len(sent), 6)
        self.assertEqual([b - a for a, b in zip(sent, sent[1:])], [6.0] * 5)

    async def test_the_next_slot_counts_from_the_end_of_a_slow_request(self):
        now, sent = [1000.0], []

        async def sleep(seconds):
            now[0] += seconds

        def slow(request):
            sent.append(now[0])
            now[0] += 4.0               # handshake and answer take 4 s
            return page(fixture('deruedas_detail.html'))
        with patch.object(D, 'CRAWL_DELAY', 6.0), patch.object(deruedas, '_clock', lambda: now[0]), \
                patch('collectors.deruedas.asyncio.sleep', sleep):
            for _ in range(2):
                await D(transport=httpx.MockTransport(slow)).fetch_detail_page(detail_url('830433'))
        self.assertEqual(sent, [1000.0, 1010.0])


class CardTests(unittest.TestCase):
    def setUp(self):
        self.cards = {item.listing_id: item for item in D.parse_search(fixture('deruedas_search.html'), 0)}

    def test_client_agency_card_with_financing_badge(self):
        item = self.cards['830268']
        self.assertEqual((item.source, item.url), ('deruedas', BASE + '/vendo/Chevrolet/Onix/Usados/Cordoba?cod=830268'))
        self.assertEqual((item.vendedor, item.vendedor_nombre), ('agencia', 'La Reserva Automotores'))
        # The site files the Onix Plus sedan under Onix, with "Plus" in the version.
        self.assertEqual((item.marca, item.modelo, item.version), ('Chevrolet', 'Onix Plus', 'Plus LS 1.2 90cv (L19)'))
        self.assertEqual((item.precio, item.moneda, item.anio, item.km), (16500000, 'ARS', 2020, 92000))
        self.assertEqual((item.ubicacion, item.combustible, item.transmision), ('Capital, Córdoba', 'Nafta', None))
        # "Entregá $ 8.250.000 y cuotas" is the site's simulator: not the price, not in the title.
        self.assertEqual((item.extra['financiable'], item.extra['entrega_sugerida_ars']), (True, 8250000))
        self.assertEqual((item.price_partial, item.price_partial_reason), (False, None))
        self.assertEqual(item.titulo, 'Chevrolet Onix Plus LS 1.2 90cv (L19)')
        self.assertEqual(item.extra['codUsr'], '288358')
        self.assertEqual(item.atributos, {'Combustible': 'Nafta', 'Segmento': 'Autos'})
        self.assertIsNone(item.published_at)

    def test_client_linked_by_user_name_is_an_agency(self):
        # Live cards of 2026-10-14: the client's link is /@slug (nombreUsuario), no longer ?codUsr=N.
        items = {item.listing_id: item for item in D.parse_search(fixture('deruedas_cards_slug.html'), 0)}
        self.assertEqual(list(items), ['830448', '827686', '830345'])
        item = items['830448']
        self.assertEqual((item.vendedor, item.vendedor_nombre), ('agencia', 'Briones Automotores'))
        self.assertEqual(item.extra['nombreUsuario'], 'briones-automotores')
        self.assertNotIn('codUsr', item.extra)
        # The same ad's detail page, read the same day.
        self.assertEqual((item.precio, item.moneda, item.anio, item.km, item.ubicacion, item.combustible),
                         (19900000, 'ARS', 2018, 109000, 'Guaymallén, Mendoza', 'GNC'))
        # A province link on the same card is not the seller's.
        self.assertEqual((items['827686'].vendedor, items['827686'].vendedor_nombre), ('agencia', 'Pelu Cars'))
        self.assertEqual(items['827686'].ubicacion, 'Capital, San Juan')
        self.assertEqual((items['830345'].vendedor, items['830345'].vendedor_nombre), (None, None))
        self.assertFalse({'codUsr', 'nombreUsuario'} & set(items['830345'].extra))

    def test_usd_price_is_the_visible_one_not_the_ars_microdata(self):
        item = self.cards['829671']
        self.assertEqual((item.precio, item.moneda), (19000, 'USD'))
        self.assertEqual(item.extra['precio_ars_sitio'], 29260000)
        self.assertNotIn('financiable', item.extra)

    def test_unknown_km_seller_without_logo_and_other_provinces(self):
        # No km line: unknown, although itemCondition says NewCondition.
        self.assertIsNone(self.cards['775675'].km)
        self.assertEqual(self.cards['775675'].ubicacion, 'Maipú, Mendoza')
        # No client logo: the detail decides (this one is an agency there).
        self.assertEqual((self.cards['824503'].vendedor, self.cards['824503'].vendedor_nombre), (None, None))
        self.assertTrue(self.cards['824503'].extra['financiable'])
        self.assertEqual(self.cards['806046'].ubicacion, 'Capital, Buenos Aires')
        self.assertEqual(self.cards['806046'].extra['provincia'], 'Buenos Aires')
        self.assertEqual(list(self.cards), ['830268', '824503', '829671', '775675', '806046', '830458'])

    def test_first_photo_in_full_size_and_placeholders_ignored(self):
        self.assertEqual(self.cards['830268'].imagenes,
                         [BASE + '/images/autos/Chevrolet-Onix-2020/830/830268_1_im.jpg?edit=2'])
        for src in ('/images/design/sinFotos_2.gif?edit=3', BASE + '/images/autos/Chevrolet-Onix-2019/830/111111_1_tr.jpg'):
            doc = soup(card(1))
            doc.select_one('img.imgCar_1')['src'] = src
            with self.subTest(src=src):
                self.assertEqual(D.parse_search(str(doc))[0].imagenes, [])

    def test_missing_version_and_exclusions_and_no_km_guessing(self):
        html = fixture('deruedas_cards_misc.html')
        self.assertEqual(len(soup(html).select('div.divVehiculo')), 4)
        kept = {item.listing_id: item for item in D.parse_search(html)}
        # 785873 is new ("Consultar", "0 Km") and 830396 a savings plan ("49 Cuota/s").
        self.assertEqual(list(kept), ['830047', '826136'])
        self.assertIsNone(kept['830047'].version)
        self.assertEqual(kept['830047'].titulo, 'Volkswagen Gol Trend')
        self.assertEqual(kept['826136'].km, 123456)
        self.assertEqual(kept['830047'].atributos, {'Combustible': 'Nafta'})

    def test_price_and_km_texts(self):
        for text, expected in (('$ 16.500.000', (16500000, 'ARS')), ('U$ 19.000', (19000, 'USD')),
                               ('U$S 19.000', (19000, 'USD')), ('US$ 950', (950, 'USD')), ('$ 14500000', (14500000, 'ARS')),
                               ('Consultar', (None, None)), ('$ 1', (None, None)), ('$ 0', (None, None)),
                               ('Entregá $ 8.250.000 y cuotas', (None, None)), ('', (None, None)), (None, (None, None))):
            with self.subTest(text=text):
                self.assertEqual(deruedas._price(text), expected)
        self.assertEqual([deruedas._km(t) for t in ('92000 Km', '112000 km', '1 Km', '0 Km', 'No Especificado', 'KMT 1', None)],
                         [92000, 112000, None, None, None, None, None])

    def test_card_identity_must_be_unambiguous(self):
        other = card(1).replace('/vendo/Chevrolet/Onix/Usados/Mendoza?cod=1" itemprop="url"',
                                '/vendo/Chevrolet/Onix/Usados/Mendoza?cod=2" itemprop="url"')
        self.assertNotEqual(other, card(1))
        for html, message in ((other, 'another vehicle'), (card(1).replace('id="car_1"', 'id="car_x"'), 'without ID'),
                              (re.sub(r'href="[^"]*"', 'href="#"', card(1)), 'another vehicle')):
            with self.subTest(message=message), self.assertRaisesRegex(RuntimeError, message):
                D.parse_search(html)

    def test_accented_path_is_encoded_in_the_stored_url(self):
        html = card(1, 'Ford', 'Coupé').replace('/vendo/Chevrolet/Onix/', '/vendo/Ford/Coupé/')
        self.assertEqual(D.parse_search(html)[0].url, BASE + '/vendo/Ford/Coup%C3%A9/Usados/Mendoza?cod=1')

    def test_dot_segments_never_reach_a_stored_url(self):
        for path in ('/vendo/%2E%2E/%2E%2E/special/Usados/Mendoza', '/vendo/../ajax/Usados/Mendoza',
                     '/vendo/Chevrolet/./Usados/Mendoza'):
            html = card(1).replace('/vendo/Chevrolet/Onix/Usados/Mendoza', path)
            self.assertNotEqual(html, card(1))
            with self.subTest(path=path), self.assertRaisesRegex(RuntimeError, 'card without detail link'):
                D.parse_search(html)

    def test_versions_the_site_files_under_another_model_get_their_own(self):
        items = {item.listing_id: item for item in D.parse_search(fixture('deruedas_cards_onix.html'), 0)}
        items['830268'] = self.cards['830268']
        models = seed_catalog()
        for cod, modelo, titulo in (
                ('830268', 'Onix Plus', 'Chevrolet Onix Plus LS 1.2 90cv (L19)'),
                ('828764', 'Onix Plus', 'Chevrolet Onix Plus Premier II 1.0t AT (L24)'),
                ('782280', 'Onix Plus', 'Chevrolet Onix Plus Joy Black 1.4 4ptas. 98cv (L19)'),
                # "Plus" only as the version's first word: "Joy+" and "AT Plus" are Onix trims.
                ('826264', 'Onix', 'Chevrolet Onix LTZ 1.0T AT Plus (L26)'),
                ('824503', 'Onix', 'Chevrolet Onix Joy+ 1.4 LS 98cv (L17)')):
            item = items.get(cod) or self.cards[cod]
            with self.subTest(cod=cod):
                self.assertEqual((item.marca, item.modelo, item.titulo), ('Chevrolet', modelo, titulo))
                match = resolve_vehicle(models, title=item.titulo, source_make=item.marca,
                                        source_model=item.modelo, source_version=item.version)
                self.assertEqual((match.make, match.model), ('Chevrolet', modelo))
        stepway = card(1, 'Renault', 'Sandero').replace('Joy 1.4 LS 98cv (L17)', 'Stepway 1.6 Privilege')
        self.assertNotEqual(stepway, card(1, 'Renault', 'Sandero'))
        self.assertEqual([(i.modelo, i.titulo) for i in D.parse_search(stepway)],
                         [('Stepway', 'Renault Sandero Stepway 1.6 Privilege')])


class DetailTests(DeRuedasCase):
    def test_client_agency_detail(self):
        raw = fixture('deruedas_detail.html')
        item = D.parse_detail(raw, detail_url('830433')).listing
        self.assertEqual((item.source, item.listing_id, item.url), ('deruedas', '830433', detail_url('830433')))
        self.assertEqual(item.titulo, 'Toyota Corolla 2.0 XLI CVT (L23)')
        self.assertEqual((item.marca, item.modelo, item.version), ('Toyota', 'Corolla', '2.0 XLI CVT (L23)'))
        self.assertEqual((item.precio, item.moneda, item.anio, item.km), (38500000, 'ARS', 2024, 27000))
        self.assertEqual((item.ubicacion, item.combustible, item.transmision),
                         ('Guaymallén, Mendoza', 'Nafta', 'Caja automática'))
        self.assertEqual((item.vendedor, item.vendedor_nombre), ('agencia', 'Briones Automotores'))
        self.assertEqual(item.imagenes, [f'{BASE}/images/autos/Toyota-Corolla-2024/830/830433_{n}_im.jpg?edit=2'
                                         for n in range(1, 9)])
        self.assertTrue(item.descripcion.startswith('BRIONES AUTOMOTORES\nCon amplia trayectoria'))
        self.assertEqual({k: v for k, v in item.atributos.items() if not k.startswith('Catálogo')}, {
            'Año': '2024', 'Kilometraje': '27000 Km', 'Precio': '$ 38.500.000', 'Ubicación': 'Mendoza',
            'Permuta por menor': 'SI', 'Permuta por mayor': 'SI'})
        self.assertEqual(item.atributos['Catálogo Transmisión'], 'Caja automática')
        self.assertTrue(item.atributos['Catálogo equipamiento'].startswith('Aire acondicionado, Dirección asistida'))
        # Volatile on every fetch: neither attributes nor a publication date.
        self.assertIn('Visitas:', raw)
        self.assertFalse({'Visitas', 'Última actualización'} & set(item.atributos))
        self.assertEqual(item.extra, {'ultima_actualizacion': 'Hoy', 'codVer': 40680, 'precio_ars_sitio': 38500000})
        self.assertIsNone(item.published_at)
        self.assertFalse(item.price_partial)

    def test_usd_detail_without_catalog_version(self):
        item = D.parse_detail(fixture('deruedas_detail_usd.html'), detail_url('828256')).listing
        self.assertEqual((item.precio, item.moneda), (180000, 'USD'))
        self.assertEqual(item.extra, {'ultima_actualizacion': 'Ayer', 'precio_ars_sitio': 277200000})
        self.assertEqual((item.km, item.transmision, item.ubicacion), (None, None, 'Capital, San Juan'))
        self.assertNotIn('Catálogo equipamiento', item.atributos)
        self.assertEqual(item.vendedor, 'agencia')

    def test_seller_type_and_name_only_for_site_clients(self):
        particular = D.parse_detail(fixture('deruedas_detail_particular.html'), detail_url('807381')).listing
        self.assertEqual((particular.vendedor, particular.vendedor_nombre), ('particular', None))
        # Sales statistics without being a client: an agency, but its contact is a person.
        nonclient = D.parse_detail(fixture('deruedas_detail_nonclient.html'), detail_url('824503')).listing
        self.assertEqual((nonclient.vendedor, nonclient.vendedor_nombre), ('agencia', None))
        self.assertEqual((nonclient.precio, nonclient.ubicacion), (14500000, 'Godoy Cruz, Mendoza'))
        for name in ('deruedas_detail_particular.html', 'deruedas_detail_nonclient.html'):
            # The redacted person, in the live markup of the private name.
            self.assertIn('<b><span style="font-size:20px; color: #666666;">Vendedor Privado</span></b>', fixture(name))
            self.assertNotIn('Vendedor Privado', json.dumps(D.parse_detail(fixture(name), detail_url(ACTIVE[name])).listing.to_dict()))

    def test_any_single_dealer_signal_means_agency(self):
        # Signals vary per dealer (d02 830431 shows only the maps link); any one is enough.
        raw = fixture('deruedas_detail_particular.html')
        place = '<b><h2><span>Mendoza, Capital</span></h2></b>'
        for signal, html in (
                ('maps', raw.replace(place, f'<a class="link" href="#" id="linkMapsGoogle" rel="nofollow">{place}</a>')),
                ('hours', raw.replace('<div id="horariosTodos"></div>',
                                      '<div id="horariosTodos"><span class="texto">Lunes: 09:00 a 19:00</span></div>')),
                ('client', raw.replace('<b><span style="font-size:20px; color: #666666;">Vendedor Privado</span></b>',
                                       '<a class="buscarMas titulo" href="/bus.asp?codUsr=1">Agencia Uno</a>'))):
            self.assertNotEqual(html, raw)
            with self.subTest(signal=signal):
                item = D.parse_detail(html, detail_url('807381')).listing
                self.assertEqual((item.vendedor, item.vendedor_nombre),
                                 ('agencia', 'Agencia Uno' if signal == 'client' else None))
                self.assertEqual(item.ubicacion, 'Capital, Mendoza')

    def test_fuel_is_the_ad_own_not_the_catalog(self):
        item = D.parse_detail(fixture('deruedas_detail_gnc.html'), detail_url('725808')).listing
        self.assertEqual((item.combustible, item.atributos['Catálogo Combustible']), ('GNC', 'Nafta'))
        self.assertEqual((item.precio, item.moneda, item.extra['precio_ars_sitio']), (1000, 'USD', 1540000))
        self.assertEqual(item.ubicacion, 'Almirante Brown, Buenos Aires')

    def test_paid_installments_flag_the_price_and_financing_boilerplate_does_not(self):
        item = D.parse_detail(fixture('deruedas_detail_partial.html'), detail_url('822494')).listing
        self.assertIn('32 CUOTAS PAGASVendo', item.descripcion)
        self.assertEqual((item.price_partial, item.price_partial_reason), (True, 'plan (deruedas): cuotas pagas'))
        self.assertEqual(item.precio, 12000000)
        raw = fixture('deruedas_detail.html')
        for text, partial in (('Financiación en 12, 24 y 36 cuotas fijas. Entrega mínima y cuotas con DNI.', False),
                              ('Transfiero plan de ahorro, 40 cuotas pagas', True), ('Plan adjudicado, retira ya', True),
                              ('Auto adjudicada de Círculo Cerrado', True), ('Planeamos viajar, por eso vendo', False)):
            html = raw.replace('BRIONES AUTOMOTORES<br/>', text + '<br/>')
            self.assertNotEqual(html, raw)
            with self.subTest(text=text):
                self.assertEqual(D.parse_detail(html, detail_url('830433')).listing.price_partial, partial)

    def test_unavailable_box_proves_gone_even_when_microdata_says_in_stock(self):
        raw = fixture('deruedas_detail_unavailable.html')
        self.assertIn('https://schema.org/InStock', raw)
        detail = D.parse_detail(raw, detail_url('750000'))
        self.assertEqual((detail.gone, detail.gone_reason, detail.listing), (True, 'no disponible (InStock)', None))
        # The box is the proof, for this ad only.
        with self.assertRaisesRegex(RuntimeError, 'another vehicle'):
            D.parse_detail(raw, detail_url('750001'))

    def test_unavailable_text_outside_the_seller_box_proves_nothing(self):
        # Seller comments, or the site's own spans elsewhere, are not the removal box.
        raw = fixture('deruedas_detail.html')
        for old, new in (('BRIONES AUTOMOTORES<br/>', 'El auto no está disponible para permuta<br/>'),
                         ('<span class="texto resaltar">$ 38.500.000</span>',
                          '<span class="texto resaltar">$ 38.500.000</span><span class="texto inv">No está disponible</span>'),
                         ('<span class="texto">Lunes: 09:00 a 19:00</span>', '<span class="texto">Lunes: no está disponible</span>')):
            html = raw.replace(old, new, 1)
            self.assertNotEqual(html, raw)
            with self.subTest(new=new):
                detail = D.parse_detail(html, detail_url('830433'))
                self.assertIs(detail.gone, False)
                self.assertEqual(detail.listing.listing_id, '830433')

    def test_redirect_to_home_proves_gone_only_for_a_numeric_cod(self):
        moved = fixture('deruedas_detail_moved.html')
        detail = D.parse_detail(moved, detail_url('810000'), 302)
        self.assertEqual((detail.gone, detail.gone_reason), (True, 'aviso eliminado (redirige al inicio)'))
        for html, url in ((moved.replace('https://www.deruedas.com.ar/', 'https://www.deruedas.com.ar/login.asp'), detail_url('810000')),
                          (moved.replace('www.deruedas.com.ar', 'www.deruedas.com'), detail_url('810000')),
                          ('<html><body>Object moved</body></html>', detail_url('810000')),
                          (moved, detail_url('abc')), (moved, BASE + '/vendo/Toyota/Corolla/Usados/Mendoza'),
                          (moved, detail_url('810000') + '&cod=810001')):
            with self.subTest(url=url, html=html[-60:]), self.assertRaises(CollectorBlocked):
                D.parse_detail(html, url, 302)
        with self.assertRaises(RuntimeError):
            D.parse_detail(moved, detail_url('810000'), 301)

    def test_only_two_proofs_of_gone_everything_else_fails(self):
        raw = fixture('deruedas_detail.html')
        url = detail_url('830433')
        home = '<html><head><title>deRuedas</title></head><body><div id="divMain">Autos usados</div></body></html>'
        broken = {
            'another vehicle': raw.replace('<meta content="830433" itemprop="sku"/>', '<meta content="830434" itemprop="sku"/>'),
            'another vehicle ': raw.replace('Mendoza?cod=830433" rel="canonical"', 'Mendoza?cod=830434" rel="canonical"'),
            'identity missing': home,
            'identity missing ': raw.replace('<meta content="830433" itemprop="sku"/>', ''),
            'state unknown': raw.replace('https://schema.org/InStock', 'https://schema.org/SoldOut'),
            'state unknown ': raw.replace('<div id="bloqueContacto"></div>', ''),
            # Without the seller's box an agency would read as a particular without its town.
            'state unknown  ': raw.replace('id="divContactoVehiculo"', 'id="divContactoVehiculoV2"'),
            'prices differ': raw.replace('<span class="texto resaltar">$ 38.500.000</span>', '<span class="texto resaltar">$ 3.850.000</span>'),
            'title missing': raw.replace('<h1>Toyota Corolla</h1>', ''),
        }
        for message, html in broken.items():
            self.assertNotEqual(html, raw, message)
            with self.subTest(message=message), self.assertRaisesRegex(RuntimeError, message.strip()):
                D.parse_detail(html, url)
        with self.assertRaisesRegex(RuntimeError, 'another vehicle'):
            D.parse_detail(raw, detail_url('830434'))
        # The site never answers these; if it did they would not prove a removal.
        for status in (404, 410, 500, 503):
            with self.subTest(status=status), self.assertRaisesRegex(RuntimeError, f'HTTP {status}') as raised:
                D.parse_detail(raw, url, status)
            self.assertNotIsInstance(raised.exception, CollectorBlocked)
        for status in (401, 403, 429):
            with self.subTest(status=status), self.assertRaises(CollectorBlocked):
                D.parse_detail(raw, url, status)

    def test_wrong_path_with_the_right_cod_is_the_same_ad(self):
        # The site serves by cod alone: /vendo/Ford/Fiesta/...?cod=830433 is the Corolla.
        url = detail_url('830433', '/vendo/Ford/Fiesta/Usado/Cordoba')
        self.assertEqual(D.parse_detail(fixture('deruedas_detail.html'), url).listing.modelo, 'Corolla')

    def test_detail_keeps_the_model_of_a_version_filed_under_another(self):
        raw, url = fixture('deruedas_detail_nonclient.html'), detail_url('824503')
        self.assertEqual(D.parse_detail(raw, url).listing.modelo, 'Onix')     # Joy+
        html = raw.replace('<h1>Chevrolet Onix</h1><span> Joy+ 1.4 LS 98cv (L17)</span>',
                           '<h1>Chevrolet Onix</h1><span> Plus LS 1.2 90cv (L19)</span>')
        self.assertNotEqual(html, raw)
        for page_ in (html, D().slim_page(Page(200, url, html))):
            item = D.parse_detail(page_, url).listing
            self.assertEqual((item.marca, item.modelo, item.titulo),
                             ('Chevrolet', 'Onix Plus', 'Chevrolet Onix Plus LS 1.2 90cv (L19)'))

    def test_photos_of_other_ads_are_not_this_ad_photos(self):
        raw = fixture('deruedas_detail.html')
        other = '<li><img data-img="9" src="https://www.deruedas.com.ar/images/autos/Ford-Ka-2019/829/829999_1_im.jpg"/></li></ul>'
        html = raw.replace('</ul>', other, 1)
        self.assertNotEqual(html, raw)
        self.assertEqual(len(D.parse_detail(html, detail_url('830433')).listing.imagenes), 8)

    async def test_fetch_rejects_urls_that_would_look_gone_before_any_request(self):
        requests = []
        scraper = D(transport=httpx.MockTransport(lambda request: requests.append(request) or httpx.Response(200)))
        for url in (BASE + '/vendo/Toyota/Corolla/Usados/Mendoza', detail_url('abc'), detail_url(''),
                    detail_url('830433') + '&cod=1', 'https://www.deruedas.com/vendo/a/b/Usados/c?cod=830433',
                    'https://deruedas.com.ar.example.org/vendo/a/b/Usados/c?cod=830433', 'https://example.org/product',
                    'http://www.deruedas.com.ar/vendo/a/b/Usados/c?cod=830433', BASE + '/special/x?cod=830433',
                    BASE + '/ajax.asp?cod=830433', BASE + '/bus.asp?cod=830433',
                    # httpx would send /special/x and the server would decode %2E%2E.
                    BASE + '/vendo/../special/x?cod=830433', BASE + '/vendo/%2E%2E/ajax.asp?cod=830433'):
            with self.subTest(url=url), self.assertRaises(ValueError):
                await scraper.fetch_detail_page(url)
        self.assertEqual(requests, [])

    async def test_fetch_keeps_the_home_redirect_and_follows_nothing(self):
        moved = fixture('deruedas_detail_moved.html')
        requests = []

        def removed(request):
            requests.append(str(request.url))
            return page(moved, 302, location=BASE + '/')
        scraper = D(transport=httpx.MockTransport(removed))
        fetched = await scraper.fetch_detail_page(detail_url('810000'))
        self.assertEqual((fetched.status, fetched.url, requests), (302, detail_url('810000'), [detail_url('810000')]))
        self.assertTrue(D.parse_detail(fetched.html, fetched.url, fetched.status).gone)
        for status, location in ((302, BASE + '/login.asp'), (302, 'https://external.example/'), (301, BASE + '/'),
                                 (302, '/'), (302, ''), (307, BASE + '/vendo/x/y/Usados/z?cod=810000')):
            requests.clear()
            scraper = D(transport=httpx.MockTransport(lambda request: requests.append(str(request.url)) or page(
                moved, status, **({'location': location} if location else {}))))
            # "/" is the home page too: it resolves to the same exact target.
            if (status, location) == (302, '/'):
                self.assertEqual((await scraper.fetch_detail_page(detail_url('810000'))).status, 302)
                continue
            with self.subTest(status=status, location=location), self.assertRaises(CollectorBlocked):
                await scraper.fetch_detail_page(detail_url('810000'))
            self.assertEqual(requests, [detail_url('810000')])

    def test_slim_page_round_trips_every_active_ad(self):
        for name, cod in ACTIVE.items():
            with self.subTest(name=name):
                raw, url = fixture(name), detail_url(cod)
                expected = D.parse_detail(raw, url).listing
                slim = D().slim_page(Page(200, url, raw))
                again = D.parse_detail(slim, url).listing
                self.assertEqual((again.to_dict(), again.extra), (expected.to_dict(), expected.extra))
                self.assertLess(len(slim), len(raw) / 2)
                # Stored once more (a reprocess) it stays the same.
                self.assertEqual(D().slim_page(Page(200, url, slim)), slim)
                with self.assertRaisesRegex(RuntimeError, 'another vehicle'):
                    D.parse_detail(slim, detail_url('1'))
        # A seller's '</script>' must not close the stored JSON early.
        raw, url = fixture('deruedas_detail.html').replace(
            'BRIONES AUTOMOTORES<br/>', 'BRIONES AUTOMOTORES &lt;/script&gt;&lt;b&gt;<br/>', 1), detail_url('830433')
        expected = D.parse_detail(raw, url).listing
        self.assertIn('</script><b>', expected.descripcion)
        slim = D().slim_page(Page(200, url, raw))
        self.assertNotIn('</script', slim[:-len('</script>')])
        again = D.parse_detail(slim, url).listing
        self.assertEqual((again.to_dict(), again.extra), (expected.to_dict(), expected.extra))
        self.assertEqual(D().slim_page(Page(200, url, slim)), slim)

    def test_a_stored_envelope_inside_a_live_page_is_seller_text(self):
        raw, url = fixture('deruedas_detail_particular.html'), detail_url('807381')
        forged = deruedas._STORED + json.dumps({
            'sku': '807381', 'canonical': url, 'brand': 'Toyota', 'model': 'Corolla', 'availability': 'https://schema.org/InStock',
            'h1': 'Toyota Corolla', 'header_price': '$ 1.000.000', 'ficha': {'Precio': '$ 1.000.000', 'Kilometraje': '1000 Km'},
            'contact_block': True, 'seller': {'client': True, 'client_name': 'Agencia Falsa'}}) + '</script>'
        box = '<div class="titulo">Comentarios del Vendedor</div>\n<div></div>\n<div class="texto">'
        html = raw.replace(box, box + forged, 1)
        self.assertNotEqual(html, raw)
        for page_ in (html, D().slim_page(Page(200, url, html))):
            with self.subTest(stored=page_.startswith(deruedas._STORED)):
                item = D.parse_detail(page_, url).listing
                self.assertEqual((item.precio, item.km, item.vendedor, item.vendedor_nombre),
                                 (20900000.0, 140000, 'particular', None))

    def test_slim_page_keeps_no_private_or_foreign_data(self):
        raw = fixture('deruedas_detail_nonclient.html')
        private = ('<a class="boton verde enviar_whatsapp" href="https://api.whatsapp.com/send?phone=54[TELEFONO_OCULTO]">'
                   'Enviar Whatsapp</a><script>var datos = {mail: "persona@example.com"};</script>')
        raw = raw.replace('<div id="bloqueContacto"></div>', '<div id="bloqueContacto">' + private + '</div>')
        raw = raw.replace('<br/><b><h2><span>Mendoza, Godoy Cruz</span></h2></b>',
                          'Calle Falsa 123<br/><b><h2><span>Mendoza, Godoy Cruz</span></h2></b>')
        raw = raw.replace('</body>', '<div id="divOpinion">Simón sabe sobre este vehículo</div>'
                          '<div class="flexslider similares"><a href="/vendo/x/y/Usados/z?cod=1">Otro aviso</a></div></body>')
        for marker in ('api.whatsapp.com', 'persona@example.com', 'Calle Falsa 123', 'Simón sabe', 'Otro aviso'):
            self.assertIn(marker, raw)
        url = detail_url('824503')
        slim = D().slim_page(Page(200, url, raw))
        for marker in ('Vendedor Privado', 'whatsapp', 'TELEFONO', '@', 'Calle Falsa', 'Simón sabe', 'Otro aviso',
                       'Hemos bloqueado', 'Visitas', 'google'):
            self.assertNotIn(marker, slim)
        stored = json.loads(soup(slim).select_one('script#eseauto-deruedas-detail').string)
        self.assertEqual(stored['seller'], {'client': False, 'client_name': None, 'stats': True, 'maps': False,
                                            'hours': False, 'location_h2': 'Mendoza, Godoy Cruz'})
        self.assertEqual(D.parse_detail(slim, url).listing.vendedor, 'agencia')
        # A client agency keeps its public name, nothing else of its box.
        agency = D().slim_page(Page(200, detail_url('830433'), fixture('deruedas_detail.html')))
        self.assertEqual(json.loads(soup(agency).select_one('script').string)['seller'], {
            'client': True, 'client_name': 'Briones Automotores', 'stats': True, 'maps': True, 'hours': True,
            'location_h2': 'Mendoza, Guaymallén'})
        self.assertNotIn('Lunes', agency)

    def test_slim_page_of_gone_and_unreadable_pages(self):
        moved = fixture('deruedas_detail_moved.html').replace('</body>', '<script src="https://static.example/beacon.js"></script></body>')
        slim = D().slim_page(Page(302, detail_url('810000'), moved))
        self.assertNotIn('<script', slim)
        self.assertTrue(D.parse_detail(slim, detail_url('810000'), 302).gone)
        raw, url = fixture('deruedas_detail_unavailable.html'), detail_url('750000')
        slim = D().slim_page(Page(200, url, raw))
        self.assertNotIn('Vendedor Privado', slim)
        self.assertEqual(D.parse_detail(slim, url).gone_reason, 'no disponible (InStock)')
        # A page without the ad's identity is kept for diagnosis, minus the seller's box.
        unknown = fixture('deruedas_detail_particular.html').replace('<meta content="807381" itemprop="sku"/>', '')
        slim = D().slim_page(Page(200, detail_url('807381'), unknown))
        self.assertIn('divFichaVehiculo', slim)
        self.assertNotIn('Vendedor Privado', slim)
        self.assertNotIn('divContactoVehiculo', slim)
        with self.assertRaisesRegex(RuntimeError, 'identity missing'):
            D.parse_detail(slim, detail_url('807381'))
        for stored in ('{', '[1]', ''):
            with self.subTest(stored=stored), self.assertRaisesRegex(RuntimeError, 'malformed stored detail'):
                D.parse_detail(f'<script type="application/json" id="eseauto-deruedas-detail">{stored}</script>', url)

    def test_card_and_detail_of_the_same_ad_agree_on_the_stored_identity_fields(self):
        listed = {item.listing_id: item for item in D.parse_search(fixture('deruedas_search.html'))}['824503']
        detail = D.parse_detail(fixture('deruedas_detail_nonclient.html'), listed.url).listing
        for field in ('listing_id', 'titulo', 'marca', 'modelo', 'version', 'anio', 'km', 'precio', 'moneda',
                      'ubicacion', 'combustible', 'url'):
            with self.subTest(field=field):
                self.assertEqual(getattr(listed, field), getattr(detail, field))
        self.assertEqual(listed.imagenes[0], detail.imagenes[0])

    async def test_strict_identity_keeps_another_ad_out_of_the_stored_listing(self):
        self.assertTrue(D.STRICT_DETAIL_ID)
        detail = D.parse_detail(fixture('deruedas_detail.html'), detail_url('830433'))
        for external_id, accepted in (('830433', True), ('830434', False)):
            row = {'id': 7, 'source': 'deruedas', 'external_id': external_id, 'url': detail_url(external_id)}
            with self.subTest(external_id=external_id), \
                    patch.object(enrich, 'ingest', new_callable=AsyncMock, return_value=IngestResult(found=1)) as ingest, \
                    patch.object(enrich, 'log_error', new_callable=AsyncMock) as errors, \
                    patch.object(enrich.repo, 'mark_detail_checked', new_callable=AsyncMock) as checked:
                await enrich.ingest_detail(row, copy.deepcopy(detail), stage='enrich')
                self.assertEqual((ingest.await_count, errors.await_count, checked.await_count),
                                 (1, 0, 0) if accepted else (0, 1, 1))
        gone = D.parse_detail(fixture('deruedas_detail_moved.html'), detail_url('810000'), 302)
        self.assertEqual((await enrich.ingest_detail({'id': 7, 'source': 'deruedas', 'external_id': '810000'},
                                                    gone, stage='reprocess', seen=False)).events, [])


class WiringTests(unittest.TestCase):
    def test_registered_as_a_per_model_source_with_strict_detail_identity(self):
        self.assertIs(collectors.REGISTRY['deruedas'], D)
        self.assertIn('deruedas', config.SOURCES)
        self.assertEqual((D.name, D.INVENTORY_TARGET, D.STRICT_DETAIL_ID, D.DETAIL_PARSER_VERSION),
                         ('deruedas', False, True, 1))
        self.assertEqual(D.BASE, 'https://www.deruedas.com.ar')
        self.assertGreaterEqual(D.CRAWL_DELAY, 6)       # robots.txt: Crawl-delay 5
        self.assertEqual(collector_repairs.COLLECTOR_FILES['deruedas'], 'deruedas')
        self.assertTrue((ROOT / 'worker' / 'collectors' / 'deruedas.py').is_file())

    def test_targets_are_derived_per_make_and_model_with_the_widest_query(self):
        profiles = [
            {'id': 1, 'filters': {'make': 'Toyota', 'model': 'Hilux', 'year_min': 2015, 'km_max': 90000}},
            {'id': 2, 'filters': {'make': 'toyota', 'model': 'hilux', 'year_min': 2012, 'km_max': 150000}},
            {'id': 3, 'filters': {'make': 'Fiat', 'model': 'Cronos', 'sources': ['deruedas']}},
            {'id': 4, 'filters': {'make': 'Ford', 'model': 'Ka', 'sources': ['carone']}},
            {'id': 5, 'filters': {}},
        ]
        targets = derive_targets(profiles, ['deruedas'])
        self.assertEqual([(t.source, t.make, t.model) for t in targets],
                         [('deruedas', 'Fiat', 'Cronos'), ('deruedas', 'Toyota', 'Hilux')])
        self.assertEqual(targets[1].query, {'year_min': 2012, 'km_max': 150000, 'profile_ids': [1, 2]})
        self.assertEqual(scraper_filters({'make': targets[1].make, 'model': targets[1].model, 'query': targets[1].query}),
                         {'marca': 'Toyota', 'modelo': 'Hilux', 'anio_min': 2012, 'km_max': 150000})

    def test_migration_and_seed_insert_the_same_idempotent_row(self):
        row = r"\(\s*'deruedas'\s*,\s*'deRuedas'\s*,\s*true\s*,\s*3600\s*,\s*140\s*,\s*6\s*\)"
        migration = (ROOT / 'supabase' / 'migrations' / '20261023180000_deruedas_source.sql').read_text(encoding='utf-8')
        self.assertRegex(migration, r'(?s)insert into public\.sources \(id, name, enabled, crawl_interval_seconds, '
                         r'priority, detail_interval_seconds\) values\s*' + row + r'\s*on conflict \(id\) do nothing;')
        self.assertNotRegex(migration, r'(?i)\b(update|delete|drop|alter)\b')
        self.assertRegex((ROOT / 'supabase' / 'seed.sql').read_text(encoding='utf-8'), row)


@pytest.mark.parametrize('url,expected', [
    ('https://www.deruedas.com.ar/vendo/Toyota/Corolla/Usados/Mendoza?cod=830433', 'deruedas'),
    ('https://deruedas.com.ar/vendo/Toyota/Corolla/Usados/Mendoza?cod=830433', 'deruedas'),
    ('https://WWW.DERUEDAS.COM.AR/bus.asp?segmento=0', 'deruedas'),
    # deruedas.com is a parked domain, and look-alikes are not the source.
    ('https://www.deruedas.com/vendo/Toyota/Corolla/Usados/Mendoza?cod=830433', None),
    ('https://deruedas.com/', None),
    ('https://www.deruedas.com.ar.example.org/vendo/x/y/Usados/z?cod=1', None),
    ('https://deruedas.com.ar.example.org/vendo/x/y/Usados/z?cod=1', None),
    ('https://m.deruedas.com.ar/vendo/x/y/Usados/z?cod=1', None),
    ('https://example.org/www.deruedas.com.ar/vendo/x?cod=1', None),
])
def test_cli_host_inference(url, expected):
    assert _source_of(url) == expected


if __name__ == '__main__':
    unittest.main()

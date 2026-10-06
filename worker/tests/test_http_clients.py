"""Repeated source requests must not reload the CA bundle on the event loop."""
import ssl
import unittest
from concurrent.futures import ThreadPoolExecutor
from time import sleep
from unittest.mock import patch

import httpx

from collectors import _http
import http_clients


class RepeatedRequestsTests(unittest.IsolatedAsyncioTestCase):
    async def test_eight_requests_load_the_ca_bundle_once(self):
        http_clients._ssl_context.cache_clear()
        original = ssl.SSLContext.load_verify_locations
        loads = []

        def load(context, *args, **kwargs):
            loads.append(context)
            return original(context, *args, **kwargs)

        async def get(client, url, **kwargs):
            return httpx.Response(200, text="<html>public</html>", request=httpx.Request("GET", url))

        with patch.object(ssl.SSLContext, "load_verify_locations", load), \
                patch.object(httpx.AsyncClient, "get", get), \
                patch.dict("os.environ", {"SSL_CERT_FILE": "", "SSL_CERT_DIR": ""}):
            for _ in range(8):
                page = await _http.fetch_page("https://example.com/vehicle")
                self.assertEqual(page.status, 200)
        self.assertEqual(len(loads), 1, "Every request reloaded certificates synchronously")

    async def test_sessions_are_separate_and_verification_stays_enabled(self):
        with patch.dict("os.environ", {"SSL_CERT_FILE": "", "SSL_CERT_DIR": ""}):
            context = http_clients._ssl_context(None, None)
            self.assertTrue(context.check_hostname)
            self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
            self.assertGreater(len(context.get_ca_certs()), 0)
            async with http_clients.async_client() as first, http_clients.async_client() as second:
                first.cookies.set("source_session", "one")
                self.assertNotIn("source_session", second.cookies)


class CertificatePolicyTests(unittest.TestCase):
    def setUp(self):
        http_clients._ssl_context.cache_clear()

    def tearDown(self):
        http_clients._ssl_context.cache_clear()

    def test_environment_certificate_file_wins_over_directory(self):
        with patch.dict("os.environ", {"SSL_CERT_FILE": "custom.pem", "SSL_CERT_DIR": "custom-dir"}), \
                patch.object(http_clients.ssl, "create_default_context") as load, \
                patch.object(http_clients.httpx, "AsyncClient") as client:
            http_clients.async_client(timeout=12)
            http_clients.async_client(timeout=24)
            load.assert_called_once_with(cafile="custom.pem")
            self.assertIs(client.call_args.kwargs["verify"], load.return_value)
            self.assertEqual(client.call_args.kwargs["timeout"], 24)

    def test_environment_directory_and_trust_env_false(self):
        with patch.dict("os.environ", {"SSL_CERT_FILE": "", "SSL_CERT_DIR": "custom-dir"}), \
                patch.object(http_clients.ssl, "create_default_context") as load, \
                patch.object(http_clients.httpx, "AsyncClient"):
            http_clients.async_client()
            load.assert_called_once_with(capath="custom-dir")
            http_clients.async_client(trust_env=False)
            self.assertEqual(load.call_args.kwargs, {"cafile": http_clients.certifi.where()})

    def test_worker_and_collector_threads_load_certificates_once(self):
        def load(**kwargs):
            sleep(0.02)
            return ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)

        with patch.dict("os.environ", {"SSL_CERT_FILE": "", "SSL_CERT_DIR": ""}), \
                patch.object(http_clients.ssl, "create_default_context", side_effect=load) as certificate_load, \
                patch.object(http_clients.httpx, "AsyncClient"):
            with ThreadPoolExecutor(max_workers=8) as pool:
                list(pool.map(lambda _: http_clients.async_client(), range(8)))
            self.assertEqual(certificate_load.call_count, 1)

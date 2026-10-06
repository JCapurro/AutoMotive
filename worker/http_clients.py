"""HTTP clients share certificate loading, while keeping their own sessions.

Loading the CA bundle is synchronous and expensive on the pilot Windows PC.
Repeated paginated requests must not keep blocking the collector/worker loops.
"""
from __future__ import annotations

import os
import ssl
from functools import lru_cache
from threading import RLock

import certifi
import httpx


_ssl_lock = RLock()


@lru_cache(maxsize=4)
def _ssl_context(cert_file: str | None, cert_dir: str | None) -> ssl.SSLContext:
    if cert_file:
        return ssl.create_default_context(cafile=cert_file)
    if cert_dir:
        return ssl.create_default_context(capath=cert_dir)
    return ssl.create_default_context(cafile=certifi.where())


def async_client(**kwargs) -> httpx.AsyncClient:
    """Retain HTTPX verification and environment CA settings, loading each once."""
    if "verify" not in kwargs:
        trust_env = kwargs.get("trust_env", True)
        cert_file = (os.getenv("SSL_CERT_FILE") or None) if trust_env else None
        cert_dir = (os.getenv("SSL_CERT_DIR") or None) if trust_env else None
        # The worker and collector run on different threads on Windows.
        with _ssl_lock:
            kwargs["verify"] = _ssl_context(cert_file, cert_dir)
    return httpx.AsyncClient(**kwargs)

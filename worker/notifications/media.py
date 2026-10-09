"""Public listing photos carried by notifications; never fetch URLs while sending."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from urllib.parse import urlsplit


MAX_PHOTOS = 3


def image_urls(images: Any) -> list[str]:
    """Accept the same URL / {url} array as the web gallery, with a small cap.

    Old notifications have no images. Ignore malformed entries, unsafe schemes
    and duplicates so a bad source image cannot break an otherwise useful alert.
    """
    if not isinstance(images, (list, tuple)):
        return []
    out: list[str] = []
    for image in images:
        url = image.get("url") if isinstance(image, Mapping) else image
        if not isinstance(url, str):
            continue
        url = url.strip()
        if not url or any(ord(c) < 32 for c in url):
            continue
        try:
            parsed = urlsplit(url)
            valid = (parsed.scheme in ("http", "https") and parsed.hostname
                     and not parsed.username and not parsed.password)
        except ValueError:
            continue
        if valid and url not in out:
            out.append(url)
        if len(out) == MAX_PHOTOS:
            break
    return out

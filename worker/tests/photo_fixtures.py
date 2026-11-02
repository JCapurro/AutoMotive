"""Deterministic images for the photo hash tests (PAR-02 resto). Drawn with
Pillow, so the tests need no binary fixture; tests/test_photo_hash.py pins
their hashes against imagehash.phash (computed once, see VECTORS there)."""
from __future__ import annotations

from io import BytesIO


def draw(kind: str, size: tuple[int, int] = (640, 480)):
    """A car-photo-like composition: sky/ground gradient plus shapes per kind."""
    from PIL import Image, ImageDraw

    w, h = size
    img = Image.new("RGB", size)
    px = img.load()
    for y in range(h):
        for x in range(w):
            if kind == "b":
                px[x, y] = (40 + (x * 180) // w, 90, 200 - (y * 150) // h)
            elif kind == "c":
                px[x, y] = ((x * y) % 256, (x + 2 * y) % 256, (3 * x) % 256)
            else:
                px[x, y] = (90 + (y * 120) // h, 120 + (y * 80) // h, 220 - (y * 160) // h)
    d = ImageDraw.Draw(img)
    if kind == "a":
        d.rectangle([w // 5, h // 2, 4 * w // 5, 3 * h // 4], fill=(180, 20, 30))
        d.ellipse([w // 4, 2 * h // 3, w // 4 + h // 6, 2 * h // 3 + h // 6], fill=(20, 20, 20))
        d.ellipse([3 * w // 5, 2 * h // 3, 3 * w // 5 + h // 6, 2 * h // 3 + h // 6], fill=(20, 20, 20))
    elif kind == "b":
        d.polygon([(w // 10, h - 10), (w // 2, h // 6), (9 * w // 10, h - 10)], fill=(240, 240, 240))
    elif kind == "c":
        d.rectangle([w // 3, h // 3, 2 * w // 3, 2 * h // 3], fill=(0, 0, 0))
    return img


def encode(img, fmt: str = "PNG", **kw) -> bytes:
    buf = BytesIO()
    img.save(buf, fmt, **kw)
    return buf.getvalue()

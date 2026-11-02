"""Perceptual hash of a listing photo (PAR-02 resto,
docs/superpowers/specs/2026-11-02-par02-resto-design.md, decision 5).

Only Pillow, imported lazily: the worker starts and runs without it (the
photo hash pass, pipeline/photo_hash.py, then logs once and does nothing).
The algorithm is imagehash.phash's: grayscale, 32×32 LANCZOS, 2-D DCT-II,
the 8×8 low frequencies (DC included) against their median, 64 bits as 16 hex
digits, first coefficient the most significant bit. The DCT's scale factor
does not change a comparison with the median, so the bits are the same;
tests/test_photo_hash.py pins it with vectors computed once with imagehash.

Pure apart from decoding the bytes; no I/O.
"""
from __future__ import annotations

import math
from io import BytesIO
from typing import Iterable

HASH_SIZE = 8
_SIDE = HASH_SIZE * 4               # 32
# Decompression bombs: a listing photo never needs more than this.
MAX_IMAGE_PIXELS = 40_000_000
# cos(pi * u * (2n + 1) / (2 * 32)) for the 8 low frequencies u and the 32 samples n.
_COS = [[math.cos(math.pi * u * (2 * n + 1) / (2 * _SIDE)) for n in range(_SIDE)] for u in range(HASH_SIZE)]
# A near-blank image (a flat colour, a placeholder) hashes to almost all 0s or 1s.
_FLAT_BITS = 4


class PillowMissing(RuntimeError):
    """Pillow is not installed; the pass skips itself."""


def available() -> bool:
    try:
        import PIL.Image  # noqa: F401
    except ImportError:
        return False
    return True


def _median(values: list[float]) -> float:
    s = sorted(values)
    mid = len(s) // 2
    return s[mid] if len(s) % 2 else (s[mid - 1] + s[mid]) / 2


def phash_pixels(pixels: list[list[float]]) -> str:
    """The hash of a 32×32 grayscale matrix (rows of columns)."""
    # Along the rows' axis (vertical frequency u) first, then the columns' (v).
    rows_dct = [[sum(_COS[u][r] * pixels[r][c] for r in range(_SIDE)) for c in range(_SIDE)]
                for u in range(HASH_SIZE)]
    low = [sum(_COS[v][c] * rows_dct[u][c] for c in range(_SIDE))
           for u in range(HASH_SIZE) for v in range(HASH_SIZE)]
    med = _median(low)
    value = 0
    for coefficient in low:
        value = (value << 1) | (1 if coefficient > med else 0)
    return f"{value:016x}"


def phash(data: bytes) -> str:
    """The hash of an encoded image. Raises PillowMissing without Pillow and
    whatever Pillow raises for a file it cannot read."""
    try:
        from PIL import Image
    except ImportError as e:
        raise PillowMissing("Pillow no instalado") from e
    Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS
    with Image.open(BytesIO(data)) as img:
        if img.format == "JPEG":
            # Decode at a reduced scale: a 32×32 hash never needs the full photo.
            img.draft("L", (_SIDE * 4, _SIDE * 4))
        small = img.convert("L").resize((_SIDE, _SIDE), Image.Resampling.LANCZOS)
        flat = list(small.tobytes())
    return phash_pixels([flat[r * _SIDE:(r + 1) * _SIDE] for r in range(_SIDE)])


def distance(a: str, b: str) -> int:
    """Hamming distance between two hex hashes."""
    return bin(int(a, 16) ^ int(b, 16)).count("1")


def is_flat(h: str) -> bool:
    """A hash with almost every bit equal: a blank image or a placeholder."""
    ones = bin(int(h, 16)).count("1")
    return ones <= _FLAT_BITS or ones >= HASH_SIZE * HASH_SIZE - _FLAT_BITS


def valid(h: object) -> bool:
    if not isinstance(h, str) or len(h) != 16:
        return False
    try:
        int(h, 16)
    except ValueError:
        return False
    return True


def best_match(a: Iterable[str], b: Iterable[str], *, ignore: set[str] = frozenset()) -> tuple[int, int, int] | None:
    """(i, j, distance) of the closest pair of hashes of two listings, all
    against all (portals reorder photos), leaving out flat and `ignore`d ones."""
    best = None
    b = list(b)
    for i, ha in enumerate(a):
        if not valid(ha) or ha in ignore or is_flat(ha):
            continue
        for j, hb in enumerate(b):
            if not valid(hb) or hb in ignore or is_flat(hb):
                continue
            d = distance(ha, hb)
            if best is None or d < best[2]:
                best = (i, j, d)
    return best

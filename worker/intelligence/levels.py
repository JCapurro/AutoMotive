"""Opportunity levels (§20, sección 6.4), thresholds from app_config.level_thresholds."""
from __future__ import annotations

from typing import Mapping


ORDER = ("low", "match", "good", "high")


def rank(level: str) -> int:
    return ORDER.index(level)


def level_for(score: int, thresholds: Mapping[str, float], *, cap: str | None = None) -> str:
    """🔥 high ≥ 85 · 🟢 good ≥ 70 · 🟡 match ≥ 50 · ⚪ low. `cap` is the highest
    level allowed (the suspicious-discount guard caps at `good`)."""
    level = "low"
    for name in ("high", "good", "match"):
        if score >= thresholds[name]:
            level = name
            break
    if cap is not None and rank(level) > rank(cap):
        level = cap
    return level


def at_least(level: str, minimum: str) -> bool:
    return rank(level) >= rank(minimum)

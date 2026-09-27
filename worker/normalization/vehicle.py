"""Make, model and trim of a listing, resolved against vehicle_catalog (sección 5.2, paso 1).

The title (plus whatever structured make/model/version the source exposes) is
matched against catalog names and aliases: exact word matches first, then
rapidfuzz for typos ("Toyta Corola"). When nothing resolves, the crawl
target's make/model is used with a low `confidence`, instead of trusting it
blindly the way the F0 scrapers did (MercadoLibre copied the search filter
into every card).

Pure functions: the catalog is loaded by db/repos/catalog.py and passed in.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from rapidfuzz import fuzz

from normalization.normalize import normalize_brand, normalize_text


@dataclass(frozen=True)
class CatalogModel:
    make: str
    model: str
    aliases: tuple[str, ...] = ()
    trims: tuple[str, ...] = ()
    year_from: int | None = None
    year_to: int | None = None

    def names(self) -> list[str]:
        return [normalize_text(self.model), *(normalize_text(a) for a in self.aliases)]


@dataclass(frozen=True)
class VehicleMatch:
    make: str | None
    model: str | None
    trim: str | None
    confidence: float
    # How make/model were settled, for debugging and the admin inspector.
    method: str = "none"
    notes: tuple[str, ...] = field(default=())


# Confidence per method. Below 0.5 means "we're echoing the search target".
CONFIDENCE = {
    "source": 0.95,        # structured make/model from the source, found in the catalog
    "title": 0.9,          # make and model named in the title
    "title_model": 0.8,    # model named in the title, make implied by it
    "fuzzy": 0.65,         # close spelling in the title
    "target": 0.4,         # nothing in the text: the crawl target's make/model
    "source_raw": 0.35,    # structured make/model the catalog doesn't know
    "none": 0.0,
}

# Brand spellings seen in titles; the catalog's own make names are added at match time.
_BRAND_WORDS = {
    "vw": "volkswagen", "volks": "volkswagen", "chevy": "chevrolet", "citroen": "citroen",
    "mercedes": "mercedes-benz", "mercedes benz": "mercedes-benz", "mb": "mercedes-benz",
}

_FUZZY_CUTOFF = 88.0
_TOKEN_RE = re.compile(r"[a-z0-9]+(?:[-+!][a-z0-9]*)*")


def _text(*parts: str | None) -> str:
    return " ".join(normalize_text(p) for p in parts if p)


def _has_phrase(text: str, phrase: str) -> bool:
    return bool(phrase) and re.search(rf"(?<![a-z0-9]){re.escape(phrase)}(?![a-z0-9])", text) is not None


def _brands_in(text: str, models: list[CatalogModel]) -> set[str]:
    brands = {normalize_brand(m.make) for m in models}
    found = {b for b in brands if _has_phrase(text, b)}
    found |= {canon for word, canon in _BRAND_WORDS.items()
              if canon in brands and _has_phrase(text, word)}
    return found


_YEARLIKE = re.compile(r"(19|20)\d\d")


def _best_by_name(text: str, candidates: list[CatalogModel], *,
                  yearlike: bool = True) -> list[CatalogModel]:
    """Models whose name or alias appears in `text`; the longest name wins, so
    "Gol Trend" beats "Gol" and "Corolla Cross" beats "Corolla".
    With `yearlike=False`, names such as Peugeot "2008" are skipped: without
    the brand in the text they are more likely the car's year."""
    hits: list[tuple[int, CatalogModel]] = []
    for m in candidates:
        for name in m.names():
            if not yearlike and _YEARLIKE.fullmatch(name):
                continue
            if _has_phrase(text, name):
                hits.append((len(name), m))
    if not hits:
        return []
    top = max(length for length, _ in hits)
    return list(dict.fromkeys(m for length, m in hits if length == top))


def _fuzzy(text: str, candidates: list[CatalogModel]) -> CatalogModel | None:
    """Closest model name among the title's words (typos, missing spaces).
    Names under 4 characters are never fuzzy-matched: "Ka" would match anything."""
    tokens = _TOKEN_RE.findall(text)
    if not tokens:
        return None
    # Windows of 1–3 words, so "corola cros" can reach "corolla cross".
    windows = {" ".join(tokens[i:i + n]) for n in (1, 2, 3) for i in range(len(tokens) - n + 1)}
    best: tuple[float, int, CatalogModel] | None = None
    for m in candidates:
        for name in m.names():
            if len(name) < 4 or _YEARLIKE.fullmatch(name):
                continue
            for w in windows:
                if abs(len(w) - len(name)) > 3:
                    continue
                score = fuzz.ratio(name, w)
                if score >= _FUZZY_CUTOFF and (best is None or (score, len(name)) > best[:2]):
                    best = (score, len(name), m)
    return best[2] if best else None


def resolve_trim(model: CatalogModel, *texts: str | None) -> str | None:
    """The catalog trim named in the texts (longest wins: "SE Plus" over "SE").
    Short trims ("S", "LT") only match as whole words, never fuzzily."""
    text = _text(*texts)
    if not text or not model.trims:
        return None
    hits = [(len(normalize_text(t)), t) for t in model.trims if _has_phrase(text, normalize_text(t))]
    return max(hits)[1] if hits else None


def _pick(candidates: list[CatalogModel], make_hint: str | None) -> CatalogModel | None:
    if len(candidates) == 1:
        return candidates[0]
    if make_hint:
        same = [m for m in candidates if normalize_brand(m.make) == normalize_brand(make_hint)]
        if len(same) == 1:
            return same[0]
    return None


def resolve_vehicle(
    models: list[CatalogModel],
    *,
    title: str | None,
    source_make: str | None = None,
    source_model: str | None = None,
    source_version: str | None = None,
    target_make: str | None = None,
    target_model: str | None = None,
    year: int | None = None,
) -> VehicleMatch:
    """Resolve (make, model, trim) for one listing.

    `source_*` are values the page states structurally (a spec table,
    schema.org microdata). `target_*` are the crawl target's, used only as a
    hint to break ties and as the last resort.
    """
    notes: list[str] = []
    title_text = _text(title)

    # 1) Structured make/model from the source, when the catalog knows them.
    if source_model:
        wanted = _text(source_make, source_model)
        pool = [m for m in models
                if not source_make or normalize_brand(m.make) == normalize_brand(source_make)]
        found = _pick(_best_by_name(_text(source_model), pool), source_make or target_make) \
            or _pick(_best_by_name(wanted, pool), source_make or target_make)
        if found:
            return _finish(found, "source", notes, year, source_version, title)

    # 2) The title: brand + model, or a model name that implies the brand.
    if title_text:
        brands = _brands_in(title_text, models)
        pool = [m for m in models if normalize_brand(m.make) in brands] if brands else models
        found = _pick(_best_by_name(title_text, pool, yearlike=bool(brands)),
                      target_make or source_make)
        if found:
            method = "title" if brands else "title_model"
            return _finish(found, method, notes, year, source_version, title)
        found = _fuzzy(title_text, pool)
        if found:
            notes.append("fuzzy")
            return _finish(found, "fuzzy", notes, year, source_version, title)

    # 3) Structured values the catalog doesn't know: keep them as the page says.
    if source_make and source_model:
        return VehicleMatch(source_make.strip(), source_model.strip(), None,
                            CONFIDENCE["source_raw"], "source_raw", tuple(notes))

    # 4) The crawl target, flagged as low confidence.
    if target_make or target_model:
        target = next((m for m in models
                       if normalize_brand(m.make) == normalize_brand(target_make)
                       and normalize_text(m.model) == normalize_text(target_model)), None)
        trim = resolve_trim(target, source_version, title) if target else None
        return VehicleMatch(target_make, target_model, trim, CONFIDENCE["target"], "target",
                            tuple(notes))
    return VehicleMatch(None, None, None, CONFIDENCE["none"], "none", tuple(notes))


def _finish(m: CatalogModel, method: str, notes: list[str], year: int | None,
            version: str | None, title: str | None) -> VehicleMatch:
    confidence = CONFIDENCE[method]
    if year and ((m.year_from and year < m.year_from) or (m.year_to and year > m.year_to)):
        # Outside the catalog's production years: probably a different model
        # with a similar name, or a typo in the year.
        confidence -= 0.2
        notes.append("year_out_of_range")
    return VehicleMatch(m.make, m.model, resolve_trim(m, version, title), round(confidence, 2),
                        method, tuple(notes))

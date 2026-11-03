"""PAR-04: a published guide's questions in the seller questions (pure).

Order: base → this listing's (red flags, description) → up to 3 of the guide
→ generic (age, missing data). Without a guide nothing changes.
"""
from __future__ import annotations

from datetime import datetime, timezone

from intelligence.copy import QUESTION
from intelligence.engine import assess
from intelligence.guides import GuideEntry, build_index, pick
from intelligence.red_flags import RedFlag
from intelligence.seller_questions import question_items, question_keys, question_texts, seller_questions

NOW = datetime(2026, 11, 3, 12, tzinfo=timezone.utc)
Q = ("¿La caja hace tirones al arrancar en frío?", "¿Le cambiaron los bujes del tren delantero?",
     "¿El multimedia funciona bien?", "¿Tiene la rueda de auxilio original?")
GUIDE = GuideEntry(12, None, 2011, 2019, Q)
OWNERS = RedFlag("no_owners", "x", "info")
# A 2017 listing with a description and transmission: owners (flag) is its
# own question; VTV, crashes and trim are generic (age, missing trim).
LISTING = {"make": "Ford", "model": "Fiesta", "catalog_model": "Fiesta", "year": 2017, "mileage_km": 90000,
           "description": "Impecable", "transmission": "manual"}


def keys(items):
    return [q.key for q in items]


def test_without_a_guide_nothing_changes():
    items = question_items(LISTING, [OWNERS], timing_belt=False, now=NOW)
    assert keys(items) == question_keys(LISTING, [OWNERS], timing_belt=False, now=NOW)
    assert all(q.origin == "template" for q in items)
    assert seller_questions(LISTING, [OWNERS], timing_belt=False, now=NOW) == " ".join(
        QUESTION[k] for k in question_keys(LISTING, [OWNERS], timing_belt=False, now=NOW))


def test_order_listing_then_guide_then_generic():
    items = question_items(LISTING, [OWNERS], timing_belt=False, now=NOW, guide=GUIDE)
    assert keys(items) == ["greeting", "available", "holder", "owners",
                           "guide:12:0", "guide:12:1", "guide:12:2", "vtv", "crashes", "trim"]
    assert [q.origin for q in items][4:7] == ["guide"] * 3
    assert items[4].origin_json() == {"key": "guide:12:0", "origin": "guide", "guide_id": 12, "text": Q[0]}
    assert items[0].origin_json() == {"key": "greeting", "origin": "template"}


def test_the_limit_is_configurable():
    items = question_items(LISTING, [], timing_belt=False, now=NOW, guide=GUIDE, guide_limit=1)
    assert [q.key for q in items if q.origin == "guide"] == ["guide:12:0"]
    assert not [q for q in question_items(LISTING, [], timing_belt=False, now=NOW, guide=GUIDE, guide_limit=0)
                if q.origin == "guide"]


def test_never_more_than_three_guide_questions():
    # Backlog: «hasta 3». A larger config value is clamped, here and in the scorer.
    many = GuideEntry(12, None, None, None, tuple(f"¿Pregunta número {n} de la guía?" for n in range(6)))
    items = question_items(LISTING, [], timing_belt=False, now=NOW, guide=many, guide_limit=6)
    assert len([q for q in items if q.origin == "guide"]) == 3
    from pipeline.scoring import guide_questions_limit
    assert guide_questions_limit({"model_guide": {"max_questions_in_listing": 6}}) == 3
    assert guide_questions_limit({"model_guide": {"max_questions_in_listing": 2}}) == 2
    assert guide_questions_limit({"model_guide": {"max_questions_in_listing": -1}}) == 0
    assert guide_questions_limit({}) == 3


def test_a_guide_question_repeating_a_template_one_is_skipped():
    guide = GuideEntry(5, None, None, None, (QUESTION["vtv"].upper().replace("?", " ?"), Q[0]))
    items = question_items(LISTING, [], timing_belt=False, now=NOW, guide=guide)
    assert [q.text for q in items if q.origin == "guide"] == [Q[0]]


def test_question_texts_takes_the_guide_only_after_the_listing_s_own():
    texts = question_texts(LISTING, [OWNERS], timing_belt=False, now=NOW, guide=GUIDE)
    assert texts == [QUESTION["owners"], Q[0], Q[1]]
    # Three questions of its own: the guide does not reach the email.
    many = {**LISTING, "description_facts": {}}
    flags = [OWNERS, RedFlag("year_mismatch", "x", "info"), RedFlag("price_mismatch", "x", "info")]
    assert question_texts(many, flags, timing_belt=False, now=NOW, guide=GUIDE) == [
        QUESTION["owners"], QUESTION["year_confirm"], QUESTION["price_confirm"]]


def test_assess_stores_the_origins():
    profile = {"filters": {"make": "Ford", "model": "Fiesta"}, "preferences": {}}
    from intelligence.config import IntelligenceConfig
    _, _, ev = assess({**LISTING, "price": 9000, "currency": "USD", "price_usd": 9000}, profile,
                      price_ref=None, cfg=IntelligenceConfig.from_app_config({}), now=NOW, guide=GUIDE)
    row = ev.row()
    assert [o["origin"] for o in row["question_origins"]].count("guide") == 3
    assert Q[0] in row["seller_questions"]
    assert Q[0] in row["contact_questions"]


# ---------------------------------------------------------------------------
# Which guide a listing gets
# ---------------------------------------------------------------------------

ROWS = [
    {"id": 1, "make": "Toyota", "model": "Corolla", "generation_label": None, "year_from": None, "year_to": None,
     "questions": [{"text": "¿General?"}]},
    {"id": 2, "make": "Toyota", "model": "Corolla", "generation_label": "E170", "year_from": 2014, "year_to": 2019,
     "questions": [{"text": "¿E170?"}]},
    {"id": 3, "make": "Toyota", "model": "Corolla", "generation_label": "E170 restyling", "year_from": 2017,
     "year_to": 2019, "questions": [{"text": "¿Restyling?"}]},
    {"id": 4, "make": "Toyota", "model": "Etios", "generation_label": None, "year_from": None, "year_to": None,
     "questions": []},
]
INDEX = build_index(ROWS)


def guide_for(**listing):
    g = pick(INDEX, {"make": "Toyota", "catalog_model": "Corolla", **listing})
    return g.guide_id if g else None


def test_the_narrowest_generation_wins():
    assert guide_for(year=2018) == 3
    assert guide_for(year=2015) == 2
    assert guide_for(year=2010) == 1


def test_without_a_year_only_the_guide_without_generation():
    assert guide_for(year=None) == 1


def test_model_by_catalog_spelling_and_case():
    assert pick(INDEX, {"make": "TOYOTA", "model": "corolla xei", "catalog_model": "Corolla", "year": 2015}).guide_id == 2
    assert pick(INDEX, {"make": "Toyota", "model": "Corolla", "year": 2015}).guide_id == 2


def test_no_guide():
    assert pick(INDEX, {"make": "Ford", "model": "Fiesta", "year": 2015}) is None
    assert pick({}, {"make": "Toyota", "model": "Corolla"}) is None
    # A guide without questions is not indexed.
    assert pick(INDEX, {"make": "Toyota", "model": "Etios", "year": 2015}) is None

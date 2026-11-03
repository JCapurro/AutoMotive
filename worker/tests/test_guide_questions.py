"""PAR-04: a published guide's questions in the seller questions (pure).

Order: base → this listing's (red flags, description) → up to 3 of the guide
→ generic (age, missing data). Without a guide nothing changes.
"""
from __future__ import annotations

from datetime import datetime, timezone

from intelligence.copy import QUESTION
from intelligence.engine import assess
from intelligence.guides import GuideEntry, build_index, pick, same_question
from intelligence.red_flags import RedFlag
from intelligence.seller_questions import (question_items, question_keys, question_texts, seller_questions,
                                           without_guides)

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
    # Every entry carries its text, in seller_questions' order (the withdrawal rebuilds the message).
    assert items[0].origin_json() == {"key": "greeting", "origin": "template", "text": QUESTION["greeting"]}
    assert " ".join(q.origin_json()["text"] for q in items) == seller_questions(
        LISTING, [OWNERS], timing_belt=False, now=NOW, guide=GUIDE)


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


def test_almost_the_same_question_is_skipped_too():
    # No description and the belt: the template asks about the timing belt and
    # the VTV; the guide asks the same with other words.
    listing = {**LISTING, "year": 2015, "description": None, "trim": "SE"}
    guide = GuideEntry(5, None, None, None, ("¿Cuándo se cambió la distribución por última vez?",
                                             "¿Tiene la VTV vigente?", "¿Hace ruido la caja en frío?"))
    items = question_items(listing, [], timing_belt=True, now=NOW, guide=guide)
    assert "timing_belt" in keys(items) and "vtv" in keys(items)
    assert [q.text for q in items if q.origin == "guide"] == ["¿Hace ruido la caja en frío?"]
    assert "¿Hace ruido la caja en frío?" in question_texts(listing, [], timing_belt=True, now=NOW, guide=guide)


def test_same_question():
    assert same_question("¿Tiene VTV vigente?", "¿tiene vtv vigente ?")
    assert same_question("¿Tiene la VTV vigente?", "¿Tiene VTV vigente?")
    assert same_question("¿Cuándo se hizo la distribución por última vez?",
                         "¿Cuándo se cambió la distribución por última vez?")
    assert same_question("¿Tenés historial de services?", "¿Hay historial de service?")
    # Different questions stay apart.
    assert not same_question("¿Tiene VTV?", "¿Tiene VTV vigente?")
    assert not same_question("¿Cuándo se cambió el aceite?", "¿Cuándo se cambió la distribución?")
    assert not same_question("¿Tenés el comprobante?", QUESTION["timing_proof"])
    assert not same_question("¿Es manual o automático?", "¿La caja automática hace tirones?")
    # No two template questions are «the same».
    texts = list(QUESTION.values())
    assert not [(a, b) for i, a in enumerate(texts) for b in texts[i + 1:] if same_question(a, b)]


def test_without_guides_rebuilds_the_message_from_what_stays():
    profile = {"filters": {"make": "Ford", "model": "Fiesta"}, "preferences": {}}
    from intelligence.config import IntelligenceConfig
    listing = {**LISTING, "price": 9000, "currency": "USD", "price_usd": 9000}
    cfg = IntelligenceConfig.from_app_config({})
    _, _, with_guide = assess(listing, profile, price_ref=None, cfg=cfg, now=NOW, guide=GUIDE)
    row = with_guide.row()
    out = without_guides(row, {12})
    assert all(o["origin"] == "template" for o in out["question_origins"])
    assert out["seller_questions"] == " ".join(o["text"] for o in out["question_origins"])
    assert not any(q in out["seller_questions"] for q in Q)
    assert not any(q in (out["contact_questions"] or []) for q in Q)
    assert (out["score"], out["level"]) == (row["score"], row["level"])
    # Another guide's id: nothing changes.
    assert without_guides(row, {99}) == row
    # A template question with the text of a dropped guide question stays.
    twin = {"seller_questions": "Hola ¿A? ¿A?", "contact_questions": ["¿A?"],
            "question_origins": [{"key": "greeting", "origin": "template", "text": "Hola"},
                                 {"key": "owners", "origin": "template", "text": "¿A?"},
                                 {"key": "guide:3:0", "origin": "guide", "guide_id": 3, "text": "¿A?"}]}
    assert without_guides(twin, {3})["seller_questions"] == "Hola ¿A?"
    assert without_guides(twin, {3})["contact_questions"] == ["¿A?"]


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

"""The color pass (pipeline/color_vision.py, docs/PLAN_FILTRO_COLOR.md §8):
which listings are read, how an answer becomes listings.color and
attributes._color, the daily cap, the inline budget and the downloader's
Meta allowance (color only). No network and no database: httpx.MockTransport
and the module's database functions patched."""
from __future__ import annotations

import asyncio
from io import BytesIO
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from llm import prompts
from normalization import color
from photo_fixtures import draw, encode
from pipeline import color_vision as cv
from pipeline import photo_hash
from pipeline import scheduler
from tools import backfill_color_vision as backfill

JPEG = encode(draw("a"), "JPEG", quality=85)
FB = [f"https://scontent-eze1-1.xx.fbcdn.net/v/t45/{i}_n.jpg?oh=sig{i}&oe=1" for i in range(12)]
WEB = [f"https://img.example.test/{i}.jpg" for i in range(3)]
DL = {"max_bytes": 2_000_000, "timeout_seconds": 5, "per_host_interval_seconds": 0}
CFG = {"enabled": True, "daily_cap": 3000, "min_confidence": "media", "skip_sources": []}


async def fake_resolve(host):
    return ["93.184.216.34"]


def ok(request):
    return httpx.Response(200, headers={"content-type": "image/jpeg"}, content=JPEG)


class FakeProvider:
    model = "gpt-6-luna"

    def __init__(self, answer=None, *, error=None, delay=0.0):
        self.answer = answer or {"visible": True, "colors": [{"color": "gris", "prob": 70},
                                                             {"color": "verde", "prob": 30}]}
        self.error, self.delay, self.calls = error, delay, []

    async def listing_color(self, images):
        self.calls.append(len(images))
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.error:
            raise self.error
        return {**self.answer, "tokens_in": 1000, "tokens_out": 30, "model": self.model}


class FakeDB:
    def __init__(self, cap=3000):
        self.cap, self.runs, self.saved, self.seen = cap, [], {}, []

    async def reserve_run(self, listing_id, photos, daily_cap):
        if len(self.runs) >= daily_cap:
            return None
        self.runs.append({"listing_id": listing_id, "photos": photos})
        return len(self.runs)

    async def finish_run(self, run_id, *, model, result, error):
        self.runs[run_id - 1].update(model=model, result=result, error=error)

    async def save(self, listing_id, value_color, value):
        self.saved[listing_id] = (value_color, value)
        return True

    async def mark_seen(self, listing_id):
        self.seen.append(listing_id)


def reader(provider=None, cfg=None, handler=ok, fake=None, dry_run=False):
    fake = fake or FakeDB()
    requests: list[str] = []

    def record(request):
        requests.append(str(request.url))
        return handler(request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(record))
    r = cv.ColorVision(provider or FakeProvider(), {**CFG, **(cfg or {})}, DL, client=client,
                       resolve=fake_resolve, dry_run=dry_run)
    return r, fake, requests


def run_with(fake, coro):
    with patch.object(cv, "reserve_run", fake.reserve_run), patch.object(cv, "finish_run", fake.finish_run), \
            patch.object(cv, "save", fake.save), patch.object(cv, "mark_seen", fake.mark_seen), \
            patch.object(cv, "log_error", AsyncMock()):
        return asyncio.run(coro)


def row(id=1, source="facebook", images=FB, color_=None, _color=None):
    attrs = {"_color": _color} if _color is not None else {}
    return {"id": id, "source": source, "images": list(images), "color": color_, "attributes": attrs}


# --------------------------------------------------------------------------- downloader

def test_meta_hosts_only_for_color():
    url = FB[0]
    assert not photo_hash.downloadable(url)
    assert photo_hash.downloadable(url, allow_meta=True)
    assert photo_hash.first_urls(FB, 10) == []
    assert photo_hash.first_urls(FB, 10, allow_meta=True) == FB[:10]
    # Still never an IP literal or plain http, color or not.
    assert not photo_hash.downloadable("https://10.0.0.1/a.jpg", allow_meta=True)
    assert not photo_hash.downloadable("http://scontent.xx.fbcdn.net/a.jpg", allow_meta=True)


def test_the_duplicates_fetcher_still_refuses_meta_and_the_color_one_fetches_it():
    seen: list[str] = []

    def record(request):
        seen.append(str(request.url))
        return ok(request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(record))
    dup = photo_hash.fetcher(client, DL, fake_resolve)
    with pytest.raises(photo_hash.DownloadError, match="disallowed"):
        asyncio.run(dup(FB[0]))
    assert seen == []
    col = photo_hash.fetcher(client, DL, fake_resolve, allow_meta=True)
    assert asyncio.run(col(FB[0])) == JPEG
    assert seen == [FB[0]]


def test_the_duplicates_pass_still_skips_facebook_photos():
    from test_photo_hash import queue_row, run_pass

    _, fake, requests, _, _ = run_pass([queue_row(source="facebook", images=FB[:3])], ok,
                                       {"photo_hash": {"skip_sources": []}})
    assert (requests, fake.saved) == ([], {})


def test_the_byte_cap_holds_for_color():
    def big(request):
        return httpx.Response(200, headers={"content-type": "image/jpeg"}, content=b"x" * 3_000_000)

    client = httpx.AsyncClient(transport=httpx.MockTransport(big))
    fetch = photo_hash.fetcher(client, DL, fake_resolve, allow_meta=True)
    with pytest.raises(photo_hash.DownloadError, match="too large"):
        asyncio.run(fetch(FB[0]))


def test_a_photo_is_fitted_to_512x384_jpeg_in_memory():
    from PIL import Image

    out = cv.prepare_image(encode(draw("b", (1600, 900)), "PNG"))
    im = Image.open(BytesIO(out))
    assert (im.format, im.size) == ("JPEG", (512, 384))


# --------------------------------------------------------------------------- the answer

@pytest.mark.parametrize("prob,level", [(100, "alta"), (80, "alta"), (79, "media"), (50, "media"), (49, "baja")])
def test_confidence(prob, level):
    assert cv.confidence(prob) == level


def test_from_answer_main_color_and_candidates():
    code, value = cv.from_answer({"visible": True, "model": "gpt-6-luna",
                                  "colors": [{"color": "verde", "prob": 30}, {"color": "gris", "prob": 70}]},
                                 photos=4, src="k", min_confidence="media")
    assert code == "gris"
    assert value["method"] == "vision" and value["confidence"] == "media" and value["v"] == 1
    assert value["candidates"] == [{"color": "gris", "prob": 70}, {"color": "verde", "prob": 30}]
    assert (value["photos"], value["model"], value["result"], value["src"]) == (4, "gpt-6-luna", "ok", "k")
    assert value["prompt"] == prompts.LISTING_COLOR_PROMPT_VERSION
    assert color.candidates(value) == [("gris", 70), ("verde", 30)]


def test_below_min_confidence_the_main_color_is_null_but_candidates_stay():
    answer = {"visible": True, "colors": [{"color": "azul", "prob": 45}, {"color": "gris", "prob": 35},
                                          {"color": "negro", "prob": 20}]}
    code, value = cv.from_answer(answer, photos=2, src="k", min_confidence="media")
    assert code is None and value["result"] == "low_confidence" and value["confidence"] == "baja"
    assert [c["color"] for c in value["candidates"]] == ["azul", "gris", "negro"]
    code, _ = cv.from_answer(answer, photos=2, src="k", min_confidence="baja")
    assert code == "azul"
    code, _ = cv.from_answer({"visible": True, "colors": [{"color": "gris", "prob": 70}]}, photos=1, src="k",
                             min_confidence="alta")
    assert code is None


@pytest.mark.parametrize("answer", [{"visible": False, "colors": [{"color": "sin_dato", "prob": 100}]},
                                    {"visible": True, "colors": [{"color": "sin_dato", "prob": 100}]},
                                    {"visible": False, "colors": [{"color": "rojo", "prob": 100}]}])
def test_not_visible(answer):
    code, value = cv.from_answer(answer, photos=3, src="k", min_confidence="media")
    assert code is None and value["result"] == "no_visible" and value["candidates"] is None


def test_settings():
    assert cv.settings(None)["enabled"] is False          # no row: no spending
    s = cv.settings({"enabled": True, "daily_cap": 10**9, "min_confidence": "x", "skip_sources": ["kavak"]})
    assert s == {"enabled": True, "daily_cap": 50_000, "min_confidence": "media", "skip_sources": ["kavak"]}


# --------------------------------------------------------------------------- selection

def test_photos_key_ignores_the_signature():
    resigned = [u.replace("sig", "other") for u in FB]
    assert cv.photos_key(FB[:10]) == cv.photos_key(resigned[:10])
    assert cv.photos_key(FB[:10]) != cv.photos_key(FB[1:11])


def test_needs_vision():
    urls = FB[:10]
    key = cv.photos_key(urls)
    assert cv.needs_vision(row(), urls) == (True, 0)
    assert cv.needs_vision(row(), []) == (False, 0)
    # Never over the source or the text.
    assert cv.needs_vision(row(color_="rojo", _color=color.build("source", "Rojo")), urls)[0] is False
    assert cv.needs_vision(row(color_="rojo", _color=color.build("text", "color rojo")), urls)[0] is False
    done = {**color.build("vision", "gris 100"), "src": key, "prompt": prompts.LISTING_COLOR_PROMPT_VERSION,
            "result": "ok", "attempts": 1}
    assert cv.needs_vision(row(color_="gris", _color=done), urls) == (False, 1)
    assert cv.needs_vision(row(_color={**done, "result": "no_visible"}), urls) == (False, 1)
    # Other photos or another prompt: read again.
    assert cv.needs_vision(row(color_="gris", _color={**done, "src": "old"}), urls) == (True, 0)
    assert cv.needs_vision(row(color_="gris", _color={**done, "prompt": "listing_color-v0"}), urls) == (True, 0)
    # A failure is retried up to MAX_ATTEMPTS.
    failed = {**done, "result": "error", "attempts": 1}
    assert cv.needs_vision(row(_color=failed), urls) == (True, 1)
    assert cv.needs_vision(row(_color={**failed, "attempts": cv.MAX_ATTEMPTS}), urls)[0] is False


def test_inline_wanted_only_color_searches_and_listings_without_color():
    rows = {1: row(1), 2: row(2, color_="blanco", _color=color.build("source", "Blanco")), 3: row(3), 4: row(4)}
    alerts = [{"profile": {"filters": {"make": "Volkswagen", "colors": ["blanco"]}, "id": "a"}},
              {"profile": {"filters": {"make": "Fiat"}, "id": "b"}}]
    passing = {"a": [1, 2, 3], "b": [4]}
    assert cv.inline_wanted(alerts, lambda p: passing[p["id"]], rows) == [1, 3]


# --------------------------------------------------------------------------- the reader

def test_read_writes_the_color_and_updates_the_row():
    r, fake, requests = reader()
    listing = row()
    assert run_with(fake, r.read(listing)) is True
    assert len(requests) == 10                     # all the photos, up to 10, Facebook included
    assert r.provider.calls == [10]
    code, value = fake.saved[1]
    assert code == "gris" and value["photos"] == 10 and value["src"] == cv.photos_key(FB[:10])
    assert listing["color"] == "gris" and listing["attributes"]["_color"] == value
    assert fake.runs == [{"listing_id": 1, "photos": 10, "model": "gpt-6-luna", "result": "ok", "error": None}]
    assert (r.stats["tokens_in"], r.stats["colored"]) == (1000, 1)


def test_read_never_overwrites_the_source_and_skips_seen_photos():
    r, fake, requests = reader()
    src = row(color_="rojo", _color=color.build("source", "Rojo"))
    seen = row(2, color_="gris", _color={**color.build("vision", "gris 100"), "src": cv.photos_key(FB[:10]),
                                          "prompt": prompts.LISTING_COLOR_PROMPT_VERSION, "result": "ok"})
    assert run_with(fake, r.read_many([src, seen])) == 0
    assert (requests, fake.saved, fake.runs, fake.seen) == ([], {}, [], [2])


def test_skip_sources():
    r, fake, requests = reader(cfg={"skip_sources": ["facebook"]})
    assert run_with(fake, r.read(row())) is False
    assert requests == [] and fake.runs == []


def test_the_daily_cap_stops_the_reader():
    fake = FakeDB()
    r, fake, _ = reader(cfg={"daily_cap": 2}, fake=fake)
    rows = [row(i, source="deruedas", images=WEB) for i in range(1, 6)]
    with patch.object(cv, "CONCURRENCY", 1):
        written = run_with(fake, r.read_many(rows))
    assert written == 2 and len(fake.runs) == 2 and r.capped and r.provider.calls == [3, 3]


def test_a_failed_call_counts_and_is_retried_later():
    from llm.provider import LLMError

    r, fake, _ = reader(FakeProvider(error=LLMError("la API de OpenAI devolvió 500")))
    listing = row(source="deruedas", images=WEB)
    assert run_with(fake, r.read(listing)) is False
    code, value = fake.saved[1]
    assert code is None and value["result"] == "error" and value["attempts"] == 1
    assert fake.runs[0]["result"] == "error" and "500" in fake.runs[0]["error"]
    assert cv.needs_vision(listing, WEB) == (True, 1)


def test_no_downloadable_photo_calls_nothing():
    r, fake, _ = reader(handler=lambda request: httpx.Response(404))
    assert run_with(fake, r.read(row(source="deruedas", images=WEB))) is False
    assert fake.runs == [] and fake.saved[1][1]["result"] == "no_photos"


def test_dry_run_downloads_calls_and_writes_nothing():
    r, fake, requests = reader(dry_run=True)
    assert run_with(fake, r.read_many([row(1), row(2, source="deruedas", images=WEB)])) == 0
    assert (requests, fake.runs, fake.saved) == ([], [], {})
    assert (r.stats["listings"], r.stats["photos"]) == (2, 13)
    lines = backfill.report({"queued": 2, **r.stats}, dry_run=True)
    assert any("costo estimado" in line for line in lines)


def test_resolve_inline_keeps_to_its_budget():
    r, fake, _ = reader(FakeProvider(delay=5))
    fast_rows = [row(1, source="deruedas", images=WEB[:1])]
    import time
    t0 = time.monotonic()
    written = run_with(fake, cv.resolve_inline(fast_rows, budget=0.3, reader=r))
    assert time.monotonic() - t0 < 2
    assert written == 0 and fast_rows[0]["color"] is None
    # The reservation still finishes (it counts toward the cap).
    assert len(fake.runs) == 1


def test_resolve_inline_reads_within_the_budget():
    r, fake, _ = reader()
    rows = [row(1, source="deruedas", images=WEB), row(2, source="deruedas", images=WEB[:2])]
    assert run_with(fake, cv.resolve_inline(rows, budget=5, reader=r)) == 2
    assert [x["color"] for x in rows] == ["gris", "gris"]


# --------------------------------------------------------------------------- wiring

class FakeScorer:
    def __init__(self, rows):
        self.rows = rows

    def evaluate(self, lid, profile):
        return object() if lid != 3 else None     # 3 fails another filter


def test_scheduler_resolves_only_color_search_candidates_without_color():
    rows = {1: row(1), 2: row(2, color_="blanco", _color=color.build("source", "Blanco")), 3: row(3), 4: row(4)}
    keys = {1: ("volkswagen", "gol"), 2: ("volkswagen", "gol"), 3: ("volkswagen", "gol"), 4: ("fiat", "uno")}
    alerts = [{"id": 1, "profile": {"filters": {"make": "Volkswagen", "model": "Gol", "colors": ["blanco"]}}},
              {"id": 2, "profile": {"filters": {"make": "Fiat", "model": "Uno"}}}]
    inline = AsyncMock(return_value=1)
    with patch.object(scheduler.color_vision, "resolve_inline", inline):
        assert asyncio.run(scheduler.resolve_colors(alerts, keys, FakeScorer(rows))) == 1
    assert [r["id"] for r in inline.await_args.args[0]] == [1]


def test_scheduler_without_color_searches_reads_nothing():
    inline = AsyncMock()
    with patch.object(scheduler.color_vision, "resolve_inline", inline):
        assert asyncio.run(scheduler.resolve_colors([{"id": 1, "profile": {"filters": {"make": "Fiat"}}}],
                                                    {1: ("fiat", None)}, FakeScorer({1: row(1)}))) == 0
    inline.assert_not_awaited()


def test_the_pass_is_off_without_config():
    with patch.object(cv.db, "get_config", AsyncMock(return_value=None)):
        assert asyncio.run(cv.ColorVision.create(provider=FakeProvider())) is None

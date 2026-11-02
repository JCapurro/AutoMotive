"""PAR-02 resto: the photo hash (intelligence/photo_hash.py) and its pass
(pipeline/photo_hash.py), off by default. No network: httpx.MockTransport."""
from __future__ import annotations

import asyncio
import builtins
import unittest
from unittest.mock import AsyncMock, patch

import httpx

from intelligence import photo_hash
from pipeline import photo_hash as pass_mod
from photo_fixtures import draw, encode

# imagehash.phash (ImageHash 4.3.2, Pillow 12.3.0) of the images drawn by
# tests/photo_fixtures.draw, computed once in dev: the hand-written pHash must
# give the very same bits.
VECTORS = {"a": "ac53862cd38c73d3", "b": "883ce1877cc17dc5", "c": "e0f3d9c27173e842"}


class PhashTests(unittest.TestCase):
    def test_same_bits_as_imagehash(self):
        for kind, expected in VECTORS.items():
            with self.subTest(kind):
                self.assertEqual(photo_hash.phash(encode(draw(kind))), expected)

    def test_a_rescaled_or_recompressed_copy_stays_within_2_bits(self):
        original = draw("a")
        for name, data in {"half size": encode(original.resize((320, 240))),
                           "jpeg q40": encode(original, "JPEG", quality=40),
                           "jpeg q85 small": encode(original.resize((480, 360)), "JPEG", quality=85)}.items():
            with self.subTest(name):
                self.assertLessEqual(photo_hash.distance(photo_hash.phash(data), VECTORS["a"]), 2)

    def test_different_images_are_farther_than_the_tolerance(self):
        for x, y in (("a", "b"), ("a", "c"), ("b", "c")):
            self.assertGreater(photo_hash.distance(VECTORS[x], VECTORS[y]), 6)

    def test_flat_and_invalid_hashes(self):
        self.assertTrue(photo_hash.is_flat("0000000000000000"))
        self.assertTrue(photo_hash.is_flat("ffffffffffffffef"))
        self.assertFalse(photo_hash.is_flat(VECTORS["a"]))
        self.assertFalse(photo_hash.valid("xyz"))
        self.assertFalse(photo_hash.valid(None))
        self.assertIsNone(photo_hash.best_match(["zz"], [VECTORS["a"]]))

    def test_an_image_over_the_pixel_cap_is_never_decoded(self):
        from PIL import Image
        png = encode(Image.new("RGB", (1500, 1000), (200, 10, 10)), "PNG")
        self.assertLess(len(png), 50_000, "flat PNGs compress to almost nothing")
        with patch.object(photo_hash, "MAX_IMAGE_PIXELS", 1_000_000), \
                patch.object(Image.Image, "convert", side_effect=AssertionError("decoded")):
            # 1.5 M pixels: between 1x and 2x Pillow's own limit, where Pillow only warns.
            with self.assertRaises(photo_hash.TooManyPixels), self.assertWarns(Image.DecompressionBombWarning):
                photo_hash.phash(png)

    def test_an_unreadable_file_raises_and_without_pillow_it_says_so(self):
        with self.assertRaises(Exception):
            photo_hash.phash(b"<html>not an image</html>")
        real_import = builtins.__import__

        def no_pil(name, *args, **kw):
            if name == "PIL" or name.startswith("PIL."):
                raise ImportError("no PIL")
            return real_import(name, *args, **kw)

        with patch("builtins.__import__", no_pil):
            self.assertFalse(photo_hash.available())
            with self.assertRaises(photo_hash.PillowMissing):
                photo_hash.phash(b"x")


JPEG = encode(draw("a"), "JPEG", quality=85)
URLS = [f"https://img.example.test/{i}.jpg" for i in range(5)]


def queue_row(id=1, source="mercadolibre", images=URLS, stored=None):
    return {"id": id, "source": source, "images": images, "photo_hashes": stored}


class FakeRepo:
    def __init__(self, rows, cap=600):
        self.rows, self.cap, self.used = rows, cap, 0
        self.saved: dict[int, dict] = {}
        self.runs: list[tuple] = []
        self.seen: dict[int, dict] = {}

    async def photo_hash_queue(self, **kw):
        self.queue_kw = kw
        return self.rows

    async def reserve_photo_run(self, listing_id, images, daily_cap):
        if self.used + images > daily_cap:
            return None
        self.used += images
        self.runs.append((listing_id, images))
        return len(self.runs)

    async def finish_photo_run(self, run_id, *, hashed, error):
        self.runs[run_id - 1] += (hashed, error)

    async def save_photo_hashes(self, listing_id, value):
        self.saved[listing_id] = value

    async def mark_photo_hashes_seen(self, listing_id, value):
        self.seen[listing_id] = value


PUBLIC = {"img.example.test": ["93.184.216.34"], "cdn.example.test": ["2606:2800:220:1::1"],
          "internal.example.test": ["10.0.0.5"], "mixed.example.test": ["93.184.216.34", "127.0.0.1"]}


async def fake_resolve(host):
    if host not in PUBLIC:
        raise OSError("no such host")
    return PUBLIC[host]


def run_pass(rows, handler, config=None, *, enabled=True, stop=None):
    cfg = {"photo_hash": {"enabled": enabled, "per_host_interval_seconds": 0, "daily_image_cap": 600,
                          "max_bytes": 100_000, **((config or {}).get("photo_hash") or {})},
           **{k: v for k, v in (config or {}).items() if k != "photo_hash"}}
    requests: list[str] = []

    def record(request: httpx.Request) -> httpx.Response:
        requests.append(str(request.url))
        return handler(request)

    fake = FakeRepo(rows)
    client = httpx.AsyncClient(transport=httpx.MockTransport(record))
    detect = AsyncMock(return_value=0)
    log_error = AsyncMock()
    with patch.object(pass_mod, "repo", fake), \
            patch.object(pass_mod.db, "get_config", AsyncMock(return_value=cfg)), \
            patch.object(pass_mod, "log_error", log_error), \
            patch("pipeline.risk_duplicates.detect_for", detect):
        done = asyncio.run(pass_mod.photo_hash_pass(stop, client=client, resolve=fake_resolve))
    return done, fake, requests, detect, log_error


def ok(request):
    return httpx.Response(200, headers={"content-type": "image/jpeg"}, content=JPEG)


class PassTests(unittest.TestCase):
    def setUp(self):
        pass_mod._pillow_reported = False

    def test_off_by_default_makes_no_request(self):
        done, fake, requests, detect, _ = run_pass([queue_row()], ok, enabled=False)
        self.assertEqual((requests, fake.saved, done["listings"]), ([], {}, 0))

    def test_hashes_the_first_three_photos_and_runs_the_detection(self):
        done, fake, requests, detect, _ = run_pass([queue_row()], ok)
        self.assertEqual(requests, URLS[:3])
        saved = fake.saved[1]
        self.assertEqual(saved["urls"], URLS[:3])
        self.assertEqual(len(saved["hashes"]), 3)
        self.assertTrue(all(photo_hash.distance(h, VECTORS["a"]) <= 2 for h in saved["hashes"]))
        self.assertEqual((saved["attempts"], saved["error"], saved["v"]), (1, None, 1))
        self.assertEqual(fake.runs, [(1, 3, 3, None)])
        detect.assert_awaited_once_with([1])
        self.assertEqual(done, {"listings": 1, "images": 3, "hashed": 3})

    def test_already_hashed_urls_are_not_downloaded_again_and_are_marked_seen(self):
        stored = {"v": 1, "urls": URLS[:3], "hashes": [VECTORS["a"]] * 3, "attempts": 1}
        _, fake, requests, _, _ = run_pass([queue_row(stored=stored)], ok)
        self.assertEqual(requests, [])
        self.assertEqual(fake.seen, {1: stored}, "the queue stops returning it")
        _, fake, _, _, _ = run_pass([queue_row(images=["http://img.example.test/a.jpg"])], ok)
        self.assertEqual((fake.seen[1]["urls"], fake.seen[1]["error"]), ([], "no downloadable photo"))

    def test_the_queue_is_asked_for_what_still_needs_work(self):
        _, fake, _, _, _ = run_pass([], ok, {"photo_hash": {"max_attempts": 3}})
        self.assertEqual((fake.queue_kw["version"], fake.queue_kw["max_attempts"]), (pass_mod.VERSION, 3))

    def test_new_urls_start_over(self):
        stored = {"v": 1, "urls": ["https://img.example.test/old.jpg"], "hashes": [None], "attempts": 2}
        _, fake, requests, _, _ = run_pass([queue_row(stored=stored)], ok)
        self.assertEqual(len(requests), 3)
        self.assertEqual(fake.saved[1]["attempts"], 1)

    def test_failures_retry_up_to_max_attempts_then_stop(self):
        stored = {"v": 1, "urls": URLS[:3], "hashes": [None, VECTORS["a"], None], "attempts": 1}
        _, fake, requests, _, _ = run_pass([queue_row(stored=stored)], ok)
        self.assertEqual(len(requests), 3)
        self.assertEqual(fake.saved[1]["attempts"], 2)
        stored["attempts"] = 2
        _, fake, requests, _, _ = run_pass([queue_row(stored=stored)], ok)
        self.assertEqual(requests, [])

    def test_too_large_html_and_timeouts_leave_a_null_hash_and_count_the_attempt(self):
        def handler(request):
            name = request.url.path
            if name.endswith("0.jpg"):
                return httpx.Response(200, headers={"content-type": "image/jpeg"}, content=b"x" * 200_000)
            if name.endswith("1.jpg"):
                return httpx.Response(200, headers={"content-type": "text/html"}, content=b"<html>")
            raise httpx.ReadTimeout("slow", request=request)

        done, fake, _, detect, _ = run_pass([queue_row()], handler)
        saved = fake.saved[1]
        self.assertEqual(saved["hashes"], [None, None, None])
        self.assertEqual(saved["attempts"], 1)
        self.assertIn("too large", saved["error"])
        self.assertIn("not an image", saved["error"])
        self.assertIn("ReadTimeout", saved["error"])
        detect.assert_not_awaited()
        self.assertEqual(done["hashed"], 0)

    def test_the_daily_cap_stops_the_pass(self):
        rows = [queue_row(id=i) for i in range(1, 4)]
        _, fake, requests, _, _ = run_pass(rows, ok, {"photo_hash": {"daily_image_cap": 7}})
        self.assertEqual(len(requests), 6)
        self.assertEqual(sorted(fake.saved), [1, 2])

    def test_skip_sources_and_unsafe_urls_are_never_downloaded(self):
        rows = [queue_row(id=1, source="facebook"),
                queue_row(id=2, images=["http://img.example.test/a.jpg", "https://127.0.0.1/a.jpg",
                                        "https://localhost/a.jpg", "https://[::1]/a.jpg"])]
        _, fake, requests, _, _ = run_pass(rows, ok, {"photo_hash": {"skip_sources": ["facebook"]}})
        self.assertEqual(requests, [])
        self.assertEqual(fake.saved, {})

    def test_the_default_skip_sources_are_the_real_facebook_and_instagram_source_ids(self):
        from collectors import REGISTRY
        from intelligence.config import risk
        skip = risk(None)["photo_hash"]["skip_sources"]
        self.assertTrue(set(skip) <= set(REGISTRY), skip)
        instagram = {sid for sid, cls in REGISTRY.items() if cls.__module__ == "collectors.instagram"}
        self.assertTrue(instagram and instagram <= set(skip), instagram)
        self.assertIn("facebook", skip)

    def test_meta_hosts_are_never_downloaded_whatever_the_config(self):
        for url in ("https://scontent.cdninstagram.com/v/a.jpg", "https://scontent-eze1-1.xx.fbcdn.net/a.jpg",
                    "https://www.facebook.com/a.jpg", "https://instagram.com/a.jpg"):
            with self.subTest(url):
                self.assertFalse(pass_mod.downloadable(url))
        _, fake, requests, _, _ = run_pass([queue_row(source="onlycarsusados",
                                                      images=["https://scontent.cdninstagram.com/a.jpg"])],
                                           ok, {"photo_hash": {"skip_sources": []}})
        self.assertEqual((requests, fake.saved), ([], {}))

    def test_redirects_are_checked_before_every_hop(self):
        def handler(request):
            path = request.url.path
            if request.url.host == "img.example.test" and path == "/0.jpg":
                return httpx.Response(302, headers={"location": "https://169.254.169.254/latest/meta-data"})
            if path == "/1.jpg":
                return httpx.Response(302, headers={"location": "https://internal.example.test/x.jpg"})
            if path == "/2.jpg":
                return httpx.Response(301, headers={"location": "https://cdn.example.test/ok.jpg"})
            return ok(request)

        _, fake, requests, _, _ = run_pass([queue_row()], handler)
        self.assertEqual(requests, URLS[:3] + ["https://cdn.example.test/ok.jpg"],
                         "neither the IP literal nor the internal host is ever requested")
        saved = fake.saved[1]
        self.assertEqual([h is None for h in saved["hashes"]], [True, True, False])
        self.assertIn("disallowed URL", saved["error"])
        self.assertIn("non-public address", saved["error"])

    def test_a_host_that_resolves_to_a_private_address_or_does_not_resolve_is_never_requested(self):
        rows = [queue_row(images=["https://internal.example.test/a.jpg", "https://mixed.example.test/b.jpg",
                                  "https://nowhere.example.test/c.jpg"])]
        _, fake, requests, _, _ = run_pass(rows, ok)
        self.assertEqual(requests, [])
        self.assertEqual(fake.saved[1]["hashes"], [None, None, None])
        self.assertIn("cannot resolve", fake.saved[1]["error"])

    def test_a_redirect_loop_stops(self):
        def loop(request):
            return httpx.Response(302, headers={"location": str(request.url)})

        _, fake, requests, _, _ = run_pass([queue_row(images=URLS[:1])], loop)
        self.assertEqual(len(requests), pass_mod.MAX_REDIRECTS + 1)
        self.assertIn("too many redirects", fake.saved[1]["error"])

    def test_without_pillow_it_logs_once_and_does_nothing(self):
        with patch.object(pass_mod.photo_hash, "available", return_value=False):
            _, _, requests, _, log_error = run_pass([queue_row()], ok)
            run_pass([queue_row()], ok)
        self.assertEqual(requests, [])
        self.assertEqual(log_error.await_args.args[:2], ("photo_hash", "pillow"))

    def test_a_queue_failure_never_raises(self):
        with patch.object(FakeRepo, "photo_hash_queue", AsyncMock(side_effect=RuntimeError("db down"))):
            done, _, _, _, log_error = run_pass([queue_row()], ok)
        self.assertEqual(done["listings"], 0)
        self.assertEqual(log_error.await_args.args[:2], ("photo_hash", "pass"))

    def test_the_host_pacer_waits_between_requests_to_the_same_host(self):
        now = [0.0]
        waits: list[float] = []

        async def sleep(s):
            waits.append(s)
            now[0] += s

        pacer = pass_mod.HostPacer(1.0, clock=lambda: now[0], sleep=sleep)

        async def go():
            await pacer.wait("https://a.test/1")
            await pacer.wait("https://b.test/1")
            now[0] += 0.25
            await pacer.wait("https://a.test/2")

        asyncio.run(go())
        self.assertEqual(waits, [0.75])


if __name__ == "__main__":
    unittest.main()

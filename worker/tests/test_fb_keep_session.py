"""Facebook searches write back the cookies Facebook refreshed (2026-11-07):
the session is kept like a real browser keeps it, not replayed from the
login's frozen snapshot."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from collectors import facebook as fb


def state(*names, fr="old"):
    cookies = [{"name": n, "value": fr if n == "fr" else "v", "domain": ".facebook.com"} for n in names]
    return {"cookies": cookies, "origins": []}


class KeepSessionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = Path(self.dir.name) / "fb_state.json"
        self.path.write_text(json.dumps(state("c_user", "xs", "fr")), encoding="utf-8")
        patcher = patch.object(fb, "FB_STORAGE_STATE", str(self.path))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self.dir.cleanup)

    def ctx(self, s):
        return MagicMock(storage_state=AsyncMock(return_value=s))

    def saved(self):
        return json.loads(self.path.read_text(encoding="utf-8"))

    async def test_refreshed_cookies_are_written_back(self):
        fresh = state("c_user", "xs", "fr", fr="new")
        self.assertTrue(await fb._keep_session(self.ctx(fresh), fb._state_mtime()))
        self.assertEqual(self.saved(), fresh)
        if os.name != "nt":
            self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)

    async def test_a_logged_out_state_never_overwrites_the_session(self):
        before = self.saved()
        self.assertFalse(await fb._keep_session(self.ctx(state("xs", "fr", fr="new")), fb._state_mtime()))
        self.assertEqual(self.saved(), before)

    async def test_a_session_renewed_during_the_run_is_kept(self):
        loaded = fb._state_mtime()
        renewed = state("c_user", "xs", fr="login")
        self.path.write_text(json.dumps(renewed), encoding="utf-8")
        os.utime(self.path, (loaded + 5, loaded + 5))
        self.assertFalse(await fb._keep_session(self.ctx(state("c_user", "xs", "fr", fr="new")), loaded))
        self.assertEqual(self.saved(), renewed)

    async def test_an_unchanged_state_is_not_rewritten(self):
        mtime = fb._state_mtime()
        self.assertFalse(await fb._keep_session(self.ctx(self.saved()), mtime))
        self.assertEqual(fb._state_mtime(), mtime)

    async def test_off_switch_and_errors_never_raise(self):
        with patch.object(fb.config, "FB_KEEP_SESSION", False):
            self.assertFalse(await fb._keep_session(self.ctx(state("c_user", fr="new")), fb._state_mtime()))
        broken = MagicMock(storage_state=AsyncMock(side_effect=RuntimeError("context closed")))
        self.assertFalse(await fb._keep_session(broken, fb._state_mtime()))
        self.assertFalse(await fb._keep_session(self.ctx(state("c_user", fr="new")), None))


if __name__ == "__main__":
    unittest.main()

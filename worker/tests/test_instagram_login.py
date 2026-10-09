"""Manual login must not replace a valid session while verification is pending."""
from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from tools import instagram_login as login


def fake_login(monkeypatch, path, *, url, cookies):
    page = SimpleNamespace(url=url, goto=AsyncMock())

    async def storage_state(*, path):
        from pathlib import Path
        Path(path).write_text(json.dumps({"cookies": cookies, "origins": []}), encoding="utf-8")

    context = SimpleNamespace(pages=[page], new_page=AsyncMock(return_value=page),
                              cookies=AsyncMock(return_value=cookies),
                              storage_state=AsyncMock(side_effect=storage_state))
    browser = SimpleNamespace(contexts=[context], new_context=AsyncMock(return_value=context),
                              close=AsyncMock())
    chromium = SimpleNamespace(launch=AsyncMock(return_value=browser),
                                connect_over_cdp=AsyncMock(return_value=browser))

    @asynccontextmanager
    async def playwright():
        yield SimpleNamespace(chromium=chromium)

    monkeypatch.setattr(login, "async_playwright", playwright)
    monkeypatch.setattr(login, "INSTAGRAM_STORAGE_STATE", str(path))
    process = SimpleNamespace(poll=lambda: 0)
    monkeypatch.setattr(login, "launch_chrome", lambda *args: (process, "http://127.0.0.1:9999"),
                        raising=False)
    monkeypatch.setattr("builtins.input", lambda prompt: "")
    return context


@pytest.mark.parametrize("url", [
    "https://www.instagram.com/accounts/login/",
    "https://www.instagram.com/challenge/",
    "https://www.instagram.com/checkpoint/",
])
def test_pending_verification_preserves_existing_session(monkeypatch, tmp_path, url):
    path = tmp_path / "state.json"
    path.write_text("previous-session", encoding="utf-8")
    context = fake_login(monkeypatch, path, url=url,
                         cookies=[{"name": "sessionid", "value": "test-session"}])
    with pytest.raises(SystemExit, match="pendientes"):
        asyncio.run(login.main())
    assert path.read_text(encoding="utf-8") == "previous-session"
    context.storage_state.assert_not_awaited()


@pytest.mark.parametrize("cookies", [[], [{"name": "sessionid", "value": ""}]])
def test_missing_session_is_not_saved(monkeypatch, tmp_path, cookies):
    path = tmp_path / "state.json"
    fake_login(monkeypatch, path, url="https://www.instagram.com/", cookies=cookies)
    with pytest.raises(SystemExit, match="No hay una sesión autenticada"):
        asyncio.run(login.main())
    assert not path.exists()


def test_completed_login_exports_session(monkeypatch, tmp_path):
    path = tmp_path / "state.json"
    context = fake_login(monkeypatch, path, url="https://www.instagram.com/",
                         cookies=[{"name": "sessionid", "value": "test-session"}])
    asyncio.run(login.main())
    assert json.loads(path.read_text(encoding="utf-8"))["cookies"][0]["name"] == "sessionid"
    context.storage_state.assert_awaited_once_with(path=str(path))

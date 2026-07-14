from unittest.mock import MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from core.web.routers import launch as launch_router
from core.web.server import app


@pytest.mark.asyncio
async def test_launch_status_reports_missing_gui_terminal(monkeypatch):
    monkeypatch.setattr(launch_router.sys, "platform", "linux")
    monkeypatch.setenv("DISPLAY", ":0")
    monkeypatch.setattr(launch_router.shutil, "which", lambda _name: None)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        response = await ac.get("/api/launch/status")

    assert response.status_code == 200
    assert response.json() == {
        "available": False,
        "terminal": None,
        "mode": "local_gui",
        "reason": "No supported GUI terminal emulator was found on the CodeAgent server",
    }


@pytest.mark.asyncio
async def test_launch_rejects_headless_fallback_instead_of_spawning_without_tty(
    monkeypatch,
):
    monkeypatch.setattr(launch_router.sys, "platform", "linux")
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.setattr(launch_router.shutil, "which", lambda _name: None)
    popen = MagicMock()
    monkeypatch.setattr(launch_router.subprocess, "Popen", popen)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        response = await ac.post("/api/launch/codex")

    assert response.status_code == 503
    assert "no graphical desktop" in response.json()["detail"]
    popen.assert_not_called()


@pytest.mark.asyncio
async def test_launch_opens_supported_terminal(monkeypatch, tmp_path):
    monkeypatch.setattr(launch_router.sys, "platform", "linux")
    monkeypatch.setenv("DISPLAY", ":0")
    monkeypatch.setattr(
        launch_router.shutil,
        "which",
        lambda name: "/usr/bin/xterm" if name == "xterm" else None,
    )
    popen = MagicMock()
    monkeypatch.setattr(launch_router.subprocess, "Popen", popen)
    monkeypatch.chdir(tmp_path)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        response = await ac.post("/api/launch/claude")

    assert response.status_code == 200
    assert response.json()["terminal"] == "xterm"
    args, kwargs = popen.call_args
    assert args[0][:2] == ["xterm", "-e"]
    assert kwargs["cwd"] == tmp_path.resolve()


@pytest.mark.asyncio
async def test_launch_rejects_unknown_engine():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        response = await ac.post("/api/launch/shell")

    assert response.status_code == 400

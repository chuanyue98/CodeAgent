"""Tests for the /api/chat/turns endpoints, with TaskRunner mocked out —
no real engine CLI is spawned in CI."""

from __future__ import annotations

import time

import pytest
from httpx import ASGITransport, AsyncClient

from core.services.runner_service import TaskRunStatus
from core.web.routers import chat as chat_router
from core.web.server import app


class _FakeRunner:
    def __init__(self):
        self.started: list[dict] = []
        self._status = None

    def run_chat_turn(self, engine, message, session_id=None, group="common"):
        self.started.append(
            {
                "engine": engine,
                "message": message,
                "session_id": session_id,
                "group": group,
            }
        )
        if engine == "shell":
            raise ValueError("Invalid engine: 'shell'")
        self._status = TaskRunStatus(
            task_id="chat_claude_123",
            engine=engine,
            pid=4242,
            status="running",
            log_path="/tmp/chat_claude_123.jsonl",
            start_time=time.time(),
        )
        return self._status

    def get_status(self, task_id):
        if self._status is None or task_id != self._status.task_id:
            return None
        return self._status


@pytest.fixture
def fake_runner(monkeypatch):
    fake = _FakeRunner()
    monkeypatch.setattr(chat_router, "_runner", fake)
    return fake


@pytest.mark.asyncio
async def test_start_chat_turn_returns_running_status(fake_runner):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        response = await ac.post(
            "/api/chat/turns",
            json={"engine": "claude", "message": "hello"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["engine"] == "claude"
    assert data["status"] == "running"
    assert fake_runner.started == [
        {"engine": "claude", "message": "hello", "session_id": None, "group": "common"}
    ]


@pytest.mark.asyncio
async def test_start_chat_turn_passes_session_id_and_group(fake_runner):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        response = await ac.post(
            "/api/chat/turns",
            json={
                "engine": "codex",
                "message": "continue",
                "session_id": "abc-123",
                "group": "work",
            },
        )

    assert response.status_code == 200
    assert fake_runner.started == [
        {
            "engine": "codex",
            "message": "continue",
            "session_id": "abc-123",
            "group": "work",
        }
    ]


@pytest.mark.asyncio
async def test_start_chat_turn_invalid_engine_returns_400(fake_runner):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        response = await ac.post(
            "/api/chat/turns",
            json={"engine": "shell", "message": "hello"},
        )

    assert response.status_code == 400
    assert "Invalid engine" in response.json()["detail"]


@pytest.mark.asyncio
async def test_get_chat_turn_returns_status(fake_runner):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        start = await ac.post(
            "/api/chat/turns", json={"engine": "claude", "message": "hi"}
        )
        turn_id = start.json()["task_id"]

        response = await ac.get(f"/api/chat/turns/{turn_id}")

    assert response.status_code == 200
    assert response.json()["task_id"] == turn_id


@pytest.mark.asyncio
async def test_get_chat_turn_missing_returns_404(fake_runner):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        response = await ac.get("/api/chat/turns/does-not-exist")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_stream_chat_turn_missing_returns_404(fake_runner):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        response = await ac.get("/api/chat/turns/does-not-exist/stream")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_list_engines_reports_supports_resume():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        response = await ac.get("/api/engines")

    assert response.status_code == 200
    engines = {e["id"]: e["supportsResume"] for e in response.json()}
    assert engines == {"gemini": False, "claude": True, "opencode": True, "codex": True}

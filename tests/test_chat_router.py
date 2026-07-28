"""Tests for the /api/chat/turns endpoints, with TaskRunner mocked out —
no real engine CLI is spawned in CI."""

from __future__ import annotations

import json
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

    def run_chat_turn(
        self,
        engine,
        message,
        session_id=None,
        group="common",
        project_path=None,
    ):
        self.started.append(
            {
                "engine": engine,
                "message": message,
                "session_id": session_id,
                "group": group,
                "project_path": project_path,
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

    def stop_task(self, task_id):
        if self._status is None or task_id != self._status.task_id:
            return False
        if self._status.status != "running":
            return False
        self._status.status = "stopped"
        return True


@pytest.fixture
def fake_runner(monkeypatch):
    fake = _FakeRunner()
    monkeypatch.setattr(chat_router, "_runner", fake)
    return fake


@pytest.fixture
def registered_project(tmp_path, monkeypatch):
    project = tmp_path / "project"
    project.mkdir()
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "project_registry": [{"path": str(project), "group": "work"}],
                "groups": {"work": {"skills": [], "hooks": [], "plugins": []}},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(chat_router, "get_config_path", lambda: config_path)
    return project


@pytest.mark.asyncio
async def test_legacy_chat_endpoints_are_disabled_by_config(tmp_path, monkeypatch):
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps({"agent_gateway": {"legacy_fallback": False}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(chat_router, "get_config_path", lambda: config_path)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        response = await ac.get("/api/chat/capabilities", params={"engine": "codex"})

    assert response.status_code == 404
    assert response.json()["detail"] == "Legacy Chat fallback is disabled"


@pytest.mark.asyncio
async def test_start_chat_turn_returns_running_status(fake_runner, registered_project):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        response = await ac.post(
            "/api/chat/turns",
            json={
                "engine": "claude",
                "message": "hello",
                "project_path": str(registered_project),
            },
        )

    assert response.status_code == 200
    data = response.json()
    assert data["engine"] == "claude"
    assert data["status"] == "running"
    assert fake_runner.started == [
        {
            "engine": "claude",
            "message": "hello",
            "session_id": None,
            "group": "work",
            "project_path": str(registered_project.resolve()),
        }
    ]


@pytest.mark.asyncio
async def test_start_chat_turn_uses_registered_project_group(
    fake_runner, registered_project
):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        response = await ac.post(
            "/api/chat/turns",
            json={
                "engine": "codex",
                "message": "continue",
                "session_id": "abc-123",
                "group": "untrusted-client-value",
                "project_path": str(registered_project),
            },
        )

    assert response.status_code == 200
    assert fake_runner.started == [
        {
            "engine": "codex",
            "message": "continue",
            "session_id": "abc-123",
            "group": "work",
            "project_path": str(registered_project.resolve()),
        }
    ]


@pytest.mark.asyncio
async def test_start_chat_turn_invalid_engine_returns_400(
    fake_runner, registered_project
):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        response = await ac.post(
            "/api/chat/turns",
            json={
                "engine": "shell",
                "message": "hello",
                "project_path": str(registered_project),
            },
        )

    assert response.status_code == 400
    assert "Invalid engine" in response.json()["detail"]


@pytest.mark.asyncio
async def test_get_chat_turn_returns_status(fake_runner, registered_project):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        start = await ac.post(
            "/api/chat/turns",
            json={
                "engine": "claude",
                "message": "hi",
                "project_path": str(registered_project),
            },
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
async def test_start_chat_turn_requires_registered_project(fake_runner, tmp_path):
    missing = tmp_path / "missing"
    missing.mkdir()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        response = await ac.post(
            "/api/chat/turns",
            json={
                "engine": "claude",
                "message": "hello",
                "project_path": str(missing),
            },
        )

    assert response.status_code == 400
    assert "registered" in response.json()["detail"]


@pytest.mark.asyncio
async def test_start_chat_turn_requires_project_path(fake_runner):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        response = await ac.post(
            "/api/chat/turns", json={"engine": "claude", "message": "hello"}
        )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_cancel_chat_turn_stops_running_process(fake_runner, registered_project):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        start = await ac.post(
            "/api/chat/turns",
            json={
                "engine": "claude",
                "message": "hello",
                "project_path": str(registered_project),
            },
        )
        response = await ac.post(f"/api/chat/turns/{start.json()['task_id']}/cancel")

    assert response.status_code == 200
    assert response.json()["status"] == "stopped"


@pytest.mark.asyncio
async def test_cancel_chat_turn_missing_returns_404(fake_runner):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        response = await ac.post("/api/chat/turns/does-not-exist/cancel")

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


@pytest.mark.asyncio
async def test_chat_capabilities_distinguish_configured_from_active(
    tmp_path, monkeypatch
):
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "groups": {
                    "web": {
                        "skills": ["base/review"],
                        "hooks": ["base/audit"],
                        "plugins": ["base/browser"],
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(chat_router, "get_config_path", lambda: config_path)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        response = await ac.get(
            "/api/chat/capabilities",
            params={"engine": "codex", "group": "web", "project_path": "/tmp/app"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["mode"] == "legacy_one_shot"
    assert data["codeagent_resources_injected"] is False
    assert data["active"] == {"skills": [], "hooks": [], "plugins": []}
    assert data["configured_but_inactive"] == {
        "skills": ["base/review"],
        "hooks": ["base/audit"],
        "plugins": ["base/browser"],
    }
    assert data["provider_native"]["status"] == "unknown"


@pytest.mark.asyncio
async def test_chat_capabilities_reject_invalid_engine():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        response = await ac.get("/api/chat/capabilities", params={"engine": "shell"})

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_chat_capabilities_tolerate_warnings_and_null_resources(
    tmp_path, monkeypatch
):
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "groups": {
                    "web": {
                        "skills": None,
                        "hooks": ["base/audit"],
                        "plugins": None,
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(chat_router, "get_config_path", lambda: config_path)
    monkeypatch.setattr(
        chat_router.ConfigService,
        "get_config",
        lambda self: (
            json.loads(config_path.read_text(encoding="utf-8")),
            ["deprecated field"],
        ),
    )

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        response = await ac.get(
            "/api/chat/capabilities", params={"engine": "codex", "group": "web"}
        )

    assert response.status_code == 200
    assert response.json()["configured_but_inactive"] == {
        "skills": [],
        "hooks": ["base/audit"],
        "plugins": [],
    }
    assert response.json()["configuration_warnings"] == ["deprecated field"]


@pytest.mark.asyncio
async def test_chat_capabilities_reject_missing_config(monkeypatch):
    monkeypatch.setattr(
        chat_router.ConfigService,
        "get_config",
        lambda self: (None, ["fatal config error"]),
    )

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        response = await ac.get("/api/chat/capabilities", params={"engine": "codex"})

    assert response.status_code == 500
    assert response.json()["detail"] == "fatal config error"

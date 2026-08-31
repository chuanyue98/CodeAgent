"""实例管理聚合路由的测试。"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.services.agent_protocol import SessionStatus
from core.web.routers import instances as instances_router
from core.web.routers import pty as pty_router
from tests._helpers import assert_camel


def _app() -> FastAPI:
    app = FastAPI()
    app.include_router(instances_router.router)
    return app


def _gateway_session(session_id: str, status: SessionStatus) -> SimpleNamespace:
    return SimpleNamespace(
        id=session_id,
        provider="claude",
        cwd="E:/demo/CodeAgent",
        title=f"会话 {session_id}",
        status=status,
        created_at=datetime(2026, 8, 24, 10, 0, 0, tzinfo=UTC),
    )


def _run(task_id: str, status: str = "running") -> SimpleNamespace:
    return SimpleNamespace(
        task_id=task_id,
        engine="gemini",
        pid=1234,
        status=status,
        log_path="",
        start_time=1_800_000_000.0,
        session_id=None,
        workspace="E:/demo/CodeAgent",
    )


@pytest.fixture(autouse=True)
def _clean_pty_registry():
    pty_router._ACTIVE_SESSIONS.clear()
    yield
    pty_router._ACTIVE_SESSIONS.clear()


def test_list_instances_empty_without_gateway():
    with TestClient(_app()) as client:
        body = client.get("/api/instances").json()
    assert body == {"instances": []}


def test_list_instances_aggregates_all_kinds(monkeypatch):
    app = _app()
    app.state.agent_gateway = SimpleNamespace(
        list_sessions=lambda limit: [
            _gateway_session("s1", SessionStatus.BUSY),
            _gateway_session("s2", SessionStatus.CLOSED),  # 已关闭的不算实例
        ]
    )
    pty_router._ACTIVE_SESSIONS["pty1"] = {
        "id": "pty1",
        "engine": "shell",
        "cwd": "E:/demo/CodeAgent",
        "pid": 42,
        "started_at": "2026-08-24T11:00:00+00:00",
        "session": object(),
    }
    # 两个 runner 是同一单例，只需补丁一次。
    monkeypatch.setattr(
        instances_router.tasks_runner, "list_runs", lambda: [_run("t1")]
    )

    with TestClient(app) as client:
        instances = client.get("/api/instances").json()["instances"]

    by_kind = {item["kind"]: item for item in instances}
    assert set(by_kind) == {"chat", "terminal", "task"}
    assert by_kind["chat"]["id"] == "s1"
    assert by_kind["chat"]["stoppable"] is False
    assert by_kind["terminal"]["pid"] == 42
    assert by_kind["terminal"]["stoppable"] is True
    assert by_kind["task"]["id"] == "t1"
    # 内部 PTY 注册表用 snake_case，跨线的实例对象一律 camelCase。
    assert "startedAt" in by_kind["terminal"]
    assert_camel(instances)


def test_stop_terminal_instance(monkeypatch):
    stopped = []

    class _FakeSession:
        async def terminate(self):
            stopped.append("pty1")

        async def shutdown(self):
            stopped.append("pty1")

    pty_router._ACTIVE_SESSIONS["pty1"] = {
        "id": "pty1",
        "engine": "claude",
        "cwd": "E:/demo/CodeAgent",
        "pid": 42,
        "started_at": "2026-08-24T11:00:00+00:00",
        "session": _FakeSession(),
    }
    with TestClient(_app()) as client:
        response = client.post("/api/instances/terminal/pty1/stop")
    assert response.json() == {"success": True}
    assert stopped == ["pty1"]


def test_stop_unknown_terminal_returns_404():
    with TestClient(_app()) as client:
        response = client.post("/api/instances/terminal/nope/stop")
    assert response.status_code == 404


def test_stop_task_delegates_to_shared_runner(monkeypatch):
    # chat._runner 与 tasks._runner 是同一单例，停止只需调一次。
    monkeypatch.setattr(
        instances_router.tasks_runner,
        "stop_task",
        lambda task_id: task_id == "t9",
    )
    with TestClient(_app()) as client:
        assert client.post("/api/instances/task/t9/stop").json() == {"success": True}
        assert client.post("/api/instances/task/unknown/stop").status_code == 404


def test_stop_chat_instance_rejected():
    with TestClient(_app()) as client:
        response = client.post("/api/instances/chat/s1/stop")
    assert response.status_code == 400


def test_stop_unknown_kind_rejected():
    with TestClient(_app()) as client:
        response = client.post("/api/instances/alien/x1/stop")
    assert response.status_code == 404

"""Tests for the /api/schedules endpoints against a real ScheduleService
backed by a temp config.json (CA_CONFIG_PATH), with TaskRunner mocked out —
no real engine CLI or ca_launcher.py is spawned in CI."""

from __future__ import annotations

import os
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient

from core.web.routers import tasks as tasks_router
from core.web.server import app
from core.services.runner_service import TaskAlreadyRunningError


class _FakeRunner:
    def __init__(self):
        self.calls: list[tuple] = []
        self.already_running = False

    def run_task(
        self,
        task_name,
        engine,
        group,
        tasks_root=None,
        workspace=None,
        prevent_overlap=False,
    ):
        if self.already_running:
            raise TaskAlreadyRunningError("Task is already running")
        self.calls.append((task_name, engine, group, workspace))
        return SimpleNamespace(
            task_id=f"{task_name}_1",
            engine=engine,
            pid=1234,
            status="running",
            log_path="/tmp/x.log",
            start_time=0.0,
            session_id=None,
        )


@pytest.fixture
def fake_runner(monkeypatch):
    fake = _FakeRunner()
    monkeypatch.setattr(tasks_router, "_runner", fake)
    return fake


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    monkeypatch.setenv("CA_CONFIG_PATH", str(tmp_path / "config.json"))
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setenv("CA_TEST_WORKSPACE", str(workspace))
    (tmp_path / "config.json").write_text(
        '{"project_registry": [{"path": "%s", "group": "common"}], "groups": {}}'
        % str(workspace).replace("\\", "\\\\"),
        encoding="utf-8",
    )


@pytest.mark.asyncio
async def test_create_and_list_schedule():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        create = await ac.post(
            "/api/schedules",
            json={
                "task_name": "nightly-review",
                "engine": "claude",
                "group": "common",
                "workspace": os.environ["CA_TEST_WORKSPACE"],
                "cron_expr": "0 9 * * *",
            },
        )
        assert create.status_code == 200
        record = create.json()
        assert record["task_name"] == "nightly-review"
        assert record["enabled"] is True
        assert record["group"] == "common"

        listed = await ac.get("/api/schedules")
        assert listed.status_code == 200
        assert [r["id"] for r in listed.json()] == [record["id"]]


@pytest.mark.asyncio
async def test_create_schedule_invalid_cron_returns_400():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        response = await ac.post(
            "/api/schedules",
            json={
                "task_name": "task",
                "engine": "claude",
                "workspace": os.environ["CA_TEST_WORKSPACE"],
                "cron_expr": "not a cron",
            },
        )
    assert response.status_code == 400
    assert "Invalid cron expression" in response.json()["detail"]


@pytest.mark.asyncio
async def test_update_schedule_toggles_enabled():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        create = await ac.post(
            "/api/schedules",
            json={
                "task_name": "task",
                "engine": "claude",
                "workspace": os.environ["CA_TEST_WORKSPACE"],
                "cron_expr": "* * * * *",
            },
        )
        schedule_id = create.json()["id"]

        update = await ac.patch(
            f"/api/schedules/{schedule_id}", json={"enabled": False}
        )
        assert update.status_code == 200
        assert update.json()["enabled"] is False


@pytest.mark.asyncio
async def test_disable_schedule_after_workspace_is_unregistered():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        create = await ac.post(
            "/api/schedules",
            json={
                "task_name": "task",
                "engine": "claude",
                "workspace": os.environ["CA_TEST_WORKSPACE"],
                "cron_expr": "* * * * *",
            },
        )
        schedule_id = create.json()["id"]
        config_path = Path(os.environ["CA_CONFIG_PATH"])
        config = json.loads(config_path.read_text(encoding="utf-8"))
        config["project_registry"] = []
        config_path.write_text(json.dumps(config), encoding="utf-8")

        update = await ac.patch(
            f"/api/schedules/{schedule_id}", json={"enabled": False}
        )

    assert update.status_code == 200
    assert update.json()["enabled"] is False


@pytest.mark.asyncio
async def test_update_missing_schedule_returns_404():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        response = await ac.patch(
            "/api/schedules/does-not-exist", json={"enabled": False}
        )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_backfills_legacy_schedule_workspace():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        create = await ac.post(
            "/api/schedules",
            json={
                "task_name": "task",
                "engine": "claude",
                "workspace": os.environ["CA_TEST_WORKSPACE"],
                "cron_expr": "* * * * *",
            },
        )
        schedule_id = create.json()["id"]

        config_path = os.environ["CA_CONFIG_PATH"]
        config = json.loads(Path(config_path).read_text(encoding="utf-8"))
        config["schedules"][0]["workspace"] = None
        Path(config_path).write_text(json.dumps(config), encoding="utf-8")

        update = await ac.patch(
            f"/api/schedules/{schedule_id}",
            json={"workspace": os.environ["CA_TEST_WORKSPACE"]},
        )

    assert update.status_code == 200
    assert update.json()["workspace"] == os.environ["CA_TEST_WORKSPACE"]
    assert update.json()["group"] == "common"


@pytest.mark.asyncio
async def test_delete_schedule():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        create = await ac.post(
            "/api/schedules",
            json={
                "task_name": "task",
                "engine": "claude",
                "workspace": os.environ["CA_TEST_WORKSPACE"],
                "cron_expr": "* * * * *",
            },
        )
        schedule_id = create.json()["id"]

        delete = await ac.delete(f"/api/schedules/{schedule_id}")
        assert delete.status_code == 200

        listed = await ac.get("/api/schedules")
        assert listed.json() == []


@pytest.mark.asyncio
async def test_delete_missing_schedule_returns_404():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        response = await ac.delete("/api/schedules/does-not-exist")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_run_now_invokes_runner_and_records_status(fake_runner):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        create = await ac.post(
            "/api/schedules",
            json={
                "task_name": "nightly-review",
                "engine": "claude",
                "group": "work",
                "workspace": os.environ["CA_TEST_WORKSPACE"],
                "cron_expr": "* * * * *",
            },
        )
        schedule_id = create.json()["id"]

        response = await ac.post(f"/api/schedules/{schedule_id}/run-now")

    assert response.status_code == 200
    assert fake_runner.calls == [
        ("nightly-review", "claude", "common", os.environ["CA_TEST_WORKSPACE"])
    ]


@pytest.mark.asyncio
async def test_run_now_missing_schedule_returns_404(fake_runner):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        response = await ac.post("/api/schedules/does-not-exist/run-now")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_run_now_returns_conflict_for_atomic_overlap(fake_runner):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        create = await ac.post(
            "/api/schedules",
            json={
                "task_name": "task",
                "engine": "claude",
                "workspace": os.environ["CA_TEST_WORKSPACE"],
                "cron_expr": "* * * * *",
            },
        )
        fake_runner.already_running = True
        response = await ac.post(f"/api/schedules/{create.json()['id']}/run-now")

    assert response.status_code == 409
    assert response.json()["detail"] == "Task is already running"

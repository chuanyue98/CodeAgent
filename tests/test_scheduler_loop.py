from __future__ import annotations

import time

import pytest

from core.services.config_service import ConfigService
from core.services.schedule_service import ScheduleService
from core.services.scheduler_loop import tick_once
from core.services.runner_service import TaskAlreadyRunningError


class _FakeTaskRunner:
    def __init__(self, raise_error: bool = False, already_running: bool = False):
        self.calls: list[tuple] = []
        self._raise_error = raise_error
        self._already_running = already_running

    def run_task(
        self,
        task_name,
        engine,
        group,
        tasks_root=None,
        workspace=None,
        prevent_overlap=False,
    ):
        self.calls.append((task_name, engine, group, workspace))
        if self._already_running:
            raise TaskAlreadyRunningError("Task is already running")
        if self._raise_error:
            raise ValueError("boom")
        return type("Status", (), {"status": "running"})()


@pytest.fixture
def tasks_root(tmp_path):
    root = tmp_path / "tasks"
    root.mkdir()
    (root / "nightly-review.md").write_text("# Nightly Review\n", encoding="utf-8")
    return root


@pytest.fixture
def schedule_service(tmp_path, tasks_root):
    config_service = ConfigService(tmp_path / "config.json")
    config_service.update_config(
        {"project_registry": [{"path": str(tasks_root), "group": "common"}]}
    )
    return ScheduleService(config_service)


@pytest.mark.asyncio
async def test_tick_fires_due_schedule(schedule_service, tasks_root):
    record = schedule_service.create_schedule(
        "nightly-review", "claude", "common", "* * * * *", workspace=str(tasks_root)
    )
    # Manually backdate next_run_at to make it due, regardless of the cron
    # expression's real next fire time.
    config, _ = schedule_service.config_service.get_config()
    config["schedules"][0]["next_run_at"] = time.time() - 1
    schedule_service.config_service.update_config(config)

    runner = _FakeTaskRunner()
    await tick_once(schedule_service, runner, lambda: tasks_root)

    assert runner.calls == [("nightly-review", "claude", "common", str(tasks_root))]
    updated = schedule_service.get_schedule(record["id"])
    assert updated["last_run_status"] == "started"
    assert updated["last_run_at"] is not None
    assert updated["next_run_at"] > time.time()


@pytest.mark.asyncio
async def test_tick_skips_disabled_schedule(schedule_service, tasks_root):
    record = schedule_service.create_schedule(
        "nightly-review",
        "claude",
        "common",
        "* * * * *",
        enabled=False,
        workspace=str(tasks_root),
    )
    config, _ = schedule_service.config_service.get_config()
    config["schedules"][0]["next_run_at"] = time.time() - 1
    schedule_service.config_service.update_config(config)

    runner = _FakeTaskRunner()
    await tick_once(schedule_service, runner, lambda: tasks_root)

    assert runner.calls == []
    assert schedule_service.get_schedule(record["id"])["last_run_status"] is None


@pytest.mark.asyncio
async def test_tick_skips_not_yet_due_schedule(schedule_service, tasks_root):
    record = schedule_service.create_schedule(
        "nightly-review", "claude", "common", "0 0 1 1 *", workspace=str(tasks_root)
    )  # once a year — not due now

    runner = _FakeTaskRunner()
    await tick_once(schedule_service, runner, lambda: tasks_root)

    assert runner.calls == []
    assert schedule_service.get_schedule(record["id"])["last_run_status"] is None


@pytest.mark.asyncio
async def test_tick_marks_missing_task_without_crashing(schedule_service, tasks_root):
    record = schedule_service.create_schedule(
        "does-not-exist", "claude", "common", "* * * * *", workspace=str(tasks_root)
    )
    config, _ = schedule_service.config_service.get_config()
    config["schedules"][0]["next_run_at"] = time.time() - 1
    schedule_service.config_service.update_config(config)

    runner = _FakeTaskRunner()
    await tick_once(schedule_service, runner, lambda: tasks_root)

    assert runner.calls == []
    assert (
        schedule_service.get_schedule(record["id"])["last_run_status"]
        == "task_not_found"
    )


@pytest.mark.asyncio
async def test_tick_records_failure_without_crashing(schedule_service, tasks_root):
    record = schedule_service.create_schedule(
        "nightly-review", "claude", "common", "* * * * *", workspace=str(tasks_root)
    )
    config, _ = schedule_service.config_service.get_config()
    config["schedules"][0]["next_run_at"] = time.time() - 1
    schedule_service.config_service.update_config(config)

    runner = _FakeTaskRunner(raise_error=True)
    await tick_once(schedule_service, runner, lambda: tasks_root)

    assert runner.calls == [("nightly-review", "claude", "common", str(tasks_root))]
    status = schedule_service.get_schedule(record["id"])["last_run_status"]
    assert status.startswith("failed:")


@pytest.mark.asyncio
async def test_tick_rejects_workspace_removed_from_registry(
    schedule_service, tasks_root
):
    record = schedule_service.create_schedule(
        "nightly-review", "claude", "common", "* * * * *", workspace=str(tasks_root)
    )
    config, _ = schedule_service.config_service.get_config()
    config["project_registry"] = []
    config["schedules"][0]["next_run_at"] = time.time() - 1
    schedule_service.config_service.update_config(config)

    runner = _FakeTaskRunner()
    await tick_once(schedule_service, runner, lambda: tasks_root)

    assert runner.calls == []
    assert (
        schedule_service.get_schedule(record["id"])["last_run_status"]
        == "workspace_unregistered"
    )


@pytest.mark.asyncio
async def test_tick_records_atomic_overlap_skip(schedule_service, tasks_root):
    record = schedule_service.create_schedule(
        "nightly-review", "claude", "common", "* * * * *", workspace=str(tasks_root)
    )
    config, _ = schedule_service.config_service.get_config()
    config["schedules"][0]["next_run_at"] = time.time() - 1
    schedule_service.config_service.update_config(config)

    runner = _FakeTaskRunner(already_running=True)
    await tick_once(schedule_service, runner, lambda: tasks_root)

    assert (
        schedule_service.get_schedule(record["id"])["last_run_status"]
        == "skipped: already_running"
    )

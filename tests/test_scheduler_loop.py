from __future__ import annotations

import time

import pytest

from core.services.config_service import ConfigService
from core.services.runner_service import TaskAlreadyRunningError
from core.services.schedule_service import ScheduleService
from core.services.scheduler_loop import tick_once


class _FakeTaskRunner:
    def __init__(
        self,
        raise_error: bool = False,
        already_running: bool = False,
        finished_runs: dict[str, str] | None = None,
    ):
        self.calls: list[tuple] = []
        self.schedule_ids: list[str | None] = []
        self._raise_error = raise_error
        self._already_running = already_running
        #: run id -> terminal status, for the settle pass to find.
        self._finished_runs = finished_runs or {}
        self._next_run_id = "run-1"

    def run_task(
        self,
        task_name,
        engine,
        group,
        tasks_root=None,
        workspace=None,
        prevent_overlap=False,
        schedule_id=None,
    ):
        self.calls.append((task_name, engine, group, workspace))
        self.schedule_ids.append(schedule_id)
        if self._already_running:
            raise TaskAlreadyRunningError("Task is already running")
        if self._raise_error:
            raise ValueError("boom")
        return type("Status", (), {"status": "running", "task_id": self._next_run_id})()

    def get_run(self, task_id):
        status = self._finished_runs.get(task_id)
        if status is None:
            return None
        return type("Status", (), {"status": status, "task_id": task_id})()


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
async def test_tick_notifies_webhook_on_schedule_failure(schedule_service, tasks_root):
    config, _ = schedule_service.config_service.get_config()
    config["notifications"] = {"webhooks": ["https://example.com/hook"]}
    schedule_service.config_service.update_config(config)

    record = schedule_service.create_schedule(
        "does-not-exist", "claude", "common", "* * * * *", workspace=str(tasks_root)
    )
    config, _ = schedule_service.config_service.get_config()
    config["schedules"][0]["next_run_at"] = time.time() - 1
    schedule_service.config_service.update_config(config)

    notify_calls = []
    import core.services.scheduler_loop as scheduler_loop_module

    original_notify = scheduler_loop_module.notify
    scheduler_loop_module.notify = lambda cfg, event, payload: notify_calls.append(
        (event, payload)
    )
    try:
        runner = _FakeTaskRunner()
        await tick_once(schedule_service, runner, lambda: tasks_root)
    finally:
        scheduler_loop_module.notify = original_notify

    assert notify_calls == [
        (
            "schedule.failed",
            {
                "schedule_id": record["id"],
                "task_name": "does-not-exist",
                "engine": "claude",
                "workspace": str(tasks_root),
                "status": "task_not_found",
            },
        )
    ]


@pytest.mark.asyncio
async def test_tick_does_not_notify_on_overlap_skip(schedule_service, tasks_root):
    config, _ = schedule_service.config_service.get_config()
    config["notifications"] = {"webhooks": ["https://example.com/hook"]}
    schedule_service.config_service.update_config(config)

    schedule_service.create_schedule(
        "nightly-review", "claude", "common", "* * * * *", workspace=str(tasks_root)
    )
    config, _ = schedule_service.config_service.get_config()
    config["schedules"][0]["next_run_at"] = time.time() - 1
    schedule_service.config_service.update_config(config)

    import core.services.scheduler_loop as scheduler_loop_module

    notify_calls = []
    original_notify = scheduler_loop_module.notify
    scheduler_loop_module.notify = lambda cfg, event, payload: notify_calls.append(
        (event, payload)
    )
    try:
        runner = _FakeTaskRunner(already_running=True)
        await tick_once(schedule_service, runner, lambda: tasks_root)
    finally:
        scheduler_loop_module.notify = original_notify

    assert notify_calls == []


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


# ─── Settling a fired run's real outcome ──────────────────────────────────
#
# A schedule used to stop at "started": the run's real outcome was never
# written back, so `last_run_status` said "started" forever and the failure
# webhook never fired for a task that failed after launching.


def _make_due_schedule(schedule_service, tasks_root, task_name="nightly-review"):
    record = schedule_service.create_schedule(
        task_name, "claude", "common", "* * * * *", workspace=str(tasks_root)
    )
    config, _ = schedule_service.config_service.get_config()
    config["schedules"][0]["next_run_at"] = time.time() - 1
    schedule_service.config_service.update_config(config)
    return record


@pytest.mark.asyncio
async def test_tick_passes_schedule_id_to_the_run(schedule_service, tasks_root):
    record = _make_due_schedule(schedule_service, tasks_root)

    runner = _FakeTaskRunner()
    await tick_once(schedule_service, runner, lambda: tasks_root)

    assert runner.schedule_ids == [record["id"]]
    saved = schedule_service.get_schedule(record["id"])
    assert saved["last_run_id"] == "run-1"
    assert saved["last_run_status"] == "started"


@pytest.mark.asyncio
async def test_next_tick_replaces_started_with_the_real_outcome(
    schedule_service, tasks_root
):
    record = _make_due_schedule(schedule_service, tasks_root)

    runner = _FakeTaskRunner()
    await tick_once(schedule_service, runner, lambda: tasks_root)
    fired = schedule_service.get_schedule(record["id"])
    assert fired["last_run_status"] == "started"

    # The run has since finished. Nothing is due now, so this tick only settles.
    runner._finished_runs = {"run-1": "failed"}
    await tick_once(schedule_service, runner, lambda: tasks_root)

    settled = schedule_service.get_schedule(record["id"])
    assert settled["last_run_status"] == "failed"
    # Settling is not a new fire: neither the schedule nor the run's start
    # time moves.
    assert settled["next_run_at"] == fired["next_run_at"]
    assert settled["last_run_at"] == fired["last_run_at"]


@pytest.mark.asyncio
async def test_a_still_running_run_is_left_alone(schedule_service, tasks_root):
    record = _make_due_schedule(schedule_service, tasks_root)

    runner = _FakeTaskRunner()
    await tick_once(schedule_service, runner, lambda: tasks_root)

    runner._finished_runs = {"run-1": "running"}
    await tick_once(schedule_service, runner, lambda: tasks_root)

    assert schedule_service.get_schedule(record["id"])["last_run_status"] == "started"


@pytest.mark.asyncio
async def test_settling_a_failure_notifies_the_webhook(schedule_service, tasks_root):
    config, _ = schedule_service.config_service.get_config()
    config["notifications"] = {"webhooks": ["https://example.com/hook"]}
    schedule_service.config_service.update_config(config)

    record = _make_due_schedule(schedule_service, tasks_root)

    import core.services.scheduler_loop as scheduler_loop_module

    notify_calls = []
    original_notify = scheduler_loop_module.notify
    scheduler_loop_module.notify = lambda cfg, event, payload: notify_calls.append(
        (event, payload)
    )
    try:
        runner = _FakeTaskRunner()
        await tick_once(schedule_service, runner, lambda: tasks_root)
        assert notify_calls == [], "launching successfully is not a failure"

        runner._finished_runs = {"run-1": "failed"}
        await tick_once(schedule_service, runner, lambda: tasks_root)
    finally:
        scheduler_loop_module.notify = original_notify

    assert len(notify_calls) == 1
    event, payload = notify_calls[0]
    assert event == "schedule.failed"
    assert payload["schedule_id"] == record["id"]
    assert payload["status"] == "failed"


@pytest.mark.asyncio
async def test_a_stopped_run_does_not_notify(schedule_service, tasks_root):
    """Somebody stopped it by hand; that is not a schedule failure."""
    config, _ = schedule_service.config_service.get_config()
    config["notifications"] = {"webhooks": ["https://example.com/hook"]}
    schedule_service.config_service.update_config(config)

    record = _make_due_schedule(schedule_service, tasks_root)

    import core.services.scheduler_loop as scheduler_loop_module

    notify_calls = []
    original_notify = scheduler_loop_module.notify
    scheduler_loop_module.notify = lambda cfg, event, payload: notify_calls.append(
        (event, payload)
    )
    try:
        runner = _FakeTaskRunner()
        await tick_once(schedule_service, runner, lambda: tasks_root)
        runner._finished_runs = {"run-1": "stopped"}
        await tick_once(schedule_service, runner, lambda: tasks_root)
    finally:
        scheduler_loop_module.notify = original_notify

    assert notify_calls == []
    assert schedule_service.get_schedule(record["id"])["last_run_status"] == "stopped"

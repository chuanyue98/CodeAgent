import json
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.services.runner_service import (
    TaskAlreadyRunningError,
    TaskRunner,
    TaskRunStatus,
)
from core.task_lib import get_tasks_dir


def test_task_runner_passes_task_mode_group_and_tasks_root(tmp_path):
    launcher = tmp_path / "ca_launcher.py"
    launcher.write_text(
        "import json, os, sys\n"
        "print(json.dumps({"
        "'argv': sys.argv[1:], "
        "'group': os.environ.get('CA_PROJECT_GROUP'), "
        "'tasks_root': os.environ.get('CA_TASKS_ROOT')"
        "}))\n",
        encoding="utf-8",
    )
    tasks_root = tmp_path / "resources" / "tasks"
    tasks_root.mkdir(parents=True)

    runner = TaskRunner(tmp_path)
    run = runner.run_task("review", "codex", "work", tasks_root=tasks_root)

    deadline = time.time() + 5
    while time.time() < deadline:
        status = runner.get_status(run.task_id)
        if status and status.status != "running":
            break
        time.sleep(0.01)

    assert status is not None
    assert status.status == "completed"
    payload = json.loads(Path(status.log_path).read_text(encoding="utf-8"))
    assert payload["argv"] == ["codex", "-t", "review", "-y"]
    assert payload["group"] == "work"
    assert payload["tasks_root"] == str(tasks_root.resolve())


def test_task_runner_rejects_unknown_engine(tmp_path):
    runner = TaskRunner(tmp_path)
    with pytest.raises(ValueError, match="Invalid engine"):
        runner.run_task("review", "shell", "common")


def test_task_library_uses_explicit_tasks_root(tmp_path, monkeypatch):
    tasks_root = tmp_path / "external-tasks"
    tasks_root.mkdir()
    monkeypatch.setenv("CA_TASKS_ROOT", str(tasks_root))

    assert get_tasks_dir() == tasks_root.resolve()


def test_failed_task_start_is_still_queryable(tmp_path):
    runner = TaskRunner(tmp_path)
    with patch(
        "core.services.runner_service.subprocess.Popen",
        side_effect=OSError("cannot start"),
    ):
        run = runner.run_task("review", "codex", "common")

    assert run.status == "failed: cannot start"
    assert runner.get_status(run.task_id) is run


def test_task_runner_kill_all(tmp_path):
    from core.services.runner_service import TaskRunner
    import time

    runner = TaskRunner(tmp_path)
    # Start a dummy long-running command (like sleep 10)
    import subprocess

    dummy_proc = subprocess.Popen(["sleep", "10"])
    runner.active_runs["dummy"] = MagicMock(pid=dummy_proc.pid, status="running")
    runner._processes["dummy"] = dummy_proc

    runner.kill_all()
    time.sleep(0.1)
    assert dummy_proc.poll() is not None  # Process terminated


def test_task_runner_kill_all_missing_from_active_runs(tmp_path):
    from core.services.runner_service import TaskRunner
    import time

    runner = TaskRunner(tmp_path)
    # Start a dummy long-running command
    import subprocess

    dummy_proc = subprocess.Popen(["sleep", "10"])
    # Do NOT put it in active_runs
    runner._processes["dummy"] = dummy_proc

    # This should not raise KeyError and should terminate the process
    runner.kill_all()
    time.sleep(0.1)
    assert dummy_proc.poll() is not None


def test_overlap_guard_refreshes_completed_process_status(tmp_path):
    (tmp_path / "ca_launcher.py").write_text("pass\n", encoding="utf-8")
    runner = TaskRunner(tmp_path)
    run = runner.run_task(
        "review",
        "codex",
        "common",
        workspace=str(tmp_path),
        prevent_overlap=True,
    )
    runner._processes[run.task_id].wait(timeout=5)

    assert runner.has_active_task("review", workspace=str(tmp_path)) is False
    assert runner.get_status(run.task_id).status == "completed"


def test_overlap_guard_is_atomic_and_scoped_to_workspace(tmp_path):
    (tmp_path / "ca_launcher.py").write_text(
        "import time\ntime.sleep(10)\n", encoding="utf-8"
    )
    other_workspace = tmp_path / "other"
    other_workspace.mkdir()
    runner = TaskRunner(tmp_path)
    runner.run_task(
        "review",
        "codex",
        "common",
        workspace=str(tmp_path),
        prevent_overlap=True,
    )

    with pytest.raises(TaskAlreadyRunningError):
        runner.run_task(
            "review",
            "codex",
            "common",
            workspace=str(tmp_path),
            prevent_overlap=True,
        )

    second = runner.run_task(
        "review",
        "codex",
        "common",
        workspace=str(other_workspace),
        prevent_overlap=True,
    )
    assert second.status == "running"
    runner.kill_all()


def _assert_runner_lock_is_available_from_another_thread(runner):
    acquired: list[bool] = []

    def acquire_lock():
        locked = runner._run_lock.acquire(timeout=0.5)
        acquired.append(locked)
        if locked:
            runner._run_lock.release()

    thread = threading.Thread(target=acquire_lock)
    thread.start()
    thread.join(timeout=1)
    assert acquired == [True]


def test_stop_task_waits_without_holding_runner_lock(tmp_path):
    runner = TaskRunner(tmp_path)
    process = MagicMock()
    process.wait.side_effect = lambda timeout: (
        _assert_runner_lock_is_available_from_another_thread(runner)
    )
    run = TaskRunStatus(
        task_id="review_1",
        engine="codex",
        pid=123,
        status="running",
        log_path=str(tmp_path / "review.log"),
        start_time=0,
        workspace=str(tmp_path),
    )
    runner.active_runs[run.task_id] = run
    runner._processes[run.task_id] = process

    with (
        patch("core.services.runner_service.os.getpgid", return_value=123),
        patch("core.services.runner_service.os.killpg"),
    ):
        assert runner.stop_task(run.task_id) is True

    assert run.status == "stopped"
    assert run.task_id not in runner._processes


def test_kill_all_waits_without_holding_runner_lock(tmp_path):
    runner = TaskRunner(tmp_path)
    process = MagicMock()
    process.wait.side_effect = lambda timeout=0: (
        _assert_runner_lock_is_available_from_another_thread(runner)
    )
    run = TaskRunStatus(
        task_id="review_1",
        engine="codex",
        pid=123,
        status="running",
        log_path=str(tmp_path / "review.log"),
        start_time=0,
        workspace=str(tmp_path),
    )
    runner.active_runs[run.task_id] = run
    runner._processes[run.task_id] = process

    runner.kill_all()

    assert run.status == "stopped"
    assert runner._processes == {}

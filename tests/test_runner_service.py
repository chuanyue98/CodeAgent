import contextlib
import json
import os
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


@pytest.fixture
def new_runner():
    """Builds TaskRunners and closes the run DB each one opened.

    Every TaskRunner opens a sqlite connection; without closing them the suite
    fills with ResourceWarnings, and the retention tests -- which open a second
    runner over the same directory to sweep it -- leak two apiece.
    """
    created: list[TaskRunner] = []

    def make(root):
        runner = TaskRunner(root)
        created.append(runner)
        return runner

    yield make
    for runner in created:
        runner.close()


def test_task_runner_passes_task_mode_group_and_tasks_root(tmp_path, new_runner):
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

    runner = new_runner(tmp_path)
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
    assert payload["argv"] == ["codex", "-t", "review", "-y", "--non-interactive"]
    assert payload["group"] == "work"
    assert payload["tasks_root"] == str(tasks_root.resolve())


def test_task_runner_rejects_unknown_engine(tmp_path, new_runner):
    runner = new_runner(tmp_path)
    with pytest.raises(ValueError, match="Invalid engine"):
        runner.run_task("review", "shell", "common")


def test_task_runner_rejects_headless_missing_engine(tmp_path, new_runner):
    """后台任务在无 TTY 下运行，freebuff 免费 CLI 没有 headless 通道——
    必须在派生前就拒绝，而不是把交互 TUI 拉进后台挂起。"""
    runner = new_runner(tmp_path)
    with pytest.raises(ValueError, match="no headless channel"):
        runner.run_task("review", "freebuff", "common")
    with pytest.raises(ValueError, match="no headless channel"):
        runner.run_chat_turn("freebuff", "hi", project_path=str(tmp_path))


def test_task_library_uses_explicit_tasks_root(tmp_path, monkeypatch):
    tasks_root = tmp_path / "external-tasks"
    tasks_root.mkdir()
    monkeypatch.setenv("CA_TASKS_ROOT", str(tasks_root))

    assert get_tasks_dir() == tasks_root.resolve()


def test_failed_task_start_is_still_queryable(tmp_path, new_runner):
    runner = new_runner(tmp_path)
    with patch(
        "core.services.runner_service.subprocess.Popen",
        side_effect=OSError("cannot start"),
    ):
        run = runner.run_task("review", "codex", "common")

    assert run.status == "failed: cannot start"
    assert runner.get_status(run.task_id) is run


def test_task_runner_kill_all(tmp_path, new_runner):
    import subprocess
    import sys
    import time

    runner = new_runner(tmp_path)
    # Use a cross-platform sleep via Python instead of the POSIX-only `sleep` binary.
    dummy_proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(10)"])
    runner.active_runs["dummy"] = MagicMock(pid=dummy_proc.pid, status="running")
    runner._processes["dummy"] = dummy_proc

    runner.kill_all()
    time.sleep(0.1)
    assert dummy_proc.poll() is not None  # Process terminated


def test_task_runner_kill_all_missing_from_active_runs(tmp_path, new_runner):
    import subprocess
    import sys
    import time

    runner = new_runner(tmp_path)
    dummy_proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(10)"])
    # Do NOT put it in active_runs
    runner._processes["dummy"] = dummy_proc

    # This should not raise KeyError and should terminate the process
    runner.kill_all()
    time.sleep(0.1)
    assert dummy_proc.poll() is not None


def test_overlap_guard_refreshes_completed_process_status(tmp_path, new_runner):
    (tmp_path / "ca_launcher.py").write_text("pass\n", encoding="utf-8")
    runner = new_runner(tmp_path)
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


def test_get_status_records_end_time_and_exit_code_on_completion(tmp_path, new_runner):
    (tmp_path / "ca_launcher.py").write_text("pass\n", encoding="utf-8")
    runner = new_runner(tmp_path)
    run = runner.run_task("review", "codex", "common")

    deadline = time.time() + 5
    status = None
    while time.time() < deadline:
        status = runner.get_status(run.task_id)
        if status and status.status != "running":
            break
        time.sleep(0.01)

    assert status is not None
    assert status.status == "completed"
    assert status.exit_code == 0
    assert status.end_time is not None
    assert status.end_time >= status.start_time


def test_overlap_guard_is_atomic_and_scoped_to_workspace(tmp_path, new_runner):
    (tmp_path / "ca_launcher.py").write_text(
        "import time\ntime.sleep(10)\n", encoding="utf-8"
    )
    other_workspace = tmp_path / "other"
    other_workspace.mkdir()
    runner = new_runner(tmp_path)
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


def test_stop_task_waits_without_holding_runner_lock(tmp_path, new_runner):
    runner = new_runner(tmp_path)
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

    # getpgid/killpg (the POSIX kill path) don't exist as os-module attributes
    # on Windows, and patch() refuses to patch an attribute that isn't there;
    # subprocess.run (the Windows taskkill path) is mocked on every platform
    # so this never sends a real kill signal to whatever PID 123 happens to
    # be on the machine running the test.
    with contextlib.ExitStack() as patches:
        patches.enter_context(patch("core.services.runner_service.subprocess.run"))
        if hasattr(os, "getpgid"):
            patches.enter_context(
                patch("core.services.runner_service.os.getpgid", return_value=123)
            )
        if hasattr(os, "killpg"):
            patches.enter_context(patch("core.services.runner_service.os.killpg"))
        assert runner.stop_task(run.task_id) is True

    assert run.status == "stopped"
    assert run.task_id not in runner._processes


def test_kill_all_waits_without_holding_runner_lock(tmp_path, new_runner):
    runner = new_runner(tmp_path)
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


def _seed_run(runner: TaskRunner, task_id: str, *, age_days: float, status="completed"):
    """Writes a finished run plus its log file, both aged *age_days* into the past."""
    from core.services.run_store import TaskRunRecord

    when = time.time() - age_days * 86400
    log_file = runner.log_dir / f"{task_id}.log"
    log_file.write_text("output\n", encoding="utf-8")
    os.utime(log_file, (when, when))
    runner._run_store.upsert(
        TaskRunRecord(
            task_id=task_id,
            engine="claude",
            pid=None,
            status=status,
            log_path=str(log_file),
            start_time=when,
            end_time=when,
        )
    )
    return log_file


@pytest.fixture
def age_only(monkeypatch):
    """Drops the keep-the-newest-N floor so age alone decides what is pruned.

    The real floor (RUN_RETENTION_KEEP) would protect every row in a test that
    seeds a handful, which would let these pass without exercising the cutoff.
    """
    monkeypatch.setattr("core.services.runner_service.RUN_RETENTION_KEEP", 0)


def test_startup_prunes_runs_past_the_retention_window(tmp_path, new_runner, age_only):
    runner = new_runner(tmp_path)
    old_log = _seed_run(runner, "ancient", age_days=90)
    fresh_log = _seed_run(runner, "yesterday", age_days=1)

    reopened = new_runner(tmp_path)
    reopened.prune_old_runs()

    assert reopened._run_store.get("ancient") is None
    assert reopened._run_store.get("yesterday") is not None
    assert not old_log.exists()
    assert fresh_log.exists()


def test_startup_leaves_a_still_running_row_alone(tmp_path, new_runner, age_only):
    runner = new_runner(tmp_path)
    log = _seed_run(runner, "ancient", age_days=90, status="running")

    reopened = new_runner(tmp_path)
    reopened.prune_old_runs()

    assert reopened._run_store.get("ancient") is not None
    assert log.exists()


def test_startup_sweeps_log_files_no_row_points_at(tmp_path, new_runner, age_only):
    runner = new_runner(tmp_path)
    orphan = runner.log_dir / "orphan.jsonl"
    orphan.write_text("{}\n", encoding="utf-8")
    when = time.time() - 90 * 86400
    os.utime(orphan, (when, when))

    new_runner(tmp_path).prune_old_runs()

    assert not orphan.exists()


def test_a_recent_orphan_log_is_left_in_place(tmp_path, new_runner, age_only):
    runner = new_runner(tmp_path)
    orphan = runner.log_dir / "orphan.jsonl"
    orphan.write_text("{}\n", encoding="utf-8")

    new_runner(tmp_path).prune_old_runs()

    assert orphan.exists()


def test_retention_can_be_disabled_by_env(tmp_path, new_runner, monkeypatch, age_only):
    runner = new_runner(tmp_path)
    log = _seed_run(runner, "ancient", age_days=90)

    monkeypatch.setenv("CA_RUN_RETENTION_DAYS", "0")
    reopened = new_runner(tmp_path)
    reopened.prune_old_runs()

    assert reopened._run_store.get("ancient") is not None
    assert log.exists()


def test_retention_window_can_be_widened_by_env(
    tmp_path, new_runner, monkeypatch, age_only
):
    runner = new_runner(tmp_path)
    _seed_run(runner, "seven-weeks-ago", age_days=49)

    monkeypatch.setenv("CA_RUN_RETENTION_DAYS", "365")
    reopened = new_runner(tmp_path)
    reopened.prune_old_runs()

    assert reopened._run_store.get("seven-weeks-ago") is not None


def test_unparsable_retention_env_falls_back_to_the_default(
    tmp_path, new_runner, monkeypatch, age_only
):
    runner = new_runner(tmp_path)
    _seed_run(runner, "ancient", age_days=90)

    monkeypatch.setenv("CA_RUN_RETENTION_DAYS", "soon")
    reopened = new_runner(tmp_path)
    reopened.prune_old_runs()

    assert reopened._run_store.get("ancient") is None


def test_the_newest_runs_survive_the_window(tmp_path, new_runner, monkeypatch):
    monkeypatch.setattr("core.services.runner_service.RUN_RETENTION_KEEP", 2)
    runner = new_runner(tmp_path)
    for index in range(4):
        _seed_run(runner, f"run-{index}", age_days=90 - index)

    reopened = new_runner(tmp_path)
    reopened.prune_old_runs()

    surviving = {r.task_id for r in reopened._run_store.list_history()}
    assert surviving == {"run-2", "run-3"}

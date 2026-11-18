import time
from pathlib import Path
from unittest.mock import Mock

import psutil

from core.services import runner_service
from core.services.runner_service import TaskRunner, TaskRunStatus
from core.utils.process_tree import process_created_at, terminate_process_tree


def test_stop_failure_keeps_running_record_and_allows_retry(tmp_path, monkeypatch):
    runner = TaskRunner(tmp_path)
    run = TaskRunStatus(
        "test", "codex", 123, "running", "test.log", 0, process_created_at=1
    )
    runner.active_runs["test"] = run
    process = Mock()
    runner._processes["test"] = process
    terminate = Mock(return_value=False)
    monkeypatch.setattr(runner_service, "terminate_process_tree", terminate)
    try:
        assert not runner.stop_task("test")
        assert run.status == "running"
        assert runner._processes["test"] is process
        assert not runner._stopping_tasks
        terminate.return_value = True
        assert runner.stop_task("test")
        assert run.status == "stopped"
        assert runner._run_store.get("test").status == "stopped"
    finally:
        runner.close()


def test_wrong_process_identity_is_never_killed():
    import os

    pid = os.getpid()
    assert not terminate_process_tree(pid, process_created_at(pid) - 1)
    assert not terminate_process_tree(pid, None)
    assert psutil.pid_exists(pid)


def test_stop_terminates_launcher_and_child(tmp_path):
    (tmp_path / "ca_launcher.py").write_text(
        "import subprocess, sys, time\n"
        "p = subprocess.Popen([sys.executable, '-c', "
        "'import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(120)'])\n"
        "print(p.pid, flush=True)\ntime.sleep(120)\n",
        encoding="utf-8",
    )
    runner = TaskRunner(tmp_path)
    child = None
    try:
        run = runner.run_task("test", "codex", "common")
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            text = Path(run.log_path).read_text(encoding="utf-8").strip()
            if text:
                child = psutil.Process(int(text))
                break
            time.sleep(0.02)
        assert child is not None
        assert runner.stop_task(run.task_id)
        assert run.status == "stopped"
        assert not child.is_running() or child.status() == psutil.STATUS_ZOMBIE
    finally:
        runner.kill_all()
        if child is not None and child.is_running():
            try:
                child.kill()
            except psutil.NoSuchProcess:
                pass
        runner.close()

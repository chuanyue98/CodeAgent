import json
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from core.services.runner_service import TaskRunner
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

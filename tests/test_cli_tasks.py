"""``ca ps`` / ``ca stop`` / ``ca batch-run`` / ``ca new`` 的 CLI 测试。"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import ca_launcher
from core.services.runner_service import TaskRunStatus


def _run(monkeypatch, *argv):
    monkeypatch.setattr("sys.argv", ["ca_launcher.py", *argv])
    return ca_launcher.main()


def _run_status(task_id, status, start_time=0, pid=123, workspace="/ws"):
    return TaskRunStatus(
        task_id=task_id,
        engine="codex",
        pid=pid,
        status=status,
        log_path=f"/tmp/{task_id}.log",
        start_time=start_time,
        workspace=workspace,
    )


class FakeRunner:
    def __init__(self, runs=None):
        self.runs = list(runs or [])
        self.stopped = []
        self.started = []

    def list_runs(self):
        return list(self.runs)

    def get_status(self, task_id):
        for run in self.runs:
            if run.task_id == task_id:
                return run
        return None

    def stop_task(self, task_id):
        self.stopped.append(task_id)
        return True

    def run_task(self, name, engine, group, **kwargs):
        self.started.append((name, engine, group, kwargs))
        return _run_status(f"{name}_{len(self.started)}", "running")


@pytest.fixture
def runner():
    fake = FakeRunner()
    with patch("core.cli.helpers._get_task_runner", return_value=fake):
        yield fake


# ── ca ps ────────────────────────────────────────────────────────────────────


def test_ps_without_runs_says_nothing_is_running(monkeypatch, capsys, runner):
    assert _run(monkeypatch, "ps") is None
    assert "No running tasks." in capsys.readouterr().out


def test_ps_all_without_runs_reports_no_tracked_runs(monkeypatch, capsys, runner):
    _run(monkeypatch, "ps", "--all")
    assert "No tracked task runs." in capsys.readouterr().out


def test_ps_lists_only_running_runs_with_a_hint(monkeypatch, capsys, runner):
    runner.runs = [
        _run_status("review_2", "completed", start_time=20),
        _run_status("review_1", "running", start_time=10, workspace="/work/a"),
    ]
    _run(monkeypatch, "ps")
    out = capsys.readouterr().out
    assert "review_1" in out
    assert "review_2" not in out
    assert "/work/a" in out
    assert "ca ps --all" in out


def test_ps_all_sorts_every_run_newest_first(monkeypatch, capsys, runner):
    runner.runs = [
        _run_status("older_1", "failed", start_time=10),
        _run_status("newest_1", "running", start_time=30),
        _run_status("middle_1", "completed", start_time=20),
    ]
    _run(monkeypatch, "ps", "--all")
    out = capsys.readouterr().out
    assert out.index("newest_1") < out.index("middle_1") < out.index("older_1")
    assert "ca ps --all" not in out


# ── ca stop ──────────────────────────────────────────────────────────────────


def test_stop_unknown_task_exits_with_a_listing_hint(monkeypatch, capsys, runner):
    with pytest.raises(SystemExit) as excinfo:
        _run(monkeypatch, "stop", "ghost_1")
    assert excinfo.value.code == 1
    out = capsys.readouterr().out
    assert "[X] No such task run: ghost_1" in out
    assert "ca ps --all" in out


def test_stop_finished_run_is_a_noop(monkeypatch, capsys, runner):
    runner.runs = [_run_status("review_1", "completed")]
    _run(monkeypatch, "stop", "review_1")
    out = capsys.readouterr().out
    assert "not running (status: completed)" in out
    assert runner.stopped == []


def test_stop_running_run_reports_success(monkeypatch, capsys, runner):
    runner.runs = [_run_status("review_1", "running")]
    _run(monkeypatch, "stop", "review_1")
    assert "[OK] Stopped review_1" in capsys.readouterr().out
    assert runner.stopped == ["review_1"]


def test_stop_failure_exits_nonzero(monkeypatch, capsys, runner):
    runner.runs = [_run_status("review_1", "running")]
    runner.stop_task = lambda task_id: False
    with pytest.raises(SystemExit) as excinfo:
        _run(monkeypatch, "stop", "review_1")
    assert excinfo.value.code == 1
    assert "[X] Failed to stop review_1" in capsys.readouterr().out


# ── ca batch-run ─────────────────────────────────────────────────────────────


@pytest.fixture
def batch_env(monkeypatch, tmp_path):
    """Registry + task blueprint + patched resource resolution."""
    tasks_root = tmp_path / "tasks"
    tasks_root.mkdir()
    config = {
        "project_registry": [
            {"path": "/work/web", "group": "work"},
            {"path": "/work/cli", "group": "common"},
        ]
    }
    monkeypatch.setattr("core.cli.helpers.load_config", lambda: config)
    monkeypatch.setattr(
        "core.web.resource_paths.resolve_resource_path",
        lambda kind, env_var: tasks_root,
    )
    monkeypatch.setattr(
        "core.services.task_service.TaskService.get_task",
        lambda self, name, log_path=None: {"name": name},
    )
    return SimpleNamespace(tasks_root=tasks_root, config=config)


def test_batch_run_without_registered_projects_exits(
    monkeypatch, capsys, runner, tmp_path
):
    monkeypatch.setattr(
        "core.cli.helpers.load_config", lambda: {"project_registry": []}
    )
    monkeypatch.setattr(
        "core.web.resource_paths.resolve_resource_path",
        lambda kind, env_var: tmp_path,
    )
    with pytest.raises(SystemExit) as excinfo:
        _run(monkeypatch, "batch-run", "review", "--engine", "codex")
    assert excinfo.value.code == 1
    assert "No registered projects" in capsys.readouterr().out


def test_batch_run_group_filter_is_named_when_it_matches_nothing(
    monkeypatch, capsys, runner, batch_env
):
    with pytest.raises(SystemExit):
        _run(
            monkeypatch, "batch-run", "review", "--engine", "codex", "--group", "ghost"
        )
    assert "in group 'ghost'" in capsys.readouterr().out


def test_batch_run_unknown_task_exits(monkeypatch, capsys, runner, batch_env):
    with patch("core.services.task_service.TaskService.get_task", return_value=None):
        with pytest.raises(SystemExit) as excinfo:
            _run(monkeypatch, "batch-run", "ghost", "--engine", "codex")
    assert excinfo.value.code == 1
    assert "No such task: ghost" in capsys.readouterr().out


def test_batch_run_dry_run_lists_the_plan_without_starting(
    monkeypatch, capsys, runner, batch_env
):
    _run(monkeypatch, "batch-run", "review", "--engine", "codex", "--dry-run")
    out = capsys.readouterr().out
    assert "2 project(s) will run 'review' with codex:" in out
    assert "/work/web" in out and "/work/cli" in out
    assert "(dry run" in out
    assert runner.started == []


def test_batch_run_starts_per_project_and_skips_busy_ones(
    monkeypatch, capsys, runner, batch_env
):
    from core.services.runner_service import TaskAlreadyRunningError

    def run_task(name, engine, group, **kwargs):
        runner.started.append((name, engine, group, kwargs))
        if kwargs["workspace"] == "/work/cli":
            raise TaskAlreadyRunningError(name, kwargs["workspace"])
        return _run_status(f"{name}_x", "running", workspace=kwargs["workspace"])

    runner.run_task = run_task
    _run(monkeypatch, "batch-run", "review", "--engine", "codex")
    out = capsys.readouterr().out
    assert "[OK] started review_x  (/work/web)" in out
    assert "skipped, already running  (/work/cli)" in out
    assert "1 started, 1 skipped, 0 failed." in out
    assert "ca ps" in out
    # Group comes from the registry entry; overlap protection is always on.
    assert runner.started[0][2] == "work"
    assert runner.started[0][3]["prevent_overlap"] is True
    assert runner.started[0][3]["tasks_root"] == batch_env.tasks_root


def test_batch_run_failure_exits_nonzero(monkeypatch, capsys, runner, batch_env):
    def run_task(name, engine, group, **kwargs):
        raise ValueError("engine missing")

    runner.run_task = run_task
    with pytest.raises(SystemExit) as excinfo:
        _run(monkeypatch, "batch-run", "review", "--engine", "codex", "--group", "work")
    assert excinfo.value.code == 1
    out = capsys.readouterr().out
    assert "failed: engine missing" in out
    assert "0 started, 0 skipped, 1 failed." in out


# ── ca new ───────────────────────────────────────────────────────────────────


def test_new_launches_the_authoring_engine_with_the_target_path(
    monkeypatch, capsys, tmp_path
):
    root = tmp_path / "root"
    root.mkdir()
    monkeypatch.setattr("core.cli.helpers._project_root", lambda: root)
    monkeypatch.setattr("core.cli.helpers.load_config", lambda: {})
    completed = MagicMock(returncode=0)

    with patch("core.cli.commands.tasks.subprocess.run", return_value=completed) as run:
        assert _run(monkeypatch, "new", "demo") == 0

    out = capsys.readouterr().out
    assert "draft: demo" in out
    assert "Target location:" in out
    cmd = run.call_args.args[0]
    assert cmd[1] == str(root / "engines" / "start_opencode.py")
    assert "demo.md" in cmd[2]


def test_new_defaults_the_task_name(monkeypatch, capsys, tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    monkeypatch.setattr("core.cli.helpers._project_root", lambda: root)
    monkeypatch.setattr("core.cli.helpers.load_config", lambda: {})

    with patch(
        "core.cli.commands.tasks.subprocess.run", return_value=MagicMock(returncode=3)
    ) as run:
        assert _run(monkeypatch, "new") == 3
    assert "unnamed_task.md" in run.call_args.args[0][2]

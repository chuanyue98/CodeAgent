"""后台委派：挂载参数、深度守卫、运行状态流转、review 的隔离。"""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

import pytest

from core.delegation_depth import DEPTH_ENV
from core.engine_base.mcp_mixin import _McpMixin
from core.services import delegation_runs, delegation_worker
from core.services.delegation_service import DelegationResult, delegate_subtask


@pytest.fixture
def mount_enabled(monkeypatch):
    monkeypatch.delenv(DEPTH_ENV)


@pytest.fixture
def runs_home(tmp_path, monkeypatch):
    monkeypatch.setattr(delegation_runs, "runs_root", lambda: tmp_path / "runs")
    return tmp_path / "runs"


# --- 挂载 ------------------------------------------------------------------


def test_claude_style_mcp_arg_is_a_single_equals_token(mount_enabled):
    """空格写法会让变长的 --mcp-config 把首条消息当成配置文件吞掉。"""
    [arg] = _McpMixin().mcp_config_arg()
    flag, _, payload = arg.partition("=")
    assert flag == "--mcp-config"
    server = json.loads(payload)["mcpServers"]["codeagent"]
    assert server["args"][-1] == "--delegation"
    assert server["env"][DEPTH_ENV] == "0"


def test_codex_overrides_are_config_flags(mount_enabled):
    args = _McpMixin().codex_mcp_overrides()
    assert args[0::2] == ["-c"] * 3
    assert args[1].startswith('mcp_servers.codeagent.command="')
    assert args[3].startswith('mcp_servers.codeagent.args=["-m",')
    assert args[5].startswith("mcp_servers.codeagent.env={PYTHONPATH = ")


def test_codebuddy_delegation_agent_runs_in_background(mount_enabled):
    [arg] = _McpMixin().delegation_agent_arg()
    flag, _, payload = arg.partition("=")
    assert flag == "--agents"
    assert json.loads(payload)["ca-delegate"]["background"] is True


def test_opencode_env_keeps_existing_config_content(mount_enabled):
    env = {"OPENCODE_CONFIG_CONTENT": json.dumps({"model": "x/y"})}
    _McpMixin().apply_opencode_mcp_env(env)
    content = json.loads(env["OPENCODE_CONFIG_CONTENT"])
    assert content["model"] == "x/y"
    assert content["mcp"]["codeagent"]["type"] == "local"
    assert env["OPENCODE_EXPERIMENTAL_BACKGROUND_SUBAGENTS"] == "true"


def test_nothing_is_mounted_at_the_depth_limit(monkeypatch):
    monkeypatch.setenv(DEPTH_ENV, "1")
    mixin = _McpMixin()
    env: dict[str, str] = {}
    mixin.apply_opencode_mcp_env(env)
    assert mixin.mcp_config_arg() == []
    assert mixin.codex_mcp_overrides() == []
    assert mixin.delegation_agent_arg() == []
    assert env == {}


def test_delegated_engine_is_started_one_level_deeper(tmp_path, monkeypatch):
    seen: dict = {}

    def fake_run(cmd, **kwargs):
        seen["env"] = kwargs["env"]
        return subprocess.CompletedProcess(cmd, 0, "done", "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(
        "core.services.delegation_service.is_git_repo", lambda _path: False
    )
    delegate_subtask("codex", "do it", workspace=tmp_path, depth=0)
    assert seen["env"][DEPTH_ENV] == "1"


# --- 运行状态 --------------------------------------------------------------


def _fake_result(**overrides) -> DelegationResult:
    fields = dict(
        success=True,
        engine="codex",
        instruction="x",
        exit_code=0,
        output="line\n" * 5 + "最终结论",
        files_changed=["a.py"],
        diff="+x",
    )
    fields.update(overrides)
    return DelegationResult(**fields)


def _new_run(runs_home: Path, run_id: str, task: dict) -> Path:
    run_dir = runs_home / run_id
    run_dir.mkdir(parents=True)
    (run_dir / "task.json").write_text(json.dumps(task), encoding="utf-8")
    return run_dir


def test_worker_writes_result_and_terminal_status(runs_home, tmp_path, monkeypatch):
    run_id = "codex-20260923-120000-aaaaaa"
    run_dir = _new_run(
        runs_home,
        run_id,
        {"engine": "codex", "instruction": "x", "workspace": str(tmp_path)},
    )
    seen: dict = {}

    def fake_delegate(**kwargs):
        seen.update(kwargs)
        return _fake_result()

    monkeypatch.setattr(delegation_worker, "delegate_subtask", fake_delegate)

    assert delegation_worker.run(run_dir) == 0
    run = delegation_runs.get_run(run_id)
    assert run["status"] == "completed"
    assert run["result"]["summary"].endswith("最终结论")
    assert run["result"]["files_changed"] == ["a.py"]
    assert seen["log_path"] == run_dir / "output.log"


def test_worker_failure_is_still_reported(runs_home, tmp_path, monkeypatch):
    run_id = "codex-20260923-120000-bbbbbb"
    run_dir = _new_run(
        runs_home,
        run_id,
        {"engine": "codex", "instruction": "x", "workspace": str(tmp_path)},
    )

    def boom(**_kwargs):
        raise RuntimeError("engine exploded")

    monkeypatch.setattr(delegation_worker, "delegate_subtask", boom)

    assert delegation_worker.run(run_dir) == 1
    run = delegation_runs.get_run(run_id)
    assert run["status"] == "failed"
    assert "engine exploded" in run["error"]


def test_dead_worker_without_result_reads_as_failed(runs_home, tmp_path):
    run_id = "codex-20260923-120000-cccccc"
    run_dir = _new_run(runs_home, run_id, {"engine": "codex"})
    proc = subprocess.Popen(["true"])
    proc.wait()
    (run_dir / "status.json").write_text(
        json.dumps({"status": "running", "pid": proc.pid, "started_at": time.time()}),
        encoding="utf-8",
    )
    assert delegation_runs.get_run(run_id)["status"] == "failed"


def test_wait_returns_running_when_the_budget_runs_out(runs_home):
    run_id = "codex-20260923-120000-dddddd"
    run_dir = _new_run(runs_home, run_id, {"engine": "codex"})
    (run_dir / "status.json").write_text(
        json.dumps({"status": "running", "started_at": time.time()}),
        encoding="utf-8",
    )
    started = time.monotonic()
    run = delegation_runs.wait_run(run_id, timeout=0.3, poll=0.1)
    assert run["status"] == "running"
    assert time.monotonic() - started < 2


def test_run_ids_cannot_escape_the_runs_directory(runs_home):
    with pytest.raises(ValueError):
        delegation_runs.get_run("../../etc")


def test_start_rejects_unknown_engine_and_mode(runs_home, tmp_path):
    with pytest.raises(ValueError):
        delegation_runs.start_delegation("nope", "x", workspace=tmp_path)
    with pytest.raises(ValueError):
        delegation_runs.start_delegation("codex", "x", workspace=tmp_path, mode="rm")


# --- review ---------------------------------------------------------------


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True
    ).stdout


@pytest.fixture
def repo_with_uncommitted_change(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    (repo / "a.py").write_text("x = 1\n", encoding="utf-8")
    _git(repo, "add", "a.py")
    _git(repo, "commit", "-qm", "init")
    (repo / "a.py").write_text("x = 2\n", encoding="utf-8")
    return repo


def test_review_sees_uncommitted_changes_and_leaves_no_trace(
    repo_with_uncommitted_change, monkeypatch
):
    repo = repo_with_uncommitted_change
    seen: dict = {}
    real_run = subprocess.run

    def fake_run(cmd, **kwargs):
        if cmd and cmd[0] == "git":
            return real_run(cmd, **kwargs)
        cwd = Path(kwargs["cwd"])
        seen["cwd"] = cwd
        seen["file"] = (cwd / "a.py").read_text(encoding="utf-8")
        seen["prompt"] = cmd[-1]
        return subprocess.CompletedProcess(cmd, 0, "未发现问题", "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    res = delegate_subtask("codex", "看并发", workspace=repo, mode="review")

    assert res.success
    assert seen["cwd"] != repo.resolve()
    assert seen["file"] == "x = 2\n", "审查者要看到的是带改动的工作区"
    assert "只读不写" in seen["prompt"] and "看并发" in seen["prompt"]
    assert res.files_changed == [] and res.diff == ""
    assert "ca/review" not in _git(repo, "branch", "--list")
    assert not (repo / ".ca_worktrees").exists()
    assert (repo / "a.py").read_text(encoding="utf-8") == "x = 2\n"


def test_review_refuses_outside_a_git_repo(tmp_path, monkeypatch):
    def must_not_run(cmd, **kwargs):
        if cmd and cmd[0] == "git":
            return subprocess.CompletedProcess(cmd, 128, "", "")
        raise AssertionError("不该在原地拉起引擎")

    monkeypatch.setattr(subprocess, "run", must_not_run)
    res = delegate_subtask("codex", "x", workspace=tmp_path, mode="review")
    assert not res.success
    assert "worktree" in (res.error or "")


def test_in_place_run_reports_only_what_the_subtask_changed(
    repo_with_uncommitted_change, monkeypatch
):
    """用户本来就有的未提交改动和未跟踪文件，不能算成子任务的产出。"""
    repo = repo_with_uncommitted_change
    (repo / "notes.txt").write_text("mine\n", encoding="utf-8")
    real_run = subprocess.run

    def fake_run(cmd, **kwargs):
        if cmd and cmd[0] == "git":
            return real_run(cmd, **kwargs)
        (repo / "b.py").write_text("y = 1\n", encoding="utf-8")
        return subprocess.CompletedProcess(cmd, 0, "done", "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    res = delegate_subtask("codex", "add b.py", workspace=repo)

    assert res.files_changed == ["b.py"]
    assert "a.py" not in res.diff
    assert (repo / "a.py").read_text(encoding="utf-8") == "x = 2\n"
    assert _git(repo, "stash", "list") == ""

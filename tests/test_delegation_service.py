"""Tests for core/services/delegation_service.py."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from core.services.delegation_service import (
    DelegationResult,
    _collect_git_changes,
    delegate_subtask,
    get_git_root,
    handoff_session,
    is_git_repo,
    isolated_worktree,
)


def _init_git_repo(path: Path) -> None:
    """Helper to initialize a test git repository."""
    subprocess.run(["git", "init", str(path)], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(path), "config", "user.name", "Test User"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(path), "config", "user.email", "test@example.com"],
        check=True,
        capture_output=True,
    )
    readme = path / "README.md"
    readme.write_text("# Test Repo\n", encoding="utf-8")
    subprocess.run(
        ["git", "-C", str(path), "add", "README.md"], check=True, capture_output=True
    )
    subprocess.run(
        ["git", "-C", str(path), "commit", "-m", "initial commit"],
        check=True,
        capture_output=True,
    )


def test_delegation_result_summary_success():
    res = DelegationResult(
        success=True,
        engine="codex",
        instruction="Refactor auth module",
        exit_code=0,
        output="Building...\nTests passed!\nDone.",
        files_changed=["auth.py", "test_auth.py"],
        diff="--- a/auth.py\n+++ b/auth.py\n@@ -1 +1 @@\n-old\n+new",
        branch="ca/worker-12345",
        isolated_worktree=True,
        duration_seconds=12.5,
    )
    summary = res.to_summary()
    assert "[CODEX] — SUCCESS" in summary
    assert "12.5s" in summary
    assert "`ca/worker-12345`" in summary
    assert "`auth.py`" in summary
    assert "```diff" in summary
    assert "<details><summary>Execution Output Tail" in summary


def test_delegation_result_summary_failure():
    res = DelegationResult(
        success=False,
        engine="claude",
        instruction="Fix syntax error",
        exit_code=1,
        output="SyntaxError: invalid syntax",
        error="Process exited with code 1",
        duration_seconds=2.1,
    )
    summary = res.to_summary()
    assert "[CLAUDE] — FAILED (exit 1)" in summary
    assert "Process exited with code 1" in summary


def test_is_git_repo_and_get_git_root(tmp_path: Path):
    non_git = tmp_path / "not_git"
    non_git.mkdir()
    assert not is_git_repo(non_git)

    git_repo = tmp_path / "git_repo"
    git_repo.mkdir()
    _init_git_repo(git_repo)

    assert is_git_repo(git_repo)
    assert get_git_root(git_repo) == git_repo.resolve()

    sub_dir = git_repo / "src" / "deep"
    sub_dir.mkdir(parents=True)
    assert is_git_repo(sub_dir)
    assert get_git_root(sub_dir) == git_repo.resolve()


def test_isolated_worktree_non_git(tmp_path: Path):
    non_git = tmp_path / "non_git_dir"
    non_git.mkdir()
    with isolated_worktree(non_git) as ctx:
        assert ctx["path"] == non_git.resolve()
        assert ctx["isolated"] is False
        assert ctx["branch"] is None


def test_isolated_worktree_git_lifecycle(tmp_path: Path):
    git_repo = tmp_path / "worktree_test_repo"
    git_repo.mkdir()
    _init_git_repo(git_repo)

    # 1. No changes made in worktree: branch should be deleted and worktree cleaned up
    with isolated_worktree(git_repo) as ctx:
        assert ctx["isolated"] is True
        assert ctx["branch"].startswith("ca/worker-")
        wt_path = ctx["path"]
        assert wt_path.exists()
        branch_name = ctx["branch"]

    assert not wt_path.exists()
    # Check branch is removed
    res = subprocess.run(
        ["git", "-C", str(git_repo), "branch", "--list", branch_name],
        capture_output=True,
        text=True,
    )
    assert branch_name not in res.stdout

    # 2. Changes made in worktree: branch should be preserved with committed changes
    saved_branch = None
    with isolated_worktree(git_repo) as ctx:
        assert ctx["isolated"] is True
        wt_path = ctx["path"]
        saved_branch = ctx["branch"]
        new_file = wt_path / "feature.txt"
        new_file.write_text("worktree feature", encoding="utf-8")

    assert not wt_path.exists()
    # Branch should exist and contain the commit
    res = subprocess.run(
        ["git", "-C", str(git_repo), "branch", "--list", saved_branch],
        capture_output=True,
        text=True,
    )
    assert saved_branch in res.stdout

    log_res = subprocess.run(
        ["git", "-C", str(git_repo), "log", "-1", "--oneline", saved_branch],
        capture_output=True,
        text=True,
    )
    assert f"ca: subtask commit on {saved_branch}" in log_res.stdout


def test_collect_git_changes(tmp_path: Path):
    git_repo = tmp_path / "diff_repo"
    git_repo.mkdir()
    _init_git_repo(git_repo)

    files, diff = _collect_git_changes(git_repo)
    assert files == []
    assert diff == ""

    # Modify file
    (git_repo / "README.md").write_text("# Updated\n", encoding="utf-8")
    files, diff = _collect_git_changes(git_repo)
    assert "README.md" in files
    assert "-# Test Repo" in diff
    assert "+# Updated" in diff


def test_delegate_subtask_validation(tmp_path: Path):
    # Invalid engine
    res = delegate_subtask("non_existent_engine", "do something")
    assert not res.success
    assert "Unknown engine" in (res.error or "")

    # Empty instruction
    res = delegate_subtask("claude", "   ")
    assert not res.success
    assert "empty" in (res.error or "").lower()

    # Missing launch script
    dummy_root = tmp_path / "fake_ca_root"
    dummy_root.mkdir()
    res = delegate_subtask("claude", "say hello", root_dir=dummy_root)
    assert not res.success
    assert "Launch script not found" in (res.error or "")


def test_delegate_subtask_execution_mocked(tmp_path: Path):
    git_repo = tmp_path / "exec_repo"
    git_repo.mkdir()
    _init_git_repo(git_repo)

    # Setup fake engine launch script
    root = tmp_path / "ca_root"
    engines_dir = root / "engines"
    engines_dir.mkdir(parents=True)
    fake_claude = engines_dir / "start_claude_code.py"
    fake_claude.write_text(
        """import sys
print("Subtask executed successfully with args:", sys.argv[1:])
with open("result.txt", "w", encoding="utf-8") as f:
    f.write("delegated result\\n")
""",
        encoding="utf-8",
    )

    res = delegate_subtask(
        engine="claude",
        instruction="Generate result.txt",
        workspace=git_repo,
        target_paths=["result.txt"],
        root_dir=root,
        isolate=True,
    )

    assert res.success
    assert res.exit_code == 0
    assert "Subtask executed successfully" in res.output
    assert "result.txt" in res.files_changed
    assert res.branch is not None
    assert res.isolated_worktree is True


def test_delegate_subtask_execution_inplace(tmp_path: Path):
    git_repo = tmp_path / "exec_repo_inplace"
    git_repo.mkdir()
    _init_git_repo(git_repo)

    # Setup fake engine launch script
    root = tmp_path / "ca_root_inplace"
    engines_dir = root / "engines"
    engines_dir.mkdir(parents=True)
    fake_claude = engines_dir / "start_claude_code.py"
    fake_claude.write_text(
        """import sys
print("Subtask in-place executed")
with open("inplace.txt", "w", encoding="utf-8") as f:
    f.write("inplace result\\n")
""",
        encoding="utf-8",
    )

    # Default isolate=False
    res = delegate_subtask(
        engine="claude",
        instruction="Generate inplace.txt",
        workspace=git_repo,
        target_paths=["inplace.txt"],
        root_dir=root,
    )

    assert res.success
    assert res.exit_code == 0
    assert "Subtask in-place executed" in res.output
    assert "inplace.txt" in res.files_changed
    assert res.branch is None
    assert res.isolated_worktree is False
    assert (git_repo / "inplace.txt").exists()
    assert (git_repo / "inplace.txt").read_text(encoding="utf-8") == "inplace result\n"


def test_delegated_launcher_runs_quiet(tmp_path: Path):
    """委派的输出会成为交给发起方模型的结果，启动器的日志不能混进去。"""
    root = tmp_path / "ca_root"
    engines_dir = root / "engines"
    engines_dir.mkdir(parents=True)
    (engines_dir / "start_claude_code.py").write_text(
        "import os\nprint('CA_QUIET=' + os.environ.get('CA_QUIET', ''))\n",
        encoding="utf-8",
    )

    res = delegate_subtask(
        engine="claude",
        instruction="anything",
        workspace=tmp_path,
        root_dir=root,
        isolate=False,
    )

    assert "CA_QUIET=1" in res.output


def test_delegate_subtask_timeout(tmp_path: Path, monkeypatch):
    root = tmp_path / "ca_root"
    engines_dir = root / "engines"
    engines_dir.mkdir(parents=True)
    fake_claude = engines_dir / "start_claude_code.py"
    fake_claude.write_text("import time\ntime.sleep(10)\n", encoding="utf-8")

    orig_run = subprocess.run

    def _timeout_run(cmd, *args, **kwargs):
        if str(fake_claude) in [str(c) for c in cmd]:
            raise subprocess.TimeoutExpired(cmd=cmd, timeout=1)
        return orig_run(cmd, *args, **kwargs)

    monkeypatch.setattr(subprocess, "run", _timeout_run)

    res = delegate_subtask(
        engine="claude",
        instruction="Run long task",
        workspace=tmp_path,
        root_dir=root,
        isolate=False,
    )
    assert not res.success
    assert res.exit_code == 124
    assert "timed out" in (res.error or "")


def test_handoff_session_validation():
    with pytest.raises(ValueError, match="Unknown target engine"):
        handoff_session(target_engine="invalid_engine")


def test_handoff_session_resolution_and_convert(tmp_path: Path, monkeypatch):
    class FakeResolved:
        session_id = "sess-123"
        engine = "claude"

    class FakeSession:
        session_id = "sess-123"
        engine = "claude"

    monkeypatch.setattr(
        "core.cli.session_select.resolve_session",
        lambda *args, **kwargs: FakeResolved(),
    )
    monkeypatch.setattr(
        "core.session_history.repository.get_full",
        lambda engine, sid, ws: FakeSession(),
    )
    monkeypatch.setattr(
        "core.session_history.writers.write_session",
        lambda session, target: "new-sess-456",
    )
    monkeypatch.setattr(
        "core.services.resume_commands.resume_command",
        lambda engine, sid, ws: ["codex", "resume", sid],
    )

    result = handoff_session(
        target_engine="codex",
        source_engine="claude",
        session_id="latest",
        project_path=tmp_path,
        reason="Rate limit hit",
    )

    assert result["status"] == "ready"
    assert result["source_engine"] == "claude"
    assert result["target_engine"] == "codex"
    assert result["original_session_id"] == "sess-123"
    assert result["new_session_id"] == "new-sess-456"
    assert result["resume_command"] == "codex resume new-sess-456"
    assert result["reason"] == "Rate limit hit"

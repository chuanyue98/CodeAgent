"""git_service：按运行窗口提取工作区变更的测试。

真实 ``git init`` 仓库 + 受控提交时间（GIT_COMMITTER_DATE），验证窗口归因、
无提交降级和根提交对空树 diff 这三条主路径。
"""

import os
import shutil
import subprocess
import time
from pathlib import Path

import pytest

from core.services import git_service
from core.services.git_service import describe_run_changes

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")

GIT = ["git", "-c", "user.name=test", "-c", "user.email=t@example.com"]


def _git(cwd: Path, *args: str, env: dict | None = None) -> None:
    subprocess.run([*GIT, *args], cwd=cwd, check=True, capture_output=True, env=env)


def _init_repo(path: Path) -> None:
    subprocess.run(
        ["git", "init", "-q", "-b", "main"], cwd=path, check=True, capture_output=True
    )


def _commit(path: Path, filename: str, content: str, message: str, at: float) -> None:
    (path / filename).write_text(content, encoding="utf-8")
    _git(path, "add", filename)
    env = {
        **os.environ,
        "GIT_AUTHOR_DATE": f"@{int(at)}",
        "GIT_COMMITTER_DATE": f"@{int(at)}",
    }
    _git(path, "commit", "-m", message, env=env)


def test_no_workspace_is_unavailable():
    result = describe_run_changes(None, 0, 1)
    assert result == {"available": False, "reason": "no_workspace", "workspace": None}


def test_git_missing_is_unavailable(tmp_path, monkeypatch):
    monkeypatch.setattr(git_service.shutil, "which", lambda _: None)
    result = describe_run_changes(str(tmp_path), 0, 1)
    assert result["available"] is False
    assert result["reason"] == "git_missing"


def test_plain_directory_is_not_git_repo(tmp_path):
    result = describe_run_changes(str(tmp_path), 0, 1)
    assert result == {
        "available": False,
        "reason": "not_git_repo",
        "workspace": str(tmp_path),
    }


def test_commits_inside_window_are_attributed_with_diff(tmp_path):
    _init_repo(tmp_path)
    t0 = time.time() - 10_000
    # 窗口外（超出 60 秒余量）：不应出现
    _commit(tmp_path, "old.txt", "old\n", "chore: old", t0 - 1_000)
    # 窗口内
    _commit(tmp_path, "app.txt", "hello\n", "feat: add app", t0 + 10)

    result = describe_run_changes(str(tmp_path), t0, t0 + 100)

    assert result["available"] is True
    assert result["mode"] == "commits"
    assert [c["message"] for c in result["commits"]] == ["feat: add app"]
    head = subprocess.run(
        ["git", "-C", str(tmp_path), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert result["commits"][0]["sha"] == head
    assert result["commits"][0]["author"] == "test"
    assert result["files"] == [{"path": "app.txt", "additions": 1, "deletions": 0}]
    assert "+hello" in result["diff"]
    assert "-old" not in result["diff"]
    assert result["diff_truncated"] is False


def test_no_commits_in_window_falls_back_to_uncommitted(tmp_path):
    _init_repo(tmp_path)
    t0 = time.time() - 10_000
    _commit(tmp_path, "app.txt", "hello\n", "feat: add app", t0 - 1_000)
    (tmp_path / "app.txt").write_text("hello world\n", encoding="utf-8")
    (tmp_path / "new.txt").write_text("new\n", encoding="utf-8")

    result = describe_run_changes(str(tmp_path), t0, t0 + 10)

    assert result["available"] is True
    assert result["mode"] == "uncommitted"
    assert result["commits"] == []
    assert result["note"] == "window_has_no_commits"
    paths = {e["path"] for e in result["entries"]}
    assert paths == {"app.txt", "new.txt"}


def test_root_commit_diffs_against_empty_tree(tmp_path):
    _init_repo(tmp_path)
    t0 = time.time() - 10_000
    # 仓库唯一的提交落在窗口内：没有父提交可对
    _commit(tmp_path, "app.txt", "hello\n", "init", t0 + 5)

    result = describe_run_changes(str(tmp_path), t0, t0 + 10)

    assert result["mode"] == "commits"
    assert result["files"] == [{"path": "app.txt", "additions": 1, "deletions": 0}]
    assert "+hello" in result["diff"]


def test_running_still_open_window_uses_now(tmp_path):
    _init_repo(tmp_path)
    t0 = time.time() - 10_000
    _commit(tmp_path, "app.txt", "hello\n", "feat: add app", t0 + 5)

    # end_time=None：运行还没结束，窗口上界取当前时间
    result = describe_run_changes(str(tmp_path), t0, None)

    assert result["mode"] == "commits"
    assert len(result["commits"]) == 1

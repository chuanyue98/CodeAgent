"""按运行时间窗口从工作区 git 仓库里提取变更，供任务结果闭环展示。

不引 GitPython，全部走 ``git -C <workspace>`` 子进程。提交归因本身是近似的：
提交时间不等于运行时间，所以窗口两端各放宽 60 秒；窗口内一个提交都没有时，
退化为展示工作区未提交变更，并在结果里说明这一点。
"""

from __future__ import annotations

import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path

# 窗口余量：提交时间戳和运行时间戳通常对不齐，两端各放宽一分钟。
_WINDOW_SLACK_SECONDS = 60

# diff 全文上限，超过截断并置 diff_truncated，避免巨型 diff 撑爆接口。
_MAX_DIFF_CHARS = 200_000

_GIT_TIMEOUT_SECONDS = 30


def _unavailable(reason: str, workspace: str | None = None) -> dict:
    result = {"available": False, "reason": reason, "workspace": workspace}
    return result


def _git(workspace: Path, *args: str, stdin: str | None = None) -> str:
    """Runs a git command in ``workspace``, raising on non-zero exit."""
    completed = subprocess.run(
        ["git", "-C", str(workspace), *args],
        capture_output=True,
        text=True,
        input=stdin,
        timeout=_GIT_TIMEOUT_SECONDS,
        check=True,
    )
    return completed.stdout


def _iso(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, tz=UTC).astimezone().isoformat()


def describe_run_changes(
    workspace: str | None,
    start: float,
    end: float | None = None,
) -> dict:
    """Describes the git changes attributable to one run.

    Returns ``{"available": False, "reason": ...}`` when nothing can be shown
    (no workspace, git missing, not a repo, or git failed). Otherwise returns
    either the commits landed in the run's time window with their combined
    diff (``mode == "commits"``), or the current uncommitted changes when the
    window has no commits (``mode == "uncommitted"``).
    """
    if not workspace:
        return _unavailable("no_workspace")
    ws = Path(workspace)
    if shutil.which("git") is None:
        return _unavailable("git_missing", workspace)
    try:
        inside = _git(ws, "rev-parse", "--is-inside-work-tree").strip()
        if inside != "true":
            return _unavailable("not_git_repo", workspace)
    except (subprocess.SubprocessError, OSError):
        return _unavailable("not_git_repo", workspace)

    since = start - _WINDOW_SLACK_SECONDS
    until = (end if end is not None else datetime.now(UTC).timestamp())
    until += _WINDOW_SLACK_SECONDS

    try:
        return _collect(ws, workspace, since, until)
    except (subprocess.SubprocessError, OSError):
        return _unavailable("git_error", workspace)


def _collect(ws: Path, workspace: str, since: float, until: float) -> dict:
    log_output = _git(
        ws,
        "log",
        f"--since={_iso(since)}",
        f"--until={_iso(until)}",
        "--pretty=%H%x00%s%x00%an%x00%cI",
    )
    commits = []
    for line in log_output.splitlines():
        sha, message, author, committed_at = line.split("\x00", 3)
        commits.append(
            {
                "sha": sha,
                "message": message,
                "author": author,
                "committed_at": committed_at,
            }
        )

    base: dict = {
        "available": True,
        "workspace": workspace,
        "window": {"since": _iso(since), "until": _iso(until)},
    }

    if not commits:
        base["mode"] = "uncommitted"
        base["commits"] = []
        base["entries"] = _porcelain_entries(ws)
        base["note"] = "window_has_no_commits"
        return base

    # git log 输出新→旧，diff 需要旧^..新
    newest, oldest = commits[0]["sha"], commits[-1]["sha"]
    base_range = f"{oldest}^"
    # rev-parse --verify -q 对不存在的引用返回非零：这是检测根提交
    # （没有父提交）的方式，此时改为对空树做 diff
    if subprocess.run(
        ["git", "-C", str(ws), "rev-parse", "--verify", "-q", base_range],
        capture_output=True,
        timeout=_GIT_TIMEOUT_SECONDS,
    ).returncode != 0:
        base_range = _git(ws, "mktree", stdin="").strip()

    base["mode"] = "commits"
    base["commits"] = commits
    base["files"] = _numstat_files(ws, base_range, newest)
    diff = _git(ws, "diff", f"{base_range}..{newest}")
    base["diff"] = diff[:_MAX_DIFF_CHARS]
    base["diff_truncated"] = len(diff) > _MAX_DIFF_CHARS
    return base


def _numstat_files(ws: Path, base: str, head: str) -> list[dict]:
    files = []
    for line in _git(ws, "diff", "--numstat", f"{base}..{head}").splitlines():
        additions, deletions, path = line.split("\t", 2)
        files.append(
            {
                "path": path,
                "additions": int(additions) if additions != "-" else None,
                "deletions": int(deletions) if deletions != "-" else None,
            }
        )
    return files


def _porcelain_entries(ws: Path) -> list[dict]:
    entries = []
    for line in _git(ws, "status", "--porcelain").splitlines():
        if len(line) < 4:
            continue
        status, path = line[:2], line[3:]
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        entries.append({"status": status.strip() or "M", "path": path})
    return entries

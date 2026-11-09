"""就地委派的检查点：开跑前、跑完后各拍一张工作区快照，失败了能一键退回。

就地委派是带 ``-y`` 直接在用户的工作区里改代码。跑砸了、超时了、被停了，
留下的半截改动和用户自己没提交的改动混在一起，手工分不开。

快照用一个临时 index：``git add -A`` → ``write-tree`` → ``commit-tree``，
把整个工作区（已跟踪的改动和未被忽略的新文件，不含 ``.gitignore`` 忽略的）
存成一个提交，挂在 ``refs/ca/checkpoints/<id>/before`` 和 ``.../after`` 上。
用户的 HEAD、index、stash 列表都不动，也不触发任何 git 钩子。

退回（:func:`rewind`）只在工作区仍等于 ``after`` 时进行：委派结束后有人又改过，
退回就会把那些改动一起抹掉，所以先拒绝并列出不一样的文件，``force`` 才强行
退回。``after`` 不在（委派被强行停掉，没来得及拍）时同样要 ``force``。
退回本身也可逆：``after`` 留着，内容随时能从那里取回来。

换行按 git 检出的规则写回（``core.autocrlf`` 等照常生效），和 ``git checkout``
得到的一样。
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

from core.logging_config import get_logger

logger = get_logger(__name__)

REF_PREFIX = "refs/ca/checkpoints/"
KEEP_CHECKPOINTS = 20
_GIT_TIMEOUT = 120
# commit-tree 要作者信息；用户没配 user.name 的仓库也得能拍快照。
_IDENTITY = {
    "GIT_AUTHOR_NAME": "CodeAgent",
    "GIT_AUTHOR_EMAIL": "codeagent@localhost",
    "GIT_COMMITTER_NAME": "CodeAgent",
    "GIT_COMMITTER_EMAIL": "codeagent@localhost",
}
_SAFE_ID = re.compile(r"[^A-Za-z0-9._-]")


class CheckpointError(Exception):
    """拍快照或退回失败，消息里是给用户看的原因。"""


@dataclass
class RewindResult:
    rewound: bool
    restored: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    changed_since: list[str] = field(default_factory=list)
    error: str | None = None


def _git(
    repo: Path,
    *args: str,
    env: dict[str, str] | None = None,
    input: bytes | None = None,
) -> str:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        timeout=_GIT_TIMEOUT,
        env=env,
        input=input,
    )
    if proc.returncode != 0:
        reason = proc.stderr.decode("utf-8", "replace").strip()
        raise CheckpointError(f"git {args[0]} 失败：{reason}")
    return proc.stdout.decode("utf-8", "replace")


def checkpoint_id(name: str | None = None) -> str:
    raw = name or time.strftime("%Y%m%d-%H%M%S") + f"-{os.getpid()}"
    return _SAFE_ID.sub("_", raw)


def _ref(cid: str, which: str) -> str:
    return f"{REF_PREFIX}{cid}/{which}"


def repo_root(path: Path) -> Path | None:
    if shutil.which("git") is None:
        return None
    try:
        return Path(_git(path, "rev-parse", "--show-toplevel").strip()).resolve()
    except (CheckpointError, OSError, subprocess.SubprocessError):
        return None


def snapshot(repo: Path, message: str) -> str:
    """把整个工作区存成一个提交，返回它的 sha。不动用户的 index。"""
    with tempfile.TemporaryDirectory(prefix="ca-checkpoint-") as tmp:
        index = Path(tmp) / "index"
        real_index = Path(_git(repo, "rev-parse", "--git-path", "index").strip())
        if not real_index.is_absolute():
            real_index = repo / real_index
        if real_index.is_file():
            # 拷用户的 index 只为借它的 stat 缓存，免得把每个文件重新算一遍哈希。
            shutil.copyfile(real_index, index)
        env = {**os.environ, **_IDENTITY, "GIT_INDEX_FILE": str(index)}
        _git(repo, "add", "-A", "--", ":/", env=env)
        tree = _git(repo, "write-tree", env=env).strip()
        head = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "--verify", "-q", "HEAD"],
            capture_output=True,
            text=True,
            timeout=_GIT_TIMEOUT,
        ).stdout.strip()
        parents = ["-p", head] if head else []
        return _git(repo, "commit-tree", tree, *parents, "-m", message, env=env).strip()


def record(repo: Path, cid: str, which: str) -> str:
    """拍快照并挂到 ``refs/ca/checkpoints/<cid>/<which>`` 上。"""
    sha = snapshot(repo, f"ca checkpoint {cid} ({which})")
    _git(repo, "update-ref", _ref(cid, which), sha)
    if which == "before":
        prune(repo)
    return sha


def _resolve(repo: Path, cid: str, which: str) -> str | None:
    proc = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "--verify", "-q", _ref(cid, which)],
        capture_output=True,
        text=True,
        timeout=_GIT_TIMEOUT,
    )
    return proc.stdout.strip() or None


def prune(repo: Path, keep: int = KEEP_CHECKPOINTS) -> None:
    """只留最近 *keep* 个检查点。"""
    out = _git(
        repo,
        "for-each-ref",
        "--sort=-creatordate",
        "--format=%(refname)",
        REF_PREFIX,
    )
    seen: list[str] = []
    for ref in out.splitlines():
        cid = ref[len(REF_PREFIX) :].rsplit("/", 1)[0]
        if cid not in seen:
            seen.append(cid)
    for cid in seen[keep:]:
        for which in ("before", "after"):
            subprocess.run(
                ["git", "-C", str(repo), "update-ref", "-d", _ref(cid, which)],
                capture_output=True,
                timeout=_GIT_TIMEOUT,
            )


def _changes(repo: Path, old: str, new: str) -> list[tuple[str, str]]:
    """``old`` → ``new`` 的 (状态, 路径)，不做改名检测。"""
    out = _git(repo, "diff", "--name-status", "--no-renames", "-z", old, new)
    parts = [p for p in out.split("\0") if p]
    return list(zip(parts[0::2], parts[1::2], strict=False))


def _remove_empty_parents(folder: Path, repo: Path) -> None:
    """委派新建的目录里的文件删光后，目录本身也删掉；碰到非空目录就停。"""
    while folder != repo and repo in folder.parents:
        try:
            folder.rmdir()
        except OSError:
            return
        folder = folder.parent


def rewind(workspace: Path, cid: str, *, force: bool = False) -> RewindResult:
    """把工作区退回检查点 *cid* 的 ``before``。"""
    repo = repo_root(workspace)
    if repo is None:
        return RewindResult(False, error=f"{workspace} 不在 git 仓库里")
    try:
        before = _resolve(repo, cid, "before")
        if before is None:
            return RewindResult(False, error=f"没有检查点 {cid}（可能已被清理）")
        after = _resolve(repo, cid, "after")
        current = snapshot(repo, f"ca checkpoint {cid} (rewind)")
        if not force:
            if after is None:
                return RewindResult(
                    False,
                    error=(
                        "委派没有正常结束，没有结束时的快照，无法确认之后没人改过；"
                        "确认要退回请加 force"
                    ),
                )
            since = [path for _status, path in _changes(repo, after, current)]
            if since:
                return RewindResult(
                    False,
                    changed_since=since,
                    error="委派结束后这些文件又被改过，退回会把这些改动一起抹掉；确认要退回请加 force",
                )
        removed: list[str] = []
        restored: list[str] = []
        for status, path in _changes(repo, before, current):
            if status == "A":
                target = repo / path
                if target.is_file() or target.is_symlink():
                    target.unlink()
                    _remove_empty_parents(target.parent, repo)
                removed.append(path)
            else:
                restored.append(path)
        if restored:
            _git(
                repo,
                "restore",
                f"--source={before}",
                "--worktree",
                "--pathspec-from-file=-",
                "--pathspec-file-nul",
                env={**os.environ, "GIT_LITERAL_PATHSPECS": "1"},
                input=b"\0".join(p.encode() for p in restored),
            )
        return RewindResult(True, restored=restored, removed=removed)
    except (CheckpointError, OSError, subprocess.SubprocessError) as exc:
        return RewindResult(False, error=str(exc))


def start(workspace: Path, name: str | None = None) -> str | None:
    """委派开跑前拍 ``before``，返回检查点 id；拍不了（不是 git 仓库等）返回 ``None``。

    检查点是额外的保险，拍失败只记警告，不挡委派。
    """
    repo = repo_root(workspace)
    if repo is None:
        return None
    cid = checkpoint_id(name)
    try:
        record(repo, cid, "before")
    except (CheckpointError, OSError, subprocess.SubprocessError) as exc:
        logger.warning("委派前的检查点没拍成，这次委派无法退回：%s", exc)
        return None
    return cid


def finish(workspace: Path, cid: str) -> None:
    """委派结束（含超时）后拍 ``after``，退回时据此判断之后有没有人改过。"""
    repo = repo_root(workspace)
    if repo is None:
        return
    try:
        record(repo, cid, "after")
    except (CheckpointError, OSError, subprocess.SubprocessError) as exc:
        logger.warning("委派后的检查点没拍成，退回时需要 force：%s", exc)

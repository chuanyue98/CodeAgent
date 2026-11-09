"""就地委派的检查点与退回（core/services/delegation_checkpoint.py）。

用真实的 git 仓库测。仓库不配 user.name：测试 HOME 是临时目录，没有全局身份，
正好覆盖「用户没配身份也得能拍快照」。
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from core.services import delegation_checkpoint as cp
from core.services.delegation_service import delegate_subtask


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        encoding="utf-8",
    ).stdout


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """一个带着用户自己未提交改动、已暂存改动和未跟踪文件的仓库。"""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "core.autocrlf", "false")
    (repo / "a.py").write_text("a = 1\n", encoding="utf-8")
    (repo / "b.py").write_text("b = 1\n", encoding="utf-8")
    (repo / "staged.py").write_text("s = 1\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "-c", "user.name=u", "-c", "user.email=u@x", "commit", "-qm", "init")
    (repo / "a.py").write_text("a = 2  # 用户的\n", encoding="utf-8")
    (repo / "staged.py").write_text("s = 2\n", encoding="utf-8")
    _git(repo, "add", "staged.py")
    (repo / "notes.txt").write_text("用户的笔记\n", encoding="utf-8")
    return repo


def _subtask_edits(repo: Path) -> None:
    (repo / "a.py").write_text("a = 3  # 子任务\n", encoding="utf-8")
    (repo / "b.py").unlink()
    (repo / "notes.txt").write_text("被子任务改了\n", encoding="utf-8")
    (repo / "new" / "deep").mkdir(parents=True)
    (repo / "new" / "deep" / "c.py").write_text("c = 1\n", encoding="utf-8")
    (repo / "[odd] name.txt").write_text("x\n", encoding="utf-8")


def _state(repo: Path) -> dict[str, str]:
    return {
        "head": _git(repo, "rev-parse", "HEAD"),
        "index": _git(repo, "diff", "--cached"),
        "stash": _git(repo, "stash", "list"),
    }


def test_rewind_undoes_only_the_subtask(repo):
    before_state = _state(repo)
    cid = cp.start(repo, "run-1")
    assert cid == "run-1"
    _subtask_edits(repo)
    cp.finish(repo, cid)

    res = cp.rewind(repo, cid)

    assert res.rewound, res.error
    assert (repo / "a.py").read_text(encoding="utf-8") == "a = 2  # 用户的\n"
    assert (repo / "b.py").read_text(encoding="utf-8") == "b = 1\n"
    assert (repo / "notes.txt").read_text(encoding="utf-8") == "用户的笔记\n"
    assert not (repo / "new").exists()
    assert not (repo / "[odd] name.txt").exists()
    assert sorted(res.removed) == ["[odd] name.txt", "new/deep/c.py"]
    # HEAD、暂存区、stash 列表都不动。
    assert _state(repo) == before_state


def test_snapshots_leave_the_users_repo_alone(repo):
    before_state = _state(repo)
    status = _git(repo, "status", "--porcelain")
    branches = _git(repo, "branch", "--list")
    cid = cp.start(repo, "run-1")
    cp.finish(repo, cid)
    assert _state(repo) == before_state
    assert _git(repo, "status", "--porcelain") == status
    assert _git(repo, "branch", "--list") == branches


def test_rewind_refuses_when_files_changed_after_the_run(repo):
    cid = cp.start(repo, "run-1")
    _subtask_edits(repo)
    cp.finish(repo, cid)
    (repo / "a.py").write_text("a = 4  # 用户之后又改的\n", encoding="utf-8")

    res = cp.rewind(repo, cid)
    assert not res.rewound
    assert res.changed_since == ["a.py"]
    assert (repo / "a.py").read_text(encoding="utf-8") == "a = 4  # 用户之后又改的\n"

    assert cp.rewind(repo, cid, force=True).rewound
    assert (repo / "a.py").read_text(encoding="utf-8") == "a = 2  # 用户的\n"


def test_stopped_run_without_after_snapshot_needs_force(repo):
    cid = cp.start(repo, "run-1")
    _subtask_edits(repo)  # 被强行停掉，没有 finish

    res = cp.rewind(repo, cid)
    assert not res.rewound and "force" in (res.error or "")
    assert cp.rewind(repo, cid, force=True).rewound
    assert (repo / "b.py").exists()


def test_rewind_is_itself_reversible(repo):
    cid = cp.start(repo, "run-1")
    _subtask_edits(repo)
    cp.finish(repo, cid)
    cp.rewind(repo, cid)

    after = _git(repo, "rev-parse", f"{cp.REF_PREFIX}{cid}/after").strip()
    assert _git(repo, "show", f"{after}:a.py") == "a = 3  # 子任务\n"


def test_unknown_checkpoint_and_non_git_dir(repo, tmp_path):
    assert "没有检查点" in (cp.rewind(repo, "nope").error or "")
    plain = tmp_path / "plain"
    plain.mkdir()
    assert cp.start(plain) is None
    assert not cp.rewind(plain, "x").rewound


def test_only_recent_checkpoints_are_kept(repo, monkeypatch):
    monkeypatch.setattr(cp, "KEEP_CHECKPOINTS", 3)
    for i in range(5):
        cid = cp.start(repo, f"run-{i}")
        cp.finish(repo, cid)
        cp.prune(repo, keep=3)
    refs = _git(repo, "for-each-ref", "--format=%(refname)", cp.REF_PREFIX).split()
    ids = {r[len(cp.REF_PREFIX) :].rsplit("/", 1)[0] for r in refs}
    assert len(ids) == 3


# ── 接进委派 ────────────────────────────────────────────────────────────


def _fake_launcher(tmp_path: Path) -> Path:
    root = tmp_path / "ca_root"
    (root / "engines").mkdir(parents=True)
    (root / "engines" / "start_codex.py").write_text("", encoding="utf-8")
    return root


def test_in_place_delegation_can_be_rewound(repo, tmp_path, monkeypatch):
    def fake_run(cmd, cwd, env, timeout, log_path):
        _subtask_edits(Path(cwd))
        return 1, "改砸了"

    monkeypatch.setattr("core.services.delegation_service._run_engine", fake_run)
    res = delegate_subtask(
        "codex",
        "do it",
        workspace=repo,
        root_dir=_fake_launcher(tmp_path),
        checkpoint_name="run-9",
    )
    assert not res.success
    assert res.checkpoint == "run-9"
    assert "run-9" in res.to_summary()
    # 中文 Windows 上 git 输出曾按 GBK 解码失败，diff 悄悄变成空的。
    assert "子任务" in res.diff

    assert cp.rewind(repo, res.checkpoint).rewound
    assert (repo / "a.py").read_text(encoding="utf-8") == "a = 2  # 用户的\n"


def test_isolated_and_review_runs_take_no_checkpoint(repo, tmp_path, monkeypatch):
    monkeypatch.setattr(
        "core.services.delegation_service._run_engine", lambda *a, **k: (0, "ok")
    )
    root = _fake_launcher(tmp_path)
    for kwargs in ({"isolate": True}, {"mode": "review"}):
        res = delegate_subtask("codex", "x", workspace=repo, root_dir=root, **kwargs)
        assert res.checkpoint is None
    assert _git(repo, "for-each-ref", cp.REF_PREFIX) == ""

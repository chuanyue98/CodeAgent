"""Checks the OpenCode converter against OpenCode, not against itself.

The existing writer tests build their database with a hand-written
``CREATE TABLE`` that mirrors the columns our writer touches, so they can only
ever confirm the writer agrees with its own assumptions. They stayed green
through a bug where a converted session loaded and rendered perfectly and then
killed OpenCode's server on the first prompt::

    TypeError: undefined is not an object (evaluating 'X.model.modelID')
        at SessionPrompt.run → SessionRunState.ensureRunning → SessionHttpApi.prompt

OpenCode resolves the model to continue with from the transcript's last
assistant turn, and ours carried no ``modelID``/``providerID``.

The contract in ``fixtures/opencode_assistant_message_contract.json`` is
derived from real OpenCode-written rows, so a field it needs and we skip fails
here instead of at the user's first keystroke.
"""

from __future__ import annotations

import json
import shutil
import sqlite3
from pathlib import Path

import pytest

from core.session_history.models import EngineType, UnifiedMessage, UnifiedSession
from core.session_history.writers.opencode_writer import write_opencode_session
from tests.test_session_history import _init_opencode_db, _make_git_repo

CONTRACT = json.loads(
    (
        Path(__file__).parent / "fixtures" / "opencode_assistant_message_contract.json"
    ).read_text(encoding="utf-8")
)


def _seed_native_models(db_path: Path, models: list[dict | None]) -> None:
    """Adds session rows of the kind OpenCode writes for itself.

    The converter reads the model out of OpenCode's own history, because the
    source engine's model name ("claude-opus-4") names no OpenCode provider.
    Rows are seeded oldest-first so the last entry is the "most recent".
    """
    con = sqlite3.connect(str(db_path))
    with con:
        for index, model in enumerate(models):
            con.execute(
                """INSERT INTO session (
                    id, project_id, slug, directory, title, version, model,
                    time_created, time_updated, metadata,
                    summary_additions, summary_deletions, summary_files
                ) VALUES (?, 'prj_native', 'slug', '/repo', 'native', '1.18.21', ?, ?, ?, '{}', 0, 0, 0)""",
                (
                    f"ses_native_{index}",
                    json.dumps(model) if model is not None else None,
                    index + 1,
                    index + 1,
                ),
            )
    con.close()


def _seed_native_model(db_path: Path, model: dict | None) -> None:
    _seed_native_models(db_path, [model])


def _convert(tmp_path: Path, monkeypatch, model: dict | None) -> dict:
    """Converts a two-message session and returns its assistant message data."""
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    db_path = tmp_path / ".local" / "share" / "opencode" / "opencode.db"
    db_path.parent.mkdir(parents=True)
    _init_opencode_db(db_path)
    _seed_native_model(db_path, model)

    worktree = tmp_path / "repo"
    _make_git_repo(worktree)

    session_id = write_opencode_session(
        UnifiedSession(
            session_id="orig",
            engine=EngineType.CLAUDE,
            project_path=str(worktree),
            model="claude-opus-4",
            messages=[
                UnifiedMessage(role="user", content="hello"),
                UnifiedMessage(role="assistant", content="hi there"),
            ],
        )
    )

    con = sqlite3.connect(str(db_path))
    rows = con.execute(
        "SELECT data FROM message WHERE session_id=?", (session_id,)
    ).fetchall()
    con.close()

    for (raw,) in rows:
        data = json.loads(raw)
        if data.get("role") == "assistant":
            return data
    raise AssertionError("the converted session has no assistant message")


NATIVE_MODEL = {"id": "x-preview-f-free", "providerID": "opencode"}


@pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")
def test_assistant_message_carries_every_key_opencode_always_writes(
    tmp_path, monkeypatch
):
    data = _convert(tmp_path, monkeypatch, NATIVE_MODEL)

    missing = sorted(set(CONTRACT["required_keys"]) - set(data))
    assert not missing, (
        f"OpenCode writes {missing} on every assistant message and the converter "
        f"does not. See the fixture for how the contract was derived."
    )


@pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")
def test_nested_token_and_time_shapes_match(tmp_path, monkeypatch):
    # The tokens.cache.read crash was this same failure one field over, so the
    # nested shapes are worth pinning too.
    data = _convert(tmp_path, monkeypatch, NATIVE_MODEL)

    for path, keys in CONTRACT["nested_required_keys"].items():
        node = data
        for step in path.split("."):
            assert isinstance(node, dict), f"{path}: {step} is not an object"
            node = node.get(step)
        assert isinstance(node, dict), f"{path} is missing"
        assert not set(keys) - set(node), (
            f"{path} is missing {sorted(set(keys) - set(node))}"
        )


@pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")
def test_the_model_comes_from_opencodes_own_history(tmp_path, monkeypatch):
    # Not from the source engine: "claude-opus-4" names no OpenCode provider,
    # and an unresolvable model fails the first turn just as surely as a
    # missing one.
    data = _convert(tmp_path, monkeypatch, NATIVE_MODEL)

    assert data["modelID"] == "x-preview-f-free"
    assert data["providerID"] == "opencode"
    assert "claude" not in json.dumps(data)


@pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")
def test_a_fresh_install_with_no_model_yet_omits_the_fields(tmp_path, monkeypatch):
    # Inventing a provider would produce a session that fails differently and
    # more confusingly than one OpenCode can fall back to a default for.
    data = _convert(tmp_path, monkeypatch, None)

    assert "modelID" not in data
    assert "providerID" not in data


@pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")
def test_zen_models_are_a_fallback_not_a_first_choice(tmp_path, monkeypatch):
    """最新的原生会话若是 Zen（providerID=opencode）模型，不能照抄。

    2026-08-31 的事故：最新一行带着 abort 会话留下的 ``big-pickle``/``opencode``，
    转换把全部 176 条消息盖成它，resume 后第一条 prompt 在
    SessionPrompt.run 里崩了（X.model.modelID undefined）——这台机器根本
    没法服务 Zen 模型。应该跳过 Zen，取最近一个真实第三方 provider。
    """
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    db_path = tmp_path / ".local" / "share" / "opencode" / "opencode.db"
    db_path.parent.mkdir(parents=True)
    _init_opencode_db(db_path)
    _seed_native_models(
        db_path,
        [
            {"id": "glm-5.3", "providerID": "agentrouter"},
            {"id": "big-pickle", "providerID": "opencode"},  # 更新，但是 Zen
        ],
    )

    worktree = tmp_path / "repo"
    _make_git_repo(worktree)

    session_id = write_opencode_session(
        UnifiedSession(
            session_id="orig",
            engine=EngineType.CLAUDE,
            project_path=str(worktree),
            model="claude-opus-4",
            messages=[
                UnifiedMessage(role="user", content="hello"),
                UnifiedMessage(role="assistant", content="hi there"),
            ],
        )
    )

    con = sqlite3.connect(str(db_path))
    rows = con.execute(
        "SELECT data FROM message WHERE session_id=?", (session_id,)
    ).fetchall()
    con.close()

    for (raw,) in rows:
        data = json.loads(raw)
        if data.get("role") == "assistant":
            assert data["modelID"] == "glm-5.3"
            assert data["providerID"] == "agentrouter"
            return
    raise AssertionError("the converted session has no assistant message")

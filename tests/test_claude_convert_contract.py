"""Checks the Claude writer against Claude, not against itself.

``core/session_history/writers/claude_writer.py`` had no tests whatsoever, and
it showed: it stamped a model id and a CLI version that were a generation out
of date, and left out three fields Claude puts on every row. None of that is
detectable by asserting the writer emits what the writer decided to emit, so
the contract in ``fixtures/claude_session_row_contract.json`` is derived from
rows Claude actually wrote.

The project path used here is short and fictional on purpose: Claude names the
session directory after the whole project path with separators replaced, so a
real pytest ``tmp_path`` produces a single directory component long enough to
break the write on Windows. The writer never touches the project directory
itself, only ``~/.claude/projects``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.session_history.models import EngineType, UnifiedMessage, UnifiedSession
from core.session_history.writers import claude_writer

CONTRACT = json.loads(
    (Path(__file__).parent / "fixtures" / "claude_session_row_contract.json").read_text(
        encoding="utf-8"
    )
)

NATIVE_MODEL = "claude-opus-5"
NATIVE_VERSION = "2.1.241"
PROJECT = "E:/x"
BRANCH = "feature/x"


def _seed_native_history(home: Path) -> None:
    """Writes one row of the kind Claude writes for itself.

    The writer reads the model and CLI version out of this, because the
    source engine's model ("gpt-5-codex", "hy3", ...) is not a Claude model
    and a hardcoded id goes stale.
    """
    project = home / ".claude" / "projects" / "E--somewhere"
    project.mkdir(parents=True)
    row = {
        "type": "assistant",
        "version": NATIVE_VERSION,
        "message": {"role": "assistant", "model": NATIVE_MODEL, "content": []},
    }
    (project / "native.jsonl").write_text(
        json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def _convert(tmp_path: Path, monkeypatch, *, seed: bool = True) -> list[dict]:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    # _git_branch has its own tests below; pinning it here keeps these focused
    # on what lands in the row.
    monkeypatch.setattr(claude_writer, "_git_branch", lambda _path: BRANCH)
    if seed:
        _seed_native_history(tmp_path)

    session_id = claude_writer.write_claude_session(
        UnifiedSession(
            session_id="orig",
            engine=EngineType.CODEX,
            project_path=PROJECT,
            model="gpt-5-codex",
            messages=[
                UnifiedMessage(role="user", content="hello"),
                UnifiedMessage(role="assistant", content="hi there"),
            ],
        )
    )

    written = next((tmp_path / ".claude" / "projects").glob(f"*/{session_id}.jsonl"))
    return [
        json.loads(line)
        for line in written.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


@pytest.mark.parametrize("role", ["user", "assistant"])
def test_rows_carry_every_key_claude_always_writes(tmp_path, monkeypatch, role):
    rows = _convert(tmp_path, monkeypatch)
    row = next(r for r in rows if r["type"] == role)

    missing = sorted(set(CONTRACT["row_required_keys"][role]) - set(row))
    assert not missing, f"Claude writes {missing} on every {role} row and we do not"


def test_assistant_message_carries_every_key_claude_always_writes(
    tmp_path, monkeypatch
):
    rows = _convert(tmp_path, monkeypatch)
    message = next(r for r in rows if r["type"] == "assistant")["message"]

    missing = sorted(set(CONTRACT["assistant_message_required_keys"]) - set(message))
    assert not missing, (
        f"Claude writes {missing} on every assistant message and we do not"
    )


def test_model_and_version_come_from_the_install_not_from_a_constant(
    tmp_path, monkeypatch
):
    rows = _convert(tmp_path, monkeypatch)
    assistant = next(r for r in rows if r["type"] == "assistant")

    assert assistant["message"]["model"] == NATIVE_MODEL
    assert assistant["version"] == NATIVE_VERSION
    # The source engine's model names no Claude model; claiming it would make
    # the row a lie and could name a model that cannot be resumed.
    assert "gpt-5-codex" not in json.dumps(rows)


def test_a_claude_to_claude_copy_keeps_the_original_model(tmp_path, monkeypatch):
    # The rule is "only a claude-* id survives", not "always overwrite":
    # copying a Claude session should keep what each turn actually ran on.
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(claude_writer, "_git_branch", lambda _path: BRANCH)
    _seed_native_history(tmp_path)

    session_id = claude_writer.write_claude_session(
        UnifiedSession(
            session_id="orig",
            engine=EngineType.CLAUDE,
            project_path=PROJECT,
            model="claude-sonnet-5",
            messages=[
                UnifiedMessage(role="user", content="hello"),
                UnifiedMessage(
                    role="assistant", content="hi", model="claude-haiku-4-5"
                ),
            ],
        )
    )

    written = next((tmp_path / ".claude" / "projects").glob(f"*/{session_id}.jsonl"))
    rows = [
        json.loads(line)
        for line in written.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assistant = next(r for r in rows if r["type"] == "assistant")

    # The message's own model wins over the session's, and both win over the
    # install default.
    assert assistant["message"]["model"] == "claude-haiku-4-5"


def test_the_resolved_branch_reaches_every_row(tmp_path, monkeypatch):
    rows = _convert(tmp_path, monkeypatch)

    assert [r["gitBranch"] for r in rows] == [BRANCH, BRANCH]


def test_an_install_with_no_history_falls_back_to_claudes_own_marker(
    tmp_path, monkeypatch
):
    # Better than naming a model that may not exist: "<synthetic>" is what
    # Claude itself records for a turn it did not generate, which is exactly
    # what a converted turn is.
    rows = _convert(tmp_path, monkeypatch, seed=False)
    assistant = next(r for r in rows if r["type"] == "assistant")

    assert assistant["message"]["model"] == claude_writer.SYNTHETIC_MODEL


# ── _git_branch, on its own ──────────────────────────────────────────────────
def test_git_branch_reads_the_checkouts_branch(tmp_path):
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "HEAD").write_text(
        "ref: refs/heads/feature/x\n", encoding="utf-8"
    )

    assert claude_writer._git_branch(str(tmp_path)) == "feature/x"


def test_a_detached_head_reports_HEAD_like_claude_does(tmp_path):
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "HEAD").write_text("a" * 40 + "\n", encoding="utf-8")

    assert claude_writer._git_branch(str(tmp_path)) == "HEAD"


def test_a_non_repo_gets_an_empty_branch_rather_than_a_crash(tmp_path):
    assert claude_writer._git_branch(str(tmp_path / "nowhere")) == ""

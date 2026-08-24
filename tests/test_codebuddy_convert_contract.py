"""Checks the CodeBuddy writer against CodeBuddy, not against itself.

Third instance of the same failure the OpenCode and Claude writers had: rows
the target can read but has not been given everything it writes itself. Here
user rows carried no ``providerData`` and assistant rows no ``parentId``, so
every reply in a converted transcript chained to nothing.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.session_history.models import EngineType, UnifiedMessage, UnifiedSession
from core.session_history.writers import codebuddy_writer

CONTRACT = json.loads(
    (Path(__file__).parent / "fixtures" / "codebuddy_row_contract.json").read_text(
        encoding="utf-8"
    )
)

PROJECT = "E:/x"
NATIVE_MODEL = "hy3"


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    return tmp_path


def _seed_native_history(home: Path) -> None:
    project = home / ".codebuddy" / "projects" / "e-somewhere"
    project.mkdir(parents=True)
    row = {
        "type": "message",
        "role": "assistant",
        "providerData": {"model": NATIVE_MODEL, "messageId": "m1"},
    }
    (project / "native.jsonl").write_text(
        json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def _convert(home: Path, engine: EngineType, model: str) -> list[dict]:
    session_id = codebuddy_writer.write_codebuddy_session(
        UnifiedSession(
            session_id="orig",
            engine=engine,
            project_path=PROJECT,
            title="t",
            model=model,
            messages=[
                UnifiedMessage(role="user", content="hello"),
                UnifiedMessage(role="assistant", content="hi there"),
            ],
        )
    )
    written = next((home / ".codebuddy" / "projects").glob(f"*/{session_id}.jsonl"))
    return [
        json.loads(line)
        for line in written.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _row(rows: list[dict], role: str) -> dict:
    return next(r for r in rows if r.get("type") == "message" and r.get("role") == role)


@pytest.mark.parametrize("role", ["user", "assistant"])
def test_rows_carry_every_key_codebuddy_always_writes(home, role):
    _seed_native_history(home)
    rows = _convert(home, EngineType.CLAUDE, "claude-opus-5")

    missing = sorted(set(CONTRACT["row_required_keys"][role]) - set(_row(rows, role)))
    assert not missing, f"CodeBuddy writes {missing} on every {role} row and we do not"


def test_the_assistant_reply_chains_to_the_turn_it_answers(home):
    _seed_native_history(home)
    rows = _convert(home, EngineType.CLAUDE, "claude-opus-5")

    assert _row(rows, "assistant")["parentId"] == _row(rows, "user")["id"]


def test_a_foreign_model_is_not_carried_into_a_codebuddy_file(home):
    # "claude-opus-5" names no CodeBuddy model. Writing it would fail the
    # same way the OpenCode conversion did -- at the first prompt, not here.
    _seed_native_history(home)
    rows = _convert(home, EngineType.CLAUDE, "claude-opus-5")

    assert "claude-opus-5" not in json.dumps(rows)
    assert _row(rows, "assistant")["providerData"]["model"] == NATIVE_MODEL


def test_a_codebuddy_source_keeps_its_own_model(home):
    _seed_native_history(home)
    rows = _convert(home, EngineType.CODEBUDDY, "some-other-model")

    assert _row(rows, "assistant")["providerData"]["model"] == "some-other-model"


def test_a_fresh_install_with_no_history_writes_no_model(home):
    rows = _convert(home, EngineType.CLAUDE, "claude-opus-5")

    # Empty rather than invented: CodeBuddy can fall back to its default,
    # but it cannot serve a model that does not exist.
    assert _row(rows, "assistant")["providerData"] == {}

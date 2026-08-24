"""Tests for the CodeBuddy Code session writer.

Round-trips a UnifiedSession through ``write_codebuddy_session`` and
``parse_codebuddy_session`` to prove the written JSONL is CodeBuddy-native
(the parser can read it back with titles, messages, models and tool calls
intact).
"""

from __future__ import annotations

import json
from pathlib import Path

from core.session_history.models import (
    EngineType,
    ToolCallSummary,
    UnifiedMessage,
    UnifiedSession,
)
from core.session_history.parsers.codebuddy_parser import (
    _encode_codebuddy_project_dir,
    parse_codebuddy_session,
)
from core.session_history.writers import write_session
from core.session_history.writers.codebuddy_writer import write_codebuddy_session


def _sample_session() -> UnifiedSession:
    return UnifiedSession(
        session_id="source-1",
        engine=EngineType.CLAUDE,
        project_path="E:/demo/CodeAgent",
        started_at="2025-08-24T10:00:00.000Z",
        ended_at="2025-08-24T10:05:00.000Z",
        title="开始新的对话会话",
        model="hy3",
        messages=[
            UnifiedMessage(
                role="user",
                content="你好啊",
                timestamp="1787548456532",
            ),
            UnifiedMessage(
                role="assistant",
                content="你好！有什么我可以帮你的吗？",
                timestamp="1787548459000",
                model="hy3",
                tool_calls=[
                    ToolCallSummary(
                        name="Bash",
                        args_preview='{"command": "git status"}',
                        result_preview="On branch main",
                    )
                ],
            ),
        ],
    )


def test_write_codebuddy_session_round_trip(home: Path) -> None:
    session = _sample_session()
    new_id = write_codebuddy_session(session)

    # The file lands in CodeBuddy's projects dir under the encoded path.
    file_path = (
        home / ".codebuddy" / "projects" / "e-demo-CodeAgent" / f"{new_id}.jsonl"
    )
    assert file_path.exists()

    # The parser reads it back with everything intact.
    parsed = parse_codebuddy_session(file_path)
    assert parsed is not None
    assert parsed.engine.value == "codebuddy"
    assert parsed.session_id == new_id
    assert parsed.title == "开始新的对话会话"
    assert parsed.model == "hy3"
    assert len(parsed.messages) == 2

    user, assistant = parsed.messages
    assert user.role == "user"
    assert user.content == "你好啊"
    assert assistant.role == "assistant"
    assert assistant.content == "你好！有什么我可以帮你的吗？"
    assert assistant.model == "hy3"

    # Tool calls re-attach to the assistant message.
    assert len(assistant.tool_calls) == 1
    tc = assistant.tool_calls[0]
    assert tc.name == "Bash"
    assert "git status" in tc.args_preview
    assert tc.result_preview == "On branch main"

    # The writer emits epoch milliseconds (CodeBuddy's own unit) and the parser
    # normalizes them back to ISO 8601 on the way in, so a round trip lands on
    # the ISO spelling the unified model documents.
    assert user.timestamp == "2026-08-24T05:14:16.532Z"
    assert assistant.timestamp == "2026-08-24T05:14:19.000Z"


def test_write_codebuddy_session_normalizes_iso_timestamps(home: Path) -> None:
    """Claude-style ISO timestamps are converted to epoch-ms strings."""
    session = UnifiedSession(
        session_id="source-2",
        engine=EngineType.CLAUDE,
        project_path="E:/demo/CodeAgent",
        messages=[
            UnifiedMessage(
                role="user",
                content="hi",
                timestamp="2025-08-24T10:00:00.000Z",
            )
        ],
    )
    new_id = write_codebuddy_session(session)
    file_path = (
        home / ".codebuddy" / "projects" / "e-demo-CodeAgent" / f"{new_id}.jsonl"
    )
    first = json.loads(file_path.read_text(encoding="utf-8").splitlines()[0])
    assert str(first["timestamp"]).isdigit()


def test_write_session_dispatches_to_codebuddy(home: Path) -> None:
    """The generic write_session() dispatcher routes codebuddy correctly."""
    new_id = write_session(_sample_session(), "codebuddy")
    assert (home / ".codebuddy" / "projects").exists()
    assert len(new_id) == 36  # a UUID


def test_written_directory_uses_parser_encoding(home: Path) -> None:
    """Writer and parser must agree on the directory encoding rule."""
    session = _sample_session()
    write_codebuddy_session(session)
    projects = home / ".codebuddy" / "projects"
    assert _encode_codebuddy_project_dir("E:/demo/CodeAgent") in [
        d.name for d in projects.iterdir()
    ]


def test_posix_cwd_stays_posix(home: Path) -> None:
    """A POSIX project path must not be back-slashed into the ``cwd`` field.

    ``/home/cy/x`` was being written as ``\\home\\cy\\x``, which names no
    directory on Linux or macOS, so every session converted into CodeBuddy
    there pointed at a working directory it could not resolve.
    """
    session = UnifiedSession(
        session_id="orig",
        engine=EngineType.CLAUDE,
        project_path="/home/cy/github/chuanyue98/CUITCCA",
        messages=[UnifiedMessage(role="user", content="hi")],
    )
    new_id = write_codebuddy_session(session)

    written = (
        home
        / ".codebuddy"
        / "projects"
        / "home-cy-github-chuanyue98-CUITCCA"
        / f"{new_id}.jsonl"
    )
    assert written.exists()  # and not under a leading-dash directory
    row = json.loads(written.read_text(encoding="utf-8").splitlines()[0])
    assert row["cwd"] == "/home/cy/github/chuanyue98/CUITCCA"


def test_rows_carry_id_and_numeric_timestamp(home: Path) -> None:
    """Every real CodeBuddy row has an ``id`` and a numeric ``timestamp``."""
    session = UnifiedSession(
        session_id="orig",
        engine=EngineType.CLAUDE,
        project_path="/home/cy/demo",
        title="a title",
        messages=[
            UnifiedMessage(
                role="assistant",
                content="done",
                timestamp="2026-08-24T05:14:16.532Z",
                tool_calls=[ToolCallSummary(name="Bash", args_preview='{"c": "ls"}')],
            )
        ],
    )
    new_id = write_codebuddy_session(session)
    written = next((home / ".codebuddy" / "projects").rglob(f"{new_id}.jsonl"))
    rows = [
        json.loads(line)
        for line in written.read_text(encoding="utf-8").splitlines()
        if line
    ]

    assert rows, "writer produced no rows"
    for row in rows:
        assert row.get("id"), f"row without id: {row['type']}"
        assert isinstance(row["timestamp"], int), (
            f"{row['type']} timestamp is {type(row['timestamp']).__name__}, "
            "but CodeBuddy stores epoch milliseconds as a JSON number"
        )

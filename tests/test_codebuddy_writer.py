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

    # Timestamps stay in epoch-millisecond strings.
    assert user.timestamp == "1787548456532"
    assert assistant.timestamp == "1787548459000"


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

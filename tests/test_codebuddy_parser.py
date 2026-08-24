"""Tests for the CodeBuddy Code session history parser.

Uses a small synthetic JSONL fixture that mirrors the real on-disk format
verified under ``~/.codebuddy/projects/e-demo-CodeAgent/<uuid>.jsonl``.
"""

from __future__ import annotations

import json
from pathlib import Path

from core.session_history.parsers.codebuddy_parser import (
    _codebuddy_dir_matches,
    _encode_codebuddy_project_dir,
    find_codebuddy_sessions,
    parse_codebuddy_session,
)

# A user turn, an ai-title, and a completed assistant turn — exactly the shape
# CodeBuddy Code writes for a "你好啊" conversation.
SAMPLE_ROWS = [
    {
        "id": "u1",
        "timestamp": 1787548456532,
        "type": "message",
        "role": "user",
        "cwd": "e:\\demo\\CodeAgent",
        "content": [{"type": "input_text", "text": "你好啊"}],
        "sessionId": "49cb2b65-d18e-4578-bd84-2d9ae96329cf",
    },
    {
        "id": "t1",
        "timestamp": 1787548458149,
        "type": "ai-title",
        "aiTitle": "开始新的对话会话",
        "cwd": "e:\\demo\\CodeAgent",
    },
    {
        "id": "a1",
        "timestamp": 1787548459000,
        "type": "message",
        "role": "assistant",
        "status": "completed",
        "providerData": {"model": "hy3"},
        "cwd": "e:\\demo\\CodeAgent",
        "content": [
            {"type": "output_text", "text": "你好！有什么我可以帮你的吗？"}
        ],
    },
    {
        "id": "f1",
        "timestamp": 1787548460000,
        "type": "function_call",
        "name": "Bash",
        "callId": "call-1",
        "arguments": {"command": "git status"},
        "cwd": "e:\\demo\\CodeAgent",
    },
    {
        "id": "r1",
        "timestamp": 1787548461000,
        "type": "function_call_result",
        "name": "Bash",
        "callId": "call-1",
        "status": "completed",
        "output": {"type": "text", "text": "On branch main"},
        "cwd": "e:\\demo\\CodeAgent",
    },
]


def _write_session(dir_path: Path, rows: list[dict], name: str = "sess-1.jsonl") -> Path:
    """Writes *rows* as JSONL into *dir_path* and returns the file path."""
    dir_path.mkdir(parents=True, exist_ok=True)
    file_path = dir_path / name
    with file_path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return file_path


def test_dir_encoding_rule() -> None:
    assert _encode_codebuddy_project_dir("E:\\demo\\CodeAgent") == "e-demo-CodeAgent"
    # Drive letter is lower-cased; the rest keeps original case.
    assert _encode_codebuddy_project_dir("C:/Users/Administrator") == "c-Users-Administrator"


def test_dir_matches_target_path() -> None:
    assert _codebuddy_dir_matches("e-demo-CodeAgent", "E:/demo/CodeAgent")
    assert _codebuddy_dir_matches("e-demo-CodeAgent", "e:/demo/codeagent")
    assert not _codebuddy_dir_matches("e-other-Project", "E:/demo/CodeAgent")


def test_missing_file_returns_none() -> None:
    assert parse_codebuddy_session(Path("/no/such/file.jsonl")) is None
    # Wrong extension is also rejected.
    assert parse_codebuddy_session(Path("/no/such/file.txt")) is None


def test_user_assistant_extraction_and_title(tmp_path: Path) -> None:
    file_path = _write_session(tmp_path, SAMPLE_ROWS)
    session = parse_codebuddy_session(file_path)

    assert session is not None
    assert session.engine.value == "codebuddy"
    assert session.title == "开始新的对话会话"

    assert len(session.messages) == 2  # user + assistant (tool calls attach, not standalone)
    user, assistant = session.messages
    assert user.role == "user"
    assert user.content == "你好啊"
    assert assistant.role == "assistant"
    assert assistant.content == "你好！有什么我可以帮你的吗？"
    assert assistant.model == "hy3"

    # Timestamps are stored as the raw millisecond strings.
    assert user.timestamp == "1787548456532"
    assert assistant.timestamp == "1787548459000"


def test_function_call_tool_summary(tmp_path: Path) -> None:
    file_path = _write_session(tmp_path, SAMPLE_ROWS)
    session = parse_codebuddy_session(file_path)
    assert session is not None

    assistant = session.messages[1]
    assert len(assistant.tool_calls) == 1
    tc = assistant.tool_calls[0]
    assert tc.name == "Bash"
    assert "git status" in tc.args_preview
    assert tc.result_preview == "On branch main"


def test_cwd_fallback_project_path(tmp_path: Path) -> None:
    # No cwd in any row: project_path falls back to the encoded directory name.
    rows = [
        {
            "id": "u1",
            "timestamp": 1787548456532,
            "type": "message",
            "role": "user",
            "content": [{"type": "input_text", "text": "hi"}],
        }
    ]
    dir_path = tmp_path / "e-demo-CodeAgent"
    file_path = _write_session(dir_path, rows)
    session = parse_codebuddy_session(file_path)

    assert session is not None
    assert session.project_path == "e-demo-CodeAgent"  # dir-name fallback


def test_find_codebuddy_sessions_with_home(home: Path) -> None:
    projects = home / ".codebuddy" / "projects"
    _write_session(projects / "e-demo-CodeAgent", SAMPLE_ROWS)

    sessions = find_codebuddy_sessions("E:/demo/CodeAgent", home=home)
    assert len(sessions) == 1

    session = sessions[0]
    assert session.engine.value == "codebuddy"
    assert session.title == "开始新的对话会话"
    assert session.session_id == "sess-1"
    # cwd resolves to the canonical (user-supplied) spelling.
    assert session.project_path == "E:/demo/CodeAgent"
    assert session.first_user_message == "你好啊"


def test_find_codebuddy_sessions_filters_other_projects(home: Path) -> None:
    projects = home / ".codebuddy" / "projects"
    _write_session(projects / "e-demo-CodeAgent", SAMPLE_ROWS)
    _write_session(
        projects / "e-other-Project",
        [
            {
                "id": "u2",
                "timestamp": 1787548456532,
                "type": "message",
                "role": "user",
                "cwd": "e:\\other\\Project",
                "content": [{"type": "input_text", "text": "x"}],
            }
        ],
    )

    # Only the matching project is returned.
    assert len(find_codebuddy_sessions("E:/demo/CodeAgent", home=home)) == 1
    # Omitting the project path returns both sessions.
    assert len(find_codebuddy_sessions(home=home)) == 2


def test_find_codebuddy_sessions_missing_home_returns_empty(tmp_path: Path) -> None:
    # With an empty (non-existent) home there is nothing to scan: no sessions.
    assert find_codebuddy_sessions(home=tmp_path) == []

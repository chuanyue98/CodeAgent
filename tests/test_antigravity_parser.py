"""Tests for Antigravity session parser, writer, and session finder integration."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from core.session_history.models import (
    EngineType,
    ToolCallSummary,
    UnifiedMessage,
    UnifiedSession,
)
from core.session_history.parsers import (
    find_antigravity_sessions,
    parse_antigravity_session,
)
from core.session_history.session_finder import find_all_sessions
from core.session_history.writers import write_session
from core.session_history.writers.antigravity_writer import write_antigravity_session


def _create_mock_antigravity_env(
    base_dir: Path,
    session_id: str,
    project_path: str,
    title: str = "Test Session Title",
) -> Path:
    """Creates a mock Antigravity CLI home environment with DB and transcript."""
    cli_dir = base_dir / ".gemini" / "antigravity-cli"
    brain_dir = cli_dir / "brain" / session_id / ".system_generated" / "logs"
    brain_dir.mkdir(parents=True, exist_ok=True)

    # 1. Create transcript.jsonl
    transcript_file = brain_dir / "transcript.jsonl"
    lines = [
        json.dumps(
            {
                "step_index": 1,
                "source": "USER_EXPLICIT",
                "type": "USER_INPUT",
                "status": "DONE",
                "created_at": "2026-07-14T03:00:00Z",
                "content": (
                    "<USER_REQUEST>\n帮我查看端口\n</USER_REQUEST>\n"
                    "<ADDITIONAL_METADATA>\ntime: 2026-07-14\n</ADDITIONAL_METADATA>"
                ),
            }
        ),
        json.dumps(
            {
                "step_index": 2,
                "source": "MODEL",
                "type": "PLANNER_RESPONSE",
                "status": "DONE",
                "created_at": "2026-07-14T03:01:00Z",
                "content": "我将为您执行命令查看端口。",
                "tool_calls": [
                    {
                        "name": "run_command",
                        "args": {
                            "CommandLine": "netstat -tuln",
                            "toolAction": "Checking ports",
                        },
                    }
                ],
            }
        ),
        json.dumps(
            {
                "step_index": 3,
                "source": "USER_EXPLICIT",
                "type": "USER_INPUT",
                "status": "DONE",
                "created_at": "2026-07-14T03:02:00Z",
                "content": "再帮我修改配置",
            }
        ),
        json.dumps(
            {
                "step_index": 4,
                "source": "MODEL",
                "type": "PLANNER_RESPONSE",
                "status": "DONE",
                "created_at": "2026-07-14T03:03:00Z",
                "content": "配置已修改完成。",
                "tool_calls": [],
            }
        ),
    ]
    transcript_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # 2. Create conversation_summaries.db
    db_path = cli_dir / "conversation_summaries.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS conversation_summaries (
                conversation_id text PRIMARY KEY,
                title text NOT NULL DEFAULT '',
                preview text NOT NULL DEFAULT '',
                step_count integer NOT NULL DEFAULT 0,
                last_modified_time datetime NOT NULL,
                workspace_uris text NOT NULL,
                status text NOT NULL DEFAULT '',
                source text NOT NULL DEFAULT '',
                project_id text NOT NULL DEFAULT '',
                agent_name text NOT NULL DEFAULT '',
                parent_conversation_id text NOT NULL DEFAULT ''
            )
            """
        )
        norm_proj = project_path.replace("\\", "/")
        if not norm_proj.startswith("/"):
            norm_proj = "/" + norm_proj
        workspace_uris = json.dumps([f"file://{norm_proj}"])
        conn.execute(
            """
            INSERT OR REPLACE INTO conversation_summaries (
                conversation_id, title, preview, step_count, last_modified_time, workspace_uris
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                title,
                "帮我查看端口",
                4,
                "2026-07-14 03:03:00+00:00",
                workspace_uris,
            ),
        )

    return transcript_file


def test_parse_antigravity_session_with_db(tmp_path: Path):
    session_id = "test-session-uuid-1"
    project_path = "/home/cy/github/chuanyue98/CodeAgent"
    transcript_path = _create_mock_antigravity_env(
        tmp_path, session_id, project_path, title="端口查询"
    )

    session = parse_antigravity_session(transcript_path)
    assert session is not None
    assert session.session_id == session_id
    assert session.engine == EngineType.ANTIGRAVITY
    assert session.title == "端口查询"
    assert session.project_path == project_path
    assert session.started_at == "2026-07-14T03:00:00Z"
    assert session.ended_at == "2026-07-14T03:03:00Z"
    assert len(session.messages) == 4

    # Message 1: extracted USER_REQUEST
    assert session.messages[0].role == "user"
    assert session.messages[0].content == "帮我查看端口"
    assert session.messages[0].timestamp == "2026-07-14T03:00:00Z"

    # Message 2: assistant with tool calls
    assert session.messages[1].role == "assistant"
    assert session.messages[1].content == "我将为您执行命令查看端口。"
    assert len(session.messages[1].tool_calls) == 1
    assert session.messages[1].tool_calls[0].name == "run_command"
    assert "netstat -tuln" in session.messages[1].tool_calls[0].args_preview

    # Message 3: plain USER_INPUT without USER_REQUEST tags
    assert session.messages[2].role == "user"
    assert session.messages[2].content == "再帮我修改配置"

    # Message 4: assistant without tool calls
    assert session.messages[3].role == "assistant"
    assert session.messages[3].content == "配置已修改完成。"


def test_parse_antigravity_session_without_db(tmp_path: Path):
    """When DB is absent, parsing still succeeds with fallback metadata."""
    log_dir = tmp_path / "brain" / "no-db-session" / ".system_generated" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    transcript_file = log_dir / "transcript.jsonl"
    transcript_file.write_text(
        json.dumps(
            {
                "step_index": 1,
                "source": "USER_EXPLICIT",
                "type": "USER_INPUT",
                "created_at": "2026-07-14T05:00:00Z",
                "content": "<USER_REQUEST>独立测试</USER_REQUEST>",
            }
        )
        + "\n"
        + json.dumps(
            {
                "step_index": 2,
                "source": "MODEL",
                "type": "PLANNER_RESPONSE",
                "created_at": "2026-07-14T05:01:00Z",
                "content": "收到",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    session = parse_antigravity_session(transcript_file)
    assert session is not None
    assert session.session_id == "no-db-session"
    assert session.engine == EngineType.ANTIGRAVITY
    assert len(session.messages) == 2
    assert session.messages[0].content == "独立测试"
    assert session.messages[1].content == "收到"


def test_find_antigravity_sessions(tmp_path: Path):
    target_project = "/home/cy/github/chuanyue98/CodeAgent"
    other_project = "/home/cy/github/chuanyue98/other-project"

    _create_mock_antigravity_env(
        tmp_path, "sess-target-1", target_project, title="Target 1"
    )
    _create_mock_antigravity_env(
        tmp_path, "sess-target-2", target_project, title="Target 2"
    )
    _create_mock_antigravity_env(
        tmp_path, "sess-other-1", other_project, title="Other 1"
    )

    # Find for target project
    matched = find_antigravity_sessions(target_project, home=tmp_path)
    assert len(matched) == 2
    ids = {s.session_id for s in matched}
    assert ids == {"sess-target-1", "sess-target-2"}

    # Find for other project
    other_matched = find_antigravity_sessions(other_project, home=tmp_path)
    assert len(other_matched) == 1
    assert other_matched[0].session_id == "sess-other-1"

    # Find all (unfiltered)
    all_sessions = find_antigravity_sessions(None, home=tmp_path)
    assert len(all_sessions) == 3


def test_write_antigravity_session_and_roundtrip(tmp_path: Path):
    session = UnifiedSession(
        session_id="written-session-uuid",
        engine=EngineType.ANTIGRAVITY,
        project_path="/home/cy/github/chuanyue98/CodeAgent",
        title="跨引擎写入测试",
        started_at="2026-07-14T10:00:00Z",
        ended_at="2026-07-14T10:05:00Z",
        messages=[
            UnifiedMessage(
                role="user",
                content="测试写入",
                timestamp="2026-07-14T10:00:00Z",
            ),
            UnifiedMessage(
                role="assistant",
                content="正在测试写入功能",
                timestamp="2026-07-14T10:01:00Z",
                tool_calls=[
                    ToolCallSummary(
                        name="test_tool",
                        args_preview='{"foo": "bar"}',
                    )
                ],
            ),
        ],
    )

    written_id = write_antigravity_session(session, home=tmp_path)
    assert written_id == "written-session-uuid"

    expected_file = (
        tmp_path
        / ".gemini"
        / "antigravity-cli"
        / "brain"
        / "written-session-uuid"
        / ".system_generated"
        / "logs"
        / "transcript.jsonl"
    )
    assert expected_file.exists()

    # Read back
    parsed = parse_antigravity_session(expected_file)
    assert parsed is not None
    assert parsed.session_id == "written-session-uuid"
    assert len(parsed.messages) == 2
    assert parsed.messages[0].role == "user"
    assert parsed.messages[0].content == "测试写入"
    assert parsed.messages[1].role == "assistant"
    assert parsed.messages[1].content == "正在测试写入功能"
    assert len(parsed.messages[1].tool_calls) == 1
    assert parsed.messages[1].tool_calls[0].name == "test_tool"


def test_write_session_dispatcher_antigravity(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    session = UnifiedSession(
        session_id="dispatcher-sess-1",
        engine=EngineType.ANTIGRAVITY,
        project_path="/home/cy/github/chuanyue98/CodeAgent",
        messages=[
            UnifiedMessage(role="user", content="通过调度器写入"),
            UnifiedMessage(role="assistant", content="调度成功"),
        ],
    )
    res_id = write_session(session, "antigravity")
    assert res_id == "dispatcher-sess-1"


def test_session_finder_find_all_sessions_includes_antigravity(tmp_path: Path):
    project = "/home/cy/github/chuanyue98/CodeAgent"
    _create_mock_antigravity_env(
        tmp_path, "finder-sess-1", project, title="Finder Antigravity Session"
    )

    sessions = find_all_sessions(project, home=tmp_path, engine="antigravity")
    assert len(sessions) == 1
    assert sessions[0].session_id == "finder-sess-1"
    assert sessions[0].engine == EngineType.ANTIGRAVITY

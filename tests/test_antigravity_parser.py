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
from core.session_history.parsers.antigravity_parser import (
    _clean_title,
    _find_repo_root,
    _is_valid_project_path,
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

    # agy --conversation resolves via conversations/<sid>.db, not the transcript.
    conv_db = (
        tmp_path / ".gemini" / "antigravity-cli" / "conversations"
        / "written-session-uuid.db"
    )
    assert conv_db.exists()
    with sqlite3.connect(conv_db) as conn:
        meta = conn.execute(
            "SELECT cascade_id, trajectory_type, source FROM trajectory_meta"
        ).fetchall()
        assert len(meta) == 1
        assert meta[0][0] == "written-session-uuid"
        assert meta[0][1] == 4
        assert meta[0][2] == 17

        steps = conn.execute(
            "SELECT idx, step_type, status FROM steps ORDER BY idx"
        ).fetchall()
        assert steps == [(0, 14, 3), (1, 15, 3)]
        # Protobuf payloads must be non-empty blobs.
        for (payload,) in conn.execute("SELECT step_payload FROM steps"):
            assert payload and len(payload) > 0

    # Summary row must exist with last_user_input_time (NOT NULL, no default).
    summary_db = tmp_path / ".gemini" / "antigravity-cli" / "conversation_summaries.db"
    assert summary_db.exists()
    with sqlite3.connect(summary_db) as conn:
        rows = conn.execute(
            "SELECT title, last_user_input_time FROM conversation_summaries "
            "WHERE conversation_id = ?",
            ("written-session-uuid",),
        ).fetchall()
        assert len(rows) == 1
        assert rows[0][0] == "跨引擎写入测试"
        assert rows[0][1]  # non-empty timestamp


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


def test_antigravity_find_repo_root(tmp_path: Path):
    repo = tmp_path / "my_project"
    sub = repo / "core" / "services"
    sub.mkdir(parents=True)
    git_dir = repo / ".git"
    git_dir.mkdir()

    # Subdirectory resolves to git repo root
    assert _find_repo_root(str(sub)) == str(repo)

    # Package root without .git but with pyproject.toml
    py_project = tmp_path / "python_lib"
    py_sub = py_project / "src" / "pkg"
    py_sub.mkdir(parents=True)
    (py_project / "pyproject.toml").write_text("[project]\nname='pkg'\n")
    assert _find_repo_root(str(py_sub)) == str(py_project)

    # Path without markers returns itself
    plain_dir = tmp_path / "plain_dir"
    plain_dir.mkdir()
    assert _find_repo_root(str(plain_dir)) == str(plain_dir)


def test_antigravity_is_valid_project_path():
    assert _is_valid_project_path("/home/cy/github/chuanyue98/CodeAgent")
    assert _is_valid_project_path('"/home/cy/github/chuanyue98/CodeAgent"')
    assert _is_valid_project_path("C:/Users/name/repo")
    assert not _is_valid_project_path("")
    assert not _is_valid_project_path("relative/path")
    assert not _is_valid_project_path("/home/cy/.gemini/antigravity-cli")
    assert not _is_valid_project_path("/tmp/scratch")


def test_antigravity_clean_title():
    prompt = (
        "<USER_REQUEST>\n你是 Task 1 实现者。请按以下流程完成 Task 1：\n</USER_REQUEST>"
    )
    assert _clean_title(prompt) == "Task 1 实现者"

    prompt_colon = "你是 Codebase Researcher: 请分析项目结构"
    assert _clean_title(prompt_colon) == "Codebase Researcher"

    normal_req = "<USER_REQUEST>\n帮我查看系统端口占用情况\n</USER_REQUEST>"
    assert _clean_title(normal_req) == "帮我查看系统端口占用情况"

    markdown_heading = "### 1. 任务说明\n请执行测试"
    assert _clean_title(markdown_heading) == "任务说明"


def test_antigravity_subagent_role_title_extraction(tmp_path: Path):
    # Session where DB has generic 'New Session' but transcript contains subagent prompt
    sub_session_id = "subagent-session-uuid"
    cli_dir = tmp_path / ".gemini" / "antigravity-cli"
    brain_dir = cli_dir / "brain" / sub_session_id / ".system_generated" / "logs"
    brain_dir.mkdir(parents=True, exist_ok=True)

    transcript = brain_dir / "transcript.jsonl"
    transcript.write_text(
        json.dumps(
            {
                "step_index": 1,
                "source": "USER_EXPLICIT",
                "type": "USER_INPUT",
                "status": "DONE",
                "created_at": "2026-07-14T03:00:00Z",
                "content": "<USER_REQUEST>\n你是 Task 3 实现者。请按以下流程完成 Task 3：\n</USER_REQUEST>",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    db_path = cli_dir / "conversation_summaries.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS conversation_summaries (
                conversation_id text PRIMARY KEY,
                title text,
                created_at text,
                updated_at text
            )
            """
        )
        conn.execute(
            "INSERT INTO conversation_summaries VALUES (?, ?, ?, ?)",
            (
                sub_session_id,
                "New Session",
                "2026-07-14T03:00:00Z",
                "2026-07-14T03:01:00Z",
            ),
        )

    sessions = find_antigravity_sessions(home=tmp_path)
    assert len(sessions) == 1
    assert sessions[0].title == "Task 3 实现者"


def test_antigravity_model_extraction_from_settings(tmp_path: Path):
    session_id = "test-model-settings-uuid"
    cli_dir = tmp_path / ".gemini" / "antigravity-cli"
    brain_dir = cli_dir / "brain" / session_id / ".system_generated" / "logs"
    brain_dir.mkdir(parents=True, exist_ok=True)

    # Write settings.json
    (cli_dir / "settings.json").write_text(
        json.dumps({"model": "gemini-3-pro"}), encoding="utf-8"
    )

    transcript = brain_dir / "transcript.jsonl"
    transcript.write_text(
        json.dumps(
            {
                "step_index": 1,
                "source": "USER_EXPLICIT",
                "type": "USER_INPUT",
                "status": "DONE",
                "created_at": "2026-07-14T03:00:00Z",
                "content": "<USER_REQUEST>你好</USER_REQUEST>",
            }
        )
        + "\n"
        + json.dumps(
            {
                "step_index": 2,
                "source": "MODEL",
                "type": "PLANNER_RESPONSE",
                "status": "DONE",
                "created_at": "2026-07-14T03:01:00Z",
                "content": "你好！有什么我可以帮你的？",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    session = parse_antigravity_session(transcript)
    assert session is not None
    assert session.model == "gemini-3-pro"
    assert session.messages[1].model == "gemini-3-pro"


def test_antigravity_model_extraction_from_transcript(tmp_path: Path):
    session_id = "test-model-transcript-uuid"
    cli_dir = tmp_path / ".gemini" / "antigravity-cli"
    brain_dir = cli_dir / "brain" / session_id / ".system_generated" / "logs"
    brain_dir.mkdir(parents=True, exist_ok=True)

    transcript = brain_dir / "transcript.jsonl"
    transcript.write_text(
        json.dumps(
            {
                "step_index": 1,
                "source": "USER_EXPLICIT",
                "type": "USER_INPUT",
                "status": "DONE",
                "created_at": "2026-07-14T03:00:00Z",
                "content": (
                    "<USER_REQUEST>测试模型提取</USER_REQUEST>\n"
                    "<USER_SETTINGS_CHANGE>\n"
                    "The user changed setting `Model Selection` from None to Gemini 3.8 Flash (Medium).\n"
                    "</USER_SETTINGS_CHANGE>"
                ),
            }
        )
        + "\n"
        + json.dumps(
            {
                "step_index": 2,
                "source": "MODEL",
                "type": "PLANNER_RESPONSE",
                "status": "DONE",
                "created_at": "2026-07-14T03:01:00Z",
                "content": "已切换并识别。",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    session = parse_antigravity_session(transcript)
    assert session is not None
    assert session.model == "gemini-3.8-flash"
    assert session.messages[1].model == "gemini-3.8-flash"


def test_antigravity_subagent_lineage_and_parent_session(tmp_path: Path):
    """Verifies that subagents spawned via invoke_subagent are correctly linked to parent."""
    from core.analytics.collectors.antigravity_collector import scan_antigravity_usage
    from core.session_history.parsers.antigravity_parser import antigravity_lineage

    cli_dir = tmp_path / ".gemini" / "antigravity-cli"
    parent_id = "parent-uuid-1"
    child1_id = "child-uuid-1"
    child2_id = "child-uuid-2"
    project_path = "/workspace/myproject"

    # 1. Create parent session
    p_log = cli_dir / "brain" / parent_id / ".system_generated" / "logs"
    p_log.mkdir(parents=True, exist_ok=True)
    p_transcript = p_log / "transcript.jsonl"
    p_lines = [
        json.dumps(
            {
                "step_index": 1,
                "source": "USER_EXPLICIT",
                "type": "USER_INPUT",
                "status": "DONE",
                "created_at": "2026-09-12T01:00:00Z",
                "content": f"<USER_REQUEST>\n开始重构\n{project_path} -> myproject\n</USER_REQUEST>",
            }
        ),
        json.dumps(
            {
                "step_index": 2,
                "source": "MODEL",
                "type": "PLANNER_RESPONSE",
                "status": "DONE",
                "created_at": "2026-09-12T01:01:00Z",
                "content": "Dispatching subagents",
                "tool_calls": [
                    {
                        "name": "invoke_subagent",
                        "args": {
                            "Subagents": [
                                {
                                    "Model": "flash",
                                    "Role": "Reviewer Subagent",
                                    "Prompt": "You are reviewing Task 1 implementation.",
                                },
                                {
                                    "Model": "flash",
                                    "Prompt": "You are implementing Task 2 of the implementation plan.",
                                },
                            ],
                            "toolAction": "Dispatch Task 2 Implementer",
                        },
                    }
                ],
            }
        ),
        json.dumps(
            {
                "step_index": 3,
                "source": "MODEL",
                "type": "INVOKE_SUBAGENT",
                "status": "DONE",
                "created_at": "2026-09-12T01:01:05Z",
                "content": (
                    "Created the following subagents:\n"
                    f'{{\n  "conversationId": "{child1_id}"\n}}\n'
                    f'{{\n  "conversationId": "{child2_id}"\n}}'
                ),
            }
        ),
    ]
    p_transcript.write_text("\n".join(p_lines) + "\n", encoding="utf-8")

    # 2. Create child 1 session (has send_message back to parent)
    c1_log = cli_dir / "brain" / child1_id / ".system_generated" / "logs"
    c1_log.mkdir(parents=True, exist_ok=True)
    c1_transcript = c1_log / "transcript.jsonl"
    c1_lines = [
        json.dumps(
            {
                "step_index": 1,
                "source": "USER_EXPLICIT",
                "type": "USER_INPUT",
                "status": "DONE",
                "created_at": "2026-09-12T01:01:10Z",
                "content": "<USER_REQUEST>You are reviewing Task 1 implementation.</USER_REQUEST>",
            }
        ),
        json.dumps(
            {
                "step_index": 2,
                "source": "MODEL",
                "type": "PLANNER_RESPONSE",
                "status": "DONE",
                "created_at": "2026-09-12T01:02:00Z",
                "content": "Review complete.",
                "tool_calls": [
                    {
                        "name": "send_message",
                        "args": {
                            "Recipient": parent_id,
                            "Message": "All checks passed.",
                        },
                    }
                ],
            }
        ),
    ]
    c1_transcript.write_text("\n".join(c1_lines) + "\n", encoding="utf-8")

    # 3. Create child 2 session (no send_message)
    c2_log = cli_dir / "brain" / child2_id / ".system_generated" / "logs"
    c2_log.mkdir(parents=True, exist_ok=True)
    c2_transcript = c2_log / "transcript.jsonl"
    c2_lines = [
        json.dumps(
            {
                "step_index": 1,
                "source": "USER_EXPLICIT",
                "type": "USER_INPUT",
                "status": "DONE",
                "created_at": "2026-09-12T01:01:15Z",
                "content": "<USER_REQUEST>You are implementing Task 2 of the implementation plan.</USER_REQUEST>",
            }
        ),
        json.dumps(
            {
                "step_index": 2,
                "source": "MODEL",
                "type": "PLANNER_RESPONSE",
                "status": "DONE",
                "created_at": "2026-09-12T01:03:00Z",
                "content": "Implementation complete.",
                "tool_calls": [],
            }
        ),
    ]
    c2_transcript.write_text("\n".join(c2_lines) + "\n", encoding="utf-8")

    # Test antigravity_lineage
    lineage = antigravity_lineage(home=tmp_path)
    assert child1_id in lineage
    assert lineage[child1_id] == (parent_id, "Reviewer Subagent")
    assert child2_id in lineage
    assert lineage[child2_id] == (parent_id, "Dispatch Task 2 Implementer")

    # Test find_antigravity_sessions
    sessions = find_antigravity_sessions(home=tmp_path)
    assert len(sessions) == 3
    by_id = {s.session_id: s for s in sessions}

    c1 = by_id[child1_id]
    assert c1.parent_session_id == parent_id
    assert c1.agent == "Reviewer Subagent"
    assert c1.title == "Reviewer Subagent"
    assert c1.project_path == project_path

    c2 = by_id[child2_id]
    assert c2.parent_session_id == parent_id
    assert c2.agent == "Dispatch Task 2 Implementer"
    assert c2.title == "Dispatch Task 2 Implementer"
    assert c2.project_path == project_path

    # Test scan_antigravity_usage
    usage_entries = scan_antigravity_usage(home=tmp_path)
    c1_usage = [e for e in usage_entries if e.session_id == child1_id]
    assert len(c1_usage) > 0
    assert c1_usage[0].parent_session_id == parent_id
    assert c1_usage[0].agent == "Reviewer Subagent"
    assert c1_usage[0].project_path == project_path

    c2_usage = [e for e in usage_entries if e.session_id == child2_id]
    assert len(c2_usage) > 0
    assert c2_usage[0].parent_session_id == parent_id
    assert c2_usage[0].agent == "Dispatch Task 2 Implementer"
    assert c2_usage[0].project_path == project_path

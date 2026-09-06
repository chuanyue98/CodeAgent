"""Tests for the Freebuff (免费版 CLI) session history parser.

Fixture mirrors the real on-disk format verified under
``~/.config/manicode/projects/<repo>/chats/<ISO-时间戳>/`` (freebuff 0.0.168):
``chat-messages.json`` is a JSON *array*, ``chat-meta.json`` holds the first
prompt, and ``run-state.json`` records the live project root / agent template.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.session_history.parsers.freebuff_parser import (
    _dir_name_to_iso,
    _ts_from_message_id,
    find_freebuff_sessions,
    parse_freebuff_session,
)

# Mirrors a real "你浏览下我们项目"-style conversation: a user turn, then an
# ai turn whose blocks carry reasoning (dropped), visible text and a tool call.
SAMPLE_MESSAGES = [
    {
        "id": "divider-1786515102015",
        "variant": "ai",
        "content": "",
        "blocks": [{"type": "mode-divider", "mode": "LITE"}],
        "timestamp": "02:11 PM",
    },
    {
        "id": "user-1786515103000",
        "variant": "user",
        "content": "你浏览下我们项目",
        "timestamp": "02:11 PM",
    },
    {
        "id": "ai-1786515104000-581683dea203d",
        "variant": "ai",
        "content": "",
        "timestamp": "02:11 PM",
        "blocks": [
            {
                "type": "text",
                "content": "The user wants a project overview.",
                "textType": "reasoning",
                "thinkingId": "thinking-1",
            },
            {
                "type": "text",
                "content": "好的，我先看一下项目结构。",
                "textType": "text",
            },
            {
                "type": "tool",
                "toolCallId": "9JkwIwnA8mo",
                "toolName": "list_directory",
                "input": {"path": "."},
                "agentId": "main-agent",
                "includeToolCall": True,
                "output": "core/\nengines/\nweb/",
            },
        ],
    },
]

CHAT_DIR_NAME = "2026-08-12T05-10-04.784Z"


def _write_chat(
    projects_root: Path,
    repo_name: str,
    chat_dir_name: str = CHAT_DIR_NAME,
    messages: list | None = None,
    project_root: str = "/home/cy/work/CodeAgent",
    agent_type: str = "base2-free-deepseek-flash",
    first_prompt: str = "你浏览下我们项目",
    include_state: bool = True,
) -> Path:
    """Writes one Freebuff conversation under ``projects_root`` and returns
    the ``chat-messages.json`` path."""
    chat_dir = projects_root / repo_name / "chats" / chat_dir_name
    chat_dir.mkdir(parents=True, exist_ok=True)
    transcript = chat_dir / "chat-messages.json"
    transcript.write_text(
        json.dumps(messages if messages is not None else SAMPLE_MESSAGES),
        encoding="utf-8",
    )
    (chat_dir / "chat-meta.json").write_text(
        json.dumps({"messageCount": 3, "firstPrompt": first_prompt}),
        encoding="utf-8",
    )
    if include_state:
        (chat_dir / "run-state.json").write_text(
            json.dumps(
                {
                    "sessionState": {
                        "fileContext": {
                            "projectRoot": project_root,
                            "cwd": project_root,
                        },
                        "mainAgentState": {"agentId": "main-agent", "agentType": agent_type},
                    },
                    "output": {"type": "ok"},
                }
            ),
            encoding="utf-8",
        )
    return transcript


def test_dir_name_to_iso() -> None:
    # Freebuff separates clock fields with dashes inside the chat dir name.
    assert _dir_name_to_iso("2026-08-12T05-10-04.784Z") == "2026-08-12T05:10:04.784Z"
    # Anything not matching is returned unchanged (never mangled).
    assert _dir_name_to_iso("not-a-timestamp") == "not-a-timestamp"


def test_message_id_epoch_extraction() -> None:
    assert _ts_from_message_id("user-1786515234478") == "2026-08-12T06:13:54.478Z"
    # ai ids carry a random suffix after the epoch.
    assert _ts_from_message_id("ai-1786515102492-581683dea203d") == (
        "2026-08-12T06:11:42.492Z"
    )
    assert _ts_from_message_id("no-digits") == ""


def test_wrong_filename_returns_none(tmp_path: Path) -> None:
    assert parse_freebuff_session(Path("/no/such/chat-messages.json")) is None
    not_transcript = tmp_path / "chat-messages.json"
    not_transcript.write_text("not json", encoding="utf-8")
    assert parse_freebuff_session(not_transcript) is None
    other = tmp_path / "chat-meta.json"
    other.write_text("{}", encoding="utf-8")
    assert parse_freebuff_session(other) is None


def test_user_assistant_extraction_and_tool_summary(home: Path) -> None:
    transcript = _write_chat(home / ".config" / "manicode" / "projects", "CodeAgent")
    session = parse_freebuff_session(transcript)

    assert session is not None
    assert session.engine.value == "freebuff"
    assert session.session_id == CHAT_DIR_NAME
    assert session.title == "你浏览下我们项目"
    # run-state's agent template is surfaced as the model best-effort.
    assert session.model == "base2-free-deepseek-flash"
    assert session.project_path == "/home/cy/work/CodeAgent"

    # reasoning + mode-divider rows are dropped; user + assistant remain.
    assert len(session.messages) == 2
    user, assistant = session.messages
    assert user.role == "user"
    assert user.content == "你浏览下我们项目"
    assert assistant.role == "assistant"
    assert assistant.content == "好的，我先看一下项目结构。"
    assert len(assistant.tool_calls) == 1
    tc = assistant.tool_calls[0]
    assert tc.name == "list_directory"
    assert tc.args_preview == '{"path": "."}'
    assert tc.result_preview == "core/\nengines/\nweb/"

    # Timestamps come from the epoch embedded in message ids.
    assert user.timestamp == "2026-08-12T06:11:43.000Z"
    assert assistant.timestamp == "2026-08-12T06:11:44.000Z"
    assert session.started_at == "2026-08-12T06:11:43.000Z"
    assert session.ended_at == "2026-08-12T06:11:44.000Z"


def test_ai_message_with_only_reasoning_is_skipped(home: Path) -> None:
    messages = [
        {
            "id": "user-1786515103000",
            "variant": "user",
            "content": "hi",
            "timestamp": "02:11 PM",
        },
        {
            "id": "ai-1786515104000-x",
            "variant": "ai",
            "content": "",
            "timestamp": "02:11 PM",
            "blocks": [
                {
                    "type": "text",
                    "content": "internal reasoning only",
                    "textType": "reasoning",
                }
            ],
        },
    ]
    projects = home / ".config" / "manicode" / "projects"
    transcript = _write_chat(projects, "CodeAgent", messages=messages)
    session = parse_freebuff_session(transcript)

    assert session is not None
    assert len(session.messages) == 1
    assert session.messages[0].role == "user"


def test_no_run_state_falls_back_to_repo_name(home: Path) -> None:
    projects = home / ".config" / "manicode" / "projects"
    transcript = _write_chat(projects, "CodeAgent", include_state=False)
    session = parse_freebuff_session(transcript)

    assert session is not None
    assert session.project_path == "CodeAgent"
    assert session.model == ""


def test_crashed_leftover_dir_is_skipped(home: Path) -> None:
    projects = home / ".config" / "manicode" / "projects"
    _write_chat(projects, "CodeAgent")
    # A killed run may leave only log.jsonl behind -- nothing to parse.
    leftover = projects / "CodeAgent" / "chats" / "2026-08-12T08-15-17.205Z"
    leftover.mkdir(parents=True)
    (leftover / "log.jsonl").write_text("{}\n", encoding="utf-8")

    sessions = find_freebuff_sessions(home=home)
    assert len(sessions) == 1


def test_find_freebuff_sessions_matches_repo_name(home: Path) -> None:
    projects = home / ".config" / "manicode" / "projects"
    _write_chat(projects, "CodeAgent", project_root="/home/cy/a/CodeAgent")
    # 老会话用无数字 id 的消息，时间戳回退到目录名，保证两个会话的
    # started_at 可排序且后者更旧。
    _write_chat(
        projects,
        "OtherRepo",
        chat_dir_name="2026-08-11T05-10-04.784Z",
        project_root="/home/cy/elsewhere/OtherRepo",
        messages=[
            {
                "id": "user-old",
                "variant": "user",
                "content": "旧会话",
                "timestamp": "",
                "blocks": [],
            }
        ],
        first_prompt="旧会话",
    )

    # Filtering by a local checkout matches the git repo name.
    sessions = find_freebuff_sessions("/home/cy/a/CodeAgent", home=home)
    assert len(sessions) == 1
    assert sessions[0].project_path == "/home/cy/a/CodeAgent"
    assert sessions[0].session_id == CHAT_DIR_NAME

    # Unfiltered returns everything, newest first.
    both = find_freebuff_sessions(home=home)
    assert len(both) == 2
    assert both[0].session_id == CHAT_DIR_NAME  # newest chat first


def test_find_freebuff_sessions_missing_home_returns_empty(tmp_path: Path) -> None:
    assert find_freebuff_sessions(home=tmp_path) == []


def test_write_session_to_freebuff_is_reserved(home: Path) -> None:
    """转换“到”freebuff 是预留项：writer 明确失败并解释原因，而不是静默
    写一份 freebuff 无法 --continue 认领的孤儿 transcript。"""
    from core.session_history.models import EngineType, UnifiedSession
    from core.session_history.writers import write_session

    session = UnifiedSession(engine=EngineType.FREEBUFF, project_path="/work/CodeAgent")
    with pytest.raises(NotImplementedError, match="转换到 freebuff 暂不支持"):
        write_session(session, "freebuff")

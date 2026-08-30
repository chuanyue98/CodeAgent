"""A subagent run's own transcript opens with the whole prompt it was handed,
so its identity -- who ran it, and what for -- comes from two places the
launcher and the run each record structurally."""

from __future__ import annotations

import json
from pathlib import Path

from core.session_history.parse_cache import clear_parse_cache
from core.session_history.parsers.claude_parser import find_claude_sessions


def _write(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )


def _project(home: Path) -> Path:
    return home / ".claude" / "projects" / "-home-user-app"


def _parent_rows(agent_id: str, description: str) -> list[dict]:
    return [
        {
            "type": "user",
            "message": {"role": "user", "content": "review the repo"},
            "timestamp": "2026-08-01T10:00:00Z",
            "cwd": "/home/user/app",
        },
        {
            "type": "user",
            "message": {
                "role": "user",
                "content": [{"type": "tool_result", "tool_use_id": "toolu_1"}],
            },
            "timestamp": "2026-08-01T10:01:00Z",
            "cwd": "/home/user/app",
            "toolUseResult": {
                "isAsync": True,
                "status": "async_launched",
                "agentId": agent_id,
                "description": description,
                "resolvedModel": "claude-opus-5",
            },
        },
    ]


def _subagent_rows(agent: str, prompt: str) -> list[dict]:
    return [
        {
            "type": "user",
            "message": {"role": "user", "content": prompt},
            "timestamp": "2026-08-01T10:02:00Z",
            "cwd": "/home/user/app",
            "sessionId": "parent-session",
            "isSidechain": True,
            "attributionAgent": agent,
        },
    ]


def test_a_subagent_run_is_named_by_its_launcher(tmp_path):
    project = _project(tmp_path)
    _write(
        project / "parent-session.jsonl", _parent_rows("abc123", "代码质量与安全审阅")
    )
    _write(
        project / "parent-session" / "subagents" / "agent-abc123.jsonl",
        _subagent_rows("general-purpose", "你是资深安全与代码质量审计工程师，" * 20),
    )
    clear_parse_cache()

    sessions = {s.session_id: s for s in find_claude_sessions(home=tmp_path)}

    child = sessions["agent-abc123"]
    assert child.parent_session_id == "parent-session"
    assert child.agent == "general-purpose"
    # Not the prompt: four subagents of one session would all read the same.
    assert child.title == "代码质量与安全审阅"


def test_a_subagent_run_whose_launch_was_not_recorded_keeps_its_prompt(tmp_path):
    project = _project(tmp_path)
    _write(
        project / "parent-session.jsonl",
        [
            {
                "type": "user",
                "message": {"role": "user", "content": "review the repo"},
                "timestamp": "2026-08-01T10:00:00Z",
                "cwd": "/home/user/app",
            }
        ],
    )
    _write(
        project / "parent-session" / "subagents" / "agent-abc123.jsonl",
        _subagent_rows("Explore", "go read the frontend"),
    )
    clear_parse_cache()

    sessions = {s.session_id: s for s in find_claude_sessions(home=tmp_path)}

    child = sessions["agent-abc123"]
    assert child.agent == "Explore"
    assert child.title == ""
    assert child.to_summary_dict()["title"] == "go read the frontend"

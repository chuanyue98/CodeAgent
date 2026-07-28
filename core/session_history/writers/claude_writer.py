"""Writer for converting UnifiedSession to Claude Code JSONL format.

Writes to: ~/.claude/projects/<encoded_project_path>/<new_uuid>.jsonl

Each line is a JSON object matching Claude's native session format.
Only user and assistant messages are written; tool calls are embedded
in assistant message content blocks.
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from core.utils.atomic_write import atomic_write

if TYPE_CHECKING:
    from core.session_history.models import UnifiedSession


def _encode_project_path(path: str) -> str:
    """Encodes a file path into Claude's dash-encoded directory name format.

    ``E:/demo/CodeAgent`` → ``E--demo-CodeAgent``

    Args:
        path: The file path to encode.

    Returns:
        str: The encoded directory name.
    """
    path = path.replace("\\", "/")
    m = re.match(r"^([A-Za-z]):/(.*)$", path)
    if m:
        drive, rest = m.groups()
        return f"{drive}--{rest.replace('/', '-')}"
    return path.replace("/", "-")


def _now_iso() -> str:
    """Returns the current UTC time as an ISO 8601 string."""
    return datetime.now(tz=UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def write_claude_session(session: UnifiedSession) -> str:
    """Writes a UnifiedSession as a Claude Code JSONL session file.

    Creates a new session file in ``~/.claude/projects/<encoded_path>/``
    with a new UUID.  The file follows Claude's native JSONL format so
    ``claude -r <id>`` can resume it.

    Args:
        session: The UnifiedSession to convert.

    Returns:
        str: The new session UUID (file stem).
    """
    new_session_id = str(uuid.uuid4())
    project_dir_name = _encode_project_path(session.project_path)
    claude_projects = Path.home() / ".claude" / "projects" / project_dir_name
    claude_projects.mkdir(parents=True, exist_ok=True)

    file_path = claude_projects / f"{new_session_id}.jsonl"
    cwd = (
        session.project_path.replace("/", "\\")
        if re.match(r"^[A-Za-z]:", session.project_path)
        else session.project_path
    )

    lines: list[str] = []
    now = _now_iso()

    # Write messages as JSONL rows
    prev_uuid = None

    for msg in session.messages:
        msg_uuid = str(uuid.uuid4())

        if msg.role == "user":
            row = {
                "parentUuid": prev_uuid,
                "isSidechain": False,
                "type": "user",
                "message": {
                    "role": "user",
                    "content": msg.content,
                },
                "uuid": msg_uuid,
                "timestamp": msg.timestamp or now,
                "permissionMode": "default",
                "origin": {"kind": "human"},
                "promptSource": "typed",
                "userType": "external",
                "entrypoint": "cli",
                "cwd": cwd,
                "sessionId": new_session_id,
                "version": "2.1.0",
            }
            lines.append(json.dumps(row, ensure_ascii=False))
            prev_uuid = msg_uuid

        elif msg.role == "assistant":
            # Build content blocks: text + tool_use
            content_blocks = []
            if msg.content:
                content_blocks.append({"type": "text", "text": msg.content})
            for tc in msg.tool_calls:
                try:
                    input_obj: Any = (
                        json.loads(tc.args_preview) if tc.args_preview else {}
                    )
                except (json.JSONDecodeError, TypeError):
                    input_obj = {}
                content_blocks.append(
                    {
                        "type": "tool_use",
                        "id": f"toolu_{uuid.uuid4().hex[:24]}",
                        "name": tc.name,
                        "input": input_obj,
                    }
                )

            if not content_blocks:
                continue

            message: dict[str, Any] = {
                "model": msg.model or session.model or "claude-sonnet-4-20250514",
                "id": f"msg_{uuid.uuid4().hex[:24]}",
                "type": "message",
                "role": "assistant",
                "content": content_blocks,
                "stop_reason": "end_turn",
                "stop_sequence": None,
                "usage": {
                    "input_tokens": 0,
                    "output_tokens": 0,
                },
            }
            row = {
                "parentUuid": prev_uuid,
                "isSidechain": False,
                "type": "assistant",
                "message": message,
                "uuid": msg_uuid,
                "timestamp": msg.timestamp or now,
                "sessionId": new_session_id,
                "cwd": cwd,
                "version": "2.1.0",
                "entrypoint": "cli",
                "userType": "external",
            }
            lines.append(json.dumps(row, ensure_ascii=False))
            prev_uuid = msg_uuid

    # Write the file atomically to prevent corruption on crash
    atomic_write(file_path, "\n".join(lines) + "\n")
    return new_session_id

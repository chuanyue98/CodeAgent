"""Writer for converting UnifiedSession to Gemini CLI JSONL format.

Writes to: ~/.gemini/tmp/<project_name>/chats/session-<timestamp>-<hash>.jsonl
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TYPE_CHECKING

from core.utils.atomic_write import atomic_write

if TYPE_CHECKING:
    from core.session_history.models import UnifiedSession


def _now_iso() -> str:
    """Returns current UTC time as ISO 8601."""
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def write_gemini_session(session: UnifiedSession) -> str:
    """Writes a UnifiedSession as a Gemini CLI JSONL session file.

    Creates a new session file in ``~/.gemini/tmp/<project>/chats/`` with
    Gemini's native JSONL format.

    Args:
        session: The UnifiedSession to convert.

    Returns:
        str: The new session ID.
    """
    new_session_id = str(uuid.uuid4())
    now = _now_iso()

    # Gemini uses the project folder name (last component of path)
    project_name = Path(session.project_path).name

    chats_dir = Path.home() / ".gemini" / "tmp" / project_name / "chats"
    chats_dir.mkdir(parents=True, exist_ok=True)

    # Generate filename: session-YYYY-MM-DDTHH-MM-<8hexhash>.jsonl
    time_str = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H-%M")
    short_hash = hashlib.md5(new_session_id.encode()).hexdigest()[:8]
    filename = f"session-{time_str}-{short_hash}.jsonl"
    file_path = chats_dir / filename

    lines: list[str] = []

    # Line 1: session metadata
    meta = {
        "sessionId": new_session_id,
        "projectHash": hashlib.sha256(session.project_path.encode()).hexdigest(),
        "startTime": now,
        "lastUpdated": now,
        "kind": "main",
    }
    lines.append(json.dumps(meta, ensure_ascii=False))

    # Write messages
    for msg in session.messages:
        msg_row: dict[str, Any]
        if msg.role == "user":
            msg_row = {
                "$set": {
                    "messages": [
                        {
                            "id": str(uuid.uuid4()),
                            "timestamp": msg.timestamp or now,
                            "type": "user",
                            "content": [{"text": msg.content}],
                        }
                    ],
                    "lastUpdated": msg.timestamp or now,
                }
            }
            lines.append(json.dumps(msg_row, ensure_ascii=False))

        elif msg.role == "assistant":
            tool_calls = []
            for tc in msg.tool_calls:
                try:
                    args_obj = json.loads(tc.args_preview) if tc.args_preview else {}
                except (json.JSONDecodeError, TypeError):
                    args_obj = {}
                tool_calls.append(
                    {
                        "id": f"call_{uuid.uuid4().hex[:24]}",
                        "name": tc.name,
                        "args": args_obj,
                        "result": [
                            {
                                "functionResponse": {
                                    "name": tc.name,
                                    "response": {"output": tc.result_preview},
                                }
                            }
                        ]
                        if tc.result_preview
                        else [],
                        "status": "success" if tc.result_preview else "unknown",
                        "timestamp": msg.timestamp or now,
                    }
                )

            msg_row = {
                "id": str(uuid.uuid4()),
                "timestamp": msg.timestamp or now,
                "type": "gemini",
                "content": msg.content,
                "thoughts": [],
                "tokens": {"input": 0, "output": 0, "total": 0},
                "model": msg.model or session.model or "gemini-2.5-flash",
                "toolCalls": tool_calls,
            }
            lines.append(json.dumps(msg_row, ensure_ascii=False))

    # Write the file atomically to prevent corruption on crash
    atomic_write(file_path, "\n".join(lines) + "\n")
    return new_session_id

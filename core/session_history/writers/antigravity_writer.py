"""Writer for converting UnifiedSession to Antigravity JSONL format.

Writes to:
    ~/.gemini/antigravity-cli/brain/<session_id>/.system_generated/logs/transcript.jsonl
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from core.utils.atomic_write import atomic_write

if TYPE_CHECKING:
    from core.session_history.models import UnifiedSession


def write_antigravity_session(
    session: UnifiedSession, home: Path | None = None
) -> str:
    """Converts a UnifiedSession and writes it to Antigravity native format.

    Args:
        session: The UnifiedSession to write.
        home: Optional home directory override.

    Returns:
        str: The session ID written.
    """
    session_id = session.session_id or str(uuid.uuid4())
    cli_dir = (home or Path.home()) / ".gemini" / "antigravity-cli"
    target_dir = cli_dir / "brain" / session_id / ".system_generated" / "logs"
    target_dir.mkdir(parents=True, exist_ok=True)
    transcript_file = target_dir / "transcript.jsonl"

    now_iso = datetime.now(tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    lines: list[str] = []
    step_index = 1

    for msg in session.messages:
        ts = msg.timestamp or now_iso
        if msg.role == "user":
            row = {
                "step_index": step_index,
                "source": "USER_EXPLICIT",
                "type": "USER_INPUT",
                "status": "DONE",
                "created_at": ts,
                "content": f"<USER_REQUEST>\n{msg.content}\n</USER_REQUEST>",
            }
            lines.append(json.dumps(row, ensure_ascii=False))
            step_index += 1
        elif msg.role == "assistant":
            tool_calls: list[dict[str, Any]] = []
            for tc in msg.tool_calls:
                args: Any = {}
                if tc.args_preview:
                    try:
                        args = json.loads(tc.args_preview)
                    except (json.JSONDecodeError, TypeError):
                        args = {"preview": tc.args_preview}
                tool_calls.append({"name": tc.name, "args": args})

            row = {
                "step_index": step_index,
                "source": "MODEL",
                "type": "PLANNER_RESPONSE",
                "status": "DONE",
                "created_at": ts,
                "content": msg.content,
                "tool_calls": tool_calls,
            }
            lines.append(json.dumps(row, ensure_ascii=False))
            step_index += 1

    content_str = "\n".join(lines) + ("\n" if lines else "")
    atomic_write(transcript_file, content_str)

    # Record into conversation_summaries.db if possible
    db_path = cli_dir / "conversation_summaries.db"
    try:
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
            proj = session.project_path
            if proj:
                norm_proj = proj.replace("\\", "/")
                if not norm_proj.startswith("/"):
                    norm_proj = "/" + norm_proj
                uris_json = json.dumps([f"file://{norm_proj}"])
            else:
                uris_json = "[]"

            db_now = datetime.now(tz=UTC).strftime("%Y-%m-%d %H:%M:%S+00:00")
            conn.execute(
                """
                INSERT OR REPLACE INTO conversation_summaries (
                    conversation_id, title, preview, step_count, last_modified_time, workspace_uris,
                    agent_name, parent_conversation_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    session.title or session.first_user_message or "",
                    session.first_user_message or "",
                    len(session.messages),
                    session.ended_at or db_now,
                    uris_json,
                    session.agent,
                    session.parent_session_id,
                ),
            )
    except Exception:
        pass

    return session_id

"""Writer for converting UnifiedSession to OpenCode SQLite format.

Writes to: ~/.local/share/opencode/opencode.db

Inserts new rows into the ``session``, ``message``, and ``part`` tables
following OpenCode's native schema.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.session_history.models import UnifiedSession


def _now_ms() -> int:
    """Returns current UTC time as Unix milliseconds."""
    return int(datetime.now(tz=timezone.utc).timestamp() * 1000)


def _find_opencode_db() -> Path | None:
    """Locates the OpenCode database file.

    Returns:
        Path to the database, or None if not found.
    """
    candidates = [
        Path.home() / ".local" / "share" / "opencode" / "opencode.db",
        Path.home() / ".opencode" / "opencode.db",
    ]
    for path in candidates:
        if path.exists():
            return path
    return None


def write_opencode_session(session: UnifiedSession) -> str:
    """Writes a UnifiedSession into the OpenCode SQLite database.

    Inserts a new session row and all associated messages and parts.
    The session can be resumed via OpenCode's native session selection.

    Args:
        session: The UnifiedSession to convert.

    Returns:
        str: The new session ID (OpenCode format: ses_<id>).

    Raises:
        FileNotFoundError: If the OpenCode database is not found.
    """
    db_path = _find_opencode_db()
    if not db_path:
        raise FileNotFoundError("OpenCode database not found. Is OpenCode installed?")

    new_session_id = f"ses_{uuid.uuid4().hex[:24]}"
    now_ms = _now_ms()

    # Generate a project ID (deterministic from path, stable across processes)
    project_id = f"pro_{hashlib.sha256(session.project_path.encode()).hexdigest()[:16]}"

    # Model JSON
    model_json = json.dumps(
        {
            "id": session.model or "unknown",
            "providerID": "converted",
        }
    )

    con = sqlite3.connect(str(db_path))

    try:
        # Insert session row
        con.execute(
            """INSERT INTO session (
                id, project_id, parent_id, slug, directory, title, version,
                model, cost, tokens_input, tokens_output, tokens_reasoning,
                tokens_cache_read, tokens_cache_write,
                time_created, time_updated, time_compacting, time_archived,
                workspace_id, path, agent, metadata,
                summary_additions, summary_deletions, summary_files,
                summary_diffs, share_url, permission
            ) VALUES (?, ?, NULL, ?, ?, ?, ?, ?, 0, 0, 0, 0, 0, 0, ?, ?, NULL, NULL, NULL, ?, NULL, '{}', 0, 0, 0, NULL, NULL, NULL)""",
            (
                new_session_id,
                project_id,
                new_session_id[-12:],  # slug
                session.project_path,
                session.title or session.first_user_message[:80] or "Converted session",
                "1.0.0",
                model_json,
                now_ms,  # time_created
                now_ms,  # time_updated
                session.project_path,  # path
            ),
        )

        # Insert messages and parts
        for i, msg in enumerate(session.messages):
            msg_id = f"msg_{uuid.uuid4().hex[:24]}"
            msg_time = now_ms + i * 1000  # stagger timestamps

            # Message data JSON
            msg_data = {
                "parentID": None,
                "role": msg.role,
                "mode": "build",
                "agent": "build",
                "path": {"cwd": session.project_path, "root": session.project_path},
                "cost": 0,
                "tokens": {"total": 0, "input": 0, "output": 0, "reasoning": 0},
                "modelID": session.model or "unknown",
                "providerID": "converted",
                "time": {"created": msg_time, "completed": msg_time + 500},
                "finish": "stop",
            }

            con.execute(
                """INSERT INTO message (id, session_id, time_created, time_updated, data)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    msg_id,
                    new_session_id,
                    msg_time,
                    msg_time,
                    json.dumps(msg_data, ensure_ascii=False),
                ),
            )

            # Insert text part
            if msg.content:
                part_data = {"type": "text", "text": msg.content}
                con.execute(
                    """INSERT INTO part (id, message_id, session_id, time_created, time_updated, data)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (
                        f"prt_{uuid.uuid4().hex[:24]}",
                        msg_id,
                        new_session_id,
                        msg_time,
                        msg_time,
                        json.dumps(part_data, ensure_ascii=False),
                    ),
                )

            # Insert tool call parts
            for tc in msg.tool_calls:
                try:
                    input_obj = json.loads(tc.args_preview) if tc.args_preview else {}
                except (json.JSONDecodeError, TypeError):
                    input_obj = {}

                tool_part = {
                    "type": "tool",
                    "tool": tc.name,
                    "callID": f"call_{uuid.uuid4().hex[:24]}",
                    "state": {
                        "status": "completed" if tc.result_preview else "unknown",
                        "input": input_obj,
                        "output": tc.result_preview or "",
                    },
                }
                con.execute(
                    """INSERT INTO part (id, message_id, session_id, time_created, time_updated, data)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (
                        f"prt_{uuid.uuid4().hex[:24]}",
                        msg_id,
                        new_session_id,
                        msg_time,
                        msg_time,
                        json.dumps(tool_part, ensure_ascii=False),
                    ),
                )

        con.commit()

    finally:
        con.close()

    return new_session_id

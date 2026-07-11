"""Parser for OpenCode session history.

OpenCode stores sessions in a SQLite database at:
    ~/.local/share/opencode/opencode.db

Key tables:
  - ``session``  → session metadata (id, directory, title, model, time_created)
  - ``message``  → messages (id, session_id, time_created, data JSON)
  - ``part``     → message parts (id, message_id, session_id, data JSON)

Message ``data`` contains ``role`` (user/assistant), and parts contain
``type`` (text/reasoning/tool/patch/step-start/step-finish).
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from core.session_history.models import (
    EngineType,
    ToolCallSummary,
    UnifiedMessage,
    UnifiedSession,
)


def _ms_to_iso(ms: int) -> str:
    """Converts a Unix millisecond timestamp to ISO 8601 string.

    Args:
        ms: Timestamp in milliseconds.

    Returns:
        str: ISO 8601 formatted string (UTC).
    """
    if not ms:
        return ""
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%S.000Z"
    )


def _find_opencode_db(home: Optional[Path] = None) -> Optional[Path]:
    """Locates the OpenCode database file.

    Checks common locations including XDG data directory.

    Args:
        home: Optional home directory override.

    Returns:
        Path to the database file, or None if not found.
    """
    candidates = [
        (home or Path.home()) / ".local" / "share" / "opencode" / "opencode.db",
        (home or Path.home()) / ".opencode" / "opencode.db",
    ]
    for path in candidates:
        if path.exists():
            return path
    return None


def parse_opencode_session(session_id: str, db_path: Path) -> Optional[UnifiedSession]:
    """Parses a single OpenCode session from the SQLite database.

    Args:
        session_id: The session ID to parse.
        db_path: Path to the OpenCode SQLite database.

    Returns:
        UnifiedSession if parsing succeeds, None otherwise.
    """
    if not db_path.exists():
        return None

    con = None
    try:
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        con.row_factory = sqlite3.Row

        # Fetch session metadata
        sess_row = con.execute(
            "SELECT id, directory, title, model, time_created, time_updated "
            "FROM session WHERE id = ?",
            (session_id,),
        ).fetchone()

        if not sess_row:
            return None

        project_path = sess_row["directory"] or ""
        title = sess_row["title"] or ""
        started_ms = sess_row["time_created"] or 0
        ended_ms = sess_row["time_updated"] or started_ms

        # Parse model JSON
        model_str = ""
        try:
            model_data = json.loads(sess_row["model"]) if sess_row["model"] else {}
            model_str = model_data.get("id", "") if isinstance(model_data, dict) else ""
        except (json.JSONDecodeError, TypeError):
            model_str = sess_row["model"] or ""

        # Fetch all messages for this session, ordered by time
        msg_rows = con.execute(
            "SELECT id, time_created, data FROM message "
            "WHERE session_id = ? ORDER BY time_created ASC",
            (session_id,),
        ).fetchall()

        messages: list[UnifiedMessage] = []

        for msg_row in msg_rows:
            msg_id = msg_row["id"]
            msg_time_ms = msg_row["time_created"] or 0
            timestamp = _ms_to_iso(msg_time_ms)

            try:
                msg_data = json.loads(msg_row["data"]) if msg_row["data"] else {}
            except (json.JSONDecodeError, TypeError):
                continue

            if not isinstance(msg_data, dict):
                continue

            role = msg_data.get("role", "")
            if role not in ("user", "assistant"):
                continue

            # Fetch parts for this message
            part_rows = con.execute(
                "SELECT data FROM part WHERE message_id = ? ORDER BY time_created ASC",
                (msg_id,),
            ).fetchall()

            text_parts: list[str] = []
            tool_calls: list[ToolCallSummary] = []

            for part_row in part_rows:
                try:
                    part_data = json.loads(part_row["data"]) if part_row["data"] else {}
                except (json.JSONDecodeError, TypeError):
                    continue

                if not isinstance(part_data, dict):
                    continue

                part_type = part_data.get("type", "")

                if part_type == "text":
                    text_parts.append(part_data.get("text", ""))

                elif part_type == "tool":
                    tool_name = part_data.get("tool", "")
                    state = part_data.get("state", {})
                    input_data = state.get("input", {})
                    args_str = (
                        json.dumps(input_data, ensure_ascii=False) if input_data else ""
                    )
                    if len(args_str) > 200:
                        args_str = args_str[:200] + "..."

                    result_preview = ""
                    output = state.get("output", "")
                    if isinstance(output, str):
                        result_preview = output[:200] if len(output) > 200 else output
                    elif isinstance(output, dict):
                        out_str = json.dumps(output, ensure_ascii=False)
                        result_preview = out_str[:200]

                    tool_calls.append(
                        ToolCallSummary(
                            name=tool_name,
                            args_preview=args_str,
                            result_preview=result_preview,
                        )
                    )

            content = "\n".join(text_parts).strip()

            # For user messages, content might be directly in msg_data
            if role == "user" and not content:
                # Some versions store user content directly in message data
                direct_content = msg_data.get("content", "")
                if isinstance(direct_content, str):
                    content = direct_content.strip()
                elif isinstance(direct_content, list):
                    parts = []
                    for block in direct_content:
                        if isinstance(block, dict) and "text" in block:
                            parts.append(block["text"])
                        elif isinstance(block, str):
                            parts.append(block)
                    content = "\n".join(parts).strip()

            if content or tool_calls:
                messages.append(
                    UnifiedMessage(
                        role=role,
                        content=content,
                        timestamp=timestamp,
                        tool_calls=tool_calls,
                        model=model_str if role == "assistant" else "",
                    )
                )

    except sqlite3.Error:
        return None
    finally:
        if con is not None:
            con.close()

    if not messages:
        return None

    return UnifiedSession(
        session_id=session_id,
        engine=EngineType.OPENCODE,
        project_path=project_path,
        started_at=_ms_to_iso(started_ms),
        ended_at=_ms_to_iso(ended_ms),
        messages=messages,
        title=title,
        model=model_str,
        source_file=str(db_path),
    )


def find_opencode_sessions(
    project_path: Optional[str] = None, home: Optional[Path] = None
) -> list[UnifiedSession]:
    """Finds all OpenCode sessions for a given project path.

    OpenCode stores all sessions in a single SQLite database and matches by
    the ``directory`` field in the ``session`` table.

    Args:
        project_path: The project directory to match against. If None,
            sessions from every project are returned unfiltered.
        home: Optional home directory override.

    Returns:
        list[UnifiedSession]: All sessions found, sorted by start time descending.
    """
    db_path = _find_opencode_db(home)
    if not db_path:
        return []

    normalized_target = (
        project_path.replace("\\", "/").lower().rstrip("/")
        if project_path is not None
        else None
    )
    sessions: list[UnifiedSession] = []

    con = None
    try:
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        con.row_factory = sqlite3.Row

        # Find all sessions matching the project path
        rows = con.execute(
            "SELECT id, directory, time_created FROM session ORDER BY time_created DESC"
        ).fetchall()

    except sqlite3.Error:
        return []
    finally:
        if con is not None:
            con.close()

    for row in rows:
        if normalized_target is not None:
            directory = (row["directory"] or "").replace("\\", "/").lower().rstrip("/")
            if directory != normalized_target:
                continue

        session = parse_opencode_session(row["id"], db_path)
        if session:
            sessions.append(session)

    sessions.sort(key=lambda s: s.started_at, reverse=True)
    return sessions

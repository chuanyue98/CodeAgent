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
from datetime import UTC, datetime
from functools import partial
from pathlib import Path

from core.session_history.models import (
    EngineType,
    ToolCallSummary,
    UnifiedMessage,
    UnifiedSession,
)
from core.session_history.parse_cache import cached_parse
from core.session_history.paths import normalize_project_path


def _ms_to_iso(ms: int) -> str:
    """Converts a Unix millisecond timestamp to ISO 8601 string.

    Args:
        ms: Timestamp in milliseconds.

    Returns:
        str: ISO 8601 formatted string (UTC).
    """
    if not ms:
        return ""
    return datetime.fromtimestamp(ms / 1000, tz=UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _find_opencode_db(home: Path | None = None) -> Path | None:
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


def _subagent_columns(con: sqlite3.Connection) -> tuple[str, str]:
    """SELECT expressions for the parent/agent columns, or empty stand-ins.

    OpenCode grew ``session.parent_id`` and ``session.agent`` with subagents;
    a database written by an older build has neither, and naming a missing
    column fails the whole query.
    """
    try:
        present = {row[1] for row in con.execute("PRAGMA table_info(session)")}
    except sqlite3.Error:
        present = set()
    return (
        "parent_id" if "parent_id" in present else "'' AS parent_id",
        "agent" if "agent" in present else "'' AS agent",
    )


def parse_opencode_session(
    session_id: str,
    db_path: Path,
    connection: sqlite3.Connection | None = None,
) -> UnifiedSession | None:
    """Parses a single OpenCode session from the SQLite database.

    Args:
        session_id: The session ID to parse.
        db_path: Path to the OpenCode SQLite database.
        connection: Optional pre-opened SQLite connection. When provided,
            it is reused for all queries and is *not* closed here. When
            None, a new read-only connection is created and closed before
            returning (backward compatible).

    Returns:
        UnifiedSession if parsing succeeds, None otherwise.
    """
    owns_connection = connection is None
    con: sqlite3.Connection | None = connection
    if owns_connection:
        if not db_path.exists():
            return None
        try:
            con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
            con.row_factory = sqlite3.Row
        except sqlite3.Error:
            return None

    try:
        assert con is not None
        # Fetch session metadata
        parent_col, agent_col = _subagent_columns(con)
        sess_row = con.execute(
            "SELECT id, directory, title, model, time_created, time_updated, "
            f"{parent_col}, {agent_col} FROM session WHERE id = ?",
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

        # Batch-fetch all parts for the entire session in a single query and
        # group them by message_id, avoiding a per-message N+1 part lookup.
        part_rows = con.execute(
            "SELECT message_id, data FROM part "
            "WHERE session_id = ? ORDER BY time_created ASC",
            (session_id,),
        ).fetchall()

        parts_by_message: dict[str, list[sqlite3.Row]] = {}
        for part_row in part_rows:
            parts_by_message.setdefault(part_row["message_id"], []).append(part_row)

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

            part_rows_for_msg = parts_by_message.get(msg_id, [])

            text_parts: list[str] = []
            tool_calls: list[ToolCallSummary] = []

            for part_row in part_rows_for_msg:
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
        if owns_connection and con is not None:
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
        parent_session_id=sess_row["parent_id"] or "",
        agent=sess_row["agent"] or "",
    )


#: Version-token half for a session the message/part scans never saw.
_NO_ROWS = (0, 0, 0, 0)


def _session_versions(con: sqlite3.Connection) -> dict[str, tuple[int, int, int, int]]:
    """Per-session change tokens for the parse cache.

    ``session.time_updated`` on its own is not a change signal: OpenCode
    appends messages and parts without always bumping it, so a growing session
    would keep serving whatever its first parse saw. Folding in each session's
    row counts and newest row time closes that -- two grouped scans, ~20 ms
    against a full history, versus ~1.3 s to re-decode it.
    """

    def aggregate(query: str) -> dict[str, tuple[int, int]]:
        return {row[0]: (row[1], row[2] or 0) for row in con.execute(query)}

    messages = aggregate(
        "SELECT session_id, COUNT(*), MAX(time_created) FROM message GROUP BY session_id"
    )
    parts = aggregate(
        "SELECT session_id, COUNT(*), MAX(time_created) FROM part GROUP BY session_id"
    )
    return {
        session_id: (*messages.get(session_id, (0, 0)), *parts.get(session_id, (0, 0)))
        for session_id in messages.keys() | parts.keys()
    }


def find_opencode_sessions(
    project_path: str | None = None, home: Path | None = None
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
        normalize_project_path(project_path) if project_path is not None else None
    )
    sessions: list[UnifiedSession] = []

    con = None
    try:
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        con.row_factory = sqlite3.Row

        # Reading one session decodes every one of its message parts, so the
        # whole history is re-decoded on each call unless the unchanged
        # sessions are memoized past it.
        versions = _session_versions(con)

        # Find all sessions matching the project path
        rows = con.execute(
            "SELECT id, directory, time_created, time_updated "
            "FROM session ORDER BY time_created DESC"
        ).fetchall()

        # Parse every matching session reusing the single connection to avoid
        # creating a new SQLite connection per session.
        for row in rows:
            if normalized_target is not None:
                directory = normalize_project_path(row["directory"] or "")
                if directory != normalized_target:
                    continue

            session = cached_parse(
                f"opencode:{db_path}:{row['id']}",
                (row["time_updated"] or 0, *versions.get(row["id"], _NO_ROWS)),
                partial(parse_opencode_session, row["id"], db_path, connection=con),
            )
            if session:
                sessions.append(session)

    except sqlite3.Error:
        return []
    finally:
        if con is not None:
            con.close()

    sessions.sort(key=lambda s: s.started_at, reverse=True)
    return sessions

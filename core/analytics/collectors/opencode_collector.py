from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from core.analytics.models import RawUsageEntry


def _ms_to_iso(ms: int) -> str:
    """Converts a millisecond timestamp to an ISO 8601 formatted string.

    Args:
        ms: The timestamp in milliseconds.

    Returns:
        str: The ISO 8601 formatted timestamp string.
    """
    return datetime.fromtimestamp(ms / 1000, tz=UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _safe_float(value: object) -> float:
    """Safely converts a value to a float.

    Args:
        value: The value to convert.

    Returns:
        float: The converted float value, or 0.0 if conversion fails.
    """
    try:
        if isinstance(value, (str, bytes, int, float)):
            return float(value)
        return 0.0
    except (TypeError, ValueError):
        return 0.0


def _iso_to_ms(iso: str) -> int:
    """Converts an ISO 8601 timestamp string to milliseconds.

    Args:
        iso: The ISO 8601 formatted timestamp string.

    Returns:
        int: The timestamp in milliseconds, or 0 if parsing fails.
    """
    if not iso:
        return 0
    try:
        return int(
            datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp() * 1000
        )
    except (ValueError, TypeError):
        return 0


def _subagent_columns(con: sqlite3.Connection) -> tuple[str, str]:
    """SELECT expressions for the parent/agent columns, or empty stand-ins.

    OpenCode grew ``session.parent_id`` and ``session.agent`` with subagents;
    a database written by an older build has neither, and naming a missing
    column costs the whole scan.
    """
    try:
        present = {row[1] for row in con.execute("PRAGMA table_info(session)")}
    except sqlite3.Error:
        present = set()
    return (
        "s.parent_id" if "parent_id" in present else "'' AS parent_id",
        "s.agent" if "agent" in present else "'' AS agent",
    )


def scan_opencode_usage(
    home: Path | None = None, since_timestamp: str = ""
) -> list[RawUsageEntry]:
    """Scans the OpenCode SQLite database for usage statistics.

    Args:
        home: Optional home directory path. If not provided, defaults to the
            user's home directory.
        since_timestamp: Only return entries newer than this ISO 8601 timestamp.

    Returns:
        List[RawUsageEntry]: A list of raw usage entries extracted from the
            OpenCode database, including token counts and costs.
    """
    db_path = (home or Path.home()) / ".local" / "share" / "opencode" / "opencode.db"
    if not db_path.exists():
        return []

    since_ms = _iso_to_ms(since_timestamp)
    entries: list[RawUsageEntry] = []
    con = None
    try:
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        con.row_factory = sqlite3.Row

        # Join part → message (for model) → session (for directory, and for
        # the parent_id/agent that mark a subagent run as belonging to the
        # session that spawned it rather than standing on its own)
        # part.data contains tokens + cost for type="step-finish"
        parent_col, agent_col = _subagent_columns(con)
        rows = con.execute(
            f"""
            SELECT
                p.session_id,
                p.message_id,
                p.time_created,
                p.data AS part_data,
                m.data AS msg_data,
                s.directory,
                {parent_col},
                {agent_col}
            FROM part p
            JOIN message m ON m.id = p.message_id
            JOIN session s ON s.id = p.session_id
            WHERE json_extract(p.data, '$.type') = 'step-finish'
              AND p.time_created > ?
              AND (
                json_extract(p.data, '$.tokens.input') > 0
                OR json_extract(p.data, '$.tokens.output') > 0
              )
            ORDER BY p.time_created ASC
            """,
            (since_ms,),
        ).fetchall()
    except sqlite3.Error:
        return []
    finally:
        if con is not None:
            con.close()

    for row in rows:
        try:
            part = json.loads(row["part_data"])
            msg = json.loads(row["msg_data"])
        except (json.JSONDecodeError, TypeError):
            continue

        tokens = part.get("tokens", {})
        cache = tokens.get("cache", {})

        input_t = int(tokens.get("input", 0) or 0)
        output_t = int(tokens.get("output", 0) or 0)
        reasoning_t = int(tokens.get("reasoning", 0) or 0)
        cache_write = int(cache.get("write", 0) or 0)
        cache_read = int(cache.get("read", 0) or 0)
        cost = _safe_float(part.get("cost"))

        model = msg.get("modelID") or msg.get("model") or "opencode-unknown"

        entries.append(
            RawUsageEntry(
                timestamp=_ms_to_iso(row["time_created"]),
                session_id=row["session_id"],
                model=model,
                input_tokens=input_t,
                output_tokens=output_t + reasoning_t,
                cache_creation_tokens=cache_write,
                cache_read_tokens=cache_read,
                cost=cost,
                project_path=row["directory"] or "",
                target="opencode",
                parent_session_id=row["parent_id"] or "",
                agent=row["agent"] or "",
            )
        )

    return entries

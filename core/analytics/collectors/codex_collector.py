from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from core.analytics.models import RawUsageEntry

# Heuristic split for Codex's session-level total (no per-turn breakdown available)
_INPUT_RATIO = 0.82
_OUTPUT_RATIO = 0.18


def _ms_to_iso(ms: int) -> str:
    """Converts a millisecond timestamp to an ISO 8601 formatted string.

    Args:
        ms: The timestamp in milliseconds.

    Returns:
        str: The ISO 8601 formatted timestamp string.
    """
    return datetime.fromtimestamp(ms / 1000, tz=UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z")


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
        # Simple parsing for common ISO formats
        return int(
            datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp() * 1000
        )
    except (ValueError, TypeError):
        return 0


def scan_codex_usage(
    home: Path | None = None, since_timestamp: str = ""
) -> list[RawUsageEntry]:
    """Scans the Codex SQLite database for usage statistics.

    Args:
        home: Optional home directory path. If not provided, defaults to the
            user's home directory.
        since_timestamp: Only return entries newer than this ISO 8601 timestamp.

    Returns:
        List[RawUsageEntry]: A list of raw usage entries extracted from the
            Codex state database.
    """
    db_path = (home or Path.home()) / ".codex" / "state_5.sqlite"
    if not db_path.exists():
        return []

    since_ms = _iso_to_ms(since_timestamp)
    entries: list[RawUsageEntry] = []
    con = None
    try:
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        con.row_factory = sqlite3.Row
        rows = con.execute(
            """
            SELECT id, created_at_ms, model, model_provider, cwd, tokens_used
            FROM threads
            WHERE tokens_used > 0 AND created_at_ms > ?
            ORDER BY created_at_ms ASC
            """,
            (since_ms,),
        ).fetchall()
    except sqlite3.Error:
        return []
    finally:
        if con is not None:
            con.close()

    for row in rows:
        total = row["tokens_used"] or 0
        if total <= 0:
            continue

        model = row["model"] or "codex-mini-latest"
        ts_ms = row["created_at_ms"] or 0
        timestamp = _ms_to_iso(ts_ms) if ts_ms else ""

        entries.append(
            RawUsageEntry(
                timestamp=timestamp,
                session_id=row["id"],
                model=model,
                input_tokens=int(total * _INPUT_RATIO),
                output_tokens=int(total * _OUTPUT_RATIO),
                cache_creation_tokens=0,
                cache_read_tokens=0,
                project_path=row["cwd"] or "",
                target="codex",
            )
        )

    return entries

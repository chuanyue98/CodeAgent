from __future__ import annotations

import json
import re
from pathlib import Path
from typing import List

from core.analytics.models import RawUsageEntry


def _decode_project_path(dir_name: str) -> str:
    """Converts Claude's dash-encoded directory name back to a standard file path.

    Claude encodes paths as: E:/demo/CodeAgent -> E--demo-CodeAgent.
    Drive letters followed by a colon and slash become <letter>--, and subsequent
    slashes become dashes.

    Args:
        dir_name: The dash-encoded directory name.

    Returns:
        str: The decoded absolute file path.
    """
    m = re.match(r"^([A-Za-z])--(.*)$", dir_name)
    if m:
        drive, rest = m.groups()
        return f"{drive}:/{rest.replace('-', '/')}"
    return dir_name.replace("-", "/")


def scan_claude_usage(
    home: Path | None = None, since_timestamp: str = ""
) -> List[RawUsageEntry]:
    """Scans the Claude projects directory for usage logs.

    Args:
        home: Optional home directory path. If not provided, defaults to the
            user's home directory.
        since_timestamp: Only return entries newer than this ISO 8601 timestamp.

    Returns:
        List[RawUsageEntry]: A list of raw usage entries extracted from Claude's
            JSONL log files.
    """
    base = (home or Path.home()) / ".claude" / "projects"
    if not base.exists():
        return []

    entries: List[RawUsageEntry] = []

    for project_dir in base.iterdir():
        if not project_dir.is_dir():
            continue
        project_path = _decode_project_path(project_dir.name)

        for jsonl_file in project_dir.glob("*.jsonl"):
            session_id = jsonl_file.stem
            _parse_claude_file(
                jsonl_file, session_id, project_path, entries, since_timestamp
            )

    return entries


def _parse_claude_file(
    path: Path,
    session_id: str,
    project_path: str,
    entries: List[RawUsageEntry],
    since_timestamp: str = "",
) -> None:
    """Parses a single Claude JSONL log file and appends entries to the list.

    Args:
        path: Path to the JSONL log file.
        session_id: The session ID associated with the log file.
        project_path: The decoded project path for these entries.
        entries: The list to which extracted RawUsageEntry objects will be appended.
        since_timestamp: Only include entries newer than this timestamp.
    """
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue

                ts = row.get("timestamp", "")
                if since_timestamp and ts <= since_timestamp:
                    continue

                msg = row.get("message")
                if not isinstance(msg, dict):
                    continue
                usage = msg.get("usage")
                if not isinstance(usage, dict):
                    continue

                input_t = usage.get("input_tokens", 0) or 0
                output_t = usage.get("output_tokens", 0) or 0
                cache_create = usage.get("cache_creation_input_tokens", 0) or 0
                cache_read = usage.get("cache_read_input_tokens", 0) or 0

                if input_t == 0 and output_t == 0:
                    continue

                entries.append(
                    RawUsageEntry(
                        timestamp=row.get("timestamp", ""),
                        session_id=session_id,
                        model=msg.get("model", "unknown"),
                        input_tokens=input_t,
                        output_tokens=output_t,
                        cache_creation_tokens=cache_create,
                        cache_read_tokens=cache_read,
                        project_path=project_path,
                        target="claude",
                    )
                )
    except OSError:
        pass

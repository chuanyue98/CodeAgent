from __future__ import annotations

import json
from pathlib import Path
from typing import List

from core.analytics.models import RawUsageEntry


def scan_gemini_usage(
    home: Path | None = None, since_timestamp: str = ""
) -> List[RawUsageEntry]:
    """Scans the Gemini temporary directory for usage logs.

    Args:
        home: Optional home directory path. If not provided, defaults to the
            user's home directory.
        since_timestamp: Only return entries newer than this ISO 8601 timestamp.

    Returns:
        List[RawUsageEntry]: A list of raw usage entries extracted from Gemini's
            JSONL log files found in the temporary directory.
    """
    base = (home or Path.home()) / ".gemini" / "tmp"
    if not base.exists():
        return []

    entries: List[RawUsageEntry] = []

    for jsonl_file in base.rglob("*.jsonl"):
        # Quick check: if the file hasn't been modified since since_timestamp, skip it.
        # This is an optimization. since_timestamp is ISO 8601, but we can compare
        # it with file mtime if we convert since_timestamp to epoch.
        # For simplicity and correctness (in case of clock drift), we'll parse the file
        # but filter entries inside.
        workspace = jsonl_file.parent.parent.name
        session_id = jsonl_file.stem
        _parse_gemini_file(jsonl_file, session_id, workspace, entries, since_timestamp)

    return entries


def _parse_gemini_file(
    path: Path,
    session_id: str,
    workspace: str,
    entries: List[RawUsageEntry],
    since_timestamp: str = "",
) -> None:
    """Parses a single Gemini JSONL log file and appends entries to the list.

    Args:
        path: Path to the JSONL log file.
        session_id: The session ID associated with the log file.
        workspace: The workspace identifier (parent directory name).
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

                tokens = row.get("tokens")
                if not isinstance(tokens, dict):
                    continue

                input_t = tokens.get("input", 0) or 0
                output_t = tokens.get("output", 0) or 0
                # Gemini "cached" maps to cache_read; "thoughts" are counted as output
                cache_read = tokens.get("cached", 0) or 0
                thoughts = tokens.get("thoughts", 0) or 0

                if input_t == 0 and output_t == 0 and thoughts == 0:
                    continue

                entries.append(
                    RawUsageEntry(
                        timestamp=row.get("timestamp", ""),
                        session_id=session_id,
                        model=row.get("model", "gemini-unknown"),
                        input_tokens=input_t,
                        output_tokens=output_t + thoughts,
                        cache_creation_tokens=0,
                        cache_read_tokens=cache_read,
                        project_path=workspace,
                        target="gemini",
                    )
                )
    except OSError:
        pass

from __future__ import annotations

import json
import re
from pathlib import Path

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
) -> list[RawUsageEntry]:
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

    entries: list[RawUsageEntry] = []

    for project_dir in base.iterdir():
        if not project_dir.is_dir():
            continue
        project_path = _decode_project_path(project_dir.name)

        for jsonl_file in project_dir.glob("*.jsonl"):
            session_id = jsonl_file.stem
            _parse_claude_file(
                jsonl_file, session_id, project_path, entries, since_timestamp
            )

        # Subagent transcripts live one level down, in
        # ``<session_id>/subagents/agent-*.jsonl``. Their rows carry the
        # *parent's* sessionId, so the file stem is the only id that tells two
        # subagents of one session apart.
        for session_dir in project_dir.iterdir():
            if not session_dir.is_dir():
                continue
            for agent_file in (session_dir / "subagents").glob("*.jsonl"):
                _parse_claude_file(
                    agent_file,
                    agent_file.stem,
                    project_path,
                    entries,
                    since_timestamp,
                    parent_session_id=session_dir.name,
                )

    return entries


def _parse_claude_file(
    path: Path,
    session_id: str,
    project_path: str,
    entries: list[RawUsageEntry],
    since_timestamp: str = "",
    parent_session_id: str = "",
) -> None:
    """Parses a single Claude JSONL log file and appends entries to the list.

    Args:
        path: Path to the JSONL log file.
        session_id: The session ID associated with the log file.
        project_path: The decoded project path for these entries.
        entries: The list to which extracted RawUsageEntry objects will be appended.
        since_timestamp: Only include entries newer than this timestamp.
        parent_session_id: Owning session when ``path`` is a subagent
            transcript; empty for a top-level session.
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

                # Session rows normally contain the exact cwd.  The parent
                # directory encoding cannot distinguish path separators from
                # dashes in directory names, so use cwd when present.
                exact_project_path = row.get("cwd") or project_path

                entries.append(
                    RawUsageEntry(
                        timestamp=row.get("timestamp", ""),
                        session_id=session_id,
                        model=msg.get("model", "unknown"),
                        input_tokens=input_t,
                        output_tokens=output_t,
                        cache_creation_tokens=cache_create,
                        cache_read_tokens=cache_read,
                        project_path=exact_project_path,
                        target="claude",
                        parent_session_id=parent_session_id,
                    )
                )
    except OSError:
        pass

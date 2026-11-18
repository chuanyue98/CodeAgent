from __future__ import annotations

import json
from pathlib import Path

from core.analytics.aggregator import _parse_ts
from core.analytics.models import RawUsageEntry
from core.session_history.parsers._subagents import subagent_files
from core.session_history.paths import (
    claude_dir,
    decode_claude_project_path,
    strip_extended_length_prefix,
)
from core.utils.long_paths import exists as path_exists
from core.utils.long_paths import list_dirs, list_files, long_path


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
    base = claude_dir(home) / "projects"
    if not path_exists(base):
        return []

    entries: list[RawUsageEntry] = []

    for project_dir in list_dirs(base):
        if not project_dir.is_dir():
            continue
        project_path = decode_claude_project_path(project_dir.name)

        for jsonl_file in list_files(project_dir, ".jsonl"):
            session_id = jsonl_file.stem
            _parse_claude_file(
                jsonl_file, session_id, project_path, entries, since_timestamp
            )

        # Subagent transcripts live one level down (or nested), in
        # ``<session_id>/subagents/**/*.jsonl``.
        for session_dir in list_dirs(project_dir):
            if not session_dir.is_dir():
                continue
            for agent_file, owner_id in subagent_files(session_dir):
                _parse_claude_file(
                    agent_file,
                    agent_file.stem,
                    project_path,
                    entries,
                    since_timestamp,
                    parent_session_id=owner_id,
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
    since_dt = _parse_ts(since_timestamp) if since_timestamp else None
    try:
        with open(long_path(path), encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue

                ts = row.get("timestamp", "")
                if since_dt is not None and _parse_ts(ts) <= since_dt:
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
                raw_cwd = row.get("cwd") or ""
                if raw_cwd:
                    slashed = raw_cwd.replace("\\", "/")
                    exact_project_path = (
                        strip_extended_length_prefix(slashed)
                        if slashed.lower().startswith("//?/")
                        else raw_cwd
                    )
                else:
                    exact_project_path = project_path

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
                        # Every row of a subagent transcript is attributed to
                        # the agent that produced it.
                        agent=row.get("attributionAgent") or "",
                    )
                )
    except OSError:
        pass

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from core.analytics.aggregator import _parse_ts
from core.analytics.models import RawUsageEntry
from core.session_history.parsers._subagents import subagent_files
from core.session_history.paths import codebuddy_dir, strip_extended_length_prefix
from core.utils.long_paths import exists as path_exists
from core.utils.long_paths import list_dirs, list_files, long_path


def _to_iso(ts) -> str:
    """Converts a CodeBuddy epoch-millisecond timestamp to ISO 8601 (UTC).

    CodeBuddy stores ``timestamp`` as epoch ms (int) on every JSONL row; the
    analytics pipeline compares timestamps as ISO strings, so normalize here.

    Args:
        ts: The raw timestamp value (int, float, or numeric string).

    Returns:
        str: ISO 8601 string, or "" if the value is not a usable timestamp.
    """
    try:
        ms = int(ts)
    except (TypeError, ValueError):
        return ""
    return datetime.fromtimestamp(ms / 1000, tz=UTC).isoformat()


def scan_codebuddy_usage(
    home: Path | None = None, since_timestamp: str = ""
) -> list[RawUsageEntry]:
    """Scans the CodeBuddy projects directory for usage logs.

    CodeBuddy records per-request token usage on each assistant ``message``
    row under ``providerData.usage`` (``inputTokens`` / ``outputTokens`` /
    ``inputTokensDetails[].cached_tokens``), with the model at
    ``providerData.model``.

    Args:
        home: Optional home directory path. If not provided, defaults to the
            user's home directory.
        since_timestamp: Only return entries newer than this ISO 8601 timestamp.

    Returns:
        List[RawUsageEntry]: A list of raw usage entries extracted from
        CodeBuddy's JSONL log files.
    """
    base = codebuddy_dir(home) / "projects"
    if not path_exists(base):
        return []

    entries: list[RawUsageEntry] = []

    for project_dir in list_dirs(base):
        if not project_dir.is_dir():
            continue
        for jsonl_file in list_files(project_dir, ".jsonl"):
            _parse_codebuddy_file(jsonl_file, jsonl_file.stem, entries, since_timestamp)

        # Subagent transcripts live in ``<session_id>/subagents/``, which a
        # flat glob never reaches. A run that spawns its own nests one level
        # further, so the owner is the nearest ``agent-<id>`` directory.
        for session_dir in list_dirs(project_dir):
            if not session_dir.is_dir():
                continue
            for agent_file, owner_id in subagent_files(session_dir):
                _parse_codebuddy_file(
                    agent_file,
                    agent_file.stem,
                    entries,
                    since_timestamp,
                    parent_session_id=owner_id,
                )

    return entries


def _parse_codebuddy_file(
    path: Path,
    session_id: str,
    entries: list[RawUsageEntry],
    since_timestamp: str = "",
    parent_session_id: str = "",
) -> None:
    """Parses a single CodeBuddy JSONL log file and appends entries.

    Args:
        path: Path to the JSONL log file.
        session_id: The session ID associated with the log file (file stem).
        entries: The list to which extracted RawUsageEntry objects are appended.
        since_timestamp: Only include entries newer than this timestamp.
        parent_session_id: Owning session when ``path`` is a subagent
            transcript; empty for a session a user started.
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

                if row.get("type") != "message" or row.get("role") != "assistant":
                    continue

                provider_data = row.get("providerData")
                if not isinstance(provider_data, dict):
                    continue
                usage = provider_data.get("usage")
                if not isinstance(usage, dict):
                    continue

                ts = _to_iso(row.get("timestamp"))
                if not ts:
                    continue
                if since_dt is not None and _parse_ts(ts) <= since_dt:
                    continue

                input_t = usage.get("inputTokens", 0) or 0
                output_t = usage.get("outputTokens", 0) or 0
                if input_t == 0 and output_t == 0:
                    continue

                cache_read = 0
                for detail in usage.get("inputTokensDetails") or []:
                    if isinstance(detail, dict):
                        cache_read += detail.get("cached_tokens", 0) or 0

                raw_cwd = row.get("cwd") or ""
                if raw_cwd:
                    slashed = raw_cwd.replace("\\", "/")
                    proj_path = (
                        strip_extended_length_prefix(slashed)
                        if slashed.lower().startswith("//?/")
                        else raw_cwd
                    )
                else:
                    proj_path = ""

                entries.append(
                    RawUsageEntry(
                        timestamp=ts,
                        session_id=session_id,
                        model=provider_data.get("model", "unknown"),
                        input_tokens=input_t,
                        output_tokens=output_t,
                        cache_read_tokens=cache_read,
                        project_path=proj_path,
                        target="codebuddy",
                        parent_session_id=parent_session_id,
                    )
                )
    except OSError:
        pass

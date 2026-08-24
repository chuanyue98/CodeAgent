from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from core.analytics.models import RawUsageEntry


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
    base = (home or Path.home()) / ".codebuddy" / "projects"
    if not base.exists():
        return []

    entries: list[RawUsageEntry] = []

    for project_dir in base.iterdir():
        if not project_dir.is_dir():
            continue
        for jsonl_file in project_dir.glob("*.jsonl"):
            _parse_codebuddy_file(jsonl_file, jsonl_file.stem, entries, since_timestamp)

    return entries


def _parse_codebuddy_file(
    path: Path,
    session_id: str,
    entries: list[RawUsageEntry],
    since_timestamp: str = "",
) -> None:
    """Parses a single CodeBuddy JSONL log file and appends entries.

    Args:
        path: Path to the JSONL log file.
        session_id: The session ID associated with the log file (file stem).
        entries: The list to which extracted RawUsageEntry objects are appended.
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
                if since_timestamp and ts <= since_timestamp:
                    continue

                input_t = usage.get("inputTokens", 0) or 0
                output_t = usage.get("outputTokens", 0) or 0
                if input_t == 0 and output_t == 0:
                    continue

                cache_read = 0
                for detail in usage.get("inputTokensDetails") or []:
                    if isinstance(detail, dict):
                        cache_read += detail.get("cached_tokens", 0) or 0

                entries.append(
                    RawUsageEntry(
                        timestamp=ts,
                        session_id=session_id,
                        model=provider_data.get("model", "unknown"),
                        input_tokens=input_t,
                        output_tokens=output_t,
                        cache_read_tokens=cache_read,
                        project_path=row.get("cwd") or "",
                        target="codebuddy",
                    )
                )
    except OSError:
        pass

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from urllib.parse import unquote, urlparse

from core.analytics.models import RawUsageEntry
from core.session_history.paths import strip_extended_length_prefix


def _uri_to_path(uri: str) -> str:
    """Converts a file:// URI to a local filesystem path."""
    if uri.startswith("file://"):
        parsed = urlparse(uri)
        path = unquote(parsed.path)
        if len(path) >= 3 and path[0] == "/" and path[2] == ":":
            path = path[1:]
        return strip_extended_length_prefix(path.replace("\\", "/"))
    return strip_extended_length_prefix(uri.replace("\\", "/"))


def _read_configured_model(base_dir: Path) -> str:
    """Reads configured model from settings.json or returns default."""
    settings_file = base_dir / "settings.json"
    if settings_file.is_file():
        try:
            with open(settings_file, encoding="utf-8") as f:
                data = json.load(f)
                model_raw = str(data.get("model", "")).lower()
                if "3.8" in model_raw and "flash" in model_raw:
                    return "gemini-3.8-flash"
                if "3.6" in model_raw and "flash" in model_raw:
                    return "gemini-3.6-flash"
                if "3" in model_raw and "pro" in model_raw:
                    return "gemini-3-pro"
                if "2.5" in model_raw and "pro" in model_raw:
                    return "gemini-2.5-pro"
                if "2.5" in model_raw and "flash" in model_raw:
                    return "gemini-2.5-flash"
                if "2.0" in model_raw and "flash" in model_raw:
                    return "gemini-2.0-flash"
        except (OSError, json.JSONDecodeError):
            pass
    return "gemini-3.8-flash"


def _parse_transcript(
    path: Path,
    session_id: str,
    project_path: str,
    model: str,
    since_timestamp: str = "",
    parent_session_id: str = "",
    agent: str = "",
) -> list[RawUsageEntry]:
    """Parses an Antigravity transcript file into raw usage entries."""
    if not path.is_file():
        return []

    entries: list[RawUsageEntry] = []
    inferred_path = project_path
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue

                if not isinstance(row, dict):
                    continue

                tool_calls = row.get("tool_calls") or []
                if not inferred_path:
                    for tc in tool_calls:
                        if isinstance(tc, dict):
                            args = tc.get("args")
                            if isinstance(args, dict):
                                cwd = args.get("Cwd") or args.get("SearchDirectory") or args.get("TargetFile")
                                if cwd and isinstance(cwd, str) and (cwd.startswith("/") or (len(cwd) > 2 and cwd[1] == ":")):
                                    inferred_path = str(Path(cwd).parent if args.get("TargetFile") else cwd).strip("\"'")
                                    break

                row_type = row.get("type", "")
                if row_type != "PLANNER_RESPONSE":
                    continue

                ts = (row.get("created_at") or "").replace(" ", "T")
                if since_timestamp and ts <= since_timestamp:
                    continue

                content = row.get("content") or ""
                thinking = row.get("thinking") or ""

                tc_len = sum(
                    len(json.dumps(tc, ensure_ascii=False))
                    for tc in tool_calls
                    if isinstance(tc, dict)
                )
                out_chars = len(content) + len(thinking)
                in_chars = tc_len + 200

                in_tokens = max(10, in_chars // 4)
                out_tokens = max(10, out_chars // 4)

                entries.append(
                    RawUsageEntry(
                        timestamp=ts,
                        session_id=session_id,
                        model=model,
                        input_tokens=in_tokens,
                        output_tokens=out_tokens,
                        cache_creation_tokens=0,
                        cache_read_tokens=0,
                        cost=0.0,
                        project_path=inferred_path,
                        target="antigravity",
                        parent_session_id=parent_session_id,
                        agent=agent,
                    )
                )
        # Update any earlier entries if inferred_path was found later
        if inferred_path and not project_path:
            for e in entries:
                if not e.project_path:
                    e.project_path = inferred_path
    except OSError:
        pass
    return entries


def scan_antigravity_usage(
    home: Path | None = None, since_timestamp: str = ""
) -> list[RawUsageEntry]:
    """Scans Antigravity storage for usage records.

    Args:
        home: Optional home directory override.
        since_timestamp: Only return entries newer than this timestamp.

    Returns:
        List of RawUsageEntry objects.
    """
    base_dir = (home or Path.home()) / ".gemini" / "antigravity-cli"
    if not base_dir.exists():
        return []

    model = _read_configured_model(base_dir)
    db_path = base_dir / "conversation_summaries.db"
    brain_dir = base_dir / "brain"

    entries: list[RawUsageEntry] = []
    seen_sessions: set[str] = set()

    # 1. From conversation_summaries.db
    if db_path.is_file():
        try:
            with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    "SELECT conversation_id, workspace_uris, last_modified_time, "
                    "step_count, parent_conversation_id, agent_name "
                    "FROM conversation_summaries"
                ).fetchall()
                for row in rows:
                    session_id = row["conversation_id"]
                    if not session_id:
                        continue
                    seen_sessions.add(session_id)

                    project_path = ""
                    uris_str = row["workspace_uris"] or ""
                    if uris_str:
                        try:
                            uris = json.loads(uris_str)
                            if isinstance(uris, list) and uris:
                                for u in uris:
                                    if isinstance(u, str) and u.startswith("file://"):
                                        project_path = _uri_to_path(u)
                                        break
                        except (json.JSONDecodeError, TypeError):
                            pass

                    last_modified = str(row["last_modified_time"] or "").replace(" ", "T")
                    parent_id = str(row["parent_conversation_id"] or "")
                    agent = str(row["agent_name"] or "")
                    step_count = int(row["step_count"] or 0)

                    transcript_file = (
                        brain_dir
                        / session_id
                        / ".system_generated"
                        / "logs"
                        / "transcript.jsonl"
                    )
                    if not transcript_file.is_file():
                        transcript_file = brain_dir / session_id / "transcript.jsonl"

                    file_entries = _parse_transcript(
                        transcript_file,
                        session_id,
                        project_path,
                        model,
                        since_timestamp,
                        parent_id,
                        agent,
                    )
                    if file_entries:
                        entries.extend(file_entries)
                    elif last_modified and (
                        not since_timestamp or last_modified > since_timestamp
                    ):
                        entries.append(
                            RawUsageEntry(
                                timestamp=last_modified,
                                session_id=session_id,
                                model=model,
                                input_tokens=max(50, step_count * 50),
                                output_tokens=max(20, step_count * 20),
                                cache_creation_tokens=0,
                                cache_read_tokens=0,
                                cost=0.0,
                                project_path=project_path,
                                target="antigravity",
                                parent_session_id=parent_id,
                                agent=agent,
                            )
                        )
        except (sqlite3.Error, OSError):
            pass

    # 2. Transcripts in brain_dir not covered by conversation_summaries.db
    if brain_dir.is_dir():
        for sess_dir in brain_dir.iterdir():
            if not sess_dir.is_dir():
                continue
            session_id = sess_dir.name
            if session_id in seen_sessions:
                continue

            transcript_file = sess_dir / ".system_generated" / "logs" / "transcript.jsonl"
            if not transcript_file.is_file():
                transcript_file = sess_dir / "transcript.jsonl"
            if not transcript_file.is_file():
                continue

            file_entries = _parse_transcript(
                transcript_file,
                session_id,
                "",
                model,
                since_timestamp,
            )
            entries.extend(file_entries)

    return entries

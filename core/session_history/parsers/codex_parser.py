"""Parser for Codex CLI session history files.

Codex stores sessions as JSONL at:
    ~/.codex/sessions/YYYY/MM/DD/rollout-<timestamp>-<session_id>.jsonl

Each line has ``{timestamp, type, payload}``.  Relevant ``type`` values:
  - ``session_meta``  → session ID, cwd, model
  - ``event_msg``     → user_message / agent_message sub-types
  - ``response_item`` → message / function_call / function_call_output
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from core.session_history.models import (
    EngineType,
    ToolCallSummary,
    UnifiedMessage,
    UnifiedSession,
)


def _ms_to_iso(timestamp: object) -> str:
    """Converts a Unix seconds or milliseconds timestamp to ISO 8601.

    Args:
        timestamp: Timestamp in seconds or milliseconds. Codex's
            ``task_complete.completed_at`` uses seconds in some versions.

    Returns:
        str: ISO 8601 formatted string (UTC).
    """
    if timestamp is None or timestamp == "":
        return ""
    if isinstance(timestamp, str):
        value = timestamp.strip()
        if not value:
            return ""
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            try:
                timestamp = float(value)
            except ValueError:
                return ""
        else:
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    if isinstance(timestamp, bool) or not isinstance(timestamp, (int, float)):
        return ""
    seconds = float(timestamp)
    if seconds > 100_000_000_000:
        seconds /= 1000
    try:
        return datetime.fromtimestamp(seconds, tz=timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%S.000Z"
        )
    except (OverflowError, OSError, ValueError):
        return ""


def parse_codex_session(file_path: Path) -> Optional[UnifiedSession]:
    """Parses a single Codex JSONL session file into a UnifiedSession.

    Args:
        file_path: Path to the ``rollout-*.jsonl`` file.

    Returns:
        UnifiedSession if parsing succeeds, None otherwise.
    """
    if not file_path.exists() or file_path.suffix != ".jsonl":
        return None

    session_id = ""
    cwd = ""
    model = ""
    messages: list[UnifiedMessage] = []
    started_at = ""
    ended_at = ""

    # Collect function calls and outputs to attach to the preceding assistant message
    pending_tool_calls: list[ToolCallSummary] = []
    call_id_to_index: dict[str, int] = {}

    try:
        with open(file_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue

                timestamp = row.get("timestamp", "")
                row_type = row.get("type", "")
                payload = row.get("payload", {})

                if not isinstance(payload, dict):
                    continue

                if row_type == "session_meta":
                    session_id = payload.get("id", "")
                    cwd = payload.get("cwd", "")
                    if not started_at:
                        started_at = timestamp
                    continue

                if row_type == "turn_context":
                    m = payload.get("model", "")
                    if m and not model:
                        model = m
                    continue

                if row_type == "event_msg":
                    sub_type = payload.get("type", "")

                    if sub_type == "user_message":
                        text = payload.get("message", "").strip()
                        if text:
                            messages.append(
                                UnifiedMessage(
                                    role="user",
                                    content=text,
                                    timestamp=timestamp,
                                )
                            )
                            if not started_at:
                                started_at = timestamp
                            ended_at = timestamp

                    elif sub_type == "agent_message":
                        # Only capture final-phase messages (not commentary)
                        phase = payload.get("phase", "final")
                        text = payload.get("message", "").strip()
                        if text and phase == "final":
                            messages.append(
                                UnifiedMessage(
                                    role="assistant",
                                    content=text,
                                    timestamp=timestamp,
                                    model=model,
                                )
                            )
                            ended_at = timestamp

                    elif sub_type == "task_complete":
                        ended_at = (
                            _ms_to_iso(payload.get("completed_at", 0)) or timestamp
                        )

                elif row_type == "response_item":
                    sub_type = payload.get("type", "")

                    if sub_type == "message":
                        role = payload.get("role", "")
                        content_list = payload.get("content", [])
                        if not isinstance(content_list, list):
                            continue

                        text_parts = []
                        for block in content_list:
                            if isinstance(block, dict):
                                text_parts.append(block.get("text", ""))

                        text = "\n".join(text_parts).strip()
                        if not text:
                            continue

                        if role == "user":
                            # Skip developer/system messages
                            pass  # user_message already captured via event_msg
                        elif role == "assistant":
                            phase = payload.get("phase", "final")
                            if phase == "final" and text:
                                # Attach any pending tool calls
                                tc = pending_tool_calls[:] if pending_tool_calls else []
                                messages.append(
                                    UnifiedMessage(
                                        role="assistant",
                                        content=text,
                                        timestamp=timestamp,
                                        tool_calls=tc,
                                        model=model,
                                    )
                                )
                                pending_tool_calls.clear()
                                call_id_to_index.clear()
                                ended_at = timestamp

                    elif sub_type == "function_call":
                        name = payload.get("name", "")
                        args_raw = payload.get("arguments", "")
                        try:
                            args_obj = json.loads(args_raw) if args_raw else {}
                            args_str = json.dumps(args_obj, ensure_ascii=False)
                        except (json.JSONDecodeError, TypeError):
                            args_str = (
                                args_raw[:200] if isinstance(args_raw, str) else ""
                            )

                        if len(args_str) > 200:
                            args_str = args_str[:200] + "..."

                        new_tc = ToolCallSummary(name=name, args_preview=args_str)
                        pending_tool_calls.append(new_tc)
                        call_id = payload.get("call_id", "")
                        if call_id:
                            call_id_to_index[call_id] = len(pending_tool_calls) - 1

                    elif sub_type == "function_call_output":
                        call_id = payload.get("call_id", "")
                        output = payload.get("output", "")
                        if isinstance(output, str) and call_id in call_id_to_index:
                            idx = call_id_to_index[call_id]
                            preview = output[:200] if len(output) > 200 else output
                            pending_tool_calls[idx].result_preview = preview

    except OSError:
        return None

    if not messages:
        return None

    # Try to extract session_id from filename if not found in content
    if not session_id:
        fname = file_path.stem
        # rollout-2026-07-03T17-50-40-019f2763-... → session_id is the UUID part
        parts = fname.split("-", 5)  # split on first 5 dashes
        if len(parts) >= 6:
            session_id = parts[5]

    return UnifiedSession(
        session_id=session_id or file_path.stem,
        engine=EngineType.CODEX,
        project_path=cwd,
        started_at=started_at,
        ended_at=ended_at,
        messages=messages,
        title="",  # Codex doesn't store titles in the session file
        model=model,
        source_file=str(file_path),
    )


def find_codex_sessions(
    project_path: Optional[str] = None, home: Optional[Path] = None
) -> list[UnifiedSession]:
    """Finds all Codex sessions for a given project path.

    Codex stores sessions under ``~/.codex/sessions/YYYY/MM/DD/`` and each
    file contains a ``cwd`` field in ``session_meta`` that is used for matching.

    Args:
        project_path: The project directory to match against. If None,
            sessions from every project are returned unfiltered.
        home: Optional home directory override.

    Returns:
        list[UnifiedSession]: All sessions found, sorted by start time descending.
    """
    base = (home or Path.home()) / ".codex" / "sessions"
    if not base.exists():
        return []

    normalized_target = (
        project_path.replace("\\", "/").lower().rstrip("/")
        if project_path is not None
        else None
    )
    sessions: list[UnifiedSession] = []

    for jsonl_file in base.rglob("*.jsonl"):
        session = parse_codex_session(jsonl_file)
        if session:
            if normalized_target is not None:
                normalized_cwd = (
                    (session.project_path or "").replace("\\", "/").lower().rstrip("/")
                )
                if normalized_cwd != normalized_target:
                    continue
            sessions.append(session)

    sessions.sort(key=lambda s: s.started_at, reverse=True)
    return sessions

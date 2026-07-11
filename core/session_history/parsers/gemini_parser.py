"""Parser for Gemini CLI session history files.

Gemini stores sessions as JSONL at:
    ~/.gemini/tmp/<project_name>/chats/session-<timestamp>-<hash>.jsonl

Each line is a JSON object.  The first line is session metadata with
``sessionId``, ``startTime``, ``lastUpdated``.  Subsequent lines contain
``$set`` patches or standalone message objects with ``type`` field:
  - ``user``     → user messages
  - ``gemini``   → model responses (with content, toolCalls, tokens)
  - ``info``     → informational messages
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from core.session_history.models import (
    EngineType,
    ToolCallSummary,
    UnifiedMessage,
    UnifiedSession,
)


def parse_gemini_session(file_path: Path) -> Optional[UnifiedSession]:
    """Parses a single Gemini JSONL session file into a UnifiedSession.

    Args:
        file_path: Path to the ``session-*.jsonl`` file.

    Returns:
        UnifiedSession if parsing succeeds, None otherwise.
    """
    if not file_path.exists() or file_path.suffix != ".jsonl":
        return None

    session_id = ""
    started_at = ""
    ended_at = ""
    model = ""
    messages: list[UnifiedMessage] = []

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

                # First line: session metadata
                if "sessionId" in row:
                    session_id = row.get("sessionId", "")
                    started_at = row.get("startTime", "") or started_at
                    ended_at = row.get("lastUpdated", "") or ended_at
                    continue

                # Skip $set patch lines (they update state, not messages)
                if "$set" in row:
                    patch = row["$set"]
                    if "lastUpdated" in patch:
                        ended_at = patch["lastUpdated"] or ended_at
                    continue

                # Message rows
                msg_type = row.get("type", "")
                timestamp = row.get("timestamp", "")

                if msg_type == "user":
                    content = _extract_gemini_user_content(row)
                    if content:
                        messages.append(UnifiedMessage(
                            role="user",
                            content=content,
                            timestamp=timestamp,
                        ))
                        if not started_at:
                            started_at = timestamp
                        ended_at = timestamp

                elif msg_type == "gemini":
                    content, tool_calls, mdl = _extract_gemini_response(row)
                    if mdl and not model:
                        model = mdl
                    if content or tool_calls:
                        messages.append(UnifiedMessage(
                            role="assistant",
                            content=content,
                            timestamp=timestamp,
                            tool_calls=tool_calls,
                            model=model,
                        ))
                        ended_at = timestamp

    except OSError:
        return None

    if not messages:
        return None

    if not session_id:
        session_id = file_path.stem

    # Project path: Gemini uses the project directory name under tmp/
    # file_path = ~/.gemini/tmp/<project>/chats/session-*.jsonl
    # parent = chats, parent.parent = <project>
    project_name = file_path.parent.parent.name

    return UnifiedSession(
        session_id=session_id,
        engine=EngineType.GEMINI,
        project_path=project_name,
        started_at=started_at,
        ended_at=ended_at,
        messages=messages,
        title="",
        model=model,
        source_file=str(file_path),
    )


def _extract_gemini_user_content(row: dict) -> str:
    """Extracts text from a Gemini user message row.

    Gemini user messages have a ``content`` array of objects with ``text``.

    Args:
        row: The parsed JSON line.

    Returns:
        str: The extracted plain text.
    """
    content = row.get("content")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and "text" in block:
                parts.append(block["text"])
        # Filter out session context markers
        text = "\n".join(parts).strip()
        # Remove <session_context> wrapper if present
        if text.startswith("<session_context>"):
            return ""
        return text
    return ""


def _extract_gemini_response(
    row: dict,
) -> tuple[str, list[ToolCallSummary], str]:
    """Extracts text, tool calls, and model from a Gemini response row.

    Args:
        row: The parsed JSON line with ``type: "gemini"``.

    Returns:
        tuple: (content_text, tool_calls, model_name)
    """
    content = row.get("content", "")
    if isinstance(content, list):
        # Some versions use a list of content blocks
        parts = []
        for block in content:
            if isinstance(block, dict) and "text" in block:
                parts.append(block["text"])
            elif isinstance(block, str):
                parts.append(block)
        content = "\n".join(parts)

    content = content.strip() if isinstance(content, str) else ""

    tool_calls: list[ToolCallSummary] = []
    raw_calls = row.get("toolCalls", [])
    if isinstance(raw_calls, list):
        for tc in raw_calls:
            if not isinstance(tc, dict):
                continue
            name = tc.get("name", "")
            args = tc.get("args", {})
            args_str = json.dumps(args, ensure_ascii=False) if args else ""
            if len(args_str) > 200:
                args_str = args_str[:200] + "..."
            result_preview = ""
            result = tc.get("result")
            if isinstance(result, list):
                for r in result:
                    if isinstance(r, dict) and "functionResponse" in r:
                        resp = r["functionResponse"].get("response", {})
                        result_str = json.dumps(resp, ensure_ascii=False)
                        result_preview = result_str[:200] if len(result_str) > 200 else result_str
                        break
            tool_calls.append(ToolCallSummary(
                name=name,
                args_preview=args_str,
                result_preview=result_preview,
            ))

    model = row.get("model", "")

    return content, tool_calls, model


def find_gemini_sessions(
    project_path: str, home: Optional[Path] = None
) -> list[UnifiedSession]:
    """Finds all Gemini sessions for a given project path.

    Gemini organizes sessions by project directory name under ``~/.gemini/tmp/``.
    The matching is done by comparing the project directory name with the last
    component of the provided ``project_path``.

    Args:
        project_path: The project directory to match against.
        home: Optional home directory override.

    Returns:
        list[UnifiedSession]: All sessions found, sorted by start time descending.
    """
    base = (home or Path.home()) / ".gemini" / "tmp"
    if not base.exists():
        return []

    # Gemini uses the project folder name (last component) as the directory
    target_name = Path(project_path).name.lower()
    sessions: list[UnifiedSession] = []

    for project_dir in base.iterdir():
        if not project_dir.is_dir():
            continue
        if project_dir.name.lower() != target_name:
            continue

        chats_dir = project_dir / "chats"
        if not chats_dir.exists():
            continue

        for jsonl_file in chats_dir.glob("*.jsonl"):
            session = parse_gemini_session(jsonl_file)
            if session:
                sessions.append(session)

    sessions.sort(key=lambda s: s.started_at, reverse=True)
    return sessions

"""Parser for Claude Code session history files.

Claude stores sessions as JSONL at:
    ~/.claude/projects/<encoded_project_path>/<session_uuid>.jsonl

Each line is a JSON object with a ``type`` field.  Relevant types:
  - ``user``      → user messages
  - ``assistant`` → assistant replies (with content[] blocks)
  - ``ai-title``  → auto-generated session title
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

from core.session_history.models import (
    EngineType,
    ToolCallSummary,
    UnifiedMessage,
    UnifiedSession,
)


def _decode_claude_project_path(dir_name: str) -> str:
    """Decodes Claude's dash-encoded directory name back to a file path.

    Claude encodes paths as: ``E:\\demo\\CodeAgent`` → ``E--demo-CodeAgent``.
    Note: single dashes in directory names (e.g. ``hearthstone-bot``) are
    ambiguous — they could be a path separator or part of the name.
    This function returns a best-guess decode; use ``_claude_dir_matches``
    for reliable project path matching.

    Args:
        dir_name: The dash-encoded directory name.

    Returns:
        str: The decoded file path (best guess).
    """
    m = re.match(r"^([A-Za-z])--(.*)$", dir_name)
    if m:
        drive, rest = m.groups()
        return f"{drive}:/{rest.replace('-', '/')}"
    return dir_name.replace("-", "/")


def _claude_dir_matches(dir_name: str, target_path: str) -> bool:
    """Checks if a Claude project directory name matches a target file path.

    Claude encodes ``E:\\demo\\hearthstone-bot`` as ``E--demo-hearthstone-bot``,
    but this is ambiguous because ``-`` is used both as a path separator and
    can appear in directory names. We work around this by comparing the
    dash-stripped forms of the path components.

    The algorithm:
    1. Normalize the target path to ``drive:/rest/of/path``
    2. Split the dir name: ``E--demo-hearthstone-bot`` → drive=``E``, rest=``demo-hearthstone-bot``
    3. Split the target rest into segments: ``demo``, ``hearthstone-bot``
    4. Try to match the segments sequentially against the dir name's segments

    A simpler heuristic that works in practice: compare the strings with all
    dashes and slashes removed, and check if the target path segments can be
    found in order within the dir name.

    Args:
        dir_name: The Claude projects directory name (e.g. ``E--demo-hearthstone-bot``).
        target_path: The target project path (e.g. ``E:/demo/hearthstone-bot``).

    Returns:
        bool: True if the directory matches the target path.
    """
    # Normalize target path
    target = target_path.replace("\\", "/").rstrip("/")
    m_target = re.match(r"^([A-Za-z]):/(.*)$", target)
    if not m_target:
        # Not a Windows drive path — fall back to exact dash-stripped comparison
        return dir_name.replace("-", "").lower() == target.replace("/", "").replace("-", "").lower()

    target_drive, target_rest = m_target.groups()
    target_segments = target_rest.split("/")

    # Parse dir name
    m_dir = re.match(r"^([A-Za-z])--(.*)$", dir_name)
    if not m_dir:
        return dir_name.replace("-", "").lower() == target.replace("/", "").replace("-", "").lower()

    dir_drive, dir_rest = m_dir.groups()
    if dir_drive.lower() != target_drive.lower():
        return False

    # Split dir_rest by single dashes, then try to match target segments
    # The key insight: we need to find a way to split "demo-hearthstone-bot"
    # into ["demo", "hearthstone-bot"] (not ["demo", "hearthstone", "bot"])
    # Strategy: greedy match from the target segments
    dir_parts = dir_rest.split("-")
    ti = 0  # target segment index
    di = 0  # dir parts index

    while ti < len(target_segments) and di < len(dir_parts):
        target_seg = target_segments[ti].lower()
        # Try to accumulate dir_parts until they match the target segment
        accumulated = dir_parts[di].lower()
        di += 1
        while accumulated != target_seg and di < len(dir_parts):
            # Try adding the next part with a dash
            accumulated += "-" + dir_parts[di].lower()
            di += 1
            # If accumulated is now longer than target_seg, no match
            if len(accumulated) > len(target_seg) + 10:
                break

        if accumulated == target_seg:
            ti += 1
        else:
            # Couldn't match this segment
            return False

    return ti == len(target_segments)


def parse_claude_session(file_path: Path) -> Optional[UnifiedSession]:
    """Parses a single Claude JSONL session file into a UnifiedSession.

    Args:
        file_path: Path to the ``<uuid>.jsonl`` file.

    Returns:
        UnifiedSession if parsing succeeds, None otherwise.
    """
    if not file_path.exists() or file_path.suffix != ".jsonl":
        return None

    session_id = file_path.stem
    messages: list[UnifiedMessage] = []
    title = ""
    started_at = ""
    ended_at = ""
    model = ""
    cwd = ""

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

                row_type = row.get("type", "")

                # Capture cwd from any row that has it
                if not cwd:
                    cwd = row.get("cwd", "")

                # Extract session title
                if row_type == "ai-title":
                    title = row.get("aiTitle", "")
                    continue

                # Skip non-message rows
                if row_type not in ("user", "assistant"):
                    continue

                # Skip meta/system wrapped messages
                if row.get("isMeta"):
                    continue

                msg = row.get("message")
                if not isinstance(msg, dict):
                    continue

                timestamp = row.get("timestamp", "")
                if not started_at and timestamp:
                    started_at = timestamp
                if timestamp:
                    ended_at = timestamp

                if row_type == "user":
                    content = _extract_user_content(msg)
                    if content:
                        messages.append(UnifiedMessage(
                            role="user",
                            content=content,
                            timestamp=timestamp,
                        ))

                elif row_type == "assistant":
                    text, tool_calls = _extract_assistant_content(msg)
                    if msg.get("model") and not model:
                        model = msg["model"]
                    if text or tool_calls:
                        messages.append(UnifiedMessage(
                            role="assistant",
                            content=text,
                            timestamp=timestamp,
                            tool_calls=tool_calls,
                            model=model,
                        ))

    except OSError:
        return None

    if not messages:
        return None

    # Decode project path from parent directory name
    project_dir = file_path.parent.name
    project_path = _decode_claude_project_path(project_dir)

    return UnifiedSession(
        session_id=session_id,
        engine=EngineType.CLAUDE,
        project_path=project_path or cwd,
        started_at=started_at,
        ended_at=ended_at,
        messages=messages,
        title=title,
        model=model,
        source_file=str(file_path),
    )


def _extract_user_content(msg: dict) -> str:
    """Extracts text content from a Claude user message dict.

    Claude user messages can have ``content`` as a string or as a list of
    content blocks.

    Args:
        msg: The ``message`` field from a JSONL row.

    Returns:
        str: The extracted plain text.
    """
    content = msg.get("content")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
        return "\n".join(parts).strip()
    return ""


def _extract_assistant_content(msg: dict) -> tuple[str, list[ToolCallSummary]]:
    """Extracts text and tool calls from a Claude assistant message dict.

    Assistant messages have a ``content`` list with block types:
    ``text``, ``thinking``, ``tool_use``.

    Args:
        msg: The ``message`` field from a JSONL row.

    Returns:
        tuple: (text_content, list_of_tool_call_summaries)
    """
    content = msg.get("content")
    if not isinstance(content, list):
        return "", []

    text_parts: list[str] = []
    tool_calls: list[ToolCallSummary] = []

    for block in content:
        if not isinstance(block, dict):
            continue

        block_type = block.get("type", "")

        if block_type == "text":
            text_parts.append(block.get("text", ""))

        elif block_type == "tool_use":
            name = block.get("name", "")
            input_data = block.get("input", {})
            # Create a short preview of the arguments
            args_str = json.dumps(input_data, ensure_ascii=False) if input_data else ""
            if len(args_str) > 200:
                args_str = args_str[:200] + "..."
            tool_calls.append(ToolCallSummary(
                name=name,
                args_preview=args_str,
            ))

    return "\n".join(text_parts).strip(), tool_calls


def find_claude_sessions(
    project_path: str, home: Optional[Path] = None
) -> list[UnifiedSession]:
    """Finds all Claude sessions for a given project path.

    Args:
        project_path: The project directory to match against.
        home: Optional home directory override.

    Returns:
        list[UnifiedSession]: All sessions found, sorted by start time descending.
    """
    base = (home or Path.home()) / ".claude" / "projects"
    if not base.exists():
        return []

    # Normalize the project path for comparison
    normalized_target = project_path.replace("\\", "/")

    sessions: list[UnifiedSession] = []

    for project_dir in base.iterdir():
        if not project_dir.is_dir():
            continue
        if not _claude_dir_matches(project_dir.name, normalized_target):
            continue

        for jsonl_file in project_dir.glob("*.jsonl"):
            session = parse_claude_session(jsonl_file)
            if session:
                # Use the actual project path from the first message's cwd if available
                if not session.project_path or session.project_path == _decode_claude_project_path(project_dir.name):
                    session.project_path = normalized_target
                sessions.append(session)

    sessions.sort(key=lambda s: s.started_at, reverse=True)
    return sessions

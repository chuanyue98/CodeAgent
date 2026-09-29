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
from pathlib import Path

from core.session_history.models import (
    EngineType,
    ToolCallSummary,
    UnifiedMessage,
    UnifiedSession,
)
from core.session_history.parse_cache import cached_file_parser
from core.session_history.parsers._subagents import (
    subagent_files,
    title_subagent_runs,
)
from core.session_history.parsers._synthetic import is_synthetic_user_content
from core.session_history.paths import (
    _claude_dir_matches,
    _decode_claude_project_path,
    _encode_claude_project_dir,
    claude_dir_matches,
    decode_claude_project_path,
    encode_claude_project_dir,
    strip_extended_length_prefix,
)

__all__ = [
    "_claude_dir_matches",
    "_decode_claude_project_path",
    "_encode_claude_project_dir",
    "claude_dir_matches",
    "decode_claude_project_path",
    "encode_claude_project_dir",
    "find_claude_sessions",
    "parse_claude_session",
]
from core.session_history.previews import args_preview, result_preview
from core.utils.long_paths import exists as path_exists
from core.utils.long_paths import list_dirs, list_files, long_path


@cached_file_parser
def parse_claude_session(file_path: Path) -> UnifiedSession | None:
    """Parses a single Claude JSONL session file into a UnifiedSession.

    Args:
        file_path: Path to the ``<uuid>.jsonl`` file.

    Returns:
        UnifiedSession if parsing succeeds, None otherwise.
    """
    if not path_exists(file_path) or file_path.suffix != ".jsonl":
        return None

    session_id = file_path.stem
    messages: list[UnifiedMessage] = []
    title = ""
    started_at = ""
    ended_at = ""
    model = ""
    cwd = ""
    agent = ""
    subagent_titles: dict[str, str] = {}
    # tool_use_id -> 调用；结果记在紧随其后的 user 行的 tool_result 块里。
    pending_tools: dict[str, ToolCallSummary] = {}

    try:
        # long_path, not a bare open: these files live under a directory named
        # after the whole project path, which passes MAX_PATH on a deep
        # enough project and makes the read fail on a file that exists.
        with open(long_path(file_path), encoding="utf-8") as f:
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

                # In a subagent transcript every row is attributed to the
                # agent that produced it ("general-purpose", "Explore", ...).
                if not agent:
                    agent = row.get("attributionAgent") or ""

                # A launcher records each subagent it starts, structured:
                # {"agentId": ..., "description": ..., "resolvedModel": ...}.
                launch = row.get("toolUseResult")
                if isinstance(launch, dict) and launch.get("agentId"):
                    description = str(launch.get("description") or "").strip()
                    if description:
                        subagent_titles[str(launch["agentId"])] = description

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
                    _attach_tool_results(msg, pending_tools)
                    content = _extract_user_content(msg)
                    if content and is_synthetic_user_content(content):
                        continue
                    if content:
                        messages.append(
                            UnifiedMessage(
                                role="user",
                                content=content,
                                timestamp=timestamp,
                            )
                        )

                elif row_type == "assistant":
                    text, tool_calls = _extract_assistant_content(msg, pending_tools)
                    if msg.get("model") and not model:
                        model = msg["model"]
                    if text or tool_calls:
                        messages.append(
                            UnifiedMessage(
                                role="assistant",
                                content=text,
                                timestamp=timestamp,
                                tool_calls=tool_calls,
                                model=model,
                            )
                        )

    except OSError:
        return None

    if not messages:
        return None

    # Claude's directory encoding is ambiguous for names containing dashes.
    # Prefer the exact cwd recorded in the JSONL whenever it is available.
    project_dir = file_path.parent.name
    project_path = cwd or _decode_claude_project_path(project_dir)

    return UnifiedSession(
        session_id=session_id,
        engine=EngineType.CLAUDE,
        project_path=project_path,
        started_at=started_at,
        ended_at=ended_at,
        messages=messages,
        title=title,
        model=model,
        source_file=str(file_path),
        agent=agent,
        subagent_titles=subagent_titles,
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


def _attach_tool_results(msg: dict, pending: dict[str, ToolCallSummary]) -> None:
    """把 user 行里的 ``tool_result`` 块填回对应的调用。"""
    content = msg.get("content")
    if not isinstance(content, list):
        return
    for block in content:
        if not isinstance(block, dict) or block.get("type") != "tool_result":
            continue
        call = pending.pop(str(block.get("tool_use_id", "")), None)
        if call is None:
            continue
        output = block.get("content")
        if isinstance(output, list):
            output = "\n".join(
                part.get("text", "")
                for part in output
                if isinstance(part, dict) and part.get("type") == "text"
            )
        call.result_preview = result_preview(output)
        call.result_captured = True


def _extract_assistant_content(
    msg: dict, pending: dict[str, ToolCallSummary] | None = None
) -> tuple[str, list[ToolCallSummary]]:
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
            call = ToolCallSummary(
                name=block.get("name", ""),
                args_preview=args_preview(block.get("input", {})),
            )
            tool_calls.append(call)
            if pending is not None and block.get("id"):
                pending[str(block["id"])] = call

    return "\n".join(text_parts).strip(), tool_calls


def find_claude_sessions(
    project_path: str | None = None, home: Path | None = None
) -> list[UnifiedSession]:
    """Finds all Claude sessions for a given project path.

    Args:
        project_path: The project directory to match against. If None,
            sessions from every project are returned unfiltered.
        home: Optional home directory override.

    Returns:
        list[UnifiedSession]: All sessions found, sorted by start time descending.
    """
    base = (home or Path.home()) / ".claude" / "projects"
    if not base.exists():
        return []

    # Normalized for comparison, but also assigned back onto the parsed
    # sessions below, so the case has to survive: only the extended-length
    # prefix is resolved here, not the spelling.
    normalized_target = (
        strip_extended_length_prefix(project_path.replace("\\", "/"))
        if project_path is not None
        else None
    )

    sessions: list[UnifiedSession] = []

    for project_dir in list_dirs(base):
        if not project_dir.is_dir():
            continue
        if normalized_target is not None and not _claude_dir_matches(
            project_dir.name, normalized_target
        ):
            continue

        candidates: list[tuple[Path, str]] = [
            (jsonl_file, "") for jsonl_file in list_files(project_dir, ".jsonl")
        ]
        # Subagent transcripts sit in ``<session_id>/subagents/``. Every row in
        # them repeats the *parent's* sessionId, so the owning session comes
        # from the directory and the child's own id from the file stem (which
        # is what ``parse_claude_session`` uses).
        for session_dir in list_dirs(project_dir):
            candidates.extend(subagent_files(session_dir))

        for jsonl_file, parent_session_id in candidates:
            session = parse_claude_session(jsonl_file)
            if not session:
                continue
            # Use the actual project path from the first message's cwd if available
            if normalized_target is not None and (
                not session.project_path
                or session.project_path == _decode_claude_project_path(project_dir.name)
            ):
                session.project_path = normalized_target
            session.parent_session_id = parent_session_id
            sessions.append(session)

    title_subagent_runs(sessions)
    sessions.sort(key=lambda s: s.started_at, reverse=True)
    return sessions

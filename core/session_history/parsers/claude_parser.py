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
from core.session_history.paths import strip_extended_length_prefix
from core.utils.long_paths import exists as path_exists
from core.utils.long_paths import list_dirs, list_files, long_path


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


def _encode_claude_project_dir(path: str) -> str:
    """Encodes a path the way Claude Code names ``~/.claude/projects/<dir>``.

    Every character that is not an ASCII letter or digit becomes a single
    ``-``: ``E:\\demo\\hearthstone-bot`` -> ``E--demo-hearthstone-bot``.

    The mapping is many-to-one — separators, dots and literal dashes all
    collapse onto ``-`` — so a directory name cannot be decoded back into an
    unambiguous path. Match by re-encoding a known path instead; see
    :func:`_claude_dir_matches`.

    Args:
        path: A file path (backslash or forward-slash separated).

    Returns:
        str: The dash-encoded directory name Claude Code would use for it.
    """
    return re.sub(r"[^A-Za-z0-9]", "-", path)


def _claude_dir_matches(dir_name: str, target_path: str) -> bool:
    """Checks if a Claude project directory name matches a target file path.

    Re-encodes ``target_path`` with :func:`_encode_claude_project_dir` and
    compares, rather than trying to invert that encoding — a decoder walking
    the dashes cannot tell a separator from a literal dash and can match the
    wrong project.

    Claude's own encoding stays ambiguous either way: ``.../my-project`` and
    ``.../my/project`` produce the same directory, so both report a match,
    exactly as Claude Code itself behaves.

    Args:
        dir_name: The Claude projects directory name (e.g. ``E--demo-hearthstone-bot``).
        target_path: The target project path (e.g. ``E:/demo/hearthstone-bot``).

    Returns:
        bool: True if the directory matches the target path.
    """
    normalized_target = strip_extended_length_prefix(
        target_path.replace("\\", "/")
    ).rstrip("/")
    if not normalized_target:
        return False
    return dir_name.lower() == _encode_claude_project_dir(normalized_target).lower()


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
                    text, tool_calls = _extract_assistant_content(msg)
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
            tool_calls.append(
                ToolCallSummary(
                    name=name,
                    args_preview=args_str,
                )
            )

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

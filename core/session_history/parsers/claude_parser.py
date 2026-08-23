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
from core.session_history.paths import strip_extended_length_prefix


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
    """Encodes a file path the way Claude Code encodes it for its
    ``~/.claude/projects/<dir>`` directory names.

    Verified directly against real ``~/.claude/projects`` directories,
    cross-checked with the ``cwd`` recorded inside their session JSONL
    files (see investigation notes in the PR/commit that introduced this):

      - ``E:\\demo\\hearthstone-bot``                              -> ``E--demo-hearthstone-bot``
      - ``E:\\me``                                                 -> ``E--me``
      - ``C:\\Users\\Administrator``                               -> ``C--Users-Administrator``
      - ``\\\\wsl.localhost\\Ubuntu-24.04\\home\\cy\\...\\CUITCCA``   -> ``--wsl-localhost-Ubuntu-24-04-home-cy-...-CUITCCA``

    The rule is simply: every character that is not an ASCII letter or
    digit (``:``, ``\\``, ``/``, ``.``, ``_``, space, and any literal ``-``
    already present in the path) is replaced 1:1 with a single ``-``. Note
    the WSL example above: the dots in ``Ubuntu-24.04`` become dashes just
    like the surrounding path separators, and the *existing* dash in
    ``Ubuntu-24.04`` is preserved as a dash too — so ``-`` in a dir name is
    inherently ambiguous about what it originally was.

    Because this collapses several distinct characters onto the same
    output character, it is a many-to-one mapping: a directory name cannot
    be decoded back into an unambiguous path in general (see
    ``_decode_claude_project_path``, which is a best-effort display
    fallback, not something to match against). It *can*, however, be
    produced unambiguously from a known path, which is what makes it
    reliable for matching — see ``_claude_dir_matches``.

    Args:
        path: A file path (backslash or forward-slash separated).

    Returns:
        str: The dash-encoded directory name Claude Code would use for it.
    """
    return re.sub(r"[^A-Za-z0-9]", "-", path)


def _claude_dir_matches(dir_name: str, target_path: str) -> bool:
    """Checks if a Claude project directory name matches a target file path.

    This used to try to *decode* ``dir_name`` back into a path using a
    length-based heuristic (accumulate dash-split parts until they got
    "close enough" to a target segment). That approach is fundamentally
    unreliable: Claude's encoding (see ``_encode_claude_project_dir``)
    collapses many different characters onto ``-``, so a decoder walking
    the dashes has no principled way to know whether a given ``-`` was a
    path separator, a literal dash in a directory name, a dot, or
    something else. In rare cases it could match a session history to the
    wrong project.

    Instead, we go the other way: re-encode the *known* ``target_path``
    with the same rule Claude uses and compare it directly to
    ``dir_name``. This mirrors exactly what Claude Code does when it
    creates the directory, so it can't misfire on ambiguous dashes — it
    never tries to invert the encoding, only to reproduce it.

    Note this does not (and cannot) resolve the underlying ambiguity in
    Claude's own encoding: e.g. a project at ``.../my-project`` and one at
    ``.../my/project`` both encode to ``...-my-project``, so Claude Code
    itself stores their sessions in the same directory. When that happens
    this function will correctly report a match for *both* target paths,
    same as Claude Code's own behavior — there is no information left to
    tell them apart after encoding.

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


def parse_claude_session(file_path: Path) -> UnifiedSession | None:
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

    for project_dir in base.iterdir():
        if not project_dir.is_dir():
            continue
        if normalized_target is not None and not _claude_dir_matches(
            project_dir.name, normalized_target
        ):
            continue

        for jsonl_file in project_dir.glob("*.jsonl"):
            session = parse_claude_session(jsonl_file)
            if session:
                # Use the actual project path from the first message's cwd if available
                if normalized_target is not None and (
                    not session.project_path
                    or session.project_path
                    == _decode_claude_project_path(project_dir.name)
                ):
                    session.project_path = normalized_target
                sessions.append(session)

    sessions.sort(key=lambda s: s.started_at, reverse=True)
    return sessions

"""Parser for CodeBuddy Code session history.

CodeBuddy Code stores sessions as JSONL at::

    ~/.codebuddy/projects/<encoded_project_path>/<session_uuid>.jsonl

Each line is a JSON object with a ``type`` field.  Relevant types:

  - ``message`` (role=user)                       → user messages
        (``content`` is a list of ``input_text`` blocks)
  - ``message`` (role=assistant, status=completed) → assistant replies
        (``content`` is a list of ``output_text`` blocks); the model lives in
        ``providerData.model`` — *not* at the top level of the message
  - ``ai-title``                                  → auto-generated session title
  - ``function_call`` / ``function_call_result``  → tool invocations
  - ``reasoning`` / ``summary`` / ``file-history-snapshot`` → skipped

Directory encoding (verified against real ``~/.codebuddy/projects``)::

    E:\\demo\\CodeAgent  →  e-demo-CodeAgent

i.e. the drive letter is lower-cased, every run of characters that is not an
ASCII letter or digit (``:``, ``\\``, ``/``, ...) collapses to a single
``-``, and all other characters keep their original case.  This is the same
*direction* as Claude's encoding but not the same result: Claude separates the
drive from the path with ``--`` (``E--demo-CodeAgent``) whereas CodeBuddy uses
a single ``-`` (``e-demo-CodeAgent``).
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
from core.session_history.paths import (
    normalize_project_path,
    strip_extended_length_prefix,
)


def _encode_codebuddy_project_dir(path: str) -> str:
    """Encodes a file path the way CodeBuddy Code names its
    ``~/.codebuddy/projects/<dir>`` directory.

    Rule (verified against real data):

      - the leading drive letter is lower-cased (``E:`` → ``e``)
      - every run of characters that is not an ASCII letter or digit
        (``:``, ``\\``, ``/`` ...) collapses to a single ``-``
      - all other characters keep their original case.

    Args:
        path: A file path (backslash or forward-slash separated).

    Returns:
        str: The dash-encoded directory name CodeBuddy Code would use.
    """
    p = path.replace("\\", "/")
    # Lower-case only the leading drive letter (``C:`` / ``c:``), leaving the
    # rest of the path's casing untouched.
    if re.match(r"^[A-Za-z]:", p):
        p = p[0].lower() + p[1:]
    # ``+`` collapses a run of separators (``:/``, ``:\``, ``\\`` ...) into a
    # single dash, matching how CodeBuddy names its project dirs
    # (``E:\demo\CodeAgent`` → ``e-demo-CodeAgent``).
    return re.sub(r"[^A-Za-z0-9]+", "-", p)


def _codebuddy_dir_matches(dir_name: str, target_path: str) -> bool:
    """Checks if a CodeBuddy projects directory name matches a target path.

    Mirrors :func:`claude_parser._claude_dir_matches`: re-encode the *known*
    ``target_path`` with CodeBuddy's rule and compare directly, rather than
    trying to invert the (ambiguous, many-to-one) encoding. This is only a
    pre-filter — the authoritative project path comes from each session's own
    ``cwd`` field via :func:`normalize_project_path`.

    Args:
        dir_name: A ``~/.codebuddy/projects`` directory name (e.g.
            ``e-demo-CodeAgent``).
        target_path: The target project path (e.g. ``E:/demo/CodeAgent``).

    Returns:
        bool: True if the directory matches the target path.
    """
    normalized_target = strip_extended_length_prefix(
        target_path.replace("\\", "/")
    ).rstrip("/")
    if not normalized_target:
        return False
    return dir_name.lower() == _encode_codebuddy_project_dir(normalized_target).lower()


def parse_codebuddy_session(file_path: Path) -> UnifiedSession | None:
    """Parses a single CodeBuddy JSONL session file into a UnifiedSession.

    Args:
        file_path: Path to the ``<uuid>.jsonl`` file.

    Returns:
        UnifiedSession if parsing yields at least one message, else None.
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
    # Tool calls are emitted as separate ``function_call`` / ``function_call_result``
    # lines. We attach each call to the assistant message that preceded it and
    # fill in its result when the matching ``function_call_result`` arrives.
    tool_calls_by_call_id: dict[str, ToolCallSummary] = {}

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

                # Capture cwd from the first row that carries one.
                if not cwd and row.get("cwd"):
                    cwd = row.get("cwd", "")

                ts = row.get("timestamp", "")
                if isinstance(ts, (int, float)) and not isinstance(ts, bool):
                    # CodeBuddy records epoch milliseconds; store as the raw
                    # string (aligned with the claude/codex passthrough style).
                    ts = str(int(ts))

                if row_type == "ai-title":
                    if not title:
                        title = row.get("aiTitle", "")
                    continue

                if row_type == "message":
                    role = row.get("role")
                    if role == "user":
                        content = _extract_text_content(
                            row.get("content"), "input_text"
                        )
                        if content:
                            if not started_at and ts:
                                started_at = ts
                            if ts:
                                ended_at = ts
                            messages.append(
                                UnifiedMessage(
                                    role="user",
                                    content=content,
                                    timestamp=ts,
                                )
                            )
                    elif role == "assistant" and row.get("status") == "completed":
                        text = _extract_text_content(
                            row.get("content"), "output_text"
                        )
                        msg_model = (row.get("providerData") or {}).get("model", "")
                        if msg_model and not model:
                            model = msg_model
                        if text:
                            if not started_at and ts:
                                started_at = ts
                            if ts:
                                ended_at = ts
                            messages.append(
                                UnifiedMessage(
                                    role="assistant",
                                    content=text,
                                    timestamp=ts,
                                    model=msg_model or model,
                                )
                            )
                    continue

                if row_type == "function_call":
                    name = row.get("name", "")
                    args = row.get("arguments")
                    if isinstance(args, (dict, list)):
                        args_str = json.dumps(args, ensure_ascii=False)
                    else:
                        args_str = str(args) if args is not None else ""
                    if len(args_str) > 200:
                        args_str = args_str[:200] + "..."
                    call_id = row.get("callId", "")
                    tc = ToolCallSummary(name=name, args_preview=args_str)
                    tool_calls_by_call_id[call_id] = tc
                    # Attach to the most recent assistant message.
                    for msg in reversed(messages):
                        if msg.role == "assistant":
                            msg.tool_calls.append(tc)
                            break
                    if ts:
                        ended_at = ts
                    continue

                if row_type == "function_call_result":
                    call_id = row.get("callId", "")
                    tc = tool_calls_by_call_id.get(call_id)
                    if tc is not None:
                        out = row.get("output")
                        if isinstance(out, dict):
                            result_text = out.get("text", "")
                        else:
                            result_text = str(out) if out is not None else ""
                        if len(result_text) > 200:
                            result_text = result_text[:200] + "..."
                        tc.result_preview = result_text
                    if ts:
                        ended_at = ts
                    continue

                # reasoning / summary / file-history-snapshot: intentionally
                # skipped — they are not part of the conversational content.
    except OSError:
        return None

    if not messages:
        return None

    # Prefer the cwd recorded in the JSONL; fall back to the encoded dir name.
    project_dir = file_path.parent.name
    project_path = cwd or project_dir

    return UnifiedSession(
        session_id=session_id,
        engine=EngineType.CODEBUDDY,
        project_path=project_path,
        started_at=started_at,
        ended_at=ended_at,
        messages=messages,
        title=title,
        model=model,
        source_file=str(file_path),
    )


def _extract_text_content(content, block_type: str) -> str:
    """Extracts plain text from a message ``content`` value.

    CodeBuddy content blocks use a ``type`` of ``input_text`` (user) or
    ``output_text`` (assistant) with a ``text`` field. A block may also be a
    bare string in some variants.

    Args:
        content: The ``content`` field of a message row.
        block_type: The block ``type`` to extract (``input_text`` / ``output_text``).

    Returns:
        str: The concatenated plain text (stripped), or "".
    """
    if isinstance(content, str):
        return content.strip()
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for block in content:
        if isinstance(block, str):
            parts.append(block)
            continue
        if not isinstance(block, dict):
            continue
        if block.get("type") == block_type:
            parts.append(block.get("text", ""))
    return "\n".join(p for p in parts if p).strip()


def find_codebuddy_sessions(
    project_path: str | None = None, home: Path | None = None
) -> list[UnifiedSession]:
    """Finds CodeBuddy sessions for a given project path.

    Args:
        project_path: The project directory to match against. If None,
            sessions from every project are returned unfiltered.
        home: Optional home directory override (for tests).

    Returns:
        list[UnifiedSession]: All sessions found, sorted by start time
        descending.
    """
    base = (home or Path.home()) / ".codebuddy" / "projects"
    if not base.exists():
        return []

    # Normalized for comparison; the spelling is preserved when assigned back.
    normalized_target = (
        strip_extended_length_prefix(project_path.replace("\\", "/"))
        if project_path is not None
        else None
    )

    sessions: list[UnifiedSession] = []
    for project_dir in base.iterdir():
        if not project_dir.is_dir():
            continue
        if normalized_target is not None and not _codebuddy_dir_matches(
            project_dir.name, normalized_target
        ):
            continue

        for jsonl_file in project_dir.glob("*.jsonl"):
            session = parse_codebuddy_session(jsonl_file)
            if session:
                # When the session's own cwd resolves to the target, surface
                # the canonical (user-supplied) spelling so the UI is stable.
                if normalized_target is not None and normalize_project_path(
                    session.project_path or ""
                ) == normalize_project_path(normalized_target):
                    session.project_path = normalized_target
                sessions.append(session)

    sessions.sort(key=lambda s: s.started_at, reverse=True)
    return sessions

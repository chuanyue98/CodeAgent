"""Parser for Freebuff (免费版 CLI) session history.

Freebuff stores one directory per conversation under::

    ~/.config/manicode/projects/<repo_name>/chats/<ISO-时间戳>/

containing ``chat-messages.json`` (the transcript), ``chat-meta.json``
(message count / first prompt / mtime), ``log.jsonl`` (app logs) and
``run-state.json`` (the live session state, incl. the real ``cwd`` and the
agent template). Layout verified against a real install (freebuff 0.0.168).

Notes on the format:

  - The ``chats/<dir>`` name is the conversation id -- it is what
    ``freebuff --continue <dir>`` resumes, so it doubles as
    :attr:`UnifiedSession.session_id` and as the resume key.
  - The top-level ``projects/<dir>`` name is the *git repo name*, not an
    encoded full path like Claude/CodeBuddy use. A local clone under any
    path maps to it by its repository name, and the authoritative local
    path of each conversation is read back from its own ``run-state.json``.
  - ``chat-messages.json`` is a JSON array, not JSONL. ``variant`` is
    ``user`` / ``ai`` / ``divider``. ``ai`` entries carry their text and tool
    calls as ``blocks``: ``text`` blocks (``textType`` ``text`` or
    ``reasoning`` -- reasoning is dropped) and ``tool`` blocks. Divider
    entries (mode switches etc.) carry no conversational content.
  - Message ids embed an epoch-millisecond timestamp (``user-1786515234478``,
    ``ai-1786515102492-581683dea203d``), which is what per-message ISO
    timestamps are derived from.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path

from core.session_history.models import (
    EngineType,
    ToolCallSummary,
    UnifiedMessage,
    UnifiedSession,
)
from core.session_history.parse_cache import cached_file_parser
from core.session_history.paths import normalize_project_path

_MANICODE_PROJECTS = Path(".config") / "manicode" / "projects"

#: ``2026-08-12T05-10-04.784Z`` → ``2026-08-12T05:10:04.784Z`` — the chat dir
#: name separates clock fields with dashes, everything else is ISO already.
_TS_DIR_RE = re.compile(r"^(\d{4}-\d{2}-\d{2}T)(\d{2})-(\d{2})-(\d{2})(.*)$")

#: Message ids embed their creation epoch (ms) as the first long digit run.
_EPOCH_MS_RE = re.compile(r"(\d{10,})")


def _dir_name_to_iso(dir_name: str) -> str:
    """Normalizes a chat-dir name to a sortable ISO 8601 timestamp."""
    return _TS_DIR_RE.sub(r"\1\2:\3:\4\5", dir_name)


def _to_iso8601(value: object) -> str:
    """Converts an epoch-milliseconds value to ISO 8601 (UTC), else \"\"."""
    if isinstance(value, bool):
        return ""
    if isinstance(value, (int, float)):
        epoch_ms = float(value)
    elif isinstance(value, str) and value.strip().isdigit():
        epoch_ms = float(value.strip())
    else:
        return ""
    try:
        moment = datetime.fromtimestamp(epoch_ms / 1000, tz=UTC)
    except (OverflowError, OSError, ValueError):
        return ""
    return moment.strftime("%Y-%m-%dT%H:%M:%S.") + f"{moment.microsecond // 1000:03d}Z"


def _ts_from_message_id(message_id: object) -> str:
    """Extracts the ISO timestamp embedded in a Freebuff message id."""
    if not isinstance(message_id, str):
        return ""
    match = _EPOCH_MS_RE.search(message_id)
    return _to_iso8601(match.group(1)) if match else ""


def _read_json_quiet(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _session_context(chat_dir: Path) -> tuple[str, str]:
    """``(project_path, model)`` recorded for one conversation.

    ``run-state.json`` carries the live ``cwd``/``projectRoot`` and the agent
    template id; both are best-effort (a killed run may leave no state file).
    """
    state = _read_json_quiet(chat_dir / "run-state.json")
    session_state = state.get("sessionState") if isinstance(state, dict) else {}
    if not isinstance(session_state, dict):
        return "", ""
    file_context = session_state.get("fileContext") or {}
    if not isinstance(file_context, dict):
        file_context = {}
    project_path = str(file_context.get("projectRoot") or file_context.get("cwd") or "")
    agent_state = session_state.get("mainAgentState") or {}
    model = (
        str(agent_state.get("agentType") or "")
        if isinstance(agent_state, dict)
        else ""
    )
    return project_path, model


def _message_timestamp(row: dict, chat_dir_name: str) -> str:
    """Per-message ISO timestamp: the id's epoch ms, else the dir name."""
    ts = _ts_from_message_id(row.get("id"))
    return ts or _dir_name_to_iso(chat_dir_name)


def _assistant_text(blocks: object) -> str:
    """Concatenates an ai message's visible text blocks (reasoning dropped)."""
    if not isinstance(blocks, list):
        return ""
    parts: list[str] = []
    for block in blocks:
        if not isinstance(block, dict):
            continue
        if block.get("type") != "text":
            continue
        if block.get("textType") not in (None, "text", ""):
            continue  # reasoning / summaries are not conversational content
        text = block.get("content")
        if isinstance(text, str) and text.strip():
            parts.append(text.strip())
    return "\n".join(parts)


def _tool_calls(blocks: object, ts: str) -> list[ToolCallSummary]:
    """Builds ToolCallSummary entries from a message's ``tool`` blocks."""
    if not isinstance(blocks, list):
        return []
    calls: list[ToolCallSummary] = []
    for block in blocks:
        if not isinstance(block, dict) or block.get("type") != "tool":
            continue
        name = str(block.get("toolName") or "")
        if not name:
            continue
        args = block.get("input")
        if isinstance(args, (dict, list)):
            args_str = json.dumps(args, ensure_ascii=False)
        elif isinstance(args, str):
            args_str = args
        else:
            args_str = ""
        if len(args_str) > 200:
            args_str = args_str[:200] + "..."
        output = block.get("output")
        if isinstance(output, str):
            result_str = output
        elif output is None:
            result_str = ""
        else:
            result_str = json.dumps(output, ensure_ascii=False)
        if len(result_str) > 200:
            result_str = result_str[:200] + "..."
        calls.append(
            ToolCallSummary(name=name, args_preview=args_str, result_preview=result_str)
        )
    return calls


@cached_file_parser
def parse_freebuff_session(file_path: Path) -> UnifiedSession | None:
    """Parses one Freebuff conversation's ``chat-messages.json``.

    Args:
        file_path: Path to a ``chat-messages.json`` (cache keyed on this file's
            stat -- Freebuff rewrites it as the conversation grows).

    Returns:
        UnifiedSession if at least one message parsed, else None.
    """
    if file_path.name != "chat-messages.json" or not file_path.exists():
        return None

    chat_dir = file_path.parent
    dir_name = chat_dir.name

    try:
        rows = json.loads(file_path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(rows, list):
        return None

    project_path, model = _session_context(chat_dir)
    meta = _read_json_quiet(chat_dir / "chat-meta.json")
    title = str(meta.get("firstPrompt") or "").strip()

    messages: list[UnifiedMessage] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        variant = row.get("variant")
        ts = _message_timestamp(row, dir_name)

        if variant == "user":
            content = row.get("content")
            if not isinstance(content, str) or not content.strip():
                continue
            messages.append(
                UnifiedMessage(role="user", content=content.strip(), timestamp=ts)
            )
            continue

        if variant == "ai":
            blocks = row.get("blocks")
            text = _assistant_text(blocks)
            calls = _tool_calls(blocks, ts)
            if not text and not calls:
                continue
            messages.append(
                UnifiedMessage(
                    role="assistant",
                    content=text,
                    timestamp=ts,
                    tool_calls=calls,
                )
            )
            continue

        # divider 及其它变体：无会话内容，跳过。

    if not messages:
        return None

    # Timestamps: prefer the ids embedded in the transcript; fall back to the
    # chat dir name (start) and chat-meta's mtime (end).
    stamps = [m.timestamp for m in messages if m.timestamp]
    if stamps:
        started_at = min(stamps)
        ended_at = max(stamps)
    else:
        started_at = _dir_name_to_iso(dir_name)
        ended_at = _to_iso8601(meta.get("messagesMtimeMs")) or started_at

    if not project_path:
        # The repo dir under projects/ is the closest thing to a location when
        # no run-state survived (e.g. a killed session's leftovers).
        project_path = chat_dir.parent.parent.name

    return UnifiedSession(
        session_id=dir_name,
        engine=EngineType.FREEBUFF,
        project_path=project_path,
        started_at=started_at,
        ended_at=ended_at,
        messages=messages,
        title=title,
        model=model,
        source_file=str(file_path),
    )


def _repo_dir_matches(dir_name: str, target_path: str) -> bool:
    """Whether a ``projects/<dir>`` (a git repo name) matches *target_path*.

    Freebuff keys history by repository name rather than by encoded full path,
    so the comparison is between the repo dir and the *basename* of the local
    checkout the user is browsing.
    """
    return dir_name.casefold() == Path(target_path).name.casefold()


def find_freebuff_sessions(
    project_path: str | None = None, home: Path | None = None
) -> list[UnifiedSession]:
    """Finds Freebuff conversations, optionally for one project (by repo name).

    Args:
        project_path: Local checkout directory to match against (matched on
            its basename / repo name). If None, sessions from every repo are
            returned unfiltered.
        home: Optional home directory override (for tests).

    Returns:
        list[UnifiedSession]: All conversations found, sorted by start time
        descending.
    """
    base = (home or Path.home()) / _MANICODE_PROJECTS
    if not base.is_dir():
        return []

    normalized_target = (
        project_path.replace("\\", "/").rstrip("/") if project_path else None
    )

    sessions: list[UnifiedSession] = []
    for repo_dir in base.iterdir():
        if not repo_dir.is_dir():
            continue
        if normalized_target is not None and not _repo_dir_matches(
            repo_dir.name, normalized_target
        ):
            continue
        chats_dir = repo_dir / "chats"
        if not chats_dir.is_dir():
            continue
        for chat_dir in sorted(chats_dir.iterdir()):
            if not chat_dir.is_dir():
                continue
            transcript = chat_dir / "chat-messages.json"
            if not transcript.is_file():
                # 崩溃残留（只有 log.jsonl）或空会话，无可解析内容。
                continue
            session = parse_freebuff_session(transcript)
            if not session:
                continue
            # 当会话自身记录的项目根与用户浏览的 checkout 归一化一致时，改用
            # 用户给出的拼写，让 UI 里的 workspace 稳定（与 codebuddy 一致）。
            if (
                normalized_target is not None
                and session.project_path
                and normalize_project_path(session.project_path)
                == normalize_project_path(normalized_target)
            ):
                session.project_path = normalized_target
            sessions.append(session)

    sessions.sort(key=lambda s: s.started_at, reverse=True)
    return sessions

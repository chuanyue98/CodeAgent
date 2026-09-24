"""Parser for Codex CLI session history files.

Codex stores sessions as JSONL at:
    ~/.codex/sessions/YYYY/MM/DD/rollout-<timestamp>-<session_id>.jsonl

Each line has ``{timestamp, type, payload}``.  Relevant ``type`` values:
  - ``session_meta``  → session ID, cwd, model
  - ``event_msg``     → user_message / agent_message sub-types
  - ``response_item`` → message / function_call / function_call_output

Codex 从 2026-08 起不再写 ``event_msg``/``user_message``，用户发言只剩
``response_item``，见 :data:`_SYNTHETIC_USER_PREFIXES` 附近的说明。
"""

from __future__ import annotations

import json
import re
import sqlite3
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
from core.session_history.previews import args_preview, result_preview
from core.utils.long_paths import exists as path_exists
from core.utils.long_paths import list_files, long_path

#: ``response_item`` 里 role=user 的那些不是人说的话：Codex 把环境快照、
#: 子代理回执、插件清单等都塞进 user 角色。老格式靠 ``event_msg`` 区分，新
#: 格式没有这层，只能按开头认。
_SYNTHETIC_USER_PREFIXES = (
    "<environment_context",
    "<user_instructions",
    "<recommended_plugins",
    "<subagent_notification",
    "<turn_aborted",
    "<codex_internal_context",
    "<user_action",
)

#: ``# AGENTS.md instructions for /path`` —— 项目约定文件的注入，不是用户输入。
_INSTRUCTIONS_HEADER = re.compile(r"^#\s+\S+\s+instructions for\s+\S")


def _is_synthetic_user_text(text: str) -> bool:
    """True when a ``role=user`` block is Codex's own injection, not a prompt."""
    if text.startswith(_SYNTHETIC_USER_PREFIXES):
        return True
    return bool(_INSTRUCTIONS_HEADER.match(text))


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
                parsed = parsed.replace(tzinfo=UTC)
            return parsed.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    if isinstance(timestamp, bool) or not isinstance(timestamp, (int, float)):
        return ""
    seconds = float(timestamp)
    if seconds > 100_000_000_000:
        seconds /= 1000
    try:
        return datetime.fromtimestamp(seconds, tz=UTC).strftime(
            "%Y-%m-%dT%H:%M:%S.000Z"
        )
    except (OverflowError, OSError, ValueError):
        return ""


@cached_file_parser
def parse_codex_session(file_path: Path) -> UnifiedSession | None:
    """Parses a single Codex JSONL session file into a UnifiedSession.

    Args:
        file_path: Path to the ``rollout-*.jsonl`` file.

    Returns:
        UnifiedSession if parsing succeeds, None otherwise.
    """
    if not path_exists(file_path) or file_path.suffix != ".jsonl":
        return None

    session_id = ""
    cwd = ""
    model = ""
    messages: list[UnifiedMessage] = []
    started_at = ""
    ended_at = ""

    # 调用发生在两段助手文本之间：先攒着，下一段文本到来前单独成一条消息插在
    # 它前面。挂到那段文本上会让目标引擎读成"先给答案、再去调用工具"。
    pending_tool_calls: list[ToolCallSummary] = []
    call_id_to_call: dict[str, ToolCallSummary] = {}

    def flush_tool_calls(timestamp: str) -> None:
        if not pending_tool_calls:
            return
        messages.append(
            UnifiedMessage(
                role="assistant",
                content="",
                timestamp=timestamp,
                tool_calls=pending_tool_calls[:],
                model=model,
            )
        )
        pending_tool_calls.clear()

    # 老格式同一句用户发言会出现两次（``response_item`` 一次、``event_msg``
    # 一次），先都收下，末尾发现文件里有 ``event_msg`` 版本时再把这批删掉。
    response_item_user_indices: list[int] = []
    saw_event_user_message = False

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
                            saw_event_user_message = True
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
                            flush_tool_calls(timestamp)
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
                            if _is_synthetic_user_text(text):
                                continue
                            response_item_user_indices.append(len(messages))
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
                        elif role == "assistant":
                            phase = payload.get("phase", "final")
                            if phase == "final" and text:
                                flush_tool_calls(timestamp)
                                # Codex records one assistant turn twice: an
                                # ``event_msg``/``agent_message`` for the UI and
                                # this ``response_item`` for the transcript.
                                if not (
                                    messages
                                    and messages[-1].role == "assistant"
                                    and messages[-1].content == text
                                ):
                                    messages.append(
                                        UnifiedMessage(
                                            role="assistant",
                                            content=text,
                                            timestamp=timestamp,
                                            model=model,
                                        )
                                    )
                                ended_at = timestamp

                    elif sub_type == "function_call":
                        name = payload.get("name", "")
                        args_raw = payload.get("arguments", "")
                        # Codex stores arguments as a JSON *string*; re-parse
                        # it so the preview clips values rather than tokens.
                        try:
                            args_obj = json.loads(args_raw) if args_raw else {}
                        except (json.JSONDecodeError, TypeError):
                            args_obj = args_raw if isinstance(args_raw, str) else ""

                        new_tc = ToolCallSummary(
                            name=name, args_preview=args_preview(args_obj)
                        )
                        pending_tool_calls.append(new_tc)
                        call_id = payload.get("call_id", "")
                        if call_id:
                            call_id_to_call[call_id] = new_tc

                    elif sub_type == "function_call_output":
                        call_id = payload.get("call_id", "")
                        output = payload.get("output", "")
                        pending = call_id_to_call.pop(call_id, None)
                        if isinstance(output, str) and pending is not None:
                            pending.result_preview = result_preview(output)
                            pending.result_captured = True

    except OSError:
        return None

    # 轮次被打断时调用后面没有文本，调用本身仍要留下。
    flush_tool_calls(ended_at)

    if saw_event_user_message:
        for index in reversed(response_item_user_indices):
            del messages[index]

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
        title="",  # 标题在 session_index.jsonl 里，由调用方补上
        model=model,
        source_file=str(file_path),
    )


def _thread_lineage(home: Path | None = None) -> dict[str, tuple[str, str]]:
    """``thread id -> (parent thread id, agent name)`` from Codex's state db.

    Codex runs a subagent as a thread of its own -- indistinguishable from a
    session someone started, unless the spawn edge it records is read back.
    Returns an empty map when the database or its columns are absent.
    """
    db_path = (home or Path.home()) / ".codex" / "state_5.sqlite"
    if not db_path.exists():
        return {}

    con = None
    try:
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        con.row_factory = sqlite3.Row
        edges = {
            row["child_thread_id"]: row["parent_thread_id"]
            for row in con.execute(
                "SELECT child_thread_id, parent_thread_id FROM thread_spawn_edges"
            )
            if row["child_thread_id"] and row["parent_thread_id"]
        }
        if not edges:
            return {}
        agents = {
            row["id"]: str(row["agent_role"] or row["agent_nickname"] or "")
            for row in con.execute("SELECT id, agent_role, agent_nickname FROM threads")
        }
    except sqlite3.Error:
        return {}
    finally:
        if con is not None:
            con.close()

    return {child: (parent, agents.get(child, "")) for child, parent in edges.items()}


def _thread_names(home: Path | None = None) -> dict[str, str]:
    """``thread id -> 名字``，取自 ``~/.codex/session_index.jsonl``。

    Codex 的 ``/rename`` 和 ca 接力写进去的标题都只在这里，rollout 文件里没有。
    同一 id 可能出现多行，以最后一行为准。
    """
    path = (home or Path.home()) / ".codex" / "session_index.jsonl"
    names: dict[str, str] = {}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return names
    for line in text.splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(row, dict):
            continue
        thread_id, name = row.get("id"), row.get("thread_name")
        if isinstance(thread_id, str) and isinstance(name, str) and name.strip():
            names[thread_id] = name.strip()
    return names


def find_codex_sessions(
    project_path: str | None = None, home: Path | None = None
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
        normalize_project_path(project_path) if project_path is not None else None
    )
    sessions: list[UnifiedSession] = []
    lineage = _thread_lineage(home)
    names = _thread_names(home)

    for jsonl_file in list_files(base, ".jsonl", recursive=True):
        session = parse_codex_session(jsonl_file)
        if session:
            session.parent_session_id, session.agent = lineage.get(
                session.session_id, ("", "")
            )
            session.title = names.get(session.session_id, "")
            if normalized_target is not None:
                normalized_cwd = normalize_project_path(session.project_path or "")
                if normalized_cwd != normalized_target:
                    continue
            sessions.append(session)

    sessions.sort(key=lambda s: s.started_at, reverse=True)
    return sessions

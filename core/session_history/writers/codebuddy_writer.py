"""Writer for converting UnifiedSession to CodeBuddy Code JSONL format.

Writes to: ~/.codebuddy/projects/<encoded_project_path>/<new_uuid>.jsonl

Each line is a JSON object matching CodeBuddy's native session format (the
same shape :func:`core.session_history.parsers.codebuddy_parser.parse_codebuddy_session`
reads back):

  - ``message`` (role=user)    → ``content`` is a list of ``input_text`` blocks
  - ``message`` (role=assistant, status=completed) → ``content`` is a list of
    ``output_text`` blocks; the model lives in ``providerData.model``
  - ``function_call`` / ``function_call_result`` → tool invocations (share ``callId``)
  - ``ai-title``               → auto-generated session title

Timestamps are epoch milliseconds (CodeBuddy's native unit), written as JSON
numbers the way CodeBuddy writes them itself.
"""

from __future__ import annotations

import json
import re
import time
import uuid
from pathlib import Path
from typing import Any

from core.session_history.models import EngineType
from core.session_history.parsers.codebuddy_parser import (
    _encode_codebuddy_project_dir,
)
from core.utils.atomic_write import atomic_write


def _recent_native_model(home: Path | None = None, scan_files: int = 6) -> str:
    """The model CodeBuddy most recently recorded in this install.

    CodeBuddy keeps it on ``providerData.model``. Read from its own files so
    a converted session names a model it can actually serve.

    Returns:
        The model id, or ``""`` when this install has no usable history.
    """
    root = (home or Path.home()) / ".codebuddy" / "projects"
    try:
        files = sorted(
            root.glob("*/*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True
        )[:scan_files]
    except OSError:
        return ""

    for path in files:
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for line in reversed(content.splitlines()):
            if '"model"' not in line:
                continue
            try:
                row = json.loads(line)
            except ValueError:
                continue
            provider = (row or {}).get("providerData") or {}
            model = provider.get("model") if isinstance(provider, dict) else None
            if isinstance(model, str) and model:
                return model
    return ""


def _codebuddy_cwd(path: str) -> str:
    """Returns the project path in CodeBuddy's on-disk ``cwd`` spelling.

    Windows paths get a lower-cased drive letter and back-slashes
    (``e:\\demo\\CodeAgent``), matching real files. POSIX paths stay as they
    are — back-slashing one names a directory that exists nowhere.
    """
    if not re.match(r"^[A-Za-z]:", path):
        return path
    p = path.replace("/", "\\")
    return p[0].lower() + p[1:]


def _to_codebuddy_ts(value: str | None) -> int:
    """Normalizes a UnifiedSession timestamp to epoch milliseconds.

    Returns an ``int``: real rows store the timestamp as a JSON number.
    """
    if not value:
        return int(time.time() * 1000)
    s = str(value).strip()
    if s.isdigit():
        return int(s)
    # ISO-8601 (e.g. Claude's ``2025-...Z``) → epoch ms.
    try:
        from datetime import datetime

        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return int(dt.timestamp() * 1000)
    except ValueError:
        return int(time.time() * 1000)


def write_codebuddy_session(session: Any) -> str:
    """Writes a UnifiedSession as a CodeBuddy Code JSONL session file.

    Creates a new session file in ``~/.codebuddy/projects/<encoded_path>/``
    with a new UUID.  The file follows CodeBuddy's native JSONL format so
    ``codebuddy --resume <id>`` can resume it.

    Args:
        session: The UnifiedSession to convert.

    Returns:
        str: The new session UUID (file stem).
    """
    new_session_id = str(uuid.uuid4())
    project_dir_name = _encode_codebuddy_project_dir(session.project_path)
    codebuddy_projects = Path.home() / ".codebuddy" / "projects" / project_dir_name
    codebuddy_projects.mkdir(parents=True, exist_ok=True)

    file_path = codebuddy_projects / f"{new_session_id}.jsonl"
    cwd = _codebuddy_cwd(session.project_path)

    lines: list[str] = []

    # Title, if present.
    if session.title:
        first_ts = _to_codebuddy_ts(
            getattr(session.messages[0], "timestamp", None)
            if session.messages
            else None
        )
        lines.append(
            json.dumps(
                {
                    "id": str(uuid.uuid4()),
                    "timestamp": first_ts,
                    "type": "ai-title",
                    "aiTitle": session.title,
                    "sessionId": new_session_id,
                    "cwd": cwd,
                },
                ensure_ascii=False,
            )
        )

    # Only a session that came *from* CodeBuddy carries a model CodeBuddy can
    # serve; "claude-opus-5" or "gpt-5-codex" in a CodeBuddy file names
    # nothing. CodeBuddy's own ids ("hy3") follow no pattern worth sniffing,
    # so the source engine is the only reliable test.
    source_model = session.model if session.engine == EngineType.CODEBUDDY else ""
    fallback_model = source_model or _recent_native_model() or ""

    previous_id: str | None = None

    for msg in session.messages:
        ts = _to_codebuddy_ts(getattr(msg, "timestamp", None))

        if msg.role == "user":
            # Annotated because the assistant branch below reassigns `row`
            # with a different value shape; without it the type is inferred
            # from this first literal alone and the two disagree.
            msg_id = str(uuid.uuid4())
            # Annotated because the assistant branch below reassigns `row`
            # with a different value shape; without it the type is inferred
            # from this first literal alone and the two disagree.
            row: dict[str, Any] = {
                "id": msg_id,
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": msg.content}],
                # Present on every one of CodeBuddy's own user rows. Empty is
                # fine -- absent is not, and that is the distinction the
                # OpenCode modelID crash was about.
                "providerData": {},
                "timestamp": ts,
                "cwd": cwd,
                "sessionId": new_session_id,
            }
            lines.append(json.dumps(row, ensure_ascii=False))
            previous_id = msg_id

        elif msg.role == "assistant":
            msg_id = str(uuid.uuid4())
            model = (msg.model if session.engine == EngineType.CODEBUDDY else "") or (
                fallback_model
            )
            row = {
                "id": msg_id,
                "type": "message",
                "role": "assistant",
                "status": "completed",
                "content": [{"type": "output_text", "text": msg.content}],
                "providerData": {"model": model} if model else {},
                # Chains the reply to the turn it answers. CodeBuddy writes
                # it on every assistant row; without it the transcript is a
                # flat list of orphans.
                "parentId": previous_id,
                "timestamp": ts,
                "cwd": cwd,
                "sessionId": new_session_id,
            }
            lines.append(json.dumps(row, ensure_ascii=False))
            previous_id = msg_id

            # Tool calls are emitted as separate function_call / result lines
            # so the parser re-attaches them to this assistant message.
            for tc in msg.tool_calls:
                call_id = f"call-{uuid.uuid4().hex[:16]}"
                try:
                    args_obj: Any = (
                        json.loads(tc.args_preview) if tc.args_preview else {}
                    )
                except (json.JSONDecodeError, TypeError):
                    args_obj = tc.args_preview or ""
                lines.append(
                    json.dumps(
                        {
                            "id": str(uuid.uuid4()),
                            "type": "function_call",
                            "name": tc.name,
                            "callId": call_id,
                            "arguments": args_obj,
                            "cwd": cwd,
                            "sessionId": new_session_id,
                            "timestamp": ts,
                        },
                        ensure_ascii=False,
                    )
                )
                result_text = tc.result_preview or ""
                lines.append(
                    json.dumps(
                        {
                            "id": str(uuid.uuid4()),
                            "type": "function_call_result",
                            "name": tc.name,
                            "callId": call_id,
                            "status": "completed",
                            "output": {"type": "text", "text": result_text},
                            "cwd": cwd,
                            "sessionId": new_session_id,
                            "timestamp": ts,
                        },
                        ensure_ascii=False,
                    )
                )

    # Write the file atomically to prevent corruption on crash
    atomic_write(file_path, "\n".join(lines) + "\n")
    return new_session_id

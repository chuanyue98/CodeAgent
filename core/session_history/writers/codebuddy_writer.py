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

from core.session_history.parsers.codebuddy_parser import (
    _encode_codebuddy_project_dir,
)
from core.utils.atomic_write import atomic_write


def _codebuddy_cwd(path: str) -> str:
    """Returns the project path in CodeBuddy's on-disk ``cwd`` spelling.

    Real ``~/.codebuddy/projects`` files store ``cwd`` with a lower-cased drive
    letter and back-slashes (``e:\\demo\\CodeAgent``), so we mirror that *on
    Windows paths only*. A POSIX path has to stay POSIX: back-slashing
    ``/home/cy/x`` into ``\\home\\cy\\x`` names a directory that exists on no
    Linux or macOS machine, so every session converted there pointed at a
    working directory CodeBuddy could not resolve.
    """
    if not re.match(r"^[A-Za-z]:", path):
        return path
    p = path.replace("/", "\\")
    return p[0].lower() + p[1:]


def _to_codebuddy_ts(value: str | None) -> int:
    """Normalizes a UnifiedSession timestamp to epoch milliseconds.

    Returns an ``int``, not a string: real ``~/.codebuddy/projects`` rows store
    ``"timestamp": 1787547364552`` as a JSON number, and this module used to
    quote it. The parser here tolerates both, so the quoting only showed up
    once CodeBuddy itself read the file back.
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

    # Title, if present. Stamped with the first turn's time and the session id,
    # the way real ``ai-title`` rows carry them.
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

    for msg in session.messages:
        ts = _to_codebuddy_ts(getattr(msg, "timestamp", None))

        if msg.role == "user":
            # Annotated because the assistant branch below reassigns `row`
            # with a different value shape; without it the type is inferred
            # from this first literal alone and the two disagree.
            row: dict[str, Any] = {
                "id": str(uuid.uuid4()),
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": msg.content}],
                "timestamp": ts,
                "cwd": cwd,
                "sessionId": new_session_id,
            }
            lines.append(json.dumps(row, ensure_ascii=False))

        elif msg.role == "assistant":
            model = msg.model or session.model or ""
            row = {
                "id": str(uuid.uuid4()),
                "type": "message",
                "role": "assistant",
                "status": "completed",
                "content": [{"type": "output_text", "text": msg.content}],
                "providerData": {"model": model} if model else {},
                "timestamp": ts,
                "cwd": cwd,
                "sessionId": new_session_id,
            }
            lines.append(json.dumps(row, ensure_ascii=False))

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

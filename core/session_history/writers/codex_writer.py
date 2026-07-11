"""Writer for converting UnifiedSession to Codex CLI JSONL format.

Writes to: ~/.codex/sessions/YYYY/MM/DD/rollout-<timestamp>-<uuid>.jsonl

Each line has ``{timestamp, type, payload}`` matching Codex's native format.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.session_history.models import UnifiedSession


def _now_iso() -> str:
    """Returns current UTC time as ISO 8601."""
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _now_filename() -> str:
    """Returns current UTC time formatted for Codex filename (dashes for colons)."""
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H-%M-%S")


def write_codex_session(session: UnifiedSession) -> str:
    """Writes a UnifiedSession as a Codex CLI JSONL session file.

    Creates a new session file in ``~/.codex/sessions/YYYY/MM/DD/`` with
    a new UUID v7-style ID. The file follows Codex's native JSONL format
    so ``codex continue`` can resume it.

    Args:
        session: The UnifiedSession to convert.

    Returns:
        str: The new session ID.
    """
    new_session_id = str(uuid.uuid4())
    now = _now_iso()
    now_fname = _now_filename()
    cwd = session.project_path

    # Build file path
    today = datetime.now(tz=timezone.utc)
    sessions_dir = Path.home() / ".codex" / "sessions"
    day_dir = (
        sessions_dir / f"{today.year:04d}" / f"{today.month:02d}" / f"{today.day:02d}"
    )
    day_dir.mkdir(parents=True, exist_ok=True)

    filename = f"rollout-{now_fname}-{new_session_id}.jsonl"
    file_path = day_dir / filename

    lines: list[str] = []

    # Line 1: session_meta
    meta = {
        "timestamp": now,
        "type": "session_meta",
        "payload": {
            "id": new_session_id,
            "timestamp": now,
            "cwd": cwd,
            "originator": "codex-tui",
            "cli_version": "0.1.0",
            "source": "cli",
            "thread_source": "user",
            "model_provider": "openai",
        },
    }
    lines.append(json.dumps(meta, ensure_ascii=False))

    # Write each message as event_msg + response_item
    for msg in session.messages:
        if msg.role == "user":
            # event_msg: user_message
            user_event = {
                "timestamp": msg.timestamp or now,
                "type": "event_msg",
                "payload": {
                    "type": "user_message",
                    "message": msg.content,
                    "images": [],
                    "local_images": [],
                    "text_elements": [],
                },
            }
            lines.append(json.dumps(user_event, ensure_ascii=False))

            # response_item: message (user)
            user_resp = {
                "timestamp": msg.timestamp or now,
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": msg.content}],
                },
            }
            lines.append(json.dumps(user_resp, ensure_ascii=False))

        elif msg.role == "assistant":
            # event_msg: agent_message
            agent_event = {
                "timestamp": msg.timestamp or now,
                "type": "event_msg",
                "payload": {
                    "type": "agent_message",
                    "message": msg.content,
                    "phase": "final",
                    "memory_citation": None,
                },
            }
            lines.append(json.dumps(agent_event, ensure_ascii=False))

            # response_item: message (assistant)
            assistant_resp = {
                "timestamp": msg.timestamp or now,
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": msg.content}],
                    "phase": "final",
                },
            }
            lines.append(json.dumps(assistant_resp, ensure_ascii=False))

            # Write tool calls as function_call + function_call_output
            for tc in msg.tool_calls:
                call_id = f"call_{uuid.uuid4().hex[:24]}"
                func_call = {
                    "timestamp": msg.timestamp or now,
                    "type": "response_item",
                    "payload": {
                        "type": "function_call",
                        "name": tc.name,
                        "arguments": tc.args_preview,
                        "call_id": call_id,
                    },
                }
                lines.append(json.dumps(func_call, ensure_ascii=False))

                if tc.result_preview:
                    func_output = {
                        "timestamp": msg.timestamp or now,
                        "type": "response_item",
                        "payload": {
                            "type": "function_call_output",
                            "call_id": call_id,
                            "output": tc.result_preview,
                        },
                    }
                    lines.append(json.dumps(func_output, ensure_ascii=False))

    # Write the file
    file_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # Also update the session index
    _update_session_index(new_session_id, session)

    return new_session_id


def _update_session_index(session_id: str, session: UnifiedSession) -> None:
    """Appends a new entry to Codex's session_index.jsonl.

    Args:
        session_id: The new session ID.
        session: The source session (for title).
    """
    index_path = Path.home() / ".codex" / "session_index.jsonl"
    title = session.title or session.first_user_message[:80] or "Converted session"

    entry = {
        "id": session_id,
        "thread_name": title[:200],
        "updated_at": _now_iso(),
    }

    # Append to the index file
    with open(index_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

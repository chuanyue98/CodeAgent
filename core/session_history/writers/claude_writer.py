"""Writer for converting UnifiedSession to Claude Code JSONL format.

Writes to: ~/.claude/projects/<encoded_project_path>/<new_uuid>.jsonl

Each line is a JSON object matching Claude's native session format.
Only user and assistant messages are written; tool calls are embedded
in assistant message content blocks.
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from core.utils.atomic_write import atomic_write
from core.utils.long_paths import list_files, long_path, mtime

if TYPE_CHECKING:
    from core.session_history.models import UnifiedSession


def _encode_project_path(path: str) -> str:
    """Encodes a file path into Claude's dash-encoded directory name format.

    ``E:/demo/CodeAgent`` → ``E--demo-CodeAgent``

    Args:
        path: The file path to encode.

    Returns:
        str: The encoded directory name.
    """
    path = path.replace("\\", "/")
    m = re.match(r"^([A-Za-z]):/(.*)$", path)
    if m:
        drive, rest = m.groups()
        return f"{drive}--{rest.replace('/', '-')}"
    return path.replace("/", "-")


def _now_iso() -> str:
    """Returns the current UTC time as an ISO 8601 string."""
    return datetime.now(tz=UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z")


#: What Claude itself records on an assistant turn it did not obtain from a
#: model call. Converted turns did not come from Claude at all, so this is
#: the honest label when the install offers nothing better -- and unlike a
#: hardcoded model id it cannot go stale.
SYNTHETIC_MODEL = "<synthetic>"

#: Only reached on an install with no Claude history to read a real version
#: out of, which is also an install where nothing will resume this file.
CLI_VERSION_FALLBACK = "2.1.0"


def _recent_native_meta(
    home: Path | None = None, scan_files: int = 8
) -> tuple[str | None, str | None]:
    """The ``model`` and ``version`` Claude last recorded in this install.

    Resolved from Claude's own files rather than invented: a converted
    session's model name ("gpt-5-codex", "hy3", ...) is not a Claude model,
    and hardcoded values age out of existence -- this writer claimed
    ``claude-sonnet-4-20250514`` and CLI version ``2.1.0`` long after
    installs had moved to ``claude-opus-5`` and ``2.1.24x``.

    Args:
        home: Home directory override, for tests.
        scan_files: How many of the newest session files to look through.

    Returns:
        ``(model, version)``, either of which is None when this install has
        no usable history yet.
    """
    root = (home or Path.home()) / ".claude" / "projects"
    try:
        files = sorted(
            list_files(root, ".jsonl", recursive=True), key=mtime, reverse=True
        )[:scan_files]
    except OSError:
        return None, None

    model: str | None = None
    version: str | None = None
    for path in files:
        try:
            with open(long_path(path), encoding="utf-8", errors="replace") as handle:
                content = handle.read()
        except OSError:
            continue
        for line in reversed(content.splitlines()):
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if not isinstance(row, dict) or row.get("type") != "assistant":
                continue
            if version is None and isinstance(row.get("version"), str):
                version = row["version"]
            if model is None:
                message = row.get("message") or {}
                candidate = message.get("model") if isinstance(message, dict) else None
                # Skip Claude's own marker for turns it did not generate --
                # copying it back would just re-emit the fallback.
                if (
                    isinstance(candidate, str)
                    and candidate
                    and candidate != SYNTHETIC_MODEL
                ):
                    model = candidate
            if model and version:
                return model, version
    return model, version


def _claude_model(*candidates: str) -> str | None:
    """The first candidate that names a Claude model.

    A cross-engine conversion carries the *source* engine's model on the
    session and on each message ("gpt-5-codex", "hy3", "x-preview-f-free"),
    and writing that into a Claude session file names a model Claude cannot
    resume with. Only a claude-* id is worth preserving -- which happens on
    a Claude-to-Claude copy, where keeping the real per-message model is
    strictly better than overwriting it with the install's current default.
    """
    for candidate in candidates:
        if isinstance(candidate, str) and candidate.startswith("claude-"):
            return candidate
    return None


def _git_branch(project_path: str) -> str:
    """The branch name Claude would record for *project_path*.

    Read straight out of ``.git/HEAD`` rather than by shelling out: this runs
    once per conversion and a subprocess would be the slowest thing in it.
    Detached heads report ``HEAD``, matching what Claude's own rows carry.
    """
    head = Path(project_path) / ".git" / "HEAD"
    try:
        content = head.read_text(encoding="utf-8").strip()
    except OSError:
        return ""
    if content.startswith("ref:"):
        return content.split("/", 2)[-1] if "/" in content else ""
    return "HEAD" if content else ""


def write_claude_session(session: UnifiedSession) -> str:
    """Writes a UnifiedSession as a Claude Code JSONL session file.

    Creates a new session file in ``~/.claude/projects/<encoded_path>/``
    with a new UUID.  The file follows Claude's native JSONL format so
    ``claude -r <id>`` can resume it.

    Args:
        session: The UnifiedSession to convert.

    Returns:
        str: The new session UUID (file stem).
    """
    new_session_id = str(uuid.uuid4())
    project_dir_name = _encode_project_path(session.project_path)
    claude_projects = Path.home() / ".claude" / "projects" / project_dir_name
    # No mkdir here: atomic_write creates the parent, and it does so through
    # the long-path spelling. Claude names this directory after the entire
    # project path, so a deep project passes MAX_PATH and a plain
    # Path.mkdir fails on a directory it is perfectly able to create.
    file_path = claude_projects / f"{new_session_id}.jsonl"
    cwd = (
        session.project_path.replace("/", "\\")
        if re.match(r"^[A-Za-z]:", session.project_path)
        else session.project_path
    )

    lines: list[str] = []
    now = _now_iso()
    # Resolved once: scanning history per message would re-read the same
    # files for every assistant turn in a 1000-message transcript.
    native_model, native_version = _recent_native_meta()
    fallback_model = native_model or SYNTHETIC_MODEL
    cli_version = native_version or CLI_VERSION_FALLBACK
    git_branch = _git_branch(session.project_path)

    # Write messages as JSONL rows
    prev_uuid = None

    for msg in session.messages:
        msg_uuid = str(uuid.uuid4())

        if msg.role == "user":
            row = {
                "parentUuid": prev_uuid,
                "isSidechain": False,
                "type": "user",
                "message": {
                    "role": "user",
                    "content": msg.content,
                },
                "uuid": msg_uuid,
                "timestamp": msg.timestamp or now,
                "permissionMode": "default",
                "origin": {"kind": "human"},
                "promptSource": "typed",
                "userType": "external",
                "entrypoint": "cli",
                "cwd": cwd,
                "sessionId": new_session_id,
                "version": cli_version,
                "gitBranch": git_branch,
            }
            lines.append(json.dumps(row, ensure_ascii=False))
            prev_uuid = msg_uuid

        elif msg.role == "assistant":
            # Build content blocks: text + tool_use
            content_blocks = []
            if msg.content:
                content_blocks.append({"type": "text", "text": msg.content})
            for tc in msg.tool_calls:
                try:
                    input_obj: Any = (
                        json.loads(tc.args_preview) if tc.args_preview else {}
                    )
                except (json.JSONDecodeError, TypeError):
                    input_obj = {}
                content_blocks.append(
                    {
                        "type": "tool_use",
                        "id": f"toolu_{uuid.uuid4().hex[:24]}",
                        "name": tc.name,
                        "input": input_obj,
                    }
                )

            if not content_blocks:
                continue

            message: dict[str, Any] = {
                "model": _claude_model(msg.model, session.model) or fallback_model,
                "id": f"msg_{uuid.uuid4().hex[:24]}",
                "type": "message",
                "role": "assistant",
                "content": content_blocks,
                "stop_reason": "end_turn",
                "stop_sequence": None,
                # Present on every one of Claude's own assistant messages and
                # null on all but a handful (they carry cache-miss detail we
                # have nothing truthful to put in). Same failure class as the
                # OpenCode modelID crash: a field the reader dereferences is
                # not optional just because it is usually empty.
                "stop_details": None,
                "diagnostics": None,
                "usage": {
                    "input_tokens": 0,
                    "output_tokens": 0,
                },
            }
            row = {
                "parentUuid": prev_uuid,
                "isSidechain": False,
                "type": "assistant",
                "message": message,
                "uuid": msg_uuid,
                "timestamp": msg.timestamp or now,
                "sessionId": new_session_id,
                "cwd": cwd,
                "version": cli_version,
                "entrypoint": "cli",
                "userType": "external",
                "gitBranch": git_branch,
            }
            lines.append(json.dumps(row, ensure_ascii=False))
            prev_uuid = msg_uuid

    # Write the file atomically to prevent corruption on crash
    atomic_write(file_path, "\n".join(lines) + "\n")
    return new_session_id

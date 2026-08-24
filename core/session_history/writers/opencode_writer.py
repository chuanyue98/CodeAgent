"""Writer for converting UnifiedSession to OpenCode SQLite format.

Writes to: ~/.local/share/opencode/opencode.db

Inserts new rows into the ``session``, ``message``, and ``part`` tables
following OpenCode's native schema.
"""

from __future__ import annotations

import json
import shutil
import sqlite3
import subprocess
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.session_history.models import UnifiedSession


# OpenCode's fallback project for directories that are not git repositories.
_GLOBAL_PROJECT_ID = "global"


def _now_ms() -> int:
    """Returns current UTC time as Unix milliseconds."""
    return int(datetime.now(tz=UTC).timestamp() * 1000)


def _opencode_project_id(worktree: str) -> str:
    """Returns the project id OpenCode itself would use for *worktree*.

    OpenCode keys a git worktree's project on the repository's root commit,
    and falls back to the shared ``global`` project elsewhere. It filters
    ``session list`` on ``session.project_id``, so an id we invent instead
    would hide the converted session from the list and the TUI picker.

    Args:
        worktree: The project's forward-slash-normalized worktree path.

    Returns:
        str: The root-commit SHA, or ``"global"`` when *worktree* is not a git
        repository (or git is unavailable).
    """
    if not shutil.which("git"):
        return _GLOBAL_PROJECT_ID
    try:
        proc = subprocess.run(
            ["git", "-C", worktree, "rev-list", "--max-parents=0", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return _GLOBAL_PROJECT_ID
    if proc.returncode != 0:
        return _GLOBAL_PROJECT_ID
    # A repository can have several root commits (an unrelated history was
    # merged in); OpenCode keys off the first line, so match that.
    root = proc.stdout.strip().splitlines()
    return root[0].strip() if root and root[0].strip() else _GLOBAL_PROJECT_ID


def _find_or_create_project(con: sqlite3.Connection, worktree: str, now_ms: int) -> str:
    """Returns the ``project`` row id to hang the converted session off.

    Inserts the row only when OpenCode has not created it yet. Matching on the
    id rather than on ``worktree`` matters: a directory can carry a stale row
    from an older OpenCode id scheme, which would hide the session again.

    Args:
        con: Open connection to the OpenCode SQLite database.
        worktree: The project's forward-slash-normalized worktree path.
        now_ms: Current time in Unix milliseconds, used if a row is created.

    Returns:
        str: The id of the matching (or newly created) project row.
    """
    project_id = _opencode_project_id(worktree)

    row = con.execute("SELECT id FROM project WHERE id = ?", (project_id,)).fetchone()
    if row:
        return row[0]

    con.execute(
        """INSERT INTO project (
            id, worktree, vcs, name, time_created, time_updated, sandboxes
        ) VALUES (?, ?, ?, NULL, ?, ?, '[]')""",
        (
            project_id,
            "/" if project_id == _GLOBAL_PROJECT_ID else worktree,
            None if project_id == _GLOBAL_PROJECT_ID else "git",
            now_ms,
            now_ms,
        ),
    )
    return project_id


def _find_opencode_db() -> Path | None:
    """Locates the OpenCode database file.

    Returns:
        Path to the database, or None if not found.
    """
    candidates = [
        Path.home() / ".local" / "share" / "opencode" / "opencode.db",
        Path.home() / ".opencode" / "opencode.db",
    ]
    for path in candidates:
        if path.exists():
            return path
    return None


def _last_used_model(con: sqlite3.Connection) -> tuple[str, str] | None:
    """The (modelID, providerID) OpenCode itself most recently ran with.

    Taken from OpenCode's own rows rather than from the source engine: the
    converted session's model name ("claude-opus-4", "gpt-5-codex", ...)
    names no OpenCode provider, and OpenCode resolves the model to continue
    with from the transcript. A value it wrote itself is one it can serve.

    Returns None when this install has no session carrying a model yet, in
    which case the caller omits the fields rather than inventing a provider.
    """
    try:
        rows = con.execute(
            "SELECT model FROM session WHERE model IS NOT NULL "
            "ORDER BY time_created DESC LIMIT 20"
        ).fetchall()
    except sqlite3.Error:
        return None

    for (raw,) in rows:
        try:
            model = json.loads(raw)
        except (TypeError, ValueError):
            continue
        model_id = model.get("id")
        provider_id = model.get("providerID")
        if model_id and provider_id:
            return str(model_id), str(provider_id)
    return None


def write_opencode_session(session: UnifiedSession) -> str:
    """Writes a UnifiedSession into the OpenCode SQLite database.

    Inserts a new session row and all associated messages and parts.
    The session can be resumed via OpenCode's native session selection.

    Args:
        session: The UnifiedSession to convert.

    Returns:
        str: The new session ID (OpenCode format: ses_<id>).

    Raises:
        FileNotFoundError: If the OpenCode database is not found.
    """
    db_path = _find_opencode_db()
    if not db_path:
        raise FileNotFoundError("OpenCode database not found. Is OpenCode installed?")

    new_session_id = f"ses_{uuid.uuid4().hex[:24]}"
    now_ms = _now_ms()
    worktree = session.project_path.replace("\\", "/")

    # NULL, so OpenCode falls back to the user's configured default. The
    # source engine's model name resolves to no OpenCode provider, and an
    # unresolvable model fails the first turn after resuming.
    session_model = None

    con = sqlite3.connect(str(db_path))

    try:
        project_id = _find_or_create_project(con, worktree, now_ms)
        # Resolved once for the whole transcript; every assistant turn we
        # write claims the same model, which is what OpenCode does within a
        # session that never switched models.
        last_model = _last_used_model(con)

        # Insert session row
        con.execute(
            """INSERT INTO session (
                id, project_id, parent_id, slug, directory, title, version,
                model, cost, tokens_input, tokens_output, tokens_reasoning,
                tokens_cache_read, tokens_cache_write,
                time_created, time_updated, time_compacting, time_archived,
                workspace_id, path, agent, metadata,
                summary_additions, summary_deletions, summary_files,
                summary_diffs, share_url, permission
            ) VALUES (?, ?, NULL, ?, ?, ?, ?, ?, 0, 0, 0, 0, 0, 0, ?, ?, NULL, NULL, NULL, ?, NULL, '{}', 0, 0, 0, NULL, NULL, NULL)""",
            (
                new_session_id,
                project_id,
                new_session_id[-12:],  # slug
                worktree,
                session.title or session.first_user_message[:80] or "Converted session",
                "1.0.0",
                session_model,
                now_ms,  # time_created
                now_ms,  # time_updated
                worktree,  # path
            ),
        )

        # Insert messages and parts
        previous_message_id: str | None = None
        for i, msg in enumerate(session.messages):
            msg_id = f"msg_{uuid.uuid4().hex[:24]}"
            msg_time = now_ms + i * 1000  # stagger timestamps

            # ``parentID`` chains each assistant reply to the turn it
            # answered; user messages start a turn and carry no parent.
            msg_data = {
                "parentID": previous_message_id if msg.role == "assistant" else None,
                "role": msg.role,
                "mode": "build",
                "agent": "build",
                "path": {"cwd": worktree, "root": worktree},
                "cost": 0,
                # OpenCode's SessionCompaction reads tokens.cache.{read,write}
                # on every message; a bare tokens object (or a user message
                # missing it) makes resume crash with
                # "TypeError: undefined is not an object (evaluating
                # 'e.tokens.cache.read')", so always emit cache and use null
                # tokens for user turns exactly like OpenCode writes natively.
                "tokens": (
                    {
                        "total": 0,
                        "input": 0,
                        "output": 0,
                        "reasoning": 0,
                        "cache": {"read": 0, "write": 0},
                    }
                    if msg.role == "assistant"
                    else None
                ),
                "time": {"created": msg_time, "completed": msg_time + 500},
                "finish": "stop",
            }

            # OpenCode resolves which model continues the conversation from
            # the transcript's last assistant turn. Without these two fields
            # that lookup yields undefined and the first prompt after a
            # convert dies inside SessionPrompt.run with
            # "TypeError: undefined is not an object (evaluating
            # 'X.model.modelID')" -- the transcript loads and renders fine,
            # so the session looks converted right up until you type.
            # Same failure class as the tokens.cache.read crash above.
            if msg.role == "assistant" and last_model is not None:
                msg_data["modelID"], msg_data["providerID"] = last_model

            con.execute(
                """INSERT INTO message (id, session_id, time_created, time_updated, data)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    msg_id,
                    new_session_id,
                    msg_time,
                    msg_time,
                    json.dumps(msg_data, ensure_ascii=False),
                ),
            )

            previous_message_id = msg_id

            # Insert text part
            if msg.content:
                part_data = {"type": "text", "text": msg.content}
                con.execute(
                    """INSERT INTO part (id, message_id, session_id, time_created, time_updated, data)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (
                        f"prt_{uuid.uuid4().hex[:24]}",
                        msg_id,
                        new_session_id,
                        msg_time,
                        msg_time,
                        json.dumps(part_data, ensure_ascii=False),
                    ),
                )

            # Insert tool call parts
            for tc in msg.tool_calls:
                try:
                    input_obj = json.loads(tc.args_preview) if tc.args_preview else {}
                except (json.JSONDecodeError, TypeError):
                    input_obj = {}

                # ``state.time`` is required: OpenCode reads it when
                # rebuilding the conversation, and a tool part without it
                # fails the next turn. ``status`` takes only
                # completed/error/running.
                tool_part = {
                    "type": "tool",
                    "tool": tc.name,
                    "callID": f"call_{uuid.uuid4().hex[:24]}",
                    "state": {
                        "status": "completed",
                        "input": input_obj,
                        "output": tc.result_preview or "",
                        "title": "",
                        "metadata": {},
                        "time": {"start": msg_time, "end": msg_time},
                    },
                }
                con.execute(
                    """INSERT INTO part (id, message_id, session_id, time_created, time_updated, data)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (
                        f"prt_{uuid.uuid4().hex[:24]}",
                        msg_id,
                        new_session_id,
                        msg_time,
                        msg_time,
                        json.dumps(tool_part, ensure_ascii=False),
                    ),
                )

        con.commit()

    finally:
        con.close()

    return new_session_id

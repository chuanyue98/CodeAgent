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

    Verified against OpenCode 1.18.21 by letting it initialize two fresh
    repositories and reading back the rows it wrote: the id of a git worktree
    is the SHA of the repository's **root commit** (``git rev-list
    --max-parents=0 HEAD``), and non-git directories fall back to the shared
    ``global`` project.

    This has to be reproduced rather than invented. ``session.project_id`` is
    what OpenCode filters on when it lists sessions for the current directory,
    so a fabricated id (what this module used to mint with ``secrets``)
    produces a session row that is well-formed, resumable by explicit id, and
    yet invisible in ``opencode session list`` and in the TUI's session picker
    -- the session is there but the user cannot find it.

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

    Looks up the id :func:`_opencode_project_id` derives, and inserts the row
    only when OpenCode has not created it yet (a workspace it has never been
    opened in). Matching on the id rather than on ``worktree`` matters: the
    same directory can already have a stale row from an older OpenCode id
    scheme, and attaching to that one hides the session again.

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

    # Deliberately left NULL rather than carrying the source engine's model
    # across. ``session.model`` names a model of the *source* engine
    # (``claude-opus-5``, ``hy3`` ...) which OpenCode has no provider for, and
    # the id it stores here is what it resolves on the next turn: this module
    # used to write ``{"id": <source model>, "providerID": "converted"}``, and
    # since no provider is registered under "converted", resuming the
    # converted session failed the moment the user typed anything --
    # ``Error: {"name":"UnknownError","message":"Unexpected server error"}``.
    # A NULL model makes OpenCode fall back to the user's configured default,
    # which is the only model we actually know works here (verified against
    # OpenCode 1.18.21).
    session_model = None

    con = sqlite3.connect(str(db_path))

    try:
        project_id = _find_or_create_project(con, worktree, now_ms)

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

            # Message data JSON. ``parentID`` chains each assistant reply to
            # the turn it answered, the way OpenCode writes it natively; user
            # messages start a turn and carry no parent.
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
                # Same reasoning as the session-level model above: naming a
                # provider OpenCode has never heard of is worse than naming
                # none, so the converted turns stay provider-less and the next
                # turn resolves against the user's default.
                "time": {"created": msg_time, "completed": msg_time + 500},
                "finish": "stop",
            }

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

                # ``state.time`` is not optional. OpenCode reads it back when
                # it rebuilds the conversation to send upstream, and a tool
                # part without it kills the next turn -- bisected against
                # OpenCode 1.18.21 by adding one field at a time: status alone
                # or title/metadata alone still failed, adding ``time`` was
                # what made the turn go through. ``status`` only ever takes
                # ``completed``/``error``/``running`` in real rows, so the
                # "unknown" this used to emit for a call whose result the
                # parser did not capture is not a value OpenCode knows.
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

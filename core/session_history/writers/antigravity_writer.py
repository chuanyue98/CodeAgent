"""Writer for converting UnifiedSession to Antigravity native format.

Writes three things ``agy --conversation`` and the history UI both need:

1. ``brain/<session_id>/.system_generated/logs/transcript.jsonl``
   -- the human-readable transcript CodeAgent's parser reads.
2. ``conversations/<session_id>.db``
   -- the per-conversation trajectory store ``agy --conversation`` looks up.
   Without this file (or without a ``trajectory_meta`` row inside it), agy
   prints ``warning: conversation "..." not found`` and starts a blank chat.
3. A row in ``conversation_summaries.db`` -- titles/projects for the picker.

Steps in (2) are protobuf-encoded blobs. The field layout is the minimum
agy accepts for USER_INPUT / PLANNER_RESPONSE history to reappear in the
model's context on resume (verified against the live binary).
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from core.utils.atomic_write import atomic_write

if TYPE_CHECKING:
    from core.session_history.models import UnifiedSession

#: agy's ``trajectory_meta.trajectory_type`` / ``source`` for a normal chat.
_TRAJECTORY_TYPE = 4
_TRAJECTORY_SOURCE = 17

#: CortexStepType enum values used by resumed history.
_STEP_USER_INPUT = 14
_STEP_PLANNER_RESPONSE = 15
_STEP_DONE = 3

#: ``trajectory_meta.field3``: 4 = user turn, 2 = model turn.
_ROLE_USER = 4
_ROLE_MODEL = 2


def _enc_varint(n: int) -> bytes:
    if n < 0:
        raise ValueError("varint must be non-negative")
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        if n:
            out.append(b | 0x80)
        else:
            out.append(b)
            return bytes(out)


def _enc_key(field: int, wire: int) -> bytes:
    return _enc_varint((field << 3) | wire)


def _enc_var(field: int, n: int) -> bytes:
    return _enc_key(field, 0) + _enc_varint(n)


def _enc_len(field: int, data: bytes) -> bytes:
    return _enc_key(field, 2) + _enc_varint(len(data)) + data


def _parse_iso_epoch(ts: str) -> tuple[int, int]:
    """ISO 8601 → ``(seconds, nanos)``; unparsable input → now."""
    if not ts:
        now = datetime.now(tz=UTC)
        return int(now.timestamp()), now.microsecond * 1000
    raw = ts.strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        now = datetime.now(tz=UTC)
        return int(now.timestamp()), now.microsecond * 1000
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    seconds = int(dt.timestamp())
    return seconds, dt.microsecond * 1000


def _step_metadata(
    step_uuid: str, trajectory_id: str, cascade_id: str, role_code: int, ts: str
) -> bytes:
    """Builds the ``metadata`` blob agy stores beside every step."""
    seconds, nanos = _parse_iso_epoch(ts)
    ids = b"\n$" + trajectory_id.encode() + b'"$' + cascade_id.encode()
    return (
        _enc_len(1, _enc_var(1, seconds) + _enc_var(2, nanos))
        + _enc_var(3, role_code)
        + _enc_len(12, step_uuid.encode())
        + _enc_len(20, ids)
    )


def _user_step_payload(text: str, metadata: bytes) -> bytes:
    # Real USER_INPUT steps carry the prompt at field 19 / field 2.
    return (
        _enc_var(1, _STEP_USER_INPUT)
        + _enc_var(4, _STEP_DONE)
        + _enc_len(5, metadata)
        + _enc_len(19, _enc_len(2, text.encode()))
    )


def _planner_step_payload(text: str, metadata: bytes) -> bytes:
    # Real PLANNER_RESPONSE steps carry the reply at field 20 / field 1.
    return (
        _enc_var(1, _STEP_PLANNER_RESPONSE)
        + _enc_var(4, _STEP_DONE)
        + _enc_len(5, metadata)
        + _enc_len(20, _enc_len(1, text.encode()))
    )


def _format_sqlite_ts(iso_ts: str) -> str:
    """``2026-07-14T10:00:00Z`` → ``2026-07-14 10:00:00+00:00``."""
    if not iso_ts:
        return datetime.now(tz=UTC).strftime("%Y-%m-%d %H:%M:%S+00:00")
    raw = iso_ts.strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        return datetime.now(tz=UTC).strftime("%Y-%m-%d %H:%M:%S+00:00")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S+00:00")


def _assistant_step_text(content: str, tool_calls: list) -> str:
    if not tool_calls:
        return content
    lines = [content or ""]
    for tc in tool_calls:
        name = getattr(tc, "name", "") or ""
        args = getattr(tc, "args_preview", "") or ""
        if name:
            lines.append(f"[tool] {name} {args}".rstrip())
    return "\n".join(lines).strip()


def _create_conversations_db(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS trajectory_meta (
                trajectory_id text,
                cascade_id text,
                trajectory_type integer,
                source integer,
                PRIMARY KEY (trajectory_id)
            );
            CREATE TABLE IF NOT EXISTS steps (
                idx integer,
                step_type integer NOT NULL DEFAULT 0,
                status integer NOT NULL DEFAULT 0,
                has_subtrajectory numeric NOT NULL DEFAULT false,
                metadata blob,
                error_details blob,
                permissions blob,
                task_details blob,
                render_info blob,
                step_payload blob,
                step_format integer NOT NULL DEFAULT 0,
                PRIMARY KEY (idx)
            );
            CREATE INDEX IF NOT EXISTS idx_steps_status ON steps(status);
            CREATE INDEX IF NOT EXISTS idx_steps_step_type ON steps(step_type);
            CREATE TABLE IF NOT EXISTS gen_metadata (
                idx integer,
                data blob,
                size integer NOT NULL DEFAULT 0,
                PRIMARY KEY (idx)
            );
            CREATE TABLE IF NOT EXISTS executor_metadata (
                idx integer,
                data blob,
                PRIMARY KEY (idx)
            );
            CREATE TABLE IF NOT EXISTS parent_references (
                idx integer,
                data blob,
                PRIMARY KEY (idx)
            );
            CREATE TABLE IF NOT EXISTS trajectory_metadata_blob (
                id text DEFAULT "main",
                data blob,
                PRIMARY KEY (id)
            );
            CREATE TABLE IF NOT EXISTS battle_mode_infos (
                idx integer,
                data blob,
                PRIMARY KEY (idx)
            );
            """
        )


def _write_conversations_db(db_path: Path, session: UnifiedSession, session_id: str) -> None:
    """Creates ``conversations/<sid>.db`` with trajectory_meta + message steps."""
    _create_conversations_db(db_path)
    trajectory_id = str(uuid.uuid4())
    steps: list[tuple] = []
    idx = 0
    for msg in session.messages:
        ts = msg.timestamp or session.ended_at or session.started_at
        step_uuid = str(uuid.uuid4())
        if msg.role == "user":
            text = msg.content or ""
            if not text:
                continue
            metadata = _step_metadata(step_uuid, trajectory_id, session_id, _ROLE_USER, ts)
            payload = _user_step_payload(text, metadata)
            steps.append(
                (
                    idx,
                    _STEP_USER_INPUT,
                    _STEP_DONE,
                    0,
                    metadata,
                    None,
                    None,
                    None,
                    None,
                    payload,
                    0,
                )
            )
            idx += 1
        elif msg.role == "assistant":
            text = _assistant_step_text(msg.content or "", msg.tool_calls)
            if not text:
                continue
            metadata = _step_metadata(step_uuid, trajectory_id, session_id, _ROLE_MODEL, ts)
            payload = _planner_step_payload(text, metadata)
            steps.append(
                (
                    idx,
                    _STEP_PLANNER_RESPONSE,
                    _STEP_DONE,
                    0,
                    metadata,
                    None,
                    None,
                    None,
                    None,
                    payload,
                    0,
                )
            )
            idx += 1

    with sqlite3.connect(db_path) as conn:
        conn.execute("DELETE FROM trajectory_meta WHERE cascade_id = ?", (session_id,))
        conn.execute("DELETE FROM steps")
        conn.execute(
            "INSERT OR REPLACE INTO trajectory_meta (trajectory_id, cascade_id, trajectory_type, source) "
            "VALUES (?, ?, ?, ?)",
            (trajectory_id, session_id, _TRAJECTORY_TYPE, _TRAJECTORY_SOURCE),
        )
        conn.executemany(
            """
            INSERT OR REPLACE INTO steps (
                idx, step_type, status, has_subtrajectory, metadata,
                error_details, permissions, task_details, render_info,
                step_payload, step_format
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            steps,
        )


def _upsert_summary(db_path: Path, session: UnifiedSession, session_id: str) -> None:
    """Inserts/updates the ``conversation_summaries`` row without silent failure.

    The live schema has several ``NOT NULL`` columns with no defaults
    (notably ``last_user_input_time``). The previous insert omitted them, hit
    ``IntegrityError``, and was swallowed by a bare ``except`` — so the row
    never appeared and agy's summary cache never saw the conversion.
    """
    try:
        with sqlite3.connect(db_path) as conn:
            cols = [
                r[1]
                for r in conn.execute(
                    "PRAGMA table_info(conversation_summaries)"
                ).fetchall()
            ]
            if not cols:
                conn.execute(
                    """
                    CREATE TABLE conversation_summaries (
                        conversation_id text PRIMARY KEY,
                        title text NOT NULL DEFAULT '',
                        preview text NOT NULL DEFAULT '',
                        step_count integer NOT NULL DEFAULT 0,
                        last_modified_time datetime NOT NULL,
                        workspace_uris text NOT NULL,
                        status text NOT NULL DEFAULT '',
                        source text NOT NULL DEFAULT '',
                        project_id text NOT NULL DEFAULT '',
                        agent_name text NOT NULL DEFAULT '',
                        parent_conversation_id text NOT NULL DEFAULT '',
                        last_user_input_time datetime NOT NULL,
                        last_user_input_step_index integer NOT NULL DEFAULT -1
                    )
                    """
                )
                cols = [
                    r[1]
                    for r in conn.execute(
                        "PRAGMA table_info(conversation_summaries)"
                    ).fetchall()
                ]

            proj = session.project_path
            if proj:
                norm_proj = proj.replace("\\", "/")
                if not norm_proj.startswith("/"):
                    norm_proj = "/" + norm_proj
                uris_json = json.dumps([f"file://{norm_proj}"])
            else:
                uris_json = "[]"

            last_user_ts = ""
            last_user_index = -1
            for i, msg in enumerate(session.messages):
                if msg.role == "user":
                    last_user_ts = msg.timestamp or last_user_ts
                    last_user_index = i

            now = datetime.now(tz=UTC)
            db_now = now.strftime("%Y-%m-%d %H:%M:%S+00:00")
            last_modified = _format_sqlite_ts(session.ended_at) if session.ended_at else db_now
            last_user_time = (
                _format_sqlite_ts(last_user_ts) if last_user_ts else last_modified
            )

            values: dict[str, Any] = {
                "conversation_id": session_id,
                "title": session.title or session.first_user_message or "",
                "preview": session.first_user_message or "",
                "step_count": len(session.messages),
                "last_modified_time": last_modified,
                "workspace_uris": uris_json,
                "status": "CASCADE_RUN_STATUS_IDLE",
                "source": "",
                "project_id": "",
                "agent_name": session.agent or "",
                "parent_conversation_id": session.parent_session_id or "",
                "last_user_input_time": last_user_time,
                "last_user_input_step_index": last_user_index,
                "nesting_depth": 0,
                "battle_id": "",
                "winning_conversation_id": "",
                "not_fully_idle": 0,
                "killed": 0,
                "app_data_dir": "",
                "raw_summary": None,
                "group_id": "",
            }

            # Only touch columns that actually exist on this install's schema.
            target_cols = [c for c in cols if c in values]
            if "conversation_id" not in target_cols:
                return
            placeholders = ", ".join("?" for _ in target_cols)
            col_sql = ", ".join(target_cols)
            conn.execute(
                f"INSERT OR REPLACE INTO conversation_summaries ({col_sql}) "
                f"VALUES ({placeholders})",
                [values[c] for c in target_cols],
            )
    except sqlite3.Error:
        # Summary row is best-effort for CodeAgent's own picker; the
        # conversations DB is what agy needs to resume. Never fail conversion.
        pass


def write_antigravity_session(session: UnifiedSession, home: Path | None = None) -> str:
    """Converts a UnifiedSession and writes it to Antigravity native format.

    Args:
        session: The UnifiedSession to write.
        home: Optional home directory override.

    Returns:
        str: The session ID written.
    """
    session_id = session.session_id or str(uuid.uuid4())
    cli_dir = (home or Path.home()) / ".gemini" / "antigravity-cli"
    target_dir = cli_dir / "brain" / session_id / ".system_generated" / "logs"
    target_dir.mkdir(parents=True, exist_ok=True)
    transcript_file = target_dir / "transcript.jsonl"

    now_iso = datetime.now(tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    lines: list[str] = []
    step_index = 1

    for msg in session.messages:
        ts = msg.timestamp or now_iso
        if msg.role == "user":
            row = {
                "step_index": step_index,
                "source": "USER_EXPLICIT",
                "type": "USER_INPUT",
                "status": "DONE",
                "created_at": ts,
                "content": f"<USER_REQUEST>\n{msg.content}\n</USER_REQUEST>",
            }
            lines.append(json.dumps(row, ensure_ascii=False))
            step_index += 1
        elif msg.role == "assistant":
            tool_calls: list[dict[str, Any]] = []
            for tc in msg.tool_calls:
                args: Any = {}
                if tc.args_preview:
                    try:
                        args = json.loads(tc.args_preview)
                    except (json.JSONDecodeError, TypeError):
                        args = {"preview": tc.args_preview}
                tool_calls.append({"name": tc.name, "args": args})

            row = {
                "step_index": step_index,
                "source": "MODEL",
                "type": "PLANNER_RESPONSE",
                "status": "DONE",
                "created_at": ts,
                "content": msg.content,
                "tool_calls": tool_calls,
            }
            lines.append(json.dumps(row, ensure_ascii=False))
            step_index += 1

    content_str = "\n".join(lines) + ("\n" if lines else "")
    atomic_write(transcript_file, content_str)

    # agy --conversation resolves via conversations/<sid>.db, not the transcript.
    try:
        _write_conversations_db(
            cli_dir / "conversations" / f"{session_id}.db", session, session_id
        )
    except sqlite3.Error:
        pass

    _upsert_summary(cli_dir / "conversation_summaries.db", session, session_id)

    return session_id

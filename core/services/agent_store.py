"""Versioned SQLite persistence for Agent Gateway sessions and event replay."""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path

from core.services.agent_protocol import AgentEvent, AgentSession, wire

SCHEMA_VERSION = 3


class AgentStore:
    def __init__(self, path: str | Path):
        self.path = Path(path).expanduser()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._connection = sqlite3.connect(self.path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.execute("PRAGMA foreign_keys=ON")
        self._migrate()

    def _migrate(self) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                "CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL)"
            )
            row = self._connection.execute(
                "SELECT version FROM schema_version LIMIT 1"
            ).fetchone()
            version = int(row["version"]) if row else 0
            if version > SCHEMA_VERSION:
                raise RuntimeError(
                    f"Agent store schema {version} is newer than supported {SCHEMA_VERSION}"
                )
            if version < 1:
                self._connection.executescript(
                    """
                    CREATE TABLE agent_sessions (
                        id TEXT PRIMARY KEY,
                        provider TEXT NOT NULL,
                        provider_session_id TEXT NOT NULL,
                        project_id TEXT NOT NULL,
                        cwd TEXT NOT NULL,
                        title TEXT,
                        model TEXT,
                        permission_mode TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        status TEXT NOT NULL,
                        last_sequence INTEGER NOT NULL DEFAULT 0,
                        capability_snapshot TEXT NOT NULL,
                        resource_snapshot TEXT NOT NULL DEFAULT '{}',
                        UNIQUE(provider, provider_session_id)
                    );
                    CREATE INDEX agent_sessions_updated_idx
                        ON agent_sessions(updated_at DESC);
                    CREATE TABLE agent_events (
                        session_id TEXT NOT NULL,
                        sequence INTEGER NOT NULL,
                        event_json TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        PRIMARY KEY(session_id, sequence),
                        FOREIGN KEY(session_id) REFERENCES agent_sessions(id)
                            ON DELETE CASCADE
                    );
                    """
                )
                if row:
                    self._connection.execute(
                        "UPDATE schema_version SET version = ?", (SCHEMA_VERSION,)
                    )
                else:
                    self._connection.execute(
                        "INSERT INTO schema_version(version) VALUES (?)",
                        (SCHEMA_VERSION,),
                    )
                version = SCHEMA_VERSION
            if version < 2:
                self._connection.execute(
                    "ALTER TABLE agent_sessions ADD COLUMN resource_snapshot "
                    "TEXT NOT NULL DEFAULT '{}'"
                )
                self._connection.execute("UPDATE schema_version SET version = ?", (2,))
                version = 2
            if version < 3:
                # Older Gateway versions could persist a stale in-memory
                # ``last_sequence`` while an adapter event was arriving. Repair
                # those rows before allocating any more event numbers.
                self._connection.execute(
                    """
                    UPDATE agent_sessions
                    SET last_sequence = MAX(
                        last_sequence,
                        COALESCE((
                            SELECT MAX(sequence)
                            FROM agent_events
                            WHERE agent_events.session_id = agent_sessions.id
                        ), 0)
                    )
                    """
                )
                self._connection.execute(
                    "UPDATE schema_version SET version = ?", (SCHEMA_VERSION,)
                )

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def upsert_session(self, session: AgentSession) -> None:
        values = wire(session)
        with self._lock, self._connection:
            self._connection.execute(
                """
                INSERT INTO agent_sessions (
                    id, provider, provider_session_id, project_id, cwd, title,
                    model, permission_mode, created_at, updated_at, status,
                    last_sequence, capability_snapshot, resource_snapshot
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    provider_session_id=excluded.provider_session_id,
                    project_id=excluded.project_id, cwd=excluded.cwd,
                    title=excluded.title, model=excluded.model,
                    permission_mode=excluded.permission_mode,
                    updated_at=excluded.updated_at, status=excluded.status,
                    -- Adapter calls can overlap with a Gateway status update.
                    -- Never let a stale in-memory session move this counter
                    -- backwards, or the next event would reuse a primary key.
                    last_sequence=MAX(agent_sessions.last_sequence, excluded.last_sequence),
                    capability_snapshot=excluded.capability_snapshot,
                    resource_snapshot=excluded.resource_snapshot
                """,
                (
                    values["id"],
                    values["provider"],
                    values["providerSessionId"],
                    values["projectId"],
                    values["cwd"],
                    values["title"],
                    values["model"],
                    values["permissionMode"],
                    values["createdAt"],
                    values["updatedAt"],
                    values["status"],
                    values["lastSequence"],
                    json.dumps(values["capabilitySnapshot"], ensure_ascii=False),
                    json.dumps(values["resourceSnapshot"], ensure_ascii=False),
                ),
            )

    @staticmethod
    def _session_from_row(row: sqlite3.Row) -> AgentSession:
        return AgentSession.model_validate(
            {
                "id": row["id"],
                "provider": row["provider"],
                "providerSessionId": row["provider_session_id"],
                "projectId": row["project_id"],
                "cwd": row["cwd"],
                "title": row["title"],
                "model": row["model"],
                "permissionMode": row["permission_mode"],
                "createdAt": row["created_at"],
                "updatedAt": row["updated_at"],
                "status": row["status"],
                "lastSequence": row["last_sequence"],
                "capabilitySnapshot": json.loads(row["capability_snapshot"]),
                "resourceSnapshot": json.loads(row["resource_snapshot"] or "{}"),
            }
        )

    def get_session(self, session_id: str) -> AgentSession | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM agent_sessions WHERE id = ?", (session_id,)
            ).fetchone()
        return self._session_from_row(row) if row else None

    def find_by_provider_session(
        self, provider: str, provider_session_id: str
    ) -> AgentSession | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM agent_sessions "
                "WHERE provider = ? AND provider_session_id = ?",
                (provider, provider_session_id),
            ).fetchone()
        return self._session_from_row(row) if row else None

    def list_sessions(self, limit: int = 100) -> list[AgentSession]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT * FROM agent_sessions ORDER BY updated_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._session_from_row(row) for row in rows]

    def list_sessions_by_provider(self, provider: str) -> list[AgentSession]:
        """All sessions belonging to one provider, regardless of age.

        The Gateway's adapter supervisor has to touch every session a
        crashed provider owns. It used to do that with
        ``list_sessions(limit=10_000)`` plus a Python-side filter, which
        deserializes the entire table -- including every other provider's
        sessions -- on each crash, reconnect, and shutdown.
        """
        with self._lock:
            rows = self._connection.execute(
                "SELECT * FROM agent_sessions WHERE provider = ? "
                "ORDER BY updated_at DESC",
                (provider,),
            ).fetchall()
        return [self._session_from_row(row) for row in rows]

    def delete_session(self, session_id: str) -> bool:
        with self._lock, self._connection:
            cursor = self._connection.execute(
                "DELETE FROM agent_sessions WHERE id = ?", (session_id,)
            )
        return cursor.rowcount > 0

    def append_event(self, event: AgentEvent) -> AgentEvent:
        """Atomically allocate the next per-session sequence and persist it."""
        with self._lock, self._connection:
            row = self._connection.execute(
                "SELECT last_sequence FROM agent_sessions WHERE id = ?",
                (event.session_id,),
            ).fetchone()
            if row is None:
                raise KeyError(f"Unknown agent session: {event.session_id}")
            # Use the event table as a defensive second source of truth. This
            # also heals a database written by an older Gateway that allowed a
            # stale session upsert to lower ``last_sequence``.
            stored = self._connection.execute(
                "SELECT MAX(sequence) AS max_sequence FROM agent_events "
                "WHERE session_id = ?",
                (event.session_id,),
            ).fetchone()
            last_sequence = max(
                int(row["last_sequence"]), int(stored["max_sequence"] or 0)
            )
            event.sequence = last_sequence + 1
            payload = wire(event)
            self._connection.execute(
                "INSERT INTO agent_events(session_id, sequence, event_json, created_at) "
                "VALUES (?, ?, ?, ?)",
                (
                    event.session_id,
                    event.sequence,
                    json.dumps(payload, ensure_ascii=False),
                    payload["timestamp"],
                ),
            )
            self._connection.execute(
                "UPDATE agent_sessions SET last_sequence = ?, updated_at = ? "
                "WHERE id = ?",
                (event.sequence, payload["timestamp"], event.session_id),
            )
        return event

    def list_events(
        self, session_id: str, after_sequence: int = 0, limit: int = 1000
    ) -> list[AgentEvent]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT event_json FROM agent_events "
                "WHERE session_id = ? AND sequence > ? "
                "ORDER BY sequence ASC LIMIT ?",
                (session_id, after_sequence, limit),
            ).fetchall()
        return [AgentEvent.model_validate_json(row["event_json"]) for row in rows]

    def list_recent_events(
        self, session_id: str, before_sequence: int | None = None, limit: int = 100
    ) -> list[AgentEvent]:
        """Return one chronological history page ending before ``before_sequence``.

        Querying newest-first keeps switching a long conversation inexpensive;
        callers reverse the page so message reducers can process it normally.
        """
        with self._lock:
            if before_sequence is None:
                rows = self._connection.execute(
                    "SELECT event_json FROM agent_events WHERE session_id = ? "
                    "ORDER BY sequence DESC LIMIT ?",
                    (session_id, limit),
                ).fetchall()
            else:
                rows = self._connection.execute(
                    "SELECT event_json FROM agent_events "
                    "WHERE session_id = ? AND sequence < ? "
                    "ORDER BY sequence DESC LIMIT ?",
                    (session_id, before_sequence, limit),
                ).fetchall()
        return [
            AgentEvent.model_validate_json(row["event_json"]) for row in reversed(rows)
        ]

    def trim_events(self, session_id: str, keep: int = 5000) -> None:
        if keep < 1:
            raise ValueError("keep must be positive")
        with self._lock, self._connection:
            self._connection.execute(
                "DELETE FROM agent_events WHERE session_id = ? AND sequence <= "
                "MAX(0, (SELECT last_sequence FROM agent_sessions WHERE id = ?) - ?)",
                (session_id, session_id, keep),
            )

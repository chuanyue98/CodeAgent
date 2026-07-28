from __future__ import annotations

import sqlite3

import pytest

from core.services.agent_protocol import (
    AgentEvent,
    AgentSession,
    ProviderCapabilities,
    SessionStatus,
)
from core.services.agent_store import SCHEMA_VERSION, AgentStore


def _session() -> AgentSession:
    return AgentSession(
        id="agent_test",
        provider="fake",
        provider_session_id="provider_test",
        project_id="/tmp/project",
        cwd="/tmp/project",
        status=SessionStatus.READY,
        capability_snapshot=ProviderCapabilities(
            provider_id="fake", display_name="Fake"
        ),
    )


def test_store_migrates_persists_and_replays_events(tmp_path):
    path = tmp_path / "agent.sqlite3"
    store = AgentStore(path)
    store.upsert_session(_session())

    first = store.append_event(
        AgentEvent(type="turn.started", session_id="agent_test", turn_id="turn_1")
    )
    second = store.append_event(
        AgentEvent(
            type="message.delta",
            session_id="agent_test",
            turn_id="turn_1",
            data={"delta": "hello"},
        )
    )
    assert (first.sequence, second.sequence) == (1, 2)
    assert store.get_session("agent_test").last_sequence == 2
    store.close()

    reopened = AgentStore(path)
    assert (
        reopened._connection.execute("SELECT version FROM schema_version").fetchone()[
            "version"
        ]
        == SCHEMA_VERSION
    )
    replay = reopened.list_events("agent_test", after_sequence=1)
    assert len(replay) == 1
    assert replay[0].data == {"delta": "hello"}
    reopened.close()


def test_store_delete_cascades_events(tmp_path):
    store = AgentStore(tmp_path / "agent.sqlite3")
    store.upsert_session(_session())
    store.append_event(AgentEvent(type="session.ready", session_id="agent_test"))
    assert store.delete_session("agent_test") is True
    assert store.get_session("agent_test") is None
    assert store.list_events("agent_test") == []
    store.close()


def test_store_never_reuses_an_event_sequence_after_stale_session_upsert(tmp_path):
    store = AgentStore(tmp_path / "agent.sqlite3")
    store.upsert_session(_session())
    store.append_event(AgentEvent(type="session.ready", session_id="agent_test"))
    store.append_event(AgentEvent(type="turn.started", session_id="agent_test"))

    # Simulate a resume/status update that began before the second event was
    # persisted and therefore still carries the old sequence number.
    stale = _session()
    stale.last_sequence = 1
    store.upsert_session(stale)
    assert store.get_session("agent_test").last_sequence == 2

    # Also repair databases created by the old behavior, where the stale
    # upsert had already lowered the stored counter.
    store._connection.execute(
        "UPDATE agent_sessions SET last_sequence = 1 WHERE id = 'agent_test'"
    )
    store._connection.commit()
    event = store.append_event(
        AgentEvent(type="turn.completed", session_id="agent_test")
    )
    assert event.sequence == 3
    assert store.get_session("agent_test").last_sequence == 3
    store.close()


def test_store_pages_recent_events_in_chronological_order(tmp_path):
    store = AgentStore(tmp_path / "agent.sqlite3")
    store.upsert_session(_session())
    for index in range(1, 6):
        store.append_event(
            AgentEvent(
                type="message.delta",
                session_id="agent_test",
                data={"delta": str(index)},
            )
        )

    latest = store.list_recent_events("agent_test", limit=2)
    earlier = store.list_recent_events(
        "agent_test", before_sequence=latest[0].sequence, limit=2
    )
    assert [event.sequence for event in latest] == [4, 5]
    assert [event.sequence for event in earlier] == [2, 3]
    store.close()


_V1_SESSIONS_TABLE = """
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
        UNIQUE(provider, provider_session_id)
    );
    CREATE TABLE agent_events (
        session_id TEXT NOT NULL,
        sequence INTEGER NOT NULL,
        event_json TEXT NOT NULL,
        created_at TEXT NOT NULL,
        PRIMARY KEY(session_id, sequence)
    );
"""


def test_store_migrates_a_v1_database_and_adds_resource_snapshot(tmp_path):
    """Recovers a pre-resource_snapshot database, as if opened after an
    upgrade — the ALTER TABLE path only runs against a database that
    predates the column, never against one AgentStore itself created."""
    path = tmp_path / "agent.sqlite3"
    raw = sqlite3.connect(path)
    raw.executescript(
        "CREATE TABLE schema_version (version INTEGER NOT NULL);"
        "INSERT INTO schema_version(version) VALUES (1);" + _V1_SESSIONS_TABLE
    )
    raw.commit()
    raw.close()

    store = AgentStore(path)
    columns = {
        row["name"]
        for row in store._connection.execute("PRAGMA table_info(agent_sessions)")
    }
    assert "resource_snapshot" in columns
    version = store._connection.execute(
        "SELECT version FROM schema_version"
    ).fetchone()["version"]
    assert version == SCHEMA_VERSION
    store.close()


def test_store_migrates_a_v2_database_and_repairs_stale_last_sequence(tmp_path):
    """Recovers a v2 database (has resource_snapshot, predates the
    last_sequence repair) whose session counter fell behind its own event
    log — the exact corruption test_store_never_reuses_an_event_sequence...
    guards against at runtime, but here as something already on disk."""
    path = tmp_path / "agent.sqlite3"
    raw = sqlite3.connect(path)
    raw.executescript(
        "CREATE TABLE schema_version (version INTEGER NOT NULL);"
        "INSERT INTO schema_version(version) VALUES (2);"
        + _V1_SESSIONS_TABLE.replace(
            "UNIQUE(provider, provider_session_id)",
            "resource_snapshot TEXT NOT NULL DEFAULT '{}',"
            "UNIQUE(provider, provider_session_id)",
        )
    )
    raw.execute(
        "INSERT INTO agent_sessions (id, provider, provider_session_id, "
        "project_id, cwd, permission_mode, created_at, updated_at, status, "
        "last_sequence, capability_snapshot) VALUES "
        "('agent_test', 'fake', 'provider_test', '/tmp/p', '/tmp/p', "
        "'workspace-write', '2024-01-01T00:00:00Z', '2024-01-01T00:00:00Z', "
        '\'ready\', 1, \'{"providerId": "fake", "displayName": "Fake"}\')'
    )
    raw.execute(
        "INSERT INTO agent_events(session_id, sequence, event_json, created_at) "
        "VALUES ('agent_test', 5, '{}', '2024-01-01T00:00:00Z')"
    )
    raw.commit()
    raw.close()

    store = AgentStore(path)
    assert store.get_session("agent_test").last_sequence == 5
    version = store._connection.execute(
        "SELECT version FROM schema_version"
    ).fetchone()["version"]
    assert version == SCHEMA_VERSION
    store.close()


def test_store_recovers_from_a_schema_version_row_with_no_tables(tmp_path):
    """A crash between creating schema_version and the real tables leaves a
    row (version 0) but no agent_sessions/agent_events — recovery must
    UPDATE that row rather than INSERT a duplicate one."""
    path = tmp_path / "agent.sqlite3"
    raw = sqlite3.connect(path)
    raw.execute("CREATE TABLE schema_version (version INTEGER NOT NULL)")
    raw.execute("INSERT INTO schema_version(version) VALUES (0)")
    raw.commit()
    raw.close()

    store = AgentStore(path)
    rows = store._connection.execute("SELECT version FROM schema_version").fetchall()
    assert [row["version"] for row in rows] == [SCHEMA_VERSION]
    store.upsert_session(_session())
    assert store.get_session("agent_test") is not None
    store.close()


def test_store_rejects_a_schema_version_newer_than_supported(tmp_path):
    path = tmp_path / "agent.sqlite3"
    raw = sqlite3.connect(path)
    raw.execute("CREATE TABLE schema_version (version INTEGER NOT NULL)")
    raw.execute("INSERT INTO schema_version(version) VALUES (?)", (SCHEMA_VERSION + 1,))
    raw.commit()
    raw.close()

    with pytest.raises(RuntimeError, match="newer than supported"):
        AgentStore(path)


def test_append_event_rejects_an_unknown_session(tmp_path):
    store = AgentStore(tmp_path / "agent.sqlite3")
    with pytest.raises(KeyError):
        store.append_event(AgentEvent(type="turn.started", session_id="missing"))
    store.close()


def test_trim_events_rejects_a_non_positive_keep(tmp_path):
    store = AgentStore(tmp_path / "agent.sqlite3")
    store.upsert_session(_session())
    with pytest.raises(ValueError):
        store.trim_events("agent_test", keep=0)
    store.close()

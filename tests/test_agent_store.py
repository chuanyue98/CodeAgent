from __future__ import annotations

from core.services.agent_protocol import (
    AgentEvent,
    AgentSession,
    ProviderCapabilities,
    SessionStatus,
)
from core.services.agent_store import AgentStore, SCHEMA_VERSION


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

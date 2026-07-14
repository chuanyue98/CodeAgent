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

from __future__ import annotations

import asyncio
import json

import pytest

from core.services.agent_adapters.fake import FakeAgentAdapter
from core.services.agent_gateway import AgentGateway, AgentGatewayError
from core.services.agent_protocol import (
    AdapterEvent,
    AgentCommand,
    AgentEvent,
    AgentInput,
    SessionStatus,
    TurnInput,
)
from core.services.agent_store import AgentStore


def _config(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    config = tmp_path / "config.json"
    config.write_text(
        json.dumps({"project_registry": [{"path": str(workspace), "group": "common"}]}),
        encoding="utf-8",
    )
    return config, workspace


@pytest.mark.asyncio
async def test_gateway_fake_adapter_turn_and_request_idempotency(tmp_path):
    config, workspace = _config(tmp_path)
    adapter = FakeAgentAdapter()
    gateway = AgentGateway(AgentStore(tmp_path / "agent.sqlite3"), config, [adapter])
    await gateway.start()
    session = await gateway.create_session(provider="fake", project_id=str(workspace))
    queue = gateway.subscribe(session.id, after_sequence=0)
    ready = await asyncio.wait_for(queue.get(), timeout=1)
    assert ready.type == "session.ready"

    command = AgentCommand(
        type="turn.start",
        request_id="request-1",
        session_id=session.id,
        input=[AgentInput(text="hello")],
    )
    first_ack = await gateway.execute_command(command)
    second_ack = await gateway.execute_command(command)
    assert first_ack.result == second_ack.result

    types = []
    while len(types) < 5:
        event = await asyncio.wait_for(queue.get(), timeout=1)
        types.append(event.type)
    assert types == [
        "message.user",
        "turn.started",
        "message.delta",
        "message.completed",
        "turn.completed",
    ]
    assert gateway.get_session(session.id).last_sequence == 6
    await gateway.stop()


@pytest.mark.asyncio
async def test_gateway_rejects_unregistered_workspace(tmp_path):
    config, _workspace = _config(tmp_path)
    other = tmp_path / "other"
    other.mkdir()
    gateway = AgentGateway(
        AgentStore(tmp_path / "agent.sqlite3"), config, [FakeAgentAdapter()]
    )
    await gateway.start()
    with pytest.raises(AgentGatewayError, match="registered") as error:
        await gateway.create_session(provider="fake", project_id=str(other))
    assert error.value.code == "workspace_not_registered"
    await gateway.stop()


@pytest.mark.asyncio
async def test_gateway_imports_existing_provider_session(tmp_path):
    config, workspace = _config(tmp_path)
    gateway = AgentGateway(
        AgentStore(tmp_path / "agent.sqlite3"), config, [FakeAgentAdapter()]
    )
    await gateway.start()
    session = await gateway.import_session(
        provider="fake",
        provider_session_id="fake-existing-session",
        project_id=str(workspace),
        title="Existing conversation",
    )
    assert session.provider_session_id == "fake-existing-session"
    assert session.title == "Existing conversation"
    assert (
        gateway.store.find_by_provider_session("fake", "fake-existing-session").id
        == session.id
    )
    await gateway.stop()


@pytest.mark.asyncio
async def test_gateway_persists_resource_snapshot(tmp_path):
    config, workspace = _config(tmp_path)
    config.write_text(
        json.dumps(
            {
                "project_registry": [{"path": str(workspace), "group": "web"}],
                "groups": {
                    "web": {
                        "skills": ["base/review"],
                        "prompts": ["base"],
                        "hooks": ["base/check"],
                        "plugins": ["base/tools"],
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    gateway = AgentGateway(
        AgentStore(tmp_path / "agent.sqlite3"), config, [FakeAgentAdapter()]
    )
    await gateway.start()
    session = await gateway.create_session(provider="fake", project_id=str(workspace))
    assert session.resource_snapshot.group == "web"
    assert session.resource_snapshot.skills == ["base/review"]
    assert gateway.get_session(session.id).resource_snapshot.plugins == ["base/tools"]
    await gateway.stop()


@pytest.mark.asyncio
async def test_gateway_replays_only_events_after_sequence(tmp_path):
    config, workspace = _config(tmp_path)
    gateway = AgentGateway(
        AgentStore(tmp_path / "agent.sqlite3"), config, [FakeAgentAdapter()]
    )
    await gateway.start()
    session = await gateway.create_session(provider="fake", project_id=str(workspace))
    await gateway.start_turn(session.id, TurnInput(input=[AgentInput(text="replay")]))
    for _ in range(20):
        if gateway.get_session(session.id).last_sequence == 6:
            break
        await asyncio.sleep(0.01)
    replay = gateway.subscribe(session.id, after_sequence=4)
    assert [(await replay.get()).sequence, (await replay.get()).sequence] == [5, 6]
    await gateway.stop()


@pytest.mark.asyncio
async def test_gateway_disconnects_subscriber_that_falls_behind(tmp_path):
    config, workspace = _config(tmp_path)
    gateway = AgentGateway(
        AgentStore(tmp_path / "agent.sqlite3"),
        config,
        [FakeAgentAdapter()],
        subscriber_queue_size=2,
    )
    await gateway.start()
    session = await gateway.create_session(provider="fake", project_id=str(workspace))
    queue = gateway.subscribe(session.id, after_sequence=1)
    await gateway.publish(AgentEvent(type="test.one", session_id=session.id))
    await gateway.publish(AgentEvent(type="test.two", session_id=session.id))
    await gateway.publish(AgentEvent(type="test.three", session_id=session.id))
    assert queue not in gateway._subscribers.get(session.id, set())
    assert (await queue.get()).type == "test.two"
    assert await queue.get() is None
    await gateway.stop()


class CrashingAdapter(FakeAgentAdapter):
    """Fake provider whose event stream dies on demand, then can restart."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.start_count = 0

    async def start(self) -> None:
        self.start_count += 1
        await super().start()

    async def events(self):
        while True:
            event = await self._events.get()
            if event is None:
                return
            if event.type == "crash":
                raise RuntimeError("adapter process died")
            yield event


async def _wait_for(predicate, timeout: float = 2.0) -> bool:
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        if predicate():
            return True
        await asyncio.sleep(0.01)
    return predicate()


@pytest.mark.asyncio
async def test_gateway_marks_provider_sessions_disconnected_when_adapter_crashes(
    tmp_path,
):
    """A crashed provider's sessions become DISCONNECTED, not ERROR.

    ERROR is terminal in the UI. The provider is coming back (see the
    reconnect test below), so the sessions are recoverable and must not be
    presented as dead.
    """
    config, workspace = _config(tmp_path)
    adapter = CrashingAdapter()
    gateway = AgentGateway(
        AgentStore(tmp_path / "agent.sqlite3"),
        config,
        [adapter],
        reconnect_base_delay=60,  # park the supervisor so it can't reconnect
    )
    await gateway.start()
    session = await gateway.create_session(provider="fake", project_id=str(workspace))
    other = await gateway.create_session(provider="fake", project_id=str(workspace))

    await adapter._events.put(AdapterEvent(type="crash", provider_session_id="x"))
    assert await _wait_for(
        lambda: gateway.get_session(session.id).status == SessionStatus.DISCONNECTED
    )
    assert gateway.get_session(other.id).status == SessionStatus.DISCONNECTED
    await gateway.stop()


@pytest.mark.asyncio
async def test_gateway_restarts_a_crashed_adapter(tmp_path):
    """The supervisor brings a crashed provider back on its own.

    Before this, the pump task simply returned after a crash: the provider
    stayed dead for the rest of the server's lifetime and the only fix was
    restarting ``ca ui``.
    """
    config, workspace = _config(tmp_path)
    adapter = CrashingAdapter()
    gateway = AgentGateway(
        AgentStore(tmp_path / "agent.sqlite3"),
        config,
        [adapter],
        reconnect_base_delay=0.01,
    )
    await gateway.start()
    await gateway.create_session(provider="fake", project_id=str(workspace))
    assert adapter.start_count == 1

    await adapter._events.put(AdapterEvent(type="crash", provider_session_id="x"))

    assert await _wait_for(lambda: adapter.start_count >= 2)
    assert (await gateway.providers())[0].available is True
    await gateway.stop()


@pytest.mark.asyncio
async def test_gateway_retries_a_provider_that_failed_to_start(tmp_path):
    """A provider unavailable at boot is retried, not abandoned.

    ``start()`` used to skip creating a pump task when the adapter failed
    to start, so a CLI installed or signed into a minute later stayed
    invisible until the server restarted.
    """

    class LateAdapter(FakeAgentAdapter):
        def __init__(self):
            super().__init__()
            self.attempts = 0

        async def start(self) -> None:
            self.attempts += 1
            if self.attempts < 3:
                raise RuntimeError("CLI not found")
            await super().start()

    config, _workspace = _config(tmp_path)
    adapter = LateAdapter()
    gateway = AgentGateway(
        AgentStore(tmp_path / "agent.sqlite3"),
        config,
        [adapter],
        reconnect_base_delay=0.01,
    )
    await gateway.start()
    assert (await gateway.providers())[0].available is False

    assert await _wait_for(lambda: adapter.attempts >= 3)
    assert await _wait_for(lambda: adapter._started)
    await gateway.stop()


@pytest.mark.asyncio
async def test_request_reconnect_cuts_short_the_backoff(tmp_path):
    """`POST /providers/{id}/reconnect` skips a long pending backoff."""
    config, workspace = _config(tmp_path)
    adapter = CrashingAdapter()
    gateway = AgentGateway(
        AgentStore(tmp_path / "agent.sqlite3"),
        config,
        [adapter],
        reconnect_base_delay=30,  # long enough that the test would time out
    )
    await gateway.start()
    await gateway.create_session(provider="fake", project_id=str(workspace))

    await adapter._events.put(AdapterEvent(type="crash", provider_session_id="x"))
    assert await _wait_for(lambda: adapter.start_count == 1 and not adapter._started)

    assert gateway.request_reconnect("fake") is True
    assert await _wait_for(lambda: adapter.start_count >= 2)

    assert gateway.request_reconnect("nope") is False
    await gateway.stop()


@pytest.mark.asyncio
async def test_gateway_reports_a_silently_ended_event_stream(tmp_path):
    """An events() stream that ends cleanly is a disconnect, not silence.

    ``iter_events`` returns on a ``None`` sentinel, which raises nothing.
    That path used to end the pump with no error event and no status
    change, leaving the UI showing a healthy provider that had in fact
    stopped delivering anything.
    """
    config, workspace = _config(tmp_path)
    adapter = FakeAgentAdapter()
    gateway = AgentGateway(
        AgentStore(tmp_path / "agent.sqlite3"),
        config,
        [adapter],
        reconnect_base_delay=60,
    )
    await gateway.start()
    session = await gateway.create_session(provider="fake", project_id=str(workspace))

    await adapter._events.put(None)
    assert await _wait_for(
        lambda: gateway.get_session(session.id).status == SessionStatus.DISCONNECTED
    )
    await gateway.stop()

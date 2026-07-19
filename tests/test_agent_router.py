from __future__ import annotations

import json
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.services.agent_adapters.fake import FakeAgentAdapter
from core.services.agent_gateway import AgentGateway
from core.services.agent_store import AgentStore
from core.session_history.models import EngineType, UnifiedMessage, UnifiedSession
from core.web.routers import agent


def _app(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps({"project_registry": [{"path": str(workspace), "group": "common"}]}),
        encoding="utf-8",
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        gateway = AgentGateway(
            AgentStore(tmp_path / "agent.sqlite3"),
            config_path,
            [FakeAgentAdapter()],
        )
        app.state.agent_gateway = gateway
        app.state.agent_gateway_status = {
            "enabled": True,
            "legacyFallback": True,
            "providers": {"fake": True},
        }
        await gateway.start()
        yield
        await gateway.stop()

    app = FastAPI(lifespan=lifespan)
    app.include_router(agent.router)
    return app, workspace


def test_agent_rest_and_websocket_ack_event_and_replay(tmp_path):
    app, workspace = _app(tmp_path)
    with TestClient(app) as client:
        status = client.get("/api/agent/status")
        assert status.json() == {
            "enabled": True,
            "legacyFallback": True,
            "providers": {"fake": True},
        }
        providers = client.get("/api/agent/providers")
        assert providers.status_code == 200
        assert providers.json()[0]["available"] is True

        created = client.post(
            "/api/agent/sessions",
            json={"provider": "fake", "projectId": str(workspace)},
        )
        assert created.status_code == 201
        session_id = created.json()["id"]

        with client.websocket_connect(
            f"/api/agent/sessions/{session_id}/events?afterSequence=0"
        ) as socket:
            assert socket.receive_json()["type"] == "session.ready"
            command = {
                "type": "turn.start",
                "requestId": "ws-1",
                "sessionId": session_id,
                "input": [{"type": "text", "text": "hello"}],
            }
            socket.send_json(command)
            messages = [socket.receive_json() for _ in range(6)]
            ack = next(message for message in messages if message["type"] == "ack")
            assert ack["requestId"] == "ws-1"
            assert {message["type"] for message in messages} >= {
                "turn.started",
                "message.user",
                "message.delta",
                "message.completed",
                "turn.completed",
            }

        with client.websocket_connect(
            f"/api/agent/sessions/{session_id}/events?afterSequence=4"
        ) as socket:
            replay = [socket.receive_json(), socket.receive_json()]
            assert [event["sequence"] for event in replay] == [5, 6]


def test_agent_rest_rejects_unregistered_workspace(tmp_path):
    app, _workspace = _app(tmp_path)
    other = tmp_path / "other"
    other.mkdir()
    with TestClient(app) as client:
        response = client.post(
            "/api/agent/sessions",
            json={"provider": "fake", "projectId": str(other)},
        )
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "workspace_not_registered"


def test_agent_history_endpoint_returns_latest_page_then_older_page(tmp_path):
    app, workspace = _app(tmp_path)
    with TestClient(app) as client:
        created = client.post(
            "/api/agent/sessions",
            json={"provider": "fake", "projectId": str(workspace)},
        )
        session_id = created.json()["id"]
        for index in range(4):
            app.state.agent_gateway.store.append_event(
                agent.AgentEvent(
                    type="message.delta",
                    session_id=session_id,
                    data={"delta": str(index)},
                )
            )

        latest = client.get(f"/api/agent/sessions/{session_id}/history?limit=2")
        assert latest.status_code == 200
        latest_body = latest.json()
        assert [event["sequence"] for event in latest_body["events"]] == [4, 5]
        assert latest_body["hasMore"] is True

        earlier = client.get(
            f"/api/agent/sessions/{session_id}/history?limit=2"
            f"&beforeSequence={latest_body['oldestSequence']}"
        )
        assert [event["sequence"] for event in earlier.json()["events"]] == [2, 3]


def test_agent_imports_native_history_into_replay_events(tmp_path, monkeypatch):
    app, workspace = _app(tmp_path)
    native = UnifiedSession(
        session_id="fake-native-session",
        engine=EngineType.OPENCODE,
        project_path=str(workspace),
        title="Imported history",
        model="test-model",
        messages=[
            UnifiedMessage(role="user", content="old question"),
            UnifiedMessage(role="assistant", content="old answer"),
        ],
    )
    monkeypatch.setattr(agent, "find_session_by_id", lambda *_args: native)

    with TestClient(app) as client:
        response = client.post(
            "/api/agent/sessions/import",
            json={
                "provider": "fake",
                "providerSessionId": native.session_id,
                "projectId": str(workspace),
            },
        )
        assert response.status_code == 201
        session_id = response.json()["id"]
        replay = app.state.agent_gateway.store.list_events(session_id)
        assert [event.type for event in replay] == [
            "session.ready",
            "message.user",
            "message.completed",
        ]
        assert replay[1].data["text"] == "old question"
        assert replay[2].data["text"] == "old answer"

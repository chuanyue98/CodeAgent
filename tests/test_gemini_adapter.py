from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest

from core.services.agent_adapters.gemini import GeminiAdapter, GeminiProtocolError
from core.services.agent_protocol import (
    AgentInput,
    ApprovalDecision,
    CreateSessionOptions,
    PermissionMode,
    TurnInput,
)


@pytest.mark.asyncio
async def test_gemini_create_session_enforces_plan_and_model(monkeypatch):
    adapter = GeminiAdapter()
    requests: list[tuple[str, dict]] = []

    async def request(method, params, timeout=120):
        requests.append((method, params))
        if method == "session/new":
            return {
                "sessionId": "gemini-session",
                "modes": {
                    "currentModeId": "default",
                    "availableModes": [{"id": "default"}, {"id": "plan"}],
                },
                "models": {"currentModelId": "auto"},
            }
        return {}

    monkeypatch.setattr(adapter, "_request", request)
    session = await adapter.create_session(
        CreateSessionOptions(
            project_id="/workspace",
            cwd="/workspace",
            model="gemini-test",
            permission_mode=PermissionMode.READ_ONLY,
        )
    )

    assert session.id == "gemini-session"
    assert session.model == "gemini-test"
    assert requests == [
        ("session/new", {"cwd": "/workspace", "mcpServers": []}),
        (
            "session/set_mode",
            {"sessionId": "gemini-session", "modeId": "plan"},
        ),
        (
            "session/set_model",
            {"sessionId": "gemini-session", "modelId": "gemini-test"},
        ),
    ]


@pytest.mark.asyncio
async def test_gemini_read_only_rejects_missing_plan_mode(monkeypatch):
    adapter = GeminiAdapter()

    async def request(_method, _params, timeout=120):
        return {
            "sessionId": "gemini-session",
            "modes": {
                "currentModeId": "default",
                "availableModes": [{"id": "default"}],
            },
        }

    monkeypatch.setattr(adapter, "_request", request)
    with pytest.raises(GeminiProtocolError, match="required 'plan'"):
        await adapter.create_session(
            CreateSessionOptions(
                project_id="/workspace",
                cwd="/workspace",
                permission_mode=PermissionMode.READ_ONLY,
            )
        )


@pytest.mark.asyncio
async def test_gemini_maps_message_tool_diff_and_usage_updates():
    adapter = GeminiAdapter()
    adapter._active_turns["session-1"] = "turn-1"
    adapter._message_text[("session-1", "turn-1")] = ""

    await adapter._handle_notification(
        "session/update",
        {
            "sessionId": "session-1",
            "update": {
                "sessionUpdate": "agent_message_chunk",
                "content": {"type": "text", "text": "hello"},
            },
        },
    )
    await adapter._handle_notification(
        "session/update",
        {
            "sessionId": "session-1",
            "update": {
                "sessionUpdate": "tool_call_update",
                "toolCallId": "tool-1",
                "title": "edit file",
                "status": "completed",
                "content": [
                    {"type": "diff", "path": "a.py", "oldText": "a", "newText": "b"}
                ],
            },
        },
    )
    await adapter._handle_notification(
        "session/update",
        {
            "sessionId": "session-1",
            "update": {"sessionUpdate": "usage_update", "used": 10, "size": 100},
        },
    )

    events = [await adapter._events.get() for _ in range(4)]
    assert [event.type for event in events] == [
        "message.delta",
        "file.diff",
        "tool.completed",
        "usage.updated",
    ]
    assert adapter._message_text[("session-1", "turn-1")] == "hello"


@pytest.mark.asyncio
async def test_gemini_permission_request_and_response_use_offered_option(monkeypatch):
    adapter = GeminiAdapter()
    adapter._active_turns["session-1"] = "turn-1"
    writes = []

    async def write(message):
        writes.append(message)

    monkeypatch.setattr(adapter, "_write", write)
    await adapter._handle_server_request(
        {
            "jsonrpc": "2.0",
            "id": 7,
            "method": "session/request_permission",
            "params": {
                "sessionId": "session-1",
                "options": [
                    {"optionId": "proceed_once", "kind": "allow_once", "name": "Allow"},
                    {"optionId": "cancel", "kind": "reject_once", "name": "Deny"},
                ],
                "toolCall": {
                    "toolCallId": "tool-1",
                    "kind": "execute",
                    "title": "Run command",
                    "rawInput": {"command": "git status"},
                },
            },
        }
    )
    event = await adapter._events.get()
    assert event.type == "approval.request"
    assert event.data["approval"]["command"] == "git status"

    await adapter.respond_to_approval("gemini:7", ApprovalDecision.ACCEPT)
    assert writes == [
        {
            "jsonrpc": "2.0",
            "id": 7,
            "result": {"outcome": {"outcome": "selected", "optionId": "proceed_once"}},
        }
    ]


@pytest.mark.asyncio
async def test_gemini_prompt_lifecycle_emits_completion(monkeypatch):
    adapter = GeminiAdapter()

    async def request(method, _params, timeout=120):
        assert method == "session/prompt"
        await adapter._handle_notification(
            "session/update",
            {
                "sessionId": "session-1",
                "update": {
                    "sessionUpdate": "agent_message_chunk",
                    "content": {"type": "text", "text": "done"},
                },
            },
        )
        return {
            "stopReason": "end_turn",
            "usage": {"inputTokens": 1, "outputTokens": 1, "totalTokens": 2},
        }

    monkeypatch.setattr(adapter, "_request", request)
    turn_id = await adapter.start_turn(
        "session-1", TurnInput(input=[AgentInput(text="hello")])
    )
    await adapter._turn_tasks["session-1"]
    events = []
    while not adapter._events.empty():
        events.append(await adapter._events.get())

    assert turn_id.startswith("gemini-turn-")
    assert [event.type for event in events] == [
        "turn.started",
        "message.delta",
        "message.completed",
        "usage.updated",
        "turn.completed",
    ]
    assert events[2].data["text"] == "done"


@pytest.mark.asyncio
@pytest.mark.skipif(
    os.environ.get("CA_LIVE_GEMINI") != "1",
    reason="set CA_LIVE_GEMINI=1 to run against the authenticated Gemini CLI",
)
async def test_gemini_live_two_turn_session():
    adapter = GeminiAdapter()
    await adapter.start()
    try:
        session = await adapter.create_session(
            CreateSessionOptions(
                project_id=str(Path.cwd()),
                cwd=str(Path.cwd()),
                permission_mode=PermissionMode.READ_ONLY,
            )
        )

        async def run_turn(prompt: str) -> str:
            turn_id = await adapter.start_turn(
                session.id, TurnInput(input=[AgentInput(text=prompt)])
            )
            text = ""
            while True:
                event = await asyncio.wait_for(anext(adapter.events()), timeout=120)
                if event.provider_turn_id != turn_id:
                    continue
                if event.type == "message.completed":
                    text = str(event.data.get("text", ""))
                if event.type == "turn.completed":
                    return text

        first = await run_turn("Reply with exactly CODEAGENT_GEMINI_ONE.")
        second = await run_turn("Repeat the exact token from your previous reply.")
        assert "CODEAGENT_GEMINI_ONE" in first
        assert "CODEAGENT_GEMINI_ONE" in second
    finally:
        await adapter.stop()

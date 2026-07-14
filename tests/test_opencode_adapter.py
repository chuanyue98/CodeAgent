from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest

from core.services.agent_adapters.opencode import OpenCodeAdapter
from core.services.agent_protocol import (
    AgentInput,
    ApprovalDecision,
    CreateSessionOptions,
    PermissionMode,
    TurnInput,
)


def test_opencode_translates_text_delta():
    adapter = OpenCodeAdapter()
    events = adapter._translate_event(
        {
            "type": "session.next.text.delta",
            "properties": {
                "sessionID": "session-1",
                "assistantMessageID": "turn-1",
                "textID": "text-1",
                "delta": "hello",
            },
        }
    )
    assert len(events) == 1
    event = events[0]
    assert event.type == "message.delta"
    assert event.provider_session_id == "session-1"
    assert event.provider_turn_id == "turn-1"
    assert event.item_id == "text-1"
    assert event.data == {"delta": "hello"}


def test_opencode_translates_tool_lifecycle():
    adapter = OpenCodeAdapter()
    started = adapter._translate_event(
        {
            "type": "session.next.tool.called",
            "properties": {
                "sessionID": "session-1",
                "callID": "call-1",
                "tool": "bash",
                "input": {"command": "ls"},
            },
        }
    )
    assert len(started) == 1
    assert started[0].type == "tool.started"
    assert started[0].data["tool"]["name"] == "bash"
    assert started[0].item_id == "call-1"

    completed = adapter._translate_event(
        {
            "type": "session.next.tool.success",
            "properties": {
                "sessionID": "session-1",
                "callID": "call-1",
            },
        }
    )
    assert len(completed) == 1
    assert completed[0].type == "tool.completed"
    assert completed[0].data["tool"]["status"] == "completed"


def test_opencode_step_started_and_ended_tracks_active_turn():
    adapter = OpenCodeAdapter()
    started = adapter._translate_event(
        {
            "type": "session.next.step.started",
            "properties": {
                "sessionID": "session-1",
                "assistantMessageID": "turn-1",
            },
        }
    )
    assert started[0].type == "turn.started"
    assert adapter._active_turns["session-1"] == "turn-1"

    ended = adapter._translate_event(
        {
            "type": "session.next.step.ended",
            "properties": {
                "sessionID": "session-1",
                "assistantMessageID": "turn-1",
                "tokens": {"input": 1},
                "finish": "stop",
            },
        }
    )
    types = [event.type for event in ended]
    assert types == ["usage.updated", "turn.completed"]
    assert "session-1" not in adapter._active_turns


def test_opencode_step_ended_with_tool_calls_keeps_turn_active():
    adapter = OpenCodeAdapter()
    adapter._active_turns["session-1"] = "turn-1"
    events = adapter._translate_event(
        {
            "type": "session.next.step.ended",
            "properties": {
                "sessionID": "session-1",
                "assistantMessageID": "turn-1",
                "tokens": {"input": 1},
                "finish": "tool-calls",
            },
        }
    )
    assert [event.type for event in events] == ["usage.updated"]
    assert adapter._active_turns["session-1"] == "turn-1"


def test_opencode_translates_permission_asked_and_tracks_pending():
    adapter = OpenCodeAdapter()
    events = adapter._translate_event(
        {
            "type": "permission.v2.asked",
            "properties": {
                "sessionID": "session-1",
                "id": "perm-1",
                "action": "bash",
            },
        }
    )
    assert len(events) == 1
    assert events[0].type == "approval.request"
    assert events[0].data["approval"]["id"] == "perm-1"
    assert adapter._pending_approvals["perm-1"] == "session-1"


@pytest.mark.asyncio
async def test_opencode_respond_to_approval_maps_decision_and_calls_api(monkeypatch):
    adapter = OpenCodeAdapter()
    adapter._pending_approvals["perm-1"] = "session-1"
    calls: list[tuple[str, str, dict | None]] = []

    async def fake_request_json(method, path, body=None, timeout=30):
        calls.append((method, path, body))
        return {}

    monkeypatch.setattr(adapter, "_request_json", fake_request_json)

    await adapter.respond_to_approval("perm-1", ApprovalDecision.ACCEPT_FOR_SESSION)

    assert calls == [
        (
            "POST",
            "/api/session/session-1/permission/perm-1/reply",
            {"reply": "always"},
        )
    ]
    assert "perm-1" not in adapter._pending_approvals


@pytest.mark.asyncio
async def test_opencode_respond_to_approval_unknown_id_raises():
    adapter = OpenCodeAdapter()
    with pytest.raises(Exception):
        await adapter.respond_to_approval("missing", ApprovalDecision.ACCEPT)


@pytest.mark.asyncio
@pytest.mark.skipif(
    os.environ.get("CA_LIVE_OPENCODE") != "1",
    reason="set CA_LIVE_OPENCODE=1 to run against the authenticated OpenCode CLI",
)
async def test_opencode_live_two_turn_session():
    adapter = OpenCodeAdapter()
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
                session.id,
                TurnInput(input=[AgentInput(text=prompt)]),
            )
            completed_text = ""
            while True:
                event = await asyncio.wait_for(anext(adapter.events()), timeout=90)
                if event.provider_turn_id != turn_id:
                    continue
                if event.type == "message.completed":
                    completed_text = str(event.data.get("text", ""))
                if event.type == "turn.completed":
                    return completed_text

        first = await run_turn(
            "Reply with exactly CODEAGENT_GATEWAY_ONE and no other text."
        )
        second = await run_turn(
            "What exact token did I ask you to output in my previous message? "
            "Reply with only that token."
        )
        assert "CODEAGENT_GATEWAY_ONE" in first
        assert "CODEAGENT_GATEWAY_ONE" in second
    finally:
        await adapter.stop()

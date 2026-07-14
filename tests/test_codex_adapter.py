from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest

from core.services.agent_adapters.codex import CodexAdapter
from core.services.agent_protocol import (
    AgentInput,
    CreateSessionOptions,
    PermissionMode,
    TurnInput,
)


@pytest.mark.asyncio
async def test_codex_notification_translation_uses_generated_v2_shapes():
    adapter = CodexAdapter()
    await adapter._handle_notification(
        "item/agentMessage/delta",
        {
            "threadId": "thread-1",
            "turnId": "turn-1",
            "itemId": "item-1",
            "delta": "hello",
        },
    )
    event = await asyncio.wait_for(adapter._events.get(), timeout=1)
    assert event.type == "message.delta"
    assert event.provider_session_id == "thread-1"
    assert event.data == {"delta": "hello"}


@pytest.mark.asyncio
async def test_codex_approval_request_is_mapped_and_routable(monkeypatch):
    adapter = CodexAdapter()
    writes = []

    async def fake_write(message):
        writes.append(message)

    monkeypatch.setattr(adapter, "_write", fake_write)
    await adapter._handle_server_request(
        {
            "id": 42,
            "method": "item/commandExecution/requestApproval",
            "params": {
                "threadId": "thread-1",
                "turnId": "turn-1",
                "itemId": "item-1",
                "command": "git status",
                "cwd": "/workspace",
                "reason": "inspect repository",
            },
        }
    )
    event = await adapter._events.get()
    approval = event.data["approval"]
    assert approval["id"] == "codex:42"
    assert approval["command"] == "git status"

    await adapter.respond_to_approval("codex:42", "accept")
    assert writes == [{"id": 42, "result": {"decision": "accept"}}]


@pytest.mark.asyncio
@pytest.mark.skipif(
    os.environ.get("CA_LIVE_CODEX") != "1",
    reason="set CA_LIVE_CODEX=1 to run against the authenticated Codex CLI",
)
async def test_codex_live_two_turn_session():
    adapter = CodexAdapter()
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


@pytest.mark.asyncio
@pytest.mark.skipif(
    os.environ.get("CA_LIVE_CODEX") != "1",
    reason="set CA_LIVE_CODEX=1 to run against the authenticated Codex CLI",
)
async def test_codex_live_approval_decline_and_cancel():
    adapter = CodexAdapter()
    await adapter.start()
    try:
        session = await adapter.create_session(
            CreateSessionOptions(
                project_id=str(Path.cwd()),
                cwd=str(Path.cwd()),
                permission_mode=PermissionMode.WORKSPACE_WRITE,
            )
        )
        approval_turn = await adapter.start_turn(
            session.id,
            TurnInput(
                input=[
                    AgentInput(
                        text=(
                            "Run exactly this shell command and do nothing else: "
                            "touch /etc/codeagent-gateway-approval-probe"
                        )
                    )
                ]
            ),
        )
        approval_id = None
        while approval_id is None:
            event = await asyncio.wait_for(anext(adapter.events()), timeout=90)
            if event.provider_turn_id != approval_turn:
                continue
            if event.type == "approval.request":
                approval_id = str(event.data["approval"]["id"])
            elif event.type == "turn.completed":
                pytest.fail("Codex completed without requesting the expected approval")
        await adapter.respond_to_approval(approval_id, "decline")
        while True:
            event = await asyncio.wait_for(anext(adapter.events()), timeout=90)
            if event.provider_turn_id == approval_turn and event.type == "turn.completed":
                break

        cancel_turn = await adapter.start_turn(
            session.id,
            TurnInput(
                input=[
                    AgentInput(
                        text=(
                            "Run exactly this shell command and do nothing else: "
                            "touch /etc/codeagent-gateway-cancel-probe"
                        )
                    )
                ]
            ),
        )
        while True:
            event = await asyncio.wait_for(anext(adapter.events()), timeout=90)
            if event.provider_turn_id != cancel_turn:
                continue
            if event.type == "approval.request":
                break
            if event.type == "turn.completed":
                pytest.fail("Codex completed before the cancel gate became active")
        await adapter.cancel_turn(session.id, cancel_turn)
        while True:
            event = await asyncio.wait_for(anext(adapter.events()), timeout=30)
            if event.provider_turn_id == cancel_turn and event.type == "turn.completed":
                assert event.data.get("status") in {"interrupted", "cancelled", "failed"}
                break
    finally:
        await adapter.stop()

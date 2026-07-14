from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest
from claude_agent_sdk import (
    AssistantMessage,
    PermissionResultAllow,
    PermissionResultDeny,
    ResultMessage,
    StreamEvent,
    ToolPermissionContext,
    ToolResultBlock,
    ToolUseBlock,
)

from core.services.agent_adapters.claude import ClaudeAdapter
from core.services.agent_protocol import (
    AgentInput,
    ApprovalDecision,
    CreateSessionOptions,
    PermissionMode,
    TurnInput,
)


def test_claude_translates_stream_text_delta():
    adapter = ClaudeAdapter()
    started = adapter._translate_message(
        "session-1",
        "turn-1",
        StreamEvent(
            uuid="u1",
            session_id="session-1",
            event={"type": "message_start", "message": {"id": "msg-1"}},
        ),
    )
    assert started == []

    events = adapter._translate_message(
        "session-1",
        "turn-1",
        StreamEvent(
            uuid="u2",
            session_id="session-1",
            event={
                "type": "content_block_delta",
                "index": 0,
                "delta": {"type": "text_delta", "text": "hello"},
            },
        ),
    )
    assert len(events) == 1
    event = events[0]
    assert event.type == "message.delta"
    assert event.provider_session_id == "session-1"
    assert event.data == {"delta": "hello"}
    assert event.item_id == "msg-1:text:0"


def test_claude_translates_assistant_message_tool_use_and_result():
    adapter = ClaudeAdapter()
    tool_use = ToolUseBlock(id="tool-1", name="Bash", input={"command": "ls"})
    events = adapter._translate_message(
        "session-1",
        "turn-1",
        AssistantMessage(content=[tool_use], model="claude-x", message_id="msg-1"),
    )
    assert len(events) == 1
    assert events[0].type == "tool.started"
    assert events[0].data["tool"]["name"] == "Bash"
    assert events[0].item_id == "tool-1"

    # A duplicate ToolUseBlock for the same id must not be re-emitted.
    duplicate = adapter._translate_message(
        "session-1",
        "turn-1",
        AssistantMessage(content=[tool_use], model="claude-x", message_id="msg-1"),
    )
    assert duplicate == []

    result_block = ToolResultBlock(tool_use_id="tool-1", content="ok", is_error=False)
    events = adapter._translate_message(
        "session-1",
        "turn-1",
        AssistantMessage(content=[result_block], model="claude-x", message_id="msg-1"),
    )
    assert len(events) == 1
    assert events[0].type == "tool.completed"
    assert events[0].data["tool"]["status"] == "completed"
    assert events[0].item_id == "tool-1"


def test_claude_translates_result_message():
    adapter = ClaudeAdapter()
    events = adapter._translate_message(
        "session-1",
        "turn-1",
        ResultMessage(
            subtype="success",
            duration_ms=10,
            duration_api_ms=5,
            is_error=False,
            num_turns=1,
            session_id="session-1",
            total_cost_usd=0.01,
            usage={"input_tokens": 1},
        ),
    )
    assert [event.type for event in events] == ["usage.updated", "turn.completed"]
    assert events[1].data["status"] == "completed"


@pytest.mark.asyncio
async def test_claude_approval_accept_resolves_pending_future():
    adapter = ClaudeAdapter()
    context = ToolPermissionContext(tool_use_id="tool-1")
    future: asyncio.Future = asyncio.get_running_loop().create_future()
    adapter._pending_approvals["approval-1"] = ("session-1", future, context)

    await adapter.respond_to_approval("approval-1", ApprovalDecision.ACCEPT)

    result = await asyncio.wait_for(future, timeout=1)
    assert isinstance(result, PermissionResultAllow)
    assert "approval-1" not in adapter._pending_approvals


@pytest.mark.asyncio
async def test_claude_approval_decline_denies_without_interrupt():
    adapter = ClaudeAdapter()
    context = ToolPermissionContext(tool_use_id="tool-1")
    future: asyncio.Future = asyncio.get_running_loop().create_future()
    adapter._pending_approvals["approval-1"] = ("session-1", future, context)

    await adapter.respond_to_approval("approval-1", ApprovalDecision.DECLINE)

    result = await asyncio.wait_for(future, timeout=1)
    assert isinstance(result, PermissionResultDeny)
    assert result.interrupt is False


@pytest.mark.asyncio
async def test_claude_approval_cancel_denies_with_interrupt():
    adapter = ClaudeAdapter()
    context = ToolPermissionContext(tool_use_id="tool-1")
    future: asyncio.Future = asyncio.get_running_loop().create_future()
    adapter._pending_approvals["approval-1"] = ("session-1", future, context)

    await adapter.respond_to_approval("approval-1", ApprovalDecision.CANCEL)

    result = await asyncio.wait_for(future, timeout=1)
    assert isinstance(result, PermissionResultDeny)
    assert result.interrupt is True


@pytest.mark.asyncio
@pytest.mark.skipif(
    os.environ.get("CA_LIVE_CLAUDE") != "1",
    reason="set CA_LIVE_CLAUDE=1 to run against the authenticated Claude Code CLI",
)
async def test_claude_live_two_turn_session():
    adapter = ClaudeAdapter()
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

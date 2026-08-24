"""Tests for the CodeBuddy ACP adapter.

Unit-level behaviour with a stubbed
``_request`` (no live process). The key CodeBuddy-specific difference under
test is that its ``session/new`` response has NO ``modes`` block (permission
modes arrive as runtime notifications instead), so session creation must
never require them.
"""

from __future__ import annotations

import asyncio

import pytest

from core.services.agent_adapters.codebuddy import (
    CodeBuddyAdapter,
    CodeBuddyProtocolError,
)
from core.services.agent_protocol import (
    AgentInput,
    CreateSessionOptions,
    PermissionMode,
    TurnInput,
)


@pytest.mark.asyncio
async def test_codebuddy_stop_gives_up_if_process_never_reaps_after_kill():
    """A hung child that doesn't die even under SIGKILL must not block
    shutdown forever — stop() has to give up and move on."""

    class StubProcess:
        pid = 4242
        returncode = None

        def terminate(self):
            pass

        def kill(self):
            pass

        async def wait(self):
            await asyncio.sleep(999)

    adapter = CodeBuddyAdapter()
    adapter._process = StubProcess()

    start = asyncio.get_event_loop().time()
    await asyncio.wait_for(adapter.stop(), timeout=15)
    elapsed = asyncio.get_event_loop().time() - start
    assert elapsed < 10
    assert adapter._process is None


@pytest.mark.asyncio
async def test_codebuddy_create_session_without_modes_block(monkeypatch):
    """CodeBuddy's session/new has no ``modes`` block —
    creating a session must succeed anyway and not require a mode."""
    adapter = CodeBuddyAdapter()
    requests: list[tuple[str, dict]] = []

    async def request(method, params, timeout=120):
        requests.append((method, params))
        if method == "session/new":
            # Shape captured from a live `codebuddy --acp` probe: sessionId
            # plus a models block, no modes.
            return {
                "sessionId": "cb-session",
                "models": {"currentModelId": "hy3"},
            }
        return {}

    monkeypatch.setattr(adapter, "_request", request)
    session = await adapter.create_session(
        CreateSessionOptions(
            project_id="/workspace",
            cwd="/workspace",
            permission_mode=PermissionMode.READ_ONLY,
        )
    )

    assert session.id == "cb-session"
    assert session.model == "hy3"
    # No mode request is attempted and nothing raises.
    assert requests == [("session/new", {"cwd": "/workspace", "mcpServers": []})]


@pytest.mark.asyncio
async def test_codebuddy_create_session_sets_model_best_effort(monkeypatch):
    adapter = CodeBuddyAdapter()
    requests: list[tuple[str, dict]] = []

    async def request(method, params, timeout=120):
        requests.append((method, params))
        if method == "session/new":
            return {
                "sessionId": "cb-session",
                "models": {"currentModelId": "hy3"},
            }
        return {}

    monkeypatch.setattr(adapter, "_request", request)
    session = await adapter.create_session(
        CreateSessionOptions(
            project_id="/workspace",
            cwd="/workspace",
            model="deepseek-v4-pro",
        )
    )
    assert session.id == "cb-session"
    assert session.model == "deepseek-v4-pro"
    assert requests[-1] == (
        "session/set_model",
        {"sessionId": "cb-session", "modelId": "deepseek-v4-pro"},
    )


@pytest.mark.asyncio
async def test_codebuddy_set_model_failure_is_tolerated(monkeypatch):
    """A failing session/set_model must not break session creation."""

    async def request(method, params, timeout=120):
        if method == "session/new":
            return {
                "sessionId": "cb-session",
                "models": {"currentModelId": "hy3"},
            }
        raise CodeBuddyProtocolError("unsupported method")

    adapter = CodeBuddyAdapter()
    monkeypatch.setattr(adapter, "_request", request)
    session = await adapter.create_session(
        CreateSessionOptions(project_id="/workspace", cwd="/workspace", model="hy3-x")
    )
    assert session.id == "cb-session"


@pytest.mark.asyncio
async def test_codebuddy_create_session_requires_session_id(monkeypatch):
    adapter = CodeBuddyAdapter()

    async def request(_method, _params, timeout=120):
        return {}

    monkeypatch.setattr(adapter, "_request", request)
    with pytest.raises(CodeBuddyProtocolError, match="did not include sessionId"):
        await adapter.create_session(CreateSessionOptions(project_id="/w", cwd="/w"))


@pytest.mark.asyncio
async def test_codebuddy_maps_message_tool_and_usage_updates():
    adapter = CodeBuddyAdapter()
    adapter._active_turns["session-1"] = "turn-1"

    await adapter._handle_notification(
        "session/update",
        {
            "sessionId": "session-1",
            "update": {
                "sessionUpdate": "agent_message_chunk",
                "content": {"type": "text", "text": "你好"},
            },
        },
    )
    await adapter._handle_notification(
        "session/update",
        {
            "sessionId": "session-1",
            "update": {
                "sessionUpdate": "tool_call",
                "toolCallId": "tc-1",
                "status": "pending",
                "content": [{"type": "diff", "text": "--- a\n+++ b"}],
            },
        },
    )
    await adapter._handle_notification(
        "session/update",
        {
            "sessionId": "session-1",
            "update": {
                "sessionUpdate": "usage_update",
                "inputTokens": 10,
                "outputTokens": 5,
            },
        },
    )

    events = [e for e in adapter._events._queue]  # type: ignore[attr-defined]
    types = [e.type for e in events]
    assert "message.delta" in types
    assert "file.diff" in types
    assert "tool.started" in types
    assert "usage.updated" in types
    # The streamed delta accumulates for message.completed.
    assert adapter._message_text[("session-1", "turn-1")] == "你好"


@pytest.mark.asyncio
async def test_codebuddy_concurrent_turn_rejected():
    adapter = CodeBuddyAdapter()

    class NeverDoneTask:
        def done(self):
            return False

    adapter._turn_tasks["session-1"] = NeverDoneTask()  # type: ignore[assignment]
    with pytest.raises(CodeBuddyProtocolError, match="already has an active turn"):
        await adapter.start_turn("session-1", TurnInput(input=[AgentInput(text="hi")]))


@pytest.mark.asyncio
async def test_codebuddy_notification_requires_session_id():
    """An update without a sessionId is dropped, not crashed on."""
    adapter = CodeBuddyAdapter()
    await adapter._handle_notification(
        "session/update",
        {
            "sessionId": "",
            "update": {
                "sessionUpdate": "agent_message_chunk",
                "content": {"type": "text", "text": "x"},
            },
        },
    )
    assert adapter._events.empty()

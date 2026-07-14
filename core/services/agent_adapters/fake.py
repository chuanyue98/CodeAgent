"""Deterministic in-memory adapter used by contract and WebSocket tests."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from uuid import uuid4

from core.services.agent_protocol import (
    AdapterEvent,
    ApprovalDecision,
    CreateSessionOptions,
    ProviderCapabilities,
    ProviderSession,
    ResumeOptions,
    TurnInput,
)


class FakeAgentAdapter:
    provider_id = "fake"

    def __init__(self, queue_size: int = 128):
        self._events: asyncio.Queue[AdapterEvent | None] = asyncio.Queue(queue_size)
        self._started = False
        self.approvals: list[tuple[str, ApprovalDecision]] = []
        self.cancelled: list[tuple[str, str]] = []

    async def start(self) -> None:
        self._started = True

    async def stop(self) -> None:
        self._started = False
        await self._events.put(None)

    async def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            provider_id=self.provider_id,
            display_name="Fake Agent",
            available=self._started,
            unavailable_reason=None if self._started else "Adapter is not running",
            supports_resume=True,
            supports_steer=True,
            supports_cancel=True,
            supports_approvals=True,
            supports_file_diff=True,
            supports_tool_events=True,
        )

    def _require_started(self) -> None:
        if not self._started:
            raise RuntimeError("Fake adapter is not running")

    async def create_session(
        self, options: CreateSessionOptions
    ) -> ProviderSession:
        self._require_started()
        return ProviderSession(id=f"fake-thread-{uuid4().hex}", model=options.model)

    async def resume_session(
        self, provider_session_id: str, options: ResumeOptions
    ) -> ProviderSession:
        self._require_started()
        return ProviderSession(id=provider_session_id, model=options.model)

    async def start_turn(self, provider_session_id: str, turn: TurnInput) -> str:
        self._require_started()
        turn_id = f"fake-turn-{uuid4().hex}"
        item_id = f"fake-item-{uuid4().hex}"
        text = "".join(value.text for value in turn.input)
        await self._events.put(
            AdapterEvent(
                type="turn.started",
                provider_session_id=provider_session_id,
                provider_turn_id=turn_id,
            )
        )
        await self._events.put(
            AdapterEvent(
                type="message.delta",
                provider_session_id=provider_session_id,
                provider_turn_id=turn_id,
                item_id=item_id,
                data={"delta": f"Echo: {text}"},
            )
        )
        await self._events.put(
            AdapterEvent(
                type="message.completed",
                provider_session_id=provider_session_id,
                provider_turn_id=turn_id,
                item_id=item_id,
                data={"text": f"Echo: {text}"},
            )
        )
        await self._events.put(
            AdapterEvent(
                type="turn.completed",
                provider_session_id=provider_session_id,
                provider_turn_id=turn_id,
                data={"status": "completed"},
            )
        )
        return turn_id

    async def steer_turn(
        self, provider_session_id: str, provider_turn_id: str, turn: TurnInput
    ) -> None:
        self._require_started()
        await self._events.put(
            AdapterEvent(
                type="message.delta",
                provider_session_id=provider_session_id,
                provider_turn_id=provider_turn_id,
                data={"delta": "".join(value.text for value in turn.input)},
            )
        )

    async def cancel_turn(
        self, provider_session_id: str, provider_turn_id: str
    ) -> None:
        self._require_started()
        self.cancelled.append((provider_session_id, provider_turn_id))
        await self._events.put(
            AdapterEvent(
                type="turn.completed",
                provider_session_id=provider_session_id,
                provider_turn_id=provider_turn_id,
                data={"status": "interrupted"},
            )
        )

    async def respond_to_approval(
        self, approval_id: str, decision: ApprovalDecision
    ) -> None:
        self._require_started()
        self.approvals.append((approval_id, decision))

    async def events(self) -> AsyncIterator[AdapterEvent]:
        while True:
            event = await self._events.get()
            if event is None:
                return
            yield event

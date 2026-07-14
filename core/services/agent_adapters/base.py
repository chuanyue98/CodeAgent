"""Adapter contract implemented by interactive agent providers."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol

from core.services.agent_protocol import (
    AdapterEvent,
    ApprovalDecision,
    CreateSessionOptions,
    ProviderCapabilities,
    ProviderSession,
    ResumeOptions,
    TurnInput,
)


class AgentAdapter(Protocol):
    provider_id: str

    async def start(self) -> None: ...

    async def stop(self) -> None: ...

    async def capabilities(self) -> ProviderCapabilities: ...

    async def create_session(
        self, options: CreateSessionOptions
    ) -> ProviderSession: ...

    async def resume_session(
        self, provider_session_id: str, options: ResumeOptions
    ) -> ProviderSession: ...

    async def start_turn(
        self, provider_session_id: str, turn: TurnInput
    ) -> str: ...

    async def steer_turn(
        self, provider_session_id: str, provider_turn_id: str, turn: TurnInput
    ) -> None: ...

    async def cancel_turn(
        self, provider_session_id: str, provider_turn_id: str
    ) -> None: ...

    async def respond_to_approval(
        self, approval_id: str, decision: ApprovalDecision
    ) -> None: ...

    def events(self) -> AsyncIterator[AdapterEvent]: ...

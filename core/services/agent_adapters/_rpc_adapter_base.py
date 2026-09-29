"""Shared base mixin for JSON-RPC based agent adapters (Codex, CodeBuddy)."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

from core.services.agent_adapters._event_queue import (
    iter_events,
    put_event_dropping_oldest,
)
from core.services.agent_protocol import AdapterEvent


class RpcAdapterBase:
    """Base mixin providing common RPC, event queuing, and approval lifecycle helpers.

    Shared across JSON-RPC based adapters like Codex and CodeBuddy.
    """

    _events: asyncio.Queue[AdapterEvent | None]
    _transport: Any
    _approval_timeouts: dict[str, asyncio.Task[Any]]
    _adapter_label: str = "Adapter"
    _default_request_timeout: float = 60.0

    def events(self) -> AsyncIterator[AdapterEvent]:
        return iter_events(self._events)

    def _put_event(self, event: AdapterEvent) -> None:
        put_event_dropping_oldest(self._events, event, label=self._adapter_label)

    async def _emit_crash_event(self, error: Exception) -> None:
        self._put_event(
            AdapterEvent(
                type="error",
                provider_session_id="",
                data={
                    "code": "provider_crashed",
                    "message": str(error),
                    "retryable": True,
                },
            )
        )

    async def _request(
        self, method: str, params: dict[str, Any], timeout: float | None = None
    ) -> dict[str, Any]:
        return await self._transport.request(
            method,
            params,
            timeout=self._default_request_timeout if timeout is None else timeout,
        )

    async def _notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        await self._transport.notify(method, params)

    async def _write(self, message: dict[str, Any]) -> None:
        await self._transport.write(message)

    def _cancel_approval_timeout(self, approval_id: str) -> None:
        """Cancels a pending approval timeout watcher, if any."""
        task = self._approval_timeouts.pop(approval_id, None)
        if task is not None:
            task.cancel()

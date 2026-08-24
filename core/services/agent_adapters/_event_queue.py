"""Shared adapter event-queue helpers.

Every adapter buffers :class:`AdapterEvent` objects in a bounded
``asyncio.Queue`` and exposes them to callers through an ``events()`` async
generator. Two behaviors around that queue were duplicated (or, worse,
inconsistent) across the four adapters:

* ``claude.py`` and ``opencode.py`` guard the queue with a non-blocking
  ``put_nowait()`` that drops the oldest buffered event (and leaves a
  ``provider_backpressure`` error behind) when the queue is full.
* ``codex.py`` and ``codebuddy.py`` instead did a blocking ``await
  self._events.put(...)``. Because that call runs inside the single
  ``_read_loop`` task that also resolves pending JSON-RPC requests, a
  stalled consumer could fill the queue and wedge the entire adapter.

This module gives every adapter the same non-blocking, drop-oldest
behavior, plus the shared ``events()`` draining generator, from one place.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from core.services.agent_protocol import AdapterEvent


def put_event_dropping_oldest(
    queue: asyncio.Queue[AdapterEvent | None], event: AdapterEvent, *, label: str
) -> None:
    """Enqueue ``event`` without blocking, dropping the oldest entry on overflow.

    ``queue`` remains a plain ``asyncio.Queue`` (adapters and tests interact
    with it directly via ``.get()``/``.empty()``/etc.) -- this is a bounded
    non-blocking put, not a queue wrapper.
    """
    try:
        queue.put_nowait(event)
    except asyncio.QueueFull:
        try:
            queue.get_nowait()
        except asyncio.QueueEmpty:
            pass
        queue.put_nowait(
            AdapterEvent(
                type="error",
                provider_session_id="",
                data={
                    "code": "provider_backpressure",
                    "message": f"{label} event queue overflowed",
                    "retryable": True,
                },
            )
        )


async def iter_events(
    queue: asyncio.Queue[AdapterEvent | None],
) -> AsyncIterator[AdapterEvent]:
    """Drain ``queue`` until a ``None`` sentinel is seen."""
    while True:
        event = await queue.get()
        if event is None:
            return
        yield event

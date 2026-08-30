"""Event bus: persistence, fan-out, subscription, replay, and adapter bridging.

Extracted verbatim from the monolithic ``agent_gateway.py`` (the former
``publish``/``subscribe``/``_handle_adapter_event`` block).
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from core.services.agent_protocol import (
    AdapterEvent,
    AgentEvent,
    SessionStatus,
    utc_now,
)

if TYPE_CHECKING:
    from core.services.agent_gateway.gateway import AgentGateway


async def handle_adapter_event(
    gateway: AgentGateway, provider: str, adapter_event: AdapterEvent
) -> None:
    if adapter_event.type == "error" and not adapter_event.provider_session_id:
        failed_sessions = await asyncio.to_thread(
            gateway.store.list_sessions_by_provider, provider
        )
        for failed_session in failed_sessions:
            failed_session.status = SessionStatus.ERROR
            failed_session.updated_at = utc_now()
            await asyncio.to_thread(gateway.store.upsert_session, failed_session)
            await gateway.publish(
                AgentEvent(
                    type="error",
                    session_id=failed_session.id,
                    data=adapter_event.data,
                )
            )
        return
    session = await asyncio.to_thread(
        gateway.store.find_by_provider_session,
        provider,
        adapter_event.provider_session_id,
    )
    if session is None:
        return
    if adapter_event.type == "turn.started":
        session.status = SessionStatus.BUSY
    elif adapter_event.type == "turn.completed":
        session.status = SessionStatus.READY
    session.updated_at = utc_now()
    await asyncio.to_thread(gateway.store.upsert_session, session)
    await gateway.publish(
        AgentEvent(
            type=adapter_event.type,
            session_id=session.id,
            turn_id=adapter_event.provider_turn_id,
            item_id=adapter_event.item_id,
            data=adapter_event.data,
        )
    )


async def publish(gateway: AgentGateway, event: AgentEvent) -> AgentEvent:
    # Persist (and trim) off the event loop: this runs for every
    # adapter event including per-token message deltas, and each call
    # is a SQLite transaction. Fan-out to subscribers stays here -- it
    # only touches in-memory queues.
    persisted = await asyncio.to_thread(persist_event, gateway, event)
    stale: list[asyncio.Queue[AgentEvent | None]] = []
    for queue in gateway._subscribers.get(event.session_id, set()):
        if queue.full():
            queue.get_nowait()
            queue.put_nowait(None)
            stale.append(queue)
        else:
            queue.put_nowait(persisted.model_copy(deep=True))
    for queue in stale:
        gateway._subscribers[event.session_id].discard(queue)
    return persisted


def persist_event(gateway: AgentGateway, event: AgentEvent) -> AgentEvent:
    persisted = gateway.store.append_event(event)
    gateway.store.trim_events(event.session_id, keep=gateway.event_retention)
    return persisted


def subscribe(
    gateway: AgentGateway, session_id: str, after_sequence: int = 0
) -> asyncio.Queue[AgentEvent | None]:
    gateway.get_session(session_id)
    queue: asyncio.Queue[AgentEvent | None] = asyncio.Queue(
        gateway.subscriber_queue_size
    )
    replay = gateway.store.list_events(
        session_id, after_sequence=after_sequence, limit=gateway.subscriber_queue_size
    )
    for event in replay:
        queue.put_nowait(event)
    gateway._subscribers[session_id].add(queue)
    return queue


def unsubscribe(
    gateway: AgentGateway, session_id: str, queue: asyncio.Queue[AgentEvent | None]
) -> None:
    gateway._subscribers[session_id].discard(queue)
    if not gateway._subscribers[session_id]:
        gateway._subscribers.pop(session_id, None)

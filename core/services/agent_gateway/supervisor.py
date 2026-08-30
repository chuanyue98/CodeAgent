"""Adapter supervision: BUSY watchdog, restart pump, reconnect backoff.

Extracted verbatim from the monolithic ``agent_gateway.py`` (the former
``_busy_watchdog_loop`` / ``_supervise_adapter`` / reconnect helpers block).
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from core.logging_config import get_logger
from core.services.agent_adapters.base import AgentAdapter
from core.services.agent_gateway import events
from core.services.agent_protocol import (
    AgentEvent,
    SessionStatus,
    utc_now,
)

if TYPE_CHECKING:
    from core.services.agent_gateway.gateway import AgentGateway

logger = get_logger(__name__)


async def busy_watchdog_loop(gateway: AgentGateway) -> None:
    """Periodically recovers sessions stuck in BUSY state.

    When an adapter hangs without crashing (turn never completes,
    ``turn.completed`` never arrives), the session stays BUSY
    forever. This watchdog checks every 30 s and transitions any
    BUSY session whose ``updated_at`` exceeds ``busy_timeout`` to
    DISCONNECTED, publishing an error event so the frontend clears
    its ``activeTurnId``.
    """
    while gateway._started:
        await asyncio.sleep(30)
        if not gateway._started:
            return
        now = utc_now()
        for session in await asyncio.to_thread(
            gateway.store.list_sessions_by_status, SessionStatus.BUSY
        ):
            age = (now - session.updated_at).total_seconds()
            if age < gateway.busy_timeout:
                continue
            logger.warning(
                "Session %s has been BUSY for %.0fs (timeout %.0fs) — "
                "forcing to DISCONNECTED",
                session.id,
                age,
                gateway.busy_timeout,
            )
            session.status = SessionStatus.DISCONNECTED
            session.updated_at = now
            await asyncio.to_thread(gateway.store.upsert_session, session)
            await gateway.publish(
                AgentEvent(
                    type="error",
                    session_id=session.id,
                    data={
                        "code": "turn_stuck",
                        "message": (
                            f"Turn has been active for {int(age)}s without "
                            "completing. The session was reset to allow a "
                            "new turn."
                        ),
                        "retryable": True,
                    },
                )
            )


async def try_start_adapter(adapter: AgentAdapter) -> bool:
    """Starts an adapter, reporting failure rather than raising.

    One unavailable provider must never take down the Gateway or the
    other providers.
    """
    try:
        await adapter.start()
        return True
    except Exception as exc:
        logger.info("Provider %s is not available yet: %s", adapter.provider_id, exc)
        return False


async def supervise_adapter(
    gateway: AgentGateway, adapter: AgentAdapter, *, already_started: bool
) -> None:
    """Keeps one provider's event pump alive for the Gateway's lifetime.

    Restarts the pump on all three ways it can stop: ``events()`` raising,
    ``events()`` returning cleanly, and ``start()`` having failed at boot.
    Any of them left unattended takes the provider out until the server is
    restarted.

    Sessions are moved to DISCONNECTED, not ERROR: ERROR is terminal in
    the UI, and these sessions are resumable once the provider is back.
    """
    loop = asyncio.get_running_loop()
    delay = gateway.reconnect_base_delay
    running = already_started
    if not running:
        await publish_provider_state(gateway, adapter, connected=False)

    while gateway._started:
        if not running:
            running = await try_start_adapter(adapter)
            if not running:
                # Announce each failed attempt so a prolonged outage
                # visibly counts up in the UI instead of showing one
                # frozen "reconnecting" line for minutes.
                bump_attempt(gateway, adapter.provider_id)
                await publish_provider_state(
                    gateway,
                    adapter,
                    connected=False,
                    reason="Provider is still unavailable",
                )
                if not await wait_before_retry(gateway, adapter, delay):
                    return
                delay = min(delay * 2, gateway.reconnect_max_delay)
                continue
            gateway._reconnect_attempts.pop(adapter.provider_id, None)
            delay = gateway.reconnect_base_delay
            await publish_provider_state(gateway, adapter, connected=True)

        started_at = loop.time()
        reason = await pump_adapter(gateway, adapter)
        running = False
        if not gateway._started:
            return

        # A pump that stayed up a while then died is a fresh incident,
        # not an escalating crash loop -- reset the backoff so recovery
        # from an occasional blip stays fast while a provider that dies
        # on every start still backs off to the cap.
        if loop.time() - started_at >= gateway.healthy_run_seconds:
            delay = gateway.reconnect_base_delay
            gateway._reconnect_attempts.pop(adapter.provider_id, None)

        # Counted before publishing so the disconnect event names the
        # attempt that is about to happen ("attempt 1"), not the zero
        # attempts made so far.
        bump_attempt(gateway, adapter.provider_id)
        await mark_provider_disconnected(gateway, adapter, reason)
        try:
            await adapter.stop()
        except Exception as exc:
            logger.debug(
                "Ignoring stop() failure while restarting %s: %s",
                adapter.provider_id,
                exc,
            )
        if not await wait_before_retry(gateway, adapter, delay):
            return
        delay = min(delay * 2, gateway.reconnect_max_delay)


def bump_attempt(gateway: AgentGateway, provider_id: str) -> int:
    attempts = gateway._reconnect_attempts.get(provider_id, 0) + 1
    gateway._reconnect_attempts[provider_id] = attempts
    return attempts


async def pump_adapter(gateway: AgentGateway, adapter: AgentAdapter) -> str:
    """Forwards adapter events until the stream ends. Never raises.

    Returns a human-readable reason the stream ended, for the
    disconnect event the supervisor publishes.
    """
    try:
        async for adapter_event in adapter.events():
            await events.handle_adapter_event(
                gateway, adapter.provider_id, adapter_event
            )
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        return str(exc) or exc.__class__.__name__
    return "Provider event stream ended"


def request_reconnect(gateway: AgentGateway, provider_id: str) -> bool:
    """Wakes a supervisor that is sleeping between retries.

    Lets the UI offer "retry now" instead of making the user wait out a
    backoff that may be up to ``reconnect_max_delay`` long. Returns
    False for an unknown provider.
    """
    event = gateway._reconnect_now.get(provider_id)
    if event is None:
        return False
    event.set()
    return True


async def wait_before_retry(
    gateway: AgentGateway, adapter: AgentAdapter, delay: float
) -> bool:
    """Sleeps ``delay`` seconds, cut short by :func:`request_reconnect`.

    Returns False when the Gateway shut down during the wait, meaning
    the supervisor should exit rather than loop again.
    """
    logger.info(
        "Provider %s reconnect attempt %d in %.1fs",
        adapter.provider_id,
        gateway._reconnect_attempts.get(adapter.provider_id, 0),
        delay,
    )
    event = gateway._reconnect_now[adapter.provider_id]
    event.clear()
    try:
        await asyncio.wait_for(event.wait(), timeout=delay)
    except TimeoutError:
        pass
    return gateway._started


async def mark_provider_disconnected(
    gateway: AgentGateway, adapter: AgentAdapter, reason: str
) -> None:
    for session in await asyncio.to_thread(
        gateway.store.list_sessions_by_provider, adapter.provider_id
    ):
        if session.status in {SessionStatus.CLOSED, SessionStatus.DISCONNECTED}:
            continue
        session.status = SessionStatus.DISCONNECTED
        session.updated_at = utc_now()
        await asyncio.to_thread(gateway.store.upsert_session, session)
        await gateway.publish(
            AgentEvent(
                type="error",
                session_id=session.id,
                data={
                    "code": "provider_disconnected",
                    "message": reason,
                    "retryable": True,
                },
            )
        )
    await publish_provider_state(gateway, adapter, connected=False, reason=reason)


async def publish_provider_state(
    gateway: AgentGateway,
    adapter: AgentAdapter,
    *,
    connected: bool,
    reason: str | None = None,
) -> None:
    """Announces a provider's connectivity on each of its sessions.

    Events are per-session because that is the only channel clients
    subscribe to; a client with no session for this provider learns the
    same thing from ``GET /api/agent/providers``.
    """
    payload: dict = {
        "provider": adapter.provider_id,
        "connected": connected,
        "attempt": gateway._reconnect_attempts.get(adapter.provider_id, 0),
    }
    if reason:
        payload["reason"] = reason
    sessions = await asyncio.to_thread(
        gateway.store.list_sessions_by_provider, adapter.provider_id
    )
    for session in sessions:
        await gateway.publish(
            AgentEvent(
                type="provider.connected" if connected else "provider.disconnected",
                session_id=session.id,
                data=payload,
            )
        )

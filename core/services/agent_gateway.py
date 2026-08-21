"""Interactive Agent Gateway lifecycle, routing, replay, and capability gates."""

from __future__ import annotations

import asyncio
from collections import OrderedDict, defaultdict
from pathlib import Path
from uuid import uuid4

from core.logging_config import get_logger
from core.services.agent_adapters.base import AgentAdapter
from core.services.agent_protocol import (
    AdapterEvent,
    AgentAck,
    AgentCommand,
    AgentEvent,
    AgentSession,
    ApprovalDecision,
    CreateSessionOptions,
    PermissionMode,
    ProviderCapabilities,
    ResourceSnapshot,
    ResumeOptions,
    SessionStatus,
    TurnInput,
    utc_now,
    wire,
)
from core.services.agent_store import AgentStore
from core.services.config_service import ConfigService

logger = get_logger(__name__)


class AgentGatewayError(Exception):
    def __init__(self, code: str, message: str, *, status_code: int = 400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


class AgentGateway:
    def __init__(
        self,
        store: AgentStore,
        config_path: str | Path,
        adapters: list[AgentAdapter],
        *,
        subscriber_queue_size: int = 512,
        event_retention: int = 5000,
        reconnect_base_delay: float = 1.0,
        reconnect_max_delay: float = 60.0,
        healthy_run_seconds: float = 30.0,
        busy_timeout: float = 300.0,
    ):
        self.store = store
        self.config_path = Path(config_path)
        self.adapters = {adapter.provider_id: adapter for adapter in adapters}
        self.subscriber_queue_size = subscriber_queue_size
        self.event_retention = event_retention
        self.reconnect_base_delay = reconnect_base_delay
        self.reconnect_max_delay = reconnect_max_delay
        self.healthy_run_seconds = healthy_run_seconds
        self.busy_timeout = busy_timeout
        self._adapter_tasks: list[asyncio.Task] = []
        self._busy_watchdog: asyncio.Task | None = None
        self._subscribers: dict[str, set[asyncio.Queue[AgentEvent | None]]] = (
            defaultdict(set)
        )
        self._acks: dict[str, OrderedDict[str, AgentAck]] = defaultdict(OrderedDict)
        self._reconnect_now: dict[str, asyncio.Event] = {}
        self._reconnect_attempts: dict[str, int] = {}
        self._started = False

    async def start(self) -> None:
        if self._started:
            return
        self._started = True
        for adapter in self.adapters.values():
            self._reconnect_now[adapter.provider_id] = asyncio.Event()
            # The first attempt is awaited inline rather than left to the
            # supervisor: create_session() gates on adapter.capabilities()
            # .available, which only becomes true once start() has run, so
            # deferring it would let a request arriving immediately after
            # boot see a provider that is merely not-yet-started as
            # unavailable.
            started = await self._try_start_adapter(adapter)
            self._adapter_tasks.append(
                asyncio.create_task(
                    self._supervise_adapter(adapter, already_started=started),
                    name=f"agent-supervisor-{adapter.provider_id}",
                )
            )
        self._busy_watchdog = asyncio.create_task(
            self._busy_watchdog_loop(),
            name="agent-busy-watchdog",
        )

    async def stop(self) -> None:
        if not self._started:
            return
        self._started = False
        if self._busy_watchdog is not None:
            self._busy_watchdog.cancel()
            self._busy_watchdog = None
        for queue_set in self._subscribers.values():
            for queue in queue_set:
                if queue.full():
                    queue.get_nowait()
                queue.put_nowait(None)
        self._subscribers.clear()
        # _started is already False, so a supervisor whose pump unblocks
        # because of this stop() returns instead of treating it as a crash
        # and scheduling a reconnect.
        for adapter in self.adapters.values():
            try:
                await adapter.stop()
            except Exception as exc:
                logger.debug(
                    "Ignoring stop() failure for %s during shutdown: %s",
                    adapter.provider_id,
                    exc,
                )
        # Wake any supervisor currently sleeping out a reconnect backoff so
        # it observes the cleared _started flag and exits promptly, rather
        # than sitting in a wait_for() that cancel() then has to interrupt.
        for event in self._reconnect_now.values():
            event.set()
        for task in self._adapter_tasks:
            task.cancel()
        await asyncio.gather(*self._adapter_tasks, return_exceptions=True)
        self._adapter_tasks.clear()
        self._reconnect_now.clear()
        self._reconnect_attempts.clear()
        for session in self.store.list_sessions(limit=10_000):
            if session.status in {SessionStatus.BUSY, SessionStatus.READY}:
                session.status = SessionStatus.DISCONNECTED
                session.updated_at = utc_now()
                self.store.upsert_session(session)
        self.store.close()

    async def providers(self) -> list[ProviderCapabilities]:
        results: list[ProviderCapabilities] = []
        for adapter in self.adapters.values():
            try:
                results.append(await adapter.capabilities())
            except Exception as exc:
                results.append(
                    ProviderCapabilities(
                        provider_id=adapter.provider_id,
                        display_name=adapter.provider_id.title(),
                        available=False,
                        unavailable_reason=str(exc),
                    )
                )
        return results

    def _registered_workspace(self, project_id: str) -> tuple[str, str]:
        """Resolve and validate a requested workspace against the registry.

        Returns ``(cwd, identity)``: ``cwd`` is the fully resolved path used
        to actually launch the provider CLI, while ``identity`` is the
        registry's own path string for that entry. The two can differ on
        Windows (``resolve()`` always normalizes to backslashes) or when the
        registry entry uses ``~``/relative segments -- callers must persist
        ``identity`` as the session's project_id so it stays byte-equal to
        what ``GET /api/projects`` returns for the frontend to match on.
        """
        config, warnings = ConfigService(self.config_path).get_config()
        if warnings:
            raise AgentGatewayError("config_error", warnings[0], status_code=500)
        requested = Path(project_id).expanduser().resolve()
        if not requested.is_dir():
            raise AgentGatewayError(
                "workspace_unavailable", "Selected workspace is unavailable"
            )
        for project in config.get("project_registry", []):
            if not isinstance(project, dict) or not isinstance(
                project.get("path"), str
            ):
                continue
            if Path(project["path"]).expanduser().resolve() == requested:
                return str(requested), project["path"]
        raise AgentGatewayError(
            "workspace_not_registered",
            "Select a workspace registered in Settings before starting an agent",
        )

    def _resource_snapshot(self, workspace: str) -> ResourceSnapshot:
        config, _warnings = ConfigService(self.config_path).get_config()
        requested = Path(workspace).expanduser().resolve()
        group_name: str | None = None
        for project in config.get("project_registry", []):
            if not isinstance(project, dict) or not isinstance(
                project.get("path"), str
            ):
                continue
            if Path(project["path"]).expanduser().resolve() == requested:
                group_name = (
                    project.get("group")
                    if isinstance(project.get("group"), str)
                    else None
                )
                break
        definition = config.get("groups", {}).get(group_name or "", {})
        if not isinstance(definition, dict):
            definition = {}

        def values(key: str) -> list[str]:
            raw = definition.get(key, [])
            return (
                [item for item in raw if isinstance(item, str)]
                if isinstance(raw, list)
                else []
            )

        return ResourceSnapshot(
            group=group_name,
            skills=values("skills"),
            prompts=values("prompts"),
            hooks=values("hooks"),
            plugins=values("plugins"),
        )

    def get_session(self, session_id: str) -> AgentSession:
        session = self.store.get_session(session_id)
        if session is None:
            raise AgentGatewayError(
                "session_not_found", "Session not found", status_code=404
            )
        return session

    def list_sessions(self, limit: int = 100) -> list[AgentSession]:
        return self.store.list_sessions(limit=limit)

    async def create_session(
        self,
        *,
        provider: str,
        project_id: str,
        model: str | None = None,
        permission_mode: PermissionMode = PermissionMode.WORKSPACE_WRITE,
        title: str | None = None,
    ) -> AgentSession:
        adapter = self.adapters.get(provider)
        if adapter is None:
            raise AgentGatewayError(
                "provider_not_found", "Provider not found", status_code=404
            )
        capabilities = await adapter.capabilities()
        if not capabilities.available:
            raise AgentGatewayError(
                "provider_unavailable",
                capabilities.unavailable_reason or "Provider is unavailable",
                status_code=503,
            )
        cwd, project_identity = self._registered_workspace(project_id)
        resource_snapshot = self._resource_snapshot(cwd)
        provider_session = await adapter.create_session(
            CreateSessionOptions(
                project_id=project_identity,
                cwd=cwd,
                model=model,
                permission_mode=permission_mode,
            )
        )
        session = AgentSession(
            id=f"agent_{uuid4().hex}",
            provider=provider,
            provider_session_id=provider_session.id,
            project_id=project_identity,
            cwd=cwd,
            title=title,
            model=provider_session.model or model,
            permission_mode=permission_mode,
            status=SessionStatus.READY,
            capability_snapshot=capabilities,
            resource_snapshot=resource_snapshot,
        )
        self.store.upsert_session(session)
        await self.publish(
            AgentEvent(
                type="session.ready",
                session_id=session.id,
                data={"session": wire(session)},
            )
        )
        return self.get_session(session.id)

    async def import_session(
        self,
        *,
        provider: str,
        provider_session_id: str,
        project_id: str,
        model: str | None = None,
        permission_mode: PermissionMode = PermissionMode.WORKSPACE_WRITE,
        title: str | None = None,
    ) -> AgentSession:
        existing = self.store.find_by_provider_session(provider, provider_session_id)
        if existing is not None:
            return await self.resume_session(existing.id)

        adapter = self.adapters.get(provider)
        if adapter is None:
            raise AgentGatewayError(
                "provider_not_found", "Provider not found", status_code=404
            )
        capabilities = await adapter.capabilities()
        if not capabilities.available:
            raise AgentGatewayError(
                "provider_unavailable",
                capabilities.unavailable_reason or "Provider is unavailable",
                status_code=503,
            )
        if not capabilities.supports_resume:
            raise AgentGatewayError(
                "unsupported_capability",
                "This provider does not support importing native sessions",
            )
        cwd, project_identity = self._registered_workspace(project_id)
        resource_snapshot = self._resource_snapshot(cwd)
        resumed = await adapter.resume_session(
            provider_session_id,
            ResumeOptions(
                cwd=cwd,
                model=model,
                permission_mode=permission_mode,
            ),
        )
        session = AgentSession(
            id=f"agent_{uuid4().hex}",
            provider=provider,
            provider_session_id=resumed.id,
            project_id=project_identity,
            cwd=cwd,
            title=title,
            model=resumed.model or model,
            permission_mode=permission_mode,
            status=SessionStatus.READY,
            capability_snapshot=capabilities,
            resource_snapshot=resource_snapshot,
        )
        self.store.upsert_session(session)
        await self.publish(
            AgentEvent(
                type="session.ready",
                session_id=session.id,
                data={"session": wire(session)},
            )
        )
        return self.get_session(session.id)

    async def resume_session(self, session_id: str) -> AgentSession:
        session = self.get_session(session_id)
        adapter = self._adapter_for(session)
        self._registered_workspace(session.project_id)
        if not session.capability_snapshot.supports_resume:
            raise AgentGatewayError(
                "unsupported_capability",
                "This provider does not support session resume",
            )
        resumed = await adapter.resume_session(
            session.provider_session_id,
            ResumeOptions(
                cwd=session.cwd,
                model=session.model,
                permission_mode=session.permission_mode,
            ),
        )
        session.provider_session_id = resumed.id
        session.model = resumed.model or session.model
        session.status = SessionStatus.READY
        session.updated_at = utc_now()
        self.store.upsert_session(session)
        await self.publish(
            AgentEvent(
                type="session.ready",
                session_id=session.id,
                data={"session": wire(session)},
            )
        )
        return self.get_session(session.id)

    def delete_session(self, session_id: str) -> bool:
        self.get_session(session_id)
        return self.store.delete_session(session_id)

    def _adapter_for(self, session: AgentSession) -> AgentAdapter:
        adapter = self.adapters.get(session.provider)
        if adapter is None:
            raise AgentGatewayError(
                "provider_unavailable",
                "Session provider is unavailable",
                status_code=503,
            )
        return adapter

    async def start_turn(self, session_id: str, turn: TurnInput) -> str:
        session = self.get_session(session_id)
        adapter = self._adapter_for(session)
        session.status = SessionStatus.BUSY
        session.updated_at = utc_now()
        self.store.upsert_session(session)
        await self.publish(
            AgentEvent(
                type="message.user",
                session_id=session.id,
                data={"text": "\n".join(value.text for value in turn.input)},
            )
        )
        try:
            return await adapter.start_turn(session.provider_session_id, turn)
        except Exception:
            session = self.get_session(session_id)
            session.status = SessionStatus.READY
            session.updated_at = utc_now()
            self.store.upsert_session(session)
            raise

    async def steer_turn(self, session_id: str, turn_id: str, turn: TurnInput) -> None:
        session = self.get_session(session_id)
        if not session.capability_snapshot.supports_steer:
            raise AgentGatewayError(
                "unsupported_capability", "This provider does not support turn steering"
            )
        await self._adapter_for(session).steer_turn(
            session.provider_session_id, turn_id, turn
        )

    async def cancel_turn(self, session_id: str, turn_id: str) -> None:
        session = self.get_session(session_id)
        if not session.capability_snapshot.supports_cancel:
            raise AgentGatewayError(
                "unsupported_capability",
                "This provider does not support turn cancellation",
            )
        await self._adapter_for(session).cancel_turn(
            session.provider_session_id, turn_id
        )

    async def respond_to_approval(
        self, session_id: str, approval_id: str, decision: ApprovalDecision
    ) -> None:
        session = self.get_session(session_id)
        if not session.capability_snapshot.supports_approvals:
            raise AgentGatewayError(
                "unsupported_capability", "This provider does not support approvals"
            )
        await self._adapter_for(session).respond_to_approval(approval_id, decision)
        await self.publish(
            AgentEvent(
                type="approval.resolved",
                session_id=session.id,
                data={"approvalId": approval_id, "decision": decision},
            )
        )

    async def execute_command(self, command: AgentCommand) -> AgentAck:
        if command.session_id != command.session_id.strip():
            raise AgentGatewayError("invalid_command", "Invalid session id")
        cached = self._acks[command.session_id].get(command.request_id)
        if cached:
            return cached
        result: dict = {}
        if command.type == "session.resume":
            result = {"session": wire(await self.resume_session(command.session_id))}
        elif command.type == "turn.start":
            if not command.input:
                raise AgentGatewayError("invalid_command", "turn.start requires input")
            result = {
                "turnId": await self.start_turn(
                    command.session_id, TurnInput(input=command.input)
                )
            }
        elif command.type == "turn.steer":
            if not command.turn_id or not command.input:
                raise AgentGatewayError(
                    "invalid_command", "turn.steer requires turnId and input"
                )
            await self.steer_turn(
                command.session_id, command.turn_id, TurnInput(input=command.input)
            )
        elif command.type == "turn.cancel":
            if not command.turn_id:
                raise AgentGatewayError(
                    "invalid_command", "turn.cancel requires turnId"
                )
            await self.cancel_turn(command.session_id, command.turn_id)
        elif command.type == "approval.respond":
            if not command.approval_id or command.decision is None:
                raise AgentGatewayError(
                    "invalid_command",
                    "approval.respond requires approvalId and decision",
                )
            await self.respond_to_approval(
                command.session_id, command.approval_id, command.decision
            )
        ack = AgentAck(
            request_id=command.request_id, command=command.type, result=result
        )
        cache = self._acks[command.session_id]
        cache[command.request_id] = ack
        cache.move_to_end(command.request_id)
        while len(cache) > 256:
            cache.popitem(last=False)
        return ack

    async def _busy_watchdog_loop(self) -> None:
        """Periodically recovers sessions stuck in BUSY state.

        When an adapter hangs without crashing (turn never completes,
        ``turn.completed`` never arrives), the session stays BUSY
        forever. This watchdog checks every 30 s and transitions any
        BUSY session whose ``updated_at`` exceeds ``busy_timeout`` to
        DISCONNECTED, publishing an error event so the frontend clears
        its ``activeTurnId``.
        """
        while self._started:
            await asyncio.sleep(30)
            if not self._started:
                return
            now = utc_now()
            for session in self.store.list_sessions(limit=10_000):
                if session.status != SessionStatus.BUSY:
                    continue
                age = (now - session.updated_at).total_seconds()
                if age < self.busy_timeout:
                    continue
                logger.warning(
                    "Session %s has been BUSY for %.0fs (timeout %.0fs) — "
                    "forcing to DISCONNECTED",
                    session.id,
                    age,
                    self.busy_timeout,
                )
                session.status = SessionStatus.DISCONNECTED
                session.updated_at = now
                self.store.upsert_session(session)
                await self.publish(
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

    async def _try_start_adapter(self, adapter: AgentAdapter) -> bool:
        """Starts an adapter, reporting failure rather than raising.

        One unavailable provider must never take down the Gateway or the
        other providers.
        """
        try:
            await adapter.start()
            return True
        except Exception as exc:
            logger.info(
                "Provider %s is not available yet: %s", adapter.provider_id, exc
            )
            return False

    async def _supervise_adapter(
        self, adapter: AgentAdapter, *, already_started: bool
    ) -> None:
        """Keeps one provider's event pump alive for the Gateway's lifetime.

        Previously this was a bare pump: when ``events()`` raised, every
        session for that provider was marked ERROR and the task simply
        returned. Nothing ever restarted it, so a single transient failure
        -- a CLI subprocess dying, a protocol hiccup, a provider that was
        merely slow to install -- removed that provider permanently until
        the user restarted the whole server. A long-lived ``ca ui`` would
        lose providers one by one with no way back.

        Three failure modes are handled here, all of which used to be
        terminal:

        * ``events()`` raises -- the crash case.
        * ``events()`` returns cleanly (the ``None`` sentinel in
          ``iter_events``), which produced no error event at all: the pump
          just stopped and the provider went quiet with the UI still
          showing it as healthy.
        * ``start()`` failed at boot, which previously skipped creating a
          pump task entirely.

        Sessions are moved to DISCONNECTED rather than ERROR because they
        are recoverable: ERROR is terminal in the UI, and the session is
        resumable again as soon as the provider comes back.
        """
        loop = asyncio.get_running_loop()
        delay = self.reconnect_base_delay
        running = already_started
        if not running:
            await self._publish_provider_state(adapter, connected=False)

        while self._started:
            if not running:
                running = await self._try_start_adapter(adapter)
                if not running:
                    # Announce each failed attempt so a prolonged outage
                    # visibly counts up in the UI instead of showing one
                    # frozen "reconnecting" line for minutes.
                    self._bump_attempt(adapter.provider_id)
                    await self._publish_provider_state(
                        adapter,
                        connected=False,
                        reason="Provider is still unavailable",
                    )
                    if not await self._wait_before_retry(adapter, delay):
                        return
                    delay = min(delay * 2, self.reconnect_max_delay)
                    continue
                self._reconnect_attempts.pop(adapter.provider_id, None)
                delay = self.reconnect_base_delay
                await self._publish_provider_state(adapter, connected=True)

            started_at = loop.time()
            reason = await self._pump_adapter(adapter)
            running = False
            if not self._started:
                return

            # A pump that stayed up a while then died is a fresh incident,
            # not an escalating crash loop -- reset the backoff so recovery
            # from an occasional blip stays fast while a provider that dies
            # on every start still backs off to the cap.
            if loop.time() - started_at >= self.healthy_run_seconds:
                delay = self.reconnect_base_delay
                self._reconnect_attempts.pop(adapter.provider_id, None)

            # Counted before publishing so the disconnect event names the
            # attempt that is about to happen ("attempt 1"), not the zero
            # attempts made so far.
            self._bump_attempt(adapter.provider_id)
            await self._mark_provider_disconnected(adapter, reason)
            try:
                await adapter.stop()
            except Exception as exc:
                logger.debug(
                    "Ignoring stop() failure while restarting %s: %s",
                    adapter.provider_id,
                    exc,
                )
            if not await self._wait_before_retry(adapter, delay):
                return
            delay = min(delay * 2, self.reconnect_max_delay)

    def _bump_attempt(self, provider_id: str) -> int:
        attempts = self._reconnect_attempts.get(provider_id, 0) + 1
        self._reconnect_attempts[provider_id] = attempts
        return attempts

    async def _pump_adapter(self, adapter: AgentAdapter) -> str:
        """Forwards adapter events until the stream ends. Never raises.

        Returns a human-readable reason the stream ended, for the
        disconnect event the supervisor publishes.
        """
        try:
            async for adapter_event in adapter.events():
                await self._handle_adapter_event(adapter.provider_id, adapter_event)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            return str(exc) or exc.__class__.__name__
        return "Provider event stream ended"

    def request_reconnect(self, provider_id: str) -> bool:
        """Wakes a supervisor that is sleeping between retries.

        Lets the UI offer "retry now" instead of making the user wait out a
        backoff that may be up to ``reconnect_max_delay`` long. Returns
        False for an unknown provider.
        """
        event = self._reconnect_now.get(provider_id)
        if event is None:
            return False
        event.set()
        return True

    async def _wait_before_retry(self, adapter: AgentAdapter, delay: float) -> bool:
        """Sleeps ``delay`` seconds, cut short by :meth:`request_reconnect`.

        Returns False when the Gateway shut down during the wait, meaning
        the supervisor should exit rather than loop again.
        """
        logger.info(
            "Provider %s reconnect attempt %d in %.1fs",
            adapter.provider_id,
            self._reconnect_attempts.get(adapter.provider_id, 0),
            delay,
        )
        event = self._reconnect_now[adapter.provider_id]
        event.clear()
        try:
            await asyncio.wait_for(event.wait(), timeout=delay)
        except TimeoutError:
            pass
        return self._started

    async def _mark_provider_disconnected(
        self, adapter: AgentAdapter, reason: str
    ) -> None:
        for session in self.store.list_sessions_by_provider(adapter.provider_id):
            if session.status in {SessionStatus.CLOSED, SessionStatus.DISCONNECTED}:
                continue
            session.status = SessionStatus.DISCONNECTED
            session.updated_at = utc_now()
            self.store.upsert_session(session)
            await self.publish(
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
        await self._publish_provider_state(adapter, connected=False, reason=reason)

    async def _publish_provider_state(
        self, adapter: AgentAdapter, *, connected: bool, reason: str | None = None
    ) -> None:
        """Announces a provider's connectivity on each of its sessions.

        Events are per-session because that is the only channel clients
        subscribe to; a client with no session for this provider learns the
        same thing from ``GET /api/agent/providers``.
        """
        payload: dict = {
            "provider": adapter.provider_id,
            "connected": connected,
            "attempt": self._reconnect_attempts.get(adapter.provider_id, 0),
        }
        if reason:
            payload["reason"] = reason
        for session in self.store.list_sessions_by_provider(adapter.provider_id):
            await self.publish(
                AgentEvent(
                    type="provider.connected" if connected else "provider.disconnected",
                    session_id=session.id,
                    data=payload,
                )
            )

    async def _handle_adapter_event(
        self, provider: str, adapter_event: AdapterEvent
    ) -> None:
        if adapter_event.type == "error" and not adapter_event.provider_session_id:
            for failed_session in self.store.list_sessions_by_provider(provider):
                failed_session.status = SessionStatus.ERROR
                failed_session.updated_at = utc_now()
                self.store.upsert_session(failed_session)
                await self.publish(
                    AgentEvent(
                        type="error",
                        session_id=failed_session.id,
                        data=adapter_event.data,
                    )
                )
            return
        session = self.store.find_by_provider_session(
            provider, adapter_event.provider_session_id
        )
        if session is None:
            return
        if adapter_event.type == "turn.started":
            session.status = SessionStatus.BUSY
        elif adapter_event.type == "turn.completed":
            session.status = SessionStatus.READY
        session.updated_at = utc_now()
        self.store.upsert_session(session)
        await self.publish(
            AgentEvent(
                type=adapter_event.type,
                session_id=session.id,
                turn_id=adapter_event.provider_turn_id,
                item_id=adapter_event.item_id,
                data=adapter_event.data,
            )
        )

    async def publish(self, event: AgentEvent) -> AgentEvent:
        persisted = self.store.append_event(event)
        self.store.trim_events(event.session_id, keep=self.event_retention)
        stale: list[asyncio.Queue[AgentEvent | None]] = []
        for queue in self._subscribers.get(event.session_id, set()):
            if queue.full():
                queue.get_nowait()
                queue.put_nowait(None)
                stale.append(queue)
            else:
                queue.put_nowait(persisted.model_copy(deep=True))
        for queue in stale:
            self._subscribers[event.session_id].discard(queue)
        return persisted

    def subscribe(
        self, session_id: str, after_sequence: int = 0
    ) -> asyncio.Queue[AgentEvent | None]:
        self.get_session(session_id)
        queue: asyncio.Queue[AgentEvent | None] = asyncio.Queue(
            self.subscriber_queue_size
        )
        replay = self.store.list_events(
            session_id, after_sequence=after_sequence, limit=self.subscriber_queue_size
        )
        for event in replay:
            queue.put_nowait(event)
        self._subscribers[session_id].add(queue)
        return queue

    def unsubscribe(
        self, session_id: str, queue: asyncio.Queue[AgentEvent | None]
    ) -> None:
        self._subscribers[session_id].discard(queue)
        if not self._subscribers[session_id]:
            self._subscribers.pop(session_id, None)

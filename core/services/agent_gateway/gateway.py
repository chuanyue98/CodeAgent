"""Thin facade composing the agent gateway's submodules.

The monolithic ``agent_gateway.py`` was split into this package; this class
keeps every public and test-referenced attribute/method on one object and
delegates to:

- :mod:`resources` — workspace registry + prompt/resource resolution
- :mod:`sessions` — session CRUD, turns, approvals
- :mod:`commands` — command execution, dedup, ack cache
- :mod:`events` — persistence, fan-out, replay
- :mod:`supervisor` — adapter restart pump, watchdog, backoff
"""

from __future__ import annotations

import asyncio
from collections import OrderedDict, defaultdict
from pathlib import Path

from core.logging_config import get_logger
from core.services.agent_adapters.base import AgentAdapter
from core.services.agent_gateway import (
    commands,
    events,
    resources,
    sessions,
    supervisor,
)
from core.services.agent_protocol import (
    AdapterEvent,
    AgentAck,
    AgentCommand,
    AgentEvent,
    AgentSession,
    ApprovalDecision,
    PermissionMode,
    ProviderCapabilities,
    ResourceSnapshot,
    SessionStatus,
    TurnInput,
    utc_now,
)
from core.services.agent_store import AgentStore
from core.services.config_service import ConfigService

logger = get_logger(__name__)

INJECTED_KINDS = resources.INJECTED_KINDS
EXCLUDED_PROMPT_FILES = resources.EXCLUDED_PROMPT_FILES


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
        ack_cache_limit: int = 256,
    ):
        self.store = store
        self.config_path = Path(config_path)
        # One shared reader: ConfigService caches by mtime, and per-call
        # construction would re-stat the file on every session operation.
        self._config_service = ConfigService(self.config_path)
        self.adapters = {adapter.provider_id: adapter for adapter in adapters}
        self.subscriber_queue_size = subscriber_queue_size
        self.event_retention = event_retention
        self.reconnect_base_delay = reconnect_base_delay
        self.reconnect_max_delay = reconnect_max_delay
        self.healthy_run_seconds = healthy_run_seconds
        self.busy_timeout = busy_timeout
        self.ack_cache_limit = ack_cache_limit
        self._adapter_tasks: list[asyncio.Task] = []
        self._busy_watchdog: asyncio.Task | None = None
        self._subscribers: dict[str, set[asyncio.Queue[AgentEvent | None]]] = (
            defaultdict(set)
        )
        self._acks: dict[str, OrderedDict[str, AgentAck]] = defaultdict(OrderedDict)
        # request_id -> future for commands still executing, so a duplicate
        # retry waits for the original instead of running the command twice.
        self._commands_in_flight: dict[tuple[str, str], asyncio.Future[AgentAck]] = {}
        self._reconnect_now: dict[str, asyncio.Event] = {}
        self._reconnect_attempts: dict[str, int] = {}
        self._resources_warned: set[str] = set()
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
            started = await supervisor.try_start_adapter(adapter)
            self._adapter_tasks.append(
                asyncio.create_task(
                    supervisor.supervise_adapter(
                        self, adapter, already_started=started
                    ),
                    name=f"agent-supervisor-{adapter.provider_id}",
                )
            )
        self._busy_watchdog = asyncio.create_task(
            supervisor.busy_watchdog_loop(self),
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
        self._resources_warned.clear()
        for session in await asyncio.to_thread(
            self.store.list_sessions_by_status,
            SessionStatus.BUSY,
            SessionStatus.READY,
        ):
            session.status = SessionStatus.DISCONNECTED
            session.updated_at = utc_now()
            await asyncio.to_thread(self.store.upsert_session, session)
        await asyncio.to_thread(self.store.close)

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

    # -- resources ----------------------------------------------------------

    def _registered_workspace(self, project_id: str) -> tuple[str, str]:
        return resources.registered_workspace(self, project_id)

    def _resource_snapshot(
        self, workspace: str, config: dict | None = None
    ) -> ResourceSnapshot:
        return resources.resource_snapshot(self, workspace, config)

    @staticmethod
    def _prompt_root(config: dict) -> Path:
        return resources.prompt_root(config)

    def _assemble_system_prompt(
        self, prompt_groups: list[str], config: dict
    ) -> tuple[str, list[dict]] | None:
        return resources.assemble_system_prompt(prompt_groups, config)

    # -- sessions -----------------------------------------------------------

    def get_session(self, session_id: str) -> AgentSession:
        return sessions.get_session(self, session_id)

    def list_sessions(self, limit: int = 100) -> list[AgentSession]:
        return sessions.list_sessions(self, limit=limit)

    async def create_session(
        self,
        *,
        provider: str,
        project_id: str,
        model: str | None = None,
        permission_mode: PermissionMode = PermissionMode.WORKSPACE_WRITE,
        title: str | None = None,
    ) -> AgentSession:
        return await sessions.create_session(
            self,
            provider=provider,
            project_id=project_id,
            model=model,
            permission_mode=permission_mode,
            title=title,
        )

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
        return await sessions.import_session(
            self,
            provider=provider,
            provider_session_id=provider_session_id,
            project_id=project_id,
            model=model,
            permission_mode=permission_mode,
            title=title,
        )

    async def resume_session(self, session_id: str) -> AgentSession:
        return await sessions.resume_session(self, session_id)

    def delete_session(self, session_id: str) -> bool:
        return sessions.delete_session(self, session_id)

    def _adapter_for(self, session: AgentSession) -> AgentAdapter:
        return sessions.adapter_for(self, session)

    async def start_turn(self, session_id: str, turn: TurnInput) -> str:
        return await sessions.start_turn(self, session_id, turn)

    async def steer_turn(self, session_id: str, turn_id: str, turn: TurnInput) -> None:
        await sessions.steer_turn(self, session_id, turn_id, turn)

    async def cancel_turn(self, session_id: str, turn_id: str) -> None:
        await sessions.cancel_turn(self, session_id, turn_id)

    async def respond_to_approval(
        self, session_id: str, approval_id: str, decision: ApprovalDecision
    ) -> None:
        await sessions.respond_to_approval(self, session_id, approval_id, decision)

    # -- commands -----------------------------------------------------------

    async def execute_command(self, command: AgentCommand) -> AgentAck:
        return await commands.execute_command(self, command)

    # -- events -------------------------------------------------------------

    async def publish(self, event: AgentEvent) -> AgentEvent:
        return await events.publish(self, event)

    def _persist_event(self, event: AgentEvent) -> AgentEvent:
        return events.persist_event(self, event)

    def subscribe(
        self, session_id: str, after_sequence: int = 0
    ) -> asyncio.Queue[AgentEvent | None]:
        return events.subscribe(self, session_id, after_sequence)

    def unsubscribe(
        self, session_id: str, queue: asyncio.Queue[AgentEvent | None]
    ) -> None:
        events.unsubscribe(self, session_id, queue)

    async def _handle_adapter_event(
        self, provider: str, adapter_event: AdapterEvent
    ) -> None:
        await events.handle_adapter_event(self, provider, adapter_event)

    # -- supervision ---------------------------------------------------------

    def request_reconnect(self, provider_id: str) -> bool:
        return supervisor.request_reconnect(self, provider_id)

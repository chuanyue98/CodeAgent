"""Interactive Agent Gateway lifecycle, routing, replay, and capability gates."""

from __future__ import annotations

import asyncio
from collections import OrderedDict, defaultdict
from pathlib import Path
from uuid import uuid4

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
    ResumeOptions,
    SessionStatus,
    TurnInput,
    ProviderCapabilities,
    ResourceSnapshot,
    utc_now,
    wire,
)
from core.services.agent_store import AgentStore
from core.services.config_service import ConfigService


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
    ):
        self.store = store
        self.config_path = Path(config_path)
        self.adapters = {adapter.provider_id: adapter for adapter in adapters}
        self.subscriber_queue_size = subscriber_queue_size
        self.event_retention = event_retention
        self._adapter_tasks: list[asyncio.Task] = []
        self._subscribers: dict[str, set[asyncio.Queue[AgentEvent | None]]] = (
            defaultdict(set)
        )
        self._acks: dict[str, OrderedDict[str, AgentAck]] = defaultdict(OrderedDict)
        self._started = False

    async def start(self) -> None:
        if self._started:
            return
        self._started = True
        for adapter in self.adapters.values():
            try:
                await adapter.start()
            except Exception:
                # One unavailable provider must not take down the Gateway.
                continue
            self._adapter_tasks.append(
                asyncio.create_task(
                    self._pump_adapter(adapter),
                    name=f"agent-events-{adapter.provider_id}",
                )
            )

    async def stop(self) -> None:
        if not self._started:
            return
        self._started = False
        for queue_set in self._subscribers.values():
            for queue in queue_set:
                if queue.full():
                    queue.get_nowait()
                queue.put_nowait(None)
        self._subscribers.clear()
        for adapter in self.adapters.values():
            try:
                await adapter.stop()
            except Exception:
                pass
        for task in self._adapter_tasks:
            task.cancel()
        await asyncio.gather(*self._adapter_tasks, return_exceptions=True)
        self._adapter_tasks.clear()
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

    async def _pump_adapter(self, adapter: AgentAdapter) -> None:
        try:
            async for adapter_event in adapter.events():
                await self._handle_adapter_event(adapter.provider_id, adapter_event)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            for session in self.store.list_sessions(limit=10_000):
                if session.provider != adapter.provider_id:
                    continue
                session.status = SessionStatus.ERROR
                session.updated_at = utc_now()
                self.store.upsert_session(session)
                await self.publish(
                    AgentEvent(
                        type="error",
                        session_id=session.id,
                        data={
                            "code": "provider_crashed",
                            "message": str(exc),
                            "retryable": True,
                        },
                    )
                )

    async def _handle_adapter_event(
        self, provider: str, adapter_event: AdapterEvent
    ) -> None:
        if adapter_event.type == "error" and not adapter_event.provider_session_id:
            for failed_session in self.store.list_sessions(limit=10_000):
                if failed_session.provider != provider:
                    continue
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

"""Interactive Agent Gateway lifecycle, routing, replay, and capability gates."""

from __future__ import annotations

import asyncio
import hashlib
import os
from collections import OrderedDict, defaultdict
from pathlib import Path
from uuid import uuid4

from core.logging_config import get_logger
from core.project_groups import resolve_project_group
from core.resource_locator import (
    CODE_ROOT,
    get_bundled_resource_root,
    resolve_resource_root_from_config,
)
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

# Resource kinds a group can declare; "prompts" is the only kind the Gateway
# currently injects (via adapters that declare supports_resource_injection).
INJECTED_KINDS = ("prompts",)
# Mirrors prompt_kit.EXCLUDED_PROMPT_FILES: non-standards docs that happen to
# live in a prompt group directory.
EXCLUDED_PROMPT_FILES = {"README.md", "IMPLEMENTATION_PLAN.md"}


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
        config, warnings = self._config_service.get_config()
        if warnings:
            # A malformed config file degrades to whatever parsed (often
            # nothing); failing the request with a 500 here used to take
            # down session creation for an unrelated syntax error. The
            # registry lookup below already gives an actionable error.
            logger.warning("Config read failed: %s", warnings[0])
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

    def _resource_snapshot(
        self, workspace: str, config: dict | None = None
    ) -> ResourceSnapshot:
        """Names the session's group configures, as a declaration.

        When :meth:`_assemble_system_prompt` succeeds for this snapshot it
        gains a ``digest`` receipt and ``applied_kinds``; otherwise clients
        must show these resources as configured-but-inactive.
        """
        if config is None:
            config, _warnings = self._config_service.get_config()
        # Longest-prefix, the same rule the CLI applies (core/project_groups).
        # This used to compare for exact equality, so a workspace covered by a
        # parent rule -- the whole point of registering `E:/demo -> web` once
        # instead of every repository under it -- resolved to no group at all,
        # and the session started with an empty resource set and no warning.
        group_name = resolve_project_group(workspace, config.get("project_registry"))
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

    @staticmethod
    def _prompt_root(config: dict) -> Path:
        """Same resolution order as core.web.resource_paths, without the web import."""
        env_root = os.environ.get("CA_PROMPTS_ROOT")
        if env_root:
            return Path(env_root)
        resolved = resolve_resource_root_from_config(config, CODE_ROOT)
        base = (
            resolved if resolved is not None else get_bundled_resource_root(CODE_ROOT)
        )
        return Path(base) / "prompt"

    def _assemble_system_prompt(
        self, prompt_groups: list[str], config: dict
    ) -> tuple[str, list[dict]] | None:
        """Reads every markdown file behind the group's prompt names.

        Mirrors prompt_kit's per-group assembly (sorted ``*.md``, README and
        IMPLEMENTATION_PLAN excluded) but returns per-file segments so the
        receipt can name exactly which content entered the model, and omits
        the task / waiting-mode tail -- a system prompt is standing
        instruction, not a one-shot kickoff message.

        Returns ``(text, segments)``, or None when nothing could be read;
        None keeps the session honest (declared but not applied).
        """
        prompt_root = self._prompt_root(config)
        segments: list[dict] = []
        parts: list[str] = []
        for group in prompt_groups:
            group_dir = prompt_root / group
            md_files = sorted(group_dir.glob("*.md")) if group_dir.is_dir() else []
            contents: list[str] = []
            for path in md_files:
                if path.name in EXCLUDED_PROMPT_FILES:
                    continue
                try:
                    content = path.read_text(encoding="utf-8").strip()
                except OSError as exc:
                    logger.warning("Skipping unreadable prompt %s: %s", path, exc)
                    continue
                if not content:
                    continue
                contents.append(content)
                segments.append(
                    {
                        "kind": "prompts",
                        "name": f"{group}/{path.stem}",
                        "path": str(path),
                        "sha256": hashlib.sha256(content.encode()).hexdigest(),
                        "bytes": len(content.encode()),
                    }
                )
            if contents:
                parts.append(f"### {group.capitalize()} Standards ###")
                parts.append("\n\n".join(contents))
        if not segments:
            return None
        return "\n\n".join(parts).strip(), segments

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
        config, _warnings = self._config_service.get_config()
        resource_snapshot = self._resource_snapshot(cwd, config)
        injection: tuple[str, list[dict]] | None = None
        if capabilities.supports_resource_injection and resource_snapshot.prompts:
            injection = self._assemble_system_prompt(resource_snapshot.prompts, config)
            if injection is None:
                logger.warning(
                    "Prompt groups %s could not be resolved for %s; "
                    "the session starts without them",
                    resource_snapshot.prompts,
                    project_identity,
                )
        provider_session = await adapter.create_session(
            CreateSessionOptions(
                project_id=project_identity,
                cwd=cwd,
                model=model,
                permission_mode=permission_mode,
                system_prompt=injection[0] if injection else None,
            )
        )
        if injection:
            resource_snapshot.digest = hashlib.sha256(injection[0].encode()).hexdigest()
            resource_snapshot.applied_kinds = list(INJECTED_KINDS)
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
        # The receipt events reference the session row (foreign key), and
        # sequence numbers come from it -- persist before logging.
        self.store.upsert_session(session)
        if injection:
            await self.publish(
                AgentEvent(
                    type="resources.resolved",
                    session_id=session.id,
                    data={"segments": injection[1]},
                )
            )
            await self.publish(
                AgentEvent(
                    type="prompt.injected",
                    session_id=session.id,
                    data={
                        "sha256": resource_snapshot.digest,
                        "bytes": len(injection[0].encode()),
                        "chars": len(injection[0]),
                    },
                )
            )
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
        await self._assert_resources_applied(session)
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

    async def _assert_resources_applied(self, session: AgentSession) -> None:
        """Runtime invariant: model-visible means logged.

        A session whose group declares prompts must carry a
        ``prompt.injected`` receipt before its turns reach a provider that
        supports injection. Gated on ``supports_resource_injection`` so
        providers without an injection channel keep their honest gray state
        instead of failing every turn. Warns once per session per process;
        the warning is a persisted event, so replay shows it too.
        """
        if not session.capability_snapshot.supports_resource_injection:
            return
        snapshot = session.resource_snapshot
        if not snapshot.prompts:
            return
        if "prompts" in snapshot.applied_kinds and snapshot.digest:
            return
        if self.store.has_event_of_type(session.id, "prompt.injected"):
            return
        if session.id in self._resources_warned:
            return
        self._resources_warned.add(session.id)
        await self.publish(
            AgentEvent(
                type="error",
                session_id=session.id,
                data={
                    "code": "resources_not_applied",
                    "message": (
                        "This session's group declares prompts "
                        f"({', '.join(snapshot.prompts)}) but no "
                        "prompt.injected receipt exists -- the model runs "
                        "without them. Recreate the session to load them."
                    ),
                    "retryable": False,
                },
            )
        )

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
        if command.request_id != command.request_id.strip():
            raise AgentGatewayError("invalid_command", "Invalid request id")
        cached = self._acks[command.session_id].get(command.request_id)
        if cached:
            return cached
        # A client retry while the original command is still executing must
        # join the running command rather than run it a second time; the
        # completed-ack cache alone only deduplicates after the fact.
        key = (command.session_id, command.request_id)
        in_flight = self._commands_in_flight.get(key)
        if in_flight is not None:
            return await asyncio.shield(in_flight)
        future: asyncio.Future[AgentAck] = asyncio.get_running_loop().create_future()
        self._commands_in_flight[key] = future
        try:
            ack = await self._run_command(command)
        except BaseException as exc:
            if not future.done():
                future.set_exception(exc)
                # Mark retrieved so an unobserved failure doesn't warn at GC;
                # joined waiters still see the exception when they await.
                future.exception()
            raise
        finally:
            self._commands_in_flight.pop(key, None)
        if not future.done():
            future.set_result(ack)
        return ack

    async def _run_command(self, command: AgentCommand) -> AgentAck:
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
        while len(cache) > self.ack_cache_limit:
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
            for session in await asyncio.to_thread(
                self.store.list_sessions_by_status, SessionStatus.BUSY
            ):
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
                await asyncio.to_thread(self.store.upsert_session, session)
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

        Restarts the pump on all three ways it can stop: ``events()`` raising,
        ``events()`` returning cleanly, and ``start()`` having failed at boot.
        Any of them left unattended takes the provider out until the server is
        restarted.

        Sessions are moved to DISCONNECTED, not ERROR: ERROR is terminal in
        the UI, and these sessions are resumable once the provider is back.
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
        for session in await asyncio.to_thread(
            self.store.list_sessions_by_provider, adapter.provider_id
        ):
            if session.status in {SessionStatus.CLOSED, SessionStatus.DISCONNECTED}:
                continue
            session.status = SessionStatus.DISCONNECTED
            session.updated_at = utc_now()
            await asyncio.to_thread(self.store.upsert_session, session)
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
        sessions = await asyncio.to_thread(
            self.store.list_sessions_by_provider, adapter.provider_id
        )
        for session in sessions:
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
            failed_sessions = await asyncio.to_thread(
                self.store.list_sessions_by_provider, provider
            )
            for failed_session in failed_sessions:
                failed_session.status = SessionStatus.ERROR
                failed_session.updated_at = utc_now()
                await asyncio.to_thread(self.store.upsert_session, failed_session)
                await self.publish(
                    AgentEvent(
                        type="error",
                        session_id=failed_session.id,
                        data=adapter_event.data,
                    )
                )
            return
        session = await asyncio.to_thread(
            self.store.find_by_provider_session,
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
        await asyncio.to_thread(self.store.upsert_session, session)
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
        # Persist (and trim) off the event loop: this runs for every
        # adapter event including per-token message deltas, and each call
        # is a SQLite transaction. Fan-out to subscribers stays here -- it
        # only touches in-memory queues.
        persisted = await asyncio.to_thread(self._persist_event, event)
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

    def _persist_event(self, event: AgentEvent) -> AgentEvent:
        persisted = self.store.append_event(event)
        self.store.trim_events(event.session_id, keep=self.event_retention)
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

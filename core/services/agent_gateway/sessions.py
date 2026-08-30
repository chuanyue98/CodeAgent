"""Session lifecycle: create/import/resume/delete, turns, and approvals.

Extracted verbatim from the monolithic ``agent_gateway.py``. Every helper
goes through the gateway facade so behavior stays identical.
"""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING
from uuid import uuid4

from core.logging_config import get_logger
from core.services.agent_adapters.base import AgentAdapter
from core.services.agent_gateway import resources
from core.services.agent_gateway.errors import AgentGatewayError
from core.services.agent_protocol import (
    AgentEvent,
    AgentSession,
    ApprovalDecision,
    CreateSessionOptions,
    PermissionMode,
    ResumeOptions,
    SessionStatus,
    TurnInput,
    utc_now,
    wire,
)

if TYPE_CHECKING:
    from core.services.agent_gateway.gateway import AgentGateway

logger = get_logger(__name__)


def get_session(gateway: AgentGateway, session_id: str) -> AgentSession:
    session = gateway.store.get_session(session_id)
    if session is None:
        raise AgentGatewayError(
            "session_not_found", "Session not found", status_code=404
        )
    return session


def list_sessions(gateway: AgentGateway, limit: int = 100) -> list[AgentSession]:
    return gateway.store.list_sessions(limit=limit)


def adapter_for(gateway: AgentGateway, session: AgentSession) -> AgentAdapter:
    adapter = gateway.adapters.get(session.provider)
    if adapter is None:
        raise AgentGatewayError(
            "provider_unavailable",
            "Session provider is unavailable",
            status_code=503,
        )
    return adapter


async def create_session(
    gateway: AgentGateway,
    *,
    provider: str,
    project_id: str,
    model: str | None = None,
    permission_mode: PermissionMode = PermissionMode.WORKSPACE_WRITE,
    title: str | None = None,
) -> AgentSession:
    adapter = gateway.adapters.get(provider)
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
    cwd, project_identity = gateway._registered_workspace(project_id)
    config, _warnings = gateway._config_service.get_config()
    resource_snapshot = gateway._resource_snapshot(cwd, config)
    injection: tuple[str, list[dict]] | None = None
    if capabilities.supports_resource_injection and resource_snapshot.prompts:
        injection = resources.assemble_system_prompt(resource_snapshot.prompts, config)
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
        resource_snapshot.applied_kinds = list(resources.INJECTED_KINDS)
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
    gateway.store.upsert_session(session)
    if injection:
        await gateway.publish(
            AgentEvent(
                type="resources.resolved",
                session_id=session.id,
                data={"segments": injection[1]},
            )
        )
        await gateway.publish(
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
    await gateway.publish(
        AgentEvent(
            type="session.ready",
            session_id=session.id,
            data={"session": wire(session)},
        )
    )
    return gateway.get_session(session.id)


async def import_session(
    gateway: AgentGateway,
    *,
    provider: str,
    provider_session_id: str,
    project_id: str,
    model: str | None = None,
    permission_mode: PermissionMode = PermissionMode.WORKSPACE_WRITE,
    title: str | None = None,
) -> AgentSession:
    existing = gateway.store.find_by_provider_session(provider, provider_session_id)
    if existing is not None:
        return await gateway.resume_session(existing.id)

    adapter = gateway.adapters.get(provider)
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
    cwd, project_identity = gateway._registered_workspace(project_id)
    resource_snapshot = gateway._resource_snapshot(cwd)
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
    gateway.store.upsert_session(session)
    await gateway.publish(
        AgentEvent(
            type="session.ready",
            session_id=session.id,
            data={"session": wire(session)},
        )
    )
    return gateway.get_session(session.id)


async def resume_session(gateway: AgentGateway, session_id: str) -> AgentSession:
    session = gateway.get_session(session_id)
    adapter = gateway._adapter_for(session)
    gateway._registered_workspace(session.project_id)
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
    gateway.store.upsert_session(session)
    await gateway.publish(
        AgentEvent(
            type="session.ready",
            session_id=session.id,
            data={"session": wire(session)},
        )
    )
    return gateway.get_session(session.id)


def delete_session(gateway: AgentGateway, session_id: str) -> bool:
    gateway.get_session(session_id)
    return gateway.store.delete_session(session_id)


async def start_turn(gateway: AgentGateway, session_id: str, turn: TurnInput) -> str:
    session = gateway.get_session(session_id)
    adapter = gateway._adapter_for(session)
    await assert_resources_applied(gateway, session)
    session.status = SessionStatus.BUSY
    session.updated_at = utc_now()
    gateway.store.upsert_session(session)
    await gateway.publish(
        AgentEvent(
            type="message.user",
            session_id=session.id,
            data={"text": "\n".join(value.text for value in turn.input)},
        )
    )
    try:
        return await adapter.start_turn(session.provider_session_id, turn)
    except Exception:
        session = gateway.get_session(session_id)
        session.status = SessionStatus.READY
        session.updated_at = utc_now()
        gateway.store.upsert_session(session)
        raise


async def assert_resources_applied(
    gateway: AgentGateway, session: AgentSession
) -> None:
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
    if gateway.store.has_event_of_type(session.id, "prompt.injected"):
        return
    if session.id in gateway._resources_warned:
        return
    gateway._resources_warned.add(session.id)
    await gateway.publish(
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


async def steer_turn(
    gateway: AgentGateway, session_id: str, turn_id: str, turn: TurnInput
) -> None:
    session = gateway.get_session(session_id)
    if not session.capability_snapshot.supports_steer:
        raise AgentGatewayError(
            "unsupported_capability", "This provider does not support turn steering"
        )
    await gateway._adapter_for(session).steer_turn(
        session.provider_session_id, turn_id, turn
    )


async def cancel_turn(gateway: AgentGateway, session_id: str, turn_id: str) -> None:
    session = gateway.get_session(session_id)
    if not session.capability_snapshot.supports_cancel:
        raise AgentGatewayError(
            "unsupported_capability",
            "This provider does not support turn cancellation",
        )
    await gateway._adapter_for(session).cancel_turn(
        session.provider_session_id, turn_id
    )


async def respond_to_approval(
    gateway: AgentGateway,
    session_id: str,
    approval_id: str,
    decision: ApprovalDecision,
) -> None:
    session = gateway.get_session(session_id)
    if not session.capability_snapshot.supports_approvals:
        raise AgentGatewayError(
            "unsupported_capability", "This provider does not support approvals"
        )
    await gateway._adapter_for(session).respond_to_approval(approval_id, decision)
    await gateway.publish(
        AgentEvent(
            type="approval.resolved",
            session_id=session.id,
            data={"approvalId": approval_id, "decision": decision},
        )
    )

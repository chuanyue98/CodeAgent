"""Provider-neutral protocol shared by the Agent Gateway and web clients."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Any, Literal

from pydantic import Field

from core.web.case_convert import ProtocolModel, _to_camel, wire

__all__ = [
    "ProtocolModel",
    "wire",
    "_to_camel",
    "utc_now",
    "PermissionMode",
    "ApprovalDecision",
    "SessionStatus",
    "ProviderCapabilities",
    "ResourceSnapshot",
    "AgentSession",
    "AgentInput",
    "CreateSessionOptions",
    "ResumeOptions",
    "TurnInput",
    "ProviderSession",
    "AdapterEvent",
    "AgentEvent",
    "AgentAck",
    "AgentError",
    "CreateAgentSessionRequest",
    "ImportAgentSessionRequest",
    "AgentCommand",
]


def utc_now() -> datetime:
    return datetime.now(UTC)


class PermissionMode(str, Enum):
    WORKSPACE_WRITE = "workspace-write"
    READ_ONLY = "read-only"


class ApprovalDecision(str, Enum):
    ACCEPT = "accept"
    ACCEPT_FOR_SESSION = "acceptForSession"
    DECLINE = "decline"
    CANCEL = "cancel"


class SessionStatus(str, Enum):
    STARTING = "starting"
    READY = "ready"
    BUSY = "busy"
    DISCONNECTED = "disconnected"
    ERROR = "error"
    CLOSED = "closed"


class ProviderCapabilities(ProtocolModel):
    provider_id: str
    display_name: str
    available: bool = True
    unavailable_reason: str | None = None
    supports_resume: bool = False
    supports_steer: bool = False
    supports_cancel: bool = False
    supports_approvals: bool = False
    supports_file_diff: bool = False
    supports_tool_events: bool = False
    supports_attachments: bool = False
    supports_model_switch: bool = False


class ResourceSnapshot(ProtocolModel):
    """Resources configured for a Gateway session at creation time."""

    group: str | None = None
    skills: list[str] = Field(default_factory=list)
    prompts: list[str] = Field(default_factory=list)
    hooks: list[str] = Field(default_factory=list)
    plugins: list[str] = Field(default_factory=list)


class AgentSession(ProtocolModel):
    id: str
    provider: str
    provider_session_id: str
    project_id: str
    cwd: str
    title: str | None = None
    model: str | None = None
    permission_mode: PermissionMode = PermissionMode.WORKSPACE_WRITE
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    status: SessionStatus = SessionStatus.STARTING
    last_sequence: int = 0
    capability_snapshot: ProviderCapabilities
    resource_snapshot: ResourceSnapshot = Field(default_factory=ResourceSnapshot)


class AgentInput(ProtocolModel):
    type: Literal["text"] = "text"
    text: str = Field(min_length=1)


class CreateSessionOptions(ProtocolModel):
    project_id: str
    cwd: str
    model: str | None = None
    permission_mode: PermissionMode = PermissionMode.WORKSPACE_WRITE


class ResumeOptions(ProtocolModel):
    cwd: str
    model: str | None = None
    permission_mode: PermissionMode = PermissionMode.WORKSPACE_WRITE


class TurnInput(ProtocolModel):
    input: list[AgentInput] = Field(min_length=1)


class ProviderSession(ProtocolModel):
    id: str
    model: str | None = None


class AdapterEvent(ProtocolModel):
    """Normalized event produced by an adapter before local session mapping."""

    type: str
    provider_session_id: str
    provider_turn_id: str | None = None
    item_id: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)


class AgentEvent(ProtocolModel):
    """Persisted browser event. Unknown future event fields live in ``data``."""

    type: str
    sequence: int = 0
    timestamp: datetime = Field(default_factory=utc_now)
    session_id: str
    turn_id: str | None = None
    item_id: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)


class AgentAck(ProtocolModel):
    type: Literal["ack"] = "ack"
    request_id: str
    command: str
    result: dict[str, Any] = Field(default_factory=dict)


class AgentError(ProtocolModel):
    type: Literal["error"] = "error"
    request_id: str | None = None
    session_id: str | None = None
    turn_id: str | None = None
    code: str
    message: str
    retryable: bool = False


class CreateAgentSessionRequest(ProtocolModel):
    provider: str
    project_id: str = Field(min_length=1)
    model: str | None = None
    permission_mode: PermissionMode = PermissionMode.WORKSPACE_WRITE
    title: str | None = None


class ImportAgentSessionRequest(ProtocolModel):
    provider: str
    provider_session_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    permission_mode: PermissionMode = PermissionMode.WORKSPACE_WRITE
    title: str | None = None
    model: str | None = None


class AgentCommand(ProtocolModel):
    """WebSocket command envelope; fields are validated per command by Gateway."""

    type: Literal[
        "session.resume",
        "turn.start",
        "turn.steer",
        "turn.cancel",
        "approval.respond",
    ]
    request_id: str = Field(min_length=1)
    session_id: str
    turn_id: str | None = None
    approval_id: str | None = None
    decision: ApprovalDecision | None = None
    input: list[AgentInput] | None = None

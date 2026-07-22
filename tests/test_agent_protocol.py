from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from core.services.agent_protocol import (
    AdapterEvent,
    AgentAck,
    AgentCommand,
    AgentError,
    AgentEvent,
    AgentInput,
    AgentSession,
    ApprovalDecision,
    CreateAgentSessionRequest,
    CreateSessionOptions,
    ImportAgentSessionRequest,
    PermissionMode,
    ProviderCapabilities,
    ResourceSnapshot,
    ResumeOptions,
    SessionStatus,
    TurnInput,
    utc_now,
    wire,
)


def test_utc_now_returns_timezone_aware_utc_datetime():
    now = utc_now()
    assert now.tzinfo is not None
    assert now.tzinfo == UTC


def _capabilities() -> ProviderCapabilities:
    return ProviderCapabilities(provider_id="claude", display_name="Claude")


def test_agent_session_defaults():
    session = AgentSession(
        id="s1",
        provider="claude",
        provider_session_id="ps1",
        project_id="proj1",
        cwd="/tmp/proj1",
        capability_snapshot=_capabilities(),
    )

    assert session.permission_mode == PermissionMode.WORKSPACE_WRITE
    assert session.status == SessionStatus.STARTING
    assert session.last_sequence == 0
    assert session.resource_snapshot == ResourceSnapshot()
    assert isinstance(session.created_at, datetime)


def test_agent_session_requires_capability_snapshot():
    with pytest.raises(ValidationError):
        AgentSession(
            id="s1",
            provider="claude",
            provider_session_id="ps1",
            project_id="proj1",
            cwd="/tmp/proj1",
        )


def test_protocol_model_uses_camel_case_aliases_on_wire():
    session = AgentSession(
        id="s1",
        provider="claude",
        provider_session_id="ps1",
        project_id="proj1",
        cwd="/tmp/proj1",
        capability_snapshot=_capabilities(),
    )

    payload = wire(session)

    assert "providerSessionId" in payload
    assert "projectId" in payload
    assert "provider_session_id" not in payload
    assert payload["providerSessionId"] == "ps1"


def test_protocol_model_populate_by_name_accepts_snake_case_construction():
    # populate_by_name=True means the Python-side snake_case kwargs used
    # throughout the codebase remain valid even though the wire format is
    # camelCase.
    capabilities = ProviderCapabilities(
        provider_id="claude",
        display_name="Claude",
        supports_resume=True,
    )
    assert capabilities.provider_id == "claude"
    assert capabilities.supports_resume is True


def test_protocol_model_accepts_camel_case_construction_via_alias():
    capabilities = ProviderCapabilities.model_validate(
        {"providerId": "claude", "displayName": "Claude"}
    )
    assert capabilities.provider_id == "claude"
    assert capabilities.display_name == "Claude"


def test_agent_input_rejects_empty_text():
    with pytest.raises(ValidationError):
        AgentInput(text="")


def test_agent_input_defaults_type_to_text():
    agent_input = AgentInput(text="hello")
    assert agent_input.type == "text"


def test_turn_input_requires_at_least_one_input():
    with pytest.raises(ValidationError):
        TurnInput(input=[])

    turn = TurnInput(input=[AgentInput(text="hi")])
    assert len(turn.input) == 1


def test_create_session_options_defaults():
    options = CreateSessionOptions(project_id="proj1", cwd="/tmp")
    assert options.model is None
    assert options.permission_mode == PermissionMode.WORKSPACE_WRITE


def test_resume_options_defaults():
    options = ResumeOptions(cwd="/tmp")
    assert options.permission_mode == PermissionMode.WORKSPACE_WRITE


def test_create_agent_session_request_requires_non_empty_project_id():
    with pytest.raises(ValidationError):
        CreateAgentSessionRequest(provider="claude", project_id="")

    request = CreateAgentSessionRequest(provider="claude", project_id="proj1")
    assert request.permission_mode == PermissionMode.WORKSPACE_WRITE


def test_import_agent_session_request_requires_provider_session_id():
    with pytest.raises(ValidationError):
        ImportAgentSessionRequest(
            provider="claude", provider_session_id="", project_id="proj1"
        )


def test_agent_command_accepts_only_known_command_types():
    command = AgentCommand(
        type="turn.start",
        request_id="req-1",
        session_id="s1",
        input=[AgentInput(text="go")],
    )
    assert command.type == "turn.start"

    with pytest.raises(ValidationError):
        AgentCommand(type="bogus", request_id="req-1", session_id="s1")


def test_agent_command_requires_non_empty_request_id():
    with pytest.raises(ValidationError):
        AgentCommand(type="turn.cancel", request_id="", session_id="s1")


def test_approval_decision_enum_values_are_wire_ready():
    command = AgentCommand(
        type="approval.respond",
        request_id="req-1",
        session_id="s1",
        approval_id="appr-1",
        decision=ApprovalDecision.ACCEPT_FOR_SESSION,
    )
    payload = wire(command)
    assert payload["decision"] == "acceptForSession"


def test_adapter_event_defaults_data_to_empty_dict():
    event = AdapterEvent(type="message", provider_session_id="ps1")
    assert event.data == {}
    assert event.provider_turn_id is None


def test_agent_event_defaults_sequence_and_timestamp():
    event = AgentEvent(type="message", session_id="s1")
    assert event.sequence == 0
    assert isinstance(event.timestamp, datetime)


def test_agent_ack_defaults_result_to_empty_dict():
    ack = AgentAck(request_id="req-1", command="turn.start")
    assert ack.result == {}
    assert ack.type == "ack"


def test_agent_error_defaults():
    error = AgentError(code="E_BAD", message="oops")
    assert error.retryable is False
    assert error.request_id is None
    assert wire(error)["retryable"] is False


def test_wire_uses_json_mode_encoding_for_datetimes():
    event = AgentEvent(type="message", session_id="s1")
    payload = wire(event)
    # In JSON mode, datetimes are serialized as ISO strings, not python objects.
    assert isinstance(payload["timestamp"], str)


def test_resource_snapshot_defaults_to_empty_lists():
    snapshot = ResourceSnapshot()
    assert snapshot.group is None
    assert snapshot.skills == []
    assert snapshot.prompts == []
    assert snapshot.hooks == []
    assert snapshot.plugins == []

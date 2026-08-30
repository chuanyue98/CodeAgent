"""Interactive Agent Gateway: lifecycle, routing, replay, and capability gates.

Package layout (split from the former monolithic ``agent_gateway.py``):

- ``gateway`` — the :class:`AgentGateway` facade
- ``errors`` — :class:`AgentGatewayError`
- ``resources`` — workspace registry + prompt/resource resolution
- ``sessions`` — session CRUD, turns, approvals
- ``commands`` — command execution, dedup, ack cache
- ``events`` — persistence, fan-out, replay
- ``supervisor`` — adapter restart pump, watchdog, backoff
"""

from core.services.agent_gateway.errors import AgentGatewayError
from core.services.agent_gateway.gateway import (
    EXCLUDED_PROMPT_FILES,
    INJECTED_KINDS,
    AgentGateway,
)

__all__ = [
    "AgentGateway",
    "AgentGatewayError",
    "INJECTED_KINDS",
    "EXCLUDED_PROMPT_FILES",
]

"""Gateway error type shared by every agent_gateway submodule."""

from __future__ import annotations


class AgentGatewayError(Exception):
    def __init__(self, code: str, message: str, *, status_code: int = 400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code

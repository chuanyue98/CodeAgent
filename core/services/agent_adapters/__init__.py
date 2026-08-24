"""Provider adapters for the interactive Agent Gateway."""

from core.services.agent_adapters.base import AgentAdapter
from core.services.agent_adapters.claude import ClaudeAdapter
from core.services.agent_adapters.codebuddy import CodeBuddyAdapter
from core.services.agent_adapters.codex import CodexAdapter
from core.services.agent_adapters.fake import FakeAgentAdapter
from core.services.agent_adapters.opencode import OpenCodeAdapter

__all__ = [
    "AgentAdapter",
    "ClaudeAdapter",
    "CodeBuddyAdapter",
    "CodexAdapter",
    "FakeAgentAdapter",
    "OpenCodeAdapter",
]

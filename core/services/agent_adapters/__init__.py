"""Provider adapters for the interactive Agent Gateway."""

from core.services.agent_adapters.base import AgentAdapter
from core.services.agent_adapters.codex import CodexAdapter
from core.services.agent_adapters.fake import FakeAgentAdapter

__all__ = ["AgentAdapter", "CodexAdapter", "FakeAgentAdapter"]

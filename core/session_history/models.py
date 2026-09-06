"""Unified session history models.

These dataclasses form the intermediate representation that sits between
engine-native parsers (readers) and engine-native writers.

    Claude JSONL  ──→  UnifiedSession  ──→  Codex JSONL
    Codex JSONL   ──→  UnifiedSession  ──→  Claude JSONL
    OpenCode DB   ──→  UnifiedSession  ──→  ...

Only core conversational content is preserved: user messages, assistant text
replies, and tool-call summaries.  Encrypted reasoning, file snapshots, and
other engine-specific metadata are intentionally dropped — the goal is
context continuity, not perfect fidelity.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class EngineType(str, Enum):
    """Supported engine types.

    claude/codex/opencode/codebuddy are launchable CLI engines (they
    are part of ``core.constants.ENGINES``, which drives launching, conversion
    targets and engine validation). codebuddy is driven through the ACP
    (Agent Client Protocol) adapter in
    ``core/services/agent_adapters/codebuddy.py``.

    freebuff 也在 ENGINES 里（交互启动 + ``freebuff --continue`` 恢复 + 历史
    浏览/分析可用），但免费版 CLI 没有 headless/ACP 通道——它不在
    ``core.constants.HEADLESS_ENGINES`` 中，因此转换写入它的 writer 是预留
    占位，转换“到” freebuff 会得到明确的 NotImplementedError。
    """

    CLAUDE = "claude"
    CODEX = "codex"
    OPENCODE = "opencode"
    CODEBUDDY = "codebuddy"
    FREEBUFF = "freebuff"


@dataclass
class ToolCallSummary:
    """A simplified representation of a tool call.

    Attributes:
        name: The tool/function name (e.g. 'read_file', 'shell_command').
        args_preview: A short string preview of the arguments.
        result_preview: A short string preview of the result, if available.
    """

    name: str = ""
    args_preview: str = ""
    result_preview: str = ""


@dataclass
class UnifiedMessage:
    """A single message in a unified session.

    Attributes:
        role: Either 'user' or 'assistant'.
        content: The text content of the message.
        timestamp: ISO 8601 formatted timestamp string.
        tool_calls: Optional list of tool call summaries made in this message.
        model: The model that generated this message (assistant only).
    """

    role: str  # "user" | "assistant"
    content: str
    timestamp: str = ""  # ISO 8601
    tool_calls: list[ToolCallSummary] = field(default_factory=list)
    model: str = ""

    def to_dict(self) -> dict:
        """Serializes to a plain dict for JSON API responses."""
        return {
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp,
            "tool_calls": [
                {
                    "name": tc.name,
                    "args_preview": tc.args_preview,
                    "result_preview": tc.result_preview,
                }
                for tc in self.tool_calls
            ],
            "model": self.model,
        }


@dataclass
class UnifiedSession:
    """The intermediate representation of an AI engine session.

    This is what every parser produces and every writer consumes.

    Attributes:
        session_id: The original engine's session ID.
        engine: Which engine this session originated from.
        project_path: The working directory the session was in.
        started_at: ISO 8601 timestamp of the first message.
        ended_at: ISO 8601 timestamp of the last message, or empty.
        messages: Ordered list of unified messages.
        title: Optional human-readable title (if the engine provides one).
        model: The primary model used in the session.
        source_file: The original file/database path this was parsed from.
        parent_session_id: The session that spawned this one, when it is a
            subagent run; empty for a session a user started.
        agent: The subagent's name, when the engine records one.
        subagent_titles: ``agent id -> the one-line description this session
            gave that subagent at launch``. Read by the finder to title the
            subagent runs, whose own transcripts open with the whole prompt.
    """

    session_id: str = ""
    engine: EngineType = EngineType.CLAUDE
    project_path: str = ""
    started_at: str = ""  # ISO 8601
    ended_at: str = ""  # ISO 8601
    messages: list[UnifiedMessage] = field(default_factory=list)
    title: str = ""
    model: str = ""
    source_file: str = ""
    parent_session_id: str = ""
    agent: str = ""
    subagent_titles: dict[str, str] = field(default_factory=dict)

    @property
    def message_count(self) -> int:
        """Returns the number of messages in this session."""
        return len(self.messages)

    @property
    def first_user_message(self) -> str:
        """Returns the content of the first user message, or empty string."""
        for msg in self.messages:
            if msg.role == "user" and msg.content.strip():
                return msg.content[:200]
        return ""

    def to_summary_dict(self) -> dict:
        """Returns a lightweight summary dict for list views.

        Does NOT include the full message list — use `to_full_dict()` for that.
        """
        return {
            "session_id": self.session_id,
            "engine": self.engine.value,
            "project_path": self.project_path,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "message_count": self.message_count,
            "title": self.title or self.first_user_message,
            "model": self.model,
            "source_file": self.source_file,
            "parent_session_id": self.parent_session_id,
            "agent": self.agent,
        }

    def to_full_dict(self) -> dict:
        """Returns the complete session including all messages."""
        return {
            **self.to_summary_dict(),
            "messages": [msg.to_dict() for msg in self.messages],
        }

    def generate_title(self) -> str:
        """Generates a title from the first user message if no title is set.

        Returns:
            str: The title (first 80 chars of the first user message).
        """
        if self.title:
            return self.title
        first = self.first_user_message
        if first:
            return first[:80] + ("..." if len(first) > 80 else "")
        return f"{self.engine.value} session"

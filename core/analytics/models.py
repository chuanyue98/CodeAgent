"""Data models for tracking and aggregating LLM usage and costs."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class RawUsageEntry:
    """Represents a single granular record of LLM usage.

    Attributes:
        timestamp: ISO 8601 formatted string of when the usage occurred.
        session_id: Unique identifier for the user session.
        model: Name of the LLM model used (e.g., 'gpt-4o').
        input_tokens: Number of prompt/input tokens.
        output_tokens: Number of completion/output tokens.
        cache_creation_tokens: Tokens used to create a new cache entry.
        cache_read_tokens: Tokens read from an existing cache.
        cost: Pre-computed cost (primarily for OpenCode); 0.0 means derive from pricing.
        project_path: Local filesystem path of the project.
        target: The engine target (e.g., 'claude', 'codex', 'opencode').
    """

    timestamp: str  # ISO 8601
    session_id: str
    model: str
    input_tokens: int
    output_tokens: int
    cache_creation_tokens: int = 0
    cache_read_tokens: int = 0
    cost: float = 0.0  # pre-computed cost (OpenCode); 0 = derive from pricing
    project_path: str = ""
    target: str = ""  # claude | codex | opencode | codebuddy


@dataclass
class ModelBreakdown:
    """Aggregated usage and cost metrics for a specific model.

    Attributes:
        model_name: Name of the LLM model.
        input_tokens: Total input tokens for this model.
        output_tokens: Total output tokens for this model.
        cache_creation_tokens: Total tokens used for cache creation.
        cache_read_tokens: Total tokens read from cache.
        cost: Total calculated cost in USD.
    """

    model_name: str
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_tokens: int = 0
    cache_read_tokens: int = 0
    cost: float = 0.0


@dataclass
class DailyUsage:
    """Usage metrics aggregated by day and engine target.

    Attributes:
        date: Date string in YYYY-MM-DD format.
        target: The engine target (e.g., 'claude', 'codex').
        input_tokens: Total input tokens for the day/target.
        output_tokens: Total output tokens for the day/target.
        cache_creation_tokens: Total cache creation tokens.
        cache_read_tokens: Total cache read tokens.
        cost: Total cost for the day/target in USD.
        models_used: List of unique model names used.
        model_breakdowns: Detailed breakdown per model.
    """

    date: str  # YYYY-MM-DD
    target: str
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_tokens: int = 0
    cache_read_tokens: int = 0
    cost: float = 0.0
    models_used: list[str] = field(default_factory=list)
    model_breakdowns: list[ModelBreakdown] = field(default_factory=list)


@dataclass
class MonthlyUsage:
    """Usage metrics aggregated by month and engine target.

    Attributes:
        month: Month string in YYYY-MM format.
        target: The engine target.
        input_tokens: Total input tokens for the month/target.
        output_tokens: Total output tokens for the month/target.
        cache_creation_tokens: Total cache creation tokens.
        cache_read_tokens: Total cache read tokens.
        cost: Total cost for the month/target in USD.
        models_used: List of unique model names used.
        model_breakdowns: Detailed breakdown per model.
    """

    month: str  # YYYY-MM
    target: str
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_tokens: int = 0
    cache_read_tokens: int = 0
    cost: float = 0.0
    models_used: list[str] = field(default_factory=list)
    model_breakdowns: list[ModelBreakdown] = field(default_factory=list)


@dataclass
class SessionUsage:
    """Usage metrics aggregated by session and engine target.

    Attributes:
        session_id: Unique identifier for the session.
        target: The engine target.
        project_path: Path of the project being worked on.
        input_tokens: Total input tokens for the session/target.
        output_tokens: Total output tokens for the session/target.
        cache_creation_tokens: Total cache creation tokens.
        cache_read_tokens: Total cache read tokens.
        cost: Total cost for the session/target in USD.
        last_activity: ISO 8601 timestamp of the last activity in the session.
        models_used: List of unique model names used.
        model_breakdowns: Detailed breakdown per model.
    """

    session_id: str
    target: str
    project_path: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_tokens: int = 0
    cache_read_tokens: int = 0
    cost: float = 0.0
    last_activity: str = ""
    models_used: list[str] = field(default_factory=list)
    model_breakdowns: list[ModelBreakdown] = field(default_factory=list)

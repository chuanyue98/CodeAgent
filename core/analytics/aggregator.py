from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List

from core.analytics.models import (
    DailyUsage,
    ModelBreakdown,
    MonthlyUsage,
    RawUsageEntry,
    SessionUsage,
)
from core.analytics.pricing import calculate_cost


def _date(ts: str) -> str:
    """Extract YYYY-MM-DD from an ISO 8601 timestamp.

    Args:
        ts: ISO 8601 timestamp string.

    Returns:
        The date part (YYYY-MM-DD) or "unknown" if ts is empty.
    """
    return ts[:10] if ts else "unknown"


def _month(ts: str) -> str:
    """Extract YYYY-MM from an ISO 8601 timestamp.

    Args:
        ts: ISO 8601 timestamp string.

    Returns:
        The month part (YYYY-MM) or "unknown" if ts is empty.
    """
    return ts[:7] if ts else "unknown"


def _entry_cost(entry: RawUsageEntry) -> float:
    """Calculates or retrieves the cost for a single usage entry.

    Args:
        entry: The RawUsageEntry to calculate cost for.

    Returns:
        The calculated or pre-computed cost.
    """
    if entry.cost > 0:
        return entry.cost
    return calculate_cost(
        entry.model,
        entry.input_tokens,
        entry.output_tokens,
        entry.cache_creation_tokens,
        entry.cache_read_tokens,
    )


def _merge_breakdown(
    breakdowns: Dict[str, ModelBreakdown], entry: RawUsageEntry, cost: float
) -> None:
    """Merges a usage entry into a model-specific breakdown dictionary.

    Args:
        breakdowns: Dictionary of model names to ModelBreakdown objects.
        entry: The usage entry to merge.
        cost: The cost associated with this entry.
    """
    bd = breakdowns.setdefault(
        entry.model,
        ModelBreakdown(model_name=entry.model),
    )
    bd.input_tokens += entry.input_tokens
    bd.output_tokens += entry.output_tokens
    bd.cache_creation_tokens += entry.cache_creation_tokens
    bd.cache_read_tokens += entry.cache_read_tokens
    bd.cost += cost


def aggregate(entries: List[RawUsageEntry]) -> Dict[str, Any]:
    """Aggregates raw usage entries into daily, monthly, and session-based summaries.

    Args:
        entries: A list of RawUsageEntry objects to aggregate.

    Returns:
        A dictionary containing summarized data for:
            - summary: Overall totals and counts.
            - daily: List of DailyUsage dictionaries.
            - monthly: List of MonthlyUsage dictionaries.
            - sessions: List of SessionUsage dictionaries.
    """
    # Keyed by (date, target)
    daily: Dict[tuple, DailyUsage] = {}
    daily_breakdowns: Dict[tuple, Dict[str, ModelBreakdown]] = defaultdict(dict)

    # Keyed by (month, target)
    monthly: Dict[tuple, MonthlyUsage] = {}
    monthly_breakdowns: Dict[tuple, Dict[str, ModelBreakdown]] = defaultdict(dict)

    # Keyed by (session_id, target)
    sessions: Dict[tuple, SessionUsage] = {}
    session_breakdowns: Dict[tuple, Dict[str, ModelBreakdown]] = defaultdict(dict)

    for e in entries:
        cost = _entry_cost(e)

        d_key = (_date(e.timestamp), e.target)
        if d_key not in daily:
            daily[d_key] = DailyUsage(date=d_key[0], target=e.target)
        du = daily[d_key]
        du.input_tokens += e.input_tokens
        du.output_tokens += e.output_tokens
        du.cache_creation_tokens += e.cache_creation_tokens
        du.cache_read_tokens += e.cache_read_tokens
        du.cost += cost
        _merge_breakdown(daily_breakdowns[d_key], e, cost)

        m_key = (_month(e.timestamp), e.target)
        if m_key not in monthly:
            monthly[m_key] = MonthlyUsage(month=m_key[0], target=e.target)
        mu = monthly[m_key]
        mu.input_tokens += e.input_tokens
        mu.output_tokens += e.output_tokens
        mu.cache_creation_tokens += e.cache_creation_tokens
        mu.cache_read_tokens += e.cache_read_tokens
        mu.cost += cost
        _merge_breakdown(monthly_breakdowns[m_key], e, cost)

        s_key = (e.session_id, e.target)
        if s_key not in sessions:
            sessions[s_key] = SessionUsage(
                session_id=e.session_id,
                target=e.target,
                project_path=e.project_path,
            )
        su = sessions[s_key]
        su.input_tokens += e.input_tokens
        su.output_tokens += e.output_tokens
        su.cache_creation_tokens += e.cache_creation_tokens
        su.cache_read_tokens += e.cache_read_tokens
        su.cost += cost
        if e.timestamp > su.last_activity:
            su.last_activity = e.timestamp
        _merge_breakdown(session_breakdowns[s_key], e, cost)

    # Attach model breakdowns and unique models
    for key, du in daily.items():
        bds = list(daily_breakdowns[key].values())
        du.model_breakdowns = bds
        du.models_used = sorted({bd.model_name for bd in bds})

    for key, mu in monthly.items():
        bds = list(monthly_breakdowns[key].values())
        mu.model_breakdowns = bds
        mu.models_used = sorted({bd.model_name for bd in bds})

    for key, su in sessions.items():
        bds = list(session_breakdowns[key].values())
        su.model_breakdowns = bds
        su.models_used = sorted({bd.model_name for bd in bds})

    daily_list = sorted(daily.values(), key=lambda x: x.date)
    monthly_list = sorted(monthly.values(), key=lambda x: x.month)
    session_list = sorted(
        sessions.values(), key=lambda x: x.last_activity, reverse=True
    )

    # Summary totals across all targets
    total_input = sum(e.input_tokens for e in entries)
    total_output = sum(e.output_tokens for e in entries)
    total_cache_create = sum(e.cache_creation_tokens for e in entries)
    total_cache_read = sum(e.cache_read_tokens for e in entries)

    targets_seen = sorted({e.target for e in entries})
    models_seen = sorted({e.model for e in entries})

    return {
        "summary": {
            "total_entries": len(entries),
            "total_input_tokens": total_input,
            "total_output_tokens": total_output,
            "total_cache_creation_tokens": total_cache_create,
            "total_cache_read_tokens": total_cache_read,
            "targets": targets_seen,
            "models": models_seen,
            "session_count": len(sessions),
        },
        "daily": [_daily_to_dict(du) for du in daily_list],
        "monthly": [_monthly_to_dict(mu) for mu in monthly_list],
        "sessions": [_session_to_dict(su) for su in session_list],
    }


def _daily_to_dict(du: DailyUsage) -> dict:
    """Converts a DailyUsage object to a dictionary.

    Args:
        du: The DailyUsage object to convert.

    Returns:
        A dictionary representation of the DailyUsage object.
    """
    return {
        "date": du.date,
        "target": du.target,
        "inputTokens": du.input_tokens,
        "outputTokens": du.output_tokens,
        "cacheCreationTokens": du.cache_creation_tokens,
        "cacheReadTokens": du.cache_read_tokens,
        "cost": du.cost,
        "modelsUsed": du.models_used,
        "modelBreakdowns": [_bd_to_dict(b) for b in du.model_breakdowns],
    }


def _monthly_to_dict(mu: MonthlyUsage) -> dict:
    """Converts a MonthlyUsage object to a dictionary.

    Args:
        mu: The MonthlyUsage object to convert.

    Returns:
        A dictionary representation of the MonthlyUsage object.
    """
    return {
        "month": mu.month,
        "target": mu.target,
        "inputTokens": mu.input_tokens,
        "outputTokens": mu.output_tokens,
        "cacheCreationTokens": mu.cache_creation_tokens,
        "cacheReadTokens": mu.cache_read_tokens,
        "cost": mu.cost,
        "modelsUsed": mu.models_used,
        "modelBreakdowns": [_bd_to_dict(b) for b in mu.model_breakdowns],
    }


def _session_to_dict(su: SessionUsage) -> dict:
    """Converts a SessionUsage object to a dictionary.

    Args:
        su: The SessionUsage object to convert.

    Returns:
        A dictionary representation of the SessionUsage object.
    """
    return {
        "sessionId": su.session_id,
        "target": su.target,
        "projectPath": su.project_path,
        "inputTokens": su.input_tokens,
        "outputTokens": su.output_tokens,
        "cacheCreationTokens": su.cache_creation_tokens,
        "cacheReadTokens": su.cache_read_tokens,
        "cost": su.cost,
        "lastActivity": su.last_activity,
        "modelsUsed": su.models_used,
        "modelBreakdowns": [_bd_to_dict(b) for b in su.model_breakdowns],
    }


def _bd_to_dict(bd: ModelBreakdown) -> dict:
    """Converts a ModelBreakdown object to a dictionary.

    Args:
        bd: The ModelBreakdown object to convert.

    Returns:
        A dictionary representation of the ModelBreakdown object.
    """
    return {
        "modelName": bd.model_name,
        "inputTokens": bd.input_tokens,
        "outputTokens": bd.output_tokens,
        "cacheCreationTokens": bd.cache_creation_tokens,
        "cacheReadTokens": bd.cache_read_tokens,
        "cost": bd.cost,
    }

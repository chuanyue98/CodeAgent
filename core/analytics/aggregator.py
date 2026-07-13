from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List

from core.analytics.models import (
    DailyUsage,
    ModelBreakdown,
    MonthlyUsage,
    RawUsageEntry,
    SessionUsage,
)
from core.analytics.pricing import calculate_cost


def _parse_ts(ts: str) -> datetime:
    """Parse an ISO 8601 timestamp string to a UTC-aware datetime for comparison.

    Handles ``Z`` suffix and mixed timezone offsets (e.g. ``+08:00``)
    that heterogeneous engine parsers may produce.
    Returns ``datetime.min`` (UTC) on parse failure or empty input.
    """
    try:
        normalized = ts.replace("Z", "+00:00") if ts else ""
        dt = datetime.fromisoformat(normalized) if normalized else datetime.min
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        return datetime.min.replace(tzinfo=timezone.utc)


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
    daily: Dict[tuple, DailyUsage] = {}
    daily_bds: Dict[tuple, Dict[str, ModelBreakdown]] = defaultdict(dict)

    monthly: Dict[tuple, MonthlyUsage] = {}
    monthly_bds: Dict[tuple, Dict[str, ModelBreakdown]] = defaultdict(dict)

    sessions: Dict[tuple, SessionUsage] = {}
    session_bds: Dict[tuple, Dict[str, ModelBreakdown]] = defaultdict(dict)

    def update_usage(usage_obj, entry: RawUsageEntry, cost: float):
        usage_obj.input_tokens += entry.input_tokens
        usage_obj.output_tokens += entry.output_tokens
        usage_obj.cache_creation_tokens += entry.cache_creation_tokens
        usage_obj.cache_read_tokens += entry.cache_read_tokens
        usage_obj.cost += cost

    for e in entries:
        cost = _entry_cost(e)

        # Daily
        d_key = (_date(e.timestamp), e.target)
        if d_key not in daily:
            daily[d_key] = DailyUsage(date=d_key[0], target=e.target)
        update_usage(daily[d_key], e, cost)
        _merge_breakdown(daily_bds[d_key], e, cost)

        # Monthly
        m_key = (_month(e.timestamp), e.target)
        if m_key not in monthly:
            monthly[m_key] = MonthlyUsage(month=m_key[0], target=e.target)
        update_usage(monthly[m_key], e, cost)
        _merge_breakdown(monthly_bds[m_key], e, cost)

        # Session
        s_key = (e.session_id, e.target)
        if s_key not in sessions:
            sessions[s_key] = SessionUsage(
                session_id=e.session_id,
                target=e.target,
                project_path=e.project_path,
            )
        su = sessions[s_key]
        update_usage(su, e, cost)
        if _parse_ts(e.timestamp) > _parse_ts(su.last_activity):
            su.last_activity = e.timestamp
        _merge_breakdown(session_bds[s_key], e, cost)

    # Attach model breakdowns and unique models
    def finalize(usage_map, breakdown_map):
        for key, obj in usage_map.items():
            bds = list(breakdown_map[key].values())
            obj.model_breakdowns = bds
            obj.models_used = sorted({bd.model_name for bd in bds})

    finalize(daily, daily_bds)
    finalize(monthly, monthly_bds)
    finalize(sessions, session_bds)

    daily_list = sorted(daily.values(), key=lambda x: x.date)
    monthly_list = sorted(monthly.values(), key=lambda x: x.month)
    session_list = sorted(
        sessions.values(), key=lambda x: x.last_activity, reverse=True
    )

    return {
        "summary": {
            "total_entries": len(entries),
            "total_input_tokens": sum(e.input_tokens for e in entries),
            "total_output_tokens": sum(e.output_tokens for e in entries),
            "total_cache_creation_tokens": sum(
                e.cache_creation_tokens for e in entries
            ),
            "total_cache_read_tokens": sum(e.cache_read_tokens for e in entries),
            "targets": sorted({e.target for e in entries}),
            "models": sorted({e.model for e in entries}),
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

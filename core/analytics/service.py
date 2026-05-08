from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List

from core.analytics.aggregator import aggregate, _entry_cost
from core.analytics.collectors.claude_collector import scan_claude_usage
from core.analytics.collectors.codex_collector import scan_codex_usage
from core.analytics.collectors.gemini_collector import scan_gemini_usage
from core.analytics.collectors.opencode_collector import scan_opencode_usage
from core.analytics.disk_cache import invalidate_cache, load_cache, save_cache
from core.analytics.history import (
    append_history,
    get_last_timestamps,
    load_history,
)
from core.analytics.models import RawUsageEntry
from core.analytics.pricing import get_rates


def _collect_all() -> List[RawUsageEntry]:
    """Collects usage entries incrementally and merges them with history.

    Returns:
        List[RawUsageEntry]: The full list of raw usage entries.
    """
    # 1. Load existing history
    history = load_history()
    last_ts = get_last_timestamps()

    # 2. Collect only new entries
    new_entries: List[RawUsageEntry] = []
    new_entries.extend(scan_claude_usage(since_timestamp=last_ts.get("claude", "")))
    new_entries.extend(scan_gemini_usage(since_timestamp=last_ts.get("gemini", "")))
    new_entries.extend(scan_codex_usage(since_timestamp=last_ts.get("codex", "")))
    new_entries.extend(scan_opencode_usage(since_timestamp=last_ts.get("opencode", "")))

    # 3. Save new entries to history file
    if new_entries:
        append_history(new_entries)
        history.extend(new_entries)

    return history


def _build_engine_summary(entries: List[RawUsageEntry]) -> List[Dict[str, Any]]:
    """Builds a summarized report of usage statistics grouped by engine.

    Args:
        entries: A list of raw usage entries to summarize.

    Returns:
        List[Dict[str, Any]]: A list of dictionaries, each containing aggregated
            statistics for a specific engine (target), including token counts,
            estimated cost, session count, and unique models used.
    """
    stats: Dict[str, Dict[str, Any]] = defaultdict(
        lambda: {
            "inputTokens": 0,
            "outputTokens": 0,
            "cacheCreationTokens": 0,
            "cacheReadTokens": 0,
            "cost": 0.0,
            "sessionIds": set(),
            "models": set(),
        }
    )
    for e in entries:
        s = stats[e.target]
        s["inputTokens"] += e.input_tokens
        s["outputTokens"] += e.output_tokens
        s["cacheCreationTokens"] += e.cache_creation_tokens
        s["cacheReadTokens"] += e.cache_read_tokens
        s["cost"] += _entry_cost(e)
        s["sessionIds"].add(e.session_id)
        s["models"].add(e.model)

    result = []
    for target in sorted(stats):
        s = stats[target]
        result.append(
            {
                "target": target,
                "inputTokens": s["inputTokens"],
                "outputTokens": s["outputTokens"],
                "cacheCreationTokens": s["cacheCreationTokens"],
                "cacheReadTokens": s["cacheReadTokens"],
                "cost": round(s["cost"], 6),
                "sessionCount": len(s["sessionIds"]),
                "models": sorted(s["models"]),
            }
        )
    return result


def _build_model_summary(entries: List[RawUsageEntry]) -> List[Dict[str, Any]]:
    stats: Dict[str, Dict[str, Any]] = defaultdict(
        lambda: {
            "inputTokens": 0,
            "outputTokens": 0,
            "cacheCreationTokens": 0,
            "cacheReadTokens": 0,
            "inputCost": 0.0,
            "outputCost": 0.0,
            "cacheWriteCost": 0.0,
            "cacheReadCost": 0.0,
            "cost": 0.0,
            "sessionIds": set(),
            "targets": set(),
        }
    )
    for e in entries:
        s = stats[e.model]
        in_r, out_r, cw_r, cr_r = get_rates(e.model)
        s["inputTokens"] += e.input_tokens
        s["outputTokens"] += e.output_tokens
        s["cacheCreationTokens"] += e.cache_creation_tokens
        s["cacheReadTokens"] += e.cache_read_tokens
        s["inputCost"] += e.input_tokens * in_r / 1_000_000
        s["outputCost"] += e.output_tokens * out_r / 1_000_000
        s["cacheWriteCost"] += e.cache_creation_tokens * cw_r / 1_000_000
        s["cacheReadCost"] += e.cache_read_tokens * cr_r / 1_000_000
        s["cost"] += _entry_cost(e)
        s["sessionIds"].add(e.session_id)
        s["targets"].add(e.target)

    result = []
    for model, s in sorted(stats.items(), key=lambda x: -x[1]["cost"]):
        result.append(
            {
                "model": model,
                "inputTokens": s["inputTokens"],
                "outputTokens": s["outputTokens"],
                "cacheCreationTokens": s["cacheCreationTokens"],
                "cacheReadTokens": s["cacheReadTokens"],
                "inputCost": round(s["inputCost"], 6),
                "outputCost": round(s["outputCost"], 6),
                "cacheWriteCost": round(s["cacheWriteCost"], 6),
                "cacheReadCost": round(s["cacheReadCost"], 6),
                "cost": round(s["cost"], 6),
                "sessionCount": len(s["sessionIds"]),
                "targets": sorted(s["targets"]),
            }
        )
    return result


def get_analytics_data(force_refresh: bool = False) -> Dict[str, Any]:
    """Retrieves analytics data, using cache if available and not forced to refresh.

    Args:
        force_refresh: If True, bypasses the cache and re-collects data from
            all sources. Defaults to False.

    Returns:
        Dict[str, Any]: The aggregated analytics data including project-level
            stats and engine-level summaries.
    """
    if not force_refresh:
        cached = load_cache()
        if cached is not None:
            return cached

    entries = _collect_all()
    data = aggregate(entries)
    data["engines"] = _build_engine_summary(entries)
    data["models"] = _build_model_summary(entries)
    save_cache(data)
    return data


def refresh_analytics_data() -> Dict[str, Any]:
    """Invalidates the cache and forces a fresh collection of analytics data.

    Returns:
        Dict[str, Any]: The freshly collected and aggregated analytics data.
    """
    invalidate_cache()
    return get_analytics_data(force_refresh=True)

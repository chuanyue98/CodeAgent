from __future__ import annotations

import threading
from collections import defaultdict
from typing import Any

from core.analytics.aggregator import aggregate
from core.analytics.collectors.antigravity_collector import scan_antigravity_usage
from core.analytics.collectors.claude_collector import scan_claude_usage
from core.analytics.collectors.codebuddy_collector import scan_codebuddy_usage
from core.analytics.collectors.codex_collector import scan_codex_usage
from core.analytics.collectors.opencode_collector import scan_opencode_usage
from core.analytics.disk_cache import invalidate_cache, load_cache, save_cache
from core.analytics.history import (
    append_history,
    backfill_pending,
    get_last_timestamps,
    load_history,
    mark_backfill_done,
    merge_history,
    save_history,
)
from core.analytics.models import RawUsageEntry
from core.logging_config import get_logger

logger = get_logger(__name__)

# Bumped when a collector starts reading records earlier versions never saw.
# The incremental scan below is watermarked per engine, so newly-visible old
# records would otherwise stay invisible forever.
#   1: subagent runs -- Claude's ``<session>/subagents/*.jsonl`` transcripts,
#      and OpenCode's parent/agent columns.
#   2: the agent name behind a Claude subagent run (``attributionAgent``).
#   3: CodeBuddy's subagent transcripts, and Codex's thread spawn edges.
#   4: Antigravity session history and transcripts.
#   5: Antigravity project_path inference from Cwd and user_information.
#   6: Antigravity subagent lineage and parent_session_id resolution.
BACKFILL_VERSION = 6


def _collect_all() -> list[RawUsageEntry]:
    """Collects usage entries incrementally and merges them with history.

    Returns:
        List[RawUsageEntry]: The full list of raw usage entries.
    """
    # 1. Load existing history
    history = load_history()

    # Snapshots from removed collectors persist in the history file and would
    # keep surfacing on the analytics pages unless actively purged.
    kept = [
        entry
        for entry in history
        if entry.target not in {"workbuddy", "trae", "gemini"}
    ]
    if len(kept) != len(history):
        history = kept
        save_history(history)

    last_ts = get_last_timestamps()

    # A record a collector has only just learned to read is usually older than
    # the watermark, so the first scan that can see it has to ignore the
    # watermark for that engine and merge rather than append.
    rebuilding = backfill_pending(BACKFILL_VERSION)
    if rebuilding:
        last_ts = dict.fromkeys(last_ts, "")

    # 2. Collect only new entries
    new_entries: list[RawUsageEntry] = []
    new_entries.extend(scan_claude_usage(since_timestamp=last_ts.get("claude", "")))
    new_entries.extend(scan_opencode_usage(since_timestamp=last_ts.get("opencode", "")))
    new_entries.extend(
        scan_codebuddy_usage(since_timestamp=last_ts.get("codebuddy", ""))
    )
    new_entries.extend(
        scan_antigravity_usage(since_timestamp=last_ts.get("antigravity", ""))
    )

    # Codex exposes a mutable session-level token total keyed by thread ID. Its
    # creation timestamp does not change as usage grows, so timestamp-only
    # incremental collection permanently misses later token updates. Re-scan
    # Codex snapshots and replace matching historical sessions instead.
    codex_snapshots = scan_codex_usage()
    codex_by_session = {
        entry.session_id: entry for entry in history if entry.target == "codex"
    }
    codex_by_session.update({entry.session_id: entry for entry in codex_snapshots})
    non_codex_history = [entry for entry in history if entry.target != "codex"]
    history = non_codex_history + list(codex_by_session.values())

    # 3. Save new entries to history file
    if rebuilding:
        # Additive on purpose: engines prune their own transcripts, so the
        # archive holds sessions the rescan cannot reproduce.
        history = merge_history(history, new_entries)
        save_history(history)
        mark_backfill_done(BACKFILL_VERSION)
    elif new_entries:
        append_history(new_entries)
        history.extend(new_entries)
    if codex_snapshots:
        save_history(history)

    return history


def _build_engine_summary(entries: list[RawUsageEntry]) -> list[dict[str, Any]]:
    """Builds a summarized report of usage statistics grouped by engine.

    Args:
        entries: A list of raw usage entries to summarize.

    Returns:
        List[Dict[str, Any]]: A list of dictionaries, each containing aggregated
            statistics for a specific engine (target), including token counts,
            session count, and unique models used.
    """
    stats: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "inputTokens": 0,
            "outputTokens": 0,
            "cacheCreationTokens": 0,
            "cacheReadTokens": 0,
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
                "sessionCount": len(s["sessionIds"]),
                "models": sorted(s["models"]),
            }
        )
    return result


def _build_model_summary(entries: list[RawUsageEntry]) -> list[dict[str, Any]]:
    stats: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "inputTokens": 0,
            "outputTokens": 0,
            "cacheCreationTokens": 0,
            "cacheReadTokens": 0,
            "sessionIds": set(),
            "targets": set(),
        }
    )
    for e in entries:
        s = stats[e.model]
        s["inputTokens"] += e.input_tokens
        s["outputTokens"] += e.output_tokens
        s["cacheCreationTokens"] += e.cache_creation_tokens
        s["cacheReadTokens"] += e.cache_read_tokens
        s["sessionIds"].add(e.session_id)
        s["targets"].add(e.target)

    # Ranked by input + output: cache reads run to billions on long sessions
    # and would put every long-context model above the ones doing the work.
    ranked = sorted(
        stats.items(), key=lambda x: -(x[1]["inputTokens"] + x[1]["outputTokens"])
    )
    result = []
    for model, s in ranked:
        result.append(
            {
                "model": model,
                "inputTokens": s["inputTokens"],
                "outputTokens": s["outputTokens"],
                "cacheCreationTokens": s["cacheCreationTokens"],
                "cacheReadTokens": s["cacheReadTokens"],
                "sessionCount": len(s["sessionIds"]),
                "targets": sorted(s["targets"]),
            }
        )
    return result


def _collect_and_cache() -> dict[str, Any]:
    """Runs the collection pipeline and caches the result (caller holds lock)."""
    entries = _collect_all()
    data = aggregate(entries)
    data["engines"] = _build_engine_summary(entries)
    data["models"] = _build_model_summary(entries)
    save_cache(data)
    return data


# The analytics routes run collection in worker threads (asyncio.to_thread),
# and the Usage page fires all six endpoints at once — every cache miss would
# otherwise run _collect_all concurrently, interleaving history-file writes
# (append_history/save_history are plain file rewrites, not atomic RMWs).
_collect_lock = threading.Lock()

#: 后台刷新在飞标志：过期时每个请求都会想踢一次，只放行第一个。
_refreshing = False
_refresh_lock = threading.Lock()


def _refresh_in_background() -> None:
    """在后台重采一次，让下一次请求读到新鲜数据。

    采集要 ~4s（重读 35MB 归档 + 扫各引擎），让它挡在请求路径上会把首屏拖到
    好几秒；而归档只会被采集本身写入，不主动回看就永远看不到新用量。
    """
    global _refreshing
    with _refresh_lock:
        if _refreshing:
            return
        _refreshing = True

    def _run() -> None:
        global _refreshing
        try:
            refresh_analytics_data()
        except Exception:
            # 派生数据：采集失败就继续用旧值，下次再试。
            logger.exception("Background analytics refresh failed")
        finally:
            with _refresh_lock:
                _refreshing = False

    threading.Thread(target=_run, daemon=True).start()


def get_analytics_data(force_refresh: bool = False) -> dict[str, Any]:
    """Retrieves analytics data, using cache if available and not forced to refresh.

    Stale-while-revalidate: an expired-but-usable cache is served immediately
    while a refresh runs in the background, so the caller never waits for a
    collection. Only a cold start (no cache at all) pays it inline.

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
        # 只是过期（不是输入变了）：先给旧数据，后台去刷新。
        stale = load_cache(allow_stale=True)
        if stale is not None:
            _refresh_in_background()
            return stale

    with _collect_lock:
        # Double-check after acquiring: a concurrent caller may have finished
        # the collection we were both queued for.
        if not force_refresh:
            cached = load_cache()
            if cached is not None:
                return cached
        return _collect_and_cache()


def refresh_analytics_data() -> dict[str, Any]:
    """Invalidates the cache and forces a fresh collection of analytics data.

    Returns:
        Dict[str, Any]: The freshly collected and aggregated analytics data.
    """
    with _collect_lock:
        invalidate_cache()
        return _collect_and_cache()

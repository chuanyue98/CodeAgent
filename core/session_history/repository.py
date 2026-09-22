"""会话历史的统一读取入口。

路由与 CLI 都不该直接碰 finder 或索引：这里把"优先查索引、索引不可用时回退
到原来的全量解析"收敛在一处，调用方拿到的形状与 ``to_summary_dict`` /
``to_full_dict`` 一致。

回退是刻意的：索引是派生数据，缺失/损坏/被显式关闭时功能必须照旧可用，只是
慢回原来的样子。
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from core.session_history.audit import build_audit_events
from core.session_history.index_ingest import get_indexer
from core.session_history.index_store import get_index, session_key, to_epoch
from core.session_history.models import UnifiedSession
from core.session_history.session_finder import find_all_sessions, find_session_by_id


def kick_sync() -> None:
    """热读端点调用：顺手触发一次防抖增量同步，不阻塞本次请求。

    没有它，长时间运行的服务会一直停在建索引那一刻的会话快照上。
    """
    indexer = get_indexer()
    if indexer is not None:
        indexer.sync_if_stale()


def force_sync() -> None:
    """同步且强制重建索引（手动刷新用）。索引不可用时什么都不做。"""
    indexer = get_indexer()
    if indexer is not None:
        indexer.sync(force=True)


def ensure_index_ready(notify: Callable[[], None] | None = None) -> bool:
    """索引没建好就在前台建完，返回之后的读是否走得到索引。

    一次性进程（CLI）在读会话之前调用：见
    :meth:`core.session_history.index_ingest.SessionIndexer.ensure_ready`。
    长驻服务不要用，它们该走 :func:`kick_sync` 的后台同步。
    """
    indexer = get_indexer()
    if indexer is None:
        return False
    return indexer.ensure_ready(notify)


def _ready_index():
    """只在索引"已经完整同步过一次"时返回它，否则 None（调用方回退）。

    首轮构建是在后台跑的：刚启动时索引还没内容，若此时就走索引，用户会看到
    空列表——宁可慢一点走原来的解析，也不要先给一个空页面。
    """
    index = get_index()
    if index is None or not index.is_ready():
        return None
    return index


def _project_or_none(project: str | None) -> str | None:
    return project or None


def list_summaries(
    *,
    project: str | None = None,
    engine: str | None = None,
    include_subagents: bool = False,
    limit: int = 500,
) -> list[dict[str, Any]]:
    """按 ``started_at`` 倒序的会话摘要列表。"""
    kick_sync()
    index = _ready_index()
    if index is not None:
        return [
            row.to_summary_dict()
            for row in index.list_summaries(
                project=project,
                engine=engine,
                include_subagents=include_subagents,
                limit=limit,
            )
        ]
    found = find_all_sessions(project, engine=engine)
    if not include_subagents:
        found = [s for s in found if not s.parent_session_id]
    return [s.to_summary_dict() for s in found[:limit]]


def get_title_map() -> dict[tuple[str, str], str]:
    """``(engine, session_id) -> 标题``，供分析页把标题并到用量行上。"""
    index = _ready_index()
    if index is not None:
        return index.get_title_map()
    return {
        (s.engine.value, s.session_id): s.to_summary_dict()["title"]
        for s in find_all_sessions()
    }


def get_summary(
    engine: str, session_id: str, project: str | None = None
) -> dict[str, Any] | None:
    index = _ready_index()
    if index is not None:
        summary = index.get_summary(engine, session_id)
        return summary.to_summary_dict() if summary else None
    session = find_session_by_id(session_id, engine, _project_or_none(project))
    return session.to_summary_dict() if session else None


def get_full(
    engine: str, session_id: str, project: str | None = None
) -> UnifiedSession | None:
    """完整会话（详情/转换用）。

    索引里查不到时回退到单次解析——刚建立、还没同步进索引的会话走这条路。
    """
    kick_sync()
    index = _ready_index()
    if index is not None:
        session = index.reconstruct(engine, session_id)
        if session is not None:
            return session
    return find_session_by_id(session_id, engine, _project_or_none(project))


def forget_session(engine: str, session_id: str) -> None:
    """把会话从索引里摘掉（引擎侧的文件由调用方删除）。"""
    index = get_index()
    if index is None:
        return
    key = session_key(engine, session_id)
    for source in index.sources_for_session(key):
        index.remove_source(source)
    index.delete_session(key)


def audit_events(
    *,
    engine: str | None = None,
    project: str | None = None,
    since: str | None = None,
    until: str | None = None,
    limit: int = 500,
) -> list[dict[str, Any]]:
    """跨会话的消息/工具调用时间线，newest first。"""
    kick_sync()
    index = _ready_index()
    if index is not None:
        return index.audit_events(
            engine=engine,
            project=project,
            since=to_epoch(since) if since else None,
            until=to_epoch(until) if until else None,
            limit=limit,
        )
    events = build_audit_events(
        find_all_sessions(_project_or_none(project), engine=engine)
    )
    if since:
        since_epoch = to_epoch(since)
        events = [
            e for e in events if (to_epoch(e["timestamp"]) or 0) >= (since_epoch or 0)
        ]
    if until:
        until_epoch = to_epoch(until)
        events = [
            e
            for e in events
            if until_epoch is not None
            and (to_epoch(e["timestamp"]) or 0) <= until_epoch
        ]
    return events[:limit]


def tool_usage(
    *,
    project: str | None = None,
    engine: str | None = None,
    days: int | None = None,
) -> dict[str, Any]:
    """按工具名统计调用次数；``days`` 只计时间窗内的会话。"""
    since: int | None = None
    if days is not None and days > 0:
        since = int((datetime.now(UTC) - timedelta(days=days)).timestamp())
    index = _ready_index()
    if index is not None:
        return index.tool_usage(project=project, engine=engine, since=since)
    return _tool_usage_fallback(project, engine, since)


def _tool_usage_fallback(
    project: str | None, engine: str | None, since: int | None
) -> dict[str, Any]:
    """索引不可用时的等价实现（沿用改造前的计数语义）。"""
    sessions = find_all_sessions(_project_or_none(project), engine=engine)
    totals: Counter[str] = Counter()
    per_engine: dict[str, Counter[str]] = defaultdict(Counter)
    engines: Counter[str] = Counter()
    counted_sessions = 0

    for session in sessions:
        if since is not None:
            activity = to_epoch(session.ended_at or session.started_at)
            # 时间戳缺失/解析不了时保留：宁可略微高估，也别悄悄漏掉。
            if activity is not None and activity < since:
                continue
        counted_sessions += 1
        session_engine = str(session.engine.value or "unknown")
        # EngineType 是 str Enum，本身就是连线值。
        for message in session.messages:
            for call in message.tool_calls:
                name = call.name.strip()
                if not name:
                    continue
                totals[name] += 1
                per_engine[name][session_engine] += 1
                engines[session_engine] += 1

    return {
        "tools": [
            {
                "name": name,
                "count": count,
                "byEngine": dict(per_engine[name].most_common()),
            }
            for name, count in totals.most_common()
        ],
        "totalCalls": sum(totals.values()),
        "sessions": counted_sessions,
        "engines": dict(engines.most_common()),
    }

from __future__ import annotations

import asyncio
import base64
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Query

from core.analytics.service import get_analytics_data, refresh_analytics_data
from core.constants import normalize_engine_name
from core.session_history import repository
from core.session_history.parse_cache import clear_parse_cache
from core.session_history.paths import normalize_project_path
from core.web.case_convert import camelize

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


async def _data() -> dict:
    # Collection is synchronous filesystem work (a cold refresh scans every
    # engine's history); running it on the loop would stall other requests,
    # including the WebSocket agent transport.
    return await asyncio.to_thread(get_analytics_data)


# (engine, session_id) -> title, from the session_history subsystem. The
# analytics usage entries carry no titles of their own, so the sessions list
# joins against the native history.
#
# This used to be held behind a 120 s TTL because building it re-read every
# engine's history -- ~900 MB of JSONL, ~2.2 s -- and one request in three paid
# for it. ``session_history.parse_cache`` now memoizes that parse per file, so
# a rebuild costs ~0.2 s of stat calls and the TTL is gone with it: a session
# started a moment ago shows up on the next request instead of up to two
# minutes later.


def _collect_session_pairs(sessions: list[dict]) -> list[tuple[str, str]]:
    """收集会话列表及其子代理对应的唯一 ``(engine, session_id)`` 键。"""
    seen: set[tuple[str, str]] = set()
    pairs: list[tuple[str, str]] = []
    for session in sessions:
        for row in (session, *session.get("subtasks", ())):
            engine = normalize_engine_name(str(row.get("target") or ""))
            session_id = str(row.get("sessionId") or "")
            if engine and session_id and (engine, session_id) not in seen:
                seen.add((engine, session_id))
                pairs.append((engine, session_id))
    return pairs


def _lookup_titles_sync(
    sessions: list[dict], *, project: str | None = None
) -> dict[tuple[str, str], str]:
    """按需查询目标会话标题，避免每次分页请求扫描或拉取整张标题表。"""
    pairs = _collect_session_pairs(sessions)
    if not pairs:
        return {}
    return repository.get_title_map(pairs=pairs, project=project)


async def _targeted_title_map(
    sessions: list[dict], *, project: str | None = None
) -> dict[tuple[str, str], str]:
    if not sessions:
        return {}
    return await asyncio.to_thread(_lookup_titles_sync, sessions, project=project)


@router.get("/summary")
async def get_summary():
    data = await _data()
    return camelize(data["summary"])


@router.get("/daily")
async def get_daily():
    data = await _data()
    return data["daily"]


@router.get("/monthly")
async def get_monthly():
    data = await _data()
    return data["monthly"]


def _encode_cursor(session: dict) -> str:
    """Opaque keyset cursor for one session row.

    Keyed on ``(lastActivity, sessionId)`` rather than an offset: the list is
    rebuilt per request, and an offset silently skips or repeats rows whenever
    a session's activity changes between two pages.
    """
    raw = f"{session.get('lastActivity', '')}|{session.get('sessionId', '')}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def _utc_sort_str(value: object) -> str:
    """将混合时区 ISO 时间戳规范为固定 UTC 字符串，保证排序与游标比较一致。"""
    raw = str(value or "").strip()
    if not raw:
        return ""
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    except ValueError:
        return raw


def _decode_cursor(cursor: str) -> tuple[str, str] | None:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode()).decode()
    except (ValueError, UnicodeDecodeError):
        return None
    activity, separator, session_id = raw.partition("|")
    return (_utc_sort_str(activity), session_id) if separator else None


def _sort_key(session: dict) -> tuple[str, str]:
    return (
        _utc_sort_str(session.get("lastActivity")),
        str(session.get("sessionId") or ""),
    )


@router.get("/sessions")
async def get_sessions(
    limit: int = Query(100, ge=1, le=1000),
    project: str | None = Query(
        None,
        description="Project directory path; omit to include every project",
    ),
    search: str | None = Query(
        None,
        description="Case-insensitive substring of the title, id, project or engine",
    ),
    cursor: str | None = Query(
        None,
        description="`nextCursor` from a previous page; omit for the first page",
    ),
):
    """One page of sessions, newest first.

    Returns ``{sessions, nextCursor, total}``. The list used to be a bare array
    capped at whatever ``limit`` the caller hard-coded, so a machine with more
    sessions than that had the remainder truncated before they reached the
    browser -- and every client-side filter then ran against that partial
    window.

    Narrowing happens before the page is cut, or a busy neighbouring project
    would crowd the requested one out and the response would look empty.
    Titles are attached only to the rows actually returned: joining them onto
    the whole set meant copying every session dict on every request.
    """
    data = await _data()
    sessions = data["sessions"]

    def _title(title_map: dict[tuple[str, str], str], session: dict) -> str:
        engine = normalize_engine_name(str(session.get("target") or ""))
        return title_map.get((engine, str(session.get("sessionId") or "")), "")

    def _with_titles(title_map: dict[tuple[str, str], str], session: dict) -> dict:
        return {
            **session,
            "title": _title(title_map, session),
            "subtasks": [
                _with_titles(title_map, child) for child in session.get("subtasks", ())
            ],
        }

    def _searchable(title_map: dict[tuple[str, str], str], session: dict) -> str:
        # Subagent titles are part of the parent's haystack: the subtask rows
        # are no longer searchable on their own, and "which session ran that
        # review" is exactly what the box is used for.
        parts = [
            _title(title_map, session),
            str(session.get("sessionId") or ""),
            str(session.get("projectPath") or ""),
            str(session.get("target") or ""),
            *(_title(title_map, child) for child in session.get("subtasks", ())),
        ]
        return " ".join(parts).lower()

    if project:
        target = normalize_project_path(project)
        sessions = [
            s
            for s in sessions
            if normalize_project_path(s.get("projectPath") or "") == target
        ]

    needle = search.strip().lower() if search else ""
    if needle:
        title_map = await _targeted_title_map(sessions, project=project)
        sessions = [s for s in sessions if needle in _searchable(title_map, s)]
        total = len(sessions)
        sessions = sorted(sessions, key=_sort_key, reverse=True)
        if cursor:
            after = _decode_cursor(cursor)
            if after is None:
                raise HTTPException(status_code=400, detail="Malformed cursor")
            sessions = [s for s in sessions if _sort_key(s) < after]
        page = sessions[:limit]
        has_more = len(sessions) > limit
    else:
        total = len(sessions)
        # `data["sessions"]` arrives sorted by last activity, but the cursor
        # compares against a specific key, so make the ordering explicit here.
        sessions = sorted(sessions, key=_sort_key, reverse=True)
        if cursor:
            after = _decode_cursor(cursor)
            if after is None:
                raise HTTPException(status_code=400, detail="Malformed cursor")
            sessions = [s for s in sessions if _sort_key(s) < after]
        page = sessions[:limit]
        has_more = len(sessions) > limit
        title_map = await _targeted_title_map(page, project=project)

    return {
        "sessions": [_with_titles(title_map, s) for s in page],
        "nextCursor": _encode_cursor(page[-1]) if page and has_more else None,
        "total": total,
    }


@router.get("/engines")
async def get_engines():
    data = await _data()
    return data["engines"]


@router.get("/models")
async def get_models():
    data = await _data()
    return data.get("models", [])


@router.get("/tools")
async def get_tool_usage(
    project: str | None = Query(
        None, description="Project directory path; omit to include every project"
    ),
    engine: str | None = Query(None, description="Filter by engine"),
    days: int | None = Query(
        None, ge=1, le=3650, description="Only count sessions active within N days"
    ),
):
    """按工具名的调用排行，从每个引擎的会话历史统计。

    刻意不来自 ``core.analytics``——那条管线只汇总 token/成本，从不带工具调用。
    跨引擎统计是任何单一厂商 CLI 都做不到的部分。
    """
    return await asyncio.to_thread(
        repository.tool_usage, project=project, engine=engine, days=days
    )


@router.post("/refresh")
async def refresh():
    # The parse cache invalidates itself on a file's mtime, but an explicit
    # refresh is what you press when you suspect something is stale -- so drop
    # it rather than explain why it was not dropped.
    clear_parse_cache()
    # 索引也要跟着重建：用户按刷新就是因为怀疑某处不是最新的。
    await asyncio.to_thread(repository.force_sync)
    data = await asyncio.to_thread(refresh_analytics_data)
    return {
        "status": "refreshed",
        "summary": camelize(data["summary"]),
    }

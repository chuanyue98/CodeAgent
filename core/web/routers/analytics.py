from __future__ import annotations

import asyncio
import base64
from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException, Query

from core.analytics.service import get_analytics_data, refresh_analytics_data
from core.session_history.parse_cache import clear_parse_cache
from core.session_history.paths import normalize_project_path
from core.session_history.session_finder import find_all_sessions
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


async def _session_title_map() -> dict[tuple[str, str], str]:
    def _build() -> dict[tuple[str, str], str]:
        return {
            (s.engine.value, s.session_id): s.to_summary_dict()["title"]
            for s in find_all_sessions()
        }

    return await asyncio.to_thread(_build)


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


def _decode_cursor(cursor: str) -> tuple[str, str] | None:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode()).decode()
    except (ValueError, UnicodeDecodeError):
        return None
    activity, separator, session_id = raw.partition("|")
    return (activity, session_id) if separator else None


def _sort_key(session: dict) -> tuple[str, str]:
    return (str(session.get("lastActivity") or ""), str(session.get("sessionId") or ""))


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
    title_map = await _session_title_map()

    def _title(session: dict) -> str:
        return title_map.get(
            (session.get("target", ""), session.get("sessionId", "")), ""
        )

    def _with_titles(session: dict) -> dict:
        return {
            **session,
            "title": _title(session),
            "subtasks": [_with_titles(child) for child in session.get("subtasks", ())],
        }

    def _searchable(session: dict) -> str:
        # Subagent titles are part of the parent's haystack: the subtask rows
        # are no longer searchable on their own, and "which session ran that
        # review" is exactly what the box is used for.
        parts = [
            _title(session),
            str(session.get("sessionId") or ""),
            str(session.get("projectPath") or ""),
            str(session.get("target") or ""),
            *(_title(child) for child in session.get("subtasks", ())),
        ]
        return " ".join(parts).lower()

    if project:
        target = normalize_project_path(project)
        sessions = [
            s
            for s in sessions
            if normalize_project_path(s.get("projectPath") or "") == target
        ]

    if search:
        needle = search.strip().lower()
        if needle:
            sessions = [s for s in sessions if needle in _searchable(s)]

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
    return {
        "sessions": [_with_titles(s) for s in page],
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


def _tool_usage(
    project: str | None,
    engine: str | None,
    days: int | None,
) -> dict:
    """Counts tool calls per tool, per engine, from parsed session history.

    Deliberately not sourced from ``core.analytics`` -- that pipeline
    aggregates token/cost rows and never carries tool calls. The parsers in
    ``core.session_history`` are the only place ``tool_calls`` exists, and
    ``/api/history/audit`` already reads them the same way.

    Counting across every engine is the part no single vendor CLI can do:
    each one only ever sees its own sessions.
    """
    sessions = find_all_sessions(project, engine=engine)

    cutoff = None
    if days is not None and days > 0:
        cutoff = datetime.now(UTC) - timedelta(days=days)

    totals: Counter[str] = Counter()
    per_engine: dict[str, Counter[str]] = defaultdict(Counter)
    engines: Counter[str] = Counter()
    counted_sessions = 0

    for session in sessions:
        if cutoff is not None:
            parsed = _as_utc(session.ended_at or session.started_at)
            # A session whose timestamp is missing or unparseable is kept:
            # dropping it would silently understate the totals, and an
            # inflated window is easier to notice than a quiet omission.
            if parsed is not None and parsed < cutoff:
                continue

        counted_sessions += 1
        # EngineType is a str Enum, so this is already the wire value.
        session_engine = str(session.engine.value or "unknown")
        for message in session.messages:
            for call in message.tool_calls:
                name = call.name.strip()
                if not name:
                    continue
                totals[name] += 1
                per_engine[name][session_engine] += 1
                engines[session_engine] += 1

    tools = [
        {
            "name": name,
            "count": count,
            "byEngine": dict(per_engine[name].most_common()),
        }
        for name, count in totals.most_common()
    ]
    return {
        "tools": tools,
        "totalCalls": sum(totals.values()),
        "sessions": counted_sessions,
        "engines": dict(engines.most_common()),
    }


def _as_utc(value: str) -> datetime | None:
    """Best-effort parse of a session timestamp into an aware UTC datetime.

    Returns None for anything unparseable; the caller treats that as "keep",
    not "drop".
    """
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


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
    """Returns a tool-usage ranking built from every engine's session history."""
    return await asyncio.to_thread(_tool_usage, project, engine, days)


@router.post("/refresh")
async def refresh():
    # The parse cache invalidates itself on a file's mtime, but an explicit
    # refresh is what you press when you suspect something is stale -- so drop
    # it rather than explain why it was not dropped.
    clear_parse_cache()
    data = await asyncio.to_thread(refresh_analytics_data)
    return {
        "status": "refreshed",
        "summary": camelize(data["summary"]),
    }

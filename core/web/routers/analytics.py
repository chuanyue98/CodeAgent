from __future__ import annotations

import asyncio

from fastapi import APIRouter, Query

from core.analytics.service import get_analytics_data, refresh_analytics_data
from core.session_history.paths import normalize_project_path

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


async def _data() -> dict:
    # Collection is synchronous filesystem work (a cold refresh scans every
    # engine's history); running it on the loop would stall other requests,
    # including the WebSocket agent transport.
    return await asyncio.to_thread(get_analytics_data)


@router.get("/summary")
async def get_summary():
    data = await _data()
    return data["summary"]


@router.get("/daily")
async def get_daily():
    data = await _data()
    return data["daily"]


@router.get("/monthly")
async def get_monthly():
    data = await _data()
    return data["monthly"]


@router.get("/sessions")
async def get_sessions(
    limit: int = 100,
    project: str | None = Query(
        None,
        description="Project directory path; omit to include every project",
    ),
):
    """Returns the most recent sessions, newest first.

    Filtering happens before ``limit`` is applied: narrowing to a project has
    to search the whole set, or a busy neighbouring project would crowd the
    requested one out of the window and the response would look empty.
    """
    data = await _data()
    sessions = data["sessions"]
    if project:
        target = normalize_project_path(project)
        sessions = [
            s
            for s in sessions
            if normalize_project_path(s.get("projectPath") or "") == target
        ]
    return sessions[:limit]


@router.get("/engines")
async def get_engines():
    data = await _data()
    return data["engines"]


@router.get("/models")
async def get_models():
    data = await _data()
    return data.get("models", [])


@router.post("/refresh")
async def refresh():
    data = await asyncio.to_thread(refresh_analytics_data)
    return {"status": "refreshed", "summary": data["summary"]}

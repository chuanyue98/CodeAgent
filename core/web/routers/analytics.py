from __future__ import annotations

from fastapi import APIRouter, Query

from core.analytics.service import get_analytics_data, refresh_analytics_data

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


def _normalize_project(path: str) -> str:
    """Canonicalizes a project path for comparison.

    Mirrors the normalization the session parsers already use (see
    codex_parser/opencode_parser): separators unified, case folded, trailing
    separator dropped — so a workspace registered as ``E:\\demo\\App`` matches
    session records written as ``e:/demo/app/``.
    """
    return path.replace("\\", "/").lower().rstrip("/")


@router.get("/summary")
async def get_summary():
    data = get_analytics_data()
    return data["summary"]


@router.get("/daily")
async def get_daily():
    data = get_analytics_data()
    return data["daily"]


@router.get("/monthly")
async def get_monthly():
    data = get_analytics_data()
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
    data = get_analytics_data()
    sessions = data["sessions"]
    if project:
        target = _normalize_project(project)
        sessions = [
            s
            for s in sessions
            if _normalize_project(s.get("projectPath") or "") == target
        ]
    return sessions[:limit]


@router.get("/engines")
async def get_engines():
    data = get_analytics_data()
    return data["engines"]


@router.get("/models")
async def get_models():
    data = get_analytics_data()
    return data.get("models", [])


@router.post("/refresh")
async def refresh():
    data = refresh_analytics_data()
    return {"status": "refreshed", "summary": data["summary"]}

from __future__ import annotations

from fastapi import APIRouter

from core.analytics.service import get_analytics_data, refresh_analytics_data

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


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
async def get_sessions(limit: int = 100):
    data = get_analytics_data()
    return data["sessions"][:limit]


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

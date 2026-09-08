from __future__ import annotations

from fastapi import APIRouter, Path, Query, Request

from core.services.run_store import RunStore
from core.web.case_convert import ProtocolModel, wire
from core.web.routers import tasks as tasks_router

router = APIRouter(prefix="/api", tags=["notifications"])


def _get_run_store(request: Request) -> RunStore:
    if hasattr(request.app.state, "run_store") and request.app.state.run_store is not None:
        return request.app.state.run_store
    return tasks_router._runner._run_store


class NotificationItem(ProtocolModel):
    id: int
    created_at: float
    schedule_id: str | None = None
    task_id: str | None = None
    task_name: str | None = None
    engine: str | None = None
    status: str
    title: str
    summary: str | None = None
    read_at: float | None = None


@router.get("/notifications")
def list_notifications(
    request: Request,
    limit: int = Query(50, le=100),
    unread_only: bool = Query(False),
) -> list[dict]:
    """Lists recent notifications (most recent first)."""
    store = _get_run_store(request)
    rows = store.list_notifications(limit=limit, unread_only=unread_only)
    result = []
    for row in rows:
        item = wire(NotificationItem(**row))
        item["task_id"] = row.get("task_id")
        item["schedule_id"] = row.get("schedule_id")
        item["task_name"] = row.get("task_name")
        item["created_at"] = row.get("created_at")
        item["read_at"] = row.get("read_at")
        result.append(item)
    return result


@router.get("/notifications/unread-count")
def unread_count(request: Request) -> dict:
    """Returns the total number of unread notifications."""
    store = _get_run_store(request)
    return {"count": store.count_unread()}


@router.post("/notifications/{notification_id}/read")
def mark_read(
    request: Request,
    notification_id: int = Path(..., ge=1),
) -> dict:
    """Marks a single notification as read."""
    store = _get_run_store(request)
    store.mark_read(notification_id)
    return {"status": "ok"}


@router.post("/notifications/read-all")
def mark_all_read(request: Request) -> dict:
    """Marks all unread notifications as read."""
    store = _get_run_store(request)
    store.mark_all_read()
    return {"status": "ok"}

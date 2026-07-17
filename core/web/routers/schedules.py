"""Web API router for CronPage: cron-triggered background task schedules.

Endpoints:
  GET    /api/schedules              List all schedules.
  POST   /api/schedules              Create a schedule.
  PATCH  /api/schedules/{id}         Update a schedule (cron_expr, enabled, ...).
  DELETE /api/schedules/{id}         Delete a schedule.
  POST   /api/schedules/{id}/run-now Fire a schedule's task immediately,
                                      independent of its cron timing.

Schedules are checked and fired by the background loop started in
core/web/server.py's lifespan (core/services/scheduler_loop.py) — this
router only manages the persisted schedule records themselves.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.services.config_service import ConfigService
from core.services.schedule_service import ScheduleService
from core.web.routers import tasks as tasks_router
from core.web.routers.config import get_config_path

router = APIRouter(prefix="/api", tags=["schedules"])


def _service() -> ScheduleService:
    return ScheduleService(ConfigService(get_config_path()))


class CreateScheduleRequest(BaseModel):
    """Request body for creating a schedule."""

    task_name: str
    engine: str
    group: str = "common"
    workspace: str
    cron_expr: str
    enabled: bool = True


class UpdateScheduleRequest(BaseModel):
    """Request body for updating a schedule. Omitted fields are left as-is."""

    task_name: str | None = None
    engine: str | None = None
    group: str | None = None
    workspace: str | None = None
    cron_expr: str | None = None
    enabled: bool | None = None


@router.get("/schedules")
def list_schedules() -> list[dict]:
    """Lists all cron schedules."""
    return _service().list_schedules()


@router.post("/schedules")
def create_schedule(req: CreateScheduleRequest) -> dict:
    """Creates a new cron schedule targeting an existing file-based Task."""
    try:
        return _service().create_schedule(
            req.task_name,
            req.engine,
            req.group,
            req.cron_expr,
            req.enabled,
            tasks_router.resolve_registered_workspace(req.workspace),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch("/schedules/{schedule_id}")
def update_schedule(schedule_id: str, req: UpdateScheduleRequest) -> dict:
    """Updates a schedule's fields (e.g. toggling enabled, editing cron_expr)."""
    try:
        fields = req.model_dump(exclude_unset=True)
        if fields.get("workspace") is not None:
            fields["workspace"] = tasks_router.resolve_registered_workspace(
                fields["workspace"]
            )
        return _service().update_schedule(schedule_id, **fields)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/schedules/{schedule_id}")
def delete_schedule(schedule_id: str) -> dict:
    """Deletes a schedule."""
    try:
        _service().delete_schedule(schedule_id)
        return {"status": "ok"}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/schedules/{schedule_id}/run-now")
def run_now(schedule_id: str) -> dict:
    """Fires a schedule's task immediately, outside its normal cron timing."""
    service = _service()
    record = service.get_schedule(schedule_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Schedule not found")

    try:
        workspace = record.get("workspace")
        if not workspace:
            raise HTTPException(
                status_code=409,
                detail="Schedule has no workspace; edit it before running",
            )
        workspace = tasks_router.resolve_registered_workspace(workspace)
        if hasattr(
            tasks_router._runner, "has_active_task"
        ) and tasks_router._runner.has_active_task(record["task_name"]):
            raise HTTPException(status_code=409, detail="Task is already running")
        status = tasks_router._runner.run_task(
            record["task_name"],
            record["engine"],
            record["group"],
            tasks_root=tasks_router.get_tasks_root(),
            workspace=workspace,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if getattr(status, "status", "running") != "running":
        service.record_run(
            schedule_id, f"failed: {status.status}", advance_schedule=False
        )
    else:
        service.record_run(schedule_id, "started", advance_schedule=False)
    return status.__dict__

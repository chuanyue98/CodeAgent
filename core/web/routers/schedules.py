"""Web API router for CronPage: cron-triggered background task schedules.

Endpoints:
  GET    /api/schedules              List all schedules.
  GET    /api/schedules/preview      Validate a cron expression and preview
                                      its next few fire times (no persistence).
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
from core.services.runner_service import TaskAlreadyRunningError
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


@router.get("/schedules/preview")
def preview_schedule(cron_expr: str) -> dict:
    """Validates a cron expression and returns its next few fire times.

    Used by the schedule form for a live "next run" preview before the
    user saves anything -- an invalid expression is a normal, expected
    input while typing, not an error, so this returns `{"valid": False}`
    rather than a 4xx.
    """
    try:
        next_runs = _service().preview_next_runs(cron_expr)
        return {"valid": True, "next_runs": next_runs}
    except ValueError:
        return {"valid": False, "next_runs": []}


@router.post("/schedules")
def create_schedule(req: CreateScheduleRequest) -> dict:
    """Creates a new cron schedule targeting an existing file-based Task."""
    try:
        workspace = tasks_router.resolve_registered_workspace(req.workspace)
        return _service().create_schedule(
            req.task_name,
            req.engine,
            workspace.group,
            req.cron_expr,
            req.enabled,
            workspace.path,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch("/schedules/{schedule_id}")
def update_schedule(schedule_id: str, req: UpdateScheduleRequest) -> dict:
    """Updates a schedule's fields (e.g. toggling enabled, editing cron_expr)."""
    try:
        fields = req.model_dump(exclude_unset=True)
        existing = _service().get_schedule(schedule_id)
        if existing is None:
            raise KeyError(f"Schedule not found: {schedule_id}")
        workspace_value = fields.get("workspace")
        if workspace_value is not None:
            workspace = tasks_router.resolve_registered_workspace(workspace_value)
            fields["workspace"] = workspace.path
            fields["group"] = workspace.group
        elif fields.get("group") is not None and existing.get("workspace"):
            workspace = tasks_router.resolve_registered_workspace(existing["workspace"])
            fields["group"] = workspace.group
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
        registered_workspace = tasks_router.resolve_registered_workspace(workspace)
        status = tasks_router._runner.run_task(
            record["task_name"],
            record["engine"],
            registered_workspace.group,
            tasks_root=tasks_router.get_tasks_root(),
            workspace=registered_workspace.path,
            prevent_overlap=True,
        )
    except TaskAlreadyRunningError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if getattr(status, "status", "running") != "running":
        failure_status = str(status.status)
        service.record_run(
            schedule_id,
            failure_status
            if failure_status.startswith("failed")
            else f"failed: {failure_status}",
            advance_schedule=False,
        )
    else:
        service.record_run(schedule_id, "started", advance_schedule=False)
    return status.__dict__

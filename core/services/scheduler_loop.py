from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path
from typing import Callable

from core.services.runner_service import TaskAlreadyRunningError, TaskRunner
from core.services.schedule_service import ScheduleService
from core.services.task_service import TaskService
from core.services.workspace_service import (
    WorkspaceConfigError,
    WorkspaceNotRegisteredError,
    WorkspaceResolutionError,
    resolve_registered_workspace,
)

TICK_INTERVAL_SECONDS = 30.0
logger = logging.getLogger(__name__)


async def scheduler_tick_loop(
    schedule_service: ScheduleService,
    task_runner: TaskRunner,
    get_tasks_root: Callable[[], Path],
    tick_interval: float = TICK_INTERVAL_SECONDS,
) -> None:
    """Background loop firing any enabled, due schedule.

    Runs until cancelled — intended to be wrapped in an asyncio.Task by the
    FastAPI lifespan and cancelled on shutdown.
    """
    while True:
        try:
            await tick_once(schedule_service, task_runner, get_tasks_root)
        except asyncio.CancelledError:
            raise
        except Exception:
            # A malformed config or one unexpected scheduler error must not
            # permanently kill the background loop.
            logger.exception("Scheduler tick failed; retrying on next interval")
        await asyncio.sleep(tick_interval)


async def tick_once(
    schedule_service: ScheduleService,
    task_runner: TaskRunner,
    get_tasks_root: Callable[[], Path],
) -> None:
    """Fires every enabled schedule whose next_run_at has passed.

    A missing target task (deleted after the schedule was created) is
    recorded as ``task_not_found`` rather than raised, so one bad schedule
    can't take down the loop for every other schedule.
    """
    now = time.time()
    schedules = await asyncio.to_thread(schedule_service.list_schedules)
    for record in schedules:
        try:
            if not record.get("enabled"):
                continue
            next_run_at = record.get("next_run_at")
            if next_run_at is None or next_run_at > now:
                continue

            workspace = record.get("workspace")
            if not isinstance(workspace, str) or not workspace:
                await asyncio.to_thread(
                    schedule_service.record_run,
                    record["id"],
                    "workspace_required",
                )
                continue

            try:
                registered_workspace = await asyncio.to_thread(
                    resolve_registered_workspace,
                    schedule_service.config_service,
                    workspace,
                )
            except WorkspaceNotRegisteredError:
                await asyncio.to_thread(
                    schedule_service.record_run,
                    record["id"],
                    "workspace_unregistered",
                )
                continue
            except WorkspaceResolutionError as exc:
                await asyncio.to_thread(
                    schedule_service.record_run,
                    record["id"],
                    f"workspace_invalid: {exc}",
                )
                continue
            except WorkspaceConfigError as exc:
                await asyncio.to_thread(
                    schedule_service.record_run,
                    record["id"],
                    f"workspace_config_error: {exc}",
                )
                continue

            tasks_root = get_tasks_root()
            task_exists = await asyncio.to_thread(
                lambda: (
                    TaskService(tasks_root).get_task(record["task_name"]) is not None
                )
            )
            if not task_exists:
                await asyncio.to_thread(
                    schedule_service.record_run, record["id"], "task_not_found"
                )
                continue

            try:
                status = await asyncio.to_thread(
                    task_runner.run_task,
                    record["task_name"],
                    record["engine"],
                    registered_workspace.group,
                    tasks_root=tasks_root,
                    workspace=registered_workspace.path,
                    prevent_overlap=True,
                )
            except TaskAlreadyRunningError:
                await asyncio.to_thread(
                    schedule_service.record_run,
                    record["id"],
                    "skipped: already_running",
                )
                continue
            result_status = getattr(status, "status", "running")
            if result_status == "running":
                recorded_status = "started"
            elif str(result_status).startswith("failed"):
                recorded_status = str(result_status)
            elif result_status in ("completed", "success"):
                recorded_status = str(result_status)
            else:
                recorded_status = f"failed: {result_status}"
            await asyncio.to_thread(
                schedule_service.record_run,
                record["id"],
                recorded_status,
            )
        except ValueError as exc:
            await asyncio.to_thread(
                schedule_service.record_run, record["id"], f"failed: {exc}"
            )
        except Exception as exc:
            logger.exception("Schedule %s failed", record.get("id"))
            try:
                await asyncio.to_thread(
                    schedule_service.record_run,
                    record["id"],
                    f"failed: {exc}",
                )
            except Exception:
                logger.exception("Could not persist schedule failure")

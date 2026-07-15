from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Callable

from core.services.runner_service import TaskRunner
from core.services.schedule_service import ScheduleService
from core.services.task_service import TaskService

TICK_INTERVAL_SECONDS = 30.0


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
        await tick_once(schedule_service, task_runner, get_tasks_root)
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
        if not record.get("enabled"):
            continue
        next_run_at = record.get("next_run_at")
        if next_run_at is None or next_run_at > now:
            continue

        tasks_root = get_tasks_root()
        task_exists = await asyncio.to_thread(
            lambda r=record, rt=tasks_root: TaskService(rt).get_task(r["task_name"])
            is not None
        )
        if not task_exists:
            await asyncio.to_thread(
                schedule_service.record_run, record["id"], "task_not_found"
            )
            continue

        try:
            await asyncio.to_thread(
                task_runner.run_task,
                record["task_name"],
                record["engine"],
                record["group"],
                tasks_root=tasks_root,
            )
            await asyncio.to_thread(
                schedule_service.record_run, record["id"], "started"
            )
        except ValueError as exc:
            await asyncio.to_thread(
                schedule_service.record_run, record["id"], f"failed: {exc}"
            )

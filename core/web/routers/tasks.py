from fastapi import APIRouter, HTTPException
from core.services.task_service import TaskService
from core.web.resource_paths import resolve_resource_path

router = APIRouter(prefix="/api")


def get_tasks_root():
    return resolve_resource_path("tasks", "CA_TASKS_ROOT")


@router.get("/tasks")
async def list_tasks():
    return TaskService(get_tasks_root()).list_tasks()


@router.get("/tasks/{name}")
async def get_task(name: str):
    task = TaskService(get_tasks_root()).get_task(name)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task

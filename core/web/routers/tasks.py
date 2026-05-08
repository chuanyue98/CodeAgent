import os
from fastapi import APIRouter
from pathlib import Path
from core.services.task_service import TaskService

router = APIRouter(prefix="/api")


def get_root_dir():
    env_path = os.environ.get("CA_ROOT_DIR")
    if env_path:
        return Path(env_path)
    return Path(__file__).resolve().parent.parent.parent.parent


@router.get("/task")
async def get_task_status():
    service = TaskService(get_root_dir())
    return service.get_plan_status()

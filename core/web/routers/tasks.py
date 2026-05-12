from fastapi import APIRouter, HTTPException, Query
from core.services.task_service import TaskService
from core.services.config_service import ConfigService
from core.services.skill_service import SkillService
from core.web.resource_paths import resolve_resource_path
from core.web.routers.config import get_config_path

router = APIRouter(prefix="/api")


def get_tasks_root():
    return resolve_resource_path("tasks", "CA_TASKS_ROOT")


@router.get("/tasks")
async def list_tasks():
    return TaskService(get_tasks_root()).list_tasks()


@router.get("/tasks/{name}")
async def get_task(name: str, group: str = Query(None)):
    task = TaskService(get_tasks_root()).get_task(name)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    if group:
        config_service = ConfigService(get_config_path())
        config, _ = config_service.get_config()
        group_def = config.get("groups", {}).get(group, {})

        # Resolve skills and their scripts
        skills_root = resolve_resource_path("skills", "CA_SKILLS_ROOT")
        skill_service = SkillService(skills_root)
        detailed_skills = skill_service.get_detailed_skills()

        task_skills = []
        group_skills_set = set(group_def.get("skills", []))
        for category in detailed_skills:
            for skill in detailed_skills[category]:
                if skill["id"] in group_skills_set:
                    task_skills.append(skill)

        task["resolved_skills"] = task_skills
        task["resolved_prompts"] = group_def.get("prompts", [])

    return task

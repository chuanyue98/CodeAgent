from fastapi import APIRouter, HTTPException, Query, Body
from core.services.task_service import TaskService
from core.services.config_service import ConfigService
from core.services.skill_service import SkillService
from core.services.runner_service import TaskRunner
from core.web.resource_paths import ROOT_DIR, resolve_resource_path
from core.web.routers.config import get_config_path

router = APIRouter(prefix="/api")

# Singleton runner for the session
_runner = TaskRunner(ROOT_DIR)


def get_tasks_root():
    return resolve_resource_path("tasks", "CA_TASKS_ROOT")


@router.get("/tasks")
async def list_tasks():
    return TaskService(get_tasks_root()).list_tasks()


@router.get("/tasks/runs")
async def list_runs():
    """Lists all background task runs."""
    return _runner.list_runs()


@router.get("/tasks/runs/{task_id}")
async def get_run_status(task_id: str):
    """Retrieves the status of a specific background task run, including real-time progress."""
    status = _runner.get_status(task_id)
    if not status:
        raise HTTPException(status_code=404, detail="Run not found")

    # Enrich with latest task data
    task_name = task_id.rsplit("_", 1)[0]
    task_service = TaskService(get_tasks_root())
    task_data = task_service.get_task(task_name, log_path=status.log_path)

    return {"status": status, "progress": task_data}


@router.post("/tasks/runs/{task_id}/stop")
async def stop_run(task_id: str):
    """Stops a running background task."""
    success = _runner.stop_task(task_id)
    return {"success": success}


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


@router.post("/tasks/{name}/run")
async def run_task(
    name: str,
    engine: str = Body(..., embed=True),
    group: str = Body("common", embed=True),
):
    """Launches a task in the background with the selected engine."""
    task_service = TaskService(get_tasks_root())
    if task_service.get_task(name) is None:
        raise HTTPException(status_code=404, detail="Task not found")
    try:
        return _runner.run_task(name, engine, group, tasks_root=get_tasks_root())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/engines")
async def list_engines():
    """Lists available AI engines.

    ``supportsResume`` reflects ChatPage's ability to continue an existing
    session with prior context intact, verified live per engine — see
    docs/chatpage-cli-spike-results.md. Gemini's individual-tier Code Assist
    client is currently sunset (``IneligibleTierError``), so its resume path
    was never confirmed and stays disabled here rather than assumed.
    """
    # This could be more dynamic by checking shutil.which for binaries
    return [
        {
            "id": "gemini",
            "name": "Gemini CLI",
            "description": "Google AI Engineering Driver",
            "supportsResume": False,
        },
        {
            "id": "claude",
            "name": "Claude Code",
            "description": "Anthropic High-Reasoning Driver",
            "supportsResume": True,
        },
        {
            "id": "opencode",
            "name": "OpenCode AI",
            "description": "Local npm CLI with TUI",
            "supportsResume": True,
        },
        {
            "id": "codex",
            "name": "OpenAI Codex",
            "description": "OpenAI Engineering Driver",
            "supportsResume": True,
        },
    ]

from fastapi import APIRouter, Body, HTTPException, Query

from core.constants import ENGINES
from core.services.config_service import ConfigService
from core.services.runner_service import TaskAlreadyRunningError, TaskRunner
from core.services.skill_service import SkillService
from core.services.task_service import TaskService, is_valid_task_name
from core.services.workspace_service import (
    RegisteredWorkspace,
    WorkspaceConfigError,
    WorkspaceResolutionError,
)
from core.services.workspace_service import (
    resolve_registered_workspace as resolve_workspace,
)
from core.web.resource_paths import ROOT_DIR, resolve_resource_path
from core.web.routers.config import get_config_path

router = APIRouter(prefix="/api")

# Singleton runner for the session
_runner = TaskRunner(ROOT_DIR)


def get_tasks_root():
    return resolve_resource_path("tasks", "CA_TASKS_ROOT")


def resolve_registered_workspace(workspace: str) -> RegisteredWorkspace:
    """Resolve a workspace and require it to be in the project registry."""
    try:
        return resolve_workspace(ConfigService(get_config_path()), workspace)
    except WorkspaceConfigError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except WorkspaceResolutionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/tasks")
async def list_tasks():
    return TaskService(get_tasks_root()).list_tasks()


@router.post("/tasks")
async def create_task(
    name: str = Body(..., embed=True),
    title: str = Body(..., embed=True),
    objective: str = Body("", embed=True),
    context: str = Body("", embed=True),
    instructions: str = Body("", embed=True),
    verification: str = Body("", embed=True),
):
    """Creates a new task blueprint as a plain markdown file in tasks/."""
    try:
        return TaskService(get_tasks_root()).create_task(
            name, title, objective, context, instructions, verification
        )
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


_GENERATE_TASK_PROMPT = """你是 CodeAgent 的任务编排专家 (Task Authoring)。请把用户下面描述的自动化任务整理成规范剧本，
直接创建文件 tasks/{name}.md（相对当前工作目录的路径，不要询问确认，直接写入）。

文件要求：
- 第一行是一级标题：# {title}
- 之后依次包含四个二级标题板块，标题文字必须完全一致：
  ## Objective (目标)
  ## Context (背景)
  ## Instructions (指令)
  ## Verification (验证)
- 每个板块下面写清楚具体、可执行的内容，不要留空，不要额外发挥需求之外的范围。

用户的任务需求描述：
{description}

写完文件后，用一句话简要说明你写了什么，不要输出文件全文。"""


@router.post("/tasks/generate")
async def generate_task(
    engine: str = Body(..., embed=True),
    name: str = Body(..., embed=True),
    title: str = Body(..., embed=True),
    description: str = Body(..., embed=True),
):
    """Runs a headless engine turn that authors tasks/<name>.md itself.

    Mirrors ``ca new``'s task-authoring flow (an AI agent writes the file
    directly with its own tools) instead of taking pre-filled section text,
    but reuses the already-hardened one-shot ChatPage pipeline
    (``build_chat_command``) rather than the interactive-oriented CLI path.
    """
    if engine not in ENGINES:
        raise HTTPException(status_code=400, detail=f"Invalid engine: {engine!r}")
    if not is_valid_task_name(name):
        raise HTTPException(status_code=400, detail="Task name must match [\\w.-]+")

    tasks_root = get_tasks_root()
    tasks_root.mkdir(parents=True, exist_ok=True)
    path = tasks_root / f"{name}.md"
    if not path.resolve().is_relative_to(tasks_root.resolve()):
        raise HTTPException(status_code=400, detail="Invalid task name")
    try:
        # Exclusive-create ("x") reserves the filename atomically so a second
        # concurrent /api/tasks/generate call for the same name fails fast
        # instead of racing the exists()-then-write TOCTOU window. The
        # background agent overwrites this empty placeholder with real
        # content using its own (non-exclusive) file write tools.
        with path.open("x", encoding="utf-8"):
            pass
    except FileExistsError as exc:
        raise HTTPException(
            status_code=409, detail=f"Task '{name}' already exists"
        ) from exc

    message = _GENERATE_TASK_PROMPT.format(
        name=name, title=title, description=description.strip()
    )
    try:
        status = _runner.run_chat_turn(
            engine, message, group="codeagent", project_path=str(ROOT_DIR)
        )
    except ValueError as exc:
        # Dispatch failed synchronously, before any agent could have started
        # writing the file: release the reserved name instead of leaving a
        # dangling empty placeholder that would 409 all future retries.
        path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return status.__dict__


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
    workspace: str = Body(..., embed=True),
):
    """Launches a task in the background with the selected engine."""
    task_service = TaskService(get_tasks_root())
    if task_service.get_task(name) is None:
        raise HTTPException(status_code=404, detail="Task not found")
    resolved_workspace = resolve_registered_workspace(workspace)
    try:
        return _runner.run_task(
            name,
            engine,
            resolved_workspace.group,
            tasks_root=get_tasks_root(),
            workspace=resolved_workspace.path,
            prevent_overlap=True,
        )
    except TaskAlreadyRunningError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/engines")
async def list_engines():
    """Lists available AI engines.

    ``supportsResume`` reflects ChatPage's ability to continue an existing
    session with prior context intact, verified live per engine — see
    docs/chatpage-cli-spike-results.md.
    """
    # This could be more dynamic by checking shutil.which for binaries
    return [
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
        {
            "id": "codebuddy",
            "name": "CodeBuddy Code",
            "description": "Tencent Engineering Driver",
            "supportsResume": True,
        },
    ]

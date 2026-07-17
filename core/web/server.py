import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from core.prompt_scanner import DEFAULT_GROUP_PROMPTS, PromptScanner
from core.skill_scanner import SkillScanner
from core.plugin_scanner import PluginScanner
from core.services.config_service import ConfigService
from core.services.schedule_service import ScheduleService
from core.services.scheduler_loop import scheduler_tick_loop
from core.web.routers import (
    agent,
    analytics,
    chat,
    config,
    history,
    hooks,
    launch,
    logs,
    mcp,
    plugins,
    prompts,
    schedules,
    skills,
    system,
    tasks,
)
from core.web.routers.config import get_config_path
from core.web.routers.tasks import _runner as _task_runner, get_tasks_root
from core.web.resource_paths import resolve_resource_path

CONFIG_PATH = get_config_path()
FRONTEND_DIST = resolve_resource_path("web/frontend/dist", "CA_FRONTEND_DIST")


def _get_roots():
    return (
        resolve_resource_path("skills", "CA_SKILLS_ROOT"),
        resolve_resource_path("prompt", "CA_PROMPTS_ROOT"),
        resolve_resource_path("hooks", "CA_HOOKS_ROOT"),
    )


# Default group → skill category mapping
DEFAULT_GROUP_CATEGORIES: dict[str, list[str]] = {
    "codeagent": ["base", "self-optimize"],
    "work": ["base", "devops", "toolbox"],
    "web": ["base", "web"],
    "common": ["base"],
}


def initialize_default_groups() -> None:
    """Seed config.json['groups'] with scanned defaults for any group not yet configured.

    Uses ``ConfigService.modify_config`` for an atomic read-modify-write so
    that concurrent scheduler / web-request writes don't clobber each other.
    """
    config_service = ConfigService(CONFIG_PATH)

    def _modifier(config_data: dict) -> dict:
        skills_root, prompts_root, hooks_root = _get_roots()
        groups: dict = config_data.get("groups", {})
        skill_scanner = SkillScanner(skills_root)
        scanned_skills, _ = skill_scanner.scan()
        prompt_scanner = PromptScanner(prompts_root)
        scanned_prompts, _ = prompt_scanner.scan()

        plugin_scanner = PluginScanner(
            resolve_resource_path("plugins", "CA_PLUGINS_ROOT")
        )
        scanned_plugins, _ = plugin_scanner.scan()

        changed = False
        for group_name, categories in DEFAULT_GROUP_CATEGORIES.items():
            prompt_defaults = [
                prompt_group
                for prompt_group in DEFAULT_GROUP_PROMPTS.get(group_name, [])
                if prompt_group in scanned_prompts
            ]
            if group_name not in groups:
                skills_list = [
                    f"{cat}/{skill}"
                    for cat in categories
                    for skill in scanned_skills.get(cat, [])
                ]
                plugins_list = [
                    f"{cat}/{plugin}"
                    for cat in categories
                    for plugin in scanned_plugins.get(cat, [])
                ]
                groups[group_name] = {
                    "skills": skills_list,
                    "prompts": prompt_defaults,
                    "hooks": [],
                    "plugins": plugins_list,
                }
                changed = True
                print(
                    f"✅ Initialized group '{group_name}' with {len(skills_list)} skills"
                )

            else:
                if "prompts" not in groups[group_name]:
                    groups[group_name]["prompts"] = prompt_defaults
                    changed = True

                if "plugins" not in groups[group_name]:
                    groups[group_name]["plugins"] = []
                    changed = True

        if changed:
            config_data["groups"] = groups

        return config_data

    try:
        config_service.modify_config(_modifier)
    except Exception:
        pass  # config file may not exist yet — silently skip


@asynccontextmanager
async def lifespan(app: FastAPI):
    initialize_default_groups()
    from core.services.agent_adapters.base import AgentAdapter
    from core.services.agent_adapters.claude import ClaudeAdapter
    from core.services.agent_adapters.codex import CodexAdapter
    from core.services.agent_adapters.fake import FakeAgentAdapter
    from core.services.agent_adapters.opencode import OpenCodeAdapter
    from core.services.agent_gateway import AgentGateway
    from core.services.agent_store import AgentStore

    agent_db = os.environ.get(
        "CA_AGENT_DB", str(Path.home() / ".codeagent" / "agent-gateway.sqlite3")
    )
    adapters: list[AgentAdapter] = (
        [FakeAgentAdapter()]
        if os.environ.get("CA_AGENT_GATEWAY_FAKE") == "1"
        else [CodexAdapter(), ClaudeAdapter(), OpenCodeAdapter()]
    )
    agent_gateway = AgentGateway(
        AgentStore(agent_db),
        get_config_path(),
        adapters,
    )
    app.state.agent_gateway = agent_gateway
    await agent_gateway.start()
    schedule_service = ScheduleService(ConfigService(get_config_path()))
    scheduler_task = asyncio.create_task(
        scheduler_tick_loop(schedule_service, _task_runner, get_tasks_root)
    )
    yield
    scheduler_task.cancel()
    try:
        await scheduler_task
    except asyncio.CancelledError:
        pass

    await agent_gateway.stop()
    app.state.agent_gateway = None

    # Clean up background subprocesses
    from core.web.routers.chat import _runner as chat_runner
    from core.web.routers.tasks import _runner as tasks_runner

    try:
        chat_runner.kill_all()
    except Exception:
        pass
    try:
        tasks_runner.kill_all()
    except Exception:
        pass


app = FastAPI(title="CodeAgent Web UI", lifespan=lifespan)

# Mount modular routers
app.include_router(agent.router)
app.include_router(analytics.router)
app.include_router(chat.router)
app.include_router(config.router)
app.include_router(history.router)
app.include_router(hooks.router)
app.include_router(launch.router)
app.include_router(logs.router)
app.include_router(mcp.router)
app.include_router(plugins.router)
app.include_router(prompts.router)
app.include_router(schedules.router)
app.include_router(skills.router)
app.include_router(system.router)
app.include_router(tasks.router)

# E2E-only reset endpoint — mounted exclusively when CA_E2E=1 so the
# production app never exposes it. See core/web/routers/e2e.py.
if os.environ.get("CA_E2E") == "1":
    from core.web.routers import e2e

    app.include_router(e2e.router)


@app.get("/api/health")
async def health_check():
    return {"status": "ok"}


if not FRONTEND_DIST.exists():

    @app.get("/", include_in_schema=False)
    async def api_root():
        return {
            "name": "CodeAgent Web UI API",
            "status": "ok",
            "ui": "http://127.0.0.1:5173",
            "health": "/api/health",
        }


else:
    from fastapi.responses import FileResponse

    assets_dir = FRONTEND_DIST / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(full_path: str):
        if full_path == "api" or full_path.startswith("api/"):
            from fastapi import HTTPException

            raise HTTPException(status_code=404, detail="API route not found")
        return FileResponse(FRONTEND_DIST / "index.html")

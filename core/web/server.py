import json
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles

from core.prompt_scanner import DEFAULT_GROUP_PROMPTS, PromptScanner
from core.skill_scanner import SkillScanner
from core.plugin_scanner import PluginScanner
from core.web.routers import (
    analytics,
    config,
    hooks,
    launch,
    plugins,
    prompts,
    skills,
    tasks,
)
from core.web.resource_paths import ROOT_DIR, resolve_resource_path

CONFIG_PATH = ROOT_DIR / "config.json"
FRONTEND_DIST = ROOT_DIR / "web" / "frontend" / "dist"


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
    """Seed config.json['groups'] with scanned defaults for any group not yet configured."""
    if not CONFIG_PATH.exists():
        return
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8-sig") as f:
            config_data = json.load(f)
    except Exception:
        return

    skills_root, prompts_root, hooks_root = _get_roots()
    groups: dict = config_data.get("groups", {})
    skill_scanner = SkillScanner(skills_root)
    scanned_skills, _ = skill_scanner.scan()
    prompt_scanner = PromptScanner(prompts_root)
    scanned_prompts, _ = prompt_scanner.scan()

    plugin_scanner = PluginScanner(resolve_resource_path("plugins", "CA_PLUGINS_ROOT"))
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
            print(f"✅ Initialized group '{group_name}' with {len(skills_list)} skills")

        else:
            if "prompts" not in groups[group_name]:
                groups[group_name]["prompts"] = prompt_defaults
                changed = True

            if "plugins" not in groups[group_name]:
                groups[group_name]["plugins"] = []
                changed = True

    if changed:
        config_data["groups"] = groups
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(config_data, f, indent=2, ensure_ascii=False)


@asynccontextmanager
async def lifespan(app: FastAPI):
    initialize_default_groups()
    yield


def create_app(frontend_dist: Path = FRONTEND_DIST) -> FastAPI:
    app = FastAPI(title="CodeAgent Web UI", lifespan=lifespan)

    # Mount modular routers
    app.include_router(analytics.router)
    app.include_router(config.router)
    app.include_router(hooks.router)
    app.include_router(launch.router)
    app.include_router(plugins.router)
    app.include_router(prompts.router)
    app.include_router(skills.router)
    app.include_router(tasks.router)

    @app.get("/api/health")
    async def health_check():
        return {"status": "ok"}

    if not frontend_dist.exists():

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

        assets_dir = frontend_dist / "assets"
        if assets_dir.exists():
            app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

        @app.get("/{full_path:path}", include_in_schema=False)
        async def serve_spa(full_path: str):
            if full_path == "api" or full_path.startswith("api/"):
                raise HTTPException(status_code=404, detail="Not Found")
            return FileResponse(frontend_dist / "index.html")

    return app


app = create_app()

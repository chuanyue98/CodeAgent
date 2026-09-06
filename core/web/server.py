import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.staticfiles import StaticFiles

from core.logging_config import configure_root_logging, get_logger
from core.plugin_scanner import PluginScanner
from core.prompt_scanner import DEFAULT_GROUP_PROMPTS, PromptScanner
from core.services.config_service import ConfigService
from core.services.schedule_service import ScheduleService
from core.services.scheduler_loop import scheduler_tick_loop
from core.skill_scanner import SkillScanner
from core.web.resource_paths import resolve_resource_path
from core.web.routers import (
    agent,
    analytics,
    chat,
    config,
    history,
    hooks,
    instances,
    logs,
    mcp,
    plugins,
    prompts,
    pty,
    schedules,
    skills,
    system,
    tasks,
)
from core.web.routers.config import get_config_path
from core.web.routers.tasks import _runner as _task_runner
from core.web.routers.tasks import get_tasks_root
from core.web.security import HostHeaderMiddleware, require_token

configure_root_logging()

logger = get_logger(__name__)

CONFIG_PATH = get_config_path()
FRONTEND_DIST = resolve_resource_path("web/frontend/dist", "CA_FRONTEND_DIST")


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() not in {"0", "false", "no", "off"}


def get_agent_gateway_settings(config: dict) -> dict:
    # The Agent Gateway (programmatic per-provider adapters behind REST/WS)
    # is an EXPERIMENTAL subsystem: its primary web UI was retired when the
    # streaming terminal became the single conversation surface, and the
    # launch path (engines/start_*.py) is the product's main adapter stack.
    # So the gateway now defaults OFF (AUDIT-001); enable it explicitly with
    # CA_AGENT_GATEWAY_ENABLED=1 or "agent_gateway": {"enabled": true}.
    raw = config.get("agent_gateway", {})
    provider_config = raw.get("providers", {})
    providers = {
        name: _env_bool(
            f"CA_AGENT_PROVIDER_{name.upper()}",
            bool(provider_config.get(name, True)),
        )
        for name in ("codex", "claude", "opencode", "codebuddy")
    }
    return {
        "enabled": _env_bool(
            "CA_AGENT_GATEWAY_ENABLED", bool(raw.get("enabled", False))
        ),
        "legacyFallback": _env_bool(
            "CA_AGENT_LEGACY_FALLBACK", bool(raw.get("legacy_fallback", True))
        ),
        "providers": providers,
    }


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
        # Whether this config has ever been seeded, as opposed to which
        # groups happen to exist right now. Keying the decision on presence
        # made every deletion temporary: remove a template group in Settings
        # and the next server start silently rebuilt it, with no way to say
        # "I do not want this one".
        first_run = "groups" not in config_data
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
            if first_run and group_name not in groups:
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
                logger.info(
                    "Initialized group '%s' with %d skills",
                    group_name,
                    len(skills_list),
                )

            # Deliberately `elif ... in groups` rather than a bare `else`:
            # after the first run a deleted template group reaches here and
            # must stay deleted, not be back-filled key by key.
            elif group_name in groups:
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
    except FileNotFoundError:
        # Genuinely expected before the first run writes a config.
        logger.debug("No config at %s yet; skipping group seeding", CONFIG_PATH)
    except Exception:
        # Everything else was being swallowed by the same handler, so a
        # permission error, a corrupt config or a bug in _modifier all looked
        # identical to "no config yet" -- the server came up with no groups
        # and nothing said why. Startup still continues; the UI degrades to
        # an empty group list rather than failing to boot.
        logger.exception("Failed to seed default groups from %s", CONFIG_PATH)


async def _prewarm_session_history() -> None:
    """Pays the first full history scan before anyone asks for it.

    The sessions list joins analytics usage against the parsed engine history.
    Both are memoized, but the first caller to touch them walks every engine's
    history -- seconds on a machine with a real backlog. Doing it here makes
    that caller startup rather than whoever opens the terminal or Activity
    first.
    """

    def _scan() -> None:
        from core.analytics.service import get_analytics_data
        from core.session_history.session_finder import find_all_sessions

        get_analytics_data()
        find_all_sessions()

    try:
        await asyncio.to_thread(_scan)
    except asyncio.CancelledError:
        raise
    except Exception:
        # A prewarm is an optimisation: the endpoints redo this work on demand
        # and report their own failures, so a broken history must not keep the
        # server from coming up.
        logger.exception("Failed to prewarm session history")


@asynccontextmanager
async def lifespan(app: FastAPI):
    initialize_default_groups()
    # Retention sweep walks the log dir, so it belongs to server startup rather
    # than to TaskRunner's constructor, which the CLI also builds for read-only
    # commands. Off the event loop: it stats every log file in the directory.
    await asyncio.to_thread(_task_runner.prune_old_runs)
    # 浏览器终端的 tmux server：清掉上次异常退出残留的会话（正常关闭时
    # lifespan 自己会 kill-server），避免引擎进程孤儿化。
    await asyncio.to_thread(pty.kill_tmux_server)
    from core.services.agent_adapters.base import AgentAdapter
    from core.services.agent_adapters.claude import ClaudeAdapter
    from core.services.agent_adapters.codebuddy import CodeBuddyAdapter
    from core.services.agent_adapters.codex import CodexAdapter
    from core.services.agent_adapters.fake import FakeAgentAdapter
    from core.services.agent_adapters.opencode import OpenCodeAdapter
    from core.services.agent_gateway import AgentGateway
    from core.services.agent_store import AgentStore

    agent_db = os.environ.get(
        "CA_AGENT_DB", str(Path.home() / ".codeagent" / "agent-gateway.sqlite3")
    )
    config, _warnings = ConfigService(get_config_path()).get_config()
    gateway_settings = get_agent_gateway_settings(config)
    app.state.agent_gateway_status = gateway_settings
    adapter_factories = {
        "codex": CodexAdapter,
        "claude": ClaudeAdapter,
        "opencode": OpenCodeAdapter,
        "codebuddy": CodeBuddyAdapter,
    }
    adapters: list[AgentAdapter] = []
    if gateway_settings["enabled"]:
        adapters = (
            [FakeAgentAdapter()]
            if os.environ.get("CA_AGENT_GATEWAY_FAKE") == "1"
            else [
                adapter_factories[name]()
                for name, enabled in gateway_settings["providers"].items()
                if enabled
            ]
        )
    agent_gateway = (
        AgentGateway(AgentStore(agent_db), get_config_path(), adapters)
        if gateway_settings["enabled"]
        else None
    )
    app.state.agent_gateway = agent_gateway
    if agent_gateway is not None:
        await agent_gateway.start()
    schedule_service = ScheduleService(ConfigService(get_config_path()))
    scheduler_task = asyncio.create_task(
        scheduler_tick_loop(schedule_service, _task_runner, get_tasks_root)
    )
    prewarm_task = asyncio.create_task(_prewarm_session_history())
    yield
    for task in (scheduler_task, prewarm_task):
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    if agent_gateway is not None:
        await agent_gateway.stop()
    app.state.agent_gateway = None

    # 终端随服务一起收摊：tmux 里的引擎在服务关闭后无人能接回，
    # 留着只会孤儿化地消耗资源。
    await asyncio.to_thread(pty.kill_tmux_server)

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

# Rejects Host headers that aren't this machine, defeating DNS rebinding.
# Applies to every route -- including static assets -- because rebinding
# does not care which path it targets. See core/web/security.py.
app.add_middleware(HostHeaderMiddleware)

# Every /api router requires the local UI token. Deliberately NOT applied
# to /api/health (defined on `app` below, so it is not covered by these
# router-level dependencies), to the SPA fallback, or to /assets: the
# browser has to load index.html before it can read the token out of the
# URL the launcher opened, and /api/health is the launcher's own readiness
# probe.
#
# This covers the WebSocket routes in agent/pty too -- router-level
# dependencies run for WS handshakes as well, which is why require_token
# takes an HTTPConnection rather than a Request. Those two routes *also*
# call verify_websocket() inline: they are the ones that spawn a shell and
# replay whole conversations, so they stay protected even if a future
# refactor mounts their router without these dependencies.
_authenticated = [Depends(require_token)]

app.include_router(agent.router, dependencies=_authenticated)
app.include_router(analytics.router, dependencies=_authenticated)
app.include_router(chat.router, dependencies=_authenticated)
app.include_router(config.router, dependencies=_authenticated)
app.include_router(history.router, dependencies=_authenticated)
app.include_router(hooks.router, dependencies=_authenticated)
app.include_router(instances.router, dependencies=_authenticated)
app.include_router(logs.router, dependencies=_authenticated)
app.include_router(mcp.router, dependencies=_authenticated)
app.include_router(plugins.router, dependencies=_authenticated)
app.include_router(prompts.router, dependencies=_authenticated)
app.include_router(pty.router, dependencies=_authenticated)
app.include_router(schedules.router, dependencies=_authenticated)
app.include_router(skills.router, dependencies=_authenticated)
app.include_router(system.router, dependencies=_authenticated)
app.include_router(tasks.router, dependencies=_authenticated)

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
        # Hashed /assets chunks can be cached forever, but index.html must
        # always revalidate: it is the only thing that points at the current
        # chunk names, and a stale cached copy keeps serving the previous
        # build's chunks after a rebuild (they may still be in cache too),
        # which looks exactly like "the rebuild changed nothing".
        return FileResponse(
            FRONTEND_DIST / "index.html",
            headers={
                "Cache-Control": "no-cache",
            },
        )

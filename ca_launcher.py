#!/usr/bin/env python3
import json
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import click

from core.console import configure_console_encoding
from core.constants import ENGINES
from core.i18n import ENV_VAR as CA_LANG_ENV
from core.i18n import resolve_language, t
from core.logging_config import configure_root_logging
from core.resource_locator import (
    CODE_ROOT,
    get_bundled_resource_root,
    get_default_config_path,
    seed_config_if_missing,
)
from core.services.config_service import ConfigService

UI_API_PORT = 8524
UI_DEV_SERVER_HOST = "127.0.0.1"
UI_DEV_SERVER_PORT = 5173
UI_DEV_SERVER_START_TIMEOUT = 15
_ui_dev_process: subprocess.Popen | None = None

configure_console_encoding()
configure_root_logging()


def _installed_root():
    return CODE_ROOT


def _looks_like_project_root(path: Path):
    return (
        (path / "pyproject.toml").exists()
        and (path / "core").is_dir()
        and (path / "engines").is_dir()
        and (path / "web" / "frontend" / "package.json").exists()
    )


def _project_root():
    try:
        cwd = Path.cwd().resolve()
    except OSError:
        # The working directory was removed/unmounted out from under this
        # process -- fall back to the installed location instead of crashing.
        return _installed_root()
    for candidate in (cwd, *cwd.parents):
        if _looks_like_project_root(candidate):
            return candidate
    return _installed_root()


def load_config():
    root = _project_root()
    config_path = get_default_config_path(root)
    default_config = {
        "default_mode": "local",
        # "auto" defers to the OS locale; "en"/"zh" pin it. See core/i18n.py.
        "language": "auto",
        "proxy": {"host": "127.0.0.1", "port": 1087},
    }
    if config_path.exists():
        try:
            with open(config_path, encoding="utf-8-sig") as f:
                return {**default_config, **json.load(f)}
        except Exception as e:
            print(t("config.load_failed", error=e))
    return default_config


def is_tcp_port_open(host, port, timeout=0.3):
    try:
        with socket.create_connection((host, int(port)), timeout=timeout):
            return True
    except OSError:
        return False


def find_available_port(start_port=8524):
    port = start_port
    while port < 9000:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
        port += 1
    return start_port


def _is_ui_dev_server_running(host=UI_DEV_SERVER_HOST, port=UI_DEV_SERVER_PORT):
    return is_tcp_port_open(host, port, timeout=0.2)


def _frontend_root():
    root = _project_root()
    source_frontend = root / "web" / "frontend"
    if source_frontend.exists():
        return source_frontend
    return get_bundled_resource_root(root) / "web" / "frontend"


def _frontend_dist_exists():
    return (_frontend_root() / "dist" / "index.html").exists()


def _frontend_source_exists():
    frontend_root = _frontend_root()
    return (frontend_root / "package.json").exists() and (
        frontend_root / "src"
    ).exists()


def _ui_dev_server_command():
    """Return the command to start the Vite dev server via bun (preferred) or npm (fallback)."""
    bun_cmd = shutil.which("bun")
    if bun_cmd:
        return [
            bun_cmd,
            "run",
            "dev",
            "--",
            "--host",
            UI_DEV_SERVER_HOST,
            "--port",
            str(UI_DEV_SERVER_PORT),
        ]

    # Fallback to npm if bun is not installed
    if sys.platform == "win32":
        npm_cmd = shutil.which("npm.cmd") or shutil.which("npm")
    else:
        npm_cmd = shutil.which("npm")
    if not npm_cmd:
        return None
    return [
        npm_cmd,
        "run",
        "dev",
        "--",
        "--host",
        UI_DEV_SERVER_HOST,
        "--port",
        str(UI_DEV_SERVER_PORT),
    ]


def _start_ui_dev_server():
    global _ui_dev_process
    if _is_ui_dev_server_running():
        return True

    if not _frontend_source_exists():
        return False

    cmd = _ui_dev_server_command()
    if not cmd:
        return False

    frontend_root = _frontend_root()
    _ui_dev_process = subprocess.Popen(  # noqa: S603
        cmd,
        cwd=str(frontend_root),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        start_new_session=True,
        env=os.environ.copy(),
    )

    deadline = time.time() + UI_DEV_SERVER_START_TIMEOUT
    while time.time() < deadline:
        if _is_ui_dev_server_running():
            return True
        time.sleep(0.25)
    _stop_ui_dev_server()
    return False


def _stop_ui_dev_server() -> None:
    """Stop only the Vite process started by this invocation."""
    global _ui_dev_process
    process = _ui_dev_process
    _ui_dev_process = None
    if process is None or process.poll() is not None:
        return
    try:
        process.terminate()
        process.wait(timeout=2)
    except (OSError, subprocess.TimeoutExpired):
        try:
            process.kill()
        except OSError:
            pass


def _can_open_browser():
    if sys.platform.startswith(("win", "darwin")):
        return True
    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def _open_browser(url):
    if not _can_open_browser():
        print(t("ui.open_in_browser", url=url))
        return False

    import webbrowser

    if not webbrowser.open(url):
        print(t("ui.open_in_browser", url=url))
        return False
    return True


def _wait_for_api_then_open_browser(api_host, api_port, url):
    """Opens the browser only once the Web UI API is actually accepting
    connections, in a background thread so it doesn't delay uvicorn.run().

    Opening the browser right before uvicorn.run() (the previous behavior)
    raced uvicorn's own startup -- mounting 16+ routers and binding the
    socket takes long enough that the very first page load routinely hit
    nothing yet listening, surfacing as a connection error or (behind a
    local proxy) a 502 that only cleared once the user manually refreshed.
    This applies in both dev-server and built-UI mode: even when the
    browser's URL points at the Vite dev server, that page's first API
    calls are proxied straight to this same API port, so it's what
    actually needs to be ready either way.
    """
    deadline = time.time() + UI_DEV_SERVER_START_TIMEOUT
    while time.time() < deadline:
        if is_tcp_port_open(api_host, api_port, timeout=0.2):
            break
        time.sleep(0.1)
    _open_browser(url)


def _extract_proxy_candidates(proxy_cfg):
    if isinstance(proxy_cfg, list):
        return [
            (e.get("host", "127.0.0.1"), int(e["port"]))
            for e in proxy_cfg
            if isinstance(e, dict) and "port" in e
        ]
    if not isinstance(proxy_cfg, dict):
        # A malformed config.json (e.g. "proxy": true from a typo) must fall
        # back to the defaults below rather than crash with an AttributeError.
        proxy_cfg = {}
    host = proxy_cfg.get("host", "127.0.0.1")
    port = proxy_cfg.get("port")
    ports = ([int(port)] if port is not None else []) + [3065, 3067, 3066, 1087]
    return list(dict.fromkeys((host, p) for p in ports))


def _select_active_proxy(candidates):
    for host, port in candidates:
        if is_tcp_port_open(host, port):
            return host, port
    return candidates[0] if candidates else ("127.0.0.1", 3065)


def build_proxy_env(config):
    proxy_cfg = config.get("proxy", {})
    candidates = _extract_proxy_candidates(proxy_cfg)
    proxy_host, selected_port = _select_active_proxy(candidates)
    # Karing commonly uses 3066 as SOCKS5-only; 3065/3067 are HTTP proxy ports.
    proxy_scheme = "socks5" if selected_port == 3066 else "http"
    proxy_url = f"{proxy_scheme}://{proxy_host}:{selected_port}"
    child_env = os.environ.copy()
    child_env["HTTP_PROXY"] = proxy_url
    child_env["HTTPS_PROXY"] = proxy_url
    child_env["ALL_PROXY"] = proxy_url
    return child_env, proxy_host, selected_port, proxy_scheme


def run_ui_command():
    try:
        # Ensure project root is in sys.path
        root = _project_root()
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))

        import uvicorn

        from core.web.server import app
    except ModuleNotFoundError as exc:
        missing_module = exc.name or "required dependency"
        print(t("ui.missing_dependency", module=missing_module))
        return 1

    use_dev_server = False
    if os.environ.get("CA_UI_DEV") == "1" and _frontend_source_exists():
        if _is_ui_dev_server_running():
            use_dev_server = True
        else:
            print(
                t(
                    "ui.vite_starting",
                    host=UI_DEV_SERVER_HOST,
                    port=UI_DEV_SERVER_PORT,
                )
            )
            use_dev_server = _start_ui_dev_server()
            if not use_dev_server:
                if _frontend_dist_exists():
                    print(t("ui.vite_failed_fallback"))
                else:
                    print(t("ui.vite_failed_no_dist"))
                    return 1

    if use_dev_server:
        port = UI_API_PORT
        url = f"http://{UI_DEV_SERVER_HOST}:{UI_DEV_SERVER_PORT}"
        print(t("ui.vite_detected", url=url))
        print(t("ui.api_starting", port=port))
    else:
        if not _frontend_dist_exists():
            # This is the very first command most people run after cloning,
            # so spell out the exact copy-pasteable fix instead of naming the
            # tools and leaving the reader to assemble the commands.
            frontend_root = _frontend_root()
            print(
                t(
                    "ui.not_built",
                    index_path=frontend_root / "dist" / "index.html",
                    frontend_root=frontend_root,
                )
            )
            return 1
        port = find_available_port(UI_API_PORT)
        url = f"http://127.0.0.1:{port}"
        print(t("ui.starting", url=url))

    api_host = os.environ.get("CA_UI_HOST", "127.0.0.1")
    threading.Thread(
        target=_wait_for_api_then_open_browser,
        args=(api_host, port, url),
        daemon=True,
    ).start()

    try:
        uvicorn.run(
            app,
            host=api_host,
            port=port,
            log_level="info",
        )
    except KeyboardInterrupt:
        pass
    finally:
        _stop_ui_dev_server()
    return 0


# ============================================================================
# Click CLI
# ============================================================================

EPILOG = """\
Engines: gemini, claude, opencode, codex
         (default: gemini; set "default_engine" in config.json to change)

YOLO mode is enabled by default.

\b
Examples:
  ca                       Start the default engine
  ca claude do something   Start claude with extra args
  ca --proxy gemini        Start gemini with proxy enabled
  ca doctor --fix          Run health check and auto-repair
  ca ui                    Start the Web UI
  ca new my-task           Create a new task draft
  ca ps                    List running background task runs
  ca stop <task_id>        Stop a background task run
  ca batch-run code_review --engine claude --group work
                           Run one task across every registered project in a group
  ca project add . --group work
                           Register the current directory, non-interactively
  ca project list         List every registered project
  ca history list          List sessions (use --engine <name> to filter)
  ca history show <engine> <session_id>
  ca history convert <source_engine> <session_id> <target_engine>
"""


def _reserved_command_can_handle(cmd, parent_ctx, cmd_name, rest):
    """A registered command name (new/doctor/ui/history) can also be the
    start of free-form prompt text, e.g. ``ca new is broken, please fix``.
    Only commit to the subcommand if the remaining tokens actually parse as
    valid arguments (and, for a subgroup like ``history``, name a real
    sub-subcommand) -- otherwise the whole line is an engine launch prompt.

    Returns ``(True, None)`` if ``cmd`` should handle the args, or
    ``(False, error)`` otherwise. ``error`` is ``None`` when the tokens should
    silently fall through to a natural-language engine prompt, or a
    ``click.UsageError`` to raise when a leading ``-``/``--`` token makes it
    clear this was a mistyped option for the reserved command rather than
    prompt text -- e.g. ``ca ui --port 8524`` must report "no such option",
    not silently launch the default engine with "ui --port 8524" as the
    prompt.
    """
    try:
        sub_ctx = cmd.make_context(cmd_name, list(rest), parent=parent_ctx)
    except click.UsageError as exc:
        if rest and rest[0].startswith("-"):
            return False, exc
        return False, None
    if isinstance(cmd, click.Group) and rest:
        first = rest[0]
        if not first.startswith("-") and cmd.get_command(sub_ctx, first) is None:
            return False, None
    return True, None


class CodeAgentGroup(click.Group):
    """Click group that routes non-subcommand arguments to engine launch.

    Registered subcommands (``doctor``, ``ui``, ``history``, ``new``) dispatch
    normally. Any other leading token -- an engine name such as ``gemini`` or
    free-form task text -- falls through to the hidden ``_launch`` command so it
    can be forwarded to the matching engine script.
    """

    def resolve_command(self, ctx, args):
        if args:
            cmd_name = args[0]
            cmd = self.get_command(ctx, cmd_name)
            if cmd is not None:
                handled, error = _reserved_command_can_handle(
                    cmd, ctx, cmd_name, args[1:]
                )
                if handled:
                    return cmd_name, cmd, args[1:]
                if error is not None:
                    raise error
        # Unknown leading token (or a reserved name that doesn't actually
        # parse as that command): forward *all* original args to engine launch.
        launch = self.get_command(ctx, "_launch")
        return "_launch", launch, args


def _ensure_project_on_path(root):
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))


def _is_path_registered(cwd: Path, root: Path, registry: list) -> bool:
    if cwd == root or root in cwd.parents:
        return True
    for item in registry:
        raw_path = item.get("path")
        if not raw_path:
            continue
        try:
            mapping_path = Path(raw_path).resolve()
        except Exception:
            continue
        if cwd == mapping_path or mapping_path in cwd.parents:
            return True
    return False


def _ensure_project_registered(root: Path, config: dict) -> None:
    """Prompt to register the current directory under a resource group if
    it isn't covered by ``project_registry`` yet, then persist the choice.

    Skips the interactive prompt outside a real terminal (scripted/CI
    invocations must not block on ``input()``) or when
    ``CA_SKIP_AUTO_REGISTER`` is set -- but in the non-interactive case still
    prints a one-line, non-blocking hint pointing at ``ca project add``, so
    running unregistered never fails *silently*.
    """
    cwd = Path.cwd().resolve()
    registry = config.get("project_registry", [])
    if _is_path_registered(cwd, root, registry):
        return

    if os.environ.get("CA_SKIP_AUTO_REGISTER"):
        return

    if not sys.stdin.isatty() or not sys.stdout.isatty():
        print(t("project.unregistered_hint", cwd=cwd), file=sys.stderr)
        return

    groups = list(config.get("groups", {}).keys()) or ["common"]
    print(t("project.unregistered_title", cwd=cwd))
    print(t("project.pick_group"))
    for i, g in enumerate(groups, 1):
        print(f"  {i}. {g}")
    print(t("project.new_group_option"))
    print(t("project.skip_option"))

    choice = input("> ").strip().lower()
    if not choice:
        return

    is_new_group = False
    if choice == "n":
        new_name = (
            input(t("project.new_group_prompt")).strip().lower().replace(" ", "-")
        )
        if not new_name:
            print(t("project.no_group_name"))
            return
        chosen_group = new_name
        is_new_group = new_name not in config.get("groups", {})
    else:
        try:
            idx = int(choice) - 1
            if idx < 0:
                raise IndexError
            chosen_group = groups[idx]
        except (ValueError, IndexError):
            print(t("project.invalid_choice"))
            return

    config_path = get_default_config_path(root)
    service = ConfigService(config_path)

    def _modifier(cfg):
        if is_new_group:
            cfg.setdefault("groups", {})[chosen_group] = {
                "skills": [],
                "prompts": [],
                "hooks": [],
                "plugins": [],
            }
        reg = cfg.get("project_registry", [])
        reg.append({"path": str(cwd), "group": chosen_group})
        cfg["project_registry"] = reg
        return cfg

    service.modify_config(_modifier)
    persisted, _ = service.get_config()
    config["project_registry"] = persisted.get("project_registry", [])
    config["groups"] = persisted.get("groups", {})
    print(t("project.registered", group=chosen_group))


FALLBACK_ENGINE = "gemini"


def _resolve_default_engine(config: dict, engine_script_map: dict) -> str:
    """Returns the engine ``ca`` launches when no engine name is given.

    Reads ``default_engine`` from config.json so a claude-first (or
    codex-first) user does not have to name their engine on every single
    invocation. An unrecognized value falls back rather than failing: the
    default engine is not worth aborting a launch over, but it is worth
    saying out loud, since silently starting a different engine than the one
    configured would be its own surprise.
    """
    configured = config.get("default_engine")
    if configured is None:
        return FALLBACK_ENGINE
    name = str(configured).strip().lower()
    if name in engine_script_map:
        return name
    print(
        t(
            "engine.unknown_default",
            value=configured,
            known=", ".join(sorted(engine_script_map)),
            fallback=FALLBACK_ENGINE,
        ),
        file=sys.stderr,
    )
    return FALLBACK_ENGINE


def _launch_engine(ctx, args):
    """Build and run the engine subprocess.

    ``args`` is the list of tokens that follow the (optional) engine name.
    ``--proxy`` / ``-y`` / ``--yolo`` / ``--help`` are only consumed by click
    when they appear *before* the engine name (``allow_interspersed_args``
    is off) -- anywhere else they're literal prompt text passed straight
    through, not flags.

    Returns the launched engine's exit code so it propagates all the way up
    through ``main()`` to ``ca``'s own process exit status.
    """
    obj = ctx.ensure_object(dict)
    child_env = obj.get("child_env")
    engine_script_map = obj["engine_script_map"]

    # Seed here rather than in load_config(): this is the "first launch"
    # doctor's hint used to promise, and it keeps read-only invocations like
    # `ca --help` from writing files as a side effect. Without it, a fresh
    # clone launched with no groups at all and mounted zero skills.
    seeded = seed_config_if_missing(obj["root"])
    if seeded is not None:
        print(t("config.seeded", path=seeded))
        obj["config"] = load_config()

    _ensure_project_registered(obj["root"], obj["config"])

    engine_name = _resolve_default_engine(obj["config"], engine_script_map)
    extra_params = []

    if args:
        first_arg = args[0].lower()
        if first_arg in engine_script_map:
            engine_name = first_arg
            # 后面的全是 extra_params
            extra_params = list(args[1:])
        else:
            # 全部视为 extra_params
            extra_params = list(args)

    # 显式向底层引擎脚本透传 -y
    if "-y" not in extra_params:
        extra_params.append("-y")

    if obj.get("yolo", True):
        print(t("engine.yolo_warning"))

    target_script = engine_script_map[engine_name]
    cmd = [sys.executable, target_script] + extra_params
    return subprocess.run(cmd, env=child_env).returncode


@click.group(
    cls=CodeAgentGroup,
    invoke_without_command=True,
    context_settings=dict(
        ignore_unknown_options=True,
        allow_extra_args=True,
        # False so ``--proxy``/``-y`` are only recognized before the engine
        # name (as documented in EPILOG); a prompt that merely *mentions*
        # one of those words after the engine name must reach the engine
        # verbatim rather than being silently consumed as a real flag.
        allow_interspersed_args=False,
    ),
    epilog=EPILOG,
)
@click.option("--proxy", is_flag=True, help="Enable proxy from config.json")
@click.option(
    "-y",
    "--yolo",
    is_flag=True,
    flag_value=True,
    default=True,
    help="Enable YOLO mode",
)
@click.pass_context
def cli(ctx, proxy, yolo):
    """CodeAgent: Professional AI Engineering Shell."""
    ctx.ensure_object(dict)

    config = load_config()
    root = _project_root()

    engine_script_map = {
        "gemini": str(root / "engines" / "start_gemini.py"),
        "claude": str(root / "engines" / "start_claude_code.py"),
        "opencode": str(root / "engines" / "start_opencode.py"),
        "codex": str(root / "engines" / "start_codex.py"),
    }

    child_env = None
    if proxy:
        child_env, proxy_host, proxy_port, proxy_scheme = build_proxy_env(config)
        print(
            t(
                "proxy.enabled",
                scheme=proxy_scheme,
                host=proxy_host,
                port=proxy_port,
            )
        )

    # Engines run as separate processes and would otherwise re-resolve the
    # language on their own. Pin the launcher's choice so both halves of a
    # session speak the same language even if the config changes mid-run.
    child_env = child_env if child_env is not None else os.environ.copy()
    child_env[CA_LANG_ENV] = resolve_language()

    ctx.obj.update(
        config=config,
        root=root,
        engine_script_map=engine_script_map,
        child_env=child_env,
        proxy=proxy,
        yolo=yolo,
    )

    # No subcommand (and no leading token) -> launch the default engine.
    if ctx.invoked_subcommand is None:
        return _launch_engine(ctx, [])


@cli.command(
    name="_launch",
    hidden=True,
    context_settings=dict(ignore_unknown_options=True, allow_extra_args=True),
)
@click.argument("args", nargs=-1)
@click.pass_context
def _launch(ctx, args):
    """Forward arbitrary arguments to an engine launch."""
    return _launch_engine(ctx, list(args))


@cli.command()
@click.option("--fix", is_flag=True, help="Auto-repair issues")
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show what --fix would change, without making any changes",
)
@click.pass_context
def doctor(ctx, fix, dry_run):
    """Run health self-check."""
    _ensure_project_on_path(ctx.obj["root"])
    from core.doctor import run_doctor

    return run_doctor(fix=fix, dry_run=dry_run)


@cli.command()
@click.pass_context
def ui(ctx):
    """Start the Web UI."""
    return run_ui_command()


@cli.command()
@click.argument("name", required=False)
@click.pass_context
def new(ctx, name):
    """Create a new task draft in tasks/[name].md."""
    config = ctx.obj["config"]
    root = ctx.obj["root"]
    child_env = ctx.obj["child_env"]

    # 'new' 语义：使用 opencode 启动一个带 interview 任务的会话
    task_name = name or "unnamed_task"

    # Resolve tasks path
    paths_cfg = config.get("paths", {})
    res_root = paths_cfg.get("resource_root")
    if res_root:
        tasks_dir = Path(res_root.replace("$CODEAGENT", str(root.as_posix()))) / "tasks"
    else:
        tasks_dir = Path(paths_cfg.get("tasks", "tasks"))

    if not tasks_dir.is_absolute():
        tasks_dir = root / tasks_dir

    try:
        rel_tasks_path = os.path.relpath(tasks_dir, Path.cwd())
    except ValueError:
        # Windows raises when tasks_dir and cwd are on different drives --
        # fall back to the absolute path rather than crash.
        rel_tasks_path = str(tasks_dir)
    target_file = os.path.join(rel_tasks_path, f"{task_name}.md").replace("\\", "/")

    # 确定启动命令：使用默认引擎 (opencode) 运行 interview 任务
    engine_script = str(root / "engines" / "start_opencode.py")

    print(t("task.authoring_start", name=task_name))
    print(t("task.target_location", path=target_file))

    # 构建命令：直接注入任务创建的专项意图
    cmd = [
        sys.executable,
        engine_script,
        t("task.authoring_prompt") + str(target_file),
    ]

    return subprocess.run(cmd, env=child_env).returncode


def _history_list(ctx, engine):
    _ensure_project_on_path(ctx.obj["root"])
    from core.session_history.session_finder import find_all_sessions

    project_path = str(Path.cwd())
    sessions = find_all_sessions(project_path, engine=engine)
    if not sessions:
        print(t("history.none"))
        return

    print(t("history.found", count=len(sessions), path=project_path))
    for i, s in enumerate(sessions):
        title = s.title or s.first_user_message[:60] or t("history.no_title")
        print(
            f"  [{i + 1}] {s.engine.value:8s} | {s.started_at[:19]:19s} | {s.message_count:3d} msgs | {title}"
        )
        print(f"       ID: {s.session_id}")
    print(t("history.show_hint"))


@cli.group(invoke_without_command=True)
@click.pass_context
def history(ctx):
    """Session history management."""
    if ctx.invoked_subcommand is None:
        # Default to listing all sessions.
        _history_list(ctx, engine=None)


@history.command(name="list")
@click.option("--engine", default=None, help="Filter by engine")
@click.pass_context
def history_list(ctx, engine):
    """List all sessions for this project."""
    _history_list(ctx, engine=engine)


@history.command()
@click.argument("engine_name")
@click.argument("session_id")
@click.pass_context
def show(ctx, engine_name, session_id):
    """Show full session content."""
    _ensure_project_on_path(ctx.obj["root"])
    from core.session_history.session_finder import find_session_by_id

    project_path = str(Path.cwd())
    session = find_session_by_id(session_id, engine_name, project_path)
    if not session:
        print(t("history.not_found", engine=engine_name, session_id=session_id))
        return

    print(f"{'=' * 60}")
    print(f"{t('history.field_engine')}  {session.engine.value}")
    print(f"{t('history.field_session')}  {session.session_id}")
    print(f"{t('history.field_started')}  {session.started_at}")
    print(f"{t('history.field_messages')}  {session.message_count}")
    print(f"{t('history.field_model')}  {session.model or t('history.unknown_model')}")
    print(f"{'=' * 60}\n")

    for msg in session.messages:
        role_label = (
            t("history.role_user")
            if msg.role == "user"
            else t("history.role_assistant")
        )
        print(f"[{msg.timestamp[:19] if msg.timestamp else ''}] {role_label}")
        if msg.content:
            # Truncate very long messages for terminal display
            text = msg.content if len(msg.content) <= 500 else msg.content[:500] + "..."
            print(text)
        for tc in msg.tool_calls:
            print(
                f"  * {tc.name}({tc.args_preview[:80]})"
                if tc.args_preview
                else f"  * {tc.name}"
            )
        print()


@history.command()
@click.argument("source_engine")
@click.argument("session_id")
@click.argument("target_engine")
@click.option("--yes", "-y", is_flag=True, help="Skip the confirmation prompt")
@click.pass_context
def convert(ctx, source_engine, session_id, target_engine, yes):
    """Convert session to another engine format."""
    _ensure_project_on_path(ctx.obj["root"])
    from core.session_history.session_finder import find_session_by_id
    from core.session_history.writers import write_session

    project_path = str(Path.cwd())
    session = find_session_by_id(session_id, source_engine, project_path)
    if not session:
        print(t("history.not_found", engine=source_engine, session_id=session_id))
        return

    title = session.title or session.first_user_message[:60] or t("history.no_title")
    print(t("convert.about_to"))
    print(
        t(
            "convert.line_source",
            engine=source_engine,
            session_id=session_id,
            count=session.message_count,
        )
    )
    print(t("convert.line_title", title=title))
    print(t("convert.line_target", engine=target_engine))

    if not yes:
        if not (sys.stdin.isatty() and sys.stdout.isatty()):
            print(t("convert.needs_confirmation"))
            return
        if not click.confirm(t("convert.confirm"), default=False):
            print(t("convert.cancelled"))
            return

    try:
        new_id = write_session(session, target_engine)
        print(t("convert.done", source=source_engine, target=target_engine))
        print(t("convert.new_id", session_id=new_id))
        if target_engine in ENGINES:
            print(t(f"convert.resume_{target_engine}", session_id=new_id))
    except Exception as e:
        print(t("convert.failed", error=e))


def _get_task_runner(root: Path):
    from core.services.runner_service import TaskRunner

    return TaskRunner(root)


@cli.command()
@click.option(
    "--all",
    "show_all",
    is_flag=True,
    help="Include completed/failed/stopped runs, not just running ones",
)
@click.pass_context
def ps(ctx, show_all):
    """List background task runs (started via the CLI, Web UI, or scheduler)."""
    _ensure_project_on_path(ctx.obj["root"])
    runner = _get_task_runner(ctx.obj["root"])
    runs = runner.list_runs()
    if not show_all:
        runs = [r for r in runs if r.status == "running"]
    if not runs:
        print(t("ps.none_tracked") if show_all else t("ps.none_running"))
        return

    runs.sort(key=lambda r: r.start_time, reverse=True)
    print(f"{'TASK ID':38s} {'ENGINE':9s} {'STATUS':10s} {'PID':8s} WORKSPACE")
    for r in runs:
        pid_str = str(r.pid) if r.pid else "-"
        workspace = r.workspace or "-"
        print(f"{r.task_id:38s} {r.engine:9s} {r.status:10s} {pid_str:8s} {workspace}")
    if not show_all:
        print(t("ps.hint"))


@cli.command()
@click.argument("task_id")
@click.pass_context
def stop(ctx, task_id):
    """Stop a background task run by its task id (see `ca ps`)."""
    _ensure_project_on_path(ctx.obj["root"])
    runner = _get_task_runner(ctx.obj["root"])
    status = runner.get_status(task_id)
    if status is None:
        print(t("stop.not_found", task_id=task_id))
        print(t("stop.list_hint"))
        sys.exit(1)
    if status.status != "running":
        print(t("stop.not_running", task_id=task_id, status=status.status))
        return
    if runner.stop_task(task_id):
        print(t("stop.stopped", task_id=task_id))
    else:
        print(t("stop.failed", task_id=task_id))
        sys.exit(1)


@cli.command(name="batch-run")
@click.argument("task_name")
@click.option(
    "--engine",
    required=True,
    type=click.Choice(["claude", "gemini", "opencode", "codex"]),
    help="Engine to run the task with in every target project.",
)
@click.option(
    "--group",
    default=None,
    help="Only target projects registered under this resource group (default: all registered projects).",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="List the projects that would run, without starting anything.",
)
@click.pass_context
def batch_run(ctx, task_name, engine, group, dry_run):
    """Run TASK_NAME across every registered project (optionally filtered by --group).

    Each project runs in its own background process via the same task runner
    the Web UI and scheduler use, so `ca ps` / `ca stop <task_id>` work on
    the runs this starts. A project already running the same task is skipped
    rather than double-started.
    """
    _ensure_project_on_path(ctx.obj["root"])
    from core.services.runner_service import TaskAlreadyRunningError
    from core.services.task_service import TaskService
    from core.web.resource_paths import resolve_resource_path

    config = ctx.obj["config"]
    registry = [
        item
        for item in config.get("project_registry", [])
        if isinstance(item, dict) and item.get("path")
    ]
    targets = [item for item in registry if group is None or item.get("group") == group]
    if not targets:
        scope = t("batch.scope_group", group=group) if group else ""
        print(t("batch.no_projects", scope=scope))
        sys.exit(1)

    tasks_root = resolve_resource_path("tasks", "CA_TASKS_ROOT")
    if TaskService(tasks_root).get_task(task_name) is None:
        print(t("batch.no_task", task=task_name, root=tasks_root))
        sys.exit(1)

    print(
        t(
            "batch.plan_header",
            count=len(targets),
            task=task_name,
            engine=engine,
        )
    )
    for target in targets:
        print(
            t(
                "batch.plan_row",
                path=target["path"],
                group=target.get("group", "?"),
            )
        )

    if dry_run:
        print(t("batch.dry_run"))
        return

    runner = _get_task_runner(ctx.obj["root"])
    started: list[tuple[str, str]] = []
    skipped: list[str] = []
    failed: list[tuple[str, str]] = []

    for target in targets:
        workspace = target["path"]
        proj_group = target.get("group") or "common"
        try:
            status = runner.run_task(
                task_name,
                engine,
                proj_group,
                tasks_root=tasks_root,
                workspace=workspace,
                prevent_overlap=True,
            )
        except TaskAlreadyRunningError:
            skipped.append(workspace)
            continue
        except ValueError as e:
            failed.append((workspace, str(e)))
            continue
        if status.status == "running":
            started.append((workspace, status.task_id))
        else:
            failed.append((workspace, status.status))

    print()
    for workspace, task_id in started:
        print(t("batch.started_row", task_id=task_id, workspace=workspace))
    for workspace in skipped:
        print(t("batch.skipped_row", workspace=workspace))
    for workspace, reason in failed:
        print(t("batch.failed_row", reason=reason, workspace=workspace))
    print(
        t(
            "batch.summary",
            started=len(started),
            skipped=len(skipped),
            failed=len(failed),
        )
    )
    if started:
        print(t("batch.track_hint"))
    if failed:
        sys.exit(1)


@cli.group(name="project", invoke_without_command=True)
@click.pass_context
def project(ctx):
    """Manage the project registry (config.json's project_registry)."""
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


@project.command(name="add")
@click.argument("path", required=False, default=".")
@click.option(
    "--group",
    default="common",
    show_default=True,
    help="Resource group to bind this project to.",
)
@click.pass_context
def project_add(ctx, path, group):
    """Register PATH (default: current directory) under GROUP, non-interactively.

    Unlike the interactive first-run prompt, this works in scripts and CI --
    no TTY required.
    """
    root = ctx.obj["root"]
    resolved = Path(path).expanduser().resolve()
    if not resolved.is_dir():
        print(t("project.not_a_directory", path=resolved))
        sys.exit(1)

    config = ctx.obj["config"]
    if group not in config.get("groups", {}):
        print(t("project.group_missing", group=group))

    service = ConfigService(get_default_config_path(root))
    registry = service.add_project(str(resolved), group)
    print(t("project.add_ok", path=resolved, group=group))
    print(t("project.registry_size", count=len(registry)))


@project.command(name="remove")
@click.argument("path")
@click.pass_context
def project_remove(ctx, path):
    """Remove PATH from the project registry."""
    root = ctx.obj["root"]
    resolved = Path(path).expanduser().resolve()
    service = ConfigService(get_default_config_path(root))
    before = service.get_config()[0].get("project_registry", [])
    registry = service.delete_project(str(resolved))
    if len(registry) == len(before):
        print(t("project.remove_missing", path=resolved))
        sys.exit(1)
    print(t("project.removed", path=resolved))


@project.command(name="list")
@click.pass_context
def project_list(ctx):
    """List every registered project."""
    config = ctx.obj["config"]
    registry = config.get("project_registry", [])
    if not registry:
        print(t("project.none_registered"))
        return
    for item in registry:
        path = item.get("path", "?")
        available = path != "?" and Path(path).expanduser().is_dir()
        mark = "v" if available else t("project.missing_marker")
        print(
            t(
                "project.list_row",
                mark=mark,
                path=path,
                group=item.get("group", "?"),
            )
        )


_RESOURCE_KINDS = ("skills", "plugins", "hooks", "prompts")


@cli.group(name="resources", invoke_without_command=True)
@click.pass_context
def resources(ctx):
    """Discover skills, plugins, hooks, and prompts without opening the Web UI."""
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


@resources.command(name="list")
@click.argument("kind", type=click.Choice(_RESOURCE_KINDS))
@click.option(
    "--group",
    default="codeagent",
    show_default=True,
    help="Resource group to check the enabled/active state against.",
)
@click.pass_context
def resources_list(ctx, kind, group):
    """List available resources of one KIND (skills, plugins, hooks, or prompts)."""
    _ensure_project_on_path(ctx.obj["root"])
    from core.web.resource_paths import ROOT_DIR, resolve_resource_path

    config = ctx.obj["config"]
    enabled_ids = set(config.get("groups", {}).get(group, {}).get(kind, []))

    # rows: (id, description, enabled)
    rows: list[tuple[str, str, bool]] = []

    if kind == "skills":
        from core.services.skill_service import SkillService

        skill_service = SkillService(resolve_resource_path("skills", "CA_SKILLS_ROOT"))
        for items in skill_service.get_detailed_skills().values():
            for item in items:
                rows.append(
                    (item["id"], item["description"], item["id"] in enabled_ids)
                )
    elif kind == "plugins":
        from core.services.plugin_service import PluginService

        plugin_service = PluginService(
            resolve_resource_path("plugins", "CA_PLUGINS_ROOT")
        )
        for items in plugin_service.get_detailed_plugins().values():
            for item in items:
                rows.append(
                    (item["id"], item["description"], item["id"] in enabled_ids)
                )
    elif kind == "hooks":
        from core.services.hook_service import HookService

        hook_service = HookService(
            resolve_resource_path("hooks", "CA_HOOKS_ROOT"),
            get_default_config_path(ctx.obj["root"]),
        )
        for item in hook_service.get_detailed_hooks():
            rows.append(
                (item["id"], item["description"] or item["event"], item["isActive"])
            )
    else:  # prompts
        from core.services.prompt_service import PromptService

        prompt_service = PromptService(
            resolve_resource_path("prompt", "CA_PROMPTS_ROOT"), ROOT_DIR
        )
        for item in prompt_service.get_prompt_groups():
            rows.append((item["id"], item["description"], item["id"] in enabled_ids))

    if not rows:
        print(t("resources.none", kind=kind))
        return

    label = (
        t("resources.label_active")
        if kind == "hooks"
        else t("resources.label_enabled_in", group=group)
    )
    click.echo(
        click.style(
            t(
                "resources.header",
                kind=kind.capitalize(),
                count=len(rows),
                label=label,
            ),
            bold=True,
        )
    )
    for resource_id, description, enabled in sorted(rows):
        mark = (
            click.style("●", fg="green")
            if enabled
            else click.style("○", fg="bright_black")
        )
        desc = f" — {description}" if description else ""
        click.echo(f"  {mark} {resource_id}{desc}")


_ENGINE_CHOICE = click.Choice(sorted(ENGINES))


@cli.group(name="mcp", invoke_without_command=True)
@click.pass_context
def mcp(ctx):
    """Inspect and sync MCP servers across engines."""
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


@mcp.command(name="list")
@click.argument("engine", type=_ENGINE_CHOICE, required=False)
@click.pass_context
def mcp_list(ctx, engine):
    """List configured MCP servers for ENGINE (default: all four)."""
    _ensure_project_on_path(ctx.obj["root"])
    from core.services import mcp_service

    project_path = str(Path.cwd())
    engines = [engine] if engine else sorted(ENGINES)

    for name in engines:
        try:
            servers = mcp_service.list_servers(name, project_path)
        except Exception as exc:
            click.echo(f"{click.style(name, bold=True)}: ⚠️  {exc}")
            continue

        scope = "project" if name in ("claude", "gemini") else "global"
        header = f"{name} ({scope})"
        if not servers:
            click.echo(f"{click.style(header, bold=True)}: (none)")
            continue
        click.echo(click.style(f"{header} — {len(servers)}", bold=True))
        for server in servers:
            target = server["url"] or " ".join(server["command"] or [])
            click.echo(f"  ● {server['name']}  [{server['transport']}]  {target}")


@mcp.command(name="add")
@click.argument("engine", type=_ENGINE_CHOICE)
@click.argument("name")
@click.argument("command", nargs=-1)
@click.option("--url", default=None, help="Remote server URL, instead of a command.")
@click.option(
    "--env",
    "env_pairs",
    multiple=True,
    metavar="KEY=VALUE",
    help="Environment variable for the server; repeatable.",
)
@click.option(
    "--transport",
    default=None,
    help="Transport for a --url server (e.g. http, sse). Ignored for stdio.",
)
@click.pass_context
def mcp_add(ctx, engine, name, command, url, env_pairs, transport):
    """Add an MCP server to ENGINE.

    Pass the launch command after NAME, or use --url for a remote server:

      ca mcp add claude fs -- npx -y @modelcontextprotocol/server-filesystem /data

      ca mcp add codex api --url https://example.com/mcp
    """
    _ensure_project_on_path(ctx.obj["root"])
    from core.services import mcp_service

    env: dict[str, str] = {}
    for pair in env_pairs:
        key, sep, value = pair.partition("=")
        if not sep:
            print(t("mcp.bad_env_pair", pair=pair))
            sys.exit(1)
        env[key] = value

    try:
        mcp_service.add_server(
            engine,
            str(Path.cwd()),
            name,
            command=list(command) or None,
            url=url,
            env=env or None,
            transport=transport,
        )
    except (ValueError, RuntimeError) as exc:
        print(t("mcp.error", error=exc))
        sys.exit(1)

    scope = (
        t("mcp.scope_project")
        if engine in ("claude", "gemini")
        else t("mcp.scope_global")
    )
    print(t("mcp.added", name=name, engine=engine, scope=scope))
    others = sorted(ENGINES - {engine})
    print(t("mcp.sync_hint", engine=engine))
    print(t("mcp.sync_targets", targets=", ".join(others)))


@mcp.command(name="remove")
@click.argument("engine", type=_ENGINE_CHOICE)
@click.argument("name")
@click.pass_context
def mcp_remove(ctx, engine, name):
    """Remove MCP server NAME from ENGINE."""
    _ensure_project_on_path(ctx.obj["root"])
    from core.services import mcp_service

    try:
        mcp_service.remove_server(engine, str(Path.cwd()), name)
    except KeyError:
        print(t("mcp.not_found", engine=engine, name=name))
        sys.exit(1)
    except (ValueError, RuntimeError) as exc:
        print(t("mcp.error", error=exc))
        sys.exit(1)

    print(t("mcp.removed", name=name, engine=engine))


@mcp.command(name="sync")
@click.argument("source", type=_ENGINE_CHOICE)
@click.option(
    "--to",
    "targets",
    multiple=True,
    type=_ENGINE_CHOICE,
    help="Target engine; repeatable. Defaults to every engine but SOURCE.",
)
@click.option(
    "--name",
    "names",
    multiple=True,
    help="Only sync this server; repeatable. Defaults to all of SOURCE's.",
)
@click.option(
    "--overwrite",
    is_flag=True,
    help="Replace same-named servers in the targets instead of skipping them.",
)
@click.option(
    "--dry-run", is_flag=True, help="Show what would change without writing anything."
)
@click.pass_context
def mcp_sync(ctx, source, targets, names, overwrite, dry_run):
    """Copy SOURCE's MCP servers into the other engines' native configs.

    codex and opencode store MCP servers globally rather than per-project, so
    syncing into them affects every project on this machine.
    """
    _ensure_project_on_path(ctx.obj["root"])
    from core.services import mcp_service

    try:
        results = mcp_service.sync_servers(
            source,
            str(Path.cwd()),
            targets=list(targets) or None,
            names=list(names) or None,
            overwrite=overwrite,
            dry_run=dry_run,
        )
    except ValueError as exc:
        print(t("mcp.error", error=exc))
        sys.exit(1)

    if not results:
        print(t("mcp.nothing_to_sync", source=source))
        return

    marks = {
        "added": click.style("+", fg="green"),
        "replaced": click.style("~", fg="yellow"),
        "skipped": click.style("=", fg="bright_black"),
        "failed": click.style("!", fg="red"),
    }
    if dry_run:
        click.echo(click.style(t("mcp.dry_run"), bold=True))
    for engine_name in dict.fromkeys(item["engine"] for item in results):
        click.echo(click.style(engine_name, bold=True))
        for item in (r for r in results if r["engine"] == engine_name):
            mark = marks.get(item["action"], "?")
            click.echo(f"  {mark} {item['name']} — {item['detail']}")

    failed = sum(1 for item in results if item["action"] == "failed")
    if failed:
        print(t("mcp.partial_failure", failed=failed, total=len(results)))
        sys.exit(1)


def main():
    try:
        return cli(standalone_mode=False)
    except click.ClickException as e:
        e.show()
        sys.exit(e.exit_code)
    except click.exceptions.Abort:
        sys.exit(1)
    except KeyboardInterrupt:
        print(t("cli.cancelled"))
        sys.exit(0)


if __name__ == "__main__":
    sys.exit(main() or 0)

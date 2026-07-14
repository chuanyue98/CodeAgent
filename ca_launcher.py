#!/usr/bin/env python3
import sys
import subprocess
import json
import os
import shutil
import socket
import time
from pathlib import Path

import click

from core.console import configure_console_encoding
from core.resource_locator import get_bundled_resource_root, get_default_config_path

UI_API_PORT = 8524
UI_DEV_SERVER_HOST = "127.0.0.1"
UI_DEV_SERVER_PORT = 5173
UI_DEV_SERVER_START_TIMEOUT = 15

configure_console_encoding()


def _installed_root():
    return Path(__file__).resolve().parent


def _looks_like_project_root(path: Path):
    return (
        (path / "pyproject.toml").exists()
        and (path / "core").is_dir()
        and (path / "engines").is_dir()
        and (path / "web" / "frontend" / "package.json").exists()
    )


def _project_root():
    cwd = Path.cwd().resolve()
    for candidate in (cwd, *cwd.parents):
        if _looks_like_project_root(candidate):
            return candidate
    return _installed_root()


def load_config():
    root = _project_root()
    config_path = get_default_config_path(root)
    default_config = {
        "default_mode": "local",
        "language": "hybrid",
        "proxy": {"host": "127.0.0.1", "port": 1087},
    }
    if config_path.exists():
        try:
            with open(config_path, "r", encoding="utf-8-sig") as f:
                return {**default_config, **json.load(f)}
        except Exception as e:
            print(f"⚠️ Warning: Failed to load config.json: {e}")
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
    if _is_ui_dev_server_running():
        return True

    if not _frontend_source_exists():
        return False

    cmd = _ui_dev_server_command()
    if not cmd:
        return False

    frontend_root = _frontend_root()
    subprocess.Popen(  # noqa: S603
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
    return False


def _can_open_browser():
    if sys.platform.startswith(("win", "darwin")):
        return True
    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def _open_browser(url):
    if not _can_open_browser():
        print(f"🌐 Open the UI in your browser: {url}")
        return False

    import webbrowser

    if not webbrowser.open(url):
        print(f"🌐 Open the UI in your browser: {url}")
        return False
    return True


def _extract_proxy_candidates(proxy_cfg):
    if isinstance(proxy_cfg, list):
        return [
            (e.get("host", "127.0.0.1"), int(e["port"]))
            for e in proxy_cfg
            if "port" in e
        ]
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
        print(
            f"❌ Missing dependency for 'ca ui': {missing_module}\n"
            "Install project dependencies first:\n"
            "  uv sync\n"
            "or:\n"
            "  pip install -e ."
        )
        return 1

    use_dev_server = False
    if _frontend_source_exists():
        if _is_ui_dev_server_running():
            use_dev_server = True
        else:
            print(
                f"⚙️ Starting Vite dev server at http://{UI_DEV_SERVER_HOST}:{UI_DEV_SERVER_PORT} ..."
            )
            use_dev_server = _start_ui_dev_server()
            if not use_dev_server:
                if _frontend_dist_exists():
                    print(
                        "⚠️ Failed to start Vite dev server; falling back to built UI."
                    )
                else:
                    print(
                        "❌ Failed to start Vite dev server, and no built UI was found.\n"
                        "Install frontend deps in web/frontend and retry."
                    )
                    return 1

    if use_dev_server:
        port = UI_API_PORT
        url = f"http://{UI_DEV_SERVER_HOST}:{UI_DEV_SERVER_PORT}"
        print(f"⚡ Detected Vite dev server at {url}")
        print(f"🚀 Starting Web UI API at http://127.0.0.1:{port} ...")
    else:
        if not _frontend_dist_exists():
            print(
                "❌ Built Web UI not found at web/frontend/dist, and source mode is unavailable.\n"
                "Run `bun install` in web/frontend or build the frontend first."
            )
            return 1
        port = find_available_port(UI_API_PORT)
        url = f"http://127.0.0.1:{port}"
        print(f"🚀 Starting Web UI at {url}...")

    _open_browser(url)

    try:
        uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")
    except KeyboardInterrupt:
        pass
    return 0


# ============================================================================
# Click CLI
# ============================================================================

EPILOG = """\
Engines: gemini, claude, opencode, codex (default: gemini)
YOLO mode is enabled by default.

Examples:
  ca                       Start the default engine (gemini)
  ca claude do something   Start claude with extra args
  ca --proxy gemini        Start gemini with proxy enabled
  ca doctor --fix          Run health check and auto-repair
  ca ui                    Start the Web UI
  ca new my-task           Create a new task draft
  ca history list          List sessions (use --engine <name> to filter)
  ca history show <engine> <session_id>
  ca history convert <source_engine> <session_id> <target_engine>
"""


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
                return cmd_name, cmd, args[1:]
        # Unknown leading token: forward *all* original args to engine launch.
        launch = self.get_command(ctx, "_launch")
        return "_launch", launch, args


def _ensure_project_on_path(root):
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))


def _launch_engine(ctx, args):
    """Build and run the engine subprocess.

    ``args`` is the list of tokens that follow the (optional) engine name and
    have already had ``--proxy`` / ``-y`` / ``--help`` stripped by click.
    """
    obj = ctx.ensure_object(dict)
    child_env = obj.get("child_env")
    engine_script_map = obj["engine_script_map"]

    engine_name = "gemini"
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

    target_script = engine_script_map[engine_name]
    cmd = [sys.executable, target_script] + extra_params
    subprocess.run(cmd, env=child_env)


@click.group(
    cls=CodeAgentGroup,
    invoke_without_command=True,
    context_settings=dict(
        ignore_unknown_options=True,
        allow_extra_args=True,
        allow_interspersed_args=True,
    ),
    epilog=EPILOG,
)
@click.option("--proxy", is_flag=True, help="Enable proxy from config.json")
@click.option("-y", "--yolo", is_flag=True, default=True, help="Enable YOLO mode")
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
        print(f"🌐 代理已启用: {proxy_scheme}://{proxy_host}:{proxy_port}")

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
        _launch_engine(ctx, [])


@cli.command(
    name="_launch",
    hidden=True,
    context_settings=dict(ignore_unknown_options=True, allow_extra_args=True),
)
@click.argument("args", nargs=-1)
@click.pass_context
def _launch(ctx, args):
    """Forward arbitrary arguments to an engine launch."""
    _launch_engine(ctx, list(args))


@cli.command()
@click.option("--fix", is_flag=True, help="Auto-repair issues")
@click.pass_context
def doctor(ctx, fix):
    """Run health self-check."""
    _ensure_project_on_path(ctx.obj["root"])
    from core.doctor import run_doctor

    return run_doctor(fix=fix)


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

    rel_tasks_path = os.path.relpath(tasks_dir, Path.cwd())
    target_file = os.path.join(rel_tasks_path, f"{task_name}.md").replace("\\", "/")

    # 确定启动命令：使用默认引擎 (opencode) 运行 interview 任务
    engine_script = str(root / "engines" / "start_opencode.py")

    print(f"✍️ 启动任务编排专家为您编写新任务: {task_name}...")
    print(f"📂 目标位置: {target_file}")

    # 构建命令：直接注入任务创建的专项意图
    cmd = [
        sys.executable,
        engine_script,
        f"请启动‘任务编排专家 (Task Authoring)’模式，目标是为 CodeAgent 编写一个新的自动化任务剧本，文件名为：{target_file}",
    ]

    subprocess.run(cmd, env=child_env)


def _history_list(ctx, engine):
    _ensure_project_on_path(ctx.obj["root"])
    from core.session_history.session_finder import find_all_sessions

    project_path = str(Path.cwd())
    sessions = find_all_sessions(project_path, engine=engine)
    if not sessions:
        print("📝 No sessions found for this project.")
        return

    print(f"📋 Found {len(sessions)} session(s) for {project_path}:\n")
    for i, s in enumerate(sessions):
        title = s.title or s.first_user_message[:60] or "(no title)"
        print(
            f"  [{i + 1}] {s.engine.value:8s} | {s.started_at[:19]:19s} | {s.message_count:3d} msgs | {title}"
        )
        print(f"       ID: {s.session_id}")
    print("\nUse: ca history show <engine> <session_id>")


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
        print(f"❌ Session not found: {engine_name}/{session_id}")
        return

    print(f"{'=' * 60}")
    print(f"Engine:    {session.engine.value}")
    print(f"Session:   {session.session_id}")
    print(f"Started:   {session.started_at}")
    print(f"Messages:  {session.message_count}")
    print(f"Model:     {session.model or '(unknown)'}")
    print(f"{'=' * 60}\n")

    for msg in session.messages:
        role_label = "👤 USER" if msg.role == "user" else "🤖 ASSISTANT"
        print(f"[{msg.timestamp[:19] if msg.timestamp else ''}] {role_label}")
        if msg.content:
            # Truncate very long messages for terminal display
            text = msg.content if len(msg.content) <= 500 else msg.content[:500] + "..."
            print(text)
        for tc in msg.tool_calls:
            print(
                f"  🔧 {tc.name}({tc.args_preview[:80]})"
                if tc.args_preview
                else f"  🔧 {tc.name}"
            )
        print()


@history.command()
@click.argument("source_engine")
@click.argument("session_id")
@click.argument("target_engine")
@click.pass_context
def convert(ctx, source_engine, session_id, target_engine):
    """Convert session to another engine format."""
    _ensure_project_on_path(ctx.obj["root"])
    from core.session_history.session_finder import find_session_by_id
    from core.session_history.writers import write_session

    project_path = str(Path.cwd())
    session = find_session_by_id(session_id, source_engine, project_path)
    if not session:
        print(f"❌ Session not found: {source_engine}/{session_id}")
        return

    try:
        new_id = write_session(session, target_engine)
        print(f"✅ Converted {source_engine} → {target_engine}")
        print(f"   New session ID: {new_id}")
        if target_engine == "claude":
            print(f"   Resume with: claude -r {new_id}")
        elif target_engine == "codex":
            print("   Resume with: codex continue")
        elif target_engine == "gemini":
            print("   Resume with: gemini (select from history)")
        elif target_engine == "opencode":
            print("   Resume with: opencode (select from history)")
    except Exception as e:
        print(f"❌ Conversion failed: {e}")


def main():
    try:
        return cli(standalone_mode=False)
    except click.ClickException as e:
        e.show()
        sys.exit(e.exit_code)
    except click.exceptions.Abort:
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n\n👋 Cancelled")
        sys.exit(0)


if __name__ == "__main__":
    sys.exit(main() or 0)

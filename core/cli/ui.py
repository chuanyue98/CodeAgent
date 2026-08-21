"""Web UI bootstrap — extracted from ``ca_launcher.py``."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import threading
import time
import urllib.parse
from pathlib import Path

from core.i18n import t
from core.resource_locator import get_bundled_resource_root

from . import helpers as _helpers

UI_API_PORT = 8524
UI_DEV_SERVER_HOST = "127.0.0.1"
UI_DEV_SERVER_PORT = 5173
UI_DEV_SERVER_START_TIMEOUT = 15
_ui_dev_process: subprocess.Popen | None = None


def _frontend_root() -> Path:
    root = _helpers._project_root()
    source_frontend = root / "web" / "frontend"
    if source_frontend.exists():
        return source_frontend
    return get_bundled_resource_root(root) / "web" / "frontend"


def _frontend_dist_exists() -> bool:
    return (_frontend_root() / "dist" / "index.html").exists()


def _frontend_source_exists() -> bool:
    frontend_root = _frontend_root()
    return (frontend_root / "package.json").exists() and (
        frontend_root / "src"
    ).exists()


def _ui_dev_server_command() -> list[str] | None:
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


def _is_ui_dev_server_running(
    host: str = UI_DEV_SERVER_HOST, port: int = UI_DEV_SERVER_PORT
) -> bool:
    return _helpers.is_tcp_port_open(host, port, timeout=0.2)


def _start_ui_dev_server() -> bool:
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


def _can_open_browser() -> bool:
    if sys.platform.startswith(("win", "darwin")):
        return True
    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def _open_browser(url: str) -> bool:
    if not _can_open_browser():
        print(t("ui.open_in_browser", url=url))
        return False
    import webbrowser

    if not webbrowser.open(url):
        print(t("ui.open_in_browser", url=url))
        return False
    return True


def _wait_for_api_then_open_browser(api_host: str, api_port: int, url: str) -> None:
    deadline = time.time() + UI_DEV_SERVER_START_TIMEOUT
    while time.time() < deadline:
        if _helpers.is_tcp_port_open(api_host, api_port, timeout=0.2):
            break
        time.sleep(0.1)
    _open_browser(url)


def run_ui_command() -> int:
    try:
        root = _helpers._project_root()
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
        import uvicorn  # type: ignore[import-untyped]

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
                t("ui.vite_starting", host=UI_DEV_SERVER_HOST, port=UI_DEV_SERVER_PORT)
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
            frontend_root = _frontend_root()
            print(
                t(
                    "ui.not_built",
                    index_path=frontend_root / "dist" / "index.html",
                    frontend_root=frontend_root,
                )
            )
            return 1
        port = _helpers.find_available_port(UI_API_PORT)
        url = f"http://127.0.0.1:{port}"
        print(t("ui.starting", url=url))

    api_host = os.environ.get("CA_UI_HOST", "127.0.0.1")

    from core.web.security import (
        TOKEN_QUERY_PARAM,
        auth_enabled,
        get_ui_token,
        is_loopback_hostname,
    )

    if auth_enabled():
        token = get_ui_token()
        url = f"{url}?{TOKEN_QUERY_PARAM}={urllib.parse.quote(token)}"
        if not is_loopback_hostname(api_host):
            print(t("ui.non_loopback_warning", host=api_host))

    threading.Thread(
        target=_wait_for_api_then_open_browser,
        args=(api_host, port, url),
        daemon=True,
    ).start()

    try:
        uvicorn.run(app, host=api_host, port=port, log_level="info")
    except KeyboardInterrupt:
        pass
    finally:
        _stop_ui_dev_server()
    return 0

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException

from core.constants import ENGINES
from core.resource_locator import CODE_ROOT

router = APIRouter(prefix="/api/launch", tags=["launch"])

_CA_LAUNCHER = CODE_ROOT / "ca_launcher.py"


def terminal_capability() -> dict:
    """Reports whether this server can open a separate local GUI terminal."""
    if sys.platform == "win32":
        return {"available": True, "terminal": "cmd", "mode": "local_gui"}
    if sys.platform == "darwin":
        return {
            "available": bool(shutil.which("osascript")),
            "terminal": "Terminal" if shutil.which("osascript") else None,
            "mode": "local_gui",
            "reason": None
            if shutil.which("osascript")
            else "macOS Terminal automation is unavailable",
        }

    if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        return {
            "available": False,
            "terminal": None,
            "mode": "local_gui",
            "reason": "The CodeAgent server has no graphical desktop session",
        }

    for terminal in (
        "gnome-terminal",
        "konsole",
        "xterm",
        "wezterm",
        "kitty",
        "xfce4-terminal",
        "alacritty",
        "foot",
        "kgx",
        "ptyxis",
        "tilix",
        "mate-terminal",
    ):
        if shutil.which(terminal):
            return {"available": True, "terminal": terminal, "mode": "local_gui"}

    return {
        "available": False,
        "terminal": None,
        "mode": "local_gui",
        "reason": "No supported GUI terminal emulator was found on the CodeAgent server",
    }


def launch_in_terminal(cmd: list[str], cwd: Path | None = None) -> str:
    """Launches a command in a visible terminal or raises if none is available."""
    working_dir = (cwd or Path.cwd()).resolve()
    capability = terminal_capability()
    if not capability["available"]:
        raise RuntimeError(capability.get("reason") or "Local terminal is unavailable")

    terminal = str(capability["terminal"])
    if sys.platform == "win32":
        subprocess.Popen(["cmd", "/c", "start", "cmd", "/k"] + cmd, cwd=working_dir)
    elif sys.platform == "darwin":
        script = (
            f'tell app "Terminal" to do script '
            f'"cd {shlex.quote(working_dir.as_posix())} && {shlex.join(cmd)}"'
        )
        subprocess.Popen(["osascript", "-e", script])
    else:
        terminal_args = {
            "gnome-terminal": [terminal, f"--working-directory={working_dir}", "--"],
            "konsole": [terminal, "--workdir", str(working_dir), "-e"],
            "xterm": [terminal, "-e"],
            "wezterm": [terminal, "start", "--cwd", str(working_dir), "--"],
            "kitty": [terminal, "--directory", str(working_dir)],
            "xfce4-terminal": [terminal, f"--working-directory={working_dir}", "-x"],
            "alacritty": [terminal, "--working-directory", str(working_dir), "-e"],
            "foot": [terminal, "--working-directory", str(working_dir)],
            "kgx": [terminal, f"--working-directory={working_dir}", "--"],
            "ptyxis": [terminal, f"--working-directory={working_dir}", "--"],
            "tilix": [terminal, f"--working-directory={working_dir}", "-e"],
            "mate-terminal": [terminal, f"--working-directory={working_dir}", "-x"],
        }
        subprocess.Popen(terminal_args[terminal] + cmd, cwd=working_dir)
    return terminal


@router.get("/status")
async def get_launch_status() -> dict:
    return terminal_capability()


@router.post("/{engine}")
async def launch_engine(engine: str) -> dict:
    if engine not in ENGINES:
        raise HTTPException(status_code=400, detail=f"Unknown engine: {engine}")

    cmd = [sys.executable, str(_CA_LAUNCHER), engine]

    try:
        terminal = launch_in_terminal(cmd)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(
            status_code=500, detail=f"Failed to open terminal: {exc}"
        ) from exc

    return {"status": "launched", "engine": engine, "terminal": terminal}

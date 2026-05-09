from __future__ import annotations

import shlex
import shutil
import subprocess
import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException

router = APIRouter()

ENGINES = {"claude", "gemini", "opencode", "codex"}
_CA_LAUNCHER = Path(__file__).resolve().parents[3] / "ca_launcher.py"


@router.post("/api/launch/{engine}")
async def launch_engine(engine: str) -> dict:
    if engine not in ENGINES:
        raise HTTPException(status_code=400, detail=f"Unknown engine: {engine}")

    cmd = [sys.executable, str(_CA_LAUNCHER), engine]

    if sys.platform == "win32":
        subprocess.Popen(["cmd", "/c", "start", "cmd", "/k"] + cmd)
    elif sys.platform == "darwin":
        script = f'tell app "Terminal" to do script "cd {shlex.quote(Path.cwd().as_posix())} && {shlex.join(cmd)}"'
        subprocess.Popen(["osascript", "-e", script])
    else:
        for terminal in ["gnome-terminal", "konsole", "xterm"]:
            if shutil.which(terminal):
                args = (
                    [terminal, "--"]
                    if terminal == "gnome-terminal"
                    else [terminal, "-e"]
                )
                subprocess.Popen(args + cmd)
                break

    return {"status": "launched", "engine": engine}

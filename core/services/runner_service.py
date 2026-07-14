from __future__ import annotations

import json
import os
import re
import shutil
import signal
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

_SAFE_NAME_RE = re.compile(r"^[\w.-]+$")

# Field name each engine's JSON(L) output uses for its session identifier.
# codex calls it "thread_id"; the other three call it "session_id"/"sessionID".
_CHAT_SESSION_ID_FIELDS: Dict[str, tuple[str, ...]] = {
    "claude": ("session_id",),
    "codex": ("thread_id",),
    "opencode": ("sessionID",),
    "gemini": ("session_id", "sessionId"),
}


@dataclass
class TaskRunStatus:
    task_id: str
    engine: str
    pid: Optional[int]
    status: str  # "running", "completed", "failed", "stopped"
    log_path: str
    start_time: float
    session_id: Optional[str] = None


class TaskRunner:
    """Manages background execution of CodeAgent tasks."""

    def __init__(self, root_dir: Path):
        self.root_dir = root_dir
        self.active_runs: Dict[str, TaskRunStatus] = {}
        self._processes: Dict[str, subprocess.Popen] = {}
        self.log_dir = self.root_dir / ".ca_task_logs"
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def run_task(
        self,
        task_name: str,
        engine: str,
        group: str = "common",
        tasks_root: Path | None = None,
    ) -> TaskRunStatus:
        """Starts a task in the background using the specified engine."""
        import time

        if not _SAFE_NAME_RE.match(task_name):
            raise ValueError(f"Invalid task name: {task_name!r}")
        if not _SAFE_NAME_RE.match(group):
            raise ValueError(f"Invalid group name: {group!r}")
        if engine not in {"claude", "gemini", "opencode", "codex"}:
            raise ValueError(f"Invalid engine: {engine!r}")

        task_id = f"{task_name}_{time.time_ns()}"
        log_file = self.log_dir / f"{task_id}.log"
        if not log_file.resolve().is_relative_to(self.log_dir.resolve()):
            raise ValueError("Log path escapes log directory")

        # Build command: python ca_launcher.py {engine} -t {task_name} -y
        launcher = self.root_dir / "ca_launcher.py"
        cmd = [sys.executable, str(launcher), engine, "-t", task_name, "-y"]
        env = os.environ.copy()
        env["CA_PROJECT_GROUP"] = group
        if tasks_root is not None:
            env["CA_TASKS_ROOT"] = str(tasks_root.resolve())

        # Use subprocess.Popen for background execution
        # Redirect stdout and stderr to the log file
        try:
            with open(log_file, "w", encoding="utf-8") as f:
                process = subprocess.Popen(
                    cmd,
                    cwd=str(Path.cwd()),
                    stdout=f,
                    stderr=subprocess.STDOUT,
                    stdin=subprocess.DEVNULL,
                    env=env,
                    start_new_session=True if sys.platform != "win32" else False,
                    creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
                    if sys.platform == "win32"
                    else 0,
                )

            status = TaskRunStatus(
                task_id=task_id,
                engine=engine,
                pid=process.pid,
                status="running",
                log_path=str(log_file),
                start_time=time.time(),
            )
            self.active_runs[task_id] = status
            self._processes[task_id] = process
            return status
        except Exception as e:
            status = TaskRunStatus(
                task_id=task_id,
                engine=engine,
                pid=None,
                status=f"failed: {e}",
                log_path=str(log_file),
                start_time=time.time(),
            )
            self.active_runs[task_id] = status
            return status

    def run_chat_turn(
        self,
        engine: str,
        message: str,
        session_id: Optional[str] = None,
        group: str = "common",
        project_path: Optional[str] = None,
    ) -> TaskRunStatus:
        """Starts one headless, non-interactive ChatPage turn in the background.

        Unlike ``run_task``, this calls each engine's ``build_chat_command()``
        directly (bypassing ca_launcher.py's skill/hook/plugin injection —
        see docs/chatpage-cli-spike-results.md for why that's out of scope
        for v1) and writes structured JSON(L) output to a distinct
        ``.jsonl`` log so ``logs.py``'s ``*.log`` glob doesn't pick it up.
        """
        import time

        if engine not in {"claude", "gemini", "opencode", "codex"}:
            raise ValueError(f"Invalid engine: {engine!r}")
        if not message or not message.strip():
            raise ValueError("message must not be empty")

        working_dir = Path.cwd()
        if project_path:
            working_dir = Path(project_path).expanduser().resolve()
            if not working_dir.is_dir():
                raise ValueError(f"Invalid project path: {project_path!r}")

        engine_obj = self._build_engine(engine)
        cmd = engine_obj.build_chat_command(message, session_id=session_id)

        turn_id = f"chat_{engine}_{time.time_ns()}"
        log_file = self.log_dir / f"{turn_id}.jsonl"
        if not log_file.resolve().is_relative_to(self.log_dir.resolve()):
            raise ValueError("Log path escapes log directory")

        env = engine_obj.env_manager.get_env()
        env["CA_PROJECT_GROUP"] = group

        resolved_cmd = list(cmd)
        executable = shutil.which(resolved_cmd[0], path=env.get("PATH"))
        if executable:
            resolved_cmd[0] = executable

        try:
            with open(log_file, "w", encoding="utf-8") as f:
                process = subprocess.Popen(
                    resolved_cmd,
                    cwd=str(working_dir),
                    stdout=f,
                    stderr=subprocess.STDOUT,
                    stdin=subprocess.DEVNULL,
                    env=env,
                    start_new_session=True if sys.platform != "win32" else False,
                    creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
                    if sys.platform == "win32"
                    else 0,
                )

            status = TaskRunStatus(
                task_id=turn_id,
                engine=engine,
                pid=process.pid,
                status="running",
                log_path=str(log_file),
                start_time=time.time(),
            )
            self.active_runs[turn_id] = status
            self._processes[turn_id] = process
            return status
        except Exception as e:
            status = TaskRunStatus(
                task_id=turn_id,
                engine=engine,
                pid=None,
                status=f"failed: {e}",
                log_path=str(log_file),
                start_time=time.time(),
            )
            self.active_runs[turn_id] = status
            return status

    def _build_engine(self, engine: str):
        """Lazily imports and instantiates the given engine's controller class.

        Lazy per-call imports avoid a core -> engines -> core import cycle
        (engines/start_*.py import from core.engine_base).
        """
        if engine == "claude":
            from engines.start_claude_code import ClaudeEngine

            return ClaudeEngine()
        if engine == "codex":
            from engines.start_codex import CodexEngine

            return CodexEngine()
        if engine == "opencode":
            from engines.start_opencode import OpenCodeEngine

            return OpenCodeEngine()
        if engine == "gemini":
            from engines.start_gemini import GeminiEngine

            return GeminiEngine()
        raise ValueError(f"Invalid engine: {engine!r}")

    def _extract_chat_session_id(self, engine: str, log_path: Path) -> Optional[str]:
        """Scans a completed chat turn's JSONL log for the engine-reported session id."""
        fields = _CHAT_SESSION_ID_FIELDS.get(engine, ())
        if not fields:
            return None
        try:
            with open(log_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        event = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    for field in fields:
                        value = event.get(field)
                        if value:
                            return str(value)
        except OSError:
            return None
        return None

    def list_runs(self) -> List[TaskRunStatus]:
        """Returns all tracked task runs, updating their status first."""
        # Update statuses for all running tasks
        for task_id in list(self.active_runs.keys()):
            self.get_status(task_id)
        return list(self.active_runs.values())

    def get_status(self, task_id: str) -> Optional[TaskRunStatus]:
        """Checks if a background task is still running and updates its status."""
        if task_id not in self.active_runs:
            return None

        run = self.active_runs[task_id]
        if run.status != "running" or run.pid is None:
            return run

        proc = self._processes.get(task_id)
        rc = proc.poll() if proc is not None else None
        if rc is not None:
            run.status = "completed" if rc == 0 else "failed"
            self._processes.pop(task_id, None)
            if run.session_id is None and run.log_path.endswith(".jsonl"):
                run.session_id = self._extract_chat_session_id(
                    run.engine, Path(run.log_path)
                )
        elif proc is None and not self._is_process_running(run.pid):
            run.status = "failed"

        return run

    def stop_task(self, task_id: str) -> bool:
        """Terminates a background task."""
        run = self.active_runs.get(task_id)
        if not run or run.pid is None or run.status != "running":
            return False

        try:
            if sys.platform == "win32":
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(run.pid)], capture_output=True
                )
            else:
                os.killpg(os.getpgid(run.pid), signal.SIGTERM)
            proc = self._processes.pop(task_id, None)
            if proc is not None:
                try:
                    proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    pass
            run.status = "stopped"
            return True
        except Exception:
            return False

    def kill_all(self):
        """Terminates all active processes immediately."""
        for task_id, process in list(self._processes.items()):
            try:
                process.terminate()
                process.wait(timeout=1.0)
            except Exception:
                try:
                    process.kill()
                    process.wait()
                except Exception:
                    pass
            if task_id in self.active_runs:
                self.active_runs[task_id].status = "stopped"

    def _is_process_running(self, pid: int) -> bool:
        try:
            if sys.platform == "win32":
                import ctypes

                PROCESS_QUERY_INFORMATION = 0x0400
                PROCESS_VM_READ = 0x0010
                handle = ctypes.windll.kernel32.OpenProcess(
                    PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, False, pid
                )
                if handle == 0:
                    return False
                ctypes.windll.kernel32.CloseHandle(handle)
                return True
            else:
                os.kill(pid, 0)
                return True
        except OSError:
            return False

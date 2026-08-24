from __future__ import annotations

import json
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
from dataclasses import dataclass
from pathlib import Path

from core.constants import ENGINES
from core.services.run_store import RunStore, TaskRunRecord

_SAFE_NAME_RE = re.compile(r"^[\w.-]+$")

# Field name each engine's JSON(L) output uses for its session identifier.
# codex calls it "thread_id"; the others call it "session_id"/"sessionID".
_CHAT_SESSION_ID_FIELDS: dict[str, tuple[str, ...]] = {
    "claude": ("session_id",),
    "codex": ("thread_id",),
    "opencode": ("sessionID",),
    "codebuddy": ("session_id", "sessionId"),
}


@dataclass
class TaskRunStatus:
    task_id: str
    engine: str
    pid: int | None
    status: str  # "running", "completed", "failed", "stopped"
    log_path: str
    start_time: float
    session_id: str | None = None
    workspace: str | None = None


class TaskAlreadyRunningError(ValueError):
    """Raised when an overlap-protected task is already active."""


class TaskRunner:
    """Manages background execution of CodeAgent tasks."""

    def __init__(self, root_dir: Path):
        self.root_dir = root_dir
        self.active_runs: dict[str, TaskRunStatus] = {}
        self._processes: dict[str, subprocess.Popen] = {}
        self._stopping_tasks: set[str] = set()
        self._run_lock = threading.RLock()
        self.log_dir = self.root_dir / ".ca_task_logs"
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self._run_store = RunStore(self.log_dir / "runs.db")
        self._load_persisted_runs()

    def reset_for_e2e(self) -> None:
        """Wipes all run state: log files, DB rows, in-memory tracking.

        Only meant to be called by the isolated E2E test backend's reset
        endpoint (core/web/routers/e2e.py) between specs, where no run is
        expected to still be active — it does not attempt to stop any
        in-flight process.
        """
        with self._run_lock:
            self.active_runs.clear()
            self._processes.clear()
            self._stopping_tasks.clear()
        self._run_store.clear()
        for pattern in ("*.log", "*.jsonl"):
            for f in self.log_dir.glob(pattern):
                f.unlink(missing_ok=True)

    def run_task(
        self,
        task_name: str,
        engine: str,
        group: str = "common",
        tasks_root: Path | None = None,
        workspace: str | None = None,
        prevent_overlap: bool = False,
    ) -> TaskRunStatus:
        """Starts a task in the background using the specified engine."""
        import time

        if not _SAFE_NAME_RE.match(task_name):
            raise ValueError(f"Invalid task name: {task_name!r}")
        if not _SAFE_NAME_RE.match(group):
            raise ValueError(f"Invalid group name: {group!r}")
        if engine not in ENGINES:
            raise ValueError(f"Invalid engine: {engine!r}")

        working_dir = (
            Path(workspace).expanduser().resolve() if workspace else Path.cwd()
        )
        if not working_dir.is_dir():
            raise ValueError(f"Invalid workspace: {workspace!r}")

        with self._run_lock:
            if prevent_overlap and self.has_active_task(
                task_name, workspace=str(working_dir)
            ):
                raise TaskAlreadyRunningError("Task is already running")

            task_id = f"{task_name}_{time.time_ns()}"
            log_file = self.log_dir / f"{task_id}.log"
            if not log_file.resolve().is_relative_to(self.log_dir.resolve()):
                raise ValueError("Log path escapes log directory")

            launcher = self.root_dir / "ca_launcher.py"
            # --non-interactive is required: background runs have no TTY/stdin,
            # so every engine adapter must be forced past its interactive-TUI
            # default (see build_command()) or it hangs on stdin / emits raw
            # ANSI. Long form is used because codex only registers that spelling.
            cmd = [
                sys.executable,
                str(launcher),
                engine,
                "-t",
                task_name,
                "-y",
                "--non-interactive",
            ]
            env = os.environ.copy()
            env["CA_PROJECT_GROUP"] = group
            if tasks_root is not None:
                env["CA_TASKS_ROOT"] = str(tasks_root.resolve())

            try:
                with open(log_file, "w", encoding="utf-8") as f:
                    process = subprocess.Popen(
                        cmd,
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
                    task_id=task_id,
                    engine=engine,
                    pid=process.pid,
                    status="running",
                    log_path=str(log_file),
                    start_time=time.time(),
                    workspace=str(working_dir),
                )
                self.active_runs[task_id] = status
                self._processes[task_id] = process
                self._persist(status)
                return status
            except Exception as e:
                status = TaskRunStatus(
                    task_id=task_id,
                    engine=engine,
                    pid=None,
                    status=f"failed: {e}",
                    log_path=str(log_file),
                    start_time=time.time(),
                    workspace=str(working_dir),
                )
                self.active_runs[task_id] = status
                self._persist(status)
                return status

    def run_chat_turn(
        self,
        engine: str,
        message: str,
        session_id: str | None = None,
        group: str = "common",
        project_path: str | None = None,
    ) -> TaskRunStatus:
        """Starts one headless, non-interactive ChatPage turn in the background.

        Unlike ``run_task``, this calls each engine's ``build_chat_command()``
        directly (bypassing ca_launcher.py's skill/hook/plugin injection —
        see docs/chatpage-cli-spike-results.md for why that's out of scope
        for v1) and writes structured JSON(L) output to a distinct
        ``.jsonl`` log so ``logs.py``'s ``*.log`` glob doesn't pick it up.
        """
        import time

        if engine not in ENGINES:
            raise ValueError(f"Invalid engine: {engine!r}")
        if not message or not message.strip():
            raise ValueError("message must not be empty")

        if not project_path:
            raise ValueError("project_path is required for chat turns")
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
            with self._run_lock:
                self.active_runs[turn_id] = status
                self._processes[turn_id] = process
                self._persist(status)
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
            with self._run_lock:
                self.active_runs[turn_id] = status
                self._persist(status)
            return status

    def _load_persisted_runs(self):
        """Reload runs from the SQLite store so they survive restarts."""
        for record in self._run_store.list_running():
            status = TaskRunStatus(
                task_id=record.task_id,
                engine=record.engine,
                pid=record.pid,
                status=record.status,
                log_path=record.log_path,
                start_time=record.start_time,
                session_id=record.session_id,
                workspace=record.workspace,
            )
            self.active_runs[record.task_id] = status

    def _persist(self, run: TaskRunStatus):
        if not isinstance(run, TaskRunStatus):
            return
        self._run_store.upsert(
            TaskRunRecord(
                task_id=run.task_id,
                engine=run.engine,
                pid=run.pid,
                status=run.status,
                log_path=run.log_path,
                start_time=run.start_time,
                session_id=run.session_id,
                workspace=run.workspace,
            )
        )

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
        if engine == "codebuddy":
            from engines.start_codebuddy import CodeBuddyEngine

            return CodeBuddyEngine()
        raise ValueError(f"Invalid engine: {engine!r}")

    def _extract_chat_session_id(self, engine: str, log_path: Path) -> str | None:
        """Scans a completed chat turn's JSONL log for the engine-reported session id."""
        fields = _CHAT_SESSION_ID_FIELDS.get(engine, ())
        if not fields:
            return None
        try:
            with open(log_path, encoding="utf-8") as f:
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

    def list_runs(self) -> list[TaskRunStatus]:
        """Returns all tracked task runs, updating their status first."""
        with self._run_lock:
            for task_id in list(self.active_runs.keys()):
                self.get_status(task_id)
            return list(self.active_runs.values())

    def has_active_task(self, task_name: str, workspace: str | None = None) -> bool:
        """Return whether a task with this name is already running.

        Schedules use this as a conservative overlap guard.  A task name is
        embedded in the generated run id, so this remains compatible with
        persisted records created before workspace metadata was introduced.
        """
        prefix = f"{task_name}_"
        resolved_workspace = (
            str(Path(workspace).expanduser().resolve()) if workspace else None
        )
        with self._run_lock:
            for task_id, _run in list(self.active_runs.items()):
                if not task_id.startswith(prefix):
                    continue
                refreshed = self.get_status(task_id)
                if refreshed is None or refreshed.status != "running":
                    continue
                if (
                    resolved_workspace is not None
                    and refreshed.workspace is not None
                    and str(Path(refreshed.workspace).expanduser().resolve())
                    != resolved_workspace
                ):
                    continue
                return True
        return False

    def get_status(self, task_id: str) -> TaskRunStatus | None:
        """Checks if a background task is still running and updates its status."""
        with self._run_lock:
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
                self._persist(run)
            elif proc is None and not self._is_process_running(run.pid):
                run.status = "failed"
                self._persist(run)

            return run

    def stop_task(self, task_id: str) -> bool:
        """Terminates a background task."""
        with self._run_lock:
            run = self.active_runs.get(task_id)
            if (
                not run
                or run.pid is None
                or run.status != "running"
                or task_id in self._stopping_tasks
            ):
                return False
            self._stopping_tasks.add(task_id)
            pid = run.pid
            proc = self._processes.get(task_id)

        try:
            if sys.platform == "win32":
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(pid)],
                    capture_output=True,
                )
            else:
                os.killpg(os.getpgid(pid), signal.SIGTERM)
            if proc is not None:
                try:
                    proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    pass
        except Exception:
            with self._run_lock:
                self._stopping_tasks.discard(task_id)
            return False

        with self._run_lock:
            try:
                if self._processes.get(task_id) is proc:
                    self._processes.pop(task_id, None)
                run.status = "stopped"
                self._persist(run)
                return True
            except Exception:
                return False
            finally:
                self._stopping_tasks.discard(task_id)

    def kill_all(self):
        """Terminates all active processes immediately."""
        with self._run_lock:
            processes_to_kill = list(self._processes.items())
            self._processes.clear()
            runs_to_persist: list[TaskRunStatus] = []
            for task_id, _process in processes_to_kill:
                if task_id in self.active_runs:
                    self.active_runs[task_id].status = "stopped"
                    runs_to_persist.append(self.active_runs[task_id])

        for run in runs_to_persist:
            self._persist(run)
        for _task_id, process in processes_to_kill:
            try:
                process.terminate()
                process.wait(timeout=1.0)
            except Exception:
                try:
                    process.kill()
                    process.wait()
                except Exception:
                    pass

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

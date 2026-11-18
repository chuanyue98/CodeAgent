from __future__ import annotations

import importlib
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import IO

import psutil

from core.engine_registry import ENGINES, get_spec, normalize_engine_name
from core.host_env import child_environ
from core.logging_config import get_logger
from core.runtime_paths import prepare_run_dir
from core.services.log_broker import LogBroker
from core.services.run_store import RunStore, TaskRunRecord
from core.services.task_service import _SAFE_NAME_RE, is_valid_task_name
from core.utils.process_tree import process_created_at, terminate_process_tree

logger = get_logger(__name__)

_MAX_TERMINAL_ACTIVE_RUNS = 200

#: Finished runs that ended more than this many days ago are dropped from the
#: run DB and their log files deleted, once, at startup. Log files are the part
#: that actually grows -- a single run's log is unbounded in size, and nothing
#: removed them before, so a long-lived install accumulated every log it ever
#: wrote. ``CA_RUN_RETENTION_DAYS=0`` turns pruning off entirely.
RUN_RETENTION_DAYS = 30
#: ...but never prune below this many most-recent runs, whatever their age, so
#: an install that sat idle past the cutoff still opens with its history.
RUN_RETENTION_KEEP = 200
RUN_RETENTION_ENV = "CA_RUN_RETENTION_DAYS"


def _retention_days() -> int:
    """Reads the retention window, falling back to the default when unusable."""
    raw = os.environ.get(RUN_RETENTION_ENV, "").strip()
    if not raw:
        return RUN_RETENTION_DAYS
    try:
        return max(0, int(raw))
    except ValueError:
        return RUN_RETENTION_DAYS


#: Every artifact kind the runner writes into ``log_dir``: ``run_task`` writes
#: ``{task_id}.log``, ``run_chat_turn`` writes ``{turn_id}.jsonl``. Both
#: sweepers glob this, so a new artifact kind is collected by adding it here.
_LOG_PATTERNS = ("*.log", "*.jsonl")

#: How long a finished run's log pump may take to drain the pipe before the run
#: is reported as stopped anyway. The pipe can hold output the child wrote just
#: before exiting; without the wait a completed run's log is one chunk short.
_PUMP_DRAIN_TIMEOUT = 5.0


def _read_available(stream: IO[bytes], size: int = 65536) -> bytes:
    """Returns what the pipe already holds, without waiting to fill *size*.

    ``BufferedReader.read(n)`` blocks until it has ``n`` bytes or reaches EOF,
    which would sit on a chunk until the next one arrived. ``read1`` returns
    after a single underlying read instead, so output is forwarded as it lands.
    """
    read1 = getattr(stream, "read1", None)
    if read1 is not None:
        result: bytes = read1(size)
        return result
    return stream.read(size)


def _feed_stdin(process: subprocess.Popen, text: str) -> None:
    """把 *text* 写进 *process* 的 stdin 后关掉；引擎先退出了就算了。"""
    assert process.stdin is not None
    try:
        process.stdin.write(text.encode("utf-8"))
    except OSError:
        pass
    finally:
        try:
            process.stdin.close()
        except OSError:
            pass


def _unlink_quietly(path: Path) -> None:
    """Deletes *path*, tolerating a handle still holding it open.

    Windows 上「上一个用例启动的引擎进程还没退出」时，日志文件句柄仍被握着
    （假引擎会 sleep 数秒），unlink 会抛 PermissionError；POSIX 允许删除打开
    中的文件所以从不触发。删不掉就留着，下一轮清理会再遇到它。
    """
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


# Field name each engine's JSON(L) output uses for its session identifier.
# Derived from the engine registry (AUDIT-002): codex calls it "thread_id";
# the others call it "session_id"/"sessionID".
_CHAT_SESSION_ID_FIELDS: dict[str, tuple[str, ...]] = {
    name: spec.session_id_fields for name, spec in ENGINES.items()
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
    end_time: float | None = None
    exit_code: int | None = None
    task_name: str | None = None
    schedule_id: str | None = None
    process_created_at: float | None = None


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
        self.log_dir = prepare_run_dir(self.root_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self._run_store = RunStore(self.log_dir / "runs.db")
        # stdout 由 _pump_stdout 线程写盘后唤醒日志流订阅者，见 log_broker。
        self._log_broker = LogBroker()
        self._pumps: dict[str, threading.Thread] = {}
        self._load_persisted_runs()

    @property
    def log_broker(self) -> LogBroker:
        """日志流端点用它等待「有新输出」，替代定时轮询文件。"""
        return self._log_broker

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
            self._pumps.clear()
        self._run_store.clear()
        for f in self._log_files():
            _unlink_quietly(f)

    def run_task(
        self,
        task_name: str,
        engine: str,
        group: str = "common",
        tasks_root: Path | None = None,
        workspace: str | None = None,
        prevent_overlap: bool = False,
        schedule_id: str | None = None,
    ) -> TaskRunStatus:
        """Starts a task in the background using the specified engine.

        ``schedule_id`` is recorded on the run when a schedule fired it, so the
        schedule can later report what the run actually did.
        """
        if not is_valid_task_name(task_name):
            raise ValueError(f"Invalid task name: {task_name!r}")
        if not _SAFE_NAME_RE.match(group):
            raise ValueError(f"Invalid group name: {group!r}")
        engine = normalize_engine_name(engine)
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
            env = child_environ()
            env["CA_PROJECT_GROUP"] = group
            if tasks_root is not None:
                env["CA_TASKS_ROOT"] = str(tasks_root.resolve())

            try:
                # 先落一个空文件：日志流端点靠「文件存在」判定这个运行可读，
                # 而内容要等 _pump_stdout 线程开始搬运后才有。
                log_file.touch()
                process = subprocess.Popen(
                    cmd,
                    cwd=str(working_dir),
                    stdout=subprocess.PIPE,
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
                    process_created_at=process_created_at(process.pid),
                    status="running",
                    log_path=str(log_file),
                    start_time=time.time(),
                    workspace=str(working_dir),
                    task_name=task_name,
                    schedule_id=schedule_id,
                )
                self.active_runs[task_id] = status
                self._processes[task_id] = process
                try:
                    self._start_pump(task_id, process, log_file)
                except Exception:
                    self._processes.pop(task_id, None)
                    terminate_process_tree(process.pid, status.process_created_at)
                    raise
                self._persist(status)
                self._trim_terminal_runs()
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
                    task_name=task_name,
                    schedule_id=schedule_id,
                    end_time=time.time(),
                )
                self.active_runs[task_id] = status
                self._persist(status)
                self._trim_terminal_runs()
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
        directly (bypassing ca_launcher.py's skill/hook/plugin injection,
        which is out of scope for v1) and writes structured JSON(L) output to a distinct
        ``.jsonl`` log so ``logs.py``'s ``*.log`` glob doesn't pick it up.
        """

        engine = normalize_engine_name(engine)
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
        stdin_text = engine_obj.chat_stdin(message)

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
                    stdin=subprocess.DEVNULL if stdin_text is None else subprocess.PIPE,
                    env=env,
                    start_new_session=True if sys.platform != "win32" else False,
                    creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
                    if sys.platform == "win32"
                    else 0,
                )
            if stdin_text is not None:
                # 放线程里写：消息超过管道缓冲时，写会一直等到引擎开始读。
                threading.Thread(
                    target=_feed_stdin,
                    args=(process, stdin_text),
                    daemon=True,
                ).start()

            status = TaskRunStatus(
                task_id=turn_id,
                engine=engine,
                pid=process.pid,
                process_created_at=process_created_at(process.pid),
                status="running",
                log_path=str(log_file),
                start_time=time.time(),
            )
            with self._run_lock:
                self.active_runs[turn_id] = status
                self._processes[turn_id] = process
                self._persist(status)
                self._trim_terminal_runs()
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
                self._trim_terminal_runs()
            return status

    def _start_pump(
        self, run_id: str, process: subprocess.Popen, log_file: Path
    ) -> None:
        """Starts the thread that drains *process* stdout into its log file.

        stdout is a pipe rather than the log file itself so every chunk is
        observable the moment it lands: the thread appends it and wakes the
        streaming clients (``LogBroker``). The draining has to happen in a
        thread regardless -- an undrained pipe fills and blocks the child
        part-way through a run.
        """
        self._log_broker.register(run_id)
        thread = threading.Thread(
            target=self._pump_stdout,
            args=(run_id, process, log_file),
            name=f"ca-log-pump-{run_id}",
            daemon=True,
        )
        self._pumps[run_id] = thread
        try:
            thread.start()
        except Exception:
            self._pumps.pop(run_id, None)
            self._log_broker.finish(run_id)
            raise

    def _pump_stdout(
        self, run_id: str, process: subprocess.Popen, log_file: Path
    ) -> None:
        """Copies the child's stdout to *log_file*, waking subscribers per chunk."""
        stream = process.stdout
        try:
            if stream is None:
                return
            with open(log_file, "wb") as fh:
                while True:
                    chunk = _read_available(stream)
                    if not chunk:
                        break
                    fh.write(chunk)
                    fh.flush()
                    self._log_broker.notify(run_id)
        except Exception:
            # 读失败只能放弃：关掉读端后子进程会拿到 EPIPE 自行退出，
            # 总好过留一个把管道写满后卡死的运行。
            logger.warning("搬运运行 %s 的日志失败", run_id, exc_info=True)
        finally:
            if stream is not None:
                try:
                    stream.close()
                except OSError:
                    pass
            self._log_broker.finish(run_id)

    def _await_pump(self, run_id: str) -> None:
        """Waits for a run's log pump to drain, so its log file is complete.

        ``get_status`` flips a run to completed as soon as the process exits,
        but the pipe may still hold output written just before that. Callers
        (the log viewer, the session-id scan) read the file to decide what
        happened, so the status must not claim completion while the file is
        still a chunk short.
        """
        with self._run_lock:
            thread = self._pumps.pop(run_id, None)
        if thread is not None:
            thread.join(timeout=_PUMP_DRAIN_TIMEOUT)

    @staticmethod
    def _status_from_record(record: TaskRunRecord) -> TaskRunStatus:
        return TaskRunStatus(
            task_id=record.task_id,
            engine=record.engine,
            pid=record.pid,
            status=record.status,
            log_path=record.log_path,
            start_time=record.start_time,
            session_id=record.session_id,
            workspace=record.workspace,
            end_time=record.end_time,
            exit_code=record.exit_code,
            task_name=record.task_name,
            schedule_id=record.schedule_id,
            process_created_at=record.process_created_at,
        )

    def close(self) -> None:
        """Releases the run DB connection this runner opened."""
        self._run_store.close()

    def prune_old_runs(self) -> None:
        """Drops aged-out run rows and the log files nothing points at any more.

        Called once from the web server's startup rather than from the
        constructor or a timer: the set only grows when a run finishes, and a
        process that never restarts is not the one with a disk problem.
        Constructing a runner stays free of side effects -- the CLI builds one
        for read-only commands like ``ca task ps``, which have no business
        deleting anything.
        """
        days = _retention_days()
        if days <= 0:
            return
        cutoff = time.time() - days * 86400

        for log_path in self._run_store.prune(
            older_than=cutoff, keep_latest=RUN_RETENTION_KEEP
        ):
            _unlink_quietly(Path(log_path))
        self._run_store.prune_notifications(days, keep_latest=RUN_RETENTION_KEEP)

        # Logs whose row was deleted individually (see `delete`) leave no
        # trace in the table, so age is the only thing left to judge them by.
        still_referenced = {Path(p) for p in self._run_store.log_paths()}
        for stale in self._log_files():
            if stale in still_referenced:
                continue
            try:
                if stale.stat().st_mtime >= cutoff:
                    continue
            except OSError:
                continue
            _unlink_quietly(stale)

    def _log_files(self) -> Iterator[Path]:
        """Every artifact the runner has written into ``log_dir``."""
        for pattern in _LOG_PATTERNS:
            yield from self.log_dir.glob(pattern)

    def _load_persisted_runs(self):
        """Reload runs from the SQLite store so they survive restarts."""
        for record in self._run_store.list_running():
            self.active_runs[record.task_id] = self._status_from_record(record)

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
                end_time=run.end_time,
                exit_code=run.exit_code,
                task_name=run.task_name,
                schedule_id=run.schedule_id,
                process_created_at=run.process_created_at,
            )
        )

    def _build_engine(self, engine: str):
        """Lazily imports and instantiates the given engine's controller class.

        The adapter module/class comes from the engine registry
        (``EngineSpec.adapter``, dotted "module:Class" path). The import is
        done per call to avoid a core -> engines -> core import cycle
        (engines/start_*.py import from core.engine_base).
        """
        spec = get_spec(engine)
        if spec is None:
            raise ValueError(f"Invalid engine: {engine!r}")
        module_name, _, class_name = spec.adapter.partition(":")
        module = importlib.import_module(module_name)
        return getattr(module, class_name)()

    _instantiate_engine = _build_engine

    def _extract_chat_session_id(self, engine: str, log_path: Path) -> str | None:
        """Scans a completed chat turn's JSONL log for the engine-reported session id."""
        fields = _CHAT_SESSION_ID_FIELDS.get(normalize_engine_name(engine), ())
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
            task_ids = list(self.active_runs.keys())
        for task_id in task_ids:
            self.get_status(task_id)
        with self._run_lock:
            return list(self.active_runs.values())

    def get_run(self, task_id: str) -> TaskRunStatus | None:
        """One run by id, falling back to the store.

        ``get_status`` only knows ``active_runs``, so it answers None for any
        run this process did not launch -- including every run made before the
        last restart. Callers that are following a specific run (a schedule
        waiting on its last fire) need the persisted row too.
        """
        with self._run_lock:
            if task_id in self.active_runs:
                return self.get_status(task_id)
            record = self._run_store.get(task_id)
        return self._status_from_record(record) if record else None

    def list_history(
        self,
        *,
        task_name: str | None = None,
        schedule_id: str | None = None,
        limit: int = 50,
    ) -> list[TaskRunStatus]:
        """Runs newest first, including ones that ended before this process started.

        ``list_runs`` only ever sees ``active_runs``, which holds what this
        process launched plus whatever was still marked running at boot. Every
        run has been written to SQLite all along; this reads it back.
        """
        with self._run_lock:
            # Settle any live run first so a just-finished process is recorded
            # with its exit code before the history is read.
            for task_id in list(self.active_runs.keys()):
                self.get_status(task_id)
            records = self._run_store.list_history(
                task_name=task_name, schedule_id=schedule_id, limit=limit
            )
        return [self._status_from_record(record) for record in records]

    @staticmethod
    def _matches_task_name(run: TaskRunStatus, task_name: str) -> bool:
        """优先精确匹配 ``run.task_name``；仅在历史遗留空字段时按 ``<name>_<数字>`` 回退。"""
        if run.task_name is not None:
            return run.task_name == task_name
        derived, _, suffix = run.task_id.rpartition("_")
        if suffix.isdigit():
            return derived == task_name
        return run.task_id == task_name

    def _trim_terminal_runs(self) -> None:
        """限制内存中已结束运行记录的数量上限，防止长期运行后内存持续膨胀。"""
        terminal = [
            (run.end_time or run.start_time, tid)
            for tid, run in self.active_runs.items()
            if run.status != "running"
        ]
        excess = len(terminal) - _MAX_TERMINAL_ACTIVE_RUNS
        if excess <= 0:
            return
        terminal.sort()
        for _, tid in terminal[:excess]:
            self.active_runs.pop(tid, None)
            self._processes.pop(tid, None)

    def has_active_task(self, task_name: str, workspace: str | None = None) -> bool:
        """Return whether a task with this name is already running."""
        resolved_workspace = (
            str(Path(workspace).expanduser().resolve()) if workspace else None
        )
        with self._run_lock:
            for task_id, run in list(self.active_runs.items()):
                if not self._matches_task_name(run, task_name):
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
            if (
                run.status != "running"
                or run.pid is None
                or task_id in self._stopping_tasks
            ):
                return run

            proc = self._processes.get(task_id)
            rc = proc.poll() if proc is not None else None

        if rc is not None:
            # 进程已退出，但管道里可能还压着它临退出前写的一段输出：先让泵线程
            # 收尾（不能在锁内 join，否则整个运行表都被它堵住）。
            self._await_pump(task_id)
            with self._run_lock:
                if run.status != "running":
                    return run
                run.status = "completed" if rc == 0 else "failed"
                run.end_time = time.time()
                run.exit_code = rc
                self._processes.pop(task_id, None)
                if run.session_id is None and run.log_path.endswith(".jsonl"):
                    run.session_id = self._extract_chat_session_id(
                        run.engine, Path(run.log_path)
                    )
                self._persist(run)
                self._trim_terminal_runs()
                return run

        with self._run_lock:
            if proc is None:
                alive = self._is_process_running(run.pid)
                if alive and run.process_created_at is not None:
                    actual_created = process_created_at(run.pid)
                    if (
                        actual_created is None
                        or abs(actual_created - run.process_created_at) > 0.5
                    ):
                        alive = False
                if not alive:
                    run.status = "failed"
                    run.end_time = time.time()
                    self._persist(run)
                    self._trim_terminal_runs()

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
            if not terminate_process_tree(pid, run.process_created_at):
                logger.error("任务 %s 未能停止，保留运行记录以便重试", task_id)
                with self._run_lock:
                    self._stopping_tasks.discard(task_id)
                return False
            if proc is not None:
                try:
                    proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    pass
            self._await_pump(task_id)
        except Exception:
            logger.warning("停止任务 %s 失败", task_id, exc_info=True)
            with self._run_lock:
                self._stopping_tasks.discard(task_id)
            return False
        with self._run_lock:
            try:
                if self._processes.get(task_id) is proc:
                    self._processes.pop(task_id, None)

                run.status = "stopped"
                run.end_time = time.time()
                self._persist(run)
                self._trim_terminal_runs()
                return True
            except Exception:
                return False
            finally:
                self._stopping_tasks.discard(task_id)

    def kill_all(self):
        """只终止本进程持有的任务；失败时保留句柄和真实状态。"""
        with self._run_lock:
            processes = list(self._processes.items())
        for task_id, process in processes:
            run = self.active_runs.get(task_id)
            if isinstance(run, TaskRunStatus):
                self.stop_task(task_id)
                continue
            # 兼容启动中尚未登记状态的子进程。
            if process.poll() is None:
                if not terminate_process_tree(
                    process.pid, process_created_at(process.pid)
                ):
                    continue
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    pass
            with self._run_lock:
                self._processes.pop(task_id, None)
            self._await_pump(task_id)

    def _is_process_running(self, pid: int) -> bool:
        """使用 psutil 检查 PID 是否仍在运行（排除已退出的僵尸进程）。"""
        try:
            proc = psutil.Process(pid)
            return proc.is_running() and proc.status() != psutil.STATUS_ZOMBIE
        except psutil.Error:
            return False

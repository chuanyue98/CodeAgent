"""后台委派：发起即返回 run id，子引擎在独立的 worker 进程里跑完。

每次委派一个目录 ``~/.codeagent/delegations/<run_id>/``：

- ``task.json``   发起时写定的任务
- ``status.json`` worker 自己维护的状态（running → completed / failed / stopped）
- ``output.log``  子引擎的实时输出
- ``result.json`` 结束后的结构化结果

状态由 worker 写盘而不是由发起方持有进程句柄：MCP 服务随宿主会话起落，
宿主一退出它就被结束，委派却应该照样跑完、结果照样取得回来。
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import Any

import psutil

from core.delegation_depth import current_depth
from core.engine_registry import ENGINES, normalize_engine_name
from core.host_env import child_environ
from core.lock_manager import LockManager
from core.resource_locator import CODE_ROOT
from core.session_history.paths import normalize_project_path
from core.utils.atomic_write import atomic_write
from core.utils.process_tree import terminate_process_tree

MODES = ("write", "review")
TERMINAL_STATUSES = ("completed", "failed", "stopped")
DEFAULT_TIMEOUT_SECONDS = 30 * 60
RETENTION_DAYS = 30
RETENTION_KEEP = 100

_RUN_ID_RE = re.compile(r"^[a-z]+-\d{8}-\d{6}-[0-9a-f]{6}$")
#: 结果里给发起方模型看的输出尾巴，够看清结论，又不至于撑爆上下文。
_SUMMARY_CHARS = 4000
_DIFF_CHARS = 6000


def runs_root() -> Path:
    return Path.home() / ".codeagent" / "delegations"


def _run_dir(run_id: str) -> Path:
    if not _RUN_ID_RE.match(run_id):
        raise ValueError(f"Invalid delegation run id: {run_id!r}")
    return runs_root() / run_id


def read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_json(path: Path, data: dict[str, Any]) -> None:
    atomic_write(path, json.dumps(data, ensure_ascii=False, indent=2))


def write_status(run_dir: Path, **fields: Any) -> None:
    status = read_json(run_dir / "status.json")
    status.update(fields)
    _write_json(run_dir / "status.json", status)


def start_delegation(
    engine: str,
    instruction: str,
    *,
    workspace: Path | str | None = None,
    mode: str = "write",
    isolate: bool = False,
    target_paths: list[str] | None = None,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    group: str = "common",
) -> str:
    """写下任务并拉起脱离当前进程的 worker，立即返回 run id。"""
    canonical = normalize_engine_name(engine)
    if canonical not in ENGINES:
        raise ValueError(
            f"Unknown engine: {engine!r} (choose from {', '.join(sorted(ENGINES))})"
        )
    if mode not in MODES:
        raise ValueError(f"Unknown mode: {mode!r} (choose from {', '.join(MODES)})")
    ws = Path(workspace).resolve() if workspace else Path.cwd().resolve()
    if not ws.is_dir():
        raise ValueError(f"Workspace does not exist: {ws}")

    run_id = f"{canonical}-{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"
    run_dir = _run_dir(run_id)
    run_dir.mkdir(parents=True, exist_ok=False)
    _write_json(
        run_dir / "task.json",
        {
            "run_id": run_id,
            "engine": canonical,
            "instruction": instruction,
            "mode": mode,
            "workspace": str(ws),
            "isolate": isolate,
            "target_paths": target_paths or [],
            "timeout": timeout,
            "group": group,
            "depth": current_depth(),
            "created_at": time.time(),
        },
    )
    write_status(run_dir, status="starting", created_at=time.time())

    env = child_environ()
    env["PYTHONPATH"] = os.pathsep.join(
        p for p in (str(CODE_ROOT), env.get("PYTHONPATH", "")) if p
    )
    detach: dict[str, Any] = (
        {
            "creationflags": getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            | getattr(subprocess, "DETACHED_PROCESS", 0)
        }
        if sys.platform == "win32"
        else {"start_new_session": True}
    )
    with open(run_dir / "worker.log", "w", encoding="utf-8") as worker_log:
        subprocess.Popen(
            [sys.executable, "-m", "core.services.delegation_worker", str(run_dir)],
            cwd=str(ws),
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=worker_log,
            stderr=subprocess.STDOUT,
            **detach,
        )
    # 不在父进程中回写 status.json，避免覆盖 worker 自己写入的 running/pid/终态。
    return run_id


def _pid_alive(
    pid: int,
    expected_created_at: float | None = None,
    run_dir: Path | None = None,
) -> bool:
    """优先通过排他文件锁探活 worker；无锁文件时回退到 psutil + create_time 核对。"""
    if run_dir is not None:
        lock_path = run_dir / "worker.lock"
        if lock_path.exists():
            locks = LockManager()
            probe = locks.try_acquire_resource_lock(lock_path)
            if probe is None:
                return True
            locks.release_resource_lock(probe)
            return False
    try:
        proc = psutil.Process(pid)
        if (
            expected_created_at is not None
            and abs(proc.create_time() - expected_created_at) > 0.5
        ):
            return False
        return proc.is_running() and proc.status() != psutil.STATUS_ZOMBIE
    except psutil.Error:
        return False


def get_run(run_id: str) -> dict[str, Any]:
    """任务、当前状态，结束后再带上结果。"""
    run_dir = _run_dir(run_id)
    if not run_dir.is_dir():
        raise ValueError(f"No such delegation run: {run_id}")
    task = read_json(run_dir / "task.json")
    status = read_json(run_dir / "status.json")
    state = status.get("status", "unknown")

    pid = status.get("pid")
    created_at = status.get("process_created_at")
    if (
        state not in TERMINAL_STATUSES
        and isinstance(pid, int)
        and not _pid_alive(pid, expected_created_at=created_at, run_dir=run_dir)
    ):
        # worker 可能刚刚在写完终态后才释放锁，重读一次避免误报失败。
        status = read_json(run_dir / "status.json")
        state = status.get("status", "unknown")
        if state not in TERMINAL_STATUSES:
            # worker 没来得及写终态就没了（被杀、崩溃）。
            state = "failed"
            write_status(
                run_dir,
                status=state,
                ended_at=time.time(),
                error="worker exited without reporting a result",
            )
            status = read_json(run_dir / "status.json")

    run: dict[str, Any] = {
        "run_id": run_id,
        "engine": task.get("engine"),
        "mode": task.get("mode"),
        "status": state,
        "instruction": task.get("instruction", ""),
        "workspace": task.get("workspace"),
        "output_log": str(run_dir / "output.log"),
        "elapsed_seconds": round(
            (status.get("ended_at") or time.time())
            - (status.get("started_at") or status.get("created_at") or time.time()),
            1,
        ),
    }
    if status.get("error"):
        run["error"] = status["error"]
    if state in TERMINAL_STATUSES:
        result = read_json(run_dir / "result.json")
        if result:
            run["result"] = result
    return run


def wait_run(run_id: str, timeout: float = 45.0, poll: float = 1.0) -> dict[str, Any]:
    """最多等 *timeout* 秒；到点还没结束就返回当前状态，调用方可以再等。"""
    deadline = time.monotonic() + max(0.0, timeout)
    while True:
        run = get_run(run_id)
        if run["status"] in TERMINAL_STATUSES or time.monotonic() >= deadline:
            return run
        time.sleep(poll)


def _prune_old_runs(run_dirs: list[Path], *, keep: int = RETENTION_KEEP) -> None:
    """清理超过保留期且已结束的旧委派目录，保留最近 ``keep`` 条与所有运行中记录。"""
    if len(run_dirs) <= keep:
        return
    cutoff = time.time() - RETENTION_DAYS * 86400
    locks = LockManager()
    for run_dir in run_dirs[keep:]:
        status = read_json(run_dir / "status.json")
        if status.get("status") not in TERMINAL_STATUSES:
            continue
        lock_path = run_dir / "worker.lock"
        if lock_path.exists():
            probe = locks.try_acquire_resource_lock(lock_path)
            if probe is None:
                continue
            locks.release_resource_lock(probe)
        ended = status.get("ended_at") or status.get("created_at")
        if not isinstance(ended, (int, float)):
            try:
                ended = run_dir.stat().st_mtime
            except OSError:
                continue
        if ended < cutoff:
            shutil.rmtree(run_dir, ignore_errors=True)


def list_runs(workspace: Path | str | None = None, limit: int = 20) -> list[dict]:
    root = runs_root()
    if not root.is_dir():
        return []
    ws = (
        normalize_project_path(str(Path(workspace).resolve()))
        if workspace is not None
        else None
    )
    runs: list[dict] = []
    run_dirs = [p for p in root.iterdir() if p.is_dir() and _RUN_ID_RE.match(p.name)]
    # run id 是 <engine>-<日期>-<时间>-<随机>，按名字排会先按引擎名排。
    run_dirs.sort(key=lambda p: p.name.split("-", 1)[1], reverse=True)
    for run_dir in run_dirs:
        task = read_json(run_dir / "task.json")
        task_ws = task.get("workspace")
        if ws is not None and (
            not isinstance(task_ws, str) or normalize_project_path(task_ws) != ws
        ):
            continue
        run = get_run(run_dir.name)
        run.pop("result", None)
        runs.append(run)
        if len(runs) >= limit:
            break
    _prune_old_runs(run_dirs, keep=max(RETENTION_KEEP, limit))
    return runs


def stop_run(run_id: str) -> bool:
    """核对锁与进程身份后结束 worker 及其全部子孙进程。"""
    run_dir = _run_dir(run_id)
    status = read_json(run_dir / "status.json")
    pid = status.get("pid")
    created_at = status.get("process_created_at")
    if status.get("status") in TERMINAL_STATUSES or not isinstance(pid, int):
        return False
    if not _pid_alive(pid, expected_created_at=created_at, run_dir=run_dir):
        return False
    if not terminate_process_tree(pid, created_at):
        return False
    latest = read_json(run_dir / "status.json")
    if latest.get("status") in TERMINAL_STATUSES:
        return False
    write_status(run_dir, status="stopped", ended_at=time.time())
    return True


def rewind_run(run_id: str, *, force: bool = False) -> dict[str, Any]:
    """把一次就地委派改过的工作区退回到它开跑前（见 delegation_checkpoint）。"""
    from core.services import delegation_checkpoint

    run = get_run(run_id)
    if run.get("status") not in TERMINAL_STATUSES:
        return {"run_id": run_id, "rewound": False, "error": "委派还在运行，先停掉它"}
    workspace = read_json(_run_dir(run_id) / "task.json").get("workspace")
    if not isinstance(workspace, str):
        return {"run_id": run_id, "rewound": False, "error": "找不到这次委派的工作区"}
    res = delegation_checkpoint.rewind(Path(workspace), run_id, force=force)
    return {"run_id": run_id, **asdict(res)}


def build_result(res: Any) -> dict[str, Any]:
    """:class:`DelegationResult` → 给发起方模型看的结构化结果。"""
    output = (res.output or "").strip()
    diff = res.diff or ""
    return {
        "success": res.success,
        "exit_code": res.exit_code,
        "summary": output[-_SUMMARY_CHARS:],
        "summary_truncated": len(output) > _SUMMARY_CHARS,
        "files_changed": res.files_changed,
        "diff": diff[:_DIFF_CHARS],
        "diff_truncated": len(diff) > _DIFF_CHARS,
        "branch": res.branch,
        "isolated_worktree": res.isolated_worktree,
        "duration_seconds": round(res.duration_seconds, 1),
        "error": res.error,
        "checkpoint": res.checkpoint,
    }

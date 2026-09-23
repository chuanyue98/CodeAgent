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
import signal
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any

from core.delegation_depth import current_depth
from core.engine_registry import ENGINES, normalize_engine_name
from core.host_env import child_environ
from core.resource_locator import CODE_ROOT
from core.utils.atomic_write import atomic_write

MODES = ("write", "review")
TERMINAL_STATUSES = ("completed", "failed", "stopped")
DEFAULT_TIMEOUT_SECONDS = 30 * 60

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
        proc = subprocess.Popen(
            [sys.executable, "-m", "core.services.delegation_worker", str(run_dir)],
            cwd=str(ws),
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=worker_log,
            stderr=subprocess.STDOUT,
            **detach,
        )
    write_status(run_dir, pid=proc.pid)
    return run_id


def _pid_alive(pid: int) -> bool:
    if sys.platform == "win32":
        result = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
            capture_output=True,
            text=True,
        )
        return str(pid) in result.stdout
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def get_run(run_id: str) -> dict[str, Any]:
    """任务、当前状态，结束后再带上结果。"""
    run_dir = _run_dir(run_id)
    if not run_dir.is_dir():
        raise ValueError(f"No such delegation run: {run_id}")
    task = read_json(run_dir / "task.json")
    status = read_json(run_dir / "status.json")
    state = status.get("status", "unknown")

    pid = status.get("pid")
    if state not in TERMINAL_STATUSES and isinstance(pid, int) and not _pid_alive(pid):
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


def list_runs(workspace: Path | str | None = None, limit: int = 20) -> list[dict]:
    root = runs_root()
    if not root.is_dir():
        return []
    ws = str(Path(workspace).resolve()) if workspace else None
    runs: list[dict] = []
    for run_dir in sorted(root.iterdir(), key=lambda p: p.name, reverse=True):
        if not _RUN_ID_RE.match(run_dir.name):
            continue
        task = read_json(run_dir / "task.json")
        if ws is not None and task.get("workspace") != ws:
            continue
        run = get_run(run_dir.name)
        run.pop("result", None)
        runs.append(run)
        if len(runs) >= limit:
            break
    return runs


def stop_run(run_id: str) -> bool:
    """结束 worker 及其拉起的子引擎（它们同属一个进程组）。"""
    run_dir = _run_dir(run_id)
    status = read_json(run_dir / "status.json")
    pid = status.get("pid")
    if status.get("status") in TERMINAL_STATUSES or not isinstance(pid, int):
        return False
    try:
        if sys.platform == "win32":
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(pid)],
                capture_output=True,
                timeout=10,
            )
        else:
            os.killpg(os.getpgid(pid), signal.SIGTERM)
    except (OSError, subprocess.SubprocessError):
        return False
    write_status(run_dir, status="stopped", ended_at=time.time())
    return True


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
    }

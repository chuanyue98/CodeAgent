"""后台委派的 worker：``python -m core.services.delegation_worker <run_dir>``。

由 :func:`core.services.delegation_runs.start_delegation` 以脱离的进程拉起，
跑完一个委派并把状态、结果写回 run 目录。
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

from core.services.delegation_runs import build_result, read_json, write_status
from core.services.delegation_service import delegate_subtask
from core.utils.atomic_write import atomic_write


def run(run_dir: Path) -> int:
    task = read_json(run_dir / "task.json")
    # pid 也由自己写：发起方写 pid 与这里写状态是两次读改写，可能互相覆盖。
    write_status(run_dir, status="running", pid=os.getpid(), started_at=time.time())
    try:
        res = delegate_subtask(
            engine=task["engine"],
            instruction=task.get("instruction", ""),
            workspace=task.get("workspace"),
            target_paths=task.get("target_paths") or None,
            timeout=int(task.get("timeout") or 1800),
            isolate=bool(task.get("isolate")),
            group=task.get("group") or "common",
            mode=task.get("mode") or "write",
            log_path=run_dir / "output.log",
            depth=int(task.get("depth") or 0),
        )
    except Exception as exc:  # 结果必须落盘，否则发起方只能等到超时
        write_status(run_dir, status="failed", ended_at=time.time(), error=str(exc))
        return 1

    atomic_write(
        run_dir / "result.json",
        json.dumps(build_result(res), ensure_ascii=False, indent=2),
    )
    write_status(
        run_dir,
        status="completed" if res.success else "failed",
        ended_at=time.time(),
        error=res.error,
    )
    return 0 if res.success else 1


def main() -> None:
    sys.exit(run(Path(sys.argv[1])))


if __name__ == "__main__":
    main()

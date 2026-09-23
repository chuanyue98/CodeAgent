"""跨引擎委派的运行记录：列表、详情、停止。

数据全在 ``delegation_runs`` 管的 run 目录里（worker 自写状态），这里只转发。
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Query

from core.services import delegation_runs
from core.web.case_convert import camelize

router = APIRouter(prefix="/api/delegations", tags=["delegations"])

#: 详情页只看输出末尾：进行中时看它在干什么，结束后结果里已有摘要。
_OUTPUT_TAIL_BYTES = 8192


def _output_tail(path: str | None) -> str:
    if not path:
        return ""
    try:
        with Path(path).open("rb") as f:
            f.seek(0, 2)
            size = f.tell()
            f.seek(max(0, size - _OUTPUT_TAIL_BYTES))
            return f.read().decode("utf-8", errors="replace")
    except OSError:
        return ""


def _get(run_id: str) -> dict:
    try:
        return delegation_runs.get_run(run_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None


@router.get("")
def list_delegations(
    workspace: str | None = None, limit: int = Query(50, ge=1, le=200)
) -> dict:
    runs = delegation_runs.list_runs(workspace=workspace, limit=limit)
    return {"runs": camelize(runs)}


@router.get("/{run_id}")
def get_delegation(run_id: str) -> dict:
    run = _get(run_id)
    run["output_tail"] = _output_tail(run.get("output_log"))
    return camelize(run)


@router.post("/{run_id}/stop")
def stop_delegation(run_id: str) -> dict:
    _get(run_id)
    if not delegation_runs.stop_run(run_id):
        raise HTTPException(status_code=409, detail="Delegation is not running")
    return {"success": True}

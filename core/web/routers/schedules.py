"""Web API router for CronPage: cron-triggered background task schedules.

Endpoints:
  GET    /api/schedules              List all schedules.
  GET    /api/schedules/preview      Validate a cron expression and preview
                                      its next few fire times (no persistence).
  POST   /api/schedules              Create a schedule.
  PATCH  /api/schedules/{id}         Update a schedule (cron_expr, enabled, ...).
  DELETE /api/schedules/{id}         Delete a schedule.
  POST   /api/schedules/{id}/run-now Fire a schedule's task immediately,
                                      independent of its cron timing.

Schedules are checked and fired by the background loop started in
core/web/server.py's lifespan (core/services/scheduler_loop.py) — this
router only manages the persisted schedule records themselves.
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from pathlib import Path

from fastapi import APIRouter, HTTPException

from core.constants import ENGINES
from core.services.config_service import ConfigService
from core.services.runner_service import TaskAlreadyRunningError
from core.services.schedule_service import ScheduleService
from core.web.case_convert import ProtocolModel, wire
from core.web.resource_paths import ROOT_DIR
from core.web.routers import tasks as tasks_router
from core.web.routers.config import get_config_path

router = APIRouter(prefix="/api", tags=["schedules"])


def _service() -> ScheduleService:
    return ScheduleService(ConfigService(get_config_path()))


class ParseScheduleRequest(ProtocolModel):
    """Request body for parsing natural language into schedule and task."""

    input: str
    engine: str = "claude"


class ParsedTask(ProtocolModel):
    """Structured task fields returned from natural language parsing."""

    name: str
    title: str
    objective: str
    context: str
    instructions: str
    verification: str


class ParseScheduleResponse(ProtocolModel):
    """Response returned from natural language parsing."""

    cron_expr: str
    cron_description: str
    next_runs: list[float]
    task: ParsedTask
    raw_output: str | None = None


class CreateScheduleRequest(ProtocolModel):
    """Request body for creating a schedule."""

    task_name: str
    engine: str
    group: str = "common"
    workspace: str
    cron_expr: str
    enabled: bool = True
    notify_on: str = "always"
    created_from_input: str | None = None


class UpdateScheduleRequest(ProtocolModel):
    """Request body for updating a schedule. Omitted fields are left as-is."""

    task_name: str | None = None
    engine: str | None = None
    group: str | None = None
    workspace: str | None = None
    cron_expr: str | None = None
    enabled: bool | None = None
    notify_on: str | None = None
    created_from_input: str | None = None


class TaskRunStatusResponse(ProtocolModel):
    """Wire shape for ``core.services.runner_service.TaskRunStatus``."""

    task_id: str
    engine: str
    pid: int | None = None
    status: str
    log_path: str
    start_time: float
    session_id: str | None = None
    workspace: str | None = None


class ScheduleRecord(ProtocolModel):
    """A persisted cron schedule."""

    id: str
    task_name: str
    engine: str
    group: str
    workspace: str | None = None
    cron_expr: str
    enabled: bool
    created_at: float
    last_run_at: float | None = None
    last_run_status: str | None = None
    next_run_at: float | None = None
    notify_on: str = "always"
    created_from_input: str | None = None


@router.get("/schedules")
def list_schedules() -> list[dict]:
    """Lists all cron schedules."""
    return [wire(ScheduleRecord(**record)) for record in _service().list_schedules()]


PARSE_TIMEOUT_SECONDS = 120

_PARSE_SCHEDULE_PROMPT = """你是 CodeAgent 的定时任务编排专家。把用户一句自然语言描述转换成结构化 JSON，只输出 JSON，不要多余文字。

输出严格符合以下 JSON（不要 markdown 代码围栏，不要其他文字）：
{{
  "cron_expr": "0 9 * * *",
  "name": "英文 slug",
  "title": "中文标题",
  "objective": "目标",
  "context": "背景",
  "instructions": "指令",
  "verification": "验证"
}}

自然语言：{input}

要求：
- cron_expr 必须是标准 5 段 cron 表达式（分 时 日 月 周），能用 croniter 解析
- name 只允许 [a-z][a-z0-9-]*，全小写
- objective/context/instructions/verification 任一不可为空
- 如果用户意图无法转成合法的 cron_expr，把 cron_expr 设为 "" 并在错误信息里说明原因"""

_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*\n?(.*?)```", re.DOTALL)
_SANITIZE_RE = re.compile(r"[^a-z0-9-]")


def _sanitize_name(name: str) -> str:
    s = name.strip().lower().replace(" ", "-").replace("_", "-")
    s = _SANITIZE_RE.sub("-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    if not s or not s[0].isalpha():
        s = f"task-{s}" if s else "nl-schedule"
    return s[:40]


def _cron_description(expr: str) -> str:
    parts = expr.strip().split()
    if len(parts) == 5:
        minute, hour, dom, month, dow = parts
        if dom == "*" and month == "*" and dow == "*":
            if minute.isdigit() and hour.isdigit():
                return f"每天 {int(hour):02d}:{int(minute):02d}"
        if dom == "*" and month == "*" and dow in ("1-5", "1,2,3,4,5"):
            if minute.isdigit() and hour.isdigit():
                return f"工作日 {int(hour):02d}:{int(minute):02d}"
    return expr


def _extract_json_from_text(text: str) -> dict | None:
    for m in _JSON_BLOCK_RE.finditer(text):
        try:
            val = json.loads(m.group(1).strip())
            if isinstance(val, dict):
                return val
        except (json.JSONDecodeError, ValueError):
            pass

    try:
        val = json.loads(text.strip())
        if isinstance(val, dict):
            if "cron_expr" in val or "cronExpr" in val:
                return val
    except (json.JSONDecodeError, ValueError):
        pass

    collected_lines: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
            if isinstance(obj, dict):
                if "cron_expr" in obj:
                    return obj
                for field in ("content", "text", "message", "delta"):
                    if field in obj and isinstance(obj[field], str):
                        collected_lines.append(obj[field])
        except (json.JSONDecodeError, ValueError):
            collected_lines.append(line)

    combined = "\n".join(collected_lines)
    for m in _JSON_BLOCK_RE.finditer(combined):
        try:
            val = json.loads(m.group(1).strip())
            if isinstance(val, dict):
                return val
        except (json.JSONDecodeError, ValueError):
            pass

    start = text.find("{")
    while start != -1:
        end = text.rfind("}")
        if end > start:
            snippet = text[start : end + 1]
            try:
                val = json.loads(snippet)
                if isinstance(val, dict) and ("cron_expr" in val or "name" in val):
                    return val
            except (json.JSONDecodeError, ValueError):
                pass
        start = text.find("{", start + 1)

    return None


@router.post("/schedules/parse")
async def parse_schedule(req: ParseScheduleRequest) -> dict:
    """Parses a natural language schedule description into structured task and cron."""
    if req.engine not in ENGINES:
        raise HTTPException(status_code=400, detail=f"Invalid engine: {req.engine!r}")
    if not req.input or not req.input.strip():
        raise HTTPException(status_code=400, detail="Input must not be empty")

    message = _PARSE_SCHEDULE_PROMPT.format(input=req.input.strip())

    try:
        status = await asyncio.to_thread(
            tasks_router._runner.run_chat_turn,
            req.engine,
            message,
            group="common",
            project_path=str(ROOT_DIR),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    deadline = time.time() + PARSE_TIMEOUT_SECONDS
    while time.time() < deadline:
        st = await asyncio.to_thread(tasks_router._runner.get_status, status.task_id)
        if st is None or st.status != "running":
            break
        await asyncio.sleep(0.2)

    log_path = Path(status.log_path)
    raw = ""
    if log_path.exists():
        try:
            raw = log_path.read_text(encoding="utf-8")
        except OSError:
            raw = ""

    parsed_json = _extract_json_from_text(raw)
    if parsed_json is None:
        return wire(
            ParseScheduleResponse(
                cron_expr="",
                cron_description="",
                next_runs=[],
                task=ParsedTask(
                    name=_sanitize_name(req.input),
                    title=req.input.strip()[:30],
                    objective="",
                    context="",
                    instructions="",
                    verification="",
                ),
                raw_output=raw[:2000] if raw else "No output produced",
            )
        )

    cron_expr = str(parsed_json.get("cron_expr", "")).strip()
    if not cron_expr:
        return wire(
            ParseScheduleResponse(
                cron_expr="",
                cron_description="",
                next_runs=[],
                task=ParsedTask(
                    name=_sanitize_name(str(parsed_json.get("name") or req.input)),
                    title=str(parsed_json.get("title") or req.input.strip()[:30]),
                    objective=str(parsed_json.get("objective", "")),
                    context=str(parsed_json.get("context", "")),
                    instructions=str(parsed_json.get("instructions", "")),
                    verification=str(parsed_json.get("verification", "")),
                ),
                raw_output=raw[:2000],
            )
        )

    try:
        next_runs = _service().preview_next_runs(cron_expr)
    except ValueError as exc:
        raise HTTPException(
            status_code=422, detail=f"Invalid cron expression: {cron_expr!r}"
        ) from exc

    name = _sanitize_name(str(parsed_json.get("name") or "nl-schedule"))
    task = ParsedTask(
        name=name,
        title=str(parsed_json.get("title") or name),
        objective=str(parsed_json.get("objective", "")),
        context=str(parsed_json.get("context", "")),
        instructions=str(parsed_json.get("instructions", "")),
        verification=str(parsed_json.get("verification", "")),
    )

    if not all([task.objective, task.context, task.instructions, task.verification]):
        raise HTTPException(
            status_code=422, detail="Missing required task fields in parsed result"
        )

    return wire(
        ParseScheduleResponse(
            cron_expr=cron_expr,
            cron_description=_cron_description(cron_expr),
            next_runs=next_runs[:3],
            task=task,
            raw_output=None,
        )
    )


@router.get("/schedules/preview")
def preview_schedule(cron_expr: str) -> dict:
    """Validates a cron expression and returns its next few fire times.

    Used by the schedule form for a live "next run" preview before the
    user saves anything -- an invalid expression is a normal, expected
    input while typing, not an error, so this returns `{"valid": False}`
    rather than a 4xx.
    """
    try:
        next_runs = _service().preview_next_runs(cron_expr)
        return {"valid": True, "nextRuns": next_runs}
    except ValueError:
        return {"valid": False, "nextRuns": []}


@router.post("/schedules")
def create_schedule(req: CreateScheduleRequest) -> dict:
    """Creates a new cron schedule targeting an existing file-based Task."""
    try:
        workspace = tasks_router.resolve_registered_workspace(req.workspace)
        record = _service().create_schedule(
            req.task_name,
            req.engine,
            workspace.group,
            req.cron_expr,
            req.enabled,
            workspace.path,
            notify_on=req.notify_on,
            created_from_input=req.created_from_input,
        )
        return wire(ScheduleRecord(**record))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch("/schedules/{schedule_id}")
def update_schedule(schedule_id: str, req: UpdateScheduleRequest) -> dict:
    """Updates a schedule's fields (e.g. toggling enabled, editing cron_expr)."""
    try:
        fields = req.model_dump(exclude_unset=True)
        existing = _service().get_schedule(schedule_id)
        if existing is None:
            raise KeyError(f"Schedule not found: {schedule_id}")
        workspace_value = fields.get("workspace")
        if workspace_value is not None:
            workspace = tasks_router.resolve_registered_workspace(workspace_value)
            fields["workspace"] = workspace.path
            fields["group"] = workspace.group
        elif fields.get("group") is not None and existing.get("workspace"):
            workspace = tasks_router.resolve_registered_workspace(existing["workspace"])
            fields["group"] = workspace.group
        updated = _service().update_schedule(schedule_id, **fields)
        return wire(ScheduleRecord(**updated))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/schedules/{schedule_id}")
def delete_schedule(schedule_id: str) -> dict:
    """Deletes a schedule."""
    try:
        _service().delete_schedule(schedule_id)
        return {"status": "ok"}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/schedules/{schedule_id}/run-now")
def run_now(schedule_id: str) -> dict:
    """Fires a schedule's task immediately, outside its normal cron timing."""
    service = _service()
    record = service.get_schedule(schedule_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Schedule not found")

    try:
        workspace = record.get("workspace")
        if not workspace:
            raise HTTPException(
                status_code=409,
                detail="Schedule has no workspace; edit it before running",
            )
        registered_workspace = tasks_router.resolve_registered_workspace(workspace)
        status = tasks_router._runner.run_task(
            record["task_name"],
            record["engine"],
            registered_workspace.group,
            tasks_root=tasks_router.get_tasks_root(),
            workspace=registered_workspace.path,
            prevent_overlap=True,
        )
    except TaskAlreadyRunningError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if getattr(status, "status", "running") != "running":
        failure_status = str(status.status)
        service.record_run(
            schedule_id,
            failure_status
            if failure_status.startswith("failed")
            else f"failed: {failure_status}",
            advance_schedule=False,
        )
    else:
        service.record_run(schedule_id, "started", advance_schedule=False)
    return wire(TaskRunStatusResponse(**status.__dict__))

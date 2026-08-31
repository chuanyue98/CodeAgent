"""实例管理：跨来源汇总当前活跃的 Agent 实例。

实例有三个来源：
- chat     —— agent gateway 的 Web 聊天会话（进程归 provider 共享，不可单独停止）
- terminal —— 浏览器 PTY 终端（routers/pty.py 的注册表，可停止）
- task     —— runner_service 的后台任务运行（tasks/chat 各有一个 runner 单例）
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request

from core.services.agent_protocol import SessionStatus
from core.web.case_convert import ProtocolModel, wire
from core.web.routers import pty as pty_router
from core.web.routers.chat import _runner as chat_runner
from core.web.routers.tasks import _runner as tasks_runner

router = APIRouter(prefix="/api/instances", tags=["instances"])


class Instance(ProtocolModel):
    kind: str
    id: str
    engine: str
    cwd: str
    title: str | None
    status: str
    pid: int | None
    started_at: str
    stoppable: bool
    # tmux 承载的浏览器终端即使断开也还在跑，可从本页重新接回。
    reattachable: bool = False


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=UTC).isoformat()


def _chat_instances(request: Request) -> list[Instance]:
    gateway = getattr(request.app.state, "agent_gateway", None)
    if gateway is None:
        return []
    instances = []
    for session in gateway.list_sessions(limit=200):
        if session.status == SessionStatus.CLOSED:
            continue
        instances.append(
            Instance(
                kind="chat",
                id=session.id,
                engine=session.provider,
                cwd=session.cwd,
                title=session.title,
                # 部分路径下 status 已被序列化成 str，两种形态都兼容。
                status=getattr(session.status, "value", session.status),
                pid=None,
                started_at=session.created_at.isoformat(),
                # 聊天会话的进程由 provider 适配器共享持有，没有可单独
                # 停止的实体；要终止只能删会话，那属于破坏性操作，不做。
                stoppable=False,
            )
        )
    return instances


async def _terminal_instances() -> list[Instance]:
    # 断开的终端（引擎还在 tmux 里跑）没有自己的 websocket 通知退出，
    # 借这次轮询清掉引擎已结束的条目。
    await pty_router.prune_detached_sessions()
    return [
        Instance(
            kind="terminal",
            id=entry["id"],
            engine=entry["engine"],
            cwd=entry["cwd"],
            title=None,
            status="running",
            pid=entry["pid"],
            started_at=entry["started_at"],
            stoppable=True,
            reattachable=bool(entry.get("tmux_name")),
        )
        for entry in pty_router.list_active_sessions()
    ]


def _task_instances() -> list[Instance]:
    instances = []
    # chat._runner 就是 tasks._runner 的共享单例（chat.py 里明示的
    # re-export），按对象去重避免每个任务出现两行。
    runners = {id(runner): runner for runner in (tasks_runner, chat_runner)}
    for runner in runners.values():
        for run in runner.list_runs():
            instances.append(
                Instance(
                    kind="task",
                    id=run.task_id,
                    engine=run.engine,
                    cwd=run.workspace or "",
                    title=None,
                    status=run.status,
                    pid=run.pid,
                    started_at=_iso(run.start_time),
                    stoppable=run.status == "running",
                )
            )
    return instances


@router.get("")
async def list_instances(request: Request) -> dict:
    instances = (
        _chat_instances(request)
        + await _terminal_instances()
        + _task_instances()
    )
    instances.sort(key=lambda item: item.started_at, reverse=True)
    return {"instances": [wire(instance) for instance in instances]}


@router.post("/{kind}/{instance_id}/stop")
async def stop_instance(kind: str, instance_id: str) -> dict:
    if kind == "terminal":
        success = await pty_router.stop_active_session(instance_id)
    elif kind == "task":
        # 两个 runner 是同一单例（见 _task_instances），调一个即可。
        success = tasks_runner.stop_task(instance_id)
    elif kind == "chat":
        raise HTTPException(
            status_code=400,
            detail="Chat sessions have no dedicated process to stop",
        )
    else:
        raise HTTPException(status_code=404, detail=f"Unknown instance kind: {kind}")
    if not success:
        raise HTTPException(status_code=404, detail="Instance not found")
    return {"success": True}

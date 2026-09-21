from __future__ import annotations

import asyncio
import json
from collections import deque
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from core.services.log_broker import LogSubscription
from core.web.case_convert import ProtocolModel, wire
from core.web.resource_paths import ROOT_DIR
from core.web.routers.tasks import _runner  # 与 tasks.py 共用的单例

router = APIRouter(prefix="/api/logs", tags=["logs"])

CA_TASK_LOGS_DIR = ROOT_DIR / ".ca_task_logs"

#: How long a log stream waits for the run to write before looking at the file
#: again. Runs this process launched are woken by their pump thread as soon as
#: output lands, so this is a safety net rather than the delivery mechanism;
#: runs with no pump (restored from the DB, written by another process) still
#: live on it, which is why it stays short.
_IDLE_POLL_SECONDS = 0.3


def _resolve_log_path(task_id: str) -> Path | None:
    safe = "".join(c for c in task_id if c.isalnum() or c in "._-")
    if not safe:
        return None
    path = CA_TASK_LOGS_DIR / f"{safe}.log"
    if not path.is_file():
        return None
    return path


class LogFile(ProtocolModel):
    task_id: str
    name: str
    size: int
    modified: int


def _list_log_files() -> list[dict]:
    files: list[dict] = []
    if not CA_TASK_LOGS_DIR.exists():
        return files
    for f in sorted(CA_TASK_LOGS_DIR.glob("*.log")):
        try:
            stat = f.stat()
            files.append(
                wire(
                    LogFile(
                        task_id=f.stem,
                        name=f.name,
                        size=stat.st_size,
                        modified=int(stat.st_mtime),
                    )
                )
            )
        except OSError:
            pass
    return files


def _read_log(path: Path, max_lines: int = 1000) -> str:
    try:
        with open(path, encoding="utf-8") as fh:
            lines = deque(fh, maxlen=max_lines)
            return "".join(lines)
    except Exception:
        return ""


@router.get("/files")
async def list_log_files():
    return await asyncio.to_thread(_list_log_files)


@router.get("/{task_id}")
async def get_log_file(task_id: str):
    path = _resolve_log_path(task_id)
    if path is None:
        raise HTTPException(status_code=404, detail="Log file not found")
    content = await asyncio.to_thread(_read_log, path)
    return {"taskId": task_id, "content": content}


def _size_of(path: Path) -> int | None:
    """Current size of *path*, or None once it can no longer be read."""
    try:
        return path.stat().st_size
    except OSError:
        return None


def _read_from(path: Path, offset: int) -> str:
    with open(path, encoding="utf-8") as fh:
        fh.seek(offset)
        return fh.read()


async def _wait_for_output(subscription: LogSubscription | None) -> None:
    """Blocks until the run writes again, or the fallback interval elapses.

    A run this process launched has a pump thread that wakes us the moment a
    chunk lands on disk; anything else has no such signal and keeps the timer.
    """
    if subscription is None:
        await asyncio.sleep(_IDLE_POLL_SECONDS)
        return
    await subscription.wait(_IDLE_POLL_SECONDS)


@router.get("/{task_id}/stream")
async def stream_log_file(task_id: str):
    """Streams one run's log over SSE, ending with a ``done`` event when it stops.

    Only new bytes are sent; the existing contents come from ``GET /{task_id}``,
    which the viewer fetches alongside this.

    The file is still the source of truth -- offsets keep a slow client from
    losing bytes and keep the buffer bounded -- but for a run this process
    launched, the wait between reads is a wake-up from the run's stdout pump
    rather than a timer, so a chunk reaches the viewer as it is written.
    """
    path = _resolve_log_path(task_id)
    if path is None:
        raise HTTPException(status_code=404, detail="Log file not found")

    is_live = _runner.log_broker.is_live(task_id)

    async def event_generator():
        subscription = _runner.log_broker.subscribe(task_id) if is_live else None
        try:
            last_size = await asyncio.to_thread(_size_of, path)
            if last_size is None:
                yield "data: {}\n\n"
                return

            while True:
                # 先复位再读文件：这样「复位」与「等待」之间落盘的字节要么被
                # 本轮读取带走，要么已经把标志置上，不会漏掉一次唤醒。
                if subscription is not None:
                    subscription.arm()

                # A finished run is read once more before the loop exits, so the
                # last lines written between the previous poll and the exit are
                # not lost to the race.
                run = await asyncio.to_thread(_runner.get_run, task_id)
                finished_as = (
                    None if run is None or run.status == "running" else run.status
                )

                current_size = await asyncio.to_thread(_size_of, path)
                if current_size is None:
                    yield 'data: {"error": "file removed"}\n\n'
                    return

                if current_size != last_size:
                    try:
                        new_data = await asyncio.to_thread(_read_from, path, last_size)
                    except OSError:
                        yield 'data: {"error": "read failed"}\n\n'
                        return
                    if new_data:
                        yield f"data: {json.dumps({'content': new_data, 'size': current_size})}\n\n"
                    last_size = current_size
                    continue

                if finished_as is not None:
                    # One last read, taken after the run was seen to stop: a
                    # process can still be flushing when its status flips, and
                    # those bytes have no later poll to catch them.
                    final_size = await asyncio.to_thread(_size_of, path)
                    if final_size is not None and final_size != last_size:
                        try:
                            tail = await asyncio.to_thread(_read_from, path, last_size)
                        except OSError:
                            tail = ""
                        if tail:
                            yield f"data: {json.dumps({'content': tail, 'size': final_size})}\n\n"

                    # Without this the stream polls a completed run forever, and
                    # the viewer keeps claiming to be following a live log.
                    yield f"event: done\ndata: {json.dumps({'status': finished_as})}\n\n"
                    return

                await _wait_for_output(subscription)
        finally:
            if subscription is not None:
                subscription.release()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )

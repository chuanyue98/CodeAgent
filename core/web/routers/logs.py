from __future__ import annotations

import asyncio
import codecs
import hashlib
import json
import os
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from core.runtime_paths import get_run_dir
from core.services.log_broker import LogSubscription
from core.web.case_convert import ProtocolModel, wire
from core.web.routers.tasks import _runner  # 与 tasks.py 共用的单例

router = APIRouter(prefix="/api/logs", tags=["logs"])

CA_TASK_LOGS_DIR: Path | None = None


def _log_dir() -> Path:
    return CA_TASK_LOGS_DIR if CA_TASK_LOGS_DIR is not None else get_run_dir()


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
    path = _log_dir() / f"{safe}.log"
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
    if not _log_dir().exists():
        return files
    for f in sorted(_log_dir().glob("*.log")):
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


@router.get("/files")
async def list_log_files():
    return await asyncio.to_thread(_list_log_files)


@router.get("/{task_id}")
async def get_log_file(task_id: str):
    path = _resolve_log_path(task_id)
    if path is None:
        raise HTTPException(status_code=404, detail="Log file not found")
    try:
        content, cursor, _ = await asyncio.to_thread(_read_chunk, path, None)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Log file not found") from exc
    return {"taskId": task_id, "content": content, "cursor": cursor}


_CHUNK_BYTES = 1024 * 1024


def _read_chunk(
    path: Path, cursor: str | None, *, final: bool = False
) -> tuple[str, str, bool]:
    """内容、实际消费位置和换代标记来自同一个文件句柄；不消费半个 UTF-8 字符。"""
    with path.open("rb") as stream:
        stat = os.fstat(stream.fileno())
        identity = f"{stat.st_dev}-{stat.st_ino}"
        reset = False
        offset = 0
        if cursor is not None:
            try:
                previous, raw_offset, digest = cursor.split(":")
                offset = int(raw_offset)
                if offset < 0:
                    raise ValueError
            except ValueError as exc:
                raise ValueError("Invalid log cursor") from exc
            stream.seek(max(0, offset - 32))
            anchor = stream.read(min(offset, 32))
            reset = (
                previous != identity
                or offset > stat.st_size
                or hashlib.sha256(anchor).hexdigest()[:16] != digest
            )
        if cursor is None or reset:
            offset = max(0, stat.st_size - _CHUNK_BYTES)
        stream.seek(offset)
        raw = stream.read(_CHUNK_BYTES)
        decoder = codecs.getincrementaldecoder("utf-8")("replace")
        text = decoder.decode(raw, final=final)
        pending, _ = decoder.getstate()
        offset += len(raw) - len(pending)
        if cursor is None or reset:
            # 快照只保留末尾行，字节位置仍对应完整读取位置。
            text = "".join(text.splitlines(keepends=True)[-1000:])
        stream.seek(max(0, offset - 32))
        digest = hashlib.sha256(stream.read(min(offset, 32))).hexdigest()[:16]
        return text.replace("\r\n", "\n"), f"{identity}:{offset}:{digest}", reset


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
async def stream_log_file(
    task_id: str,
    request: Request = None,  # type: ignore[assignment]
    cursor: str | None = None,
):
    """以快照游标或浏览器 Last-Event-ID 续传；换代时发送新的快照。"""
    path = _resolve_log_path(task_id)
    if path is None:
        raise HTTPException(status_code=404, detail="Log file not found")
    resume = (
        request.headers.get("last-event-id") if request is not None else None
    ) or cursor
    if resume is not None:
        try:
            _, offset, _ = resume.split(":")
            if int(offset) < 0:
                raise ValueError
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid log cursor") from exc

    if resume is None:
        try:
            _, resume, _ = await asyncio.to_thread(_read_chunk, path, None)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Log file not found") from exc

    async def event_generator():
        subscription = _runner.log_broker.subscribe(task_id)
        try:
            position = resume
            while True:
                subscription.arm()
                run = await asyncio.to_thread(_runner.get_run, task_id)
                finished = (
                    None if run is None or run.status == "running" else run.status
                )
                try:
                    content, next_position, reset = await asyncio.to_thread(
                        _read_chunk, path, position, final=finished is not None
                    )
                except OSError:
                    yield 'data: {"error": "file removed"}\n\n'
                    return
                changed = next_position != position
                position = next_position
                if content or reset:
                    event = "event: reset\n" if reset else ""
                    payload = json.dumps({"content": content, "cursor": position})
                    yield f"{event}id: {position}\ndata: {payload}\n\n"
                if changed:
                    continue
                if finished is not None:
                    yield f"event: done\ndata: {json.dumps({'status': finished})}\n\n"
                    return
                await _wait_for_output(subscription)
        finally:
            subscription.release()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

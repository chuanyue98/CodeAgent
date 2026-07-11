from __future__ import annotations

import asyncio
import json
from collections import deque
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

router = APIRouter(prefix="/api/logs", tags=["logs"])

CA_TASK_LOGS_DIR = Path(__file__).resolve().parent.parent.parent / ".ca_task_logs"


def _resolve_log_path(task_id: str) -> Path | None:
    safe = "".join(c for c in task_id if c.isalnum() or c in "._-")
    if not safe:
        return None
    path = CA_TASK_LOGS_DIR / f"{safe}.log"
    if not path.is_file():
        return None
    return path


def _list_log_files() -> list[dict]:
    files: list[dict] = []
    if not CA_TASK_LOGS_DIR.exists():
        return files
    for f in sorted(CA_TASK_LOGS_DIR.glob("*.log")):
        try:
            stat = f.stat()
            files.append(
                {
                    "task_id": f.stem,
                    "name": f.name,
                    "size": stat.st_size,
                    "modified": int(stat.st_mtime),
                }
            )
        except OSError:
            pass
    return files


def _read_log(path: Path, max_lines: int = 1000) -> str:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            lines = deque(fh, maxlen=max_lines)
            return "".join(lines)
    except Exception:
        return ""


@router.get("/files")
async def list_log_files():
    return _list_log_files()


@router.get("/{task_id}")
async def get_log_file(task_id: str):
    path = _resolve_log_path(task_id)
    if path is None:
        return {"detail": "Log file not found"}, 404
    content = _read_log(path)
    return {"task_id": task_id, "content": content}


@router.get("/{task_id}/stream")
async def stream_log_file(task_id: str):
    path = _resolve_log_path(task_id)
    if path is None:
        return {"detail": "Log file not found"}, 404

    async def event_generator():
        last_size = 0
        try:
            last_size = path.stat().st_size
        except OSError:
            yield "data: {}\n\n"
            return

        while True:
            try:
                current_size = path.stat().st_size
            except OSError:
                yield 'data: {"error": "file removed"}\n\n'
                break

            if current_size != last_size:
                try:
                    with open(path, "r", encoding="utf-8") as fh:
                        fh.seek(last_size)
                        new_data = fh.read()
                        if new_data:
                            yield f"data: {json.dumps({'content': new_data, 'size': current_size})}\n\n"
                except Exception:
                    yield 'data: {"error": "read failed"}\n\n'
                    break
                last_size = current_size

            await asyncio.sleep(0.3)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )

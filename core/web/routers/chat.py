"""Web API router for ChatPage: one-shot, resumable turns against each engine CLI.

Endpoints:
  POST /api/chat/turns
      Starts one headless turn in the background (new session, or resuming
      an existing one via ``session_id`` — see docs/chatpage-cli-spike-results.md
      for which engines actually carry context forward on resume).

  GET  /api/chat/turns/{turn_id}
      Polls the current status of a turn (running/completed/failed).

  GET  /api/chat/turns/{turn_id}/stream
      SSE stream of the turn's raw JSON(L) engine events, one per line,
      terminated by a ``done`` event once the process exits and the log
      file stops growing.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from fastapi.responses import StreamingResponse

from core.services.runner_service import TaskRunner
from core.web.resource_paths import ROOT_DIR

router = APIRouter(prefix="/api/chat", tags=["chat"])

# Separate singleton from tasks.py's — chat turns (.jsonl) and task runs
# (.log) are distinct entities tracked under distinct id prefixes/log
# extensions, so there's no need to share one instance's in-memory dicts.
_runner = TaskRunner(ROOT_DIR)


class StartChatTurnRequest(BaseModel):
    """Request body for starting one ChatPage turn."""

    engine: str
    message: str
    session_id: str | None = None
    group: str = "common"


@router.post("/turns")
async def start_chat_turn(req: StartChatTurnRequest) -> dict:
    """Starts one headless turn in the background.

    Args:
        req: The turn request (engine, message, optional resume session_id).

    Returns:
        dict: The initial TaskRunStatus (running, with the log path to poll/stream).
    """
    try:
        return _runner.run_chat_turn(
            req.engine,
            req.message,
            session_id=req.session_id,
            group=req.group,
        ).__dict__
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/turns/{turn_id}")
async def get_chat_turn(turn_id: str) -> dict:
    """Polls the current status of a chat turn.

    Args:
        turn_id: The turn id returned by ``POST /turns``.

    Returns:
        dict: The current TaskRunStatus, including ``session_id`` once known.
    """
    status = _runner.get_status(turn_id)
    if not status:
        raise HTTPException(status_code=404, detail="Turn not found")
    return status.__dict__


@router.get("/turns/{turn_id}/stream")
async def stream_chat_turn(turn_id: str):
    """Streams a chat turn's engine events over SSE, one JSON line per event.

    Args:
        turn_id: The turn id returned by ``POST /turns``.

    Returns:
        StreamingResponse: text/event-stream of engine JSON events, ending
        with a ``done`` event once the process has exited.
    """
    status = _runner.get_status(turn_id)
    if not status:
        raise HTTPException(status_code=404, detail="Turn not found")

    path = Path(status.log_path)

    async def event_generator():
        last_size = 0
        buffer = ""

        while True:
            current_status = _runner.get_status(turn_id)
            try:
                current_size = path.stat().st_size
            except OSError:
                yield 'data: {"error": "log file removed"}\n\n'
                return

            if current_size != last_size:

                def _read_new_bytes(p: Path = path, offset: int = last_size) -> str:
                    with open(p, "r", encoding="utf-8") as fh:
                        fh.seek(offset)
                        return fh.read()

                try:
                    new_data = await asyncio.to_thread(_read_new_bytes)
                except Exception:
                    yield 'data: {"error": "read failed"}\n\n'
                    return

                last_size = current_size
                buffer += new_data
                lines = buffer.split("\n")
                buffer = lines.pop()  # keep the possibly-incomplete trailing line
                for line in lines:
                    line = line.strip()
                    if line:
                        yield f"data: {line}\n\n"

            if (
                current_status is not None
                and current_status.status != "running"
                and current_size == last_size
            ):
                trailing = buffer.strip()
                if trailing:
                    yield f"data: {trailing}\n\n"
                done_payload = {
                    "status": current_status.status,
                    "session_id": current_status.session_id,
                }
                yield f"event: done\ndata: {json.dumps(done_payload)}\n\n"
                return

            await asyncio.sleep(0.3)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )

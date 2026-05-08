from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter()

_SHELL: list[str] = (
    ["powershell.exe"]
    if sys.platform == "win32"
    else [shutil.which("bash") or "/bin/sh"]
)


@router.websocket("/ws/terminal")
async def terminal_ws(websocket: WebSocket) -> None:
    await websocket.accept()
    try:
        if sys.platform == "win32":
            await _session_windows(websocket)
        else:
            await _session_unix(websocket)
    except WebSocketDisconnect:
        pass
    except Exception:
        pass


# ── Unix ──────────────────────────────────────────────────────────────────


async def _session_unix(websocket: WebSocket) -> None:
    import fcntl
    import pty
    import struct
    import termios

    master_fd, slave_fd = pty.openpty()
    proc = await asyncio.create_subprocess_exec(
        *_SHELL,
        stdin=slave_fd,
        stdout=slave_fd,
        stderr=slave_fd,
        preexec_fn=os.setsid,
    )
    os.close(slave_fd)
    loop = asyncio.get_event_loop()

    async def _read() -> None:
        while True:
            try:
                data = await loop.run_in_executor(None, os.read, master_fd, 4096)
                await websocket.send_bytes(data)
            except OSError:
                break

    async def _write() -> None:
        while True:
            try:
                msg = await websocket.receive()
                if msg["type"] == "websocket.disconnect":
                    break
                raw: bytes = msg.get("bytes") or (msg.get("text") or "").encode()
                try:
                    ctrl = json.loads(raw)
                    if ctrl.get("type") == "resize":
                        winsize = struct.pack("HHHH", ctrl["rows"], ctrl["cols"], 0, 0)
                        fcntl.ioctl(master_fd, termios.TIOCSWINSZ, winsize)
                        continue
                except (json.JSONDecodeError, KeyError, ValueError):
                    pass
                os.write(master_fd, raw)
            except Exception:
                break

    read_task = asyncio.create_task(_read())
    write_task = asyncio.create_task(_write())
    try:
        _done, pending = await asyncio.wait(
            [read_task, write_task], return_when=asyncio.FIRST_COMPLETED
        )
        for t in pending:
            t.cancel()
            try:
                await t
            except asyncio.CancelledError:
                pass
    finally:
        proc.kill()
        try:
            os.close(master_fd)
        except OSError:
            pass


# ── Windows ───────────────────────────────────────────────────────────────


async def _session_windows(websocket: WebSocket) -> None:
    import winpty  # type: ignore[import]

    proc = winpty.PtyProcess.spawn(" ".join(_SHELL))
    loop = asyncio.get_event_loop()

    async def _read() -> None:
        while proc.isalive():
            try:
                data = await loop.run_in_executor(None, proc.read, 4096)
                if data:
                    await websocket.send_text(data)
            except Exception:
                break

    async def _write() -> None:
        while True:
            try:
                msg = await websocket.receive()
                if msg["type"] == "websocket.disconnect":
                    break
                text: str = msg.get("text") or (msg.get("bytes") or b"").decode()
                try:
                    ctrl = json.loads(text)
                    if ctrl.get("type") == "resize":
                        proc.setwinsize(ctrl["rows"], ctrl["cols"])
                        continue
                except (json.JSONDecodeError, KeyError, ValueError):
                    pass
                proc.write(text)
            except Exception:
                break

    read_task = asyncio.create_task(_read())
    write_task = asyncio.create_task(_write())
    try:
        _done, pending = await asyncio.wait(
            [read_task, write_task], return_when=asyncio.FIRST_COMPLETED
        )
        for t in pending:
            t.cancel()
            try:
                await t
            except asyncio.CancelledError:
                pass
    finally:
        proc.terminate()

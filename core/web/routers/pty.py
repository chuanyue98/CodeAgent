"""Browser-based PTY sessions for the interactive terminal launcher.

Spawns the same engine command the native-terminal launcher (``launch.py``)
uses, but attaches it to a pseudo-terminal streamed over a WebSocket instead
of a separate GUI terminal window, so the CLI is usable directly in the
browser.
"""

from __future__ import annotations

import asyncio
import codecs
import contextlib
import os
import struct
import sys
from pathlib import Path

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

try:
    # POSIX-only; core/web/server.py imports this router unconditionally,
    # so a top-level import failure here would crash the whole server on
    # Windows before pty_capability()'s own platform check ever runs.
    import fcntl
    import termios
except ImportError:  # pragma: no cover - exercised only on Windows
    fcntl = None  # type: ignore[assignment]
    termios = None  # type: ignore[assignment]

from core.services.config_service import ConfigService
from core.web.routers.config import get_config_path
from core.web.routers.launch import ENGINES, _CA_LAUNCHER

router = APIRouter(prefix="/api/pty", tags=["pty"])

_READ_CHUNK = 65536


def pty_capability() -> dict:
    """Reports whether this server can attach a browser-streamed PTY."""
    if sys.platform == "win32":
        return {
            "available": False,
            "reason": "Browser terminal is not supported on Windows yet",
        }
    return {"available": True, "reason": None}


@router.get("/status")
async def get_pty_status() -> dict:
    return pty_capability()


def _resolve_registered_workspace(cwd: str) -> Path:
    config, warnings = ConfigService(get_config_path()).get_config()
    if warnings:
        raise ValueError(warnings[0])
    requested = Path(cwd).expanduser().resolve()
    if not requested.is_dir():
        raise ValueError("Selected workspace is unavailable")
    for project in config.get("project_registry", []):
        if not isinstance(project, dict) or not isinstance(project.get("path"), str):
            continue
        if Path(project["path"]).expanduser().resolve() == requested:
            return requested
    raise ValueError(
        "Select a workspace registered in Settings before opening a terminal"
    )


def _resize(fd: int, cols: int, rows: int) -> None:
    with contextlib.suppress(OSError):
        fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))


@router.websocket("/ws")
async def pty_websocket(
    websocket: WebSocket,
    engine: str = Query(...),
    cwd: str = Query(...),
) -> None:
    if sys.platform == "win32":
        await websocket.close(
            code=1013, reason="Browser terminal is not supported on Windows"
        )
        return
    if engine not in ENGINES:
        await websocket.close(code=4400, reason=f"Unknown engine: {engine}")
        return
    try:
        working_dir = _resolve_registered_workspace(cwd)
    except ValueError as exc:
        await websocket.close(code=4400, reason=str(exc))
        return

    await websocket.accept()

    import pty  # POSIX-only; imported lazily so the module still loads on Windows.

    master_fd, slave_fd = pty.openpty()
    _resize(master_fd, cols=80, rows=24)
    env = {
        **os.environ,
        "TERM": "xterm-256color",
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
    }

    try:
        try:
            process = await asyncio.create_subprocess_exec(
                sys.executable,
                str(_CA_LAUNCHER),
                engine,
                stdin=slave_fd,
                stdout=slave_fd,
                stderr=slave_fd,
                cwd=str(working_dir),
                env=env,
                start_new_session=True,
            )
        finally:
            os.close(slave_fd)
    except BaseException as exc:
        # Spawn failed (e.g. out of file descriptors/processes) or the await
        # was cancelled (e.g. the client vanished mid-connect -- raised as
        # asyncio.CancelledError, a BaseException, not an Exception, so it
        # must be caught here too). Either way the slave fd is already
        # closed above, but master_fd was opened before this try and
        # nothing else owns it yet, so it must be closed here or it leaks
        # for the life of the server process.
        with contextlib.suppress(OSError):
            os.close(master_fd)
        if not isinstance(exc, OSError):
            raise
        with contextlib.suppress(Exception):
            await websocket.close(code=1011, reason=f"Failed to start session: {exc}")
        return

    loop = asyncio.get_running_loop()
    output_queue: asyncio.Queue[bytes | None] = asyncio.Queue()

    def _on_readable() -> None:
        try:
            chunk = os.read(master_fd, _READ_CHUNK)
        except OSError:
            chunk = b""
        if not chunk:
            with contextlib.suppress(ValueError):
                loop.remove_reader(master_fd)
            output_queue.put_nowait(None)
            return
        output_queue.put_nowait(chunk)

    loop.add_reader(master_fd, _on_readable)
    decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")

    async def pump_output() -> None:
        while True:
            chunk = await output_queue.get()
            if chunk is None:
                return
            with contextlib.suppress(Exception):
                await websocket.send_json(
                    {"type": "output", "data": decoder.decode(chunk)}
                )

    process_exited = asyncio.Event()

    async def pump_exit() -> None:
        returncode = await process.wait()
        # _on_readable removes the reader and signals pump_output itself
        # once it sees real EOF on the PTY master. Wait for that natural
        # drain here (shielded so our own timeout below can't cancel it)
        # instead of tearing the reader down ourselves right away, or any
        # output still buffered in the kernel when the process exits would
        # race with -- and often lose to -- this task, truncating the
        # tail of the output. Bounded in case an orphaned descendant still
        # holds the slave fd open and EOF never naturally arrives.
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(asyncio.shield(output_task), timeout=2)
        with contextlib.suppress(Exception):
            await websocket.send_json({"type": "exit", "code": returncode})
        process_exited.set()

    output_task = asyncio.create_task(pump_output())
    exit_task = asyncio.create_task(pump_exit())
    exit_wait_task = asyncio.create_task(process_exited.wait())

    try:
        while not process_exited.is_set():
            receive_task = asyncio.ensure_future(websocket.receive_json())
            done, pending = await asyncio.wait(
                {receive_task, exit_wait_task}, return_when=asyncio.FIRST_COMPLETED
            )
            if exit_wait_task in done:
                receive_task.cancel()
                with contextlib.suppress(Exception, asyncio.CancelledError):
                    await receive_task
                break
            message = receive_task.result()
            if not isinstance(message, dict):
                continue
            kind = message.get("type")
            if kind == "input":
                data = message.get("data")
                if isinstance(data, str):
                    with contextlib.suppress(OSError):
                        os.write(master_fd, data.encode())
            elif kind == "resize":
                cols, rows = message.get("cols"), message.get("rows")
                if isinstance(cols, int) and isinstance(rows, int):
                    _resize(master_fd, cols, rows)
    except WebSocketDisconnect:
        pass
    finally:
        exit_wait_task.cancel()
        with contextlib.suppress(Exception, asyncio.CancelledError):
            await exit_wait_task
        with contextlib.suppress(ValueError):
            loop.remove_reader(master_fd)
        if process.returncode is None:
            with contextlib.suppress(ProcessLookupError):
                process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=3)
            except TimeoutError:
                with contextlib.suppress(ProcessLookupError):
                    process.kill()
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(process.wait(), timeout=5)
        exit_task.cancel()
        output_task.cancel()
        await asyncio.gather(exit_task, output_task, return_exceptions=True)
        with contextlib.suppress(OSError):
            os.close(master_fd)
        with contextlib.suppress(Exception):
            await websocket.close()

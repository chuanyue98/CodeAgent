"""Browser-based PTY sessions for the interactive terminal launcher.

Spawns the same engine command the native-terminal launcher (``launch.py``)
uses, but attaches it to a pseudo-terminal streamed over a WebSocket instead
of a separate GUI terminal window, so the CLI is usable directly in the
browser. POSIX uses the standard library's `pty` module; Windows uses
ConPTY via `pywinpty`. Both paths converge on the same `output_queue` /
`pump_output` machinery below, so the message loop and cleanup logic don't
need to branch on platform.
"""

from __future__ import annotations

import asyncio
import codecs
import contextlib
import os
import struct
import subprocess
import sys
import threading
from pathlib import Path
from typing import Protocol

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

try:
    # Windows-only; see the try/except above for why this must not be a
    # top-level hard import.
    import winpty
except ImportError:  # pragma: no cover - exercised only on POSIX
    winpty = None  # type: ignore[assignment]

from core.services.config_service import ConfigService
from core.web.routers.config import get_config_path
from core.web.routers.launch import _CA_LAUNCHER, ENGINES
from core.web.security import verify_websocket

router = APIRouter(prefix="/api/pty", tags=["pty"])

_READ_CHUNK = 65536


def pty_capability() -> dict:
    """Reports whether this server can attach a browser-streamed PTY."""
    if sys.platform == "win32" and winpty is None:
        return {
            "available": False,
            "reason": "pywinpty is not installed",
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


# ── Uniform session interface ─────────────────────────────────────────────
#
# The websocket handler below is written once against this interface; the
# POSIX and Windows implementations each push decoded output text into the
# same `output_queue` (POSIX pushes raw bytes through an incremental UTF-8
# decoder in pump_output; Windows' `PtyProcess.read()` already returns
# decoded str, so its chunks skip that decoder) and post `None` to signal
# EOF, exactly like the original POSIX-only implementation did.


class PtySession(Protocol):
    def write(self, data: str) -> None: ...
    def resize(self, cols: int, rows: int) -> None: ...
    async def wait(self) -> int:
        """Blocks until the child exits and returns its exit code."""
        ...

    async def terminate(self) -> None: ...
    async def kill(self) -> None: ...
    async def close(self) -> None: ...
    @property
    def returncode(self) -> int | None: ...


class SpawnError(Exception):
    """Raised when a PTY session could not be started."""


def _resize_fd(fd: int, cols: int, rows: int) -> None:
    with contextlib.suppress(OSError):
        fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))


class _PosixSession:
    def __init__(self, process, master_fd: int):
        self._process = process
        self._master_fd = master_fd

    def write(self, data: str) -> None:
        with contextlib.suppress(OSError):
            os.write(self._master_fd, data.encode())

    def resize(self, cols: int, rows: int) -> None:
        _resize_fd(self._master_fd, cols, rows)

    async def wait(self) -> int:
        return await self._process.wait()

    async def terminate(self) -> None:
        with contextlib.suppress(ProcessLookupError):
            self._process.terminate()

    async def kill(self) -> None:
        with contextlib.suppress(ProcessLookupError):
            self._process.kill()

    async def close(self) -> None:
        with contextlib.suppress(OSError):
            os.close(self._master_fd)

    @property
    def returncode(self) -> int | None:
        return self._process.returncode


async def _spawn_posix(
    engine: str, working_dir: Path, output_queue: asyncio.Queue[bytes | str | None]
) -> _PosixSession:
    import pty  # POSIX-only; imported lazily so the module still loads on Windows.

    master_fd, slave_fd = pty.openpty()
    _resize_fd(master_fd, cols=80, rows=24)
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
        # Only a genuine spawn failure (OSError) becomes a clean websocket
        # close via SpawnError -- cancellation must propagate unwrapped so
        # it keeps behaving like real task cancellation for the caller.
        if not isinstance(exc, OSError):
            raise
        raise SpawnError(str(exc)) from exc

    loop = asyncio.get_running_loop()

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
    return _PosixSession(process, master_fd)


class _WindowsSession:  # pragma: no cover - exercised only on Windows
    def __init__(self, pty_process, loop: asyncio.AbstractEventLoop, output_queue):
        self._pty = pty_process
        self._loop = loop
        self._queue = output_queue
        self._returncode: int | None = None
        # Set by close() before it tears down the pty, so the reader thread
        # (whose blocking read() unblocks once the pty closes) knows not to
        # post into a queue tied to a loop that may already be shutting
        # down, rather than racing that shutdown.
        self._closing = threading.Event()
        self._reader_thread = threading.Thread(
            target=self._read_loop, daemon=True, name="pty-windows-reader"
        )
        self._reader_thread.start()

    def _read_loop(self) -> None:
        while True:
            try:
                data = self._pty.read(_READ_CHUNK)
            except EOFError:
                data = ""
            except Exception:
                data = ""
            if self._closing.is_set():
                return
            with contextlib.suppress(RuntimeError):
                self._loop.call_soon_threadsafe(self._queue.put_nowait, data or None)
            if not data:
                return

    def write(self, data: str) -> None:
        with contextlib.suppress(Exception):
            self._pty.write(data)

    def resize(self, cols: int, rows: int) -> None:
        with contextlib.suppress(Exception):
            self._pty.setwinsize(rows, cols)

    async def wait(self) -> int:
        # PtyProcess.wait() blocks the calling thread, so it must run off
        # the event loop -- otherwise it would stall every other
        # connection/request this server is handling until the child exits.
        code = await asyncio.to_thread(self._pty.wait)
        self._returncode = code if isinstance(code, int) else 0
        return self._returncode

    async def _kill_process_tree(self) -> None:
        # PtyProcess.terminate() only signals the one PID it directly
        # spawned. On this and apparently many Windows Python setups,
        # sys.executable is a thin relauncher that immediately re-execs a
        # child process to run the real interpreter -- killing just the
        # tracked PID leaves that child (the one actually running the
        # engine) orphaned and still running. `taskkill /T` kills the whole
        # tree, so it's used unconditionally rather than trusting
        # PtyProcess's own single-PID terminate/kill.
        pid = self._pty.pid
        if pid is None:
            return
        with contextlib.suppress(Exception):
            await asyncio.to_thread(
                subprocess.run,
                ["taskkill", "/T", "/F", "/PID", str(pid)],
                capture_output=True,
            )

    async def terminate(self) -> None:
        await self._kill_process_tree()

    async def kill(self) -> None:
        await self._kill_process_tree()

    async def close(self) -> None:
        self._closing.set()
        with contextlib.suppress(Exception):
            await asyncio.to_thread(self._pty.close, True)
        # Wait for the reader thread to actually exit (its blocking read()
        # call unblocks once the pty closes above) so it can't outlive this
        # coroutine and post into a queue tied to a loop that's already
        # shutting down.
        await asyncio.to_thread(self._reader_thread.join, 3)

    @property
    def returncode(self) -> int | None:
        if self._returncode is not None:
            return self._returncode
        with contextlib.suppress(Exception):
            if not self._pty.isalive():
                self._returncode = self._pty.exitstatus or 0
        return self._returncode


async def _spawn_windows(  # pragma: no cover - exercised only on Windows
    engine: str, working_dir: Path, output_queue: asyncio.Queue[bytes | str | None]
) -> _WindowsSession:
    loop = asyncio.get_running_loop()
    env = {**os.environ, "TERM": "xterm-256color"}
    try:
        # PtyProcess.spawn() does a PATH lookup + creates the ConPTY
        # synchronously; it's fast, but run it off-thread anyway so a slow
        # PATH lookup on a loaded machine can't stall the event loop.
        pty_process = await asyncio.to_thread(
            winpty.PtyProcess.spawn,
            [sys.executable, str(_CA_LAUNCHER), engine],
            cwd=str(working_dir),
            env=env,
            dimensions=(24, 80),
        )
    except Exception as exc:
        raise SpawnError(str(exc)) from exc
    return _WindowsSession(pty_process, loop, output_queue)


@router.websocket("/ws")
async def pty_websocket(
    websocket: WebSocket,
    engine: str = Query(...),
    cwd: str = Query(...),
) -> None:
    # Authenticate before anything else: this endpoint hands the caller an
    # interactive shell, and a WebSocket handshake is not subject to the
    # same-origin policy, so without this any page the user visits could
    # open one. verify_websocket() closes the socket itself on failure.
    if not await verify_websocket(websocket):
        return
    capability = pty_capability()
    if not capability["available"]:
        await websocket.close(code=1013, reason=capability["reason"])
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

    output_queue: asyncio.Queue[bytes | str | None] = asyncio.Queue()

    try:
        if sys.platform == "win32":  # pragma: no cover - exercised only on Windows
            session: PtySession = await _spawn_windows(
                engine, working_dir, output_queue
            )
        else:
            session = await _spawn_posix(engine, working_dir, output_queue)
    except SpawnError as exc:
        with contextlib.suppress(Exception):
            await websocket.close(code=1011, reason=f"Failed to start session: {exc}")
        return

    decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")

    async def pump_output() -> None:
        while True:
            chunk = await output_queue.get()
            if chunk is None:
                return
            text = decoder.decode(chunk) if isinstance(chunk, bytes) else chunk
            with contextlib.suppress(Exception):
                await websocket.send_json({"type": "output", "data": text})

    process_exited = asyncio.Event()

    async def pump_exit() -> None:
        returncode = await session.wait()
        # The reader (POSIX: _on_readable, Windows: _read_loop) signals
        # pump_output itself once it sees real EOF. Wait for that natural
        # drain here (shielded so our own timeout below can't cancel it)
        # instead of tearing things down right away, or any output still
        # buffered when the process exits would race with -- and often
        # lose to -- this task, truncating the tail of the output. Bounded
        # in case an orphaned descendant still holds the pty open and EOF
        # never naturally arrives.
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
                    session.write(data)
            elif kind == "resize":
                cols, rows = message.get("cols"), message.get("rows")
                if isinstance(cols, int) and isinstance(rows, int):
                    session.resize(cols, rows)
    except WebSocketDisconnect:
        pass
    finally:
        exit_wait_task.cancel()
        with contextlib.suppress(Exception, asyncio.CancelledError):
            await exit_wait_task
        if session.returncode is None:
            await session.terminate()
            try:
                await asyncio.wait_for(session.wait(), timeout=3)
            except TimeoutError:
                await session.kill()
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(session.wait(), timeout=5)
        exit_task.cancel()
        output_task.cancel()
        await asyncio.gather(exit_task, output_task, return_exceptions=True)
        await session.close()
        with contextlib.suppress(Exception):
            await websocket.close()

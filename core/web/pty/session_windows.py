"""Windows (winpty/ConPTY) session implementation for PTY sessions."""

from __future__ import annotations

import asyncio
import contextlib
import subprocess
import threading
import time
from collections.abc import Callable
from pathlib import Path

from core.host_env import child_environ
from core.logging_config import get_logger
from core.web.pty.common import SpawnError, _enqueue_pty_output

logger = get_logger(__name__)

_READ_CHUNK = 4096

try:
    import winpty  # type: ignore[import-untyped,import-not-found]
except ImportError:
    winpty = None  # pragma: no cover - absent on POSIX


class _WindowsSession:  # pragma: no cover - exercised only on Windows
    def __init__(self, pty_process, loop: asyncio.AbstractEventLoop, output_queue):
        self._pty = pty_process
        self._loop = loop
        self._queue = output_queue
        self._returncode: int | None = None
        self._closing = threading.Event()
        self._reader_thread = threading.Thread(
            target=self._read_loop, daemon=True, name="pty-windows-reader"
        )
        self._reader_thread.start()

    @property
    def pid(self) -> int | None:
        return self._pty.pid

    def _read_loop(self) -> None:
        consecutive_errors = 0
        while True:
            try:
                data = self._pty.read(_READ_CHUNK)
                consecutive_errors = 0
            except EOFError:
                data = ""
            except Exception as exc:
                if self._closing.is_set():
                    return
                consecutive_errors += 1
                logger.warning(
                    "Unexpected error reading from Windows PTY (retry %d): %s",
                    consecutive_errors,
                    exc,
                )
                is_alive = getattr(self._pty, "isalive", lambda: True)()
                if not is_alive or consecutive_errors >= 5:
                    logger.error(
                        "Windows PTY process is not alive or exceeded error threshold; stopping reader."
                    )
                    data = ""
                else:
                    time.sleep(0.05)
                    continue
            if self._closing.is_set():
                return
            with contextlib.suppress(RuntimeError):
                self._loop.call_soon_threadsafe(
                    _enqueue_pty_output, self._queue, data or None
                )
            if not data:
                return

    def write(self, data: str) -> None:
        with contextlib.suppress(Exception):
            self._pty.write(data)

    def resize(self, cols: int, rows: int) -> None:
        with contextlib.suppress(Exception):
            self._pty.setwinsize(rows, cols)

    async def wait(self) -> int:
        code = await asyncio.to_thread(self._pty.wait)
        self._returncode = code if isinstance(code, int) else 0
        return self._returncode

    async def _kill_process_tree(self) -> None:
        pid = self._pty.pid
        if pid is None:
            return
        with contextlib.suppress(Exception):
            await asyncio.to_thread(
                subprocess.run,
                ["taskkill", "/T", "/F", "/PID", str(pid)],
                capture_output=True,
                timeout=10,
            )

    async def terminate(self) -> None:
        await self._kill_process_tree()

    async def shutdown(self) -> None:
        await self._kill_process_tree()

    async def kill(self) -> None:
        await self._kill_process_tree()

    async def close(self) -> None:
        self._closing.set()
        with contextlib.suppress(Exception):
            await asyncio.to_thread(self._pty.close, True)
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
    engine: str,
    working_dir: Path,
    output_queue: asyncio.Queue[bytes | str | None],
    session_id: str | None = None,
    cols: int = 80,
    rows: int = 24,
    initial_prompt: str | None = None,
    engine_argv_fn: Callable[[str, Path, str | None, str | None], list[str]]
    | None = None,
) -> _WindowsSession:
    loop = asyncio.get_running_loop()
    env = {**child_environ(), "TERM": "xterm-256color"}
    if engine_argv_fn is not None:
        argv = engine_argv_fn(engine, working_dir, session_id, initial_prompt)
    else:
        from core.web.routers.pty import _engine_argv

        argv = _engine_argv(engine, working_dir, session_id, initial_prompt)
    try:
        pty_process = await asyncio.to_thread(
            winpty.PtyProcess.spawn,
            argv,
            cwd=str(working_dir),
            env=env,
            dimensions=(rows, cols),
        )
    except Exception as exc:
        raise SpawnError(str(exc)) from exc
    return _WindowsSession(pty_process, loop, output_queue)

"""POSIX PTY session and tmux attach client implementation."""

from __future__ import annotations

import asyncio
import contextlib
import os
import signal
from collections.abc import Callable
from pathlib import Path

from core.host_env import child_environ
from core.web.pty.common import SpawnError, _enqueue_pty_output, _resize_fd
from core.web.pty.tmux import (
    _run_tmux,
    _tmux_binary,
    _tmux_ensure_session,
    _tmux_kill_session,
    _tmux_session_name,
    _tmux_socket,
)

_READ_CHUNK = 4096


def _tmux_resize_window(name: str | None, cols: int, rows: int) -> None:
    if not name:
        return
    with contextlib.suppress(Exception):
        _run_tmux("resize-window", "-t", name, "-x", str(cols), "-y", str(rows))


class _PosixSession:
    def __init__(
        self,
        process,
        master_fd: int,
        tmux_name: str | None = None,
    ):
        self._process = process
        self._master_fd = master_fd
        self.tmux_name = tmux_name

    @property
    def pid(self) -> int | None:
        return self._process.pid

    def write(self, data: str) -> None:
        with contextlib.suppress(OSError):
            os.write(self._master_fd, data.encode())

    def resize(self, cols: int, rows: int) -> None:
        _resize_fd(self._master_fd, cols, rows)
        _tmux_resize_window(self.tmux_name, cols, rows)

    async def wait(self) -> int:
        return await self._process.wait()

    def _signal_process_group(self, sig: int) -> None:
        pid = self._process.pid
        if pid is None:
            return
        with contextlib.suppress(ProcessLookupError, PermissionError, OSError):
            os.killpg(os.getpgid(pid), sig)  # type: ignore[attr-defined]

    async def terminate(self) -> None:
        self._signal_process_group(signal.SIGTERM)

    async def kill(self) -> None:
        self._signal_process_group(signal.SIGKILL)  # type: ignore[attr-defined]

    async def shutdown(self) -> None:
        if self.tmux_name:
            await asyncio.to_thread(_tmux_kill_session, self.tmux_name)
        await self.terminate()  # type: ignore[attr-defined]

    async def close(self) -> None:
        with contextlib.suppress(OSError):
            os.close(self._master_fd)

    @property
    def returncode(self) -> int | None:
        return self._process.returncode


async def _spawn_posix(
    engine: str,
    working_dir: Path,
    output_queue: asyncio.Queue[bytes | str | None],
    session_id: str | None = None,
    *,
    tmux_name: str | None = None,
    tab_key: str | None = None,
    cols: int = 80,
    rows: int = 24,
    initial_prompt: str | None = None,
    engine_argv_fn: Callable[[str, Path, str | None, str | None], list[str]]
    | None = None,
    tmux_binary_fn: Callable[[], str | None] | None = None,
) -> _PosixSession:
    """Spawns what the browser terminal drives."""
    import pty

    master_fd, slave_fd = pty.openpty()  # type: ignore[attr-defined]
    _resize_fd(master_fd, cols=cols, rows=rows)
    env = {
        **child_environ(),
        "TERM": "xterm-256color",
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
    }

    created_tmux_name: str | None = None
    try:
        try:
            if engine_argv_fn is not None:
                engine_argv = engine_argv_fn(
                    engine, working_dir, session_id, initial_prompt
                )
            else:
                from core.web.routers.pty import _engine_argv

                engine_argv = _engine_argv(
                    engine, working_dir, session_id, initial_prompt
                )
            if tmux_binary_fn is not None:
                binary = tmux_binary_fn()
            else:
                try:
                    from core.web.routers import pty as pty_router

                    binary = getattr(pty_router, "_tmux_binary", _tmux_binary)()
                except Exception:
                    binary = _tmux_binary()
            if binary is None:
                tmux_name = None
                argv = engine_argv
            else:
                if tmux_name is None:
                    tmux_name = _tmux_session_name(
                        engine, working_dir, session_id, tab_key
                    )
                    created_tmux_name = tmux_name
                    await asyncio.to_thread(
                        _tmux_ensure_session,
                        tmux_name,
                        engine_argv,
                        working_dir,
                        cols,
                        rows,
                    )
                argv = [binary, "-L", _tmux_socket(), "attach-session", "-t", tmux_name]
            process = await asyncio.create_subprocess_exec(
                *argv,
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
        with contextlib.suppress(OSError):
            os.close(master_fd)
        if created_tmux_name is not None:
            with contextlib.suppress(Exception):
                await asyncio.to_thread(_tmux_kill_session, created_tmux_name)
        if not isinstance(exc, (OSError, SpawnError)):
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
            _enqueue_pty_output(output_queue, None)
            return
        _enqueue_pty_output(output_queue, chunk)

    loop.add_reader(master_fd, _on_readable)
    return _PosixSession(process, master_fd, tmux_name=tmux_name)

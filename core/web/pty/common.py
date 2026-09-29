"""Shared types, exceptions, and queue helpers for PTY sessions."""

from __future__ import annotations

import asyncio
import contextlib
import os
import struct
from typing import Protocol

from core.logging_config import get_logger

logger = get_logger(__name__)

# Output queue maximum capacity to prevent memory bloat under slow clients
_PTY_QUEUE_MAX_SIZE = 1024

SHELL_ENGINE = "shell"


class PtySession(Protocol):
    def write(self, data: str) -> None: ...
    def resize(self, cols: int, rows: int) -> None: ...
    @property
    def pid(self) -> int | None: ...
    async def wait(self) -> int:
        """Blocks until the child exits and returns its exit code."""
        ...

    async def terminate(self) -> None: ...

    async def shutdown(self) -> None:
        """Stops the engine itself, not just the attach client."""
        ...

    async def kill(self) -> None: ...
    async def close(self) -> None: ...
    @property
    def returncode(self) -> int | None: ...


class SpawnError(Exception):
    """Raised when a PTY session could not be started."""


def _enqueue_pty_output(
    queue: asyncio.Queue[bytes | str | None], item: bytes | str | None
) -> None:
    """Enqueues output chunk into queue, dropping oldest chunks if full to prevent OOM.

    Trade-off note: Dropping the oldest chunk when the queue is saturated prioritizes
    system stability and memory bounds over continuous terminal stream integrity.
    Discarding an arbitrary chunk may split an in-flight ANSI escape sequence or a
    multi-byte UTF-8 character boundary, potentially resulting in transient terminal
    rendering artifacts until the next redraw/clear. This is an intentional choice:
    preventing process crash / out-of-memory under slow client consumption takes
    precedence over lossless backlog preservation.
    """
    if item is None:
        while queue.full():
            try:
                queue.get_nowait()
            except (asyncio.QueueEmpty, ValueError):
                break
        try:
            queue.put_nowait(None)
        except asyncio.QueueFull:
            pass
        return

    if queue.full():
        try:
            queue.get_nowait()
            logger.warning(
                "PTY output queue full (%d items); dropped oldest chunk to prevent memory exhaustion",
                queue.maxsize,
            )
        except (asyncio.QueueEmpty, ValueError):
            pass
    try:
        queue.put_nowait(item)
    except asyncio.QueueFull:
        pass


def _resize_fd(fd: int, cols: int, rows: int) -> None:
    if os.name == "nt":  # pragma: no cover - exercised only on Windows
        return
    try:
        import fcntl
        import termios

        with contextlib.suppress(OSError):
            fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))  # type: ignore[attr-defined]
    except ImportError:  # pragma: no cover
        pass

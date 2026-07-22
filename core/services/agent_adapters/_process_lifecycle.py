"""Shared subprocess graceful-teardown helper.

``claude.py``, ``codex.py``, ``gemini.py``, and ``opencode.py`` each spawn a
child process and each independently implemented the same shutdown
sequence: ask nicely (``terminate()``), give it a short grace period, then
``kill()`` and give it a longer grace period, and finally give up and log a
warning rather than block shutdown forever on a child stuck in
uninterruptible I/O. This module extracts that sequence so every adapter
composes it instead of re-implementing it.
"""

from __future__ import annotations

import asyncio
import logging
from asyncio.subprocess import Process


async def graceful_terminate(
    process: Process | None,
    *,
    logger: logging.Logger,
    label: str,
    terminate_timeout: float = 3,
    kill_timeout: float = 5,
) -> None:
    """Terminate ``process``, escalating to SIGKILL if it won't exit.

    Never raises and never blocks longer than ``terminate_timeout +
    kill_timeout``: a child that survives even SIGKILL (e.g. stuck in
    uninterruptible I/O) is abandoned with a warning rather than awaited
    forever.
    """
    if process is None or process.returncode is not None:
        return
    process.terminate()
    try:
        await asyncio.wait_for(process.wait(), timeout=terminate_timeout)
    except TimeoutError:
        process.kill()
        try:
            await asyncio.wait_for(process.wait(), timeout=kill_timeout)
        except TimeoutError:
            logger.warning(
                "%s process (pid=%s) did not exit after SIGKILL; abandoning "
                "it to avoid blocking shutdown",
                label,
                process.pid,
            )

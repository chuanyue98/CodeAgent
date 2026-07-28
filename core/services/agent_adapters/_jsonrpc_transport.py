"""Shared JSON-RPC-over-stdio transport for the Codex and Gemini adapters.

Both ``codex.py`` (Codex's app-server protocol) and ``gemini.py`` (the
Agent Client Protocol) speak line-delimited JSON-RPC to a child process over
stdio: a pending-futures map keyed by request id, a write lock around
stdout writes, an incrementing request id counter, and a read loop that
either resolves a pending future, dispatches a server-initiated request, or
dispatches a notification. The only structural difference between the two
protocols is that ACP (Gemini) wraps every message in a
``{"jsonrpc": "2.0", ...}`` envelope while Codex's app-server protocol does
not. :class:`JsonRpcStdioTransport` extracts that machinery so both
adapters compose it instead of re-implementing it; the adapter-specific
event translation (``_handle_server_request`` / ``_handle_notification``)
stays in each adapter.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from typing import Any

from core.logging_config import get_logger

logger = get_logger(__name__)


class JsonRpcStdioTransport:
    """Request/response and notification dispatch for a JSON-RPC stdio child."""

    def __init__(
        self,
        *,
        protocol_error: type[Exception],
        crash_label: str,
        on_server_request: Callable[[dict[str, Any]], Awaitable[None]],
        on_notification: Callable[[str, dict[str, Any]], Awaitable[None]],
        on_crash: Callable[[Exception], Awaitable[None]],
        use_jsonrpc_envelope: bool = False,
        is_stopping: Callable[[], bool] | None = None,
    ) -> None:
        self._protocol_error = protocol_error
        self._crash_label = crash_label
        self._on_server_request = on_server_request
        self._on_notification = on_notification
        self._on_crash = on_crash
        self._use_jsonrpc_envelope = use_jsonrpc_envelope
        self._is_stopping = is_stopping or (lambda: False)
        self.process: asyncio.subprocess.Process | None = None
        self._reader_task: asyncio.Task | None = None
        self._stderr_task: asyncio.Task | None = None
        self._pending: dict[str, asyncio.Future] = {}
        self._next_request_id = 1
        self._write_lock = asyncio.Lock()

    def attach(
        self,
        process: asyncio.subprocess.Process,
        *,
        reader_name: str,
        stderr_name: str,
    ) -> None:
        """Start dispatching stdout/stderr for a freshly spawned process."""
        self.process = process
        self._reader_task = asyncio.create_task(self._read_loop(), name=reader_name)
        self._stderr_task = asyncio.create_task(self._drain_stderr(), name=stderr_name)

    async def detach(self) -> None:
        """Stop the reader/stderr tasks and fail any pending requests.

        Callers should null out their own process reference (and ask the
        process to terminate) before calling this, so the read loop's crash
        detection can tell a deliberate shutdown apart from an unexpected
        exit.
        """
        self.process = None
        for task in (self._reader_task, self._stderr_task):
            if task:
                task.cancel()
        await asyncio.gather(
            *(task for task in (self._reader_task, self._stderr_task) if task),
            return_exceptions=True,
        )
        self._reader_task = None
        self._stderr_task = None
        stop_error = self._protocol_error(f"{self._crash_label} stopped")
        for future in self._pending.values():
            if not future.done():
                future.set_exception(stop_error)
        self._pending.clear()

    async def request(
        self, method: str, params: dict[str, Any], timeout: float = 60
    ) -> dict[str, Any]:
        request_id = self._next_request_id
        self._next_request_id += 1
        future = asyncio.get_running_loop().create_future()
        self._pending[str(request_id)] = future
        await self.write({"id": request_id, "method": method, "params": params})
        try:
            result = await asyncio.wait_for(future, timeout=timeout)
        finally:
            self._pending.pop(str(request_id), None)
        if not isinstance(result, dict):
            raise self._protocol_error(f"{method} returned a non-object result")
        return result

    async def notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        message: dict[str, Any] = {"method": method}
        if params is not None:
            message["params"] = params
        await self.write(message)

    async def write(self, message: dict[str, Any]) -> None:
        process = self.process
        if not process or process.returncode is not None or not process.stdin:
            raise self._protocol_error(f"{self._crash_label} is not running")
        if self._use_jsonrpc_envelope and "jsonrpc" not in message:
            message = {"jsonrpc": "2.0", **message}
        encoded = (json.dumps(message, ensure_ascii=False) + "\n").encode()
        async with self._write_lock:
            process.stdin.write(encoded)
            await process.stdin.drain()

    async def _read_loop(self) -> None:
        assert self.process and self.process.stdout
        try:
            while line := await self.process.stdout.readline():
                try:
                    message = json.loads(line)
                except (json.JSONDecodeError, UnicodeDecodeError):
                    logger.debug(
                        "%s: dropping unparseable line from stdout: %r",
                        self._crash_label,
                        line,
                    )
                    continue
                request_id = message.get("id")
                method = message.get("method")
                if request_id is not None and method is None:
                    future = self._pending.get(str(request_id))
                    if future and not future.done():
                        if "error" in message:
                            future.set_exception(
                                self._protocol_error(str(message["error"]))
                            )
                        else:
                            future.set_result(message.get("result", {}))
                elif request_id is not None and isinstance(method, str):
                    await self._on_server_request(message)
                elif isinstance(method, str):
                    await self._on_notification(method, message.get("params") or {})
        except asyncio.CancelledError:
            raise
        finally:
            if self.process is not None and not self._is_stopping():
                error = self._protocol_error(f"{self._crash_label} exited unexpectedly")
                for future in self._pending.values():
                    if not future.done():
                        future.set_exception(error)
                await self._on_crash(error)

    async def _drain_stderr(self) -> None:
        assert self.process and self.process.stderr
        try:
            while await self.process.stderr.readline():
                pass
        except asyncio.CancelledError:
            raise

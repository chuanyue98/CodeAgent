"""Codex 0.144 app-server stdio adapter.

The subprocess protocol is intentionally contained here; browser clients only
receive the provider-neutral events defined in :mod:`agent_protocol`.
"""

from __future__ import annotations

import asyncio
import json
import shutil
from collections.abc import AsyncIterator
from typing import Any

from core.services.agent_protocol import (
    AdapterEvent,
    ApprovalDecision,
    CreateSessionOptions,
    ProviderCapabilities,
    ProviderSession,
    ResumeOptions,
    TurnInput,
    wire,
)


class CodexProtocolError(RuntimeError):
    pass


class CodexAdapter:
    provider_id = "codex"

    def __init__(self, executable: str = "codex", queue_size: int = 1024):
        self.executable = executable
        self._events: asyncio.Queue[AdapterEvent | None] = asyncio.Queue(queue_size)
        self._process: asyncio.subprocess.Process | None = None
        self._reader_task: asyncio.Task | None = None
        self._stderr_task: asyncio.Task | None = None
        self._pending: dict[str, asyncio.Future] = {}
        self._approval_requests: dict[str, tuple[Any, str]] = {}
        self._next_request_id = 1
        self._write_lock = asyncio.Lock()
        self._unavailable_reason: str | None = None

    async def start(self) -> None:
        if self._process and self._process.returncode is None:
            return
        executable = shutil.which(self.executable)
        if not executable:
            self._unavailable_reason = "Codex CLI was not found on the CodeAgent server"
            raise RuntimeError(self._unavailable_reason)
        try:
            self._process = await asyncio.create_subprocess_exec(
                executable,
                "app-server",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            self._reader_task = asyncio.create_task(
                self._read_loop(), name="codex-app-server-stdout"
            )
            self._stderr_task = asyncio.create_task(
                self._drain_stderr(), name="codex-app-server-stderr"
            )
            await self._request(
                "initialize",
                {
                    "clientInfo": {
                        "name": "codeagent",
                        "title": "CodeAgent Web",
                        "version": "0.1.0",
                    },
                    "capabilities": {"experimentalApi": False},
                },
                timeout=15,
            )
            await self._notify("initialized")
            self._unavailable_reason = None
        except Exception as exc:
            self._unavailable_reason = f"Codex app-server failed to start: {exc}"
            await self.stop()
            raise RuntimeError(self._unavailable_reason) from exc

    async def stop(self) -> None:
        process = self._process
        self._process = None
        if process and process.returncode is None:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=3)
            except TimeoutError:
                process.kill()
                await process.wait()
        for task in (self._reader_task, self._stderr_task):
            if task:
                task.cancel()
        await asyncio.gather(
            *(task for task in (self._reader_task, self._stderr_task) if task),
            return_exceptions=True,
        )
        self._reader_task = None
        self._stderr_task = None
        for future in self._pending.values():
            if not future.done():
                future.set_exception(CodexProtocolError("Codex app-server stopped"))
        self._pending.clear()

    async def capabilities(self) -> ProviderCapabilities:
        running = self._process is not None and self._process.returncode is None
        return ProviderCapabilities(
            provider_id=self.provider_id,
            display_name="Codex",
            available=running,
            unavailable_reason=None
            if running
            else (self._unavailable_reason or "Codex app-server is not running"),
            supports_resume=True,
            supports_steer=True,
            supports_cancel=True,
            supports_approvals=True,
            supports_file_diff=True,
            supports_tool_events=True,
            supports_attachments=False,
            supports_model_switch=True,
        )

    async def create_session(self, options: CreateSessionOptions) -> ProviderSession:
        result = await self._request(
            "thread/start",
            {
                "cwd": options.cwd,
                "model": options.model,
                "approvalPolicy": "on-request",
                "approvalsReviewer": "user",
                "sandbox": options.permission_mode,
            },
        )
        thread = result.get("thread") or {}
        thread_id = thread.get("id")
        if not isinstance(thread_id, str):
            raise CodexProtocolError("thread/start response did not include thread.id")
        return ProviderSession(id=thread_id, model=result.get("model"))

    async def resume_session(
        self, provider_session_id: str, options: ResumeOptions
    ) -> ProviderSession:
        result = await self._request(
            "thread/resume",
            {
                "threadId": provider_session_id,
                "cwd": options.cwd,
                "model": options.model,
                "approvalPolicy": "on-request",
                "approvalsReviewer": "user",
                "sandbox": options.permission_mode,
            },
        )
        thread = result.get("thread") or {}
        thread_id = thread.get("id")
        if not isinstance(thread_id, str):
            raise CodexProtocolError("thread/resume response did not include thread.id")
        return ProviderSession(id=thread_id, model=result.get("model"))

    async def start_turn(self, provider_session_id: str, turn: TurnInput) -> str:
        result = await self._request(
            "turn/start",
            {
                "threadId": provider_session_id,
                "input": [wire(value) for value in turn.input],
            },
        )
        turn_id = (result.get("turn") or {}).get("id")
        if not isinstance(turn_id, str):
            raise CodexProtocolError("turn/start response did not include turn.id")
        return turn_id

    async def steer_turn(
        self, provider_session_id: str, provider_turn_id: str, turn: TurnInput
    ) -> None:
        await self._request(
            "turn/steer",
            {
                "threadId": provider_session_id,
                "expectedTurnId": provider_turn_id,
                "input": [wire(value) for value in turn.input],
            },
        )

    async def cancel_turn(
        self, provider_session_id: str, provider_turn_id: str
    ) -> None:
        await self._request(
            "turn/interrupt",
            {"threadId": provider_session_id, "turnId": provider_turn_id},
        )

    async def respond_to_approval(
        self, approval_id: str, decision: ApprovalDecision
    ) -> None:
        pending = self._approval_requests.pop(approval_id, None)
        if pending is None:
            raise CodexProtocolError("Approval request is no longer pending")
        request_id, _method = pending
        await self._write({"id": request_id, "result": {"decision": decision}})

    async def events(self) -> AsyncIterator[AdapterEvent]:
        while True:
            event = await self._events.get()
            if event is None:
                return
            yield event

    async def _request(
        self, method: str, params: dict[str, Any], timeout: float = 60
    ) -> dict[str, Any]:
        request_id = self._next_request_id
        self._next_request_id += 1
        future = asyncio.get_running_loop().create_future()
        self._pending[str(request_id)] = future
        await self._write({"id": request_id, "method": method, "params": params})
        try:
            result = await asyncio.wait_for(future, timeout=timeout)
        finally:
            self._pending.pop(str(request_id), None)
        if not isinstance(result, dict):
            raise CodexProtocolError(f"{method} returned a non-object result")
        return result

    async def _notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        message: dict[str, Any] = {"method": method}
        if params is not None:
            message["params"] = params
        await self._write(message)

    async def _write(self, message: dict[str, Any]) -> None:
        process = self._process
        if not process or process.returncode is not None or not process.stdin:
            raise CodexProtocolError("Codex app-server is not running")
        encoded = (json.dumps(message, ensure_ascii=False) + "\n").encode()
        async with self._write_lock:
            process.stdin.write(encoded)
            await process.stdin.drain()

    async def _read_loop(self) -> None:
        assert self._process and self._process.stdout
        try:
            while line := await self._process.stdout.readline():
                try:
                    message = json.loads(line)
                except (json.JSONDecodeError, UnicodeDecodeError):
                    continue
                request_id = message.get("id")
                method = message.get("method")
                if request_id is not None and method is None:
                    future = self._pending.get(str(request_id))
                    if future and not future.done():
                        if "error" in message:
                            future.set_exception(
                                CodexProtocolError(str(message["error"]))
                            )
                        else:
                            future.set_result(message.get("result", {}))
                elif request_id is not None and isinstance(method, str):
                    await self._handle_server_request(message)
                elif isinstance(method, str):
                    await self._handle_notification(method, message.get("params") or {})
        except asyncio.CancelledError:
            raise
        finally:
            if self._process is not None:
                error = CodexProtocolError("Codex app-server exited unexpectedly")
                for future in self._pending.values():
                    if not future.done():
                        future.set_exception(error)
                await self._events.put(
                    AdapterEvent(
                        type="error",
                        provider_session_id="",
                        data={
                            "code": "provider_crashed",
                            "message": str(error),
                            "retryable": True,
                        },
                    )
                )

    async def _drain_stderr(self) -> None:
        assert self._process and self._process.stderr
        try:
            while await self._process.stderr.readline():
                pass
        except asyncio.CancelledError:
            raise

    async def _handle_server_request(self, message: dict[str, Any]) -> None:
        method = message["method"]
        params = message.get("params") or {}
        if method in {
            "item/commandExecution/requestApproval",
            "item/fileChange/requestApproval",
            "item/permissions/requestApproval",
        }:
            request_id = message["id"]
            approval_id = f"codex:{request_id}"
            self._approval_requests[approval_id] = (request_id, method)
            await self._events.put(
                AdapterEvent(
                    type="approval.request",
                    provider_session_id=params.get("threadId", ""),
                    provider_turn_id=params.get("turnId"),
                    item_id=params.get("itemId"),
                    data={
                        "approval": {
                            "id": approval_id,
                            "kind": method,
                            "command": params.get("command"),
                            "commandActions": params.get("commandActions"),
                            "cwd": params.get("cwd"),
                            "reason": params.get("reason"),
                            "grantRoot": params.get("grantRoot"),
                        }
                    },
                )
            )
            return
        await self._write(
            {
                "id": message["id"],
                "error": {"code": -32601, "message": f"Unsupported request: {method}"},
            }
        )

    async def _handle_notification(self, method: str, params: dict[str, Any]) -> None:
        thread_id = params.get("threadId", "")
        turn = params.get("turn") or {}
        turn_id = params.get("turnId") or turn.get("id")
        item = params.get("item") or {}
        item_id = params.get("itemId") or item.get("id")
        event_type: str | None = None
        data: dict[str, Any] = {}

        if method == "turn/started":
            event_type = "turn.started"
        elif method == "turn/completed":
            event_type = "turn.completed"
            data = {"status": turn.get("status", "completed")}
            if turn.get("error") is not None:
                data["error"] = turn["error"]
        elif method == "item/agentMessage/delta":
            event_type = "message.delta"
            data = {"delta": params.get("delta", "")}
        elif method in {"item/started", "item/completed"}:
            completed = method.endswith("completed")
            item_type = item.get("type")
            if item_type == "agentMessage" and completed:
                event_type = "message.completed"
                data = {"text": item.get("text", "")}
            elif item_type == "commandExecution":
                event_type = "tool.completed" if completed else "tool.started"
                data = {"tool": {"kind": "command", **item}}
            elif item_type == "fileChange":
                event_type = "tool.completed" if completed else "tool.started"
                data = {"tool": {"kind": "fileChange", **item}}
            elif item_type and item_type not in {"userMessage", "reasoning"}:
                event_type = "tool.completed" if completed else "tool.started"
                data = {"tool": item}
        elif method == "item/commandExecution/outputDelta":
            event_type = "command.output"
            data = {
                "commandId": item_id,
                "stream": params.get("stream", "stdout"),
                "delta": params.get("delta", ""),
            }
        elif method in {"item/fileChange/patchUpdated", "turn/diff/updated"}:
            event_type = "file.diff"
            data = {"diff": params.get("changes") or params.get("diff") or params}
        elif method == "thread/tokenUsage/updated":
            event_type = "usage.updated"
            data = {"usage": params.get("tokenUsage") or params}
        elif method == "error":
            event_type = "error"
            data = {
                "code": "provider_error",
                "message": (params.get("error") or {}).get("message")
                or params.get("message")
                or "Codex reported an error",
                "retryable": bool(params.get("willRetry")),
            }

        if event_type and thread_id:
            await self._events.put(
                AdapterEvent(
                    type=event_type,
                    provider_session_id=thread_id,
                    provider_turn_id=turn_id,
                    item_id=item_id,
                    data=data,
                )
            )

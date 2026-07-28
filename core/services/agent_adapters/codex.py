"""Codex 0.144 app-server stdio adapter.

The subprocess protocol is intentionally contained here; browser clients only
receive the provider-neutral events defined in :mod:`agent_protocol`.
"""

from __future__ import annotations

import asyncio
import shutil
from collections.abc import AsyncIterator
from typing import Any

from core.logging_config import get_logger
from core.services.agent_adapters._event_queue import (
    iter_events,
    put_event_dropping_oldest,
)
from core.services.agent_adapters._jsonrpc_transport import JsonRpcStdioTransport
from core.services.agent_adapters._process_lifecycle import graceful_terminate
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

logger = get_logger(__name__)


class CodexProtocolError(RuntimeError):
    pass


class CodexAdapter:
    provider_id = "codex"

    def __init__(self, executable: str = "codex", queue_size: int = 1024):
        self.executable = executable
        self._events: asyncio.Queue[AdapterEvent | None] = asyncio.Queue(queue_size)
        self._process: asyncio.subprocess.Process | None = None
        self._transport = JsonRpcStdioTransport(
            protocol_error=CodexProtocolError,
            crash_label="Codex app-server",
            on_server_request=self._handle_server_request,
            on_notification=self._handle_notification,
            on_crash=self._emit_crash_event,
        )
        self._approval_requests: dict[str, tuple[Any, str]] = {}
        self._approval_timeouts: dict[str, asyncio.Task] = {}
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
            self._transport.attach(
                self._process,
                reader_name="codex-app-server-stdout",
                stderr_name="codex-app-server-stderr",
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
        await graceful_terminate(process, logger=logger, label="Codex app-server")
        await self._transport.detach()
        for task in self._approval_timeouts.values():
            task.cancel()
        self._approval_timeouts.clear()
        self._approval_requests.clear()

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
        try:
            await self._write({"id": request_id, "result": {"decision": decision}})
        finally:
            self._cancel_approval_timeout(approval_id)

    def events(self) -> AsyncIterator[AdapterEvent]:
        return iter_events(self._events)

    def _put_event(self, event: AdapterEvent) -> None:
        put_event_dropping_oldest(self._events, event, label="Codex")

    async def _emit_crash_event(self, error: Exception) -> None:
        self._put_event(
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

    async def _request(
        self, method: str, params: dict[str, Any], timeout: float = 60
    ) -> dict[str, Any]:
        return await self._transport.request(method, params, timeout=timeout)

    async def _notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        await self._transport.notify(method, params)

    async def _write(self, message: dict[str, Any]) -> None:
        await self._transport.write(message)

    def _cancel_approval_timeout(self, approval_id: str) -> None:
        """Cancels a pending approval timeout watcher, if any."""
        task = self._approval_timeouts.pop(approval_id, None)
        if task is not None:
            task.cancel()

    async def _timeout_approval(self, approval_id: str) -> None:
        """Auto-responds to an approval after 5 minutes so the server is never left waiting indefinitely.

        Runs as a background task scheduled when the approval request arrives.
        If the user responds in time the task is cancelled via
        :meth:`_cancel_approval_timeout`; otherwise it sends a ``decline``
        decision to the server and clears the pending entry.
        """
        try:
            await asyncio.sleep(300)
        except asyncio.CancelledError:
            return
        pending = self._approval_requests.pop(approval_id, None)
        self._approval_timeouts.pop(approval_id, None)
        if pending is None:
            return
        request_id = pending[0]
        logger.warning(
            "Codex approval %s timed out after 300s; sending decline response",
            approval_id,
        )
        try:
            await self._write(
                {"id": request_id, "result": {"decision": ApprovalDecision.DECLINE}}
            )
        except Exception:
            logger.debug("Failed to send timeout response for %s", approval_id)

    async def _handle_server_request(self, message: dict[str, Any]) -> None:
        method = message.get("method")
        if method is None:
            logger.warning("Server request missing 'method' field, skipping")
            return
        params = message.get("params") or {}
        request_id = message.get("id")
        if request_id is None:
            logger.warning("Server request missing 'id' field, skipping: %s", method)
            return
        if method in {
            "item/commandExecution/requestApproval",
            "item/fileChange/requestApproval",
            "item/permissions/requestApproval",
        }:
            approval_id = f"codex:{request_id}"
            self._approval_requests[approval_id] = (request_id, method)
            self._approval_timeouts[approval_id] = asyncio.create_task(
                self._timeout_approval(approval_id)
            )
            self._put_event(
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
                "id": request_id,
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
            self._put_event(
                AdapterEvent(
                    type=event_type,
                    provider_session_id=thread_id,
                    provider_turn_id=turn_id,
                    item_id=item_id,
                    data=data,
                )
            )

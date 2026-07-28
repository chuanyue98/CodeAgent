"""Gemini CLI adapter using Agent Client Protocol JSON-RPC over stdio."""

from __future__ import annotations

import asyncio
import shutil
from collections.abc import AsyncIterator
from typing import Any
from uuid import uuid4

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
    PermissionMode,
    ProviderCapabilities,
    ProviderSession,
    ResumeOptions,
    TurnInput,
)

logger = get_logger(__name__)


class GeminiProtocolError(RuntimeError):
    pass


class GeminiAdapter:
    provider_id = "gemini"

    def __init__(self, executable: str = "gemini", queue_size: int = 1024):
        self.executable = executable
        self._events: asyncio.Queue[AdapterEvent | None] = asyncio.Queue(queue_size)
        self._process: asyncio.subprocess.Process | None = None
        self._transport = JsonRpcStdioTransport(
            protocol_error=GeminiProtocolError,
            crash_label="Gemini ACP",
            on_server_request=self._handle_server_request,
            on_notification=self._handle_notification,
            on_crash=self._emit_crash_event,
            use_jsonrpc_envelope=True,
            is_stopping=lambda: self._stopping,
        )
        self._pending_approvals: dict[str, tuple[Any, list[dict[str, Any]], str]] = {}
        self._approval_timeouts: dict[str, asyncio.Task] = {}
        self._turn_tasks: dict[str, asyncio.Task] = {}
        self._active_turns: dict[str, str] = {}
        self._message_text: dict[tuple[str, str], str] = {}
        self._unavailable_reason: str | None = None
        self._stopping = False

    async def start(self) -> None:
        if self._process and self._process.returncode is None:
            return
        executable = shutil.which(self.executable)
        if not executable:
            self._unavailable_reason = (
                "Gemini CLI was not found on the CodeAgent server"
            )
            raise RuntimeError(self._unavailable_reason)
        self._stopping = False
        try:
            self._process = await asyncio.create_subprocess_exec(
                executable,
                "--acp",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            self._transport.attach(
                self._process,
                reader_name="gemini-acp-stdout",
                stderr_name="gemini-acp-stderr",
            )
            await self._request(
                "initialize",
                {
                    "protocolVersion": 1,
                    "clientCapabilities": {
                        "fs": {"readTextFile": False, "writeTextFile": False},
                        "terminal": False,
                    },
                    "clientInfo": {
                        "name": "codeagent",
                        "title": "CodeAgent Web",
                        "version": "0.1.0",
                    },
                },
                timeout=15,
            )
            self._unavailable_reason = None
        except Exception as exc:
            self._unavailable_reason = f"Gemini ACP failed to start: {exc}"
            await self.stop()
            raise RuntimeError(self._unavailable_reason) from exc

    async def stop(self) -> None:
        self._stopping = True
        for task in self._turn_tasks.values():
            task.cancel()
        await asyncio.gather(*self._turn_tasks.values(), return_exceptions=True)
        self._turn_tasks.clear()
        process = self._process
        self._process = None
        await graceful_terminate(process, logger=logger, label="Gemini ACP")
        await self._transport.detach()
        for task in self._approval_timeouts.values():
            task.cancel()
        self._approval_timeouts.clear()
        self._pending_approvals.clear()
        self._active_turns.clear()
        self._message_text.clear()

    async def capabilities(self) -> ProviderCapabilities:
        running = self._process is not None and self._process.returncode is None
        return ProviderCapabilities(
            provider_id=self.provider_id,
            display_name="Gemini CLI",
            available=running,
            unavailable_reason=None
            if running
            else (self._unavailable_reason or "Gemini ACP is not running"),
            supports_resume=True,
            supports_steer=False,
            supports_cancel=True,
            supports_approvals=True,
            supports_file_diff=True,
            supports_tool_events=True,
            supports_attachments=False,
            supports_model_switch=True,
        )

    async def create_session(self, options: CreateSessionOptions) -> ProviderSession:
        result = await self._request(
            "session/new", {"cwd": options.cwd, "mcpServers": []}
        )
        session_id = result.get("sessionId")
        if not isinstance(session_id, str):
            raise GeminiProtocolError("session/new response did not include sessionId")
        await self._configure_session(session_id, result, options)
        return ProviderSession(
            id=session_id, model=self._result_model(result, options.model)
        )

    async def resume_session(
        self, provider_session_id: str, options: ResumeOptions
    ) -> ProviderSession:
        result = await self._request(
            "session/load",
            {"sessionId": provider_session_id, "cwd": options.cwd, "mcpServers": []},
        )
        await self._configure_session(provider_session_id, result, options)
        return ProviderSession(
            id=provider_session_id, model=self._result_model(result, options.model)
        )

    async def _configure_session(
        self,
        session_id: str,
        result: dict[str, Any],
        options: CreateSessionOptions | ResumeOptions,
    ) -> None:
        mode_id = (
            "plan" if options.permission_mode == PermissionMode.READ_ONLY else "default"
        )
        modes = (result.get("modes") or {}).get("availableModes") or []
        available_modes = {
            value.get("id") for value in modes if isinstance(value, dict)
        }
        if mode_id not in available_modes:
            raise GeminiProtocolError(
                f"Gemini ACP does not expose the required {mode_id!r} permission mode"
            )
        if (result.get("modes") or {}).get("currentModeId") != mode_id:
            await self._request(
                "session/set_mode", {"sessionId": session_id, "modeId": mode_id}
            )
        current_model = (result.get("models") or {}).get("currentModelId")
        if options.model and options.model != current_model:
            await self._request(
                "session/set_model", {"sessionId": session_id, "modelId": options.model}
            )

    @staticmethod
    def _result_model(result: dict[str, Any], requested: str | None) -> str | None:
        current = (result.get("models") or {}).get("currentModelId")
        return requested or (current if isinstance(current, str) else None)

    async def start_turn(self, provider_session_id: str, turn: TurnInput) -> str:
        active = self._turn_tasks.get(provider_session_id)
        if active and not active.done():
            raise GeminiProtocolError("Gemini session already has an active turn")
        turn_id = f"gemini-turn-{uuid4().hex}"
        self._active_turns[provider_session_id] = turn_id
        self._message_text[(provider_session_id, turn_id)] = ""
        self._put_event(
            AdapterEvent(
                type="turn.started",
                provider_session_id=provider_session_id,
                provider_turn_id=turn_id,
            )
        )
        task = asyncio.create_task(
            self._run_prompt(provider_session_id, turn_id, turn),
            name=f"gemini-turn-{provider_session_id}",
        )
        self._turn_tasks[provider_session_id] = task
        return turn_id

    async def _run_prompt(
        self, provider_session_id: str, turn_id: str, turn: TurnInput
    ) -> None:
        try:
            result = await self._request(
                "session/prompt",
                {
                    "sessionId": provider_session_id,
                    "prompt": [
                        {"type": "text", "text": value.text} for value in turn.input
                    ],
                },
            )
            text = self._message_text.get((provider_session_id, turn_id), "")
            self._put_event(
                AdapterEvent(
                    type="message.completed",
                    provider_session_id=provider_session_id,
                    provider_turn_id=turn_id,
                    data={"text": text},
                )
            )
            usage = result.get("usage")
            if isinstance(usage, dict):
                self._put_event(
                    AdapterEvent(
                        type="usage.updated",
                        provider_session_id=provider_session_id,
                        provider_turn_id=turn_id,
                        data={"usage": usage},
                    )
                )
            self._put_event(
                AdapterEvent(
                    type="turn.completed",
                    provider_session_id=provider_session_id,
                    provider_turn_id=turn_id,
                    data={"status": result.get("stopReason", "end_turn")},
                )
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._put_event(
                AdapterEvent(
                    type="error",
                    provider_session_id=provider_session_id,
                    provider_turn_id=turn_id,
                    data={"code": "provider_error", "message": str(exc)},
                )
            )
            self._put_event(
                AdapterEvent(
                    type="turn.completed",
                    provider_session_id=provider_session_id,
                    provider_turn_id=turn_id,
                    data={"status": "error"},
                )
            )
        finally:
            self._active_turns.pop(provider_session_id, None)
            self._message_text.pop((provider_session_id, turn_id), None)

    async def steer_turn(
        self, provider_session_id: str, provider_turn_id: str, turn: TurnInput
    ) -> None:
        raise GeminiProtocolError("Gemini ACP does not support same-turn steering")

    async def cancel_turn(
        self, provider_session_id: str, provider_turn_id: str
    ) -> None:
        await self._notify("session/cancel", {"sessionId": provider_session_id})

    async def respond_to_approval(
        self, approval_id: str, decision: ApprovalDecision
    ) -> None:
        pending = self._pending_approvals.get(approval_id)
        if pending is None:
            raise GeminiProtocolError("Approval request is no longer pending")
        request_id, options, _session_id = pending
        try:
            if decision == ApprovalDecision.CANCEL:
                outcome = {"outcome": "cancelled"}
            else:
                desired_kind = {
                    ApprovalDecision.ACCEPT: "allow_once",
                    ApprovalDecision.ACCEPT_FOR_SESSION: "allow_always",
                    ApprovalDecision.DECLINE: "reject_once",
                }[decision]
                selected = next(
                    (
                        option
                        for option in options
                        if option.get("kind") == desired_kind
                    ),
                    None,
                )
                if selected is None and decision == ApprovalDecision.ACCEPT_FOR_SESSION:
                    selected = next(
                        (
                            option
                            for option in options
                            if option.get("kind") == "allow_once"
                        ),
                        None,
                    )
                if selected is None:
                    raise GeminiProtocolError(
                        f"Gemini did not offer a {desired_kind} permission option"
                    )
                outcome = {"outcome": "selected", "optionId": selected["optionId"]}
            await self._write(
                {"jsonrpc": "2.0", "id": request_id, "result": {"outcome": outcome}}
            )
        except Exception:
            # Validation failed or the write raised. The entry is still
            # pending at this point, so make sure the server receives *some*
            # response (a JSON-RPC error) instead of hanging forever, then
            # remove the pending entry and surface the error to the caller.
            try:
                await self._write(
                    {
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "error": {
                            "code": -32603,
                            "message": "Failed to resolve approval",
                        },
                    }
                )
            except Exception:
                pass
            self._pending_approvals.pop(approval_id, None)
            self._cancel_approval_timeout(approval_id)
            raise
        self._pending_approvals.pop(approval_id, None)
        self._cancel_approval_timeout(approval_id)

    def events(self) -> AsyncIterator[AdapterEvent]:
        return iter_events(self._events)

    def _put_event(self, event: AdapterEvent) -> None:
        put_event_dropping_oldest(self._events, event, label="Gemini")

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
        self, method: str, params: dict[str, Any], timeout: float = 120
    ) -> dict[str, Any]:
        return await self._transport.request(method, params, timeout=timeout)

    async def _notify(self, method: str, params: dict[str, Any]) -> None:
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
        :meth:`_cancel_approval_timeout`; otherwise it sends a ``cancelled``
        outcome to the server and clears the pending entry.
        """
        try:
            await asyncio.sleep(300)
        except asyncio.CancelledError:
            return
        pending = self._pending_approvals.pop(approval_id, None)
        self._approval_timeouts.pop(approval_id, None)
        if pending is None:
            return
        request_id = pending[0]
        logger.warning(
            "Gemini approval %s timed out after 300s; sending cancelled response",
            approval_id,
        )
        try:
            await self._write(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {"outcome": "cancelled"},
                }
            )
        except Exception:
            logger.debug("Failed to send timeout response for %s", approval_id)

    async def _handle_server_request(self, message: dict[str, Any]) -> None:
        method = message["method"]
        params = message.get("params") or {}
        if method == "session/request_permission":
            request_id = message["id"]
            approval_id = f"gemini:{request_id}"
            options = params.get("options") or []
            session_id = params.get("sessionId", "")
            self._pending_approvals[approval_id] = (request_id, options, session_id)
            self._approval_timeouts[approval_id] = asyncio.create_task(
                self._timeout_approval(approval_id)
            )
            tool_call = params.get("toolCall") or {}
            raw_input = tool_call.get("rawInput")
            command = raw_input.get("command") if isinstance(raw_input, dict) else None
            self._put_event(
                AdapterEvent(
                    type="approval.request",
                    provider_session_id=session_id,
                    provider_turn_id=self._active_turns.get(session_id),
                    item_id=tool_call.get("toolCallId"),
                    data={
                        "approval": {
                            "id": approval_id,
                            "kind": tool_call.get("kind", "other"),
                            "command": command,
                            "reason": tool_call.get("title"),
                            "locations": tool_call.get("locations"),
                            "options": options,
                        }
                    },
                )
            )
            return
        await self._write(
            {
                "jsonrpc": "2.0",
                "id": message["id"],
                "error": {"code": -32601, "message": f"Unsupported request: {method}"},
            }
        )

    async def _handle_notification(self, method: str, params: dict[str, Any]) -> None:
        if method != "session/update":
            return
        session_id = params.get("sessionId", "")
        update = params.get("update") or {}
        turn_id = self._active_turns.get(session_id)
        update_type = update.get("sessionUpdate")
        event_type: str | None = None
        item_id = update.get("toolCallId")
        data: dict[str, Any] = {}

        if update_type == "agent_message_chunk":
            content = update.get("content") or {}
            delta = content.get("text", "") if content.get("type") == "text" else ""
            event_type = "message.delta"
            data = {"delta": delta}
            if turn_id:
                key = (session_id, turn_id)
                self._message_text[key] = self._message_text.get(key, "") + delta
        elif update_type in {"tool_call", "tool_call_update"}:
            status = update.get("status")
            event_type = (
                "tool.completed"
                if status in {"completed", "failed"}
                else "tool.started"
            )
            data = {"tool": update}
            diffs = [
                value
                for value in (update.get("content") or [])
                if isinstance(value, dict) and value.get("type") == "diff"
            ]
            if diffs:
                self._put_event(
                    AdapterEvent(
                        type="file.diff",
                        provider_session_id=session_id,
                        provider_turn_id=turn_id,
                        item_id=item_id,
                        data={"diff": diffs},
                    )
                )
        elif update_type == "usage_update":
            event_type = "usage.updated"
            data = {"usage": update}

        if event_type and session_id:
            self._put_event(
                AdapterEvent(
                    type=event_type,
                    provider_session_id=session_id,
                    provider_turn_id=turn_id,
                    item_id=item_id,
                    data=data,
                )
            )

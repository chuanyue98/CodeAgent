"""CodeBuddy Code adapter using Agent Client Protocol JSON-RPC over stdio.

CodeBuddy Code exposes an Agent Client Protocol (ACP) server via
``codebuddy --acp``: JSON-RPC 2.0 over newline-delimited JSON on stdin/stdout.
This is the same transport Codex uses, so this adapter reuses the shared
``JsonRpcStdioTransport`` and simply adapts CodeBuddy's specific handshake
quirks (permission modes arrive as ``config_option_update`` notifications
rather than a ``modes`` block, so we never require them).

On Windows the ``codebuddy`` binary on PATH is a ``.cmd`` shim that
``asyncio.create_subprocess_exec`` cannot launch directly; we wrap it in
``cmd /c`` in that case.
"""

from __future__ import annotations

import asyncio
import os
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
    ProviderCapabilities,
    ProviderSession,
    ResumeOptions,
    TurnInput,
)

logger = get_logger(__name__)


class CodeBuddyProtocolError(RuntimeError):
    pass


class CodeBuddyAdapter:
    provider_id = "codebuddy"

    def __init__(self, executable: str = "codebuddy", queue_size: int = 1024):
        self.executable = executable
        self._events: asyncio.Queue[AdapterEvent | None] = asyncio.Queue(queue_size)
        self._process: asyncio.subprocess.Process | None = None
        self._transport = JsonRpcStdioTransport(
            protocol_error=CodeBuddyProtocolError,
            crash_label="CodeBuddy ACP",
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
                "CodeBuddy CLI was not found on the CodeAgent server"
            )
            raise RuntimeError(self._unavailable_reason)
        self._stopping = False
        try:
            # On Windows the resolved executable is a ``.cmd`` shim that
            # asyncio cannot exec directly; route it through ``cmd /c``.
            if os.name == "nt" and executable.lower().endswith((".cmd", ".bat")):
                spawn_args = ["cmd", "/c", executable, "--acp"]
            else:
                spawn_args = [executable, "--acp"]
            self._process = await asyncio.create_subprocess_exec(
                *spawn_args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            self._transport.attach(
                self._process,
                reader_name="codebuddy-acp-stdout",
                stderr_name="codebuddy-acp-stderr",
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
                timeout=30,
            )
            self._unavailable_reason = None
        except Exception as exc:
            self._unavailable_reason = f"CodeBuddy ACP failed to start: {exc}"
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
        await graceful_terminate(process, logger=logger, label="CodeBuddy ACP")
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
            display_name="CodeBuddy Code",
            available=running,
            unavailable_reason=None
            if running
            else (self._unavailable_reason or "CodeBuddy ACP is not running"),
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
            raise CodeBuddyProtocolError(
                "session/new response did not include sessionId"
            )
        await self._configure_session(session_id, result, options)
        return ProviderSession(
            id=session_id, model=self._result_model(result, options.model)
        )

    async def resume_session(
        self, provider_session_id: str, options: ResumeOptions
    ) -> ProviderSession:
        result = await self._request(
            "session/load",
            {
                "sessionId": provider_session_id,
                "cwd": options.cwd,
                "mcpServers": [],
            },
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
        # CodeBuddy reports available models under ``models`` (not the
        # ``modes``/``session/set_mode`` shape ACP defines) and surfaces
        # permission modes as runtime ``config_option_update`` notifications.
        # We best-effort the model selection and never require a mode, so an
        # unusual response shape can't break session creation.
        current_model = (result.get("models") or {}).get("currentModelId")
        if options.model and options.model != current_model:
            try:
                await self._request(
                    "session/set_model",
                    {"sessionId": session_id, "modelId": options.model},
                )
            except Exception as exc:  # pragma: no cover - protocol tolerance
                logger.warning("CodeBuddy set_model failed (ignored): %s", exc)

    @staticmethod
    def _result_model(result: dict[str, Any], requested: str | None) -> str | None:
        current = (result.get("models") or {}).get("currentModelId")
        return requested or (current if isinstance(current, str) else None)

    async def start_turn(self, provider_session_id: str, turn: TurnInput) -> str:
        active = self._turn_tasks.get(provider_session_id)
        if active and not active.done():
            raise CodeBuddyProtocolError("CodeBuddy session already has an active turn")
        turn_id = f"codebuddy-turn-{uuid4().hex}"
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
            name=f"codebuddy-turn-{provider_session_id}",
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
        raise CodeBuddyProtocolError(
            "CodeBuddy ACP does not support same-turn steering"
        )

    async def cancel_turn(
        self, provider_session_id: str, provider_turn_id: str
    ) -> None:
        await self._notify("session/cancel", {"sessionId": provider_session_id})

    async def respond_to_approval(
        self, approval_id: str, decision: ApprovalDecision
    ) -> None:
        pending = self._pending_approvals.get(approval_id)
        if pending is None:
            raise CodeBuddyProtocolError("Approval request is no longer pending")
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
                    raise CodeBuddyProtocolError(
                        f"CodeBuddy did not offer a {desired_kind} permission option"
                    )
                outcome = {"outcome": "selected", "optionId": selected["optionId"]}
            await self._write(
                {"jsonrpc": "2.0", "id": request_id, "result": {"outcome": outcome}}
            )
        except Exception:
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
        put_event_dropping_oldest(self._events, event, label="CodeBuddy")

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
        task = self._approval_timeouts.pop(approval_id, None)
        if task is not None:
            task.cancel()

    async def _timeout_approval(self, approval_id: str) -> None:
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
            "CodeBuddy approval %s timed out after 300s; sending cancelled response",
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
            approval_id = f"codebuddy:{request_id}"
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

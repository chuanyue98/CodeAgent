"""Gemini CLI adapter using Agent Client Protocol JSON-RPC over stdio."""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
from collections.abc import AsyncIterator
from typing import Any
from uuid import uuid4

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

logger = logging.getLogger(__name__)


class GeminiProtocolError(RuntimeError):
    pass


class GeminiAdapter:
    provider_id = "gemini"

    def __init__(self, executable: str = "gemini", queue_size: int = 1024):
        self.executable = executable
        self._events: asyncio.Queue[AdapterEvent | None] = asyncio.Queue(queue_size)
        self._process: asyncio.subprocess.Process | None = None
        self._reader_task: asyncio.Task | None = None
        self._stderr_task: asyncio.Task | None = None
        self._pending: dict[str, asyncio.Future] = {}
        self._pending_approvals: dict[str, tuple[Any, list[dict[str, Any]], str]] = {}
        self._turn_tasks: dict[str, asyncio.Task] = {}
        self._active_turns: dict[str, str] = {}
        self._message_text: dict[tuple[str, str], str] = {}
        self._next_request_id = 1
        self._write_lock = asyncio.Lock()
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
            self._reader_task = asyncio.create_task(
                self._read_loop(), name="gemini-acp-stdout"
            )
            self._stderr_task = asyncio.create_task(
                self._drain_stderr(), name="gemini-acp-stderr"
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
        if process and process.returncode is None:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=3)
            except TimeoutError:
                process.kill()
                try:
                    await asyncio.wait_for(process.wait(), timeout=5)
                except TimeoutError:
                    logger.warning(
                        "Gemini ACP process (pid=%s) did not exit after SIGKILL; "
                        "abandoning it to avoid blocking shutdown",
                        process.pid,
                    )
        for subprocess_task in (self._reader_task, self._stderr_task):
            if subprocess_task:
                subprocess_task.cancel()
        await asyncio.gather(
            *(task for task in (self._reader_task, self._stderr_task) if task),
            return_exceptions=True,
        )
        self._reader_task = self._stderr_task = None
        for future in self._pending.values():
            if not future.done():
                future.set_exception(GeminiProtocolError("Gemini ACP stopped"))
        self._pending.clear()
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
        await self._events.put(
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
            await self._events.put(
                AdapterEvent(
                    type="message.completed",
                    provider_session_id=provider_session_id,
                    provider_turn_id=turn_id,
                    data={"text": text},
                )
            )
            usage = result.get("usage")
            if isinstance(usage, dict):
                await self._events.put(
                    AdapterEvent(
                        type="usage.updated",
                        provider_session_id=provider_session_id,
                        provider_turn_id=turn_id,
                        data={"usage": usage},
                    )
                )
            await self._events.put(
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
            await self._events.put(
                AdapterEvent(
                    type="error",
                    provider_session_id=provider_session_id,
                    provider_turn_id=turn_id,
                    data={"code": "provider_error", "message": str(exc)},
                )
            )
            await self._events.put(
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
        pending = self._pending_approvals.pop(approval_id, None)
        if pending is None:
            raise GeminiProtocolError("Approval request is no longer pending")
        request_id, options, _session_id = pending
        if decision == ApprovalDecision.CANCEL:
            outcome = {"outcome": "cancelled"}
        else:
            desired_kind = {
                ApprovalDecision.ACCEPT: "allow_once",
                ApprovalDecision.ACCEPT_FOR_SESSION: "allow_always",
                ApprovalDecision.DECLINE: "reject_once",
            }[decision]
            selected = next(
                (option for option in options if option.get("kind") == desired_kind),
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

    async def events(self) -> AsyncIterator[AdapterEvent]:
        while True:
            event = await self._events.get()
            if event is None:
                return
            yield event

    async def _request(
        self, method: str, params: dict[str, Any], timeout: float = 120
    ) -> dict[str, Any]:
        request_id = self._next_request_id
        self._next_request_id += 1
        future = asyncio.get_running_loop().create_future()
        self._pending[str(request_id)] = future
        await self._write(
            {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}
        )
        try:
            result = await asyncio.wait_for(future, timeout=timeout)
        finally:
            self._pending.pop(str(request_id), None)
        if not isinstance(result, dict):
            raise GeminiProtocolError(f"{method} returned a non-object result")
        return result

    async def _notify(self, method: str, params: dict[str, Any]) -> None:
        await self._write({"jsonrpc": "2.0", "method": method, "params": params})

    async def _write(self, message: dict[str, Any]) -> None:
        process = self._process
        if not process or process.returncode is not None or not process.stdin:
            raise GeminiProtocolError("Gemini ACP is not running")
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
                                GeminiProtocolError(str(message["error"]))
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
            if not self._stopping and self._process is not None:
                error = GeminiProtocolError("Gemini ACP exited unexpectedly")
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
        if method == "session/request_permission":
            request_id = message["id"]
            approval_id = f"gemini:{request_id}"
            options = params.get("options") or []
            session_id = params.get("sessionId", "")
            self._pending_approvals[approval_id] = (request_id, options, session_id)
            tool_call = params.get("toolCall") or {}
            raw_input = tool_call.get("rawInput")
            command = raw_input.get("command") if isinstance(raw_input, dict) else None
            await self._events.put(
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
                await self._events.put(
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
            await self._events.put(
                AdapterEvent(
                    type=event_type,
                    provider_session_id=session_id,
                    provider_turn_id=turn_id,
                    item_id=item_id,
                    data=data,
                )
            )

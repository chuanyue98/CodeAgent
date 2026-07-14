"""Claude Agent SDK adapter with interactive permission callbacks."""

from __future__ import annotations

import asyncio
import shutil
from collections.abc import AsyncIterator, Callable
from typing import Any
from uuid import uuid4

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    PermissionResultAllow,
    PermissionResultDeny,
    ResultMessage,
    StreamEvent,
    SystemMessage,
    TextBlock,
    ToolPermissionContext,
    ToolResultBlock,
    ToolUseBlock,
)

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


class ClaudeProtocolError(RuntimeError):
    pass


class ClaudeAdapter:
    provider_id = "claude"

    def __init__(
        self,
        executable: str = "claude",
        queue_size: int = 1024,
        client_factory: Callable[[ClaudeAgentOptions], ClaudeSDKClient] = ClaudeSDKClient,
    ):
        self.executable = executable
        self._client_factory = client_factory
        self._events: asyncio.Queue[AdapterEvent | None] = asyncio.Queue(queue_size)
        self._clients: dict[str, ClaudeSDKClient] = {}
        self._client_tasks: dict[str, asyncio.Task] = {}
        self._active_turns: dict[str, str] = {}
        self._session_cwds: dict[str, str] = {}
        self._pending_approvals: dict[
            str,
            tuple[
                str,
                asyncio.Future[PermissionResultAllow | PermissionResultDeny],
                ToolPermissionContext,
            ],
        ] = {}
        self._current_message_ids: dict[str, str] = {}
        self._started_tools: set[tuple[str, str]] = set()
        self._started = False
        self._unavailable_reason: str | None = None

    async def start(self) -> None:
        if self._started:
            return
        if not shutil.which(self.executable):
            self._unavailable_reason = "Claude Code CLI was not found on the CodeAgent server"
            raise RuntimeError(self._unavailable_reason)
        self._started = True
        self._unavailable_reason = None

    async def stop(self) -> None:
        self._started = False
        for _approval_id, (_session_id, future, _context) in list(
            self._pending_approvals.items()
        ):
            if not future.done():
                future.set_result(
                    PermissionResultDeny(
                        message="CodeAgent Gateway is shutting down", interrupt=True
                    )
                )
        self._pending_approvals.clear()
        for task in self._client_tasks.values():
            task.cancel()
        await asyncio.gather(*self._client_tasks.values(), return_exceptions=True)
        self._client_tasks.clear()
        await asyncio.gather(
            *(client.disconnect() for client in self._clients.values()),
            return_exceptions=True,
        )
        self._clients.clear()
        self._active_turns.clear()
        self._session_cwds.clear()
        self._current_message_ids.clear()
        self._started_tools.clear()

    async def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            provider_id=self.provider_id,
            display_name="Claude Code",
            available=self._started,
            unavailable_reason=None
            if self._started
            else (self._unavailable_reason or "Claude adapter is not running"),
            supports_resume=True,
            supports_steer=False,
            supports_cancel=True,
            supports_approvals=True,
            supports_file_diff=False,
            supports_tool_events=True,
            supports_attachments=False,
            supports_model_switch=True,
        )

    async def create_session(self, options: CreateSessionOptions) -> ProviderSession:
        self._require_started()
        session_id = str(uuid4())
        client = await self._connect_client(
            session_id,
            cwd=options.cwd,
            model=options.model,
            permission_mode=options.permission_mode,
            resume=False,
        )
        info = await client.get_server_info() or {}
        return ProviderSession(
            id=session_id,
            model=info.get("model") if isinstance(info.get("model"), str) else options.model,
        )

    async def resume_session(
        self, provider_session_id: str, options: ResumeOptions
    ) -> ProviderSession:
        self._require_started()
        existing = self._clients.get(provider_session_id)
        if existing is not None:
            info = await existing.get_server_info() or {}
            return ProviderSession(
                id=provider_session_id,
                model=info.get("model")
                if isinstance(info.get("model"), str)
                else options.model,
            )
        client = await self._connect_client(
            provider_session_id,
            cwd=options.cwd,
            model=options.model,
            permission_mode=options.permission_mode,
            resume=True,
        )
        info = await client.get_server_info() or {}
        return ProviderSession(
            id=provider_session_id,
            model=info.get("model") if isinstance(info.get("model"), str) else options.model,
        )

    async def start_turn(self, provider_session_id: str, turn: TurnInput) -> str:
        client = self._client(provider_session_id)
        active = self._client_tasks.get(provider_session_id)
        if active and not active.done():
            raise ClaudeProtocolError("Claude session already has an active turn")
        turn_id = f"claude-turn-{uuid4().hex}"
        self._active_turns[provider_session_id] = turn_id
        await client.query(
            "\n".join(value.text for value in turn.input),
            session_id=provider_session_id,
        )
        self._put_event(
            AdapterEvent(
                type="turn.started",
                provider_session_id=provider_session_id,
                provider_turn_id=turn_id,
            )
        )
        self._client_tasks[provider_session_id] = asyncio.create_task(
            self._consume_response(provider_session_id, turn_id),
            name=f"claude-turn-{provider_session_id}",
        )
        return turn_id

    async def steer_turn(
        self, provider_session_id: str, provider_turn_id: str, turn: TurnInput
    ) -> None:
        raise ClaudeProtocolError("Claude same-turn steering is not enabled")

    async def cancel_turn(
        self, provider_session_id: str, provider_turn_id: str
    ) -> None:
        client = self._client(provider_session_id)
        for approval_id, (session_id, future, _context) in list(
            self._pending_approvals.items()
        ):
            if session_id != provider_session_id:
                continue
            if not future.done():
                future.set_result(
                    PermissionResultDeny(message="Turn cancelled", interrupt=True)
                )
            self._pending_approvals.pop(approval_id, None)
        await client.interrupt()

    async def respond_to_approval(
        self, approval_id: str, decision: ApprovalDecision
    ) -> None:
        pending = self._pending_approvals.pop(approval_id, None)
        if pending is None:
            raise ClaudeProtocolError("Approval request is no longer pending")
        _session_id, future, context = pending
        if future.done():
            raise ClaudeProtocolError("Approval request is already resolved")
        if decision == ApprovalDecision.ACCEPT:
            result: PermissionResultAllow | PermissionResultDeny = PermissionResultAllow()
        elif decision == ApprovalDecision.ACCEPT_FOR_SESSION:
            result = PermissionResultAllow(
                updated_permissions=context.suggestions or None
            )
        else:
            result = PermissionResultDeny(
                message="Denied by the user",
                interrupt=decision == ApprovalDecision.CANCEL,
            )
        future.set_result(result)

    async def events(self) -> AsyncIterator[AdapterEvent]:
        while True:
            event = await self._events.get()
            if event is None:
                return
            yield event

    def _require_started(self) -> None:
        if not self._started:
            raise ClaudeProtocolError("Claude adapter is not running")

    def _client(self, provider_session_id: str) -> ClaudeSDKClient:
        self._require_started()
        client = self._clients.get(provider_session_id)
        if client is None:
            raise ClaudeProtocolError("Claude session is not connected; resume it first")
        return client

    async def _connect_client(
        self,
        session_id: str,
        *,
        cwd: str,
        model: str | None,
        permission_mode: PermissionMode,
        resume: bool,
    ) -> ClaudeSDKClient:
        async def can_use_tool(
            tool_name: str,
            tool_input: dict[str, Any],
            context: ToolPermissionContext,
        ) -> PermissionResultAllow | PermissionResultDeny:
            approval_id = context.tool_use_id or f"claude-approval-{uuid4().hex}"
            future: asyncio.Future[
                PermissionResultAllow | PermissionResultDeny
            ] = asyncio.get_running_loop().create_future()
            self._pending_approvals[approval_id] = (session_id, future, context)
            self._put_event(
                AdapterEvent(
                    type="approval.request",
                    provider_session_id=session_id,
                    provider_turn_id=self._active_turns.get(session_id),
                    item_id=context.tool_use_id,
                    data={
                        "approval": {
                            "id": approval_id,
                            "kind": tool_name,
                            "command": tool_input.get("command"),
                            "cwd": self._session_cwds.get(session_id),
                            "reason": context.title
                            or context.description
                            or context.decision_reason,
                            "blockedPath": context.blocked_path,
                            "metadata": tool_input,
                        }
                    },
                )
            )
            try:
                return await future
            finally:
                self._pending_approvals.pop(approval_id, None)

        sdk_mode = "plan" if permission_mode == PermissionMode.READ_ONLY else "default"
        options = ClaudeAgentOptions(
            cwd=cwd,
            cli_path=shutil.which(self.executable),
            model=model,
            permission_mode=sdk_mode,
            can_use_tool=can_use_tool,
            include_partial_messages=True,
            include_hook_events=True,
            setting_sources=["user", "project", "local"],
            resume=session_id if resume else None,
            session_id=None if resume else session_id,
            stderr=lambda _line: None,
        )
        client = self._client_factory(options)
        try:
            await client.connect()
        except Exception:
            await client.disconnect()
            raise
        self._clients[session_id] = client
        self._session_cwds[session_id] = cwd
        return client

    async def _consume_response(self, session_id: str, turn_id: str) -> None:
        client = self._client(session_id)
        try:
            async for message in client.receive_response():
                for event in self._translate_message(session_id, turn_id, message):
                    self._put_event(event)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._put_event(
                AdapterEvent(
                    type="error",
                    provider_session_id=session_id,
                    provider_turn_id=turn_id,
                    data={
                        "code": "provider_error",
                        "message": str(exc),
                        "retryable": True,
                    },
                )
            )
            self._put_event(
                AdapterEvent(
                    type="turn.completed",
                    provider_session_id=session_id,
                    provider_turn_id=turn_id,
                    data={"status": "failed"},
                )
            )
        finally:
            self._active_turns.pop(session_id, None)
            self._current_message_ids.pop(session_id, None)

    def _translate_message(
        self, session_id: str, turn_id: str, message: Any
    ) -> list[AdapterEvent]:
        def event(
            kind: str,
            data: dict[str, Any] | None = None,
            *,
            item_id: str | None = None,
        ) -> AdapterEvent:
            return AdapterEvent(
                type=kind,
                provider_session_id=session_id,
                provider_turn_id=turn_id,
                item_id=item_id,
                data=data or {},
            )

        if isinstance(message, StreamEvent):
            raw = message.event
            raw_type = raw.get("type")
            if raw_type == "message_start":
                message_id = (raw.get("message") or {}).get("id")
                if isinstance(message_id, str):
                    self._current_message_ids[session_id] = message_id
                return []
            if raw_type == "content_block_delta":
                delta = raw.get("delta") or {}
                if delta.get("type") != "text_delta":
                    return []
                index = raw.get("index", 0)
                message_id = self._current_message_ids.get(session_id, turn_id)
                return [
                    event(
                        "message.delta",
                        {"delta": delta.get("text", "")},
                        item_id=f"{message_id}:text:{index}",
                    )
                ]
            if raw_type == "content_block_start":
                block = raw.get("content_block") or {}
                if block.get("type") != "tool_use":
                    return []
                tool_id = block.get("id")
                if not isinstance(tool_id, str):
                    return []
                self._started_tools.add((session_id, tool_id))
                return [
                    event(
                        "tool.started",
                        {
                            "tool": {
                                "id": tool_id,
                                "name": block.get("name"),
                                "input": block.get("input", {}),
                            }
                        },
                        item_id=tool_id,
                    )
                ]
            return []

        if isinstance(message, AssistantMessage):
            translated: list[AdapterEvent] = []
            message_id = message.message_id or self._current_message_ids.get(
                session_id, turn_id
            )
            for index, block in enumerate(message.content):
                if isinstance(block, TextBlock):
                    translated.append(
                        event(
                            "message.completed",
                            {"text": block.text},
                            item_id=f"{message_id}:text:{index}",
                        )
                    )
                elif isinstance(block, ToolUseBlock):
                    key = (session_id, block.id)
                    if key not in self._started_tools:
                        self._started_tools.add(key)
                        translated.append(
                            event(
                                "tool.started",
                                {
                                    "tool": {
                                        "id": block.id,
                                        "name": block.name,
                                        "input": block.input,
                                    }
                                },
                                item_id=block.id,
                            )
                        )
                elif isinstance(block, ToolResultBlock):
                    self._started_tools.discard((session_id, block.tool_use_id))
                    translated.append(
                        event(
                            "tool.completed",
                            {
                                "tool": {
                                    "id": block.tool_use_id,
                                    "status": "failed" if block.is_error else "completed",
                                    "result": block.content,
                                }
                            },
                            item_id=block.tool_use_id,
                        )
                    )
            return translated

        if isinstance(message, ResultMessage):
            status = "failed" if message.is_error else "completed"
            return [
                event(
                    "usage.updated",
                    {
                        "usage": message.usage or {},
                        "cost": message.total_cost_usd,
                        "modelUsage": message.model_usage,
                    },
                ),
                event(
                    "turn.completed",
                    {
                        "status": status,
                        "stopReason": message.stop_reason,
                        "permissionDenials": message.permission_denials,
                    },
                ),
            ]

        if isinstance(message, SystemMessage) and message.subtype == "status":
            if message.data.get("status") == "compacting":
                return [event("session.compacting")]
        return []

    def _put_event(self, event: AdapterEvent) -> None:
        try:
            self._events.put_nowait(event)
        except asyncio.QueueFull:
            try:
                self._events.get_nowait()
            except asyncio.QueueEmpty:
                pass
            self._events.put_nowait(
                AdapterEvent(
                    type="error",
                    provider_session_id="",
                    data={
                        "code": "provider_backpressure",
                        "message": "Claude event queue overflowed",
                        "retryable": True,
                    },
                )
            )

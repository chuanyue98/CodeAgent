"""OpenCode headless-server adapter using its loopback HTTP/SSE API."""

from __future__ import annotations

import asyncio
import base64
import json
import secrets
import shutil
import socket
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import AsyncIterator
from typing import Any

from core.host_env import child_environ
from core.logging_config import get_logger
from core.services.agent_adapters._event_queue import (
    iter_events,
    put_event_dropping_oldest,
)
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


class OpenCodeProtocolError(RuntimeError):
    pass


class OpenCodeAdapter:
    provider_id = "opencode"

    def __init__(self, executable: str = "opencode", queue_size: int = 1024):
        self.executable = executable
        self._events: asyncio.Queue[AdapterEvent | None] = asyncio.Queue(queue_size)
        self._process: asyncio.subprocess.Process | None = None
        self._base_url: str | None = None
        self._password: str | None = None
        self._stderr_task: asyncio.Task | None = None
        self._stdout_task: asyncio.Task | None = None
        self._sse_task: asyncio.Task | None = None
        self._sse_response: Any | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._started = False
        self._stopping = False
        self._unavailable_reason: str | None = None
        self._active_turns: dict[str, str] = {}
        self._pending_approvals: dict[str, str] = {}
        self._stderr_lines: list[str] = []

    @staticmethod
    def _reserve_port() -> int:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            return int(sock.getsockname()[1])

    async def start(self) -> None:
        if self._started:
            return
        executable = shutil.which(self.executable)
        if not executable:
            self._unavailable_reason = (
                "OpenCode CLI was not found on the CodeAgent server"
            )
            raise RuntimeError(self._unavailable_reason)
        self._stopping = False
        self._loop = asyncio.get_running_loop()
        self._password = secrets.token_urlsafe(32)
        env = child_environ()
        env["OPENCODE_SERVER_PASSWORD"] = self._password

        # _reserve_port() closes its probe socket before the child process
        # binds the same port, leaving a small TOCTOU window where another
        # process could grab it first. Rather than reworking process
        # startup to hand the child an already-bound socket, treat an
        # immediate exit on the first attempt as a possible port collision
        # and retry once on a freshly reserved port.
        max_attempts = 2
        last_exc: Exception = OpenCodeProtocolError("OpenCode server failed to start")
        for attempt in range(max_attempts):
            port = self._reserve_port()
            self._base_url = f"http://127.0.0.1:{port}"
            try:
                await self._spawn_and_wait_healthy(executable, port, env)
                self._started = True
                self._unavailable_reason = None
                self._sse_task = asyncio.create_task(
                    asyncio.to_thread(self._sse_worker), name="opencode-global-events"
                )
                return
            except Exception as exc:
                last_exc = exc
                retry = (
                    attempt < max_attempts - 1
                    and self._process is not None
                    and self._process.returncode is not None
                )
                await self.stop()
                if not retry:
                    break

        stderr_tail = "\n".join(self._stderr_lines[-20:])
        detail = f"\nstderr:\n{stderr_tail}" if stderr_tail else ""
        self._unavailable_reason = (
            f"OpenCode server failed to start: {last_exc}{detail}"
        )
        raise RuntimeError(self._unavailable_reason) from last_exc

    async def _spawn_and_wait_healthy(
        self, executable: str, port: int, env: dict[str, str]
    ) -> None:
        """Spawn the OpenCode server on ``port`` and wait for it to report healthy.

        Raises if the process exits early or never becomes healthy within
        the startup deadline; the caller decides whether that's worth a
        retry on a different port.
        """
        assert self._loop is not None
        self._process = await asyncio.create_subprocess_exec(
            executable,
            "serve",
            "--hostname",
            "127.0.0.1",
            "--port",
            str(port),
            "--log-level",
            "WARN",
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        self._stderr_lines = []
        self._stdout_task = asyncio.create_task(
            self._drain(self._process.stdout), name="opencode-server-stdout"
        )
        self._stderr_task = asyncio.create_task(
            self._drain(self._process.stderr, self._stderr_lines),
            name="opencode-server-stderr",
        )
        deadline = self._loop.time() + 20
        while True:
            if self._process.returncode is not None:
                raise OpenCodeProtocolError("OpenCode server exited during startup")
            try:
                health = await self._request_json("GET", "/global/health", timeout=2)
                if health.get("healthy") is True:
                    break
            except Exception:
                if self._loop.time() >= deadline:
                    raise
                await asyncio.sleep(0.1)

    async def stop(self) -> None:
        self._stopping = True
        self._started = False
        response = self._sse_response
        self._sse_response = None
        if response is not None:
            try:
                response.close()
            except Exception:
                pass
        process = self._process
        self._process = None
        await graceful_terminate(
            process,
            logger=logger,
            label="OpenCode",
            terminate_timeout=5,
        )
        for task in (self._sse_task, self._stdout_task, self._stderr_task):
            if task:
                task.cancel()
        await asyncio.gather(
            *(
                task
                for task in (self._sse_task, self._stdout_task, self._stderr_task)
                if task
            ),
            return_exceptions=True,
        )
        self._sse_task = self._stdout_task = self._stderr_task = None
        self._active_turns.clear()
        self._pending_approvals.clear()

    async def capabilities(self) -> ProviderCapabilities:
        running = (
            self._started
            and self._process is not None
            and self._process.returncode is None
        )
        return ProviderCapabilities(
            provider_id=self.provider_id,
            display_name="OpenCode",
            available=running,
            unavailable_reason=None
            if running
            else (self._unavailable_reason or "OpenCode server is not running"),
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
        body: dict[str, Any] = {}
        model = self._parse_model(options.model)
        if model:
            body["model"] = {"providerID": model[0], "id": model[1]}
        if options.permission_mode == PermissionMode.READ_ONLY:
            body["permission"] = [
                {"permission": "*", "pattern": "*", "action": "deny"},
                {"permission": "read", "pattern": "*", "action": "allow"},
                {"permission": "list", "pattern": "*", "action": "allow"},
                {"permission": "glob", "pattern": "*", "action": "allow"},
                {"permission": "grep", "pattern": "*", "action": "allow"},
            ]
        result = await self._request_json(
            "POST",
            "/session?" + urllib.parse.urlencode({"directory": options.cwd}),
            body,
        )
        session_id = result.get("id")
        if not isinstance(session_id, str):
            raise OpenCodeProtocolError("session.create did not return an id")
        returned_model = result.get("model") or {}
        model_name = self._format_model(returned_model) or options.model
        return ProviderSession(id=session_id, model=model_name)

    async def resume_session(
        self, provider_session_id: str, options: ResumeOptions
    ) -> ProviderSession:
        result = await self._request_json(
            "GET",
            f"/session/{urllib.parse.quote(provider_session_id, safe='')}?"
            + urllib.parse.urlencode({"directory": options.cwd}),
        )
        if result.get("id") != provider_session_id:
            raise OpenCodeProtocolError("OpenCode session could not be resumed")
        return ProviderSession(
            id=provider_session_id,
            model=self._format_model(result.get("model") or {}) or options.model,
        )

    async def start_turn(self, provider_session_id: str, turn: TurnInput) -> str:
        result = await self._prompt(provider_session_id, turn, delivery="steer")
        admitted = result.get("data") or result
        turn_id = admitted.get("id")
        if not isinstance(turn_id, str):
            raise OpenCodeProtocolError("session.prompt did not return a message id")
        self._active_turns[provider_session_id] = turn_id
        return turn_id

    async def steer_turn(
        self, provider_session_id: str, provider_turn_id: str, turn: TurnInput
    ) -> None:
        await self._prompt(provider_session_id, turn, delivery="steer")

    async def cancel_turn(
        self, provider_session_id: str, provider_turn_id: str
    ) -> None:
        for approval_id, session_id in list(self._pending_approvals.items()):
            if session_id == provider_session_id:
                self._pending_approvals.pop(approval_id, None)
        await self._request_json(
            "POST",
            f"/api/session/{urllib.parse.quote(provider_session_id, safe='')}/interrupt",
        )

    async def respond_to_approval(
        self, approval_id: str, decision: ApprovalDecision
    ) -> None:
        session_id = self._pending_approvals.pop(approval_id, None)
        if session_id is None:
            raise OpenCodeProtocolError("Approval request is no longer pending")
        reply = {
            ApprovalDecision.ACCEPT: "once",
            ApprovalDecision.ACCEPT_FOR_SESSION: "always",
            ApprovalDecision.DECLINE: "reject",
            ApprovalDecision.CANCEL: "reject",
        }[decision]
        await self._request_json(
            "POST",
            f"/api/session/{urllib.parse.quote(session_id, safe='')}/permission/"
            f"{urllib.parse.quote(approval_id, safe='')}/reply",
            {"reply": reply},
        )
        if decision == ApprovalDecision.CANCEL:
            await self.cancel_turn(session_id, self._active_turns.get(session_id, ""))

    def events(self) -> AsyncIterator[AdapterEvent]:
        return iter_events(self._events)

    async def _prompt(
        self, provider_session_id: str, turn: TurnInput, *, delivery: str
    ) -> dict[str, Any]:
        text = "\n".join(value.text for value in turn.input)
        return await self._request_json(
            "POST",
            f"/api/session/{urllib.parse.quote(provider_session_id, safe='')}/prompt",
            {"prompt": {"text": text}, "delivery": delivery},
        )

    @staticmethod
    def _parse_model(model: str | None) -> tuple[str, str] | None:
        if not model or "/" not in model:
            return None
        provider, model_id = model.split("/", 1)
        return provider, model_id

    @staticmethod
    def _format_model(model: dict[str, Any]) -> str | None:
        provider = model.get("providerID")
        model_id = model.get("id") or model.get("modelID")
        if isinstance(provider, str) and isinstance(model_id, str):
            return f"{provider}/{model_id}"
        return None

    def _headers(self) -> dict[str, str]:
        if not self._password:
            return {}
        token = base64.b64encode(f"opencode:{self._password}".encode()).decode()
        return {"Authorization": f"Basic {token}"}

    async def _request_json(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        timeout: float = 30,
    ) -> dict[str, Any]:
        return await asyncio.to_thread(
            self._request_json_sync, method, path, body, timeout
        )

    def _request_json_sync(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None,
        timeout: float,
    ) -> dict[str, Any]:
        if not self._base_url:
            raise OpenCodeProtocolError("OpenCode server is not running")
        data = json.dumps(body).encode() if body is not None else None
        headers = self._headers()
        if data is not None:
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            self._base_url + path, data=data, headers=headers, method=method
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                payload = response.read()
                if not payload:
                    return {}
                result = json.loads(payload)
                if not isinstance(result, dict):
                    return {"data": result}
                return result
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(errors="replace")
            raise OpenCodeProtocolError(
                f"OpenCode HTTP {exc.code}: {detail or exc.reason}"
            ) from exc
        except urllib.error.URLError as exc:
            raise OpenCodeProtocolError(
                f"OpenCode request failed: {exc.reason}"
            ) from exc

    async def _drain(
        self, stream: asyncio.StreamReader | None, buffer: list[str] | None = None
    ) -> None:
        if stream is None:
            return
        try:
            while line := await stream.readline():
                if buffer is not None:
                    buffer.append(line.decode(errors="replace").rstrip())
                    del buffer[:-20]
        except asyncio.CancelledError:
            raise

    def _sse_worker(self) -> None:
        if not self._base_url or not self._loop:
            return
        request = urllib.request.Request(
            self._base_url + "/global/event", headers=self._headers(), method="GET"
        )
        try:
            # A long-lived SSE stream legitimately has no data for stretches
            # at a time, so this can't use a short read timeout without
            # tearing down idle-but-healthy connections. An unbounded
            # timeout, though, means a peer that stops responding without
            # closing the socket (e.g. the OpenCode process wedging) leaves
            # this thread blocked forever. 300s is a conservative ceiling
            # that tolerates normal idle gaps while still guaranteeing the
            # worker eventually notices a truly stuck connection.
            response = urllib.request.urlopen(request, timeout=300)
            self._sse_response = response
            if self._stopping:
                response.close()
                self._sse_response = None
                return
            data_lines: list[str] = []
            for raw_line in response:
                line = raw_line.decode(errors="replace").rstrip("\r\n")
                if not line:
                    if data_lines:
                        try:
                            envelope = json.loads("\n".join(data_lines))
                            self._loop.call_soon_threadsafe(
                                self._handle_sse_envelope, envelope
                            )
                        except json.JSONDecodeError:
                            pass
                        data_lines.clear()
                    continue
                if line.startswith("data:"):
                    data_lines.append(line[5:].lstrip())
        except Exception as exc:
            if not self._stopping and self._loop:
                self._loop.call_soon_threadsafe(
                    self._emit_global_error,
                    f"OpenCode event stream stopped: {exc}",
                )
        finally:
            self._sse_response = None

    def _put_event(self, event: AdapterEvent) -> None:
        put_event_dropping_oldest(self._events, event, label="OpenCode")

    def _emit_global_error(self, message: str) -> None:
        self._put_event(
            AdapterEvent(
                type="error",
                provider_session_id="",
                data={
                    "code": "provider_crashed",
                    "message": message,
                    "retryable": True,
                },
            )
        )

    def _handle_sse_envelope(self, envelope: dict[str, Any]) -> None:
        payload = envelope.get("payload") or envelope
        if not isinstance(payload, dict) or payload.get("type") == "sync":
            return
        for event in self._translate_event(payload):
            self._put_event(event)

    def _translate_event(self, payload: dict[str, Any]) -> list[AdapterEvent]:
        event_type = payload.get("type")
        data = payload.get("properties") or payload.get("data") or {}
        if not isinstance(data, dict):
            return []
        session_id = data.get("sessionID")
        if not isinstance(session_id, str):
            return []
        # The turn id we hand back to callers from start_turn() is the
        # "admitted" message id from the initial prompt response, which is
        # what all subsequent events must be tagged with for callers to
        # correlate them. OpenCode's own assistantMessageID (used below only
        # as a fallback for turns we didn't initiate) is a different id, so
        # the already-tracked value always takes priority.
        turn_id = self._active_turns.get(session_id) or data.get("assistantMessageID")
        item_id = data.get("textID") or data.get("callID")

        def event(kind: str, event_data: dict[str, Any] | None = None) -> AdapterEvent:
            return AdapterEvent(
                type=kind,
                provider_session_id=session_id,
                provider_turn_id=turn_id if isinstance(turn_id, str) else None,
                item_id=item_id if isinstance(item_id, str) else None,
                data=event_data or {},
            )

        if event_type == "session.next.step.started":
            if session_id not in self._active_turns:
                assistant_id = data.get("assistantMessageID")
                if isinstance(assistant_id, str):
                    self._active_turns[session_id] = assistant_id
                    turn_id = assistant_id
            return [event("turn.started")]
        if event_type == "session.next.text.delta":
            return [event("message.delta", {"delta": data.get("delta", "")})]
        if event_type == "session.next.text.ended":
            return [event("message.completed", {"text": data.get("text", "")})]
        if event_type in {"session.next.tool.called", "session.next.shell.started"}:
            tool = {
                "id": data.get("callID"),
                "name": data.get("tool") or "shell",
                "input": data.get("input") or {"command": data.get("command")},
                "kind": "command" if event_type.endswith("shell.started") else "tool",
            }
            return [event("tool.started", {"tool": tool})]
        if event_type == "session.next.tool.progress":
            return [
                event(
                    "command.output",
                    {
                        "commandId": data.get("callID"),
                        "stream": "stdout",
                        "delta": self._content_text(data.get("content")),
                    },
                )
            ]
        if event_type == "session.next.shell.ended":
            return [
                event(
                    "command.output",
                    {
                        "commandId": data.get("callID"),
                        "stream": "stdout",
                        "delta": data.get("output", ""),
                    },
                ),
                event(
                    "tool.completed",
                    {"tool": {"id": data.get("callID"), "status": "completed"}},
                ),
            ]
        if event_type in {"session.next.tool.success", "session.next.tool.failed"}:
            status = "completed" if event_type.endswith("success") else "failed"
            return [event("tool.completed", {"tool": {**data, "status": status}})]
        if event_type in {"permission.v2.asked", "permission.asked"}:
            approval_id = data.get("id")
            if not isinstance(approval_id, str):
                return []
            self._pending_approvals[approval_id] = session_id
            return [
                event(
                    "approval.request",
                    {
                        "approval": {
                            "id": approval_id,
                            "kind": data.get("action") or data.get("permission"),
                            "resources": data.get("resources") or data.get("patterns"),
                            "reason": data.get("metadata", {}).get("description")
                            if isinstance(data.get("metadata"), dict)
                            else None,
                            "metadata": data.get("metadata"),
                        }
                    },
                )
            ]
        if event_type == "session.diff":
            return [event("file.diff", {"diff": data.get("diff", [])})]
        if event_type == "session.next.step.ended":
            events = [
                event(
                    "usage.updated",
                    {
                        "usage": {
                            "tokens": data.get("tokens", {}),
                            "cost": data.get("cost"),
                        }
                    },
                )
            ]
            if data.get("finish") not in {"tool-calls", "tool_calls"}:
                self._active_turns.pop(session_id, None)
                events.append(
                    event("turn.completed", {"status": data.get("finish", "completed")})
                )
            return events
        if event_type == "session.next.step.failed":
            self._active_turns.pop(session_id, None)
            return [
                event(
                    "error",
                    {
                        "code": "provider_error",
                        "message": str(data.get("error") or "OpenCode step failed"),
                        "retryable": False,
                    },
                ),
                event("turn.completed", {"status": "failed"}),
            ]
        return []

    @staticmethod
    def _content_text(content: Any) -> str:
        if isinstance(content, str):
            return content
        if not isinstance(content, list):
            return ""
        values: list[str] = []
        for item in content:
            if isinstance(item, str):
                values.append(item)
            elif isinstance(item, dict) and isinstance(item.get("text"), str):
                values.append(item["text"])
        return "".join(values)

"""REST discovery and WebSocket transport for the interactive Agent Gateway."""

from __future__ import annotations

import asyncio

from fastapi import (
    APIRouter,
    HTTPException,
    Query,
    Request,
    WebSocket,
    WebSocketDisconnect,
)
from pydantic import ValidationError

from core.services.agent_gateway import AgentGateway, AgentGatewayError
from core.services.agent_protocol import (
    AgentCommand,
    AgentError,
    AgentEvent,
    CreateAgentSessionRequest,
    ImportAgentSessionRequest,
    wire,
)
from core.session_history.session_finder import find_session_by_id

router = APIRouter(prefix="/api/agent", tags=["agent"])


def _gateway(source: Request | WebSocket) -> AgentGateway:
    gateway = getattr(source.app.state, "agent_gateway", None)
    if gateway is None:
        raise AgentGatewayError(
            "gateway_unavailable",
            "Agent Gateway is not running",
            status_code=503,
        )
    return gateway


def _http_error(exc: AgentGatewayError) -> HTTPException:
    return HTTPException(
        status_code=exc.status_code,
        detail={"code": exc.code, "message": exc.message},
    )


@router.get("/status")
async def get_agent_gateway_status(request: Request) -> dict:
    status = getattr(request.app.state, "agent_gateway_status", None)
    if not isinstance(status, dict):
        status = {
            "enabled": getattr(request.app.state, "agent_gateway", None) is not None,
            "legacyFallback": False,
            "providers": {},
        }
    return status


@router.get("/providers")
async def list_agent_providers(request: Request) -> list[dict]:
    try:
        return [wire(value) for value in await _gateway(request).providers()]
    except AgentGatewayError as exc:
        raise _http_error(exc) from exc


@router.get("/sessions")
async def list_agent_sessions(
    request: Request, limit: int = Query(100, ge=1, le=500)
) -> list[dict]:
    try:
        return [wire(value) for value in _gateway(request).list_sessions(limit)]
    except AgentGatewayError as exc:
        raise _http_error(exc) from exc


@router.post("/sessions", status_code=201)
async def create_agent_session(
    payload: CreateAgentSessionRequest, request: Request
) -> dict:
    try:
        session = await _gateway(request).create_session(
            provider=payload.provider,
            project_id=payload.project_id,
            model=payload.model,
            permission_mode=payload.permission_mode,
            title=payload.title,
        )
        return wire(session)
    except AgentGatewayError as exc:
        raise _http_error(exc) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/sessions/import", status_code=201)
async def import_agent_session(
    payload: ImportAgentSessionRequest, request: Request
) -> dict:
    native = await asyncio.to_thread(
        find_session_by_id,
        payload.provider_session_id,
        payload.provider,
        payload.project_id,
    )
    if native is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "native_session_not_found",
                "message": "Provider session was not found in local history",
            },
        )
    gateway = _gateway(request)
    existing = gateway.store.find_by_provider_session(
        payload.provider, payload.provider_session_id
    )
    try:
        session = await gateway.import_session(
            provider=payload.provider,
            provider_session_id=payload.provider_session_id,
            project_id=native.project_path,
            model=native.model or payload.model,
            permission_mode=payload.permission_mode,
            title=native.title or payload.title,
        )
        if existing is None:
            turn_number = 0
            for index, message in enumerate(native.messages):
                if message.role == "user":
                    turn_number += 1
                turn_id = f"history-{turn_number or 1}"
                event_type = (
                    "message.user" if message.role == "user" else "message.completed"
                )
                data_key = "text"
                await gateway.publish(
                    AgentEvent(
                        type=event_type,
                        session_id=session.id,
                        turn_id=turn_id,
                        item_id=f"history-message-{index}",
                        data={data_key: message.content},
                    )
                )
                for tool_index, tool in enumerate(message.tool_calls):
                    await gateway.publish(
                        AgentEvent(
                            type="tool.completed",
                            session_id=session.id,
                            turn_id=turn_id,
                            item_id=f"history-tool-{index}-{tool_index}",
                            data={
                                "tool": {
                                    "name": tool.name,
                                    "input": tool.args_preview,
                                    "result": tool.result_preview,
                                    "status": "completed",
                                }
                            },
                        )
                    )
        return wire(gateway.get_session(session.id))
    except AgentGatewayError as exc:
        raise _http_error(exc) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/sessions/{session_id}")
async def get_agent_session(session_id: str, request: Request) -> dict:
    try:
        return wire(_gateway(request).get_session(session_id))
    except AgentGatewayError as exc:
        raise _http_error(exc) from exc


@router.get("/sessions/{session_id}/history")
async def get_agent_session_history(
    session_id: str,
    request: Request,
    before_sequence: int | None = Query(None, alias="beforeSequence", ge=1),
    limit: int = Query(100, ge=1, le=200),
) -> dict:
    """Fetch one newest-first conversation page without opening a WebSocket."""
    try:
        gateway = _gateway(request)
        gateway.get_session(session_id)
        # Fetch one extra event so we can tell whether there's another page
        # without issuing a second query: if we get back more than `limit`,
        # the oldest one is dropped and just used as the "more" signal.
        fetched = await asyncio.to_thread(
            gateway.store.list_recent_events, session_id, before_sequence, limit + 1
        )
        has_more = len(fetched) > limit
        events = fetched[-limit:] if has_more else fetched
        return {
            "events": [wire(event) for event in events],
            "oldestSequence": events[0].sequence if events else None,
            "latestSequence": events[-1].sequence if events else 0,
            "hasMore": has_more,
        }
    except AgentGatewayError as exc:
        raise _http_error(exc) from exc


@router.post("/sessions/{session_id}/resume")
async def resume_agent_session(session_id: str, request: Request) -> dict:
    try:
        return wire(await _gateway(request).resume_session(session_id))
    except AgentGatewayError as exc:
        raise _http_error(exc) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.delete("/sessions/{session_id}")
async def delete_agent_session(session_id: str, request: Request) -> dict:
    try:
        _gateway(request).delete_session(session_id)
        return {"status": "deleted", "sessionId": session_id}
    except AgentGatewayError as exc:
        raise _http_error(exc) from exc


@router.websocket("/sessions/{session_id}/events")
async def agent_session_events(
    websocket: WebSocket,
    session_id: str,
    after_sequence: int = Query(0, alias="afterSequence", ge=0),
) -> None:
    await websocket.accept()
    try:
        gateway = _gateway(websocket)
        queue = gateway.subscribe(session_id, after_sequence)
    except AgentGatewayError as exc:
        await websocket.send_json(
            wire(
                AgentError(
                    session_id=session_id,
                    code=exc.code,
                    message=exc.message,
                )
            )
        )
        await websocket.close(code=4404 if exc.status_code == 404 else 1013)
        return

    send_lock = asyncio.Lock()

    async def send(payload: dict) -> None:
        async with send_lock:
            await websocket.send_json(payload)

    async def event_sender() -> None:
        while True:
            event = await queue.get()
            if event is None:
                await websocket.close(
                    code=1013, reason="Subscriber fell behind; reconnect to replay"
                )
                return
            await send(wire(event))

    sender = asyncio.create_task(event_sender(), name=f"agent-ws-{session_id}")
    try:
        while True:
            raw = await websocket.receive_json()
            try:
                command = AgentCommand.model_validate(raw)
                if command.session_id != session_id:
                    raise AgentGatewayError(
                        "session_mismatch",
                        "Command sessionId does not match WebSocket session",
                    )
                ack = await gateway.execute_command(command)
                await send(wire(ack))
            except ValidationError as exc:
                request_id = raw.get("requestId") if isinstance(raw, dict) else None
                await send(
                    wire(
                        AgentError(
                            request_id=request_id,
                            session_id=session_id,
                            code="invalid_command",
                            message=str(exc),
                        )
                    )
                )
            except AgentGatewayError as exc:
                await send(
                    wire(
                        AgentError(
                            request_id=(
                                raw.get("requestId") if isinstance(raw, dict) else None
                            ),
                            session_id=session_id,
                            code=exc.code,
                            message=exc.message,
                        )
                    )
                )
            except Exception as exc:
                await send(
                    wire(
                        AgentError(
                            request_id=(
                                raw.get("requestId") if isinstance(raw, dict) else None
                            ),
                            session_id=session_id,
                            code="provider_error",
                            message=str(exc),
                            retryable=True,
                        )
                    )
                )
    except WebSocketDisconnect:
        pass
    finally:
        sender.cancel()
        await asyncio.gather(sender, return_exceptions=True)
        gateway.unsubscribe(session_id, queue)

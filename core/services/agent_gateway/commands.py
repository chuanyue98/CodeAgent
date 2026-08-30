"""Command execution with in-flight deduplication and ack caching.

Extracted verbatim from the monolithic ``agent_gateway.py``. The ack cache
and in-flight future map still live on the gateway facade, since tests
inspect them there.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from core.services.agent_gateway.errors import AgentGatewayError
from core.services.agent_protocol import AgentAck, AgentCommand, TurnInput, wire

if TYPE_CHECKING:
    from core.services.agent_gateway.gateway import AgentGateway


async def execute_command(gateway: AgentGateway, command: AgentCommand) -> AgentAck:
    if command.session_id != command.session_id.strip():
        raise AgentGatewayError("invalid_command", "Invalid session id")
    if command.request_id != command.request_id.strip():
        raise AgentGatewayError("invalid_command", "Invalid request id")
    cached = gateway._acks[command.session_id].get(command.request_id)
    if cached:
        return cached
    # A client retry while the original command is still executing must
    # join the running command rather than run it a second time; the
    # completed-ack cache alone only deduplicates after the fact.
    key = (command.session_id, command.request_id)
    in_flight = gateway._commands_in_flight.get(key)
    if in_flight is not None:
        return await asyncio.shield(in_flight)
    future: asyncio.Future[AgentAck] = asyncio.get_running_loop().create_future()
    gateway._commands_in_flight[key] = future
    try:
        ack = await run_command(gateway, command)
    except BaseException as exc:
        if not future.done():
            future.set_exception(exc)
            # Mark retrieved so an unobserved failure doesn't warn at GC;
            # joined waiters still see the exception when they await.
            future.exception()
        raise
    finally:
        gateway._commands_in_flight.pop(key, None)
    if not future.done():
        future.set_result(ack)
    return ack


async def run_command(gateway: AgentGateway, command: AgentCommand) -> AgentAck:
    result: dict = {}
    if command.type == "session.resume":
        result = {"session": wire(await gateway.resume_session(command.session_id))}
    elif command.type == "turn.start":
        if not command.input:
            raise AgentGatewayError("invalid_command", "turn.start requires input")
        result = {
            "turnId": await gateway.start_turn(
                command.session_id, TurnInput(input=command.input)
            )
        }
    elif command.type == "turn.steer":
        if not command.turn_id or not command.input:
            raise AgentGatewayError(
                "invalid_command", "turn.steer requires turnId and input"
            )
        await gateway.steer_turn(
            command.session_id, command.turn_id, TurnInput(input=command.input)
        )
    elif command.type == "turn.cancel":
        if not command.turn_id:
            raise AgentGatewayError("invalid_command", "turn.cancel requires turnId")
        await gateway.cancel_turn(command.session_id, command.turn_id)
    elif command.type == "approval.respond":
        if not command.approval_id or command.decision is None:
            raise AgentGatewayError(
                "invalid_command",
                "approval.respond requires approvalId and decision",
            )
        await gateway.respond_to_approval(
            command.session_id, command.approval_id, command.decision
        )
    ack = AgentAck(request_id=command.request_id, command=command.type, result=result)
    cache = gateway._acks[command.session_id]
    cache[command.request_id] = ack
    cache.move_to_end(command.request_id)
    while len(cache) > gateway.ack_cache_limit:
        cache.popitem(last=False)
    return ack

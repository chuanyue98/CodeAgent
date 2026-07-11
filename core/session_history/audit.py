"""Flattens unified sessions into a time-sorted audit event list.

This is a message/tool-call timeline across engines and sessions — it is
NOT an approval or permission log. No approval/denial decision is recorded
anywhere in ``UnifiedMessage``/``ToolCallSummary``, because none of the four
engine parsers capture one. ``args_preview``/``result_preview`` on tool-call
events are truncated to 200 chars by the parsers at parse time and cannot be
recovered here without re-parsing the raw source file.
"""

from __future__ import annotations

from core.session_history.models import UnifiedSession


def build_audit_events(sessions: list[UnifiedSession]) -> list[dict]:
    """Flattens sessions into a time-sorted list of message/tool-call events.

    Args:
        sessions: Unified sessions to flatten, typically from
            ``find_all_sessions()``.

    Returns:
        list[dict]: One row per message plus one row per tool call within
        that message, sorted by ``timestamp`` descending (most recent
        first). Tool-call rows inherit their parent message's timestamp,
        role, and model, since ``ToolCallSummary`` carries no timestamp
        of its own.
    """
    events: list[dict] = []

    for session in sessions:
        engine = session.engine.value
        session_title = session.title or session.first_user_message

        for msg_idx, message in enumerate(session.messages):
            events.append(
                {
                    "event_id": f"{engine}:{session.session_id}:{msg_idx}",
                    "event_type": "message",
                    "engine": engine,
                    "project_path": session.project_path,
                    "session_id": session.session_id,
                    "session_title": session_title,
                    "timestamp": message.timestamp,
                    "role": message.role,
                    "model": message.model,
                    "content_preview": message.content,
                }
            )

            for tc_idx, tool_call in enumerate(message.tool_calls):
                events.append(
                    {
                        "event_id": f"{engine}:{session.session_id}:{msg_idx}:{tc_idx}",
                        "event_type": "tool_call",
                        "engine": engine,
                        "project_path": session.project_path,
                        "session_id": session.session_id,
                        "session_title": session_title,
                        "timestamp": message.timestamp,
                        "role": message.role,
                        "model": message.model,
                        "tool_name": tool_call.name,
                        "args_preview": tool_call.args_preview,
                        "result_preview": tool_call.result_preview,
                    }
                )

    events.sort(key=lambda e: e["timestamp"], reverse=True)
    return events

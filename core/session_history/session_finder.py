"""Session finder that aggregates sessions across all engines.

This is the main entry point for finding sessions by project path.
It calls each engine's ``find_*_sessions`` function and merges the results.
"""

from __future__ import annotations

from pathlib import Path

from core.constants import normalize_engine_name
from core.session_history.models import UnifiedMessage, UnifiedSession
from core.session_history.parsers import (
    find_antigravity_sessions,
    find_claude_sessions,
    find_codebuddy_sessions,
    find_codex_sessions,
    find_opencode_sessions,
)


def _message_key(message: UnifiedMessage) -> tuple[str, str, str, str]:
    return (message.role, message.timestamp, message.content, message.model)


def _merge_session_metadata(
    base: UnifiedSession, other: UnifiedSession
) -> UnifiedSession:
    """合并重复会话的元信息，保留子代理父子字段与子代理标题映射。"""
    merged_titles = {**other.subagent_titles, **base.subagent_titles}
    needs_update = (
        (not base.project_path and bool(other.project_path))
        or (not base.started_at and bool(other.started_at))
        or (not base.ended_at and bool(other.ended_at))
        or (not base.title and bool(other.title))
        or (not base.model and bool(other.model))
        or (not base.source_file and bool(other.source_file))
        or (not base.parent_session_id and bool(other.parent_session_id))
        or (not base.agent and bool(other.agent))
        or merged_titles != base.subagent_titles
    )
    if not needs_update:
        return base
    return UnifiedSession(
        session_id=base.session_id,
        engine=base.engine,
        project_path=base.project_path or other.project_path,
        started_at=base.started_at or other.started_at,
        ended_at=base.ended_at or other.ended_at,
        messages=base.messages,
        title=base.title or other.title,
        model=base.model or other.model,
        source_file=base.source_file or other.source_file,
        parent_session_id=base.parent_session_id or other.parent_session_id,
        agent=base.agent or other.agent,
        subagent_titles=merged_titles,
    )


def _merge_duplicate_sessions(
    current: UnifiedSession, candidate: UnifiedSession
) -> UnifiedSession:
    """Merges rollout files while avoiding duplicated conversation prefixes."""
    current_keys = {_message_key(message) for message in current.messages}
    candidate_keys = {_message_key(message) for message in candidate.messages}
    if candidate_keys.issubset(current_keys):
        return _merge_session_metadata(current, candidate)
    if current_keys.issubset(candidate_keys):
        return _merge_session_metadata(candidate, current)

    preferred = max(
        (current, candidate),
        key=lambda session: (
            session.ended_at,
            session.started_at,
            session.message_count,
            session.source_file,
        ),
    )
    other = candidate if preferred is current else current
    messages: list[UnifiedMessage] = []
    seen: set[tuple[str, str, str, str]] = set()
    for message in [*current.messages, *candidate.messages]:
        key = _message_key(message)
        if key not in seen:
            seen.add(key)
            messages.append(message)
    messages.sort(key=lambda message: message.timestamp or "9999")
    starts = [value for value in (current.started_at, candidate.started_at) if value]
    ends = [value for value in (current.ended_at, candidate.ended_at) if value]
    return UnifiedSession(
        session_id=preferred.session_id,
        engine=preferred.engine,
        project_path=preferred.project_path or other.project_path,
        started_at=min(starts) if starts else "",
        ended_at=max(ends) if ends else "",
        messages=messages,
        title=preferred.title or other.title,
        model=preferred.model or other.model,
        source_file=preferred.source_file or other.source_file,
        parent_session_id=preferred.parent_session_id or other.parent_session_id,
        agent=preferred.agent or other.agent,
        subagent_titles={**other.subagent_titles, **preferred.subagent_titles},
    )


def _deduplicate_sessions(
    sessions: list[UnifiedSession],
) -> list[UnifiedSession]:
    """Collapses provider files that represent the same logical session.

    Codex can write a new rollout file when a session is resumed while keeping
    the original session ID. Rollout files can overlap or contain only a
    continuation, so merge their messages before presenting one session.
    """
    by_identity: dict[tuple[str, str], UnifiedSession] = {}
    for session in sessions:
        identity = (session.engine.value, session.session_id)
        current = by_identity.get(identity)
        by_identity[identity] = (
            session if current is None else _merge_duplicate_sessions(current, session)
        )
    return list(by_identity.values())


def find_all_sessions(
    project_path: str | None = None,
    home: Path | None = None,
    engine: str | None = None,
) -> list[UnifiedSession]:
    """Finds sessions across all AI engines for a given project path.

    Args:
        project_path: The project directory to search for. If None,
            sessions from every project are returned unfiltered.
        home: Optional home directory override.
        engine: Optional filter — only return sessions from this engine
            (e.g. "claude", "codex", "opencode", "codebuddy").

    Returns:
        list[UnifiedSession]: All sessions found, sorted by start time
        descending (most recent first).
    """
    normalized_engine = normalize_engine_name(engine) if engine is not None else None
    all_sessions: list[UnifiedSession] = []

    if normalized_engine is None or normalized_engine == "claude":
        all_sessions.extend(find_claude_sessions(project_path, home))

    if normalized_engine is None or normalized_engine == "codex":
        all_sessions.extend(find_codex_sessions(project_path, home))

    if normalized_engine is None or normalized_engine == "opencode":
        all_sessions.extend(find_opencode_sessions(project_path, home))

    if normalized_engine is None or normalized_engine == "codebuddy":
        all_sessions.extend(find_codebuddy_sessions(project_path, home))

    if normalized_engine is None or normalized_engine == "antigravity":
        all_sessions.extend(find_antigravity_sessions(project_path, home))

    # A provider may expose multiple backing files for one logical session.
    all_sessions = _deduplicate_sessions(all_sessions)

    # Sort by start time descending
    all_sessions.sort(key=lambda s: s.started_at, reverse=True)
    return all_sessions


def find_session_by_id(
    session_id: str,
    engine: str,
    project_path: str | None,
    home: Path | None = None,
) -> UnifiedSession | None:
    """Finds a specific session by its ID and engine.

    Args:
        session_id: The session ID to find.
        engine: The engine type ("claude", "codex", "opencode", "codebuddy").
        project_path: The project path to search within.
        home: Optional home directory override.

    Returns:
        UnifiedSession if found, None otherwise.
    """
    engine = normalize_engine_name(engine)
    sessions = find_all_sessions(project_path, home, engine=engine)
    for session in sessions:
        if session.session_id == session_id:
            return session
    return None

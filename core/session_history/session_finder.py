"""Session finder that aggregates sessions across all engines.

This is the main entry point for finding sessions by project path.
It calls each engine's ``find_*_sessions`` function and merges the results.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from core.session_history.models import UnifiedSession
from core.session_history.parsers import (
    find_claude_sessions,
    find_codex_sessions,
    find_gemini_sessions,
    find_opencode_sessions,
)


def find_all_sessions(
    project_path: Optional[str] = None,
    home: Optional[Path] = None,
    engine: Optional[str] = None,
) -> list[UnifiedSession]:
    """Finds sessions across all AI engines for a given project path.

    Args:
        project_path: The project directory to search for. If None,
            sessions from every project are returned unfiltered.
        home: Optional home directory override.
        engine: Optional filter — only return sessions from this engine
            (e.g. "claude", "codex", "gemini", "opencode").

    Returns:
        list[UnifiedSession]: All sessions found, sorted by start time
        descending (most recent first).
    """
    all_sessions: list[UnifiedSession] = []

    if engine is None or engine == "claude":
        all_sessions.extend(find_claude_sessions(project_path, home))

    if engine is None or engine == "codex":
        all_sessions.extend(find_codex_sessions(project_path, home))

    if engine is None or engine == "gemini":
        all_sessions.extend(find_gemini_sessions(project_path, home))

    if engine is None or engine == "opencode":
        all_sessions.extend(find_opencode_sessions(project_path, home))

    # Sort by start time descending
    all_sessions.sort(key=lambda s: s.started_at, reverse=True)
    return all_sessions


def find_session_by_id(
    session_id: str,
    engine: str,
    project_path: str,
    home: Optional[Path] = None,
) -> Optional[UnifiedSession]:
    """Finds a specific session by its ID and engine.

    Args:
        session_id: The session ID to find.
        engine: The engine type ("claude", "codex", "gemini", "opencode").
        project_path: The project path to search within.
        home: Optional home directory override.

    Returns:
        UnifiedSession if found, None otherwise.
    """
    sessions = find_all_sessions(project_path, home, engine=engine)
    for session in sessions:
        if session.session_id == session_id:
            return session
    return None


def get_session_summaries(
    project_path: Optional[str] = None,
    home: Optional[Path] = None,
    engine: Optional[str] = None,
) -> list[dict]:
    """Returns lightweight session summaries for list views.

    This is a convenience wrapper that calls ``find_all_sessions`` and
    converts each result to a summary dict (without full messages).

    Args:
        project_path: The project directory to search for. If None,
            sessions from every project are returned unfiltered.
        home: Optional home directory override.
        engine: Optional engine filter.

    Returns:
        list[dict]: List of session summary dicts.
    """
    sessions = find_all_sessions(project_path, home, engine)
    return [s.to_summary_dict() for s in sessions]

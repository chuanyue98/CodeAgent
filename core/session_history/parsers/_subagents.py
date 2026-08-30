"""Shared handling for subagent runs across the file-backed engines.

Claude Code and CodeBuddy both write a subagent's transcript to
``<session_id>/subagents/agent-<id>.jsonl`` and both open that transcript with
the entire prompt the agent was handed. Their launchers, though, each recorded
a one-line description of the run -- which is what a list wants to show.
"""

from __future__ import annotations

from pathlib import Path

from core.session_history.models import UnifiedSession
from core.utils.long_paths import list_files


def subagent_files(session_dir: Path) -> list[tuple[Path, str]]:
    """``(transcript, owning session id)`` for every subagent run below *session_dir*.

    A subagent that spawns its own runs nests them one level further, so the
    owner is the nearest enclosing ``agent-<id>`` directory when there is one.
    """
    found: list[tuple[Path, str]] = []
    root = session_dir / "subagents"
    for transcript in list_files(root, ".jsonl", recursive=True):
        owner = transcript.parent.name
        found.append(
            (transcript, owner if owner.startswith("agent-") else session_dir.name)
        )
    return found


def title_subagent_runs(sessions: list[UnifiedSession]) -> None:
    """Names each subagent run the way its launcher described it.

    Four reviews dispatched from one session otherwise all read as the same
    wall of prompt text. Runs whose launch was not recorded keep their prompt.
    """
    by_id = {session.session_id: session for session in sessions}
    for session in sessions:
        if not session.parent_session_id or session.title:
            continue
        parent = by_id.get(session.parent_session_id)
        if parent is None:
            continue
        title = parent.subagent_titles.get(
            session.session_id.removeprefix("agent-")
        ) or parent.subagent_titles.get(session.session_id)
        if title:
            session.title = title

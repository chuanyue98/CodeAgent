"""The argv that hands an existing session back to its own engine CLI.

Every engine can resume a conversation it already has on disk, and the four
spellings differ only in flag shape. This lives outside any router because two
of them need it: the history endpoints, which answer "resume this session",
and the browser PTY, which is what actually runs the result.

No CodeAgent prompt/skill/plugin injection happens on this path -- the
conversation is already materialized in the engine's native storage, so the
engine is invoked directly rather than through ``ca_launcher.py``.
"""

from __future__ import annotations

import re
from pathlib import Path

#: A session id ends up as one element of an argv list. Nothing here reaches a
#: shell, so there is no quoting hazard, but an id beginning with ``-`` would
#: be read by the engine CLI as a flag rather than as an id. Engines issue
#: UUIDs and ``ses_``-style ids, all of which satisfy this.
_SAFE_SESSION_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


def is_safe_session_id(session_id: str) -> bool:
    """True when *session_id* is safe to place in an argv list."""
    return bool(session_id) and bool(_SAFE_SESSION_ID.match(session_id))


def resume_command(engine: str, session_id: str, project: Path) -> list[str]:
    """Builds the engine CLI argv that resumes *session_id*.

    Args:
        engine: Engine that owns the session.
        session_id: The session id in that engine's own format.
        project: Working directory the session belongs to. Only OpenCode
            takes it as an argument; for the others the caller sets the
            process's cwd.

    Returns:
        list[str]: argv to spawn.

    Raises:
        ValueError: On an unknown engine, or a session id that could be
            mistaken for a flag.
    """
    if not is_safe_session_id(session_id):
        raise ValueError(f"Unsafe session id: {session_id!r}")
    if engine == "opencode":
        return ["opencode", str(project), "-s", session_id]
    if engine == "claude":
        return ["claude", "--resume", session_id]
    if engine == "codex":
        return ["codex", "resume", session_id]
    if engine == "codebuddy":
        return ["codebuddy", "--resume", session_id]
    if engine == "antigravity":
        return ["agy", "--conversation", session_id]
    raise ValueError(f"Unknown engine: {engine}")

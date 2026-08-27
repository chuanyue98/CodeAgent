"""Turns what a user can reasonably type into one concrete session.

``ca history`` prints a numbered list, so the number it printed is the
selector people reach for first. Accepting only the raw session id -- which
is what the underlying finders key on -- forced them to copy a UUID out of a
list that had just offered them ``[1]``.
"""

from __future__ import annotations

from core.session_history.models import UnifiedSession
from core.session_history.session_finder import find_all_sessions


class SessionSelectorError(Exception):
    """Raised when a selector matches no session.

    Carries the i18n key and format arguments rather than a rendered string:
    the callers are CLI commands that print in the user's language.
    """

    def __init__(self, message_key: str, **fields: object) -> None:
        super().__init__(message_key)
        self.message_key = message_key
        self.fields = fields


def resolve_session(
    selector: str | None,
    project_path: str,
    *,
    engine: str | None = None,
) -> UnifiedSession:
    """Resolves *selector* against the sessions of *project_path*.

    Args:
        selector: A 1-based index into the same ordering ``ca history``
            prints, a session id, or None for the most recent session.
        project_path: Project whose sessions are searched.
        engine: Optional engine filter, matching ``ca history --engine``.

    Returns:
        UnifiedSession: The selected session.

    Raises:
        SessionSelectorError: When the project has no sessions, or the
            selector matches none of them.
    """
    sessions = find_all_sessions(project_path, engine=engine)
    if not sessions:
        raise SessionSelectorError("select.no_sessions", path=project_path)

    if selector is None:
        return sessions[0]

    # A bare integer is the printed index. Session ids are UUIDs and
    # ``ses_``-style strings, so none of them parse as one.
    try:
        index = int(selector)
    except ValueError:
        pass
    else:
        if not 1 <= index <= len(sessions):
            raise SessionSelectorError(
                "select.index_out_of_range", index=index, count=len(sessions)
            )
        return sessions[index - 1]

    for session in sessions:
        if session.session_id == selector:
            return session
    raise SessionSelectorError("select.not_found", selector=selector)

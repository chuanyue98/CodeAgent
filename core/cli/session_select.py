"""Turns what a user can reasonably type into one concrete session.

``ca history`` prints a numbered list, so the number it printed is the
selector people reach for first. Accepting only the raw session id -- which
is what the underlying finders key on -- forced them to copy a UUID out of a
list that had just offered them ``[1]``.
"""

from __future__ import annotations

from core.session_history import repository
from core.session_history.models import UnifiedSession


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
    # 与 ``ca history`` 同一套排序：先拿摘要选，再按需取完整会话，避免为选一个
    # 会话就把整个项目的消息都解析一遍。
    summaries = repository.list_summaries(
        project=project_path, engine=engine, include_subagents=True, limit=100000
    )
    if not summaries:
        raise SessionSelectorError("select.no_sessions", path=project_path)

    chosen: dict | None = None
    if selector is None:
        chosen = summaries[0]
    else:
        # A bare integer is the printed index. Session ids are UUIDs and
        # ``ses_``-style strings, so none of them parse as one.
        try:
            index = int(selector)
        except ValueError:
            pass
        else:
            if not 1 <= index <= len(summaries):
                raise SessionSelectorError(
                    "select.index_out_of_range", index=index, count=len(summaries)
                )
            chosen = summaries[index - 1]

    if chosen is None:
        for summary in summaries:
            if summary["session_id"] == selector:
                chosen = summary
                break
    if chosen is None:
        raise SessionSelectorError("select.not_found", selector=selector)

    session = repository.get_full(
        chosen["engine"], chosen["session_id"], project_path
    )
    if session is None:
        raise SessionSelectorError("select.not_found", selector=selector)
    return session

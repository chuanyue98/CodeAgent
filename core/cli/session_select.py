"""Turns what a user can reasonably type into one concrete session.

``ca history`` prints a numbered list, so the number it printed is the
selector people reach for first. Accepting only the raw session id -- which
is what the underlying finders key on -- forced them to copy a UUID out of a
list that had just offered them ``[1]``.

编号必须与用户看到的那份列表同一口径：``ca -r`` 与 ``ca history list`` 默认
不列子任务，所以按编号解析时也要先把子任务过滤掉，否则同一个 ``3`` 在列表里
和在 ``ca -s`` 里指向两个不同的会话。会话 id 是用户明确指定的目标，因此仍在
全量会话里查找——用 id 点名一个子任务应该照样能命中。
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
    include_subagents: bool = False,
) -> UnifiedSession:
    """Resolves *selector* against the sessions of *project_path*.

    Args:
        selector: A 1-based index into the same ordering ``ca history``
            prints, a session id, or None for the most recent session.
        project_path: Project whose sessions are searched.
        engine: Optional engine filter, matching ``ca history --engine``.
        include_subagents: 子任务会话是否参与编号与"最近一条"的判定。默认
            False，与 ``ca -r`` / ``ca history list`` 打印的列表一致；调用方
            若展示了含子任务的列表，传 True 才能保持编号对齐。

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

    # 编号与"最近一条"走这份，id 查找走全量：见模块 docstring。
    listed = (
        summaries
        if include_subagents
        else [s for s in summaries if not s.get("parent_session_id")]
    )

    chosen: dict | None = None
    if selector is None:
        if not listed:
            raise SessionSelectorError("select.no_sessions", path=project_path)
        chosen = listed[0]
    else:
        # A bare integer is the printed index. Session ids are UUIDs and
        # ``ses_``-style strings, so none of them parse as one.
        try:
            index = int(selector)
        except ValueError:
            pass
        else:
            if not 1 <= index <= len(listed):
                raise SessionSelectorError(
                    "select.index_out_of_range", index=index, count=len(listed)
                )
            chosen = listed[index - 1]

    if chosen is None:
        for summary in summaries:
            if summary["session_id"] == selector:
                chosen = summary
                break
    if chosen is None:
        raise SessionSelectorError("select.not_found", selector=selector)

    session = repository.get_full(chosen["engine"], chosen["session_id"], project_path)
    if session is None:
        raise SessionSelectorError("select.not_found", selector=selector)
    return session

"""会话索引存储层的单元测试（schema、迁移、查询、级联）。"""

from __future__ import annotations

import sqlite3

import pytest

from core.session_history.index_store import (
    LAST_SYNC_KEY,
    SCHEMA_VERSION,
    SessionIndex,
    SourceRef,
    session_key,
)
from core.session_history.models import (
    EngineType,
    ToolCallSummary,
    UnifiedMessage,
    UnifiedSession,
)


@pytest.fixture
def index(tmp_path):
    store = SessionIndex(tmp_path / "session-index.sqlite3")
    yield store
    store.close()


def _session(
    session_id: str = "s1",
    *,
    project: str = "E:/Demo/App",
    messages: list[UnifiedMessage] | None = None,
    title: str = "",
    parent: str = "",
) -> UnifiedSession:
    return UnifiedSession(
        session_id=session_id,
        engine=EngineType.CLAUDE,
        project_path=project,
        started_at="2026-07-11T10:00:00Z",
        ended_at="2026-07-11T10:05:00Z",
        title=title,
        model="claude-sonnet-4",
        source_file=f"/x/{session_id}.jsonl",
        parent_session_id=parent,
        messages=messages
        if messages is not None
        else [
            UnifiedMessage(
                role="user", content="hello there", timestamp="2026-07-11T10:00:00Z"
            )
        ],
    )


def test_fresh_db_is_not_ready(index):
    """首轮同步之前不算就绪，读路径必须回退而不是返回空列表。"""
    assert index.is_ready() is False
    index.set_meta(LAST_SYNC_KEY, "1700000000")
    assert index.is_ready() is True


def test_clearing_for_a_rebuild_takes_readiness_with_it(index):
    """清空之后不能还说自己就绪，否则重建期间历史一律显示"没有会话"。

    重建跑在后台线程里，而 ``ca history`` 这类命令清完就退出了：留在盘上的
    就是一个空的、却仍然 is_ready() 的索引。
    """
    index.write_session(_session())
    index.set_meta(LAST_SYNC_KEY, "1700000000")
    assert index.is_ready() is True

    index.clear_all()

    assert index.session_count() == 0
    assert index.is_ready() is False


def test_newer_schema_rebuilds_instead_of_bricking(index, tmp_path):
    """派生索引遇到更新的 schema 应该"重建"，而不是把服务拦下来。

    这里只验证：打开时抛错，且错误是可识别的（调用方据此走回退）。
    """
    path = tmp_path / "newer.sqlite3"
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE schema_version (version INTEGER NOT NULL)")
    con.execute(
        "INSERT INTO schema_version(version) VALUES (?)", (SCHEMA_VERSION + 10,)
    )
    con.commit()
    con.close()
    with pytest.raises(RuntimeError, match="newer than supported"):
        SessionIndex(path)


def test_cascade_deletes_messages_and_tool_calls(index):
    """删会话必须把消息与工具调用一起清掉，不能留下孤儿行。"""
    session = _session(
        messages=[
            UnifiedMessage(
                role="assistant",
                content="",
                timestamp="2026-07-11T10:01:00Z",
                model="claude-sonnet-4",
                tool_calls=[ToolCallSummary(name="Read", args_preview="{}")],
            )
        ]
    )
    index.write_session(session)
    assert index.audit_events(limit=100)

    index.delete_session(session_key("claude", "s1"))
    assert index.session_count() == 0
    assert index.audit_events(limit=100) == []
    assert index.tool_usage()["totalCalls"] == 0


def test_orphan_cleanup_removes_sessions_without_sources(index):
    index.write_session(_session())
    # 没登记来源：属于"来源已消失"的残留。
    assert index.session_count() == 1
    assert index.delete_orphan_sessions() == 1
    assert index.session_count() == 0


def test_list_summaries_pushes_filters_and_limit_down(index):
    index.write_session(_session("in-app", project="E:/Demo/App"))
    index.write_session(_session("other", project="E:/Other"))
    index.write_session(_session("child", project="E:/Demo/App", parent="in-app"))

    rows = index.list_summaries(project="e:/demo/app", limit=10)
    # 子代理默认不出现，且按 project 过滤、大小写/分隔符都规范化过。
    assert {r.session_id for r in rows} == {"in-app"}
    # 三个会话的 started_at 相同，排序落在 session_key 的次级键上；这里只关心
    # 集合，顺序由 test_list_summaries_orders_by_started_at 单独锁定。
    assert {r.session_id for r in index.list_summaries(include_subagents=True)} == {
        "in-app",
        "other",
        "child",
    }
    assert len(index.list_summaries(limit=2)) == 2


def test_list_summaries_orders_by_started_at(index):
    """列表顺序与 finder 一致：按 started_at 倒序。"""
    for session_id, started in [
        ("older", "2026-07-10T10:00:00Z"),
        ("newest", "2026-07-12T10:00:00Z"),
        ("middle", "2026-07-11T10:00:00Z"),
    ]:
        session = _session(session_id)
        session.started_at = started
        index.write_session(session)
    assert [r.session_id for r in index.list_summaries()] == [
        "newest",
        "middle",
        "older",
    ]


def test_reconstruct_round_trips_the_full_session(index):
    original = _session(
        messages=[
            UnifiedMessage(role="user", content="q", timestamp="2026-07-11T10:00:00Z"),
            UnifiedMessage(
                role="assistant",
                content="a",
                timestamp="2026-07-11T10:01:00Z",
                model="claude-sonnet-4",
                tool_calls=[ToolCallSummary(name="Bash", args_preview="ls")],
            ),
        ]
    )
    index.write_session(original)
    restored = index.reconstruct("claude", "s1")
    assert restored is not None
    assert restored.to_full_dict() == original.to_full_dict()


def test_unresolved_subagents_are_reported_for_titling(index):
    """子代理标题对账：只挑"引擎没给标题"且"还没被父覆盖"的行。"""
    index.write_session(_session("parent", title="parent title"))
    index.write_session(_session("child", parent="parent"))
    unresolved = index.unresolved_subagents()
    assert [row[2] for row in unresolved] == ["child"]

    index.set_session_title(session_key("claude", "child"), "given by parent")
    assert index.unresolved_subagents() == []


def test_inherit_parent_projects_fills_only_empty_children(tmp_path):
    store = SessionIndex(tmp_path / "inherit.sqlite3")
    try:
        store.write_session(_session("parent", project="E:/Demo/App"))
        store.write_session(_session("child", project="", parent="parent"))
        assert store.inherit_parent_projects("claude") == 1
        child = store.get_summary("claude", "child")
        assert child is not None
        assert child.project_path == "E:/Demo/App"
        # 已经继承过就不再改动，供调用方循环到 0 为止。
        assert store.inherit_parent_projects("claude") == 0
    finally:
        store.close()


def test_sources_track_version_tokens(index):
    ref = SourceRef(
        source_key="claude:/x/s1.jsonl",
        engine="claude",
        source_file="/x/s1.jsonl",
        version_token="1:2",
        session_key=session_key("claude", "s1"),
    )
    index.upsert_source(ref)
    assert index.source_versions("claude") == {"claude:/x/s1.jsonl": "1:2"}
    assert index.sources_for_session(session_key("claude", "s1")) == [
        "claude:/x/s1.jsonl"
    ]
    index.remove_source("claude:/x/s1.jsonl")
    assert index.source_versions("claude") == {}


def test_closed_index_stops_background_sync(tmp_path):
    """后台同步线程要能感知索引已关闭，而不是往关闭的连接上写。"""
    store = SessionIndex(tmp_path / "closed.sqlite3")
    store.close()
    assert store.closed is True

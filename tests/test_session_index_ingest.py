"""增量摄取与"索引 vs finder"对拍。

重点是增量正确性：没变的文件不重解析、变了的要重解析、删掉的要从索引里消失。
最后一条对拍是回退期的护栏——只要索引还在并行运行，两条路径产出的结果就必须
一致。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import core.session_history.index_ingest as ingest
from core.session_history.audit import build_audit_events
from core.session_history.index_ingest import SessionIndexer
from core.session_history.index_store import SessionIndex
from core.session_history.session_finder import find_all_sessions
from core.session_history.sources import ENGINE_PARSERS


def _row(
    session_id: str,
    text: str,
    *,
    timestamp: str = "2026-07-11T10:00:00.000Z",
    role: str = "user",
) -> str:
    return json.dumps(
        {
            "type": role,
            "sessionId": session_id,
            "cwd": "E:/demo/app",
            "timestamp": timestamp,
            "message": {"role": role, "content": text},
        }
    )


def _write_session(home: Path, session_id: str, *rows: str) -> Path:
    session_dir = home / ".claude" / "projects" / "E--demo-app"
    session_dir.mkdir(parents=True, exist_ok=True)
    path = session_dir / f"{session_id}.jsonl"
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    return path


@pytest.fixture
def home_path(tmp_path) -> Path:
    directory = tmp_path / "home"
    directory.mkdir()
    return directory


@pytest.fixture
def store_and_indexer(tmp_path, home_path):
    store = SessionIndex(tmp_path / "session-index.sqlite3")
    yield store, SessionIndexer(store, home=home_path)
    store.close()


@pytest.fixture
def call_counter(monkeypatch):
    """记录 claude 解析器的调用次数，用来断言"没变就不重解析"。"""
    real_parser = ENGINE_PARSERS["claude"][1]
    calls: list[Path] = []

    def counting(path: Path):
        calls.append(path)
        return real_parser(path)

    monkeypatch.setitem(
        ingest.ENGINE_PARSERS, "claude", (ENGINE_PARSERS["claude"][0], counting)
    )
    return calls


def test_first_sync_indexes_every_session(store_and_indexer, home_path):
    store, indexer = store_and_indexer
    _write_session(home_path, "s1", _row("s1", "hello"))
    indexer.sync()

    assert store.session_count() == 1
    summary = store.get_summary("claude", "s1")
    assert summary is not None
    assert summary.title == "hello"
    assert store.is_ready() is True


def test_unchanged_file_is_not_reparsed(store_and_indexer, home_path, call_counter):
    store, indexer = store_and_indexer
    _write_session(home_path, "s1", _row("s1", "hello"))
    indexer.sync()
    assert len(call_counter) == 1

    indexer.sync()
    assert len(call_counter) == 1, "未变更的文件被重新解析了"
    assert store.session_count() == 1


def test_changed_file_is_reparsed(store_and_indexer, home_path, call_counter):
    store, indexer = store_and_indexer
    path = _write_session(home_path, "s1", _row("s1", "hello"))
    indexer.sync()
    assert store.get_summary("claude", "s1").message_count == 1

    path.write_text(
        _row("s1", "hello")
        + "\n"
        + _row("s1", "again", timestamp="2026-07-11T10:01:00.000Z")
        + "\n",
        encoding="utf-8",
    )
    indexer.sync()

    assert len(call_counter) == 2
    assert store.get_summary("claude", "s1").message_count == 2


def test_deleted_file_drops_the_session(store_and_indexer, home_path):
    store, indexer = store_and_indexer
    path = _write_session(home_path, "s1", _row("s1", "hello"))
    indexer.sync()
    assert store.session_count() == 1

    path.unlink()
    indexer.sync()
    assert store.session_count() == 0
    assert store.audit_events(limit=100) == []


def test_parser_fingerprint_change_forces_a_rebuild(
    store_and_indexer, home_path, call_counter
):
    store, indexer = store_and_indexer
    _write_session(home_path, "s1", _row("s1", "hello"))
    indexer.sync()
    assert len(call_counter) == 1

    # 解析器源码变了：旧副本不能再信，必须整轮重建。
    store.set_meta("parser_fingerprint", "some-other-fingerprint")
    indexer.sync()
    assert len(call_counter) == 2


def test_empty_sources_are_remembered(store_and_indexer, home_path, call_counter):
    """解析不出会话的文件也要登记，否则每次同步都会重解析一遍空文件。"""
    store, indexer = store_and_indexer
    _write_session(home_path, "empty", json.dumps({"type": "summary"}))
    indexer.sync()
    assert len(call_counter) == 1
    assert store.session_count() == 0

    indexer.sync()
    assert len(call_counter) == 1, "空来源没被记住，每次都在重解析"


def test_subagent_titles_come_from_the_parent(store_and_indexer, home_path):
    """子代理的标题来自父会话记录的启动描述（跨文件依赖）。"""
    store, indexer = store_and_indexer
    launch = json.dumps(
        {
            "type": "assistant",
            "sessionId": "parent",
            "timestamp": "2026-07-11T10:00:00.000Z",
            "message": {"role": "assistant", "content": "dispatching"},
            "toolUseResult": {"agentId": "abc123", "description": "审查 PR"},
        }
    )
    _write_session(home_path, "parent", _row("parent", "go"), launch)

    child_dir = (
        home_path / ".claude" / "projects" / "E--demo-app" / "parent" / "subagents"
    )
    child_dir.mkdir(parents=True, exist_ok=True)
    (child_dir / "agent-abc123.jsonl").write_text(
        _row("agent-abc123", "整个 prompt 都在这里") + "\n", encoding="utf-8"
    )

    indexer.sync()

    child = store.get_summary("claude", "agent-abc123")
    assert child is not None
    assert child.parent_session_id == "parent"
    # 不是子代理自己那一长串 prompt，而是父记录的一行描述。
    assert child.title == "审查 PR"


def test_ingest_never_populates_the_resident_parse_cache(store_and_indexer, home_path):
    """摄取绝不能经过 parse_cache，否则"全量常驻内存"会悄悄回来。

    这是本轮改造的命门，而失效方式很隐蔽（解析器被重新包上装饰器即可），所以
    用一条断言钉住。
    """
    from core.session_history import parse_cache

    store, indexer = store_and_indexer
    _write_session(home_path, "s1", _row("s1", "hello"))
    parse_cache.clear_parse_cache()
    indexer.sync()
    assert parse_cache.parse_cache_size() == 0
    assert store.session_count() == 1


def test_index_matches_the_finder(store_and_indexer, home_path):
    """对拍护栏：索引与 find_all_sessions 必须给出同样的结果。"""
    store, indexer = store_and_indexer
    _write_session(home_path, "s1", _row("s1", "first question"))
    _write_session(
        home_path,
        "s2",
        _row("s2", "second question", timestamp="2026-07-11T11:00:00.000Z"),
        _row(
            "s2", "the answer", timestamp="2026-07-11T11:01:00.000Z", role="assistant"
        ),
    )
    indexer.sync()

    found = {
        (s.engine.value, s.session_id): s for s in find_all_sessions(home=home_path)
    }
    rows = {
        (r.engine, r.session_id): r
        for r in store.list_summaries(include_subagents=True, limit=1000)
    }
    assert set(rows) == set(found)
    for key, session in found.items():
        row = rows[key]
        assert row.title == (session.title or session.first_user_message)
        assert row.message_count == len(session.messages)
        assert row.started_at == session.started_at
        assert row.project_path == session.project_path

    expected_events = {e["event_id"] for e in build_audit_events(list(found.values()))}
    actual_events = {e["event_id"] for e in store.audit_events(limit=5000)}
    assert actual_events == expected_events


def test_audit_limit_is_pushed_down(store_and_indexer, home_path):
    """limit 必须在 SQL 里生效，而不是先摊平成全部事件再切片。"""
    store, indexer = store_and_indexer
    rows = [
        _row("s1", f"message {i}", timestamp=f"2026-07-11T10:{i:02d}:00.000Z")
        for i in range(30)
    ]
    _write_session(home_path, "s1", *rows)
    indexer.sync()

    assert len(store.audit_events(limit=5)) == 5
    newest = store.audit_events(limit=1)[0]
    assert newest["timestamp"] == "2026-07-11T10:29:00.000Z"


def test_engine_filter_and_project_filter_are_pushed_down(store_and_indexer, home_path):
    store, indexer = store_and_indexer
    _write_session(
        home_path, "s1", _row("s1", "hello", timestamp="2026-07-11T10:00:00.000Z")
    )
    indexer.sync()

    assert store.audit_events(engine="claude", limit=100)
    assert store.audit_events(engine="codex", limit=100) == []
    assert store.audit_events(project="e:/demo/app", limit=100)
    assert store.audit_events(project="e:/elsewhere", limit=100) == []


def test_since_and_until_are_pushed_down(store_and_indexer, home_path):
    from core.session_history.index_store import to_epoch

    store, indexer = store_and_indexer
    _write_session(
        home_path,
        "s1",
        _row("s1", "early", timestamp="2026-07-11T10:00:00.000Z"),
        _row("s1", "late", timestamp="2026-07-11T12:00:00.000Z"),
    )
    indexer.sync()

    boundary = to_epoch("2026-07-11T11:00:00.000Z")
    assert boundary is not None
    since = store.audit_events(since=boundary, limit=100)
    assert {e["timestamp"] for e in since} == {"2026-07-11T12:00:00.000Z"}
    until = store.audit_events(until=boundary, limit=100)
    assert {e["timestamp"] for e in until} == {"2026-07-11T10:00:00.000Z"}


def test_antigravity_subagent_lineage_ingest(store_and_indexer, home_path):
    """Antigravity 子代理在索引摄取后能正确归属父会话并隐藏在顶层列表。"""
    store, indexer = store_and_indexer
    cli_dir = home_path / ".gemini" / "antigravity-cli"

    # Parent
    p_log = cli_dir / "brain" / "parent-1" / ".system_generated" / "logs"
    p_log.mkdir(parents=True, exist_ok=True)
    p_lines = [
        json.dumps(
            {
                "step_index": 1,
                "source": "USER_EXPLICIT",
                "type": "USER_INPUT",
                "status": "DONE",
                "created_at": "2026-09-12T01:00:00Z",
                "content": "<USER_REQUEST>\n主任务执行\n/workspace/demo -> demo\n</USER_REQUEST>",
            }
        ),
        json.dumps(
            {
                "step_index": 2,
                "source": "MODEL",
                "type": "PLANNER_RESPONSE",
                "status": "DONE",
                "created_at": "2026-09-12T01:01:00Z",
                "tool_calls": [
                    {
                        "name": "invoke_subagent",
                        "args": {
                            "Subagents": [
                                {
                                    "Model": "flash",
                                    "Role": "Task 1 Reviewer",
                                    "Prompt": "Review task 1",
                                }
                            ],
                        },
                    }
                ],
            }
        ),
        json.dumps(
            {
                "step_index": 3,
                "source": "MODEL",
                "type": "INVOKE_SUBAGENT",
                "status": "DONE",
                "created_at": "2026-09-12T01:01:05Z",
                "content": 'Created the following subagents:\n{\n  "conversationId": "child-1"\n}',
            }
        ),
    ]
    (p_log / "transcript.jsonl").write_text("\n".join(p_lines) + "\n", encoding="utf-8")

    # Child
    c_log = cli_dir / "brain" / "child-1" / ".system_generated" / "logs"
    c_log.mkdir(parents=True, exist_ok=True)
    c_lines = [
        json.dumps(
            {
                "step_index": 1,
                "source": "USER_EXPLICIT",
                "type": "USER_INPUT",
                "status": "DONE",
                "created_at": "2026-09-12T01:01:10Z",
                "content": "<USER_REQUEST>Review task 1</USER_REQUEST>",
            }
        ),
        json.dumps(
            {
                "step_index": 2,
                "source": "MODEL",
                "type": "PLANNER_RESPONSE",
                "status": "DONE",
                "created_at": "2026-09-12T01:02:00Z",
                "content": "Done review.",
                "tool_calls": [],
            }
        ),
    ]
    (c_log / "transcript.jsonl").write_text("\n".join(c_lines) + "\n", encoding="utf-8")

    indexer.sync()

    # Without subagents: only parent
    top_summaries = store.list_summaries(include_subagents=False)
    assert len(top_summaries) == 1
    assert top_summaries[0].session_id == "parent-1"

    # With subagents: both parent and child
    all_summaries = store.list_summaries(include_subagents=True)
    assert len(all_summaries) == 2
    by_id = {s.session_id: s for s in all_summaries}

    c = by_id["child-1"]
    assert c.parent_session_id == "parent-1"
    assert c.agent == "Task 1 Reviewer"
    assert c.title == "Task 1 Reviewer"
    assert c.project_path == "/workspace/demo"


def test_ensure_ready_builds_the_index_in_the_foreground(store_and_indexer, home_path):
    """一次性进程的读路径靠它：返回时索引必须已经可查，而不是刚起了个线程。"""
    store, indexer = store_and_indexer
    _write_session(home_path, "s1", _row("s1", "hello"))

    assert store.is_ready() is False
    assert indexer.ensure_ready() is True
    assert store.is_ready() is True
    assert store.get_summary("claude", "s1") is not None


def test_ensure_ready_announces_only_when_it_blocks(store_and_indexer, home_path):
    store, indexer = store_and_indexer
    _write_session(home_path, "s1", _row("s1", "hello"))
    notices: list[int] = []

    assert indexer.ensure_ready(lambda: notices.append(1)) is True
    assert len(notices) == 1

    # 已经建好了：第二次不该再打断用户，也不该再同步一轮。
    assert indexer.ensure_ready(lambda: notices.append(1)) is True
    assert len(notices) == 1


def test_ensure_ready_picks_up_sessions_written_after_the_first_build(
    store_and_indexer, home_path
):
    """索引早就建好了，新进程里 ensure_ready 仍要前台补一次增量：
    刚在引擎里聊完、紧接着 ``ca -s`` 的那个会话必须能被选到。"""
    store, indexer = store_and_indexer
    _write_session(home_path, "s1", _row("s1", "hello"))
    indexer.sync()
    _write_session(home_path, "s2", _row("s2", "just finished"))

    fresh_process = SessionIndexer(store, home=home_path)
    assert fresh_process.ensure_ready() is True
    assert store.get_summary("claude", "s2") is not None


def test_ensure_ready_gives_up_after_one_failed_build(
    store_and_indexer, home_path, monkeypatch
):
    """建不起来时只赔一轮全量解析：同一条命令里的第二次读直接走回退。"""
    store, indexer = store_and_indexer
    _write_session(home_path, "s1", _row("s1", "hello"))
    syncs: list[int] = []

    def failing_sync(*args, **kwargs):
        syncs.append(1)
        # 真实的 sync() 会把异常吞掉并保持索引未就绪，这里等价地模拟。

    monkeypatch.setattr(indexer, "sync", failing_sync)

    assert indexer.ensure_ready() is False
    assert indexer.ensure_ready() is False
    assert len(syncs) == 1


def test_ensure_ready_rebuilds_when_the_parsers_changed(store_and_indexer, home_path):
    """升级换了解析器：旧索引还"ready"，但内容出自上一版 parser，必须先重建。"""
    store, indexer = store_and_indexer
    _write_session(home_path, "s1", _row("s1", "hello"))
    indexer.sync()
    assert store.is_ready() is True

    store.set_meta("parser_fingerprint", "produced-by-an-older-release")
    notices: list[int] = []

    assert indexer.ensure_ready(lambda: notices.append(1)) is True
    assert notices == [1], "指纹失配时应该重建，而不是直接把旧索引当可用"
    assert store.get_summary("claude", "s1") is not None

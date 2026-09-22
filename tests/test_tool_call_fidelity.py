"""工具调用能不能完整活着到另一个引擎里——这一层以前没有任何断言。

原来的转换测试都是**形状**契约（"每个 key 都在"、"id 格式对"），所以两个
丢内容的 bug 一路绿灯到线上：

1. 参数预览把序列化后的 JSON 从中间切断，writer 再 ``json.loads`` 必然失
   败并退回 ``{}``。本机 17298 次工具调用里 60% 超过那个 200 字符预算，也
   就是大多数转换过去的调用到达时**一个参数都没有**。
2. 源引擎没取到结果时写成 ``""``。模型读空串不是"这条没带过来"，是"命令
   执行了、没有输出"——一次转过去的 ``grep`` 于是成了"仓库里没有这个字符
   串"的证据。

所以这里断言的是内容而不是形状。
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from core.session_history.models import (
    EngineType,
    ToolCallSummary,
    UnifiedMessage,
    UnifiedSession,
)
from core.session_history.previews import (
    ARGS_PREVIEW_LIMIT,
    RESULT_NOT_CAPTURED,
    args_preview,
    result_for_writer,
    result_preview,
)
from core.session_history.writers.opencode_writer import write_opencode_session
from tests.test_session_history import _init_opencode_db, _make_git_repo

# ---------------------------------------------------------------------------
# 参数预览：永远是能 parse 的 JSON
# ---------------------------------------------------------------------------

ARGS_CASES = {
    "短参数原样通过": {"command": "ls", "description": "list"},
    "刚好超预算的命令": {"command": "x" * (ARGS_PREVIEW_LIMIT + 50)},
    "巨大的写入正文": {
        "file_path": "/repo/gui/main_window.py",
        "new_string": "行\n" * 40000,
    },
    "深层嵌套": {"a": {"b": {"c": ["y" * 9000, {"d": "z" * 9000}]}}},
    "成百上千个键": {f"key_{i}": f"value_{i}" * 20 for i in range(2000)},
    "非 ASCII": {"command": "grep -rn 本局后停止 gui/" * 900},
}


@pytest.mark.parametrize("case", list(ARGS_CASES), ids=list(ARGS_CASES))
def test_args_preview_is_always_parseable_json(case):
    """writer 无条件 ``json.loads`` 这个字符串，所以它只能是合法 JSON。"""
    rendered = args_preview(ARGS_CASES[case])
    json.loads(rendered)  # 抛异常即失败——这正是线上那个 bug 的形态
    assert len(rendered) <= ARGS_PREVIEW_LIMIT


def test_args_preview_keeps_the_structure_and_clips_the_values():
    """放不下时丢的是正文，不是"改了哪个文件"。"""
    rendered = args_preview(
        {"file_path": "/repo/gui/main_window.py", "new_string": "x" * 90000}
    )
    parsed = json.loads(rendered)

    assert parsed["file_path"] == "/repo/gui/main_window.py"
    assert "chars]" in parsed["new_string"], "裁过的值必须说明自己是裁过的"


def test_args_preview_leaves_an_empty_call_empty():
    assert args_preview({}) == ""
    assert args_preview(None) == ""


def test_result_preview_marks_what_it_dropped():
    """裁过的结果不能读起来像完整输出。"""
    assert "chars]" in result_preview("o" * 5000)
    assert result_preview("short") == "short"


# ---------------------------------------------------------------------------
# 结果：拿不到 ≠ 空
# ---------------------------------------------------------------------------


def test_a_result_we_never_captured_says_so():
    assert result_for_writer(ToolCallSummary(name="Bash")) == RESULT_NOT_CAPTURED


def test_a_genuinely_empty_result_stays_empty():
    """命令真的没有输出时，占位就成了另一句假话。"""
    call = ToolCallSummary(name="Bash", result_preview="", result_captured=True)
    assert result_for_writer(call) == ""


def test_a_result_without_the_flag_is_still_a_result():
    """flag 只消解空结果的歧义；漏设不该把真实结果抹成占位。"""
    call = ToolCallSummary(name="Bash", result_preview="On branch main")
    assert result_for_writer(call) == "On branch main"


# ---------------------------------------------------------------------------
# 端到端：Claude 的会话转到 OpenCode
# ---------------------------------------------------------------------------


def _convert_call(tmp_path: Path, monkeypatch, call: ToolCallSummary) -> dict:
    """把带 *call* 的会话转成 OpenCode，返回那个 tool part 的 ``state``。"""
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    db_path = tmp_path / ".local" / "share" / "opencode" / "opencode.db"
    db_path.parent.mkdir(parents=True)
    _init_opencode_db(db_path)

    worktree = tmp_path / "repo"
    _make_git_repo(worktree)

    session_id = write_opencode_session(
        UnifiedSession(
            session_id="orig",
            engine=EngineType.CLAUDE,
            project_path=str(worktree),
            messages=[
                UnifiedMessage(role="user", content="看一下停止的范围"),
                UnifiedMessage(role="assistant", content="我查一下", tool_calls=[call]),
            ],
        )
    )

    con = sqlite3.connect(str(db_path))
    rows = con.execute(
        "SELECT data FROM part WHERE session_id=?", (session_id,)
    ).fetchall()
    con.close()

    for (raw,) in rows:
        part = json.loads(raw)
        if part.get("type") == "tool":
            return part["state"]
    raise AssertionError("转换后的会话里没有工具调用")


def test_a_long_command_still_arrives_with_its_arguments(tmp_path, monkeypatch):
    """线上 bug 的回归：>200 字符的命令曾经整条变成 ``input: {}``。"""
    command = "grep -rn '本局后停止' gui/ " + "# 补足长度 " * 60
    state = _convert_call(
        tmp_path,
        monkeypatch,
        ToolCallSummary(name="Bash", args_preview=args_preview({"command": command})),
    )

    assert state["input"], "参数整条丢了"
    assert state["input"]["command"] == command


def test_an_uncaptured_result_does_not_arrive_as_an_empty_one(tmp_path, monkeypatch):
    """Claude 的解析器不取结果，所以转过去的每条调用都走这条路。"""
    state = _convert_call(tmp_path, monkeypatch, ToolCallSummary(name="Bash"))

    assert state["output"] != ""
    assert state["output"] == RESULT_NOT_CAPTURED


def test_a_captured_empty_result_arrives_empty(tmp_path, monkeypatch):
    state = _convert_call(
        tmp_path,
        monkeypatch,
        ToolCallSummary(name="Bash", result_preview="", result_captured=True),
    )

    assert state["output"] == ""


# ---------------------------------------------------------------------------
# 索引层：``ca switch`` 读的是索引，不是源文件
# ---------------------------------------------------------------------------


def _indexed_round_trip(tmp_path: Path, call: ToolCallSummary) -> ToolCallSummary:
    """把带 *call* 的会话写进索引再读回来。"""
    from core.session_history.index_store import SessionIndex

    index = SessionIndex(tmp_path / "index.db")
    try:
        index.write_session(
            UnifiedSession(
                session_id="s1",
                engine=EngineType.CLAUDE,
                project_path=str(tmp_path),
                messages=[
                    UnifiedMessage(role="assistant", content="查", tool_calls=[call])
                ],
            )
        )
        restored = index.reconstruct("claude", "s1")
    finally:
        index.close()

    assert restored is not None
    return restored.messages[0].tool_calls[0]


@pytest.mark.parametrize("captured", [True, False], ids=["captured", "uncaptured"])
def test_the_index_remembers_whether_a_result_was_captured(tmp_path, captured):
    """索引丢了这个位，writer 就没法把"空"和"没取"分开。"""
    restored = _indexed_round_trip(
        tmp_path,
        ToolCallSummary(name="Bash", result_preview="", result_captured=captured),
    )

    assert restored.result_captured is captured
    assert result_for_writer(restored) == ("" if captured else RESULT_NOT_CAPTURED)


def test_an_old_index_is_rebuilt_rather_than_migrated_in_place(tmp_path):
    """v1 的行推不出 ``result_captured``，ALTER 的默认值会让它们集体撒谎。"""
    from core.session_history.index_store import SCHEMA_VERSION, SessionIndex

    path = tmp_path / "index.db"
    con = sqlite3.connect(path)
    with con:
        con.executescript(
            """
            CREATE TABLE schema_version (version INTEGER NOT NULL);
            CREATE TABLE index_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE sources (source_key TEXT PRIMARY KEY);
            CREATE TABLE sessions (session_key TEXT PRIMARY KEY);
            CREATE TABLE messages (session_key TEXT, ordinal INTEGER);
            CREATE TABLE tool_calls (session_key TEXT, name TEXT);
            INSERT INTO schema_version(version) VALUES (1);
            INSERT INTO tool_calls(session_key, name) VALUES ('stale', 'Bash');
            """
        )
    con.close()

    index = SessionIndex(path)
    try:
        assert index.session_count() == 0, "陈旧的行应该被重建掉，而不是留着"
        columns = {
            row[1] for row in index._connection.execute("PRAGMA table_info(tool_calls)")
        }
        assert "result_captured" in columns
        version = index._connection.execute(
            "SELECT version FROM schema_version"
        ).fetchone()[0]
        assert version == SCHEMA_VERSION
    finally:
        index.close()


# ---------------------------------------------------------------------------
# OpenCode 的失败调用：消息在 state.error 里，不在 output 里
# ---------------------------------------------------------------------------


def _opencode_tool_call(state: dict) -> ToolCallSummary:
    """用一个 ``state`` 建库、解析，返回解析出的工具调用。"""
    from core.session_history.parsers.opencode_parser import parse_opencode_session

    part = {"type": "tool", "tool": "read", "callID": "c1", "state": state}
    import tempfile

    db_path = Path(tempfile.mkdtemp()) / "opencode.db"
    _init_opencode_db(db_path)
    con = sqlite3.connect(db_path)
    with con:
        con.execute(
            "INSERT INTO session (id, project_id, slug, directory, title, version,"
            " time_created, time_updated, metadata, summary_additions,"
            " summary_deletions, summary_files) VALUES"
            " ('ses_1','p','s','/repo','t','1.0.0',1,1,'{}',0,0,0)"
        )
        con.execute(
            "INSERT INTO message (id, session_id, time_created, time_updated, data)"
            " VALUES ('msg_1','ses_1',1,1,?)",
            (json.dumps({"role": "assistant"}),),
        )
        con.execute(
            "INSERT INTO part (id, message_id, session_id, time_created,"
            " time_updated, data) VALUES ('prt_1','msg_1','ses_1',1,1,?)",
            (json.dumps(part),),
        )
    con.close()

    parsed = parse_opencode_session("ses_1", db_path)
    assert parsed is not None
    return parsed.messages[0].tool_calls[0]


def test_a_failed_opencode_call_carries_its_error():
    """失败是已知事实，不该退化成"没取到结果"。"""
    call = _opencode_tool_call(
        {"status": "error", "input": {"filePath": "/x"}, "error": "File not found: /x"}
    )

    assert call.result_captured is True
    assert "File not found: /x" in call.result_preview


def test_a_call_left_running_is_not_reported_as_empty():
    call = _opencode_tool_call({"status": "running", "input": {"filePath": "/x"}})

    assert call.result_captured is False
    assert result_for_writer(call) == RESULT_NOT_CAPTURED

"""Coverage for the OpenCode parser -- 307 lines that had none.

It is the reader half of the pair whose writer half broke twice this week, and
it is the only thing standing between OpenCode's private SQLite schema and
every session list, transcript and usage figure we show. The cases pinned here
are the ones where a malformed or partial row must degrade rather than take
the whole listing down.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from core.session_history.parse_cache import clear_parse_cache
from core.session_history.parsers import opencode_parser
from core.session_history.parsers.opencode_parser import (
    find_opencode_sessions,
    parse_opencode_session,
)


def _make_db(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(path))
    with con:
        con.execute(
            """CREATE TABLE session (
                id TEXT PRIMARY KEY, project_id TEXT, directory TEXT, title TEXT,
                model TEXT, time_created INTEGER, time_updated INTEGER
            )"""
        )
        con.execute(
            """CREATE TABLE message (
                id TEXT PRIMARY KEY, session_id TEXT, time_created INTEGER, data TEXT
            )"""
        )
        con.execute(
            """CREATE TABLE part (
                id TEXT PRIMARY KEY, message_id TEXT, session_id TEXT,
                time_created INTEGER, data TEXT
            )"""
        )
    return con


def _session(con, sid="ses_1", *, directory="E:/x", model='{"id":"m1"}', title="t"):
    with con:
        con.execute(
            "INSERT INTO session VALUES (?,?,?,?,?,?,?)",
            (sid, "prj", directory, title, model, 1_700_000_000_000, 1_700_000_060_000),
        )


def _message(con, mid, sid="ses_1", *, role="user", when=1_700_000_000_000, data=None):
    payload = {"role": role} if data is None else data
    with con:
        con.execute(
            "INSERT INTO message VALUES (?,?,?,?)",
            (mid, sid, when, json.dumps(payload) if payload is not None else None),
        )


def _part(con, pid, mid, sid="ses_1", *, data=None, when=1_700_000_000_000):
    with con:
        con.execute(
            "INSERT INTO part VALUES (?,?,?,?,?)",
            (pid, mid, sid, when, json.dumps(data) if data is not None else None),
        )


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "opencode.db"
    con = _make_db(path)
    yield path, con
    con.close()


@pytest.fixture(autouse=True)
def _clean_parse_cache():
    clear_parse_cache()
    yield
    clear_parse_cache()


# ── the happy path ───────────────────────────────────────────────────────────
def test_a_session_parses_into_messages_and_tool_calls(db):
    path, con = db
    _session(con)
    _message(con, "m_u", role="user", when=1_700_000_000_000)
    _part(con, "p1", "m_u", data={"type": "text", "text": "hello"})
    _message(con, "m_a", role="assistant", when=1_700_000_030_000)
    _part(con, "p2", "m_a", data={"type": "text", "text": "hi"})
    _part(
        con,
        "p3",
        "m_a",
        data={"type": "tool", "tool": "bash", "state": {"input": {"command": "ls"}}},
    )

    parsed = parse_opencode_session("ses_1", path)

    assert parsed is not None
    assert parsed.engine.value == "opencode"
    assert parsed.model == "m1"
    assert [m.role for m in parsed.messages] == ["user", "assistant"]
    assert parsed.messages[0].content == "hello"
    assert [tc.name for tc in parsed.messages[1].tool_calls] == ["bash"]


def test_messages_come_back_in_time_order(db):
    path, con = db
    _session(con)
    _message(con, "m_late", role="assistant", when=2_000)
    _part(con, "p_late", "m_late", data={"type": "text", "text": "second"})
    _message(con, "m_early", role="user", when=1_000)
    _part(con, "p_early", "m_early", data={"type": "text", "text": "first"})

    parsed = parse_opencode_session("ses_1", path)

    assert [m.content for m in parsed.messages] == ["first", "second"]


# ── degradation, which is the whole point of a parser ────────────────────────
def test_an_unknown_session_id_returns_none_rather_than_raising(db):
    path, con = db
    _session(con)

    assert parse_opencode_session("ses_missing", path) is None


def test_a_missing_database_returns_none(tmp_path):
    assert parse_opencode_session("ses_1", tmp_path / "nope.db") is None


def test_a_message_with_unparseable_json_is_skipped_not_fatal(db):
    path, con = db
    _session(con)
    with con:
        con.execute(
            "INSERT INTO message VALUES (?,?,?,?)", ("m_bad", "ses_1", 1_000, "{oops")
        )
    _message(con, "m_ok", role="user", when=2_000)
    _part(con, "p", "m_ok", data={"type": "text", "text": "survived"})

    parsed = parse_opencode_session("ses_1", path)

    assert [m.content for m in parsed.messages] == ["survived"]


def test_a_part_with_unparseable_json_is_skipped_not_fatal(db):
    path, con = db
    _session(con)
    _message(con, "m", role="user")
    with con:
        con.execute(
            "INSERT INTO part VALUES (?,?,?,?,?)",
            ("p_bad", "m", "ses_1", 1_000, "{oops"),
        )
    _part(con, "p_ok", "m", data={"type": "text", "text": "kept"}, when=2_000)

    parsed = parse_opencode_session("ses_1", path)

    assert parsed.messages[0].content == "kept"


def test_roles_other_than_user_and_assistant_are_dropped(db):
    path, con = db
    _session(con)
    _message(con, "m_sys", role="system")
    _part(con, "p", "m_sys", data={"type": "text", "text": "ignore me"})
    _message(con, "m_u", role="user", when=2_000)
    _part(con, "p2", "m_u", data={"type": "text", "text": "keep me"})

    parsed = parse_opencode_session("ses_1", path)

    assert [m.content for m in parsed.messages] == ["keep me"]


def _with_one_message(con) -> None:
    _message(con, "m", role="user")
    _part(con, "p", "m", data={"type": "text", "text": "x"})


def test_a_model_column_that_is_not_json_is_used_verbatim(db):
    # Older rows stored a bare string; losing the model entirely would make
    # every cost for that session fall back to the unknown-model rate.
    path, con = db
    _session(con, model="plain-model-id")
    _with_one_message(con)

    assert parse_opencode_session("ses_1", path).model == "plain-model-id"


def test_a_null_model_leaves_the_field_empty(db):
    path, con = db
    _session(con, model=None)
    _with_one_message(con)

    assert parse_opencode_session("ses_1", path).model == ""


def test_a_session_with_no_messages_is_not_a_session(db):
    # Empty rows exist -- OpenCode writes the session before the first turn.
    # Returning None keeps them out of every listing rather than showing a
    # row that opens onto nothing.
    path, con = db
    _session(con)

    assert parse_opencode_session("ses_1", path) is None


def test_a_caller_supplied_connection_is_left_open(db):
    # find_opencode_sessions reuses one connection across every session; if
    # the parser closed it the second call would fail.
    path, con = db
    _session(con)
    _message(con, "m", role="user")
    _part(con, "p", "m", data={"type": "text", "text": "x"})

    reader = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    reader.row_factory = sqlite3.Row
    try:
        assert parse_opencode_session("ses_1", path, connection=reader) is not None
        assert parse_opencode_session("ses_1", path, connection=reader) is not None
    finally:
        reader.close()


# ── discovery ────────────────────────────────────────────────────────────────
def test_find_returns_sessions_for_a_matching_directory(db, tmp_path, monkeypatch):
    path, con = db
    _session(con, "ses_a", directory="E:/work/app")
    _message(con, "m", "ses_a", role="user")
    _part(con, "p", "m", "ses_a", data={"type": "text", "text": "x"})
    _session(con, "ses_b", directory="E:/work/other")

    monkeypatch.setattr(
        "core.session_history.parsers.opencode_parser._find_opencode_db",
        lambda home=None: path,
    )

    found = find_opencode_sessions("E:/work/app")

    assert [s.session_id for s in found] == ["ses_a"]


def test_find_without_a_database_returns_empty(monkeypatch):
    monkeypatch.setattr(
        "core.session_history.parsers.opencode_parser._find_opencode_db",
        lambda home=None: None,
    )

    assert find_opencode_sessions("E:/work/app") == []


# ── the parse cache ──────────────────────────────────────────────────────────
def test_an_unchanged_session_is_not_reparsed(db, monkeypatch):
    path, con = db
    _session(con, "ses_a", directory="E:/work/app")
    _message(con, "m", "ses_a", role="user")
    _part(con, "p", "m", "ses_a", data={"type": "text", "text": "x"})

    monkeypatch.setattr(opencode_parser, "_find_opencode_db", lambda home=None: path)
    parses = []
    real_parse = opencode_parser.parse_opencode_session

    def counting_parse(session_id, db_path, connection=None):
        parses.append(session_id)
        return real_parse(session_id, db_path, connection=connection)

    monkeypatch.setattr(opencode_parser, "parse_opencode_session", counting_parse)

    assert len(find_opencode_sessions("E:/work/app")) == 1
    assert parses == ["ses_a"]
    assert len(find_opencode_sessions("E:/work/app")) == 1
    assert parses == ["ses_a"], "cache hit still re-parsed the session"


def test_an_appended_part_is_picked_up_without_a_time_updated_bump(db, monkeypatch):
    # OpenCode writes parts without always bumping session.time_updated, so
    # keying the cache on that column alone would serve the first parse
    # forever. _session never touches time_updated after the insert, which is
    # exactly the case being pinned here.
    path, con = db
    _session(con, "ses_a", directory="E:/work/app")
    _message(con, "m", "ses_a", role="user")
    _part(con, "p1", "m", "ses_a", data={"type": "text", "text": "first"})

    monkeypatch.setattr(opencode_parser, "_find_opencode_db", lambda home=None: path)

    before = find_opencode_sessions("E:/work/app")
    assert before[0].messages[0].content == "first"

    _part(con, "p2", "m", "ses_a", data={"type": "text", "text": "second"})

    after = find_opencode_sessions("E:/work/app")
    assert "second" in after[0].messages[0].content


def _make_db_with_subagent_columns(path: Path) -> sqlite3.Connection:
    """A database from a build that knows about subagents."""
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(path))
    with con:
        con.execute(
            """CREATE TABLE session (
                id TEXT PRIMARY KEY, project_id TEXT, directory TEXT, title TEXT,
                model TEXT, time_created INTEGER, time_updated INTEGER,
                parent_id TEXT, agent TEXT
            )"""
        )
        con.execute(
            """CREATE TABLE message (
                id TEXT PRIMARY KEY, session_id TEXT, time_created INTEGER, data TEXT
            )"""
        )
        con.execute(
            """CREATE TABLE part (
                id TEXT PRIMARY KEY, message_id TEXT, session_id TEXT,
                time_created INTEGER, data TEXT
            )"""
        )
    return con


def test_a_subagent_session_carries_its_parent_and_agent(tmp_path):
    path = tmp_path / "opencode.db"
    con = _make_db_with_subagent_columns(path)
    try:
        with con:
            con.execute(
                "INSERT INTO session VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    "ses_child",
                    "prj",
                    "E:/x",
                    "前端代码质量检查 (@explore subagent)",
                    '{"id":"m1"}',
                    1_700_000_000_000,
                    1_700_000_060_000,
                    "ses_parent",
                    "explore",
                ),
            )
            con.execute(
                "INSERT INTO message VALUES (?,?,?,?)",
                ("m1", "ses_child", 1_700_000_000_000, json.dumps({"role": "user"})),
            )
            con.execute(
                "INSERT INTO part VALUES (?,?,?,?,?)",
                (
                    "p1",
                    "m1",
                    "ses_child",
                    1_700_000_000_000,
                    json.dumps({"type": "text", "text": "查一下前端"}),
                ),
            )
        clear_parse_cache()

        session = parse_opencode_session("ses_child", path)

        assert session is not None
        assert session.parent_session_id == "ses_parent"
        assert session.agent == "explore"
    finally:
        con.close()


def test_a_database_without_the_subagent_columns_still_parses(db):
    """OpenCode grew parent_id/agent late; naming them on an older database
    would fail the whole query rather than one field."""
    path, con = db
    _session(con, "ses_1")
    _message(con, "m1")
    _part(con, "p1", "m1", data={"type": "text", "text": "hello"})
    clear_parse_cache()

    session = parse_opencode_session("ses_1", path)

    assert session is not None
    assert session.parent_session_id == ""
    assert session.agent == ""

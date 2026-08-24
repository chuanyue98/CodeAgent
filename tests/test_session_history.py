"""Tests for cross-engine session history parsing, conversion, and API."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from core.session_history.models import (
    EngineType,
    ToolCallSummary,
    UnifiedMessage,
    UnifiedSession,
)
from core.session_history.parsers.claude_parser import (
    _claude_dir_matches,
    _decode_claude_project_path,
    _encode_claude_project_dir,
    parse_claude_session,
)
from core.session_history.parsers.codex_parser import _ms_to_iso, parse_codex_session

# ─── UnifiedSession model tests ───────────────────────────────────────


def test_unified_session_basic():
    session = UnifiedSession(
        session_id="test-123",
        engine=EngineType.CLAUDE,
        project_path="E:/demo/test",
        started_at="2026-07-11T10:00:00.000Z",
        ended_at="2026-07-11T11:00:00.000Z",
        messages=[
            UnifiedMessage(role="user", content="Hello"),
            UnifiedMessage(role="assistant", content="Hi there"),
        ],
        title="Test Session",
        model="claude-sonnet-4",
    )
    assert session.message_count == 2
    assert session.first_user_message == "Hello"
    summary = session.to_summary_dict()
    assert summary["engine"] == "claude"
    assert summary["message_count"] == 2
    assert summary["title"] == "Test Session"
    full = session.to_full_dict()
    assert len(full["messages"]) == 2
    assert full["messages"][0]["role"] == "user"


def test_unified_session_no_title_generates_from_first_message():
    session = UnifiedSession(
        messages=[UnifiedMessage(role="user", content="Fix the auth bug in middleware")]
    )
    title = session.generate_title()
    assert "Fix the auth bug" in title


def test_tool_call_summary():
    tc = ToolCallSummary(
        name="read_file",
        args_preview='{"path": "src/main.py"}',
        result_preview="file contents",
    )
    assert tc.name == "read_file"
    d = UnifiedMessage(role="assistant", content="", tool_calls=[tc]).to_dict()
    assert d["tool_calls"][0]["name"] == "read_file"


# ─── Claude parser tests ──────────────────────────────────────────────


def test_decode_claude_project_path_windows():
    assert _decode_claude_project_path("E--demo-CodeAgent") == "E:/demo/CodeAgent"
    assert (
        _decode_claude_project_path("C--Users-Administrator")
        == "C:/Users/Administrator"
    )


def test_encode_claude_project_dir_matches_real_claude_code_output():
    """Verified against real ``~/.claude/projects`` directories on this
    machine, cross-checked with the ``cwd`` recorded inside each session's
    JSONL. Claude Code's real rule replaces every non-alphanumeric
    character with a dash — not just path separators, e.g. the dots in
    ``Ubuntu-24.04`` become dashes too, same as the surrounding
    backslashes and the existing literal dash."""
    assert _encode_claude_project_dir("E:/demo/hearthstone-bot") == (
        "E--demo-hearthstone-bot"
    )
    assert _encode_claude_project_dir("E:/me") == "E--me"
    assert (
        _encode_claude_project_dir("C:/Users/Administrator") == "C--Users-Administrator"
    )
    assert (
        _encode_claude_project_dir(
            "//wsl.localhost/Ubuntu-24.04/home/cy/github/chuanyue98/CUITCCA"
        )
        == "--wsl-localhost-Ubuntu-24-04-home-cy-github-chuanyue98-CUITCCA"
    )


def test_claude_dir_matches_real_world_samples():
    """These dir_name/target_path pairs are taken directly from real
    ``~/.claude/projects/<dir>`` entries and the ``cwd`` field recorded in
    their session JSONL files."""
    assert _claude_dir_matches("E--demo-hearthstone-bot", "E:\\demo\\hearthstone-bot")
    assert _claude_dir_matches("E--demo-hearthstone-bot", "E:/demo/hearthstone-bot")
    assert _claude_dir_matches("E--me", "E:\\me")
    assert _claude_dir_matches("C--Users-Administrator", "C:\\Users\\Administrator")
    assert _claude_dir_matches(
        "--wsl-localhost-Ubuntu-24-04-home-cy-github-chuanyue98-CUITCCA",
        "\\\\wsl.localhost\\Ubuntu-24.04\\home\\cy\\github\\chuanyue98\\CUITCCA",
    )


def test_claude_dir_matches_is_case_insensitive():
    assert _claude_dir_matches("e--demo-test", "E:/demo/test")
    assert _claude_dir_matches("E--DEMO-TEST", "e:/demo/test")


def test_claude_dir_matches_rejects_similar_but_different_paths():
    assert not _claude_dir_matches("E--demo-project-a", "E:/demo/project-b")
    # A dir name must not match a shorter/longer prefix of itself.
    assert not _claude_dir_matches("E--demo-project-a", "E:/demo/project-ab")
    assert not _claude_dir_matches("E--demo-project-ab", "E:/demo/project-a")


def test_claude_dir_matches_handles_dashes_in_project_name():
    """A project directory whose real name contains a literal dash (e.g.
    ``my-project``) must still match on its own encoded path."""
    assert _claude_dir_matches("E--demo-my-project", "E:/demo/my-project")
    assert _claude_dir_matches("E--demo-my-project", "E:\\demo\\my-project")


def test_claude_dir_matches_inherent_claude_code_ambiguity():
    """Claude Code's own encoding collapses ``my-project`` (a literal dash
    in the name) and ``my/project`` (a nested directory) onto the exact
    same directory name, ``...-my-project``. Claude Code itself cannot
    tell these two projects apart on disk, so this matcher — which mirrors
    Claude's own encoding rather than trying to invert it — correctly
    reports a match for *both* target paths against that one directory.
    This is a pre-existing limitation of Claude Code's own encoding, not
    something a matcher can resolve after the fact."""
    assert _claude_dir_matches("E--demo-my-project", "E:/demo/my-project")
    assert _claude_dir_matches("E--demo-my-project", "E:/demo/my/project")


def test_parse_claude_session(tmp_path):
    """Test parsing a minimal Claude JSONL session file."""
    session_dir = tmp_path / ".claude" / "projects" / "E--demo-test"
    session_dir.mkdir(parents=True)
    session_file = session_dir / "abc123.jsonl"

    lines = [
        json.dumps(
            {
                "type": "ai-title",
                "aiTitle": "Debug auth flow",
            }
        ),
        json.dumps(
            {
                "type": "user",
                "message": {"role": "user", "content": "Help me debug the auth"},
                "uuid": "msg-1",
                "timestamp": "2026-07-10T10:00:00.000Z",
                "cwd": "E:\\demo\\test",
                "sessionId": "abc123",
            }
        ),
        json.dumps(
            {
                "type": "assistant",
                "message": {
                    "model": "claude-sonnet-4",
                    "role": "assistant",
                    "content": [
                        {"type": "text", "text": "I'll look at the auth middleware."},
                        {
                            "type": "tool_use",
                            "id": "tool-1",
                            "name": "read_file",
                            "input": {"path": "src/auth.ts"},
                        },
                    ],
                    "stop_reason": "tool_use",
                },
                "uuid": "msg-2",
                "timestamp": "2026-07-10T10:00:05.000Z",
                "sessionId": "abc123",
            }
        ),
        json.dumps(
            {
                "type": "user",
                "message": {"role": "user", "content": "The issue is in token refresh"},
                "uuid": "msg-3",
                "timestamp": "2026-07-10T10:01:00.000Z",
                "sessionId": "abc123",
            }
        ),
    ]
    session_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

    session = parse_claude_session(session_file)

    assert session is not None
    assert session.session_id == "abc123"
    assert session.engine == EngineType.CLAUDE
    assert session.title == "Debug auth flow"
    assert session.model == "claude-sonnet-4"
    assert session.message_count == 3
    assert session.messages[0].role == "user"
    assert session.messages[0].content == "Help me debug the auth"
    assert session.messages[1].role == "assistant"
    assert "auth middleware" in session.messages[1].content
    assert len(session.messages[1].tool_calls) == 1
    assert session.messages[1].tool_calls[0].name == "read_file"


def test_parse_claude_empty_file(tmp_path):
    """Empty or non-existent files return None."""
    assert parse_claude_session(tmp_path / "nonexistent.jsonl") is None


def test_parse_claude_session_prefers_exact_cwd_for_hyphenated_path(tmp_path):
    session_dir = tmp_path / ".claude" / "projects" / "-home-user-my-project"
    session_dir.mkdir(parents=True)
    session_file = session_dir / "hyphenated.jsonl"
    session_file.write_text(
        json.dumps(
            {
                "type": "user",
                "message": {"role": "user", "content": "hello"},
                "timestamp": "2026-07-10T10:00:00.000Z",
                "cwd": "/home/user/my-project",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    session = parse_claude_session(session_file)

    assert session is not None
    assert session.project_path == "/home/user/my-project"


# ─── Codex parser tests ───────────────────────────────────────────────


def test_parse_codex_session(tmp_path):
    """Test parsing a minimal Codex JSONL session file."""
    session_dir = tmp_path / ".codex" / "sessions" / "2026" / "07" / "11"
    session_dir.mkdir(parents=True)
    session_file = session_dir / "rollout-2026-07-11T10-00-00-abc123.jsonl"

    lines = [
        json.dumps(
            {
                "timestamp": "2026-07-11T10:00:00.000Z",
                "type": "session_meta",
                "payload": {
                    "id": "abc123",
                    "cwd": "E:\\demo\\test",
                    "cli_version": "0.132.0",
                },
            }
        ),
        json.dumps(
            {
                "timestamp": "2026-07-11T10:00:01.000Z",
                "type": "turn_context",
                "payload": {"model": "gpt-5.4-mini"},
            }
        ),
        json.dumps(
            {
                "timestamp": "2026-07-11T10:00:02.000Z",
                "type": "event_msg",
                "payload": {"type": "user_message", "message": "Fix the N+1 query"},
            }
        ),
        json.dumps(
            {
                "timestamp": "2026-07-11T10:00:03.000Z",
                "type": "event_msg",
                "payload": {
                    "type": "agent_message",
                    "message": "I'll optimize the query.",
                    "phase": "final",
                },
            }
        ),
    ]
    session_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

    session = parse_codex_session(session_file)

    assert session is not None
    assert session.engine == EngineType.CODEX
    assert session.project_path == "E:\\demo\\test"
    assert session.model == "gpt-5.4-mini"
    assert session.message_count == 2
    assert session.messages[0].role == "user"
    assert session.messages[0].content == "Fix the N+1 query"
    assert session.messages[1].role == "assistant"
    assert "optimize" in session.messages[1].content


def test_codex_timestamp_parser_accepts_seconds_and_milliseconds():
    assert _ms_to_iso(1_700_000_000) == "2023-11-14T22:13:20.000Z"
    assert _ms_to_iso(1_700_000_000_000) == "2023-11-14T22:13:20.000Z"
    assert _ms_to_iso("2023-11-14T22:13:20Z") == "2023-11-14T22:13:20.000Z"
    assert _ms_to_iso(None) == ""
    assert _ms_to_iso("not-a-timestamp") == ""


# ─── Round-trip conversion test ───────────────────────────────────────


def test_claude_to_codex_round_trip(tmp_path, monkeypatch):
    """Test converting a Claude session to Codex format and parsing it back."""
    # Create a Claude session file
    claude_dir = tmp_path / ".claude" / "projects" / "E--demo-test"
    claude_dir.mkdir(parents=True)
    claude_file = claude_dir / "orig-session.jsonl"

    lines = [
        json.dumps(
            {
                "type": "user",
                "message": {"role": "user", "content": "Write a hello world"},
                "uuid": "u1",
                "timestamp": "2026-07-10T10:00:00.000Z",
                "cwd": "E:\\demo\\test",
                "sessionId": "orig-session",
            }
        ),
        json.dumps(
            {
                "type": "assistant",
                "message": {
                    "model": "claude-sonnet-4",
                    "role": "assistant",
                    "content": [{"type": "text", "text": "print('Hello, World!')"}],
                    "stop_reason": "end_turn",
                },
                "uuid": "a1",
                "timestamp": "2026-07-10T10:00:05.000Z",
                "sessionId": "orig-session",
            }
        ),
    ]
    claude_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # Parse the Claude session
    from core.session_history.parsers.claude_parser import parse_claude_session

    session = parse_claude_session(claude_file)
    assert session is not None
    assert session.message_count == 2

    # Override home directory for the writer
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    # Write as Codex format
    from core.session_history.writers.codex_writer import write_codex_session

    new_id = write_codex_session(session)
    assert new_id

    # Find and parse the written Codex file
    codex_sessions_dir = tmp_path / ".codex" / "sessions"
    codex_files = list(codex_sessions_dir.rglob("*.jsonl"))
    assert len(codex_files) == 1

    from core.session_history.parsers.codex_parser import parse_codex_session

    codex_session = parse_codex_session(codex_files[0])

    assert codex_session is not None
    assert codex_session.engine == EngineType.CODEX
    assert codex_session.message_count >= 2
    # Check that the user message survived the round-trip
    user_msgs = [m for m in codex_session.messages if m.role == "user"]
    assert any("hello world" in m.content.lower() for m in user_msgs)
    # Check that the assistant message survived
    assistant_msgs = [m for m in codex_session.messages if m.role == "assistant"]
    assert any("Hello, World" in m.content for m in assistant_msgs)


def _init_opencode_db(db_path):
    """Creates an OpenCode-shaped SQLite db with the columns write_opencode_session uses."""
    import sqlite3

    con = sqlite3.connect(str(db_path))
    with con:
        con.execute(
            """CREATE TABLE project (
                id TEXT PRIMARY KEY, worktree TEXT NOT NULL, vcs TEXT, name TEXT,
                time_created INTEGER NOT NULL, time_updated INTEGER NOT NULL,
                sandboxes TEXT NOT NULL
            )"""
        )
        con.execute(
            """CREATE TABLE session (
                id TEXT PRIMARY KEY, project_id TEXT NOT NULL, parent_id TEXT, slug TEXT NOT NULL,
                directory TEXT NOT NULL, title TEXT NOT NULL, version TEXT NOT NULL,
                model TEXT, cost REAL, tokens_input INTEGER, tokens_output INTEGER,
                tokens_reasoning INTEGER, tokens_cache_read INTEGER, tokens_cache_write INTEGER,
                time_created INTEGER NOT NULL, time_updated INTEGER NOT NULL,
                time_compacting INTEGER, time_archived INTEGER, workspace_id TEXT, path TEXT,
                agent TEXT, metadata TEXT, summary_additions INTEGER, summary_deletions INTEGER,
                summary_files INTEGER, summary_diffs TEXT, share_url TEXT, permission TEXT
            )"""
        )
        con.execute(
            """CREATE TABLE message (
                id TEXT PRIMARY KEY, session_id TEXT NOT NULL, time_created INTEGER NOT NULL,
                time_updated INTEGER NOT NULL, data TEXT NOT NULL
            )"""
        )
        con.execute(
            """CREATE TABLE part (
                id TEXT PRIMARY KEY, message_id TEXT NOT NULL, session_id TEXT NOT NULL,
                time_created INTEGER NOT NULL, time_updated INTEGER NOT NULL, data TEXT NOT NULL
            )"""
        )
    con.close()


def _make_git_repo(path: Path) -> str:
    """Creates a git repository at *path* and returns its root-commit SHA."""
    path.mkdir(parents=True, exist_ok=True)
    run = lambda *args: subprocess.run(  # noqa: E731
        ["git", "-C", str(path), *args], capture_output=True, text=True, check=True
    )
    run("init", "-q")
    run("config", "user.email", "t@example.com")
    run("config", "user.name", "t")
    (path / "README.md").write_text("x", encoding="utf-8")
    run("add", "-A")
    run("commit", "-qm", "init")
    return run("rev-parse", "HEAD").stdout.strip()


@pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")
def test_write_opencode_session_uses_opencode_project_id(tmp_path, monkeypatch):
    """The session must hang off the project id OpenCode itself derives.

    OpenCode keys a git worktree's project on the repository's root commit, and
    filters ``session list`` on ``session.project_id``. Minting an id of our own
    (which this writer used to do) leaves a well-formed row that is invisible in
    both ``opencode session list`` and the TUI picker.
    """
    import sqlite3

    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    db_path = tmp_path / ".local" / "share" / "opencode" / "opencode.db"
    db_path.parent.mkdir(parents=True)
    _init_opencode_db(db_path)

    worktree = tmp_path / "repo"
    root_commit = _make_git_repo(worktree)

    session = UnifiedSession(
        session_id="orig-session",
        engine=EngineType.CLAUDE,
        project_path=str(worktree),
        messages=[
            UnifiedMessage(role="user", content="hello"),
            UnifiedMessage(role="assistant", content="hi there"),
        ],
    )

    from core.session_history.writers.opencode_writer import write_opencode_session

    new_id = write_opencode_session(session)

    con = sqlite3.connect(str(db_path))
    project_id = con.execute(
        "SELECT project_id FROM session WHERE id = ?", (new_id,)
    ).fetchone()[0]
    project_count = con.execute(
        "SELECT COUNT(*) FROM project WHERE id = ?", (project_id,)
    ).fetchone()[0]
    con.close()

    assert project_id == root_commit
    assert project_count == 1


@pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")
def test_write_opencode_session_reuses_existing_project(tmp_path, monkeypatch):
    """A project row OpenCode already wrote is reused, not duplicated."""
    import sqlite3

    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    db_path = tmp_path / ".local" / "share" / "opencode" / "opencode.db"
    db_path.parent.mkdir(parents=True)
    _init_opencode_db(db_path)

    worktree = tmp_path / "repo"
    root_commit = _make_git_repo(worktree)

    con = sqlite3.connect(str(db_path))
    with con:
        con.execute(
            "INSERT INTO project (id, worktree, time_created, time_updated, sandboxes) "
            "VALUES (?, ?, 1700000000000, 1700000000000, '[]')",
            (root_commit, str(worktree)),
        )
    con.close()

    session = UnifiedSession(
        session_id="orig-session",
        engine=EngineType.CLAUDE,
        project_path=str(worktree),
        messages=[UnifiedMessage(role="user", content="hello")],
    )

    from core.session_history.writers.opencode_writer import write_opencode_session

    new_id = write_opencode_session(session)

    con = sqlite3.connect(str(db_path))
    project_id = con.execute(
        "SELECT project_id FROM session WHERE id = ?", (new_id,)
    ).fetchone()[0]
    total = con.execute("SELECT COUNT(*) FROM project").fetchone()[0]
    con.close()

    assert project_id == root_commit
    assert total == 1  # reused, not duplicated


def test_write_opencode_session_falls_back_to_global_outside_git(tmp_path, monkeypatch):
    """A directory that is not a git repository lands in OpenCode's ``global``
    project, which is where OpenCode itself puts those sessions."""
    import sqlite3

    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    db_path = tmp_path / ".local" / "share" / "opencode" / "opencode.db"
    db_path.parent.mkdir(parents=True)
    _init_opencode_db(db_path)

    plain = tmp_path / "not-a-repo"
    plain.mkdir()

    session = UnifiedSession(
        session_id="orig-session",
        engine=EngineType.CLAUDE,
        project_path=str(plain),
        messages=[UnifiedMessage(role="user", content="hello")],
    )

    from core.session_history.writers.opencode_writer import write_opencode_session

    new_id = write_opencode_session(session)

    con = sqlite3.connect(str(db_path))
    project_id = con.execute(
        "SELECT project_id FROM session WHERE id = ?", (new_id,)
    ).fetchone()[0]
    con.close()

    assert project_id == "global"


def test_write_opencode_session_omits_unknown_provider(tmp_path, monkeypatch):
    """The converted session must not name a provider OpenCode cannot resolve.

    Writing ``{"id": <source model>, "providerID": "converted"}`` made the very
    first turn after resuming fail with ``UnknownError: Unexpected server
    error`` — there is no provider registered under that name. A NULL model
    falls back to the user's configured default.
    """
    import sqlite3

    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    db_path = tmp_path / ".local" / "share" / "opencode" / "opencode.db"
    db_path.parent.mkdir(parents=True)
    _init_opencode_db(db_path)

    session = UnifiedSession(
        session_id="orig-session",
        engine=EngineType.CLAUDE,
        project_path=str(tmp_path / "plain"),
        model="claude-opus-5",
        messages=[
            UnifiedMessage(role="user", content="hello"),
            UnifiedMessage(role="assistant", content="hi", model="claude-opus-5"),
        ],
    )

    from core.session_history.writers.opencode_writer import write_opencode_session

    new_id = write_opencode_session(session)

    con = sqlite3.connect(str(db_path))
    model = con.execute("SELECT model FROM session WHERE id = ?", (new_id,)).fetchone()[
        0
    ]
    payloads = [
        json.loads(row[0])
        for row in con.execute(
            "SELECT data FROM message WHERE session_id = ?", (new_id,)
        )
    ]
    con.close()

    assert model is None
    assert all("providerID" not in payload for payload in payloads)
    # The assistant reply chains to the user turn it answered.
    assistant = next(p for p in payloads if p["role"] == "assistant")
    assert assistant["parentID"] is not None


def test_write_opencode_session_tool_part_carries_state_time(tmp_path, monkeypatch):
    """Tool parts need ``state.time``.

    Bisected against OpenCode 1.18.21: a converted session whose tool parts
    omitted ``state.time`` failed on the next turn, while adding just that field
    made it go through. ``status`` also has to be one of OpenCode's own values —
    the "unknown" this used to emit is not one.
    """
    import sqlite3

    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    db_path = tmp_path / ".local" / "share" / "opencode" / "opencode.db"
    db_path.parent.mkdir(parents=True)
    _init_opencode_db(db_path)

    session = UnifiedSession(
        session_id="orig-session",
        engine=EngineType.CLAUDE,
        project_path=str(tmp_path / "plain"),
        messages=[
            UnifiedMessage(
                role="assistant",
                content="running it",
                tool_calls=[ToolCallSummary(name="Bash", args_preview='{"cmd": "ls"}')],
            )
        ],
    )

    from core.session_history.writers.opencode_writer import write_opencode_session

    new_id = write_opencode_session(session)

    con = sqlite3.connect(str(db_path))
    parts = [
        json.loads(row[0])
        for row in con.execute("SELECT data FROM part WHERE session_id = ?", (new_id,))
    ]
    con.close()

    tool_part = next(p for p in parts if p["type"] == "tool")
    assert tool_part["state"]["status"] == "completed"
    assert set(tool_part["state"]["time"]) == {"start", "end"}
    assert "title" in tool_part["state"]
    assert "metadata" in tool_part["state"]


# ─── Session finder tests ─────────────────────────────────────────────


def test_find_all_sessions_empty(tmp_path, monkeypatch):
    """When no sessions exist, returns empty list."""
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    from core.session_history.session_finder import find_all_sessions

    sessions = find_all_sessions("E:/demo/nonexistent")
    assert sessions == []


def _write_claude_session(
    base: Path, project_dir: str, session_id: str, timestamp: str
):
    session_dir = base / ".claude" / "projects" / project_dir
    session_dir.mkdir(parents=True)
    session_file = session_dir / f"{session_id}.jsonl"
    line = json.dumps(
        {
            "type": "user",
            "message": {"role": "user", "content": "hello"},
            "uuid": "u1",
            "timestamp": timestamp,
            "sessionId": session_id,
        }
    )
    session_file.write_text(line + "\n", encoding="utf-8")


def test_find_all_sessions_no_project_filter(tmp_path):
    """With project_path=None, sessions from every project directory are returned."""
    from core.session_history.session_finder import find_all_sessions

    _write_claude_session(
        tmp_path, "E--demo-project-a", "sess-a", "2026-07-10T10:00:00.000Z"
    )
    _write_claude_session(
        tmp_path, "E--demo-project-b", "sess-b", "2026-07-11T10:00:00.000Z"
    )

    sessions = find_all_sessions(None, home=tmp_path, engine="claude")
    ids = {s.session_id for s in sessions}
    assert ids == {"sess-a", "sess-b"}
    # Most recent first
    assert sessions[0].session_id == "sess-b"


def test_find_all_sessions_with_project_filter_still_scopes(tmp_path):
    """Passing an explicit project_path still filters to the matching project only."""
    from core.session_history.session_finder import find_all_sessions

    _write_claude_session(
        tmp_path, "E--demo-project-a", "sess-a", "2026-07-10T10:00:00.000Z"
    )
    _write_claude_session(
        tmp_path, "E--demo-project-b", "sess-b", "2026-07-11T10:00:00.000Z"
    )

    sessions = find_all_sessions("E:/demo/project-a", home=tmp_path, engine="claude")
    assert {s.session_id for s in sessions} == {"sess-a"}


def test_find_all_sessions_with_project_filter_scopes_dashed_project_name(tmp_path):
    """A real project whose name itself contains a dash (e.g.
    ``hearthstone-bot``) must not be confused with a same-prefix project
    whose name is one segment longer (e.g. ``hearthstone-bot-v2``)."""
    from core.session_history.session_finder import find_all_sessions

    _write_claude_session(
        tmp_path, "E--demo-hearthstone-bot", "sess-a", "2026-07-10T10:00:00.000Z"
    )
    _write_claude_session(
        tmp_path, "E--demo-hearthstone-bot-v2", "sess-b", "2026-07-11T10:00:00.000Z"
    )

    sessions = find_all_sessions(
        "E:/demo/hearthstone-bot", home=tmp_path, engine="claude"
    )
    assert {s.session_id for s in sessions} == {"sess-a"}


def test_find_all_sessions_deduplicates_resumed_provider_files(monkeypatch):
    """Resumed rollout files with one native ID appear as one conversation."""
    from core.session_history import session_finder

    less_complete = UnifiedSession(
        session_id="resumed-session",
        engine=EngineType.CODEX,
        started_at="2026-07-11T11:00:00.000Z",
        ended_at="2026-07-11T11:05:00.000Z",
        messages=[UnifiedMessage(role="user", content="first")],
        source_file="older.jsonl",
    )
    more_complete = UnifiedSession(
        session_id="resumed-session",
        engine=EngineType.CODEX,
        started_at="2026-07-11T10:00:00.000Z",
        ended_at="2026-07-11T11:04:00.000Z",
        messages=[
            UnifiedMessage(role="user", content="first"),
            UnifiedMessage(role="assistant", content="second"),
        ],
        source_file="complete.jsonl",
    )
    another_session = UnifiedSession(
        session_id="another-session",
        engine=EngineType.CODEX,
        started_at="2026-07-12T10:00:00.000Z",
        messages=[UnifiedMessage(role="user", content="newest")],
    )

    monkeypatch.setattr(
        session_finder,
        "find_codex_sessions",
        lambda project_path, home: [less_complete, more_complete, another_session],
    )

    sessions = session_finder.find_all_sessions(engine="codex")

    assert [session.session_id for session in sessions] == [
        "another-session",
        "resumed-session",
    ]
    assert sessions[1] is more_complete


# ─── Audit event tests ─────────────────────────────────────────────────


def test_build_audit_events_flattens_messages_and_tool_calls():
    from core.session_history.audit import build_audit_events

    session = UnifiedSession(
        session_id="s1",
        engine=EngineType.CLAUDE,
        project_path="E:/demo/test",
        title="Debug session",
        messages=[
            UnifiedMessage(
                role="user", content="hi", timestamp="2026-07-10T10:00:00.000Z"
            ),
            UnifiedMessage(
                role="assistant",
                content="doing it",
                timestamp="2026-07-10T10:00:05.000Z",
                tool_calls=[
                    ToolCallSummary(
                        name="read_file", args_preview="{}", result_preview="ok"
                    ),
                    ToolCallSummary(
                        name="write_file", args_preview="{}", result_preview="ok"
                    ),
                ],
            ),
        ],
    )

    events = build_audit_events([session])

    # 1 message event + 1 message event + 2 tool_call events = 4
    assert len(events) == 4
    message_events = [e for e in events if e["event_type"] == "message"]
    tool_call_events = [e for e in events if e["event_type"] == "tool_call"]
    assert len(message_events) == 2
    assert len(tool_call_events) == 2
    assert {e["tool_name"] for e in tool_call_events} == {"read_file", "write_file"}
    # Tool-call events inherit the parent message's timestamp
    assert all(e["timestamp"] == "2026-07-10T10:00:05.000Z" for e in tool_call_events)
    assert all(e["engine"] == "claude" for e in events)
    assert all(e["session_title"] == "Debug session" for e in events)


def test_build_audit_events_sorted_descending():
    from core.session_history.audit import build_audit_events

    session = UnifiedSession(
        session_id="s1",
        engine=EngineType.CLAUDE,
        messages=[
            UnifiedMessage(
                role="user", content="first", timestamp="2026-07-10T10:00:00.000Z"
            ),
            UnifiedMessage(
                role="assistant", content="second", timestamp="2026-07-11T10:00:00.000Z"
            ),
        ],
    )

    events = build_audit_events([session])
    assert [e["content_preview"] for e in events] == ["second", "first"]


def test_build_audit_events_empty_input():
    from core.session_history.audit import build_audit_events

    assert build_audit_events([]) == []


def test_claude_parser_drops_cli_synthetic_user_rows(tmp_path):
    """Claude Code's own CLI events are not conversation turns.

    Slash commands and friends are recorded as ordinary ``type: "user"`` rows.
    They were being carried into the unified session, and because they are
    often the *first* one, converted sessions ended up titled
    ``<command-name>/clear</command-name>`` and replayed a ``/clear`` at the top
    of the transcript in whichever engine they were opened.
    """
    rows = [
        {
            "type": "user",
            "message": {
                "role": "user",
                "content": (
                    "<command-name>/clear</command-name>\n"
                    "            <command-message>clear</command-message>"
                ),
            },
            "uuid": "u0",
            "timestamp": "2026-08-24T03:00:00.000Z",
            "cwd": "/home/cy/demo",
        },
        {
            "type": "user",
            "message": {
                "role": "user",
                "content": "<task-notification>done</task-notification>",
            },
            "uuid": "u1",
            "timestamp": "2026-08-24T03:00:01.000Z",
            "cwd": "/home/cy/demo",
        },
        {
            "type": "user",
            "message": {"role": "user", "content": "我们主分支是什么"},
            "uuid": "u2",
            "timestamp": "2026-08-24T03:00:02.000Z",
            "cwd": "/home/cy/demo",
        },
    ]
    path = tmp_path / "11111111-2222-3333-4444-555555555555.jsonl"
    path.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
        encoding="utf-8",
    )

    session = parse_claude_session(path)

    assert session is not None
    assert [m.content for m in session.messages] == ["我们主分支是什么"]
    assert session.generate_title() == "我们主分支是什么"


def test_codex_writer_reads_configured_model_provider(tmp_path):
    """The converted session records the provider the user actually runs."""
    from core.session_history.writers.codex_writer import _configured_model_provider

    codex_dir = tmp_path / ".codex"
    codex_dir.mkdir()
    (codex_dir / "config.toml").write_text(
        'model = "gpt-5.6-sol"\n'
        'model_provider = "river98"\n'
        "\n"
        "[model_providers.river98]\n"
        'model_provider = "ignored-inside-a-table"\n',
        encoding="utf-8",
    )

    assert _configured_model_provider(tmp_path) == "river98"


def test_codex_writer_model_provider_defaults_to_openai(tmp_path):
    """No config, or no key in it, falls back to the stock provider."""
    from core.session_history.writers.codex_writer import _configured_model_provider

    assert _configured_model_provider(tmp_path) == "openai"

    codex_dir = tmp_path / ".codex"
    codex_dir.mkdir()
    (codex_dir / "config.toml").write_text('model = "gpt-5.6-sol"\n', encoding="utf-8")
    assert _configured_model_provider(tmp_path) == "openai"


def test_codex_parser_does_not_double_assistant_turns(tmp_path):
    """Codex records one assistant turn twice; only one belongs in the session.

    ``event_msg``/``agent_message`` drives the UI and ``response_item``/
    ``message`` is the model transcript. Counting both showed every Codex reply
    twice in the Sessions list and duplicated it into every conversion.
    """
    rows = [
        {
            "timestamp": "2026-08-24T10:00:00.000Z",
            "type": "session_meta",
            "payload": {
                "id": "s1",
                "cwd": "/home/cy/demo",
                "timestamp": "2026-08-24T10:00:00.000Z",
            },
        },
        {
            "timestamp": "2026-08-24T10:00:01.000Z",
            "type": "event_msg",
            "payload": {"type": "user_message", "message": "后台启动"},
        },
        {
            "timestamp": "2026-08-24T10:00:02.000Z",
            "type": "response_item",
            "payload": {
                "type": "function_call",
                "name": "shell",
                "arguments": '{"cmd": "npm run dev"}',
                "call_id": "call_1",
            },
        },
        {
            "timestamp": "2026-08-24T10:00:03.000Z",
            "type": "event_msg",
            "payload": {"type": "agent_message", "message": "已启动", "phase": "final"},
        },
        {
            "timestamp": "2026-08-24T10:00:03.000Z",
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": "已启动"}],
                "phase": "final",
            },
        },
    ]
    path = tmp_path / "rollout-2026-08-24T10-00-00-s1.jsonl"
    path.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
        encoding="utf-8",
    )

    session = parse_codex_session(path)

    assert session is not None
    assert [(m.role, m.content) for m in session.messages] == [
        ("user", "后台启动"),
        ("assistant", "已启动"),
    ]
    # The surviving copy keeps the tool call, which only the response_item has.
    assert [tc.name for tc in session.messages[1].tool_calls] == ["shell"]

"""Tests for the /api/history/audit endpoint."""

import json
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from core.web.server import app


def _write_claude_session(
    base: Path, project_dir: str, session_id: str, timestamp: str, text: str
):
    session_dir = base / ".claude" / "projects" / project_dir
    session_dir.mkdir(parents=True)
    session_file = session_dir / f"{session_id}.jsonl"
    lines = [
        json.dumps(
            {
                "type": "user",
                "message": {"role": "user", "content": text},
                "uuid": "u1",
                "timestamp": timestamp,
                "sessionId": session_id,
            }
        ),
        json.dumps(
            {
                "type": "assistant",
                "message": {
                    "model": "claude-sonnet-4",
                    "role": "assistant",
                    "content": [
                        {"type": "text", "text": "ack"},
                        {
                            "type": "tool_use",
                            "id": "tool-1",
                            "name": "read_file",
                            "input": {"path": "src/main.py"},
                        },
                    ],
                },
                "uuid": "a1",
                "timestamp": timestamp,
                "sessionId": session_id,
            }
        ),
    ]
    session_file.write_text("\n".join(lines) + "\n", encoding="utf-8")


@pytest.fixture
def two_project_history(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    _write_claude_session(
        tmp_path,
        "E--demo-project-a",
        "sess-a",
        "2026-07-10T10:00:00.000Z",
        "hello from a",
    )
    _write_claude_session(
        tmp_path,
        "E--demo-project-b",
        "sess-b",
        "2026-07-11T10:00:00.000Z",
        "hello from b",
    )
    return tmp_path


@pytest.mark.asyncio
async def test_audit_events_across_all_projects(two_project_history):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        response = await ac.get("/api/history/audit")

    assert response.status_code == 200
    data = response.json()
    session_ids = {e["sessionId"] for e in data["events"]}
    assert session_ids == {"sess-a", "sess-b"}
    # message + tool_call events for each session's assistant turn, plus user turn
    event_types = {e["eventType"] for e in data["events"]}
    assert event_types == {"message", "tool_call"}
    # Most recent session's events should sort first
    assert data["events"][0]["sessionId"] == "sess-b"


@pytest.mark.asyncio
async def test_audit_events_filtered_by_project(two_project_history):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        response = await ac.get(
            "/api/history/audit", params={"project": "E:/demo/project-a"}
        )

    assert response.status_code == 200
    data = response.json()
    assert {e["sessionId"] for e in data["events"]} == {"sess-a"}


@pytest.mark.asyncio
async def test_audit_events_limit(two_project_history):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        response = await ac.get("/api/history/audit", params={"limit": 1})

    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 1
    assert len(data["events"]) == 1


@pytest.mark.asyncio
async def test_audit_events_since_filter(two_project_history):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        response = await ac.get(
            "/api/history/audit", params={"since": "2026-07-11T00:00:00.000Z"}
        )

    assert response.status_code == 200
    data = response.json()
    assert all(e["sessionId"] == "sess-b" for e in data["events"])
    assert len(data["events"]) > 0


@pytest.mark.asyncio
async def test_audit_events_no_sessions(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        response = await ac.get("/api/history/audit")

    assert response.status_code == 200
    assert response.json() == {"events": [], "count": 0}


@pytest.mark.asyncio
async def test_list_sessions_without_project_searches_all_projects(two_project_history):
    """ChatPage's 'continue session' picker relies on this (no project filter)."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        response = await ac.get("/api/history")

    assert response.status_code == 200
    data = response.json()
    session_ids = {s["sessionId"] for s in data["sessions"]}
    assert session_ids == {"sess-a", "sess-b"}


@pytest.mark.asyncio
async def test_continue_session_answers_with_a_browser_terminal_target(
    two_project_history, monkeypatch
):
    """POST /api/history/{engine}/{id}/continue no longer opens anything.

    It used to shell out to a GUI terminal on whatever machine ran the
    server -- useless from a remote browser, and a 503 on a headless host.
    The endpoint now validates and hands back what /api/pty/ws needs.
    """
    monkeypatch.setattr(
        "core.web.routers.history._resolve_history_workspace", lambda p: p
    )

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        response = await ac.post(
            "/api/history/claude/sess-a/continue",
            params={"project": "E:/demo/project-a"},
        )

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "engine": "claude",
        "sessionId": "sess-a",
        "project": "E:/demo/project-a",
    }


@pytest.mark.asyncio
async def test_continue_session_unknown_engine(two_project_history, monkeypatch):
    monkeypatch.setattr(
        "core.web.routers.history._resolve_history_workspace", lambda p: p
    )

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        response = await ac.post(
            "/api/history/unknown/sess-a/continue",
            params={"project": "E:/demo/project-a"},
        )

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_continue_session_not_found(two_project_history, monkeypatch):
    monkeypatch.setattr(
        "core.web.routers.history._resolve_history_workspace", lambda p: p
    )

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        response = await ac.post(
            "/api/history/claude/nope/continue",
            params={"project": "E:/demo/project-a"},
        )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_continue_session_in_an_unregistered_workspace(
    two_project_history, tmp_path
):
    """No entry needed on loopback -- see resolve_registered_workspace."""
    unreg = tmp_path / "unreg-workspace-continue"
    unreg.mkdir()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        response = await ac.post(
            "/api/history/claude/sess-a/continue",
            params={"project": str(unreg)},
        )

    # Past the registry, and now failing for the honest reason: that
    # directory has no such session, rather than "you did not register it".
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_list_sessions_still_scopes_to_project_when_given(two_project_history):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        response = await ac.get("/api/history", params={"project": "E:/demo/project-a"})

    assert response.status_code == 200
    data = response.json()
    assert {s["sessionId"] for s in data["sessions"]} == {"sess-a"}


@pytest.mark.asyncio
async def test_delete_session(two_project_history):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        # First verify it exists
        list_res = await ac.get("/api/history", params={"project": "E:/demo/project-a"})
        assert len(list_res.json()["sessions"]) == 1

        # Call delete
        del_res = await ac.delete(
            "/api/history/claude/sess-a", params={"project": "E:/demo/project-a"}
        )
        assert del_res.status_code == 200
        assert del_res.json()["status"] == "deleted"

        # Verify it no longer exists
        list_res2 = await ac.get(
            "/api/history", params={"project": "E:/demo/project-a"}
        )
        assert len(list_res2.json()["sessions"]) == 0


@pytest.mark.asyncio
async def test_delete_opencode_session(tmp_path, monkeypatch):
    import sqlite3

    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    db_dir = tmp_path / ".opencode"
    db_dir.mkdir(parents=True)
    db_path = db_dir / "opencode.db"

    # Initialize DB
    con = sqlite3.connect(str(db_path))
    with con:
        con.execute("""
            CREATE TABLE session (
                id TEXT PRIMARY KEY,
                directory TEXT,
                title TEXT,
                model TEXT,
                time_created INTEGER,
                time_updated INTEGER
            )
        """)
        con.execute("""
            CREATE TABLE message (
                id TEXT PRIMARY KEY,
                session_id TEXT,
                time_created INTEGER,
                data TEXT
            )
        """)
        con.execute("""
            CREATE TABLE part (
                id TEXT PRIMARY KEY,
                message_id TEXT,
                session_id TEXT,
                time_created INTEGER,
                data TEXT
            )
        """)

        # Populate dummy data
        con.execute(
            "INSERT INTO session VALUES (?, ?, ?, ?, ?, ?)",
            (
                "sess-opencode",
                "E:/demo/project-a",
                "OpenCode Session",
                '{"id": "opencode-model"}',
                1700000000000,
                1700000000000,
            ),
        )
        con.execute(
            "INSERT INTO message VALUES (?, ?, ?, ?)",
            ("msg-1", "sess-opencode", 1700000000000, '{"role": "user"}'),
        )
        con.execute(
            "INSERT INTO part VALUES (?, ?, ?, ?, ?)",
            (
                "part-1",
                "msg-1",
                "sess-opencode",
                1700000000000,
                '{"type": "text", "text": "hello"}',
            ),
        )
    con.close()

    # Verify they are in the DB
    con = sqlite3.connect(str(db_path))
    assert con.execute("SELECT count(*) FROM session").fetchone()[0] == 1
    assert con.execute("SELECT count(*) FROM message").fetchone()[0] == 1
    assert con.execute("SELECT count(*) FROM part").fetchone()[0] == 1
    con.close()

    # Call the DELETE endpoint via AsyncClient
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        # First verify it exists in list view
        list_res = await ac.get(
            "/api/history",
            params={"project": "E:/demo/project-a", "engine": "opencode"},
        )
        assert list_res.status_code == 200
        assert len(list_res.json()["sessions"]) == 1
        assert list_res.json()["sessions"][0]["sessionId"] == "sess-opencode"

        # Call delete
        del_res = await ac.delete(
            "/api/history/opencode/sess-opencode",
            params={"project": "E:/demo/project-a"},
        )
        assert del_res.status_code == 200
        assert del_res.json()["status"] == "deleted"

        # Verify it no longer exists in list view
        list_res2 = await ac.get(
            "/api/history",
            params={"project": "E:/demo/project-a", "engine": "opencode"},
        )
        assert len(list_res2.json()["sessions"]) == 0

    # Assert database file itself is intact
    assert db_path.exists()
    assert db_path.is_file()

    # Assert database tables are empty
    con = sqlite3.connect(str(db_path))
    assert (
        con.execute(
            "SELECT count(*) FROM session WHERE id = 'sess-opencode'"
        ).fetchone()[0]
        == 0
    )
    assert (
        con.execute(
            "SELECT count(*) FROM message WHERE session_id = 'sess-opencode'"
        ).fetchone()[0]
        == 0
    )
    assert (
        con.execute(
            "SELECT count(*) FROM part WHERE session_id = 'sess-opencode'"
        ).fetchone()[0]
        == 0
    )
    con.close()


@pytest.mark.asyncio
async def test_convert_session_success(two_project_history, monkeypatch):
    monkeypatch.setattr(
        "core.web.routers.history._resolve_history_workspace", lambda p: p
    )
    monkeypatch.setattr(
        "core.session_history.writers.write_session", lambda s, e: "new-id-123"
    )

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        res = await ac.post(
            "/api/history/convert",
            json={
                "sourceEngine": "claude",
                "sessionId": "sess-a",
                "targetEngine": "codex",
                "projectPath": "E:/demo/project-a",
            },
        )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert data["newSessionId"] == "new-id-123"


@pytest.mark.asyncio
async def test_convert_session_not_found(two_project_history, monkeypatch):
    monkeypatch.setattr(
        "core.web.routers.history._resolve_history_workspace", lambda p: p
    )
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        res = await ac.post(
            "/api/history/convert",
            json={
                "sourceEngine": "claude",
                "sessionId": "does-not-exist",
                "targetEngine": "codex",
                "projectPath": "E:/demo/project-a",
            },
        )
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_convert_session_in_an_unregistered_workspace(
    two_project_history, tmp_path
):
    unreg = tmp_path / "unreg-workspace-convert"
    unreg.mkdir()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        res = await ac.post(
            "/api/history/convert",
            json={
                "sourceEngine": "claude",
                "sessionId": "sess-a",
                "targetEngine": "codex",
                "projectPath": str(unreg),
            },
        )
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_convert_and_launch_success(two_project_history, monkeypatch):
    monkeypatch.setattr(
        "core.web.routers.history._resolve_history_workspace", lambda p: p
    )
    monkeypatch.setattr(
        "core.session_history.writers.write_session", lambda s, e: "new-id-456"
    )

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        res = await ac.post(
            "/api/history/convert-and-launch",
            json={
                "sourceEngine": "claude",
                "sessionId": "sess-a",
                "targetEngine": "opencode",
                "projectPath": "E:/demo/project-a",
            },
        )
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ready"
    assert body["newSessionId"] == "new-id-456"
    # The converted session is addressed the same way an existing one is, so
    # the caller opens one kind of terminal either way.
    assert body["engine"] == "opencode"
    assert body["sessionId"] == "new-id-456"
    assert body["project"] == "E:/demo/project-a"


@pytest.mark.asyncio
async def test_convert_and_launch_rejects_an_unusable_session_id(
    two_project_history, monkeypatch
):
    """A written id that would read as a CLI flag must not reach an argv."""
    monkeypatch.setattr(
        "core.web.routers.history._resolve_history_workspace", lambda p: p
    )
    monkeypatch.setattr(
        "core.session_history.writers.write_session", lambda s, e: "--resume-all"
    )

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        res = await ac.post(
            "/api/history/convert-and-launch",
            json={
                "sourceEngine": "claude",
                "sessionId": "sess-a",
                "targetEngine": "claude",
                "projectPath": "E:/demo/project-a",
            },
        )
    assert res.status_code == 500


@pytest.mark.asyncio
async def test_delete_session_invalid_source_file(two_project_history, monkeypatch):
    from core.session_history.models import EngineType, UnifiedSession

    # Mock find_session_by_id to return a session with an empty source_file
    dummy_session_empty = UnifiedSession(
        session_id="sess-empty",
        engine=EngineType.CLAUDE,
        project_path="E:/demo/project-a",
        source_file="",
    )

    # Mock find_session_by_id to return a session with an invalid source_file
    dummy_session_invalid = UnifiedSession(
        session_id="sess-invalid",
        engine=EngineType.CLAUDE,
        project_path="E:/demo/project-a",
        source_file="/nonexistent/path/to/file.jsonl",
    )

    import core.web.routers.history as history_router

    original_find = history_router.find_session_by_id

    def mock_find(session_id, engine, project):
        if session_id == "sess-empty":
            return dummy_session_empty
        if session_id == "sess-invalid":
            return dummy_session_invalid
        return original_find(session_id, engine, project)

    monkeypatch.setattr(history_router, "find_session_by_id", mock_find)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        # Delete empty source_file session
        res_empty = await ac.delete(
            "/api/history/claude/sess-empty", params={"project": "E:/demo/project-a"}
        )
        assert res_empty.status_code == 400
        assert "empty" in res_empty.json()["detail"]["error"]

        # Delete invalid/non-existent source_file session
        res_invalid = await ac.delete(
            "/api/history/claude/sess-invalid", params={"project": "E:/demo/project-a"}
        )
        assert res_invalid.status_code == 400
        assert "invalid" in res_invalid.json()["detail"]["error"]


def _write_claude_subagent(
    base: Path, project_dir: str, parent_session_id: str, agent_file: str, text: str
):
    """A subagent transcript, where Claude Code puts it: one level below its
    parent session, with rows that repeat the parent's sessionId."""
    subagents = base / ".claude" / "projects" / project_dir / parent_session_id
    subagents = subagents / "subagents"
    subagents.mkdir(parents=True)
    (subagents / f"{agent_file}.jsonl").write_text(
        json.dumps(
            {
                "type": "user",
                "message": {"role": "user", "content": text},
                "uuid": "u1",
                "timestamp": "2026-07-10T10:05:00.000Z",
                "sessionId": parent_session_id,
                "isSidechain": True,
            }
        )
        + "\n",
        encoding="utf-8",
    )


@pytest.fixture
def history_with_a_subagent(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    _write_claude_session(
        tmp_path,
        "E--demo-project-a",
        "sess-a",
        "2026-07-10T10:00:00.000Z",
        "hello from a",
    )
    _write_claude_subagent(
        tmp_path,
        "E--demo-project-a",
        "sess-a",
        "agent-abc123",
        "go review the frontend",
    )
    return tmp_path


@pytest.mark.asyncio
async def test_list_sessions_hides_subagent_runs(history_with_a_subagent):
    """A subagent run belongs to the session that spawned it; listing it
    alongside real sessions is what buried them in the first place."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        response = await ac.get("/api/history")

    assert response.status_code == 200
    data = response.json()
    assert [s["sessionId"] for s in data["sessions"]] == ["sess-a"]
    assert data["count"] == 1


@pytest.mark.asyncio
async def test_list_sessions_can_include_subagent_runs(history_with_a_subagent):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        response = await ac.get("/api/history", params={"include_subagents": "true"})

    assert response.status_code == 200
    data = response.json()
    by_id = {s["sessionId"]: s for s in data["sessions"]}
    assert set(by_id) == {"sess-a", "agent-abc123"}
    assert by_id["agent-abc123"]["parentSessionId"] == "sess-a"
    assert by_id["sess-a"]["parentSessionId"] == ""


def _write_freebuff_chat(base: Path, repo: str, chat_id: str, text: str) -> Path:
    """Writes one Freebuff conversation under ``base`` (a fake home)."""
    chat_dir = base / ".config" / "manicode" / "projects" / repo / "chats" / chat_id
    chat_dir.mkdir(parents=True)
    project_root = str(base / "work" / repo)
    (chat_dir / "chat-messages.json").write_text(
        json.dumps(
            [
                {
                    "id": "user-1786515103000",
                    "variant": "user",
                    "content": text,
                    "timestamp": "02:11 PM",
                }
            ]
        ),
        encoding="utf-8",
    )
    (chat_dir / "chat-meta.json").write_text(
        json.dumps({"messageCount": 1, "firstPrompt": text}), encoding="utf-8"
    )
    (chat_dir / "run-state.json").write_text(
        json.dumps(
            {
                "sessionState": {
                    "fileContext": {"projectRoot": project_root, "cwd": project_root},
                    "mainAgentState": {"agentType": "base3-free-deepseek-flash"},
                }
            }
        ),
        encoding="utf-8",
    )
    return chat_dir / "chat-messages.json"


@pytest.mark.asyncio
async def test_freebuff_session_list_continue_and_delete(tmp_path, monkeypatch):
    """freebuff 会话走完整的历史链路：列出（repo 名匹配）、恢复（继续目标是
    freebuff --continue <chat 目录名>）、删除（只允许删 ~/.config/manicode
    projects 内的文件）。"""
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    chat_id = "2026-08-12T05-10-04.784Z"
    _write_freebuff_chat(tmp_path, "CodeAgent", chat_id, "你浏览下我们项目")
    project = str(tmp_path / "work" / "CodeAgent")

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        # List, filtered to this checkout by its repo name.
        response = await ac.get(
            "/api/history", params={"project": project, "engine": "freebuff"}
        )
    assert response.status_code == 200
    sessions = response.json()["sessions"]
    assert len(sessions) == 1
    assert sessions[0]["sessionId"] == chat_id
    assert sessions[0]["engine"] == "freebuff"
    assert sessions[0]["projectPath"] == project

    monkeypatch.setattr(
        "core.web.routers.history._resolve_history_workspace", lambda p: p
    )
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        # Continue: the answer is a browser-terminal target for freebuff.
        cont = await ac.post(
            f"/api/history/freebuff/{chat_id}/continue",
            params={"project": project},
        )
        assert cont.status_code == 200
        assert cont.json() == {
            "status": "ready",
            "engine": "freebuff",
            "sessionId": chat_id,
            "project": project,
        }

        # Delete removes the transcript (the session id is the chat dir name).
        deleted = await ac.delete(
            f"/api/history/freebuff/{chat_id}", params={"project": project}
        )
        assert deleted.status_code == 200
        assert deleted.json()["status"] == "deleted"

        response = await ac.get(
            "/api/history", params={"project": project, "engine": "freebuff"}
        )
        assert response.json()["count"] == 0

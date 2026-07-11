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
    session_ids = {e["session_id"] for e in data["events"]}
    assert session_ids == {"sess-a", "sess-b"}
    # message + tool_call events for each session's assistant turn, plus user turn
    event_types = {e["event_type"] for e in data["events"]}
    assert event_types == {"message", "tool_call"}
    # Most recent session's events should sort first
    assert data["events"][0]["session_id"] == "sess-b"


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
    assert {e["session_id"] for e in data["events"]} == {"sess-a"}


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
    assert all(e["session_id"] == "sess-b" for e in data["events"])
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

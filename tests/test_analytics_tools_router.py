"""Tests for GET /api/analytics/tools -- the cross-engine tool ranking.

The counts come from ``core.session_history`` rather than the analytics
pipeline, because ``tool_calls`` only exists on the parsed sessions. Counting
across every engine at once is the part a single vendor CLI structurally
cannot do: each one only ever sees its own history.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.session_history.models import (
    EngineType,
    ToolCallSummary,
    UnifiedMessage,
    UnifiedSession,
)
from core.web.routers import analytics


def _session(
    engine: EngineType,
    tools: list[str],
    *,
    ended_at: str = "2026-08-24T10:00:00Z",
) -> UnifiedSession:
    return UnifiedSession(
        session_id=f"{engine.value}-1",
        engine=engine,
        project_path="/work/app",
        started_at=ended_at,
        ended_at=ended_at,
        messages=[
            UnifiedMessage(
                role="assistant",
                content="",
                tool_calls=[ToolCallSummary(name=name) for name in tools],
            )
        ],
    )


def _get(sessions: list[UnifiedSession], **params):
    app = FastAPI()
    app.include_router(analytics.router)
    with patch.object(analytics, "find_all_sessions", return_value=sessions):
        return TestClient(app).get("/api/analytics/tools", params=params)


def test_tools_are_ranked_by_call_count():
    response = _get(
        [
            _session(EngineType.CLAUDE, ["Bash", "Read", "Bash", "Edit"]),
            _session(EngineType.CODEX, ["Bash", "Read"]),
        ]
    )

    assert response.status_code == 200
    body = response.json()
    assert [tool["name"] for tool in body["tools"]] == ["Bash", "Read", "Edit"]
    assert [tool["count"] for tool in body["tools"]] == [3, 2, 1]
    assert body["totalCalls"] == 6
    assert body["sessions"] == 2


def test_each_tool_carries_its_per_engine_split():
    response = _get(
        [
            _session(EngineType.CLAUDE, ["Bash", "Bash"]),
            _session(EngineType.CODEX, ["Bash"]),
        ]
    )

    bash = response.json()["tools"][0]
    assert bash["byEngine"] == {"claude": 2, "codex": 1}


def test_unnamed_tool_calls_are_skipped():
    response = _get([_session(EngineType.CLAUDE, ["Bash", "", "   "])])

    body = response.json()
    assert [tool["name"] for tool in body["tools"]] == ["Bash"]
    assert body["totalCalls"] == 1


def test_days_window_drops_older_sessions():
    recent = datetime.now(UTC).isoformat()
    old = (datetime.now(UTC) - timedelta(days=30)).isoformat()

    response = _get(
        [
            _session(EngineType.CLAUDE, ["Bash"], ended_at=recent),
            _session(EngineType.CODEX, ["Grep"], ended_at=old),
        ],
        days=7,
    )

    body = response.json()
    assert [tool["name"] for tool in body["tools"]] == ["Bash"]
    assert body["sessions"] == 1


def test_a_session_with_an_unparseable_timestamp_is_kept():
    # Dropping it would silently understate the totals. An inflated window is
    # easier to notice than a quiet omission.
    response = _get(
        [_session(EngineType.CLAUDE, ["Bash"], ended_at="not-a-timestamp")],
        days=7,
    )

    assert response.json()["sessions"] == 1


def test_empty_history_returns_an_empty_ranking_not_an_error():
    response = _get([])

    assert response.status_code == 200
    assert response.json() == {
        "tools": [],
        "totalCalls": 0,
        "sessions": 0,
        "engines": {},
    }

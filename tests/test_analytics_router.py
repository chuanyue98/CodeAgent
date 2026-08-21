from __future__ import annotations

from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.web.routers import analytics


def _session(session_id: str, project_path: str) -> dict:
    return {
        "sessionId": session_id,
        "target": "claude",
        "projectPath": project_path,
        "inputTokens": 10,
        "outputTokens": 5,
        "cacheCreationTokens": 0,
        "cacheReadTokens": 0,
        "cost": 0.01,
        "lastActivity": "2026-08-21T10:00:00Z",
        "modelsUsed": ["claude-opus"],
        "modelBreakdowns": [],
    }


def _get(sessions: list[dict], **params):
    """Calls GET /api/analytics/sessions over a fixed analytics snapshot."""
    app = FastAPI()
    app.include_router(analytics.router)
    with patch.object(
        analytics, "get_analytics_data", return_value={"sessions": sessions}
    ):
        return TestClient(app).get("/api/analytics/sessions", params=params)


def test_sessions_returns_every_project_when_unfiltered():
    response = _get([_session("a", "/work/one"), _session("b", "/work/two")])

    assert response.status_code == 200
    assert {s["sessionId"] for s in response.json()} == {"a", "b"}


def test_sessions_filters_by_project():
    response = _get(
        [_session("a", "/work/one"), _session("b", "/work/two")],
        project="/work/one",
    )

    assert response.status_code == 200
    assert [s["sessionId"] for s in response.json()] == ["a"]


def test_sessions_project_match_ignores_separator_case_and_trailing_slash():
    response = _get(
        [_session("a", "E:\\demo\\App"), _session("b", "/work/two")],
        project="e:/demo/app/",
    )

    assert [s["sessionId"] for s in response.json()] == ["a"]


def test_sessions_filters_before_applying_limit():
    # A busy neighbouring project must not crowd the requested one out of the
    # window: filtering after slicing would return nothing here.
    sessions = [_session(f"noise-{i}", "/work/busy") for i in range(50)]
    sessions.append(_session("wanted", "/work/quiet"))

    response = _get(sessions, project="/work/quiet", limit=10)

    assert [s["sessionId"] for s in response.json()] == ["wanted"]


def test_sessions_unknown_project_returns_empty_list():
    response = _get([_session("a", "/work/one")], project="/nope")

    assert response.json() == []


def test_sessions_tolerates_records_without_a_project_path():
    sessions = [_session("a", "/work/one")]
    sessions.append({**_session("b", "/work/two"), "projectPath": None})

    assert [s["sessionId"] for s in _get(sessions, project="/work/one").json()] == ["a"]
    assert {s["sessionId"] for s in _get(sessions).json()} == {"a", "b"}

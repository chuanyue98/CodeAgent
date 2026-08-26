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


def _rows(response) -> list[dict]:
    """The page itself, out of the {sessions, nextCursor, total} envelope."""
    return response.json()["sessions"]


def test_sessions_returns_every_project_when_unfiltered():
    response = _get([_session("a", "/work/one"), _session("b", "/work/two")])

    assert response.status_code == 200
    assert {s["sessionId"] for s in _rows(response)} == {"a", "b"}


def test_sessions_filters_by_project():
    response = _get(
        [_session("a", "/work/one"), _session("b", "/work/two")],
        project="/work/one",
    )

    assert response.status_code == 200
    assert [s["sessionId"] for s in _rows(response)] == ["a"]


def test_sessions_project_match_ignores_separator_case_and_trailing_slash():
    response = _get(
        [_session("a", "E:\\demo\\App"), _session("b", "/work/two")],
        project="e:/demo/app/",
    )

    assert [s["sessionId"] for s in _rows(response)] == ["a"]


def test_sessions_filters_before_applying_limit():
    # A busy neighbouring project must not crowd the requested one out of the
    # window: filtering after slicing would return nothing here.
    sessions = [_session(f"noise-{i}", "/work/busy") for i in range(50)]
    sessions.append(_session("wanted", "/work/quiet"))

    response = _get(sessions, project="/work/quiet", limit=10)

    assert [s["sessionId"] for s in _rows(response)] == ["wanted"]


def test_sessions_unknown_project_returns_empty_list():
    response = _get([_session("a", "/work/one")], project="/nope")

    assert _rows(response) == []


def test_sessions_tolerates_records_without_a_project_path():
    sessions = [_session("a", "/work/one")]
    sessions.append({**_session("b", "/work/two"), "projectPath": None})

    assert [s["sessionId"] for s in _rows(_get(sessions, project="/work/one"))] == ["a"]
    assert {s["sessionId"] for s in _rows(_get(sessions))} == {"a", "b"}


def test_sessions_match_across_windows_extended_length_spellings():
    # codex records the working directory in Windows extended-length form,
    # while opencode and claude write the plain path. Before these were
    # canonicalized together, filtering Sessions by a workspace silently
    # dropped every codex run for that same directory.
    sessions = [
        _session("opencode", "E:/demo/CodeAgent"),
        _session("claude", r"E:\demo\CodeAgent"),
        _session("codex", r"\\?\E:\demo\CodeAgent"),
        _session("elsewhere", "E:/demo/other"),
    ]

    response = _get(sessions, project="E:/demo/CodeAgent")

    assert {s["sessionId"] for s in _rows(response)} == {"opencode", "claude", "codex"}


def test_sessions_match_when_the_filter_itself_is_extended_length():
    # The same has to hold in reverse: a workspace registered from a codex
    # session carries the prefix, and must still find the plain-path records.
    sessions = [
        _session("plain", "E:/demo/CodeAgent"),
        _session("elsewhere", "E:/demo/other"),
    ]

    response = _get(sessions, project=r"\\?\E:\demo\CodeAgent")

    assert [s["sessionId"] for s in _rows(response)] == ["plain"]


def test_sessions_match_unc_paths_across_spellings():
    sessions = [
        _session("extended", r"\\?\UNC\wsl.localhost\Ubuntu\home\cy\app"),
        _session("plain", "//wsl.localhost/Ubuntu/home/cy/app"),
    ]

    response = _get(sessions, project="//wsl.localhost/Ubuntu/home/cy/app")

    assert {s["sessionId"] for s in _rows(response)} == {"extended", "plain"}


def test_sessions_keep_distinct_projects_apart():
    # Stripping the prefix must not collapse genuinely different paths.
    sessions = [
        _session("a", r"\\?\E:\demo\CodeAgent"),
        _session("b", r"\\?\E:\demo\CodeAgentOther"),
    ]

    response = _get(sessions, project="E:/demo/CodeAgent")

    assert [s["sessionId"] for s in _rows(response)] == ["a"]


# ─── Paging and server-side search ────────────────────────────────────────
#
# The list was a bare array capped at whatever limit the caller hard-coded,
# so anything past that never reached the browser and every client-side
# filter ran against the truncated window.


def _dated_session(session_id: str, last_activity: str) -> dict:
    session = _session(session_id, "/work/one")
    session["lastActivity"] = last_activity
    return session


def test_sessions_envelope_reports_the_unpaged_total():
    response = _get(
        [_dated_session(str(i), f"2026-08-{i + 10}T10:00:00Z") for i in range(5)],
        limit=2,
    )

    body = response.json()
    assert len(body["sessions"]) == 2
    assert body["total"] == 5


def test_cursor_walks_the_whole_list_without_repeats():
    sessions = [_dated_session(str(i), f"2026-08-{i + 10}T10:00:00Z") for i in range(5)]

    seen: list[str] = []
    cursor = None
    for _ in range(5):
        params = {"limit": 2}
        if cursor:
            params["cursor"] = cursor
        body = _get(sessions, **params).json()
        seen.extend(s["sessionId"] for s in body["sessions"])
        cursor = body["nextCursor"]
        if cursor is None:
            break

    assert cursor is None
    # Newest first, every row exactly once.
    assert seen == ["4", "3", "2", "1", "0"]


def test_last_page_has_no_next_cursor():
    body = _get([_dated_session("a", "2026-08-21T10:00:00Z")], limit=10).json()

    assert body["nextCursor"] is None


def test_malformed_cursor_is_rejected():
    response = _get([_session("a", "/work/one")], cursor="not-base64!!")

    assert response.status_code == 400


def test_search_matches_the_session_id():
    response = _get(
        [_session("wanted", "/work/one"), _session("other", "/work/one")], search="want"
    )

    assert [s["sessionId"] for s in _rows(response)] == ["wanted"]


def test_search_matches_the_project_path():
    response = _get(
        [_session("a", "/work/alpha"), _session("b", "/work/beta")], search="ALPHA"
    )

    assert [s["sessionId"] for s in _rows(response)] == ["a"]


def test_search_narrows_the_total_too():
    body = _get(
        [_session("a", "/work/alpha"), _session("b", "/work/beta")], search="alpha"
    ).json()

    # Not the unfiltered count -- the UI shows this as "N sessions".
    assert body["total"] == 1

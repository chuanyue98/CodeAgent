from pathlib import Path
from unittest.mock import patch

import pytest

from core.analytics.aggregator import aggregate
from core.analytics.collectors.claude_collector import scan_claude_usage
from core.analytics.history import (
    append_history,
    get_last_timestamps,
    load_history,
    mark_backfill_done,
)
from core.analytics.models import RawUsageEntry
from core.analytics.service import (
    BACKFILL_VERSION,
    _collect_all,
    get_analytics_data,
)


@pytest.fixture
def mock_history_file(tmp_path):
    history_file = tmp_path / ".ca_analytics_history.jsonl"
    cache_file = tmp_path / ".ca_analytics_cache.json"
    # Redirect the disk cache too, or force_refresh tests write their mock
    # data into the developer's real ~/.ca_analytics_cache.json and the live
    # server then serves poisoned data for the cache TTL window.
    with (
        patch("core.analytics.history._history_path", return_value=history_file),
        patch("core.analytics.disk_cache._default_cache_path", return_value=cache_file),
    ):
        # Most tests assert the steady-state incremental path; the one-off
        # rescan after an upgrade has its own test and opts back in.
        mark_backfill_done(BACKFILL_VERSION)
        yield history_file


def test_aggregation_logic():
    entries = [
        RawUsageEntry(
            timestamp="2026-05-01T10:00:00Z",
            session_id="s1",
            model="gpt-4o",
            input_tokens=100,
            output_tokens=50,
            target="claude",
        ),
        RawUsageEntry(
            timestamp="2026-05-01T11:00:00Z",
            session_id="s1",
            model="gpt-4o",
            input_tokens=200,
            output_tokens=100,
            target="claude",
        ),
        RawUsageEntry(
            timestamp="2026-05-02T10:00:00Z",
            session_id="s2",
            model="hy3",
            input_tokens=500,
            output_tokens=200,
            target="codebuddy",
        ),
    ]

    result = aggregate(entries)

    assert result["summary"]["total_entries"] == 3
    assert result["summary"]["total_input_tokens"] == 800
    assert result["summary"]["total_output_tokens"] == 350
    assert len(result["daily"]) == 2
    assert result["daily"][0]["date"] == "2026-05-01"
    assert result["daily"][1]["date"] == "2026-05-02"
    assert len(result["sessions"]) == 2


def test_incremental_history(mock_history_file):
    entries = [
        RawUsageEntry(
            timestamp="2026-05-01T10:00:00Z",
            session_id="s1",
            model="gpt-4o",
            input_tokens=100,
            output_tokens=50,
            target="claude",
        )
    ]

    # Test append and load
    append_history(entries)
    loaded = load_history()
    assert len(loaded) == 1
    assert loaded[0].timestamp == "2026-05-01T10:00:00Z"

    # Test last timestamps
    last_ts = get_last_timestamps()
    assert last_ts["claude"] == "2026-05-01T10:00:00Z"

    # Append more
    new_entries = [
        RawUsageEntry(
            timestamp="2026-05-01T11:00:00Z",
            session_id="s1",
            model="gpt-4o",
            input_tokens=200,
            output_tokens=100,
            target="claude",
        )
    ]
    append_history(new_entries)
    assert len(load_history()) == 2
    assert get_last_timestamps()["claude"] == "2026-05-01T11:00:00Z"


@patch("core.analytics.service.scan_claude_usage")
@patch("core.analytics.service.scan_codex_usage")
@patch("core.analytics.service.scan_opencode_usage")
@patch("core.analytics.service.scan_codebuddy_usage", return_value=[])
def test_service_incremental_collection(
    mock_codebuddy, mock_opencode, mock_codex, mock_claude, mock_history_file
):
    # Setup initial history
    initial_entry = RawUsageEntry(
        timestamp="2026-05-01T10:00:00Z",
        session_id="s1",
        model="gpt-4o",
        input_tokens=100,
        output_tokens=50,
        target="claude",
    )
    append_history([initial_entry])

    # Mock collectors to return only NEW entries
    new_entry = RawUsageEntry(
        timestamp="2026-05-01T11:00:00Z",
        session_id="s1",
        model="gpt-4o",
        input_tokens=200,
        output_tokens=100,
        target="claude",
    )
    mock_claude.return_value = [new_entry]
    mock_codex.return_value = []
    mock_opencode.return_value = []

    # Run service
    data = get_analytics_data(force_refresh=True)

    # Verify results
    assert data["summary"]["total_entries"] == 2
    assert mock_claude.call_args[1]["since_timestamp"] == "2026-05-01T10:00:00Z"

    # Verify history file was updated
    assert len(load_history()) == 2


@patch("core.analytics.service.scan_claude_usage", return_value=[])
@patch("core.analytics.service.scan_opencode_usage", return_value=[])
@patch("core.analytics.service.scan_codebuddy_usage", return_value=[])
@patch("core.analytics.service.scan_codex_usage")
def test_codex_session_snapshot_is_replaced(
    mock_codex, _mock_codebuddy, _mock_opencode, _mock_claude, mock_history_file
):
    append_history(
        [
            RawUsageEntry(
                timestamp="2026-05-01T10:00:00Z",
                session_id="codex-session",
                model="gpt-5",
                input_tokens=82,
                output_tokens=18,
                target="codex",
            )
        ]
    )
    mock_codex.return_value = [
        RawUsageEntry(
            timestamp="2026-05-01T10:00:00Z",
            session_id="codex-session",
            model="gpt-5",
            input_tokens=164,
            output_tokens=36,
            target="codex",
        )
    ]

    entries = _collect_all()

    codex_entries = [entry for entry in entries if entry.target == "codex"]
    assert len(codex_entries) == 1
    assert codex_entries[0].input_tokens == 164
    assert len(load_history()) == 1


def test_claude_usage_prefers_exact_cwd_for_hyphenated_project(tmp_path):
    project_dir = tmp_path / ".claude" / "projects" / "-home-user-my-project"
    project_dir.mkdir(parents=True)
    (project_dir / "session.jsonl").write_text(
        '{"timestamp":"2026-07-10T10:00:00Z","cwd":"/home/user/my-project",'
        '"message":{"model":"claude-test","usage":{"input_tokens":10,'
        '"output_tokens":5}}}\n',
        encoding="utf-8",
    )

    entries = scan_claude_usage(home=tmp_path)

    assert len(entries) == 1
    assert entries[0].project_path == "/home/user/my-project"


def test_concurrent_cache_misses_collect_once(monkeypatch, tmp_path):
    """Six parallel endpoint hits on a cold cache must not run the collection
    pipeline six times over the same history files — the to_thread analytics
    routes made that the common case on the Usage page."""
    import threading
    from concurrent.futures import ThreadPoolExecutor

    import core.analytics.service as service

    calls = {"collect": 0}
    lock = threading.Lock()

    def fake_collect():
        with lock:
            calls["collect"] += 1
        return []

    monkeypatch.setattr(service, "_collect_all", fake_collect)
    monkeypatch.setattr(service, "_build_engine_summary", lambda entries: [])
    monkeypatch.setattr(service, "_build_model_summary", lambda entries: [])
    # Real roundtrip semantics: save persists, load reads it back — the
    # double-check inside the lock only collapses concurrent misses if the
    # cache actually answers after the first collector finishes.
    cache: dict = {}
    monkeypatch.setattr(
        service, "save_cache", lambda data: cache.__setitem__("data", data)
    )
    monkeypatch.setattr(service, "load_cache", lambda *a, **k: cache.get("data"))

    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(lambda _: service.get_analytics_data(), range(6)))

    assert len(results) == 6
    assert calls["collect"] == 1


def test_codebuddy_collector_extracts_usage(tmp_path):
    """CodeBuddy's providerData.usage maps onto RawUsageEntry correctly."""
    import json

    from core.analytics.collectors.codebuddy_collector import scan_codebuddy_usage

    project_dir = tmp_path / ".codebuddy" / "projects" / "e-demo-CodeAgent"
    project_dir.mkdir(parents=True)
    rows = [
        {
            "type": "message",
            "role": "user",
            "timestamp": 1787548456532,
            "cwd": "e:\\demo\\CodeAgent",
            "content": [{"type": "input_text", "text": "你好"}],
        },
        {
            "type": "message",
            "role": "assistant",
            "status": "completed",
            "timestamp": 1787548459000,
            "cwd": "e:\\demo\\CodeAgent",
            "providerData": {
                "model": "hy3",
                "usage": {
                    "requests": 1,
                    "inputTokens": 25949,
                    "outputTokens": 50,
                    "totalTokens": 25999,
                    "inputTokensDetails": [{"cached_tokens": 384}],
                },
            },
            "content": [{"type": "output_text", "text": "你好！"}],
        },
        # No usage block → skipped.
        {
            "type": "message",
            "role": "assistant",
            "status": "completed",
            "timestamp": 1787548460000,
            "cwd": "e:\\demo\\CodeAgent",
            "providerData": {"model": "hy3"},
            "content": [{"type": "output_text", "text": "ok"}],
        },
    ]
    with (project_dir / "sess-1.jsonl").open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    entries = scan_codebuddy_usage(home=tmp_path)

    assert len(entries) == 1
    entry = entries[0]
    assert entry.target == "codebuddy"
    assert entry.session_id == "sess-1"
    assert entry.model == "hy3"
    assert entry.input_tokens == 25949
    assert entry.output_tokens == 50
    assert entry.cache_read_tokens == 384
    assert entry.project_path == "e:\\demo\\CodeAgent"
    # Epoch-ms converted to ISO 8601 (string-comparable for incremental scans).
    assert entry.timestamp.startswith("2026-")
    assert "T" in entry.timestamp


def test_codebuddy_collector_incremental_skips_older(tmp_path):
    import json

    from core.analytics.collectors.codebuddy_collector import scan_codebuddy_usage

    project_dir = tmp_path / ".codebuddy" / "projects" / "e-demo-CodeAgent"
    project_dir.mkdir(parents=True)
    with (project_dir / "sess-1.jsonl").open("w", encoding="utf-8") as f:
        f.write(
            json.dumps(
                {
                    "type": "message",
                    "role": "assistant",
                    "timestamp": 1787548459000,
                    "cwd": "e:\\demo\\CodeAgent",
                    "providerData": {
                        "model": "hy3",
                        "usage": {"inputTokens": 10, "outputTokens": 5},
                    },
                    "content": [{"type": "output_text", "text": "x"}],
                }
            )
            + "\n"
        )

    all_entries = scan_codebuddy_usage(home=tmp_path)
    assert len(all_entries) == 1
    # With a since_timestamp at/after the entry's time, nothing new is returned.
    assert (
        scan_codebuddy_usage(home=tmp_path, since_timestamp=all_entries[0].timestamp)
        == []
    )


@patch("core.analytics.service.scan_claude_usage", return_value=[])
@patch("core.analytics.service.scan_codex_usage", return_value=[])
@patch("core.analytics.service.scan_opencode_usage", return_value=[])
@patch("core.analytics.service.scan_codebuddy_usage", return_value=[])
def test_collect_all_purges_removed_targets(
    _mock_codebuddy,
    _mock_opencode,
    _mock_codex,
    _mock_claude,
    mock_history_file,
):
    """Stale trae/workbuddy snapshots are dropped from the history store."""
    append_history(
        [
            RawUsageEntry(
                timestamp="2026-05-01T10:00:00Z",
                session_id="wb-1",
                model="hy3",
                input_tokens=100,
                output_tokens=50,
                target="workbuddy",
            ),
            RawUsageEntry(
                timestamp="2026-05-01T10:00:00Z",
                session_id="trae-1",
                model="hy3",
                input_tokens=100,
                output_tokens=50,
                target="trae",
            ),
            RawUsageEntry(
                timestamp="2026-05-01T10:00:00Z",
                session_id="claude-1",
                model="gpt-4o",
                input_tokens=100,
                output_tokens=50,
                target="claude",
            ),
        ]
    )

    entries = _collect_all()

    assert {e.target for e in entries} == {"claude"}
    assert {e.target for e in load_history()} == {"claude"}


def test_subagent_runs_roll_up_into_the_session_that_spawned_them():
    entries = [
        RawUsageEntry(
            timestamp="2026-08-01T10:00:00Z",
            session_id="parent",
            model="claude-test",
            input_tokens=100,
            output_tokens=10,
            target="claude",
        ),
        RawUsageEntry(
            timestamp="2026-08-01T11:00:00Z",
            session_id="child",
            model="claude-test",
            input_tokens=40,
            output_tokens=4,
            target="claude",
            parent_session_id="parent",
            agent="explore",
        ),
    ]

    result = aggregate(entries)

    assert result["summary"]["session_count"] == 1
    (session,) = result["sessions"]
    assert session["sessionId"] == "parent"
    # Rolled totals answer "what did this piece of work cost"...
    assert session["inputTokens"] == 140
    # ...while `own` keeps the main thread's share addressable.
    assert session["own"]["inputTokens"] == 100
    assert [s["sessionId"] for s in session["subtasks"]] == ["child"]
    assert session["subtasks"][0]["agent"] == "explore"
    # The parent's last message predates its subagent's; sorting on the
    # parent's own timestamp would file the session before work it contains.
    assert session["lastActivity"] == "2026-08-01T11:00:00Z"


def test_a_subagent_whose_parent_is_gone_stays_at_top_level():
    """The engine prunes transcripts; the archive keeps the usage rows.

    Filing such a row under a parent that no longer exists would drop it out
    of the list -- and its cost out of every per-session figure with it.
    """
    entries = [
        RawUsageEntry(
            timestamp="2026-08-01T10:00:00Z",
            session_id="orphan",
            model="claude-test",
            input_tokens=7,
            output_tokens=1,
            target="claude",
            parent_session_id="pruned",
            agent="explore",
        ),
    ]

    result = aggregate(entries)

    (session,) = result["sessions"]
    assert session["sessionId"] == "orphan"
    assert session["parentSessionId"] == "pruned"


def test_a_parent_cycle_does_not_swallow_the_sessions():
    entries = [
        RawUsageEntry(
            timestamp="2026-08-01T10:00:00Z",
            session_id="a",
            model="claude-test",
            input_tokens=1,
            output_tokens=1,
            target="claude",
            parent_session_id="b",
        ),
        RawUsageEntry(
            timestamp="2026-08-01T10:00:01Z",
            session_id="b",
            model="claude-test",
            input_tokens=1,
            output_tokens=1,
            target="claude",
            parent_session_id="a",
        ),
    ]

    result = aggregate(entries)

    assert {s["sessionId"] for s in result["sessions"]} == {"a", "b"}


def test_claude_collector_reads_subagent_transcripts(tmp_path):
    project_dir = tmp_path / ".claude" / "projects" / "-home-user-app"
    subagents = project_dir / "parent-session" / "subagents"
    subagents.mkdir(parents=True)
    (project_dir / "parent-session.jsonl").write_text(
        '{"timestamp":"2026-08-01T10:00:00Z","cwd":"/home/user/app",'
        '"message":{"model":"claude-test","usage":{"input_tokens":10,'
        '"output_tokens":5}}}\n',
        encoding="utf-8",
    )
    # Subagent rows repeat the parent's sessionId, so only the file stem tells
    # two subagents of one session apart.
    (subagents / "agent-abc123.jsonl").write_text(
        '{"timestamp":"2026-08-01T10:05:00Z","cwd":"/home/user/app",'
        '"sessionId":"parent-session","isSidechain":true,'
        '"message":{"model":"claude-test","usage":{"input_tokens":40,'
        '"output_tokens":2}}}\n',
        encoding="utf-8",
    )

    entries = scan_claude_usage(home=tmp_path)

    by_session = {e.session_id: e for e in entries}
    assert set(by_session) == {"parent-session", "agent-abc123"}
    assert by_session["agent-abc123"].parent_session_id == "parent-session"
    assert by_session["parent-session"].parent_session_id == ""


@patch("core.analytics.service.scan_claude_usage")
@patch("core.analytics.service.scan_codex_usage", return_value=[])
@patch("core.analytics.service.scan_opencode_usage", return_value=[])
@patch("core.analytics.service.scan_codebuddy_usage", return_value=[])
def test_the_first_collection_after_an_upgrade_rescans_in_full(
    _mock_codebuddy, _mock_opencode, _mock_codex, mock_claude, mock_history_file
):
    """Subagent transcripts were invisible to every earlier scan, so the
    records that first become readable are older than the watermark. Without a
    full pass they would never be collected at all."""
    Path(mock_history_file).parent.joinpath(".ca_analytics_state.json").unlink(
        missing_ok=True
    )
    append_history(
        [
            RawUsageEntry(
                timestamp="2026-05-02T10:00:00Z",
                session_id="parent",
                model="claude-test",
                input_tokens=100,
                output_tokens=50,
                target="claude",
            )
        ]
    )
    # Older than the watermark above, and only now readable.
    mock_claude.return_value = [
        RawUsageEntry(
            timestamp="2026-05-01T10:00:00Z",
            session_id="agent-abc123",
            model="claude-test",
            input_tokens=10,
            output_tokens=5,
            target="claude",
            parent_session_id="parent",
        )
    ]

    entries = _collect_all()

    assert mock_claude.call_args[1]["since_timestamp"] == ""
    assert {e.session_id for e in entries} == {"parent", "agent-abc123"}
    # The pre-existing row survives -- its transcript may be long gone.
    assert len(load_history()) == 2

    # And the rebuild happens once: the next collection is incremental again.
    mock_claude.return_value = []
    _collect_all()
    assert mock_claude.call_args[1]["since_timestamp"] == "2026-05-02T10:00:00Z"

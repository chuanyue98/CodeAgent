from unittest.mock import patch

import pytest

from core.analytics.aggregator import aggregate
from core.analytics.collectors.claude_collector import scan_claude_usage
from core.analytics.history import append_history, get_last_timestamps, load_history
from core.analytics.models import RawUsageEntry
from core.analytics.service import _collect_all, get_analytics_data


@pytest.fixture
def mock_history_file(tmp_path):
    history_file = tmp_path / ".ca_analytics_history.jsonl"
    with patch("core.analytics.history._history_path", return_value=history_file):
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
            model="gemini-1.5-pro",
            input_tokens=500,
            output_tokens=200,
            target="gemini",
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
@patch("core.analytics.service.scan_gemini_usage")
@patch("core.analytics.service.scan_codex_usage")
@patch("core.analytics.service.scan_opencode_usage")
def test_service_incremental_collection(
    mock_opencode, mock_codex, mock_gemini, mock_claude, mock_history_file
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
    mock_gemini.return_value = []
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
@patch("core.analytics.service.scan_gemini_usage", return_value=[])
@patch("core.analytics.service.scan_opencode_usage", return_value=[])
@patch("core.analytics.service.scan_codex_usage")
def test_codex_session_snapshot_is_replaced(
    mock_codex, _mock_opencode, _mock_gemini, _mock_claude, mock_history_file
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

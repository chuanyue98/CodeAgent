"""``ca switch`` and the session selector behind it."""

from unittest.mock import MagicMock, patch

import pytest

import ca_launcher
from core.cli.session_select import SessionSelectorError, resolve_session
from core.session_history.models import EngineType, UnifiedMessage, UnifiedSession


def _session(session_id: str, engine: EngineType, started_at: str) -> UnifiedSession:
    return UnifiedSession(
        session_id=session_id,
        engine=engine,
        project_path="/proj",
        started_at=started_at,
        messages=[UnifiedMessage(role="user", content="hi")],
    )


@pytest.fixture
def sessions():
    """Newest first, matching what find_all_sessions returns."""
    return [
        _session("newest", EngineType.CLAUDE, "2026-08-27T10:00:00"),
        _session("middle", EngineType.OPENCODE, "2026-08-26T10:00:00"),
        _session("oldest", EngineType.CODEX, "2026-08-25T10:00:00"),
    ]


@pytest.fixture
def find_all(sessions):
    with patch(
        "core.cli.session_select.find_all_sessions", return_value=sessions
    ) as mock:
        yield mock


def test_no_selector_takes_the_most_recent_session(find_all):
    assert resolve_session(None, "/proj").session_id == "newest"


def test_a_bare_number_is_the_index_ca_history_printed(find_all):
    assert resolve_session("2", "/proj").session_id == "middle"


def test_a_session_id_resolves_to_that_session(find_all):
    assert resolve_session("oldest", "/proj").session_id == "oldest"


def test_index_past_the_end_names_the_actual_count(find_all):
    with pytest.raises(SessionSelectorError) as excinfo:
        resolve_session("4", "/proj")
    assert excinfo.value.message_key == "select.index_out_of_range"
    assert excinfo.value.fields == {"index": 4, "count": 3}


def test_unmatched_selector_reports_not_found(find_all):
    with pytest.raises(SessionSelectorError) as excinfo:
        resolve_session("no-such-id", "/proj")
    assert excinfo.value.message_key == "select.not_found"


def test_empty_project_points_at_starting_a_session():
    with patch("core.cli.session_select.find_all_sessions", return_value=[]):
        with pytest.raises(SessionSelectorError) as excinfo:
            resolve_session(None, "/proj")
    assert excinfo.value.message_key == "select.no_sessions"


def test_engine_filter_reaches_the_finder(find_all):
    resolve_session(None, "/proj", engine="codex")
    assert find_all.call_args.kwargs["engine"] == "codex"


def _run_switch(monkeypatch, argv):
    monkeypatch.setattr("sys.argv", ["ca_launcher.py", "switch", *argv])
    return ca_launcher.main()


def test_switch_converts_then_launches_the_target_engine(monkeypatch, capsys):
    source = _session("src-id", EngineType.CLAUDE, "2026-08-27T10:00:00")
    completed = MagicMock(returncode=0)

    with patch("core.cli.commands.switch.resolve_session", return_value=source):
        with patch(
            "core.session_history.writers.write_session", return_value="new-id"
        ) as write:
            with patch(
                "core.cli.commands.switch.subprocess.run", return_value=completed
            ) as run:
                assert _run_switch(monkeypatch, ["codex"]) == 0

    write.assert_called_once_with(source, "codex")
    assert run.call_args.args[0] == ["codex", "resume", "new-id"]
    out = capsys.readouterr().out
    assert "claude -> codex" in out
    assert "new-id" in out


def test_switching_to_the_engine_it_is_already_in_does_not_fork_a_copy(
    monkeypatch, capsys
):
    source = _session("src-id", EngineType.CODEX, "2026-08-27T10:00:00")
    completed = MagicMock(returncode=0)

    with patch("core.cli.commands.switch.resolve_session", return_value=source):
        with patch("core.session_history.writers.write_session") as write:
            with patch(
                "core.cli.commands.switch.subprocess.run", return_value=completed
            ) as run:
                assert _run_switch(monkeypatch, ["codex"]) == 0

    write.assert_not_called()
    assert run.call_args.args[0] == ["codex", "resume", "src-id"]
    assert "Already a codex session" in capsys.readouterr().out


def test_no_launch_converts_and_prints_the_command_without_running_it(
    monkeypatch, capsys
):
    source = _session("src-id", EngineType.CLAUDE, "2026-08-27T10:00:00")

    with patch("core.cli.commands.switch.resolve_session", return_value=source):
        with patch("core.session_history.writers.write_session", return_value="new-id"):
            with patch("core.cli.commands.switch.subprocess.run") as run:
                assert _run_switch(monkeypatch, ["codex", "--no-launch"]) == 0

    run.assert_not_called()
    assert "codex resume new-id" in capsys.readouterr().out


def test_unknown_target_engine_lists_the_known_ones(monkeypatch, capsys):
    assert _run_switch(monkeypatch, ["gpt5"]) == 1
    out = capsys.readouterr().out
    assert "Unknown engine: gpt5" in out
    assert "codex" in out


def test_a_missing_engine_cli_still_reports_the_conversion_succeeded(
    monkeypatch, capsys
):
    source = _session("src-id", EngineType.CLAUDE, "2026-08-27T10:00:00")

    with patch("core.cli.commands.switch.resolve_session", return_value=source):
        with patch("core.session_history.writers.write_session", return_value="new-id"):
            with patch(
                "core.cli.commands.switch.subprocess.run", side_effect=FileNotFoundError
            ):
                assert _run_switch(monkeypatch, ["codex"]) == 1

    out = capsys.readouterr().out
    assert "was converted" in out
    assert "codex resume new-id" in out

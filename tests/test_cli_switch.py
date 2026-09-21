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
    """Newest first, matching what ``ca history`` prints."""
    return [
        _session("newest", EngineType.CLAUDE, "2026-08-27T10:00:00"),
        _session("middle", EngineType.OPENCODE, "2026-08-26T10:00:00"),
        _session("oldest", EngineType.CODEX, "2026-08-25T10:00:00"),
    ]


@pytest.fixture
def find_all(sessions):
    """打在仓储层：先给摘要列表供选择，再按 id 取完整会话。"""
    summaries = [s.to_summary_dict() for s in sessions]
    by_id = {s.session_id: s for s in sessions}
    with patch(
        "core.session_history.repository.list_summaries", return_value=summaries
    ) as list_mock:
        with patch(
            "core.session_history.repository.get_full",
            side_effect=lambda engine, session_id, project=None: by_id.get(session_id),
        ):
            yield list_mock


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
    with patch("core.session_history.repository.list_summaries", return_value=[]):
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


def _run_cli(monkeypatch, argv):
    monkeypatch.setattr("sys.argv", ["ca_launcher.py", *argv])
    return ca_launcher.main()


def test_switch_dash_s_shorthand_routes_to_switch(monkeypatch, capsys):
    source = _session("src-id", EngineType.CLAUDE, "2026-08-27T10:00:00")
    completed = MagicMock(returncode=0)

    with patch("core.cli.commands.switch.resolve_session", return_value=source):
        with patch("core.session_history.writers.write_session", return_value="new-id"):
            with patch(
                "core.cli.commands.switch.subprocess.run", return_value=completed
            ) as run:
                assert _run_cli(monkeypatch, ["-s", "codex"]) == 0

    assert run.call_args.args[0] == ["codex", "resume", "new-id"]


def test_switch_dash_s_with_selector(monkeypatch, capsys):
    source = _session("src-id", EngineType.CLAUDE, "2026-08-27T10:00:00")
    completed = MagicMock(returncode=0)

    with patch(
        "core.cli.commands.switch.resolve_session", return_value=source
    ) as mock_resolve:
        with patch("core.session_history.writers.write_session", return_value="new-id"):
            with patch(
                "core.cli.commands.switch.subprocess.run", return_value=completed
            ):
                assert _run_cli(monkeypatch, ["-s", "codex", "2"]) == 0

    mock_resolve.assert_called_once()
    assert mock_resolve.call_args.args[0] == "2"


def test_switch_s_subcommand_routes_to_switch(monkeypatch, capsys):
    source = _session("src-id", EngineType.CLAUDE, "2026-08-27T10:00:00")
    completed = MagicMock(returncode=0)

    with patch("core.cli.commands.switch.resolve_session", return_value=source):
        with patch("core.session_history.writers.write_session", return_value="new-id"):
            with patch(
                "core.cli.commands.switch.subprocess.run", return_value=completed
            ):
                assert _run_cli(monkeypatch, ["s", "codex"]) == 0


def test_interactive_switch_shows_preview_and_confirms_default_with_enter(
    monkeypatch, capsys, sessions
):
    summaries = [s.to_summary_dict() for s in sessions]
    completed = MagicMock(returncode=0)

    with patch("sys.stdin.isatty", return_value=True):
        with patch("builtins.input", return_value=""):  # Press Enter for default [1]
            with patch(
                "core.session_history.repository.list_summaries",
                return_value=summaries,
            ):
                with patch(
                    "core.session_history.repository.get_full",
                    return_value=sessions[0],
                ):
                    with patch(
                        "core.session_history.writers.write_session",
                        return_value="new-id",
                    ):
                        with patch(
                            "core.cli.commands.switch.subprocess.run",
                            return_value=completed,
                        ) as run:
                            assert _run_cli(monkeypatch, ["-s", "codex"]) == 0

    out = capsys.readouterr().out
    assert "[ 1]" in out
    assert "default" in out or "默认" in out
    assert run.call_args.args[0] == ["codex", "resume", "new-id"]


def test_interactive_switch_picks_another_session_by_index(
    monkeypatch, capsys, sessions
):
    summaries = [s.to_summary_dict() for s in sessions]
    completed = MagicMock(returncode=0)

    with patch("sys.stdin.isatty", return_value=True):
        with patch("builtins.input", return_value="2"):  # Pick #2 (middle: opencode)
            with patch(
                "core.session_history.repository.list_summaries",
                return_value=summaries,
            ):
                with patch(
                    "core.session_history.repository.get_full",
                    return_value=sessions[1],
                ):
                    with patch(
                        "core.session_history.writers.write_session",
                        return_value="new-id",
                    ):
                        with patch(
                            "core.cli.commands.switch.subprocess.run",
                            return_value=completed,
                        ) as run:
                            assert _run_cli(monkeypatch, ["-s", "codex"]) == 0

    out = capsys.readouterr().out
    assert "opencode -> codex" in out
    assert run.call_args.args[0] == ["codex", "resume", "new-id"]


def test_interactive_switch_quit(monkeypatch, capsys, sessions):
    summaries = [s.to_summary_dict() for s in sessions]

    with patch("sys.stdin.isatty", return_value=True):
        with patch("builtins.input", return_value="q"):
            with patch(
                "core.session_history.repository.list_summaries",
                return_value=summaries,
            ):
                assert _run_cli(monkeypatch, ["-s", "codex"]) == 0


def test_interactive_bare_switch_prompts_for_source_and_target_engine(
    monkeypatch, capsys, sessions
):
    summaries = [s.to_summary_dict() for s in sessions]
    completed = MagicMock(returncode=0)

    # First input: "" (confirm default session [1], which is CLAUDE)
    # Second input: "1" (select first target engine in list, which is codex)
    inputs = iter(["", "1"])

    with patch("sys.stdin.isatty", return_value=True):
        with patch("builtins.input", side_effect=lambda *args, **kwargs: next(inputs)):
            with patch(
                "core.session_history.repository.list_summaries",
                return_value=summaries,
            ):
                with patch(
                    "core.session_history.repository.get_full",
                    return_value=sessions[0],
                ):
                    with patch(
                        "core.session_history.writers.write_session",
                        return_value="new-id",
                    ):
                        with patch(
                            "core.cli.commands.switch.subprocess.run",
                            return_value=completed,
                        ) as run:
                            assert _run_cli(monkeypatch, ["-s"]) == 0

    out = capsys.readouterr().out
    assert "codex" in out
    assert run.call_args.args[0] == ["codex", "resume", "new-id"]


def test_noninteractive_bare_switch_requires_target_engine(monkeypatch, capsys):
    with patch("sys.stdin.isatty", return_value=False):
        assert _run_cli(monkeypatch, ["-s"]) == 1

    out = capsys.readouterr().out
    assert "Target engine is required" in out or "非交互模式下必须指定目标引擎" in out


def test_bare_switch_validates_target_before_reading_sessions(monkeypatch, capsys):
    """缺少 target_engine 时不能先去读会话。

    在没有任何会话历史的环境（CI / 新机器 / 容器）里，先读会话会抛出
    "No sessions found" 并掩盖真正的原因：用户只是漏了目标引擎。这里用
    抛错的桩固化顺序——一旦 resolve_session 被调用，本用例立刻失败。
    """
    with patch("sys.stdin.isatty", return_value=False):
        with patch(
            "core.cli.commands.switch.resolve_session",
            side_effect=AssertionError("不应在 target_engine 校验之前读取会话"),
        ):
            assert _run_cli(monkeypatch, ["-s"]) == 1

    out = capsys.readouterr().out
    assert "Target engine is required" in out or "非交互模式下必须指定目标引擎" in out


def test_switch_yes_flag_skips_prompt(monkeypatch, capsys, sessions):
    completed = MagicMock(returncode=0)

    with patch("sys.stdin.isatty", return_value=True):
        with patch(
            "builtins.input",
            side_effect=AssertionError("Should not prompt with -y"),
        ):
            with patch(
                "core.cli.commands.switch.resolve_session",
                return_value=sessions[0],
            ):
                with patch(
                    "core.session_history.writers.write_session",
                    return_value="new-id",
                ):
                    with patch(
                        "core.cli.commands.switch.subprocess.run",
                        return_value=completed,
                    ):
                        assert _run_cli(monkeypatch, ["-s", "codex", "-y"]) == 0

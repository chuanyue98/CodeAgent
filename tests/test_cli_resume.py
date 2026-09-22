"""``ca -r`` and ``ca resume`` CLI tests."""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

import ca_launcher
from core.cli.commands.resume import format_relative_time
from core.session_history.models import EngineType, UnifiedMessage, UnifiedSession


def _session(
    session_id: str,
    engine: EngineType,
    started_at: str,
    title: str = "",
) -> UnifiedSession:
    return UnifiedSession(
        session_id=session_id,
        engine=engine,
        project_path="/proj",
        started_at=started_at,
        title=title,
        messages=[UnifiedMessage(role="user", content="hi")],
    )


@pytest.fixture
def mock_sessions():
    """Newest first, across multiple engines."""
    now = datetime.now(UTC)
    return [
        _session(
            "ses-claude-1",
            EngineType.CLAUDE,
            (now - timedelta(minutes=5)).isoformat(),
            title="Claude Task",
        ),
        _session(
            "ses-codex-2",
            EngineType.CODEX,
            (now - timedelta(hours=2)).isoformat(),
            title="Codex Task",
        ),
        _session(
            "ses-opencode-3",
            EngineType.OPENCODE,
            (now - timedelta(days=1)).isoformat(),
            title="OpenCode Task",
        ),
    ]


@pytest.fixture
def find_all(mock_sessions):
    summaries = [s.to_summary_dict() for s in mock_sessions]
    by_id = {s.session_id: s for s in mock_sessions}
    with patch(
        "core.session_history.repository.list_summaries", return_value=summaries
    ) as list_mock:
        with patch(
            "core.session_history.repository.get_full",
            side_effect=lambda engine, session_id, project=None: by_id.get(session_id),
        ):
            yield list_mock


def _run_cli(monkeypatch, argv):
    monkeypatch.setattr("sys.argv", ["ca_launcher.py", *argv])
    return ca_launcher.main()


# ── Relative time formatting ──────────────────────────────────────────────────


def test_format_relative_time_units():
    now = datetime.now(UTC)
    assert format_relative_time("") == "-"
    assert format_relative_time((now - timedelta(seconds=10)).isoformat()) in (
        "刚刚",
        "just now",
    )
    assert "分钟" in format_relative_time(
        (now - timedelta(minutes=15)).isoformat()
    ) or "15m ago" in format_relative_time((now - timedelta(minutes=15)).isoformat())
    assert "小时" in format_relative_time(
        (now - timedelta(hours=3)).isoformat()
    ) or "3h ago" in format_relative_time((now - timedelta(hours=3)).isoformat())
    assert format_relative_time((now - timedelta(days=1)).isoformat()) in (
        "昨天",
        "yesterday",
    )


# ── ca -r / ca resume ─────────────────────────────────────────────────────────


def test_bare_ca_prints_help_and_exits_zero(monkeypatch, capsys):
    ret = _run_cli(monkeypatch, [])
    assert ret == 0
    out = capsys.readouterr().out
    assert "Usage: ca" in out
    assert "ca -r" in out


def test_unknown_command_or_engine_fails_without_fallback(monkeypatch, capsys):
    ret = _run_cli(monkeypatch, ["non_existent_engine_or_cmd"])
    assert ret == 1
    err = capsys.readouterr().err
    assert "non_existent_engine_or_cmd" in err
    assert "Available engines" in err or "可用引擎" in err


def test_ca_dash_r_non_interactive_resumes_most_recent(find_all, monkeypatch, capsys):
    completed = MagicMock(returncode=0)
    with patch("subprocess.run", return_value=completed):
        ret = _run_cli(monkeypatch, ["-r", "--no-launch"])
        assert ret == 0

    out = capsys.readouterr().out
    assert "Claude Task" in out
    assert "claude --resume ses-claude-1" in out


def test_ca_dash_r_with_index_resumes_that_session(find_all, monkeypatch, capsys):
    completed = MagicMock(returncode=0)
    with patch("subprocess.run", return_value=completed):
        ret = _run_cli(monkeypatch, ["-r", "2", "--no-launch"])
        assert ret == 0

    out = capsys.readouterr().out
    assert "Codex Task" in out
    assert "codex resume ses-codex-2" in out


def test_ca_resume_command_works_identically(find_all, monkeypatch, capsys):
    completed = MagicMock(returncode=0)
    with patch("subprocess.run", return_value=completed):
        ret = _run_cli(monkeypatch, ["resume", "3", "--no-launch"])
        assert ret == 0

    out = capsys.readouterr().out
    assert "OpenCode Task" in out
    assert "opencode" in out
    assert "-s ses-opencode-3" in out


def test_ca_dash_r_with_session_id(find_all, monkeypatch, capsys):
    completed = MagicMock(returncode=0)
    with patch("subprocess.run", return_value=completed):
        ret = _run_cli(monkeypatch, ["-r", "ses-codex-2", "--no-launch"])
        assert ret == 0

    out = capsys.readouterr().out
    assert "Codex Task" in out
    assert "codex resume ses-codex-2" in out


def test_ca_dash_r_invalid_index(find_all, monkeypatch, capsys):
    ret = _run_cli(monkeypatch, ["-r", "99", "--no-launch"])
    assert ret == 1
    out = capsys.readouterr().out
    assert "99" in out


def test_ca_dash_r_no_sessions(monkeypatch, capsys):
    with patch("core.session_history.repository.list_summaries", return_value=[]):
        ret = _run_cli(monkeypatch, ["-r"])
        assert ret == 1
    out = capsys.readouterr().out
    assert "没有找到任何历史会话" in out or "No session history found" in out


def test_ca_resume_engine_filter(find_all, monkeypatch):
    completed = MagicMock(returncode=0)
    with patch("subprocess.run", return_value=completed):
        ret = _run_cli(monkeypatch, ["resume", "-e", "codex", "1", "--no-launch"])
        assert ret == 0
    find_all.assert_called_with(
        project=unittest_cwd(),
        engine="codex",
        include_subagents=False,
        limit=20,
    )


def unittest_cwd() -> str:
    from pathlib import Path

    return str(Path.cwd())


def test_ca_dash_r_interactive_questionary_select(find_all, monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    mock_select = MagicMock()
    mock_select.ask.return_value = {
        "engine": "opencode",
        "session_id": "ses-opencode-3",
        "title": "OpenCode Task",
    }
    completed = MagicMock(returncode=0)
    with patch("questionary.select", return_value=mock_select):
        with patch("subprocess.run", return_value=completed):
            ret = _run_cli(monkeypatch, ["-r", "--no-launch"])
            assert ret == 0

    out = capsys.readouterr().out
    assert "OpenCode Task" in out
    assert "opencode" in out
    assert "-s ses-opencode-3" in out


def test_ca_dash_r_interactive_questionary_exit(find_all, monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    mock_select = MagicMock()
    mock_select.ask.return_value = "exit"
    with patch("questionary.select", return_value=mock_select):
        ret = _run_cli(monkeypatch, ["-r", "--no-launch"])
        assert ret == 0

    out = capsys.readouterr().out
    assert "操作已取消" in out or "cancelled" in out.lower()


def test_ca_resume_resolves_windows_cli_candidate_on_file_not_found(
    find_all, monkeypatch
):
    """When bare command raises FileNotFoundError on Windows, fallback resolves .cmd."""
    monkeypatch.setattr("sys.platform", "win32")
    calls = []

    def mock_run(argv, **kwargs):
        calls.append(argv)
        if argv[0] == "codex":
            raise FileNotFoundError("codex not found")
        return MagicMock(returncode=0)

    with patch(
        "shutil.which",
        side_effect=lambda cmd: r"C:\npm\codex.cmd" if "codex" in cmd else None,
    ):
        with patch("subprocess.run", side_effect=mock_run):
            ret = _run_cli(monkeypatch, ["-r", "2"])
            assert ret == 0

    assert len(calls) == 2
    assert calls[0] == ["codex", "resume", "ses-codex-2"]
    assert calls[1][0] == r"C:\npm\codex.cmd"
    assert calls[1][1:] == ["resume", "ses-codex-2"]


# ── 会话索引预热 ──────────────────────────────────────────────────────────────


def test_resume_builds_the_index_before_reading(monkeypatch, find_all, tmp_path):
    """CLI 在列会话之前必须先确保索引可用，否则每次都退回全量解析。"""
    calls: list[str] = []

    def fake_ensure(notify=None):
        calls.append("ensure")
        return True

    monkeypatch.setattr(
        "core.session_history.repository.ensure_index_ready", fake_ensure
    )
    find_all.side_effect = lambda **kwargs: calls.append("list") or []

    _run_cli(monkeypatch, ["-r", "--no-launch"])

    assert calls[:2] == ["ensure", "list"]


def test_index_warmup_notice_goes_to_stderr(monkeypatch, capsys):
    """``ca -r 1 --no-launch`` 的 stdout 是给人复制的命令，提示不能混进去。"""
    from core.cli import helpers

    monkeypatch.setattr(
        "core.session_history.repository.ensure_index_ready",
        lambda notify=None: (notify and notify(), False)[1],
    )

    helpers.warm_session_index()

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "index" in captured.err.lower() or "索引" in captured.err

"""``ca history`` / ``ca history show`` / ``ca history convert`` 的 CLI 测试。"""

from unittest.mock import patch

import ca_launcher
from core.session_history.models import (
    EngineType,
    ToolCallSummary,
    UnifiedMessage,
    UnifiedSession,
)


def _run(monkeypatch, *argv):
    monkeypatch.setattr("sys.argv", ["ca_launcher.py", *argv])
    return ca_launcher.main()


def _session(session_id="s1", engine=EngineType.CLAUDE, **overrides):
    defaults = dict(
        session_id=session_id,
        engine=engine,
        project_path="/proj",
        started_at="2026-08-27T10:00:00",
        title="Fix the parser",
        model="sonnet",
        messages=[
            UnifiedMessage(
                role="user",
                content="please fix it",
                timestamp="2026-08-27T10:00:01",
            ),
            UnifiedMessage(
                role="assistant",
                content="done",
                timestamp="2026-08-27T10:00:02",
                tool_calls=[ToolCallSummary(name="read_file", args_preview="a.py")],
            ),
        ],
    )
    defaults.update(overrides)
    return UnifiedSession(**defaults)


# ── ca history (list) ────────────────────────────────────────────────────────


def test_bare_history_lists_sessions(monkeypatch, capsys):
    with patch(
        "core.session_history.session_finder.find_all_sessions",
        return_value=[_session()],
    ):
        _run(monkeypatch, "history")
    out = capsys.readouterr().out
    assert "Found 1 session(s)" in out
    assert "Fix the parser" in out
    assert "ID: s1" in out
    assert "ca history show" in out


def test_history_empty_project(monkeypatch, capsys):
    with patch(
        "core.session_history.session_finder.find_all_sessions", return_value=[]
    ):
        _run(monkeypatch, "history", "list")
    assert "No sessions found for this project." in capsys.readouterr().out


def test_history_engine_filter_reaches_the_finder(monkeypatch):
    with patch(
        "core.session_history.session_finder.find_all_sessions", return_value=[]
    ) as find_all:
        _run(monkeypatch, "history", "list", "--engine", "codex")
    assert find_all.call_args.kwargs["engine"] == "codex"


# ── ca history show ──────────────────────────────────────────────────────────


def test_show_unknown_session_reports_not_found(monkeypatch, capsys):
    with patch(
        "core.session_history.session_finder.find_session_by_id", return_value=None
    ):
        _run(monkeypatch, "history", "show", "claude", "ghost")
    assert "[X] Session not found: claude/ghost" in capsys.readouterr().out


def test_show_prints_metadata_messages_and_tool_calls(monkeypatch, capsys):
    with patch(
        "core.session_history.session_finder.find_session_by_id",
        return_value=_session(),
    ):
        _run(monkeypatch, "history", "show", "claude", "s1")
    out = capsys.readouterr().out
    assert "Engine:" in out and "claude" in out
    assert "Session:" in out and "s1" in out
    assert "Messages:" in out and "2" in out
    assert "Model:" in out and "sonnet" in out
    assert "USER" in out and "please fix it" in out
    assert "ASSISTANT" in out and "done" in out
    assert "* read_file(a.py)" in out


def test_show_missing_model_falls_back_to_unknown(monkeypatch, capsys):
    with patch(
        "core.session_history.session_finder.find_session_by_id",
        return_value=_session(model=""),
    ):
        _run(monkeypatch, "history", "show", "claude", "s1")
    assert "(unknown)" in capsys.readouterr().out


# ── ca history convert ───────────────────────────────────────────────────────


def test_convert_unknown_session_reports_not_found(monkeypatch, capsys):
    with patch(
        "core.session_history.session_finder.find_session_by_id", return_value=None
    ):
        _run(monkeypatch, "history", "convert", "claude", "ghost", "codex")
    assert "[X] Session not found: claude/ghost" in capsys.readouterr().out


def test_convert_refuses_without_confirmation_when_not_interactive(
    monkeypatch, capsys
):
    with patch(
        "core.session_history.session_finder.find_session_by_id",
        return_value=_session(),
    ):
        with patch("core.session_history.writers.write_session") as write:
            _run(monkeypatch, "history", "convert", "claude", "s1", "codex")
    write.assert_not_called()
    out = capsys.readouterr().out
    assert "Refusing to convert without confirmation" in out
    assert "--yes" in out


def test_convert_with_yes_writes_and_shows_the_resume_hint(monkeypatch, capsys):
    source = _session()
    with patch(
        "core.session_history.session_finder.find_session_by_id", return_value=source
    ):
        with patch(
            "core.session_history.writers.write_session", return_value="new-id"
        ) as write:
            _run(monkeypatch, "history", "convert", "claude", "s1", "codex", "--yes")

    write.assert_called_once_with(source, "codex")
    out = capsys.readouterr().out
    assert "[OK] Converted claude -> codex" in out
    assert "New session ID: new-id" in out
    assert "codex continue" in out


def test_convert_writer_failure_is_reported(monkeypatch, capsys):
    with patch(
        "core.session_history.session_finder.find_session_by_id",
        return_value=_session(),
    ):
        with patch(
            "core.session_history.writers.write_session",
            side_effect=RuntimeError("disk full"),
        ):
            _run(monkeypatch, "history", "convert", "claude", "s1", "codex", "--yes")
    assert "[X] Conversion failed: disk full" in capsys.readouterr().out

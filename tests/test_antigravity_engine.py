from __future__ import annotations

from core.constants import ENGINES, HEADLESS_ENGINES, MCP_ENGINES
from engines.start_antigravity import AntigravityEngine


def test_antigravity_constants():
    assert "antigravity" in ENGINES
    assert "antigravity" in HEADLESS_ENGINES
    assert "antigravity" in MCP_ENGINES


def test_antigravity_engine_build_command():
    engine = AntigravityEngine()
    cmd = engine.build_command("test message", non_interactive=False, yolo=True)
    assert cmd == ["agy", "-i", "test message", "--dangerously-skip-permissions"]

    cmd_ni = engine.build_command("test message", non_interactive=True, yolo=True)
    assert cmd_ni == [
        "agy",
        "-p",
        "test message",
        "--output-format",
        "json",
        "--dangerously-skip-permissions",
    ]

    cmd_interactive_noyolo = engine.build_command(
        "test message", non_interactive=False, yolo=False
    )
    assert cmd_interactive_noyolo == ["agy", "-i", "test message"]

    cmd_empty = engine.build_command("", non_interactive=False, yolo=False)
    assert cmd_empty == ["agy"]


def test_antigravity_engine_build_chat_command():
    engine = AntigravityEngine()
    cmd = engine.build_chat_command("prompt", session_id="sess-123")
    assert cmd == [
        "agy",
        "-p",
        "prompt",
        "--output-format",
        "json",
        "--dangerously-skip-permissions",
        "--conversation",
        "sess-123",
    ]

    cmd_no_session = engine.build_chat_command("prompt")
    assert cmd_no_session == [
        "agy",
        "-p",
        "prompt",
        "--output-format",
        "json",
        "--dangerously-skip-permissions",
    ]


def test_doctor_engine_commands():
    from core.doctor import ENGINE_BINARIES, ENGINE_COMMANDS

    assert "antigravity" in ENGINE_BINARIES
    assert "antigravity" in ENGINE_COMMANDS
    assert "agy" in ENGINE_BINARIES["antigravity"]


def test_cli_antigravity_routing():
    from unittest.mock import patch

    from click.testing import CliRunner

    from core.cli.main import cli

    runner = CliRunner()
    with patch("core.cli.helpers._launch_engine") as mock_launch:
        mock_launch.return_value = 0
        runner.invoke(cli, ["antigravity"])
        assert mock_launch.called
        assert mock_launch.call_args[0][1][0] == "antigravity"

        runner.invoke(cli, ["agy"])
        assert mock_launch.call_args[0][1][0] == "agy"


def test_start_antigravity_main(monkeypatch):
    import sys
    from unittest.mock import MagicMock

    import pytest

    import engines.start_antigravity as start_mod

    # 1. --list flag
    mock_show = MagicMock()
    monkeypatch.setattr(start_mod, "show_tasks", mock_show)
    monkeypatch.setattr(sys, "argv", ["start_antigravity.py", "--list"])
    start_mod.main()
    assert mock_show.called

    # 2. CLI missing -> sys.exit(1)
    monkeypatch.setattr(start_mod, "require_engine_cli", lambda _: False)
    monkeypatch.setattr(sys, "argv", ["start_antigravity.py", "some prompt"])
    with pytest.raises(SystemExit) as exc:
        start_mod.main()
    assert exc.value.code == 1

    # 3. Normal launch with -t task
    monkeypatch.setattr(start_mod, "require_engine_cli", lambda _: True)
    monkeypatch.setattr(start_mod, "handle_task_mode", lambda *a, **kw: "task content")
    mock_run = MagicMock()
    monkeypatch.setattr(start_mod.AntigravityEngine, "run_shell", mock_run)
    monkeypatch.setattr(
        sys, "argv", ["start_antigravity.py", "-t", "001", "additional input"]
    )
    start_mod.main()
    assert mock_run.called
    cmd, env = mock_run.call_args[0]
    assert "agy" in cmd
    assert any("task content" in arg for arg in cmd)

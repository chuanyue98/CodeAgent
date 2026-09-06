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
    from core.cli.main import cli

    assert "antigravity" in cli.commands
    assert "agy" in cli.commands

"""ca 启动器到原生 CLI 的端到端行为：参数透传、并发会话。

规范不在这里测：启动器不投递规范，各引擎自己读项目根的 AGENTS.md。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

import engines.start_antigravity as agy_mod
import engines.start_claude_code as claude_mod
import engines.start_codebuddy as codebuddy_mod
import engines.start_codex as codex_mod
import engines.start_opencode as opencode_mod

BYPASS = codex_mod.CODEX_SKIP_PERMISSIONS_FLAG


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    """项目目录和家目录都指到 tmp，会话登记表与注入都不碰真实环境。"""
    home = tmp_path / "home"
    project = tmp_path / "project"
    home.mkdir()
    project.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.delenv("CA_YOLO", raising=False)
    monkeypatch.chdir(project)
    return project


def _stub_resources(monkeypatch, module, engine_cls):
    monkeypatch.setattr(module, "require_engine_cli", lambda _name: True)
    for name in ("get_plugins_to_mount", "get_skills_to_mount", "get_hooks_to_inject"):
        monkeypatch.setattr(engine_cls, name, lambda self: [])


def _capture_run(monkeypatch, engine_cls, on_run=None):
    seen: dict = {}

    def fake_run(self, cmd, env):
        seen["cmd"] = list(cmd)
        seen["env"] = dict(env)
        if on_run:
            on_run(seen)

    monkeypatch.setattr(engine_cls, "run_shell", fake_run)
    return seen


# --- first message ------------------------------------------------------


def test_first_message_moves_multiline_text_into_a_file(isolated):
    engine = claude_mod.ClaudeEngine()
    try:
        assert engine.first_message("单行") == "单行"
        assert engine.first_message("") == ""

        guidance = engine.first_message("第一行\n第二行")
        path = Path(guidance.split("CodeAgent file: ", 1)[1].split(". ", 1)[0])
        assert path.read_text(encoding="utf-8") == "第一行\n第二行"
    finally:
        engine.cleanup_temp_prompt()


# --- shared injection ----------------------------------------------------


def test_teardown_waits_for_the_last_concurrent_session(isolated):
    engine = claude_mod.ClaudeEngine()
    calls: list[str] = []
    scope = isolated / ".claude"

    def setup():
        calls.append("setup")

    def teardown():
        calls.append("teardown")

    with engine.shared_injection(scope, setup, teardown):
        with engine.shared_injection(scope, setup, teardown):
            pass
        assert calls == ["setup", "setup"]
    assert calls == ["setup", "setup", "teardown"]


def test_teardown_still_runs_when_the_session_fails(isolated):
    engine = claude_mod.ClaudeEngine()
    calls: list[str] = []

    with pytest.raises(RuntimeError):
        with engine.shared_injection(
            isolated / ".claude", lambda: None, lambda: calls.append("teardown")
        ):
            raise RuntimeError("engine crashed")
    assert calls == ["teardown"]


# --- claude --------------------------------------------------------------


def _run_claude(monkeypatch, argv):
    _stub_resources(monkeypatch, claude_mod, claude_mod.ClaudeEngine)
    seen = _capture_run(monkeypatch, claude_mod.ClaudeEngine)
    monkeypatch.setattr(sys, "argv", ["start_claude_code.py", *argv])
    claude_mod.main()
    return seen


def test_claude_resume_flag_reaches_claude_instead_of_the_prompt(isolated, monkeypatch):
    seen = _run_claude(monkeypatch, ["-r"])

    assert seen["cmd"][-1] == "-r"
    assert not any("CURRENT TASK" in arg or "IMPORTANT" in arg for arg in seen["cmd"])


def test_claude_plain_words_become_the_first_message(isolated, monkeypatch):
    seen = _run_claude(monkeypatch, ["修一下", "登录"])

    assert seen["cmd"][-1] == "修一下 登录"


def test_claude_help_is_claudes_own(isolated, monkeypatch):
    seen = _run_claude(monkeypatch, ["--help"])

    assert seen["cmd"][-1] == "--help"


def test_claude_non_interactive_uses_print_mode():
    cmd = claude_mod.ClaudeEngine().build_command("do it", True)

    assert cmd[-2:] == ["-p", "do it"]


# --- codebuddy -----------------------------------------------------------


def _run_codebuddy(monkeypatch, argv):
    _stub_resources(monkeypatch, codebuddy_mod, codebuddy_mod.CodeBuddyEngine)
    seen = _capture_run(monkeypatch, codebuddy_mod.CodeBuddyEngine)
    monkeypatch.setattr(sys, "argv", ["start_codebuddy.py", *argv])
    codebuddy_mod.main()
    return seen


def test_codebuddy_keeps_auto_permission_mode_and_passes_through(isolated, monkeypatch):
    seen = _run_codebuddy(monkeypatch, ["--resume", "abc"])

    assert seen["cmd"] == [
        "codebuddy",
        "--permission-mode",
        "auto",
        "--resume",
        "abc",
    ]


# --- codex ---------------------------------------------------------------


def test_codex_session_subcommand_comes_before_the_bypass_flag():
    cmd = codex_mod.CodexEngine().build_command(
        "", yolo=True, passthrough=["resume", "abc"]
    )

    assert cmd == ["codex", "resume", BYPASS, "abc"]


def test_codex_unrelated_subcommand_is_passed_through_bare():
    cmd = codex_mod.CodexEngine().build_command("", yolo=True, passthrough=["login"])

    assert cmd == ["codex", "login"]


def test_codex_non_interactive_shape_is_unchanged():
    assert codex_mod.CodexEngine().build_command("task", True) == [
        "codex",
        "exec",
        BYPASS,
        "task",
    ]


def _run_codex(monkeypatch, argv):
    _stub_resources(monkeypatch, codex_mod, codex_mod.CodexEngine)
    monkeypatch.setattr(codex_mod, "list_code_plan_directories", lambda: [])
    seen = _capture_run(monkeypatch, codex_mod.CodexEngine)
    monkeypatch.setattr(sys, "argv", ["start_codex.py", *argv])
    codex_mod.main()
    return seen


def test_codex_native_config_flag_is_not_mistaken_for_code_plan(isolated, monkeypatch):
    seen = _run_codex(monkeypatch, ["-c", "model=o3"])

    assert seen["cmd"][-2:] == ["-c", "model=o3"]


# --- opencode ------------------------------------------------------------


def _run_opencode(monkeypatch, argv):
    _stub_resources(monkeypatch, opencode_mod, opencode_mod.OpenCodeEngine)
    seen = _capture_run(monkeypatch, opencode_mod.OpenCodeEngine)
    monkeypatch.setattr(sys, "argv", ["start_opencode.py", *argv])
    opencode_mod.main()
    return seen


def test_opencode_session_flag_is_passed_through(isolated, monkeypatch):
    seen = _run_opencode(monkeypatch, ["-s", "ses_1"])

    assert seen["cmd"] == ["opencode", ".", "-s", "ses_1"]


# --- antigravity ---------------------------------------------------------


def test_antigravity_conversation_flag_is_passed_through(isolated, monkeypatch):
    monkeypatch.setattr(agy_mod, "require_engine_cli", lambda _name: True)
    seen = _capture_run(monkeypatch, agy_mod.AntigravityEngine)
    monkeypatch.setattr(sys, "argv", ["start_antigravity.py", "--conversation", "c1"])

    agy_mod.main()

    assert seen["cmd"] == [
        "agy",
        "--conversation",
        "c1",
        "--dangerously-skip-permissions",
    ]


# --- the decision this file guards ---------------------------------------


def test_launchers_never_pass_standards_to_the_engine(isolated, monkeypatch):
    """启动器不往命令行/环境里塞 system prompt，各引擎自己读 AGENTS.md。

    claude/codebuddy/codex 各是一套原生参数（--append-system-prompt-file、
    --append-system-prompt、-c developer_instructions=），opencode 是环境变量；
    这些都删掉了，这里把它们钉住不许回来。
    """
    runs = [
        _run_claude(monkeypatch, []),
        _run_codebuddy(monkeypatch, []),
        _run_codex(monkeypatch, []),
        _run_opencode(monkeypatch, []),
    ]

    for seen in runs:
        assert not any("system-prompt" in arg for arg in seen["cmd"])
        assert not any(arg.startswith("developer_instructions") for arg in seen["cmd"])
        assert "OPENCODE_CONFIG_CONTENT" not in seen["env"]

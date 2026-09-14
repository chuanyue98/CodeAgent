"""ca 启动器到原生 CLI 的端到端行为：参数透传、规范走系统提示、并发会话。"""

from __future__ import annotations

import json
import sys
import tomllib
from pathlib import Path

import pytest

import engines.start_antigravity as agy_mod
import engines.start_claude_code as claude_mod
import engines.start_codebuddy as codebuddy_mod
import engines.start_codex as codex_mod
import engines.start_opencode as opencode_mod
from core.prompt_kit import prompt_general, prompt_standards

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
    monkeypatch.delenv(opencode_mod.CONFIG_CONTENT_ENV, raising=False)
    monkeypatch.chdir(project)
    return project


def _stub_resources(monkeypatch, module, engine_cls, standards="STANDARDS_MARKER"):
    monkeypatch.setattr(module, "require_engine_cli", lambda _name: True)
    monkeypatch.setattr(engine_cls, "assemble_standards", lambda self: standards)
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


# --- prompt assembly -----------------------------------------------------


def test_prompt_standards_has_no_task_or_waiting_mode_section(tmp_path):
    (tmp_path / "base").mkdir()
    (tmp_path / "base" / "rules.md").write_text("RULE_BODY", encoding="utf-8")

    standards = prompt_standards(groups=["base"], prompt_root=tmp_path)

    assert standards == "### Base Standards ###RULE_BODY"
    assert prompt_general(groups=["base"], prompt_root=tmp_path).startswith(standards)
    assert "WAITING FOR INSTRUCTION" in prompt_general(
        groups=["base"], prompt_root=tmp_path
    )


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

    def read_standards(seen):
        cmd = seen["cmd"]
        standards_path = Path(cmd[cmd.index("--append-system-prompt-file") + 1])
        seen["standards_path"] = standards_path
        seen["standards"] = standards_path.read_text(encoding="utf-8")

    seen = _capture_run(monkeypatch, claude_mod.ClaudeEngine, read_standards)
    monkeypatch.setattr(sys, "argv", ["start_claude_code.py", *argv])
    claude_mod.main()
    return seen


def test_claude_resume_flag_reaches_claude_instead_of_the_prompt(isolated, monkeypatch):
    seen = _run_claude(monkeypatch, ["-r"])

    assert seen["cmd"][-1] == "-r"
    assert seen["standards"] == "STANDARDS_MARKER"
    assert not any("CURRENT TASK" in arg or "IMPORTANT" in arg for arg in seen["cmd"])


def test_claude_plain_words_become_the_first_message(isolated, monkeypatch):
    seen = _run_claude(monkeypatch, ["修一下", "登录"])

    assert seen["cmd"][-1] == "修一下 登录"


def test_claude_help_is_claudes_own(isolated, monkeypatch):
    seen = _run_claude(monkeypatch, ["--help"])

    assert seen["cmd"][-1] == "--help"


def test_claude_standards_file_is_removed_after_the_session(isolated, monkeypatch):
    seen = _run_claude(monkeypatch, [])

    assert not seen["standards_path"].exists()


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


def test_codebuddy_appends_standards_to_the_system_prompt(isolated, monkeypatch):
    seen = _run_codebuddy(monkeypatch, ["--resume", "abc"])

    cmd = seen["cmd"]
    assert cmd[cmd.index("--append-system-prompt") + 1] == "STANDARDS_MARKER"
    assert cmd[-2:] == ["--resume", "abc"]


def test_codebuddy_skips_standards_behind_a_windows_cmd_wrapper(
    isolated, monkeypatch, capsys
):
    monkeypatch.setattr(codebuddy_mod, "is_batch_shim", lambda *_a: True)

    seen = _run_codebuddy(monkeypatch, ["hi"])

    assert "--append-system-prompt" not in seen["cmd"]
    assert seen["cmd"][-1] == "hi"
    assert ".cmd" in capsys.readouterr().err


# --- codex ---------------------------------------------------------------


def test_codex_session_subcommand_takes_the_injected_flags_after_it():
    cmd = codex_mod.CodexEngine().build_command(
        "", yolo=True, standards="S", passthrough=["resume", "abc"]
    )

    assert cmd == ["codex", "resume", BYPASS, "-c", 'developer_instructions="S"', "abc"]


def test_codex_unrelated_subcommand_is_passed_through_bare():
    cmd = codex_mod.CodexEngine().build_command(
        "", yolo=True, standards="S", passthrough=["login"]
    )

    assert cmd == ["codex", "login"]


def test_codex_non_interactive_shape_is_unchanged():
    assert codex_mod.CodexEngine().build_command("task", True) == [
        "codex",
        "exec",
        BYPASS,
        "task",
    ]


def test_codex_standards_value_round_trips_through_toml():
    standards = '# 规范\nsay "hi" & | <x>\n\ttab \\ backslash'
    cmd = codex_mod.CodexEngine().build_command("", standards=standards)

    key, _, value = cmd[cmd.index("-c") + 1].partition("=")
    assert key == "developer_instructions"
    assert tomllib.loads(f"v = {value}")["v"] == standards


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
    assert 'developer_instructions="STANDARDS_MARKER"' in seen["cmd"]


def test_codex_skips_standards_behind_a_windows_cmd_wrapper(
    isolated, monkeypatch, capsys
):
    monkeypatch.setattr(codex_mod, "is_batch_shim", lambda *_a: True)

    seen = _run_codex(monkeypatch, ["hi"])

    assert not any(arg.startswith("developer_instructions") for arg in seen["cmd"])
    assert ".cmd" in capsys.readouterr().err


# --- opencode ------------------------------------------------------------


def test_opencode_standards_are_appended_to_existing_config_content():
    env = {opencode_mod.CONFIG_CONTENT_ENV: '{"instructions": ["a.md"], "model": "x"}'}

    opencode_mod.OpenCodeEngine().inject_standards(env, Path("/tmp/std.md"))

    data = json.loads(env[opencode_mod.CONFIG_CONTENT_ENV])
    assert data == {"instructions": ["a.md", "/tmp/std.md"], "model": "x"}


def test_opencode_leaves_unmergeable_config_content_alone():
    env = {opencode_mod.CONFIG_CONTENT_ENV: "not json"}

    opencode_mod.OpenCodeEngine().inject_standards(env, Path("/tmp/std.md"))

    assert env[opencode_mod.CONFIG_CONTENT_ENV] == "not json"


def test_opencode_session_flag_is_passed_through(isolated, monkeypatch):
    _stub_resources(monkeypatch, opencode_mod, opencode_mod.OpenCodeEngine)

    def read_instructions(seen):
        content = json.loads(seen["env"][opencode_mod.CONFIG_CONTENT_ENV])
        seen["standards"] = Path(content["instructions"][0]).read_text(encoding="utf-8")

    seen = _capture_run(monkeypatch, opencode_mod.OpenCodeEngine, read_instructions)
    monkeypatch.setattr(sys, "argv", ["start_opencode.py", "-s", "ses_1"])
    opencode_mod.main()

    assert seen["cmd"] == ["opencode", ".", "-s", "ses_1"]
    assert seen["standards"] == "STANDARDS_MARKER"


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

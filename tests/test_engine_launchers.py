"""ca 启动器到原生 CLI 的端到端行为：参数透传、并发会话。

规范不在这里测：启动器不投递规范，各引擎自己读项目根的 AGENTS.md。
"""

from __future__ import annotations

import json
import os
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

    def fake_run(self, cmd, env, stdin_text=None):
        seen["cmd"] = list(cmd)
        seen["env"] = dict(env)
        seen["stdin"] = stdin_text
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


def test_launch_banner_is_silent_when_quiet(monkeypatch, capsys):
    from core.engine_base.launch_args import announce_launch
    from core.logging_config import QUIET_ENV

    announce_launch("Claude")
    assert "Launching Claude" in capsys.readouterr().out

    monkeypatch.setenv(QUIET_ENV, "1")
    announce_launch("Claude")
    assert capsys.readouterr().out == ""


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


def test_a_scope_dir_ca_created_is_removed_once_empty(isolated):
    """用一次 ca codex，项目里不该多出一个空的 .codex/。"""
    engine = claude_mod.ClaudeEngine()
    scope = isolated / ".claude"

    with engine.shared_injection(scope, lambda: scope.mkdir(), lambda: None):
        with engine.shared_injection(scope, lambda: None, lambda: None):
            pass
        assert scope.is_dir()
    assert not scope.exists()


def test_a_scope_dir_the_user_had_is_kept(isolated):
    engine = claude_mod.ClaudeEngine()
    scope = isolated / ".claude"
    scope.mkdir()

    with engine.shared_injection(scope, lambda: None, lambda: None):
        pass
    assert scope.is_dir()


def test_a_created_scope_dir_that_gained_content_is_kept(isolated):
    engine = claude_mod.ClaudeEngine()
    scope = isolated / ".claude"

    def setup():
        scope.mkdir()
        (scope / "settings.local.json").write_text("{}", encoding="utf-8")

    with engine.shared_injection(scope, setup, lambda: None):
        pass
    assert (scope / "settings.local.json").exists()


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


def _run_claude_with(monkeypatch, isolated, on_run=None):
    """挂一个技能、一个 before_tool 钩子跑一次 ca claude。"""
    skill = isolated.parent / "skill-src" / "probe"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("---\nname: probe\n---\n", encoding="utf-8")
    monkeypatch.setattr(claude_mod, "require_engine_cli", lambda _name: True)
    monkeypatch.setattr(
        claude_mod.ClaudeEngine,
        "resolve_skill_sources",
        lambda self: [("probe", skill)],
    )
    monkeypatch.setattr(
        claude_mod.ClaudeEngine,
        "get_hooks_to_inject",
        lambda self: [{"name": "guard", "event": "before_tool", "command": "guard.sh"}],
    )
    monkeypatch.setattr(
        claude_mod.ClaudeEngine, "get_plugins_to_mount", lambda self: []
    )
    seen = _capture_run(monkeypatch, claude_mod.ClaudeEngine, on_run)
    monkeypatch.setattr(sys, "argv", ["start_claude_code.py"])
    claude_mod.main()
    return seen


def test_claude_mounts_skills_and_hooks_as_a_plugin_outside_the_workspace(
    isolated, monkeypatch
):
    def inspect(seen):
        root = Path(seen["cmd"][seen["cmd"].index("--plugin-dir") + 1])
        seen["root"] = root
        seen["skill"] = (root / "skills" / "probe" / "SKILL.md").exists()
        seen["hooks"] = json.loads((root / "hooks" / "hooks.json").read_text("utf-8"))

    seen = _run_claude_with(monkeypatch, isolated, inspect)

    assert Path.home() in seen["root"].parents
    assert seen["skill"]
    assert seen["hooks"] == {
        "hooks": {
            "PreToolUse": [
                {"matcher": "*", "hooks": [{"type": "command", "command": "guard.sh"}]}
            ]
        }
    }
    assert not (isolated / ".claude").exists()
    assert not seen["root"].exists()


def test_claude_clears_a_crashed_old_version_injection(isolated, monkeypatch):
    claude_dir = isolated / ".claude"
    claude_dir.mkdir()
    original = '{"permissions": {}}'
    (claude_dir / "settings.json.bak").write_text(original, encoding="utf-8")
    (claude_dir / "settings.json").write_text(
        '{"_ca_injected": true, "hooks": {}}', encoding="utf-8"
    )

    _run_claude_with(monkeypatch, isolated)

    assert (claude_dir / "settings.json").read_text(encoding="utf-8") == original
    assert not (claude_dir / "settings.json.bak").exists()


def test_claude_leaves_a_live_old_version_session_alone(isolated, monkeypatch):
    from core.lock_manager import SessionRegistry

    claude_dir = isolated / ".claude"
    claude_dir.mkdir()
    injected = '{"_ca_injected": true, "hooks": {}}'
    (claude_dir / "settings.json").write_text(injected, encoding="utf-8")
    (claude_dir / "settings.json.bak").write_text("{}", encoding="utf-8")

    old_session = SessionRegistry(claude_dir)
    with old_session.exclusive():
        old_session.join()
    try:
        _run_claude_with(monkeypatch, isolated)
    finally:
        with old_session.exclusive():
            old_session.leave()

    assert (claude_dir / "settings.json").read_text(encoding="utf-8") == injected


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


def test_codebuddy_mounts_hooks_in_its_inline_plugin(isolated, monkeypatch):
    monkeypatch.setattr(codebuddy_mod, "require_engine_cli", lambda _name: True)
    for name in ("get_plugins_to_mount", "get_skills_to_mount"):
        monkeypatch.setattr(codebuddy_mod.CodeBuddyEngine, name, lambda self: [])
    monkeypatch.setattr(
        codebuddy_mod.CodeBuddyEngine,
        "get_hooks_to_inject",
        lambda self: [{"name": "guard", "event": "before_tool", "command": "guard.sh"}],
    )

    def inspect(seen):
        root = Path(seen["env"]["CODEBUDDY_PLUGIN_DIRS"])
        seen["hooks"] = json.loads((root / "hooks" / "hooks.json").read_text("utf-8"))

    seen = _capture_run(monkeypatch, codebuddy_mod.CodeBuddyEngine, inspect)
    monkeypatch.setattr(sys, "argv", ["start_codebuddy.py"])
    codebuddy_mod.main()

    assert seen["hooks"]["hooks"]["PreToolUse"][0]["hooks"] == [
        {"type": "command", "command": "guard.sh"}
    ]
    assert not (isolated / ".codebuddy").exists()


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


def test_opencode_headless_message_goes_on_stdin(isolated, monkeypatch):
    """opencode run 会给带空格的参数包引号、内部 " 转义，所以消息不进参数。"""
    message = '第一行 "引号"\n第二行'
    seen = _run_opencode(monkeypatch, ["-ni", message])

    assert seen["cmd"] == ["opencode", "run"]
    assert seen["stdin"] == message


def _run_opencode_with(monkeypatch, isolated, on_run=None):
    """挂一个技能、一个 before_tool 钩子跑一次 ca opencode。"""
    skill = isolated.parent / "skill-src" / "probe"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("---\nname: probe\n---\n", encoding="utf-8")
    engine_cls = opencode_mod.OpenCodeEngine
    monkeypatch.setattr(opencode_mod, "require_engine_cli", lambda _name: True)
    monkeypatch.setattr(
        engine_cls, "resolve_skill_sources", lambda self: [("probe", skill)]
    )
    monkeypatch.setattr(
        engine_cls,
        "get_hooks_to_inject",
        lambda self: [{"name": "guard", "event": "before_tool", "command": "guard.sh"}],
    )
    monkeypatch.setattr(engine_cls, "get_plugins_to_mount", lambda self: [])
    seen = _capture_run(monkeypatch, engine_cls, on_run)
    monkeypatch.setattr(sys, "argv", ["start_opencode.py"])
    opencode_mod.main()
    return seen


def test_opencode_mounts_through_its_config_dir_not_the_workspace(
    isolated, monkeypatch
):
    def inspect(seen):
        root = Path(seen["env"][opencode_mod.CONFIG_DIR_ENV])
        seen["root"] = root
        seen["skill"] = (root / "skills" / "probe" / "SKILL.md").exists()
        seen["bridge"] = (root / "plugins" / "ca_hooks_bridge.js").exists()

    seen = _run_opencode_with(monkeypatch, isolated, inspect)

    assert Path.home() in seen["root"].parents
    assert seen["skill"] and seen["bridge"]
    assert not (isolated / ".opencode").exists()
    assert not seen["root"].exists()


def test_opencode_keeps_the_users_own_config_dir(isolated, monkeypatch):
    user_dir = isolated.parent / "my-opencode"
    (user_dir / "skills" / "mine").mkdir(parents=True)
    (user_dir / "agent").mkdir()
    monkeypatch.setenv(opencode_mod.CONFIG_DIR_ENV, str(user_dir))

    def inspect(seen):
        root = Path(seen["env"][opencode_mod.CONFIG_DIR_ENV])
        seen["names"] = {
            "skills": sorted(
                p.name
                for p in (root / "skills").iterdir()
                if not p.name.startswith(".")
            ),
            "agent": (root / "agent").is_dir(),
        }

    seen = _run_opencode_with(monkeypatch, isolated, inspect)

    assert seen["names"] == {"skills": ["mine", "probe"], "agent": True}
    assert (user_dir / "skills" / "mine").is_dir()


def test_opencode_clears_a_crashed_old_version_injection(isolated, monkeypatch):
    plugins = isolated / ".opencode" / "plugins"
    plugins.mkdir(parents=True)
    bridge = plugins / "ca_hooks_bridge.js"
    bridge.write_text("/* _ca_injected: true */", encoding="utf-8")
    users_own = plugins / "mine.js"
    users_own.write_text("export default {}", encoding="utf-8")

    _run_opencode_with(monkeypatch, isolated)

    assert not bridge.exists()
    assert users_own.exists()


def test_run_shell_sends_stdin_text_as_utf8(isolated):
    engine = opencode_mod.OpenCodeEngine()
    message = '中文 "引号"\n第二行'
    check = (
        f"import sys; sys.exit(sys.stdin.buffer.read().decode('utf-8') != {message!r})"
    )

    engine.run_shell(
        [sys.executable, "-c", check], dict(os.environ), stdin_text=message
    )


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

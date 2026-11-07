"""注入账本：退出时只收回 CodeAgent 写的部分，会话期间别人的改动保留。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import tomlkit

from core import doctor
from core.injection_ledger import InjectionLedger, ledger_path_for
from core.settings_manager import SettingsManager

HOOK = {"name": "guard", "event": "before_tool", "command": "run guard"}


@pytest.fixture
def manager():
    return SettingsManager({"before_tool": "PreToolUse"})


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_untouched_file_is_restored_byte_for_byte(tmp_path, manager):
    """没人动过就按原文写回，CRLF、缩进、键序都不变。"""
    settings = tmp_path / "settings.json"
    original = b'{\r\n    "theme":   "dark"\r\n}\r\n'
    settings.write_bytes(original)

    manager.inject_hooks(settings, [HOOK])
    assert _json(settings)["hooks"]["PreToolUse"][0]["hooks"][0]["name"] == "guard"

    manager.restore_settings(settings)

    assert settings.read_bytes() == original
    assert not ledger_path_for(settings).exists()


def test_edits_made_during_the_session_survive_teardown(tmp_path, manager):
    """回归：旧版整文件还原会把会话期间的改动一起抹掉。"""
    settings = tmp_path / "settings.json"
    settings.write_text(json.dumps({"theme": "dark"}), encoding="utf-8")
    manager.inject_hooks(settings, [HOOK])

    # 会话期间引擎/用户改了文件：加了一个设置项和一个自己的钩子。
    data = _json(settings)
    data["permissions"] = {"allow": ["Bash(ls)"]}
    data["hooks"]["PreToolUse"][0]["hooks"].append(
        {"name": "mine", "type": "command", "command": "keep me"}
    )
    settings.write_text(json.dumps(data), encoding="utf-8")

    manager.restore_settings(settings)

    after = _json(settings)
    assert after["theme"] == "dark"
    assert after["permissions"] == {"allow": ["Bash(ls)"]}
    names = [h["name"] for h in after["hooks"]["PreToolUse"][0]["hooks"]]
    assert names == ["mine"]
    assert not ledger_path_for(settings).exists()


def test_containers_created_by_injection_are_pruned(tmp_path, manager):
    settings = tmp_path / "settings.json"
    settings.write_text(json.dumps({"theme": "dark"}), encoding="utf-8")
    manager.inject_hooks(settings, [HOOK])

    data = _json(settings)
    data["model"] = "x"
    settings.write_text(json.dumps(data), encoding="utf-8")
    manager.restore_settings(settings)

    assert _json(settings) == {"theme": "dark", "model": "x"}


def test_a_users_same_named_hook_gets_its_own_value_back(tmp_path, manager):
    settings = tmp_path / "settings.json"
    users_hook = {"name": "guard", "type": "command", "command": "user's own"}
    settings.write_text(
        json.dumps(
            {"hooks": {"PreToolUse": [{"matcher": "*", "hooks": [users_hook]}]}}
        ),
        encoding="utf-8",
    )
    manager.inject_hooks(settings, [HOOK])
    data = _json(settings)
    data["theme"] = "light"
    settings.write_text(json.dumps(data), encoding="utf-8")

    manager.restore_settings(settings)

    after = _json(settings)
    assert after["hooks"]["PreToolUse"][0]["hooks"] == [users_hook]
    assert after["theme"] == "light"


def test_a_hook_changed_during_the_session_is_left_alone(tmp_path, manager):
    settings = tmp_path / "settings.json"
    manager.inject_hooks(settings, [HOOK])
    data = _json(settings)
    data["hooks"]["PreToolUse"][0]["hooks"][0]["command"] = "edited by user"
    settings.write_text(json.dumps(data), encoding="utf-8")

    manager.restore_settings(settings)

    hooks = _json(settings)["hooks"]["PreToolUse"][0]["hooks"]
    assert hooks[0]["command"] == "edited by user"


def test_a_second_session_does_not_overwrite_the_original(tmp_path, manager):
    """并发会话各自跑一次注入：原文和条目的原值只在第一次记下。"""
    settings = tmp_path / "settings.json"
    original = json.dumps({"theme": "dark"})
    settings.write_text(original, encoding="utf-8")

    manager.inject_hooks(settings, [HOOK])
    manager.inject_hooks(settings, [HOOK])

    ledger = InjectionLedger(settings)
    assert ledger.load()
    assert ledger.original == original
    assert len(ledger.entries) == 1
    assert ledger.entries[0]["previous"] is None

    manager.restore_settings(settings)
    assert settings.read_text(encoding="utf-8") == original


def test_a_crashed_session_is_cleaned_up_by_the_next_one(tmp_path, manager):
    settings = tmp_path / "settings.json"
    original = json.dumps({"theme": "dark"})
    settings.write_text(original, encoding="utf-8")
    manager.inject_hooks(settings, [HOOK])
    # 崩溃：没有 restore。下一次启动照常注入、照常退出。
    manager.inject_hooks(settings, [HOOK])
    manager.restore_settings(settings)

    assert settings.read_text(encoding="utf-8") == original
    assert not ledger_path_for(settings).exists()


def test_a_file_codeagent_created_is_removed_even_after_edits(tmp_path, manager):
    settings = tmp_path / "settings.json"
    manager.inject_hooks(settings, [HOOK])
    data = _json(settings)
    data["hooks"]["PreToolUse"][0]["hooks"][0]["command"] = HOOK["command"]
    settings.write_text(json.dumps(data, indent=4), encoding="utf-8")

    manager.restore_settings(settings)

    assert not settings.exists()


def test_toml_edits_and_comments_survive(tmp_path, manager):
    config = tmp_path / "config.toml"
    config.write_text('# keep this comment\nmodel = "a"\n', encoding="utf-8")
    manager.inject_hooks(config, [HOOK])

    doc = tomlkit.parse(config.read_text(encoding="utf-8"))
    doc["approval_policy"] = "never"
    config.write_text(tomlkit.dumps(doc), encoding="utf-8")

    manager.restore_settings(config)

    text = config.read_text(encoding="utf-8")
    assert "# keep this comment" in text
    after = tomlkit.parse(text)
    assert after["model"] == "a"
    assert after["approval_policy"] == "never"
    assert "hooks" not in after


def test_a_legacy_whole_file_injection_is_cleaned_before_reinjecting(tmp_path, manager):
    settings = tmp_path / "settings.json"
    settings.write_text(json.dumps({"hooks": {}, "_ca_injected": True}), "utf-8")
    backup = tmp_path / "settings.json.bak"
    backup.write_text(json.dumps({"theme": "dark"}), encoding="utf-8")

    manager.inject_hooks(settings, [HOOK])
    assert "_ca_injected" not in _json(settings)
    manager.restore_settings(settings)

    assert _json(settings) == {"theme": "dark"}
    assert not backup.exists()


# ── ca doctor ──────────────────────────────────────────────────────────────


def test_doctor_reports_and_withdraws_a_leftover_ledger(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    settings = tmp_path / ".claude" / "settings.json"
    settings.parent.mkdir()
    settings.write_text(json.dumps({"theme": "dark"}), encoding="utf-8")
    SettingsManager({"before_tool": "PreToolUse"}).inject_hooks(settings, [HOOK])
    data = _json(settings)
    data["model"] = "opus"
    settings.write_text(json.dumps(data), encoding="utf-8")

    stale = doctor.check_stale_injections(doctor.Section("Stale"))
    assert stale == [settings]

    doctor.preview_stale_injections(stale)
    assert ledger_path_for(settings).exists()

    doctor.fix_stale_injections(stale)

    assert _json(settings) == {"theme": "dark", "model": "opus"}
    assert not ledger_path_for(settings).exists()


# ── codex 用户级 config.toml 里的插件登记 ─────────────────────────────────


@pytest.fixture
def codex(tmp_path, monkeypatch):
    from engines.start_codex import CodexEngine

    engine = CodexEngine()
    home = tmp_path / "codex_home"
    home.mkdir()
    plugin_dir = tmp_path / "plugin-src"
    plugin_dir.mkdir()
    monkeypatch.setattr(engine, "_get_codex_home", lambda: home)
    monkeypatch.setattr(
        engine,
        "get_plugins_to_mount",
        lambda: [{"name": "demo", "_plugin_dir": str(plugin_dir)}],
    )
    return engine


def test_codex_keeps_what_codex_wrote_during_the_session(codex):
    """回归：会话期间 codex 写进全局配置的项目信任，退出时不能被旧备份覆盖。"""
    config = codex._get_user_config_path()
    config.write_text('model = "gpt-5"\n', encoding="utf-8")

    codex.ensure_plugins_available()
    assert f"demo@{codex.MARKETPLACE_NAME}" in config.read_text(encoding="utf-8")

    doc = tomlkit.parse(config.read_text(encoding="utf-8"))
    doc["projects"] = {"/work/repo": {"trust_level": "trusted"}}
    config.write_text(tomlkit.dumps(doc), encoding="utf-8")

    codex.cleanup_plugins_available()

    after = tomlkit.parse(config.read_text(encoding="utf-8"))
    assert after["model"] == "gpt-5"
    assert after["projects"]["/work/repo"]["trust_level"] == "trusted"
    assert "marketplaces" not in after
    assert "plugins" not in after
    assert not ledger_path_for(config).exists()
    assert not (config.parent / "config.toml.bak").exists()


def test_codex_untouched_global_config_is_restored_exactly(codex):
    config = codex._get_user_config_path()
    original = (
        '# mine\nmodel = "gpt-5"\n\n[plugins."other@elsewhere"]\nenabled = true\n'
    )
    config.write_text(original, encoding="utf-8")

    codex.ensure_plugins_available()
    codex.cleanup_plugins_available()

    assert config.read_text(encoding="utf-8") == original


def test_codex_leftover_without_a_ledger_is_still_withdrawn(codex):
    """旧版本留下的命名空间条目：没有账本也按命名空间摘掉，别的不动。"""
    config = codex._get_user_config_path()
    name = codex.MARKETPLACE_NAME
    config.write_text(
        f'model = "gpt-5"\n\n[marketplaces.{name}]\nsource_type = "local"\n\n'
        f'[plugins."demo@{name}"]\nenabled = true\n\n'
        '[plugins."other@elsewhere"]\nenabled = true\n',
        encoding="utf-8",
    )

    codex.cleanup_plugins_available()

    after = tomlkit.parse(config.read_text(encoding="utf-8"))
    assert after["model"] == "gpt-5"
    assert name not in after.get("marketplaces", {})
    assert list(after["plugins"].keys()) == ["other@elsewhere"]

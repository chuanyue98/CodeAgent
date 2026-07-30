import json

from core.engine_base import BaseEngine


def test_inject_hooks_to_settings_new_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    # Mocking necessary parts of BaseEngine to avoid loading real config
    engine = BaseEngine("Dummy", "dummy-model")

    settings_rel_path = ".gemini/settings.json"
    hooks = [{"name": "test-hook", "event": "BeforeAgent", "command": "echo hello"}]

    # This should fail because the method is not implemented yet
    engine.inject_hooks_to_settings(settings_rel_path, hooks)

    settings_path = tmp_path / settings_rel_path
    assert settings_path.exists()

    with open(settings_path, encoding="utf-8") as f:
        data = json.load(f)

    assert "hooks" in data
    assert "BeforeAgent" in data["hooks"]
    assert len(data["hooks"]["BeforeAgent"]) == 1
    assert data["hooks"]["BeforeAgent"][0]["matcher"] == "*"
    assert len(data["hooks"]["BeforeAgent"][0]["hooks"]) == 1
    assert data["hooks"]["BeforeAgent"][0]["hooks"][0]["name"] == "test-hook"
    assert data["hooks"]["BeforeAgent"][0]["hooks"][0]["command"] == "echo hello"


def test_inject_hooks_to_settings_update_existing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    engine = BaseEngine("Dummy", "dummy-model")

    settings_rel_path = ".gemini/settings.json"
    settings_path = tmp_path / settings_rel_path
    settings_path.parent.mkdir(parents=True)

    initial_data = {
        "hooks": {
            "BeforeAgent": [
                {
                    "matcher": "*",
                    "hooks": [
                        {
                            "name": "test-hook",
                            "type": "command",
                            "command": "old command",
                        },
                        {"name": "other-hook", "type": "command", "command": "keep me"},
                    ],
                }
            ]
        }
    }
    with open(settings_path, "w", encoding="utf-8") as f:
        json.dump(initial_data, f)

    hooks = [
        {"name": "test-hook", "event": "BeforeAgent", "command": "new command"},
        {"name": "new-hook", "event": "BeforeAgent", "command": "brand new"},
    ]

    engine.inject_hooks_to_settings(settings_rel_path, hooks)

    with open(settings_path, encoding="utf-8") as f:
        data = json.load(f)

    event_hooks = data["hooks"]["BeforeAgent"][0]["hooks"]
    assert len(event_hooks) == 3

    test_hook = next(h for h in event_hooks if h["name"] == "test-hook")
    assert test_hook["command"] == "new command"

    other_hook = next(h for h in event_hooks if h["name"] == "other-hook")
    assert other_hook["command"] == "keep me"

    new_hook = next(h for h in event_hooks if h["name"] == "new-hook")
    assert new_hook["command"] == "brand new"


def test_inject_hooks_writes_toml_for_codex_config(tmp_path, monkeypatch):
    """codex reads hooks from .codex/config.toml, so a .toml target must be
    written as TOML rather than JSON — the shape below is the one codex-cli
    0.142.5 was confirmed to parse via its app-server ``hooks/list`` method."""
    import tomlkit

    monkeypatch.chdir(tmp_path)
    engine = BaseEngine("Dummy", "dummy-model")
    engine.settings_manager.event_map = {
        "before_tool": "PreToolUse",
        "after_tool": "PostToolUse",
    }

    engine.inject_hooks_to_settings(
        ".codex/config.toml",
        [
            {"name": "branch-protection", "event": "before_tool", "command": "run me"},
            {"name": "ci-monitor", "event": "after_tool", "command": "run me too"},
        ],
    )

    raw = (tmp_path / ".codex" / "config.toml").read_text(encoding="utf-8")
    assert "[[hooks.PreToolUse]]" in raw
    assert "[[hooks.PreToolUse.hooks]]" in raw

    data = tomlkit.parse(raw)
    pre = data["hooks"]["PreToolUse"]
    assert pre[0]["matcher"] == "*"
    assert pre[0]["hooks"][0]["command"] == "run me"
    assert pre[0]["hooks"][0]["type"] == "command"
    assert data["hooks"]["PostToolUse"][0]["hooks"][0]["command"] == "run me too"


def test_inject_hooks_preserves_existing_toml_settings(tmp_path, monkeypatch):
    """A project's own .codex/config.toml keys must survive hook injection."""
    import tomlkit

    monkeypatch.chdir(tmp_path)
    config_path = tmp_path / ".codex" / "config.toml"
    config_path.parent.mkdir(parents=True)
    config_path.write_text('model = "keep-me"\n', encoding="utf-8")

    engine = BaseEngine("Dummy", "dummy-model")
    engine.settings_manager.event_map = {"before_tool": "PreToolUse"}
    engine.inject_hooks_to_settings(
        ".codex/config.toml",
        [{"name": "h", "event": "before_tool", "command": "c"}],
    )

    data = tomlkit.parse(config_path.read_text(encoding="utf-8"))
    assert data["model"] == "keep-me"
    assert data["hooks"]["PreToolUse"][0]["hooks"][0]["command"] == "c"


def test_restore_settings_recovers_the_original_toml(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    config_path = tmp_path / ".codex" / "config.toml"
    config_path.parent.mkdir(parents=True)
    original = 'model = "keep-me"\n'
    config_path.write_text(original, encoding="utf-8")

    engine = BaseEngine("Dummy", "dummy-model")
    engine.settings_manager.event_map = {"before_tool": "PreToolUse"}
    engine.inject_hooks_to_settings(
        ".codex/config.toml", [{"name": "h", "event": "before_tool", "command": "c"}]
    )
    engine.restore_settings(".codex/config.toml")

    assert config_path.read_text(encoding="utf-8") == original


def test_restore_settings_removes_a_toml_file_codeagent_created(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    engine = BaseEngine("Dummy", "dummy-model")
    engine.settings_manager.event_map = {"before_tool": "PreToolUse"}
    engine.inject_hooks_to_settings(
        ".codex/config.toml", [{"name": "h", "event": "before_tool", "command": "c"}]
    )
    assert (tmp_path / ".codex" / "config.toml").exists()

    engine.restore_settings(".codex/config.toml")

    assert not (tmp_path / ".codex" / "config.toml").exists()

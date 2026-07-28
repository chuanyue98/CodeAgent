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

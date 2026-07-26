import json

from core.services.hook_service import HookService


def _write_hook(hooks_root, category, name, event="BeforeAgent", description=""):
    hook_dir = hooks_root / category / name
    hook_dir.mkdir(parents=True)
    metadata = {
        "name": name,
        "event": event,
        "description": description,
    }
    (hook_dir / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
    return hook_dir


def test_get_detailed_hooks_no_config_marks_all_inactive(tmp_path):
    hooks_root = tmp_path / "hooks"
    _write_hook(hooks_root, "base", "greet", event="BeforeAgent", description="Says hi")

    service = HookService(hooks_root, tmp_path / "config.json")
    hooks = service.get_detailed_hooks()

    assert len(hooks) == 1
    hook = hooks[0]
    assert hook["id"] == "base/greet"
    assert hook["name"] == "greet"
    assert hook["event"] == "BeforeAgent"
    assert hook["description"] == "Says hi"
    assert hook["isActive"] is False


def test_get_detailed_hooks_marks_active_from_config(tmp_path):
    hooks_root = tmp_path / "hooks"
    _write_hook(hooks_root, "base", "greet")

    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps({"hooks": {"project_hooks": {"common": ["base/greet"]}}}),
        encoding="utf-8",
    )

    service = HookService(hooks_root, config_path)
    hooks = service.get_detailed_hooks()

    assert hooks[0]["isActive"] is True


def test_get_detailed_hooks_ignores_malformed_config(tmp_path):
    hooks_root = tmp_path / "hooks"
    _write_hook(hooks_root, "base", "greet")

    config_path = tmp_path / "config.json"
    config_path.write_text("{ not valid json", encoding="utf-8")

    service = HookService(hooks_root, config_path)
    hooks = service.get_detailed_hooks()

    assert hooks[0]["isActive"] is False


def test_get_detailed_hooks_handles_non_list_project_hooks_entries(tmp_path):
    hooks_root = tmp_path / "hooks"
    _write_hook(hooks_root, "base", "greet")

    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps({"hooks": {"project_hooks": {"common": "not-a-list"}}}),
        encoding="utf-8",
    )

    service = HookService(hooks_root, config_path)
    hooks = service.get_detailed_hooks()

    assert hooks[0]["isActive"] is False


def test_get_detailed_hooks_empty_root_returns_empty_list(tmp_path):
    service = HookService(tmp_path / "missing", tmp_path / "config.json")
    assert service.get_detailed_hooks() == []


def test_get_detailed_hooks_defaults_when_metadata_missing_fields(tmp_path):
    hooks_root = tmp_path / "hooks"
    hook_dir = hooks_root / "base" / "bare"
    hook_dir.mkdir(parents=True)
    (hook_dir / "metadata.json").write_text("{}", encoding="utf-8")

    service = HookService(hooks_root, tmp_path / "config.json")
    hooks = service.get_detailed_hooks()

    assert hooks[0]["name"] == "bare"
    assert hooks[0]["event"] == "Unknown"
    assert hooks[0]["description"] == ""
    # The scanner always stamps _hook_dir onto loaded metadata, so the
    # detailed view resolves a real path even though the file itself
    # supplied no fields of its own.
    assert hooks[0]["path"] == str(hook_dir.resolve().as_posix())

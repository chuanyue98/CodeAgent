import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.engine_base import BaseEngine, EnvironmentManager


class DummyEngine(BaseEngine):
    def __init__(self, root_dir=None):
        if root_dir:
            from core.link_manager import LinkManager
            from core.lock_manager import LockManager
            from core.settings_manager import SettingsManager

            self.root_dir = root_dir
            self.name = "Dummy"
            self.default_model = "dummy-model"
            self.config_manager = _DummyConfigManager(self.root_dir)
            self.full_config = self.config_manager.full_config
            self.env_manager = EnvironmentManager(self.root_dir)
            self.temp_prompt_name = ".ca_prompt.tmp"
            self._temp_prompt_paths = set()
            self.link_manager = LinkManager()
            self.lock_manager = LockManager()
            self.settings_manager = SettingsManager(self.EVENT_MAP)
        else:
            super().__init__("Dummy", "dummy-model")


class _DummyConfigManager:
    def __init__(self, root_dir):
        from core.config_manager import ConfigManager

        self._impl = ConfigManager(root_dir)

    @property
    def root_dir(self):
        return self._impl.root_dir

    @property
    def full_config(self):
        return self._impl.full_config

    @full_config.setter
    def full_config(self, value):
        self._impl.full_config = value

    def __getattr__(self, name):
        return getattr(self._impl, name)


@pytest.fixture
def mock_engine(tmp_path):
    root_dir = tmp_path / "codeagent"
    root_dir.mkdir()
    (root_dir / "skills").mkdir()
    (root_dir / "prompt").mkdir()
    (root_dir / "hooks").mkdir()
    (root_dir / "plugins").mkdir()

    config = {
        "prompts": {
            "default_group": "common",
            "project_mapping": [{"pattern": ".*-web-.*", "group": "frontend"}],
            "groups": {"frontend": ["web", "react"]},
        },
        "project_registry": [
            {"path": str(tmp_path / "my-web-project"), "group": "web-app"}
        ],
    }
    (root_dir / "config.json").write_text(json.dumps(config))

    return DummyEngine(root_dir=root_dir)


def test_environment_manager_get_env(tmp_path):
    manager = EnvironmentManager(tmp_path)
    env = manager.get_env()
    assert env["CODEAGENT_PATH"] == str(tmp_path.absolute()).replace("\\", "/")


def test_engine_get_current_project_group(mock_engine, tmp_path, monkeypatch):
    # 1. Inside CodeAgent root
    monkeypatch.chdir(mock_engine.root_dir)
    assert mock_engine.get_current_project_group() == "codeagent"

    # 2. Registered project
    proj_dir = tmp_path / "my-web-project"
    proj_dir.mkdir()
    monkeypatch.chdir(proj_dir)
    assert mock_engine.get_current_project_group() == "web-app"

    # 3. Common directory
    other_dir = tmp_path / "other"
    other_dir.mkdir()
    monkeypatch.chdir(other_dir)
    assert mock_engine.get_current_project_group() == "common"

    monkeypatch.setenv("CA_PROJECT_GROUP", "forced-group")
    assert mock_engine.get_current_project_group() == "forced-group"


def test_a_registry_rule_wins_over_the_codeagent_default(mock_engine, monkeypatch):
    # Registering CodeAgent's own tree under another group used to be ignored:
    # the "inside CodeAgent root -> codeagent" shortcut ran before the registry
    # was even consulted, so an explicit rule lost to a hardcoded name.
    mock_engine.config_manager.full_config.setdefault("project_registry", []).append(
        {"path": str(mock_engine.root_dir), "group": "self-hosted"}
    )
    monkeypatch.chdir(mock_engine.root_dir)

    assert mock_engine.get_current_project_group() == "self-hosted"


def test_a_parent_rule_covers_a_nested_repository(mock_engine, tmp_path, monkeypatch):
    parent = tmp_path / "demo"
    nested = parent / "nested-repo"
    nested.mkdir(parents=True)
    mock_engine.config_manager.full_config.setdefault("project_registry", []).append(
        {"path": str(parent), "group": "web-app"}
    )
    monkeypatch.chdir(nested)

    assert mock_engine.get_current_project_group() == "web-app"


def test_engine_temp_prompt_lifecycle(mock_engine):
    prompt_content = "Hello CodeAgent"
    instruction = mock_engine.write_temp_prompt(prompt_content)

    [temp_file] = mock_engine._temp_prompt_paths
    assert temp_file.exists()
    assert temp_file.parent.name == "codeagent-prompts"
    assert temp_file.read_text(encoding="utf-8") == prompt_content
    assert str(temp_file.absolute()).replace("\\", "/") in instruction

    mock_engine.cleanup_temp_prompt()
    assert not temp_file.exists()


def test_engine_temp_prompts_are_unique_per_instance(tmp_path):
    root = tmp_path / "ca"
    root.mkdir()
    first = DummyEngine(root_dir=root)
    second = DummyEngine(root_dir=root)

    first.write_temp_prompt("first")
    second.write_temp_prompt("second")

    [first_path] = first._temp_prompt_paths
    [second_path] = second._temp_prompt_paths
    assert first_path != second_path
    assert first_path.read_text(encoding="utf-8") == "first"
    assert second_path.read_text(encoding="utf-8") == "second"

    first.cleanup_temp_prompt()
    assert not first_path.exists()
    assert second_path.exists()
    second.cleanup_temp_prompt()


def test_engine_inject_hooks_to_settings(mock_engine, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    settings_file = tmp_path / "settings.json"

    hooks = [{"name": "test-hook", "event": "pre-commit", "command": "echo hello"}]

    mock_engine.inject_hooks_to_settings("settings.json", hooks)

    assert settings_file.exists()
    with open(settings_file) as f:
        data = json.load(f)
        assert "_ca_injected" not in data
        assert data["hooks"]["pre-commit"][0]["hooks"][0]["name"] == "test-hook"

    # Test restore
    mock_engine.restore_settings("settings.json")
    assert not settings_file.exists()


def test_ensure_skills_link_deduplicates_same_skill_name(monkeypatch, tmp_path, caplog):
    # Reuse original test logic but integrated with new mock structure if needed
    # (Original test 1)
    engine = DummyEngine(root_dir=tmp_path / "ca")
    engine.root_dir.mkdir()

    project_root = tmp_path / "project"
    project_root.mkdir()

    project_skills_root = project_root / "skills"
    (project_skills_root / "ui-ux-pro-max").mkdir(parents=True)
    (project_skills_root / "ui-ux-pro-max" / "SKILL.md").write_text(
        "project", encoding="utf-8"
    )

    builtin_root = tmp_path / "builtin-root"
    (builtin_root / "web" / "ui-ux-pro-max").mkdir(parents=True)
    (builtin_root / "web" / "ui-ux-pro-max" / "SKILL.md").write_text(
        "builtin", encoding="utf-8"
    )

    monkeypatch.chdir(project_root)
    monkeypatch.setattr(engine, "get_skills_to_mount", lambda: ["ui-ux-pro-max", "web"])
    monkeypatch.setattr(
        engine,
        "_get_skill_search_roots",
        lambda: [project_skills_root, builtin_root],
    )

    with caplog.at_level("INFO"):
        engine.ensure_skills_link(".opencode/skills")

    mounted_root = project_root / ".opencode" / "skills"
    assert (mounted_root / "ui-ux-pro-max" / "SKILL.md").read_text(
        encoding="utf-8"
    ) == "project"

    assert "Skip duplicate skill 'ui-ux-pro-max'" in caplog.text


def test_ensure_skills_link_preserves_unmanaged_links_and_regular_dirs(
    monkeypatch, tmp_path
):
    # (Original test 2)
    engine = DummyEngine(root_dir=tmp_path / "ca")
    engine.root_dir.mkdir()

    project_root = tmp_path / "project"
    project_root.mkdir()
    monkeypatch.chdir(project_root)

    builtin_root = tmp_path / "builtin-root"
    stale_skill_root = builtin_root / "web" / "old-skill"
    fresh_skill_root = builtin_root / "web" / "new-skill"
    stale_skill_root.mkdir(parents=True)
    fresh_skill_root.mkdir(parents=True)
    (stale_skill_root / "SKILL.md").write_text("old", encoding="utf-8")
    (fresh_skill_root / "SKILL.md").write_text("new", encoding="utf-8")

    mounted_root = project_root / ".opencode" / "skills"
    mounted_root.mkdir(parents=True)
    engine._create_skill_link(stale_skill_root, mounted_root / "old-skill")

    regular_dir = mounted_root / "notes"
    regular_dir.mkdir()
    (regular_dir / "keep.txt").write_text("keep", encoding="utf-8")

    monkeypatch.setattr(engine, "get_skills_to_mount", lambda: ["web/new-skill"])
    monkeypatch.setattr(engine, "_get_skill_search_roots", lambda: [builtin_root])

    engine.ensure_skills_link(".opencode/skills")

    # On Windows the link is a junction (mklink /j), not a symlink — is_symlink()
    # is False but it must still exist as a directory/junction and not be removed.
    assert (mounted_root / "old-skill").exists()
    assert (mounted_root / "old-skill").is_dir() or (
        mounted_root / "old-skill"
    ).is_symlink()
    assert (mounted_root / "new-skill" / "SKILL.md").read_text(
        encoding="utf-8"
    ) == "new"
    assert (regular_dir / "keep.txt").read_text(encoding="utf-8") == "keep"

    engine.link_manager.cleanup_link_dir(mounted_root)
    assert (mounted_root / "old-skill").exists()
    assert not (mounted_root / "new-skill").exists()


def test_ensure_skills_link_does_not_replace_regular_file(monkeypatch, tmp_path):
    engine = DummyEngine(root_dir=tmp_path / "ca")
    engine.root_dir.mkdir()
    project_root = tmp_path / "project"
    project_root.mkdir()
    monkeypatch.chdir(project_root)

    source = tmp_path / "source" / "skill"
    source.mkdir(parents=True)
    (source / "SKILL.md").write_text("skill", encoding="utf-8")
    mounted_root = project_root / ".opencode" / "skills"
    mounted_root.mkdir(parents=True)
    collision = mounted_root / "skill"
    collision.write_text("user-owned", encoding="utf-8")

    monkeypatch.setattr(engine, "get_skills_to_mount", lambda: ["skill"])
    monkeypatch.setattr(engine, "_get_skill_search_roots", lambda: [source.parent])

    engine.ensure_skills_link(".opencode/skills")

    assert collision.read_text(encoding="utf-8") == "user-owned"


def test_ensure_skills_link_warns_when_resolved_dir_has_no_skill_md(
    monkeypatch, tmp_path, caplog
):
    """A skill group directory that resolves but contains no SKILL.md
    (directly or in a subdirectory) -- e.g. an empty or half-written skill
    -- must not be dropped silently; the user needs to see why it didn't
    mount."""
    engine = DummyEngine(root_dir=tmp_path / "ca")
    engine.root_dir.mkdir()

    project_root = tmp_path / "project"
    project_root.mkdir()
    monkeypatch.chdir(project_root)

    builtin_root = tmp_path / "builtin-root"
    broken = builtin_root / "broken-skill"
    broken.mkdir(parents=True)
    (broken / "notes.txt").write_text("oops", encoding="utf-8")

    good = builtin_root / "good-skill"
    good.mkdir(parents=True)
    (good / "SKILL.md").write_text("good", encoding="utf-8")

    monkeypatch.setattr(
        engine, "get_skills_to_mount", lambda: ["broken-skill", "good-skill"]
    )
    monkeypatch.setattr(engine, "_get_skill_search_roots", lambda: [builtin_root])

    with caplog.at_level("INFO"):
        engine.ensure_skills_link(".opencode/skills")

    assert "broken-skill" in caplog.text
    assert "no SKILL.md" in caplog.text

    mounted_root = project_root / ".opencode" / "skills"
    assert (mounted_root / "good-skill" / "SKILL.md").exists()
    assert not (mounted_root / "broken-skill").exists()


def test_safe_remove_link_reports_windows_rmdir_failure(mock_engine, tmp_path, caplog):
    target = tmp_path / "linked-dir"
    target.mkdir()

    with caplog.at_level("WARNING"):
        with patch("os.name", "nt"):
            with patch.object(Path, "is_symlink", return_value=True):
                with patch("os.rmdir", side_effect=OSError("Access is denied.")):
                    mock_engine._safe_remove_link(target)

    assert "Access is denied" in caplog.text


def test_create_skill_link_unix(mock_engine, tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    target = tmp_path / "target"

    with patch("os.name", "posix"):
        with patch.object(Path, "symlink_to") as mock_symlink:
            mock_engine._create_skill_link(source, target)
            mock_symlink.assert_called_once_with(source, target_is_directory=True)


def test_create_skill_link_windows_fallback(mock_engine, tmp_path):
    import sys

    source = tmp_path / "source"
    source.mkdir()
    target = tmp_path / "target"

    if sys.platform == "win32":
        with patch.object(Path, "symlink_to", side_effect=OSError("Admin required")):
            mock_engine._create_skill_link(source, target)
        assert target.is_junction()
        assert target.resolve() == source.resolve()
        mock_engine._safe_remove_link(target)
        assert not os.path.lexists(target)
    else:
        with patch("os.name", "nt"):
            with patch.object(
                Path, "symlink_to", side_effect=OSError("Admin required")
            ):
                with patch.dict("sys.modules", {"_winapi": MagicMock()}) as _:
                    mock_engine._create_skill_link(source, target)
                    sys.modules["_winapi"].CreateJunction.assert_called_once_with(
                        str(source), str(target)
                    )


def test_safe_remove_link_windows_dir(mock_engine, tmp_path):
    import stat

    target = tmp_path / "link_dir"
    target.mkdir()

    fake_stat = MagicMock(st_file_attributes=stat.FILE_ATTRIBUTE_DIRECTORY | 0x400)
    with patch("os.name", "nt"):
        with patch("core.link_manager.is_windows_link", return_value=True):
            with patch.object(Path, "lstat", return_value=fake_stat):
                with patch("os.rmdir") as mock_rmdir:
                    mock_engine._safe_remove_link(target)
                    mock_rmdir.assert_called_once_with(target)


def test_safe_remove_dangling_windows_junction_is_cleaned(mock_engine, tmp_path):
    import sys

    if sys.platform != "win32":
        pytest.skip("Windows junction test")
    import _winapi

    source = tmp_path / "R&D src"
    source.mkdir()
    target = tmp_path / "R&D link"
    _winapi.CreateJunction(str(source), str(target))
    source.rmdir()
    assert not target.exists()
    assert os.path.lexists(target)
    mock_engine._safe_remove_link(target)
    assert not os.path.lexists(target)


def test_is_windows_link_detection(mock_engine, tmp_path):
    path = tmp_path / "fake_link"
    path.touch()

    # 1. Test symlink (cross-platform)
    with patch.object(Path, "is_symlink", return_value=True):
        assert mock_engine._is_windows_link(path) is True

    # 2. Test Windows Junction via reparse point attribute
    with patch.object(Path, "is_symlink", return_value=False):
        with patch.object(Path, "lstat") as mock_lstat:
            mock_stat = MagicMock()
            # Simulate Windows-only attribute
            mock_stat.st_file_attributes = 1024
            mock_lstat.return_value = mock_stat

            assert mock_engine._is_windows_link(path) is True

    # 3. Normal non-link directory is not treated as a Windows link
    with patch.object(Path, "is_symlink", return_value=False):
        with patch.object(Path, "is_junction", return_value=False):
            with patch.object(Path, "lstat") as mock_lstat:
                mock_lstat.return_value = MagicMock(st_file_attributes=0)
                assert mock_engine._is_windows_link(path) is False


def test_resolve_path_token(mock_engine, tmp_path):
    # $CWD resolution
    with patch("pathlib.Path.cwd", return_value=tmp_path):
        resolved = mock_engine.config_manager.resolve_path_token("$CWD/subdir")
        assert resolved == tmp_path / "subdir"

    # $CODEAGENT resolution
    resolved = mock_engine.config_manager.resolve_path_token("$CODEAGENT/core")
    assert resolved == (mock_engine.root_dir / "core").resolve()


def test_get_skill_search_roots_with_mapping(mock_engine, tmp_path, monkeypatch):
    custom_skills = tmp_path / "custom_skills"
    custom_skills.mkdir()

    # Configure mapping in engine (must sync with config_manager)
    mock_engine.full_config["skills"] = {
        "project_skill_root_mapping": [
            {"pattern": ".*mapped.*", "path": str(custom_skills)}
        ]
    }
    mock_engine.config_manager.full_config = mock_engine.full_config

    # Test mapping hit
    mapped_dir = tmp_path / "mapped_project"
    mapped_dir.mkdir()
    monkeypatch.chdir(mapped_dir)

    roots = mock_engine._get_skill_search_roots()
    assert custom_skills.resolve() in roots
    assert (mapped_dir / "skills").resolve() not in roots  # Not a dir yet

    # Test project-local skills discovery
    project_skills = mapped_dir / "skills"
    project_skills.mkdir()
    roots = mock_engine._get_skill_search_roots()
    assert project_skills.resolve() in roots


def test_ensure_plugins_link(mock_engine, tmp_path, monkeypatch):
    # Setup global extensions dir
    global_ext = tmp_path / "global_ext"
    global_ext.mkdir()
    monkeypatch.setattr(mock_engine, "_get_plugin_link_dir", lambda: global_ext)

    # Setup a plugin
    plugin_dir = tmp_path / "my-plugin"
    plugin_dir.mkdir()
    (plugin_dir / "AGENTS.md").touch()

    monkeypatch.setattr(
        mock_engine,
        "get_plugins_to_mount",
        lambda: [{"name": "my-plugin", "_plugin_dir": str(plugin_dir)}],
    )

    mock_engine.ensure_plugins_link()

    assert (global_ext / "my-plugin").exists()
    assert (global_ext / "my-plugin").resolve() == plugin_dir.resolve()

    # Cleanup
    mock_engine.cleanup_plugins_link()
    assert not (global_ext / "my-plugin").exists()


def test_load_manifest_corrupted_json_returns_empty(tmp_path):
    from core.link_manager import LINK_MANIFEST, LinkManager

    mgr = LinkManager()
    manifest_file = tmp_path / LINK_MANIFEST
    manifest_file.write_text("{ corrupt json: ...", encoding="utf-8")
    result = mgr.load_manifest(tmp_path)
    assert result == {}

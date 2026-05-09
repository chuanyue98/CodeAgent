import os
from core.plugin_scanner import PluginScanner, get_plugins_to_mount
from core.engine_base import BaseEngine


class DummyEngine(BaseEngine):
    def __init__(self):
        # We don't need a real root_dir for these tests as we'll monkeypatch search roots
        super().__init__("Dummy", "dummy-model")


def test_plugin_scanner_scan(tmp_path):
    plugins_root = tmp_path / "plugins"
    cat_dir = plugins_root / "base"
    cat_dir.mkdir(parents=True)
    (cat_dir / "test-plugin").mkdir()

    scanner = PluginScanner(plugins_root)
    result = scanner.scan()

    assert "base" in result
    assert "test-plugin" in result["base"]


def test_plugin_scanner_empty(tmp_path):
    scanner = PluginScanner(tmp_path / "non_existent")
    assert scanner.scan() == {}


def test_get_plugins_to_mount(tmp_path, monkeypatch):
    config = {"groups": {"common": {"plugins": ["base/plugin1"]}}}

    # Create global plugin root
    global_plugins = tmp_path / "global_plugins"
    (global_plugins / "base" / "plugin1").mkdir(parents=True)
    scanner = PluginScanner(global_plugins)

    # Mock CWD to something else
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    monkeypatch.chdir(project_dir)

    # Create local plugin
    (project_dir / "plugins" / "local" / "local-plugin").mkdir(parents=True)

    plugins = get_plugins_to_mount(config, scanner, "common")
    plugin_names = [p["name"] for p in plugins]
    assert "plugin1" in plugin_names
    assert "local-plugin" in plugin_names


def test_ensure_plugins_link(tmp_path, monkeypatch):
    engine = DummyEngine()

    project_root = tmp_path / "project"
    project_root.mkdir()
    monkeypatch.chdir(project_root)

    # Mock global extensions directory to a temporary path
    mock_global_exts = tmp_path / "global_exts"
    mock_global_exts.mkdir()
    monkeypatch.setattr(engine, "_get_plugin_link_dir", lambda: mock_global_exts)

    plugin_root = tmp_path / "global_plugins"
    plugin_dir = plugin_root / "base" / "test-plugin"
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "info.txt").write_text("hello")

    monkeypatch.setattr(
        engine,
        "get_plugins_to_mount",
        lambda: [
            {"name": "test-plugin", "_plugin_dir": str(plugin_dir.resolve().as_posix())}
        ],
    )
    monkeypatch.setattr(engine, "_get_plugin_search_roots", lambda: [plugin_root])

    engine.ensure_plugins_link()

    mounted_path = mock_global_exts / "test-plugin"
    assert mounted_path.exists()
    if os.name == "nt":
        assert engine._is_windows_link(mounted_path)
    else:
        assert mounted_path.is_symlink()

    assert (mounted_path / "info.txt").read_text() == "hello"

    # Test cleanup
    engine.cleanup_plugins_link()
    assert not mounted_path.exists()


def test_assemble_prompt_basic(tmp_path, monkeypatch):
    engine = DummyEngine()
    monkeypatch.setattr(engine, "get_prompts_to_inject", lambda: ["base"])

    import core.engine_base

    # Mock prompt_general
    monkeypatch.setattr(
        core.engine_base,
        "prompt_general",
        lambda task, groups, extra_contents=None: f"Base Prompt Groups={groups}",
    )

    prompt = engine.assemble_prompt()
    assert "Base Prompt" in prompt
    assert "Groups=['base']" in prompt

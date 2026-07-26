from core.services.plugin_service import PluginService


def test_get_detailed_plugins_extracts_description_from_readme(tmp_path):
    plugins_root = tmp_path / "plugins"
    plugin_dir = plugins_root / "base" / "greeter"
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "README.md").write_text(
        "# Greeter\n\nSays hello to the user.\n", encoding="utf-8"
    )

    service = PluginService(plugins_root)
    detailed = service.get_detailed_plugins()

    assert list(detailed.keys()) == ["base"]
    plugin = detailed["base"][0]
    assert plugin["name"] == "greeter"
    assert plugin["id"] == "base/greeter"
    assert plugin["description"] == "Says hello to the user."
    assert "Says hello to the user." in plugin["readme"]


def test_get_detailed_plugins_defaults_when_no_readme(tmp_path):
    plugins_root = tmp_path / "plugins"
    plugin_dir = plugins_root / "base" / "bare"
    plugin_dir.mkdir(parents=True)

    service = PluginService(plugins_root)
    detailed = service.get_detailed_plugins()

    plugin = detailed["base"][0]
    assert plugin["description"] == "Plugin from base"
    assert "No README available" in plugin["readme"]


def test_get_detailed_plugins_defaults_when_readme_has_only_headings(tmp_path):
    plugins_root = tmp_path / "plugins"
    plugin_dir = plugins_root / "base" / "headings-only"
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "README.md").write_text("# Title\n## Subtitle\n", encoding="utf-8")

    service = PluginService(plugins_root)
    detailed = service.get_detailed_plugins()

    plugin = detailed["base"][0]
    assert plugin["description"] == "Plugin from base"
    assert plugin["readme"] == "# Title\n## Subtitle\n"


def test_get_detailed_plugins_multiple_categories_and_plugins(tmp_path):
    plugins_root = tmp_path / "plugins"
    for category, name in [("base", "a"), ("base", "b"), ("web", "c")]:
        (plugins_root / category / name).mkdir(parents=True)

    service = PluginService(plugins_root)
    detailed = service.get_detailed_plugins()

    assert sorted(detailed.keys()) == ["base", "web"]
    assert {p["name"] for p in detailed["base"]} == {"a", "b"}
    assert {p["name"] for p in detailed["web"]} == {"c"}


def test_get_detailed_plugins_empty_root_returns_empty_dict(tmp_path):
    service = PluginService(tmp_path / "missing")
    assert service.get_detailed_plugins() == {}

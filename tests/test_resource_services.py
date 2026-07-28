from core.services.plugin_service import PluginService
from core.services.skill_service import SkillService


def test_skill_metadata_extraction(tmp_path):
    skills_root = tmp_path / "skills"
    skill_dir = skills_root / "base" / "test-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\ndescription: test desc\n---\nbody content", encoding="utf-8"
    )

    service = SkillService(skills_root)
    skills = service.get_detailed_skills()

    assert "base" in skills
    assert skills["base"][0]["name"] == "test-skill"
    assert skills["base"][0]["description"] == "test desc"
    assert "body content" in skills["base"][0]["readme"]


def test_plugin_metadata_extraction(tmp_path):
    plugins_root = tmp_path / "plugins"
    plugin_dir = plugins_root / "base" / "test-plugin"
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "README.md").write_text(
        "# Test Plugin\n\nThis is a test plugin description.", encoding="utf-8"
    )

    service = PluginService(plugins_root)
    plugins = service.get_detailed_plugins()

    assert "base" in plugins
    assert plugins["base"][0]["name"] == "test-plugin"
    assert "test plugin description" in plugins["base"][0]["description"].lower()
    assert "This is a test plugin description." in plugins["base"][0]["readme"]

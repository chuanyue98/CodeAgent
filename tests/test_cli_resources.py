"""``ca resources list`` 的 CLI 测试。"""

from unittest.mock import patch

import ca_launcher


def _run(monkeypatch, *argv, config=None):
    monkeypatch.setattr("sys.argv", ["ca_launcher.py", *argv])
    if config is not None:
        monkeypatch.setattr("core.cli.helpers.load_config", lambda: config)
    return ca_launcher.main()


CONFIG = {"groups": {"codeagent": {"skills": ["base/one"], "prompts": ["base"]}}}


class FakeSkillService:
    def __init__(self, skills):
        self._skills = skills

    def get_detailed_skills(self):
        return self._skills


def test_skills_list_marks_the_enabled_ones(monkeypatch, capsys):
    skills = {
        "base": [
            {"id": "base/one", "description": "First skill"},
            {"id": "base/two", "description": ""},
        ]
    }
    with patch(
        "core.services.skill_service.SkillService",
        lambda root: FakeSkillService(skills),
    ):
        _run(monkeypatch, "resources", "list", "skills", config=CONFIG)

    out = capsys.readouterr().out
    assert "Skills (2) — enabled in 'codeagent'" in out
    assert "● base/one — First skill" in out
    assert "○ base/two" in out


def test_skills_list_group_flag_changes_the_enabled_view(monkeypatch, capsys):
    skills = {"base": [{"id": "base/one", "description": ""}]}
    with patch(
        "core.services.skill_service.SkillService",
        lambda root: FakeSkillService(skills),
    ):
        _run(
            monkeypatch,
            "resources",
            "list",
            "skills",
            "--group",
            "common",
            config=CONFIG,
        )
    out = capsys.readouterr().out
    assert "enabled in 'common'" in out
    assert "○ base/one" in out


def test_empty_kind_says_nothing_was_found(monkeypatch, capsys):
    with patch(
        "core.services.skill_service.SkillService",
        lambda root: FakeSkillService({}),
    ):
        _run(monkeypatch, "resources", "list", "skills", config=CONFIG)
    assert "No skills found." in capsys.readouterr().out


def test_prompts_list_uses_the_prompt_service(monkeypatch, capsys):
    class FakePromptService:
        def __init__(self, root, root_dir):
            pass

        def get_prompt_groups(self):
            return [
                {"id": "base", "description": "Base prompts"},
                {"id": "work", "description": ""},
            ]

    with patch("core.services.prompt_service.PromptService", FakePromptService):
        _run(monkeypatch, "resources", "list", "prompts", config=CONFIG)

    out = capsys.readouterr().out
    assert "Prompts (2)" in out
    assert "● base — Base prompts" in out
    assert "○ work" in out

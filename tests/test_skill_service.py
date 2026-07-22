from core.services.skill_service import SkillService


def _write_skill(skills_root, category, name, content):
    skill_dir = skills_root / category / name
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(content, encoding="utf-8")
    return skill_dir


def test_get_detailed_skills_extracts_description_from_frontmatter(tmp_path):
    skills_root = tmp_path / "skills"
    _write_skill(
        skills_root,
        "base",
        "greeter",
        "---\ndescription: Greets the user politely\n---\n\n# Greeter\n\nBody text.\n",
    )

    service = SkillService(skills_root)
    detailed = service.get_detailed_skills()

    assert list(detailed.keys()) == ["base"]
    skill = detailed["base"][0]
    assert skill["name"] == "greeter"
    assert skill["id"] == "base/greeter"
    assert skill["description"] == "Greets the user politely"
    assert "Body text." in skill["readme"]
    assert skill["scripts"] == []


def test_get_detailed_skills_falls_back_to_first_non_heading_line(tmp_path):
    skills_root = tmp_path / "skills"
    _write_skill(
        skills_root,
        "base",
        "no-frontmatter",
        "# Title\n\nThis is the fallback description.\nMore text.\n",
    )

    service = SkillService(skills_root)
    detailed = service.get_detailed_skills()

    assert detailed["base"][0]["description"] == "This is the fallback description."


def test_get_detailed_skills_handles_malformed_frontmatter_gracefully(tmp_path):
    skills_root = tmp_path / "skills"
    _write_skill(
        skills_root,
        "base",
        "bad-frontmatter",
        "---\n[unclosed\n---\n\nFallback line here.\n",
    )

    service = SkillService(skills_root)
    detailed = service.get_detailed_skills()

    # yaml.safe_load raises on the unclosed flow sequence, so the code
    # falls back to scanning raw lines of the *whole* file for the first
    # non-empty line that isn't a heading or a "---" delimiter. That scan
    # starts from the top of the file (not after the frontmatter block),
    # so it lands on "[unclosed" rather than the later prose line -- this
    # pins down that real (if surprising) fallback behavior.
    assert detailed["base"][0]["description"] == "[unclosed"


def test_get_detailed_skills_lists_scripts(tmp_path):
    skills_root = tmp_path / "skills"
    skill_dir = _write_skill(skills_root, "base", "scripted", "content")
    scripts_dir = skill_dir / "scripts"
    scripts_dir.mkdir()
    (scripts_dir / "run.py").write_text("print('hi')", encoding="utf-8")
    (scripts_dir / "b.sh").write_text("echo hi", encoding="utf-8")
    (scripts_dir / ".hidden").write_text("secret", encoding="utf-8")
    (scripts_dir / "subdir").mkdir()

    service = SkillService(skills_root)
    detailed = service.get_detailed_skills()

    assert detailed["base"][0]["scripts"] == ["b.sh", "run.py"]


def test_get_detailed_skills_excludes_dirs_without_skill_md(tmp_path):
    # SkillScanner only counts a directory as a skill if it has SKILL.md,
    # so a category containing only such directories never shows up.
    skills_root = tmp_path / "skills"
    (skills_root / "base" / "bare").mkdir(parents=True)

    service = SkillService(skills_root)
    detailed = service.get_detailed_skills()

    assert detailed == {}


def test_get_detailed_skills_empty_root_returns_empty_dict(tmp_path):
    service = SkillService(tmp_path / "missing")
    assert service.get_detailed_skills() == {}

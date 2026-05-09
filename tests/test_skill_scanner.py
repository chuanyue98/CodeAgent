from core.skill_scanner import SkillScanner


def test_skill_scanner_scan_returns_tuple(tmp_path):
    skills_root = tmp_path / "skills"
    base_dir = skills_root / "base"
    base_dir.mkdir(parents=True)
    skill_dir = base_dir / "test-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("content", encoding="utf-8")

    scanner = SkillScanner(skills_root)
    result, warnings = scanner.scan()

    assert result == {"base": ["test-skill"]}
    assert warnings == []


def test_skill_scanner_scan_handles_missing_root(tmp_path):
    skills_root = tmp_path / "non-existent"
    scanner = SkillScanner(skills_root)
    result, warnings = scanner.scan()
    assert result == {}
    assert warnings == []


def test_skill_scanner_scan_warns_on_missing_skill_md(tmp_path):
    skills_root = tmp_path / "skills"
    base_dir = skills_root / "base"
    base_dir.mkdir(parents=True)
    skill_dir = base_dir / "invalid-skill"
    skill_dir.mkdir()
    # No SKILL.md

    scanner = SkillScanner(skills_root)
    result, warnings = scanner.scan()

    assert result == {}
    assert len(warnings) == 1
    assert "does not contain SKILL.md" in warnings[0]

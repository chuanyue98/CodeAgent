from core.services.prompt_service import PromptService


def test_get_prompt_groups_combines_files_and_extracts_description(tmp_path):
    prompts_root = tmp_path / "prompts"
    group_dir = prompts_root / "base"
    group_dir.mkdir(parents=True)
    (group_dir / "first.md").write_text(
        "# First\n\nDo the first thing.\n", encoding="utf-8"
    )
    (group_dir / "second.md").write_text(
        "# Second\n\nDo the second thing.\n", encoding="utf-8"
    )

    service = PromptService(prompts_root, tmp_path)
    groups = service.get_prompt_groups()

    assert len(groups) == 1
    group = groups[0]
    assert group["id"] == "base"
    assert group["name"] == "base"
    assert group["description"] == "Do the first thing."
    assert [f["name"] for f in group["files"]] == ["first", "second"]
    assert "## first" in group["readme"]
    assert "## second" in group["readme"]
    assert group["files"][0]["path"] == str(
        (group_dir / "first.md").resolve().as_posix()
    )


def test_get_prompt_groups_skips_excluded_files(tmp_path):
    prompts_root = tmp_path / "prompts"
    group_dir = prompts_root / "base"
    group_dir.mkdir(parents=True)
    (group_dir / "README.md").write_text("Should be excluded", encoding="utf-8")
    (group_dir / "IMPLEMENTATION_PLAN.md").write_text(
        "Should also be excluded", encoding="utf-8"
    )
    (group_dir / "kept.md").write_text("Kept content", encoding="utf-8")

    service = PromptService(prompts_root, tmp_path)
    groups = service.get_prompt_groups()

    assert [f["name"] for f in groups[0]["files"]] == ["kept"]


def test_get_prompt_groups_skips_empty_files(tmp_path):
    prompts_root = tmp_path / "prompts"
    group_dir = prompts_root / "base"
    group_dir.mkdir(parents=True)
    (group_dir / "empty.md").write_text("   \n\n", encoding="utf-8")

    service = PromptService(prompts_root, tmp_path)
    groups = service.get_prompt_groups()

    assert groups[0]["files"] == []
    assert groups[0]["description"] == "0 prompt files in 'base'"


def test_get_prompt_groups_sorted_by_category(tmp_path):
    prompts_root = tmp_path / "prompts"
    for category in ["web", "base", "coding"]:
        group_dir = prompts_root / category
        group_dir.mkdir(parents=True)
        (group_dir / "sample.md").write_text("content", encoding="utf-8")

    service = PromptService(prompts_root, tmp_path)
    groups = service.get_prompt_groups()

    assert [g["id"] for g in groups] == ["base", "coding", "web"]


def test_get_prompt_groups_empty_root_returns_empty_list(tmp_path):
    service = PromptService(tmp_path / "missing", tmp_path)
    assert service.get_prompt_groups() == []

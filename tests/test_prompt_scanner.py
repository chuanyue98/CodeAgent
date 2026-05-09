from core.prompt_scanner import PromptScanner, get_prompts_to_inject


def test_prompt_scanner_scan(tmp_path):
    prompt_root = tmp_path / "prompt"
    group1 = prompt_root / "group1"
    group1.mkdir(parents=True)
    (group1 / "prompt1.md").write_text("content", encoding="utf-8")
    (group1 / "README.md").write_text("readme", encoding="utf-8")

    scanner = PromptScanner(prompt_root)
    result, warnings = scanner.scan()

    assert result == {"group1": ["prompt1"]}
    assert warnings == []


def test_get_prompts_to_inject_uses_configured_group_prompts(tmp_path):
    prompt_root = tmp_path / "prompt"
    for group in ["base", "engineering", "coding", "web"]:
        group_dir = prompt_root / group
        group_dir.mkdir(parents=True)
        (group_dir / "sample.md").write_text("content", encoding="utf-8")

    scanner = PromptScanner(prompt_root)
    config = {
        "groups": {
            "web": {
                "prompts": ["base", "web"],
            }
        }
    }

    prompts = get_prompts_to_inject(config, scanner, project_type="web")

    assert prompts == ["base", "web"]


def test_get_prompts_to_inject_falls_back_to_default_mapping(tmp_path):
    prompt_root = tmp_path / "prompt"
    for group in ["base", "engineering", "coding", "work"]:
        group_dir = prompt_root / group
        group_dir.mkdir(parents=True)
        (group_dir / "sample.md").write_text("content", encoding="utf-8")

    scanner = PromptScanner(prompt_root)

    prompts = get_prompts_to_inject({}, scanner, project_type="work")

    assert prompts == ["base", "engineering", "coding", "work"]


def test_get_prompts_to_inject_respects_explicit_empty_prompt_config(tmp_path):
    prompt_root = tmp_path / "prompt"
    for group in ["base", "engineering", "coding", "work"]:
        group_dir = prompt_root / group
        group_dir.mkdir(parents=True)
        (group_dir / "sample.md").write_text("content", encoding="utf-8")

    scanner = PromptScanner(prompt_root)
    config = {
        "groups": {
            "work": {
                "prompts": [],
            }
        }
    }

    prompts = get_prompts_to_inject(config, scanner, project_type="work")

    assert prompts == []

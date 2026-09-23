from core.prompt_scanner import PromptScanner


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

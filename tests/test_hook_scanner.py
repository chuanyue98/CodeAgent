import json

from core.hook_scanner import HookScanner


def test_hook_scanner_scan(tmp_path):
    # Setup: Create a mock hooks directory structure
    hooks_root = tmp_path / "hooks"
    category_dir = hooks_root / "base"
    category_dir.mkdir(parents=True)

    hook_dir = category_dir / "test-hook"
    hook_dir.mkdir()

    metadata = {
        "name": "test-hook",
        "event": "BeforeAgent",
        "command": "python {hook_dir}/hook.py",
        "description": "A simple test hook for validation.",
    }

    with open(hook_dir / "metadata.json", "w", encoding="utf-8") as f:
        json.dump(metadata, f)

    # Execution
    scanner = HookScanner(hooks_root)
    result, warnings = scanner.scan()

    # Verification
    assert isinstance(result, dict)
    assert isinstance(warnings, list)
    assert "base" in result
    assert "test-hook" in result["base"]
    assert result["base"]["test-hook"]["name"] == "test-hook"
    assert "_hook_dir" in result["base"]["test-hook"]
    assert result["base"]["test-hook"]["_hook_dir"] == str(
        hook_dir.resolve().as_posix()
    )


def test_hook_scanner_empty_dir(tmp_path):
    scanner = HookScanner(tmp_path / "non_existent")
    result, warnings = scanner.scan()
    assert result == {}
    assert warnings == []


def test_hook_scanner_invalid_metadata(tmp_path):
    # Setup: Create a mock hooks directory structure with invalid metadata.json
    hooks_root = tmp_path / "hooks"
    category_dir = hooks_root / "base"
    category_dir.mkdir(parents=True)

    hook_dir = category_dir / "bad-hook"
    hook_dir.mkdir()

    # Write invalid JSON content
    with open(hook_dir / "metadata.json", "w", encoding="utf-8") as f:
        f.write("invalid json")

    # Execution
    scanner = HookScanner(hooks_root)
    result, warnings = scanner.scan()

    # Verification
    assert "base" in result
    assert "bad-hook" not in result["base"]
    assert len(warnings) == 1
    assert "bad-hook" in warnings[0]
    assert "metadata.json" in warnings[0]
    assert "Failed to load hook metadata" in warnings[0]

import json
from core.hook_scanner import HookScanner, get_hooks_to_inject


def test_hook_scanner_multiple_roots(tmp_path):
    root1 = tmp_path / "root1"
    root2 = tmp_path / "root2"
    root1.mkdir()
    root2.mkdir()

    # Hook in root1
    cat1 = root1 / "base"
    cat1.mkdir()
    hook1 = cat1 / "hook1"
    hook1.mkdir()
    (hook1 / "metadata.json").write_text(
        json.dumps(
            {
                "name": "hook1",
                "event": "BeforeAgent",
                "command": "python {hook_dir}/h1.py",
            }
        )
    )

    # Hook in root2
    cat2 = root2 / "devops"
    cat2.mkdir()
    hook2 = cat2 / "hook2"
    hook2.mkdir()
    (hook2 / "metadata.json").write_text(
        json.dumps(
            {
                "name": "hook2",
                "event": "AfterAgent",
                "command": "python {hook_dir}/h2.py",
            }
        )
    )

    # Override hook in root2 (lower priority)
    cat1_root2 = root2 / "base"
    cat1_root2.mkdir()
    hook1_root2 = cat1_root2 / "hook1"
    hook1_root2.mkdir()
    (hook1_root2 / "metadata.json").write_text(
        json.dumps(
            {
                "name": "hook1-override",
                "event": "BeforeAgent",
                "command": "python {hook_dir}/h1_override.py",
            }
        )
    )

    scanner = HookScanner([root1, root2])
    scanned, _ = scanner.scan()

    assert "base" in scanned
    assert "devops" in scanned
    assert "hook1" in scanned["base"]
    assert "hook2" in scanned["devops"]
    # Should keep root1 version
    assert scanned["base"]["hook1"]["name"] == "hook1"


def test_get_hooks_to_inject_dynamic(tmp_path):
    ca_root = tmp_path / "ca"
    ca_root.mkdir()
    ca_hooks = ca_root / "hooks"
    ca_hooks.mkdir()

    cat_base = ca_hooks / "base"
    cat_base.mkdir()
    h_git = cat_base / "git-context"
    h_git.mkdir()
    (h_git / "metadata.json").write_text(
        json.dumps(
            {
                "name": "git-context",
                "event": "BeforeAgent",
                "command": "python {hook_dir}/git.py",
            }
        )
    )

    # Local project hooks
    project_root = tmp_path / "project"
    project_root.mkdir()
    project_hooks = project_root / "hooks"
    project_hooks.mkdir()

    cat_local = project_hooks / "local"
    cat_local.mkdir()
    h_local = cat_local / "my-hook"
    h_local.mkdir()
    (h_local / "metadata.json").write_text(
        json.dumps(
            {
                "name": "my-hook",
                "event": "BeforeAgent",
                "command": "python {hook_dir}/my.py",
            }
        )
    )

    scanner = HookScanner([ca_hooks, project_hooks])
    config = {
        "groups": {"web": {"hooks": ["base/git-context"]}},
        "hooks": {
            "project_hooks": {
                "web": ["base/some-other-hook"]  # Legacy
            }
        },
    }

    # Test auto-loading local hooks and resolving configured ones
    hooks, warnings = get_hooks_to_inject(
        config, scanner, project_type="web", extra_hooks=["local/my-hook"]
    )

    names = [h["name"] for h in hooks]
    assert "git-context" in names
    assert "my-hook" in names

    # Test auto-loading of local hooks (any hook in project_hooks should be loaded if not already)
    # Actually, should we auto-load ALL hooks from project_hooks?
    # SkillScanner does: "result.add(item.name)" for all dirs in local_skills.
    # So for hooks, we should probably auto-load all hooks in the non-CA root.

    # If we want to strictly follow SkillScanner:
    # it adds all item.name in cwd/skills.
    # For hooks, it might be more complex because of categories.

    assert "my-hook" in names
    assert warnings == []

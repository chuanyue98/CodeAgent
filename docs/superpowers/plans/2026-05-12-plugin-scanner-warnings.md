# PluginScanner Warnings Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor `PluginScanner` to return explicit warnings when metadata loading fails.

**Architecture:** Update `scan()` to return `(data, warnings)` tuple. Use `try...except` for robust error handling during scanning.

**Tech Stack:** Python, pytest.

---

### Task 1: Update PluginScanner.scan

**Files:**
- Modify: `core/plugin_scanner.py`

- [ ] **Step 1: Modify `PluginScanner.scan` return type and add error handling**

```python
    def scan(self) -> tuple[Dict[str, Dict[str, Any]], List[str]]:
        """Scans the plugins root directory for categories and plugin metadata.

        Returns:
            A tuple containing:
            - A dictionary mapping category names to dictionaries of plugin metadata.
            - A list of warning strings.
        """
        result = {}
        warnings = []
        if not self.plugins_root.exists():
            return result, warnings

        for category_dir in self.plugins_root.iterdir():
            if not category_dir.is_dir():
                continue
            category = category_dir.name
            plugins = {}
            for item in category_dir.iterdir():
                if not item.is_dir():
                    continue

                # Validation: Look for metadata.json or some common markers
                metadata_path = item / "metadata.json"
                metadata = {}
                if metadata_path.exists():
                    try:
                        with open(metadata_path, "r", encoding="utf-8") as f:
                            metadata = json.load(f)
                    except Exception as e:
                        import os
                        msg = f"Failed to load metadata from {metadata_path}: {e}"
                        warnings.append(msg)
                        if os.getenv("CA_DEBUG"):
                            import traceback
                            traceback.print_exc()
                        continue

                # Basic info
                metadata["name"] = item.name
                metadata["_plugin_dir"] = str(item.resolve().as_posix())
                # ... rest of the method
```

- [ ] **Step 2: Update `get_plugins_to_mount` to handle tuple**

```python
def get_plugins_to_mount(
    config: dict,
    scanner: PluginScanner,
    project_type: str = "common",
) -> List[Dict[str, Any]]:
    # ...
    scanned, scan_warnings = scanner.scan()
    # Log or handle scan_warnings if needed (at least unpack them)
    result_map = {}
    # ...
    if cwd.resolve() != Path(__file__).resolve().parent.parent.resolve():
        local_plugins = cwd / "plugins"
        if local_plugins.exists():
            # Scan local plugins
            local_scanner = PluginScanner(local_plugins)
            local_scanned, local_warnings = local_scanner.scan()
            # ...
```

### Task 2: Update and Add Tests

**Files:**
- Modify: `tests/test_plugin.py`

- [ ] **Step 1: Update existing tests to expect tuple**
- [ ] **Step 2: Add `test_plugin_scanner_invalid_json`**

```python
def test_plugin_scanner_invalid_json(tmp_path, monkeypatch):
    plugins_root = tmp_path / "plugins"
    cat_dir = plugins_root / "base"
    cat_dir.mkdir(parents=True)
    plugin_dir = cat_dir / "bad-plugin"
    plugin_dir.mkdir()
    (plugin_dir / "metadata.json").write_text("{ invalid json }")

    scanner = PluginScanner(plugins_root)
    result, warnings = scanner.scan()

    assert "base" not in result
    assert len(warnings) == 1
    assert "Failed to load metadata" in warnings[0]
```

- [ ] **Step 3: Run all tests**
Run: `pytest tests/test_plugin.py`
Expected: ALL PASS

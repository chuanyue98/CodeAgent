# Refactor PromptScanner to Return Warnings Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor `PromptScanner.scan` to return a `tuple[Dict[str, List[str]], List[str]]` containing data and warnings, and update all call sites.

**Architecture:** Following the "explicit tuple return" pattern already used in `PluginScanner` and `HookScanner`.

**Tech Stack:** Python

---

### Task 1: Refactor PromptScanner.scan and get_prompts_to_inject

**Files:**
- Modify: `core/prompt_scanner.py`

- [ ] **Step 1: Modify `PromptScanner.scan` return type and implementation**

```python
    def scan(self) -> tuple[Dict[str, List[str]], List[str]]:
        """Scans the prompt root directory for prompt groups and files.

        Returns:
            A tuple containing:
            - A dictionary mapping group names to lists of prompt names (file stems).
            - A list of warning strings.
        """
        result = {}
        warnings = []
        if not self.prompt_root.exists():
            return result, warnings

        try:
            for group_dir in self.prompt_root.iterdir():
                if not group_dir.is_dir():
                    continue
                group = group_dir.name
                prompts = []
                try:
                    for md_file in group_dir.glob("*.md"):
                        if md_file.stem not in ("README", "IMPLEMENTATION_PLAN"):
                            prompts.append(md_file.stem)
                except Exception as e:
                    warnings.append(f"Failed to scan directory {group_dir}: {e}")
                    continue

                if prompts:
                    result[group] = prompts
        except Exception as e:
            warnings.append(f"Failed to iterate prompt root {self.prompt_root}: {e}")

        return result, warnings
```

- [ ] **Step 2: Update `get_prompts_to_inject` to handle tuple return**

```python
def get_prompts_to_inject(
    config: dict,
    scanner: PromptScanner,
    project_type: str = "common",
    extra_prompts: List[str] = None,
) -> List[str]:
    # ...
    scanned, scan_warnings = scanner.scan()
    # ...
```

### Task 2: Update Call Sites

**Files:**
- Modify: `core/services/prompt_service.py`
- Modify: `core/web/server.py`

- [ ] **Step 1: Update `core/services/prompt_service.py`**

```python
    def get_prompt_groups(self) -> list[dict]:
        # ...
        scanned, _ = self.scanner.scan()
        # ...
```

- [ ] **Step 2: Update `core/web/server.py`**

```python
    # ...
    prompt_scanner = PromptScanner(prompts_root)
    scanned_prompts, _ = prompt_scanner.scan()
    # ...
```

### Task 3: Update Tests

**Files:**
- Modify: `tests/test_prompt_scanner.py`

- [ ] **Step 1: Update tests to assert tuple return**

- [ ] **Step 2: Run tests**

Run: `pytest tests/test_prompt_scanner.py`

---

## Verification Plan

- Run `pytest tests/test_prompt_scanner.py`
- Run `pytest tests/test_resource_services.py` (which likely uses `PromptService`)
- Run `pytest tests/test_web_api.py` (which likely triggers `server.py` logic)

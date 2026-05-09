# Refactor SkillScanner Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor `SkillScanner.scan` to return a tuple of `(result, warnings)` and update all callers.

**Architecture:** Change the return type of `SkillScanner.scan` from `Dict[str, List[str]]` to `tuple[Dict[str, List[str]], List[str]]`. Callers will unpack this tuple.

**Tech Stack:** Python 3.x, pytest, FastAPI.

---

### Task 1: Refactor SkillScanner.scan

**Files:**
- Modify: `core/skill_scanner.py`
- Test: `tests/test_skill_scanner.py`

- [ ] **Step 1: Verify current failure**
  The tests already exist and are failing with `ValueError: not enough values to unpack`.
  Run: `python -m pytest tests/test_skill_scanner.py`
  Expected: FAIL (ValueError)

- [ ] **Step 2: Update SkillScanner.scan implementation**
  Modify `core/skill_scanner.py` to return a tuple and handle errors.

```python
    def scan(self) -> tuple[Dict[str, List[str]], List[str]]:
        """Scans the skills root directory for categories and individual skill definitions.

        Returns:
            A tuple containing:
            - A dictionary mapping category names to lists of skill names.
            - A list of warning messages encountered during scanning.
        """
        result: Dict[str, List[str]] = {}
        warnings: List[str] = []
        if not self.skills_root.exists():
            return result, warnings

        try:
            for category_dir in self.skills_root.iterdir():
                if not category_dir.is_dir():
                    continue
                category = category_dir.name
                skills = []
                try:
                    for item in category_dir.iterdir():
                        if item.is_dir():
                            if (item / "SKILL.md").exists():
                                skills.append(item.name)
                            else:
                                warnings.append(f"Skill directory '{item}' does not contain SKILL.md")
                except Exception as e:
                    warnings.append(f"Failed to scan category directory '{category_dir}': {e}")

                if skills:
                    result[category] = skills
        except Exception as e:
            warnings.append(f"Failed to iterate skills root '{self.skills_root}': {e}")

        return result, warnings
```

- [ ] **Step 3: Run tests to verify they pass**
  Run: `python -m pytest tests/test_skill_scanner.py`
  Expected: PASS

### Task 2: Update SkillService

**Files:**
- Modify: `core/services/skill_service.py`

- [ ] **Step 1: Update get_detailed_skills**
  Modify `core/services/skill_service.py` to unpack the result of `self.scanner.scan()`.

```python
    def get_detailed_skills(self) -> dict:
        """Retrieves a detailed dictionary of all scanned skills by category.

        Returns:
            A dictionary mapping categories to lists of skill details.
            Each skill detail includes: name, id, description, and readme (content).
        """
        scanned, warnings = self.scanner.scan()
        # Log warnings if necessary, or just ignore them for now as per requirements
        detailed_skills = {}
        for category, skills in scanned.items():
            # ... existing logic ...
```

- [ ] **Step 2: Verify with tests**
  Run: `python -m pytest tests/test_resource_services.py` (if it exists) or check for regressions.

### Task 3: Update Web Server Initialization

**Files:**
- Modify: `core/web/server.py`

- [ ] **Step 1: Update initialize_default_groups**
  Modify `core/web/server.py` to unpack the result of `skill_scanner.scan()`.

```python
    skills_root, prompts_root, hooks_root = _get_roots()
    groups: dict = config_data.get("groups", {})
    skill_scanner = SkillScanner(skills_root)
    scanned_skills, _ = skill_scanner.scan()
    prompt_scanner = PromptScanner(prompts_root)
```

- [ ] **Step 2: Verify web server starts**
  Run: `python -m core.web.server` (or equivalent start command) or run `tests/test_web_api.py`.
  Run: `python -m pytest tests/test_web_api.py`

### Task 4: Final Verification

- [ ] **Step 1: Run all related tests**
  Run: `python -m pytest tests/test_skill_scanner.py tests/test_resource_services.py tests/test_web_api.py`
  Expected: All PASS

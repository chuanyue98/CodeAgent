# ConfigService Explicit Error Handling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor `ConfigService.get_config` to return `tuple[dict, list[str]]` for explicit error handling and update all callers.

**Architecture:** Use a tuple return type `(data, warnings)` to provide visibility into configuration errors. Catch exceptions during JSON parsing and return them as warnings.

**Tech Stack:** Python, pytest, FastAPI (for routers)

---

### Task 1: Update Tests (TDD - Red Phase)

**Files:**
- Modify: `tests/test_config_service.py`

- [ ] **Step 1: Update existing tests to expect a tuple**
- [ ] **Step 2: Add a test case for malformed JSON**
- [ ] **Step 3: Run tests and verify they fail**

Run: `pytest tests/test_config_service.py`
Expected: FAIL (TypeError or AssertionError due to return type change)

### Task 2: Refactor ConfigService.get_config

**Files:**
- Modify: `core/services/config_service.py`

- [ ] **Step 1: Update `get_config` to return `tuple[dict, list[str]]`**
- [ ] **Step 2: Implement error handling with `try...except` and `CA_DEBUG` support**
- [ ] **Step 3: Update `add_project` and `delete_project` to unpack the tuple**
- [ ] **Step 4: Run tests and verify they pass**

Run: `pytest tests/test_config_service.py`
Expected: PASS

### Task 3: Update Callers in Web Routers

**Files:**
- Modify: `core/web/routers/config.py`

- [ ] **Step 1: Update `list_projects` to unpack `get_config()`**
- [ ] **Step 2: Update `list_groups` to unpack `get_config()`**
- [ ] **Step 3: Update `update_group` to unpack `get_config()`**
- [ ] **Step 4: Update `delete_group` to unpack `get_config()`**
- [ ] **Step 5: Update `get_config` (API endpoint) to unpack and return just the data (or data + warnings depending on API design, for now just the data to avoid breaking UI)**

### Task 4: Final Verification

- [ ] **Step 1: Run all tests**
- [ ] **Step 2: Verify `CA_DEBUG` behavior manually if possible or via a mock test**

# Design Spec: Refactor SkillScanner for Warnings

## 1. Problem Statement
The current `SkillScanner.scan` method only returns a dictionary of discovered skills. It lacks the ability to report issues encountered during the scan, such as directories that are missing the required `SKILL.md` file or permission errors when accessing directories.

## 2. Proposed Changes

### 2.1 SkillScanner (core/skill_scanner.py)
- Change `scan()` return type to `tuple[Dict[str, List[str]], List[str]]`.
- Initialize an empty `warnings` list.
- Wrap the main scanning loop and `iterdir()` calls in `try...except Exception` blocks to catch and record warnings for IO-related failures.
- Add a specific warning if a subdirectory in a category does not contain `SKILL.md`.

### 2.2 SkillService (core/services/skill_service.py)
- Update `get_detailed_skills` to unpack the result and warnings from `self.scanner.scan()`.

### 2.3 Web Server (core/web/server.py)
- Update `initialize_default_groups` to unpack the result and warnings from `skill_scanner.scan()`.

## 3. Architecture and Data Flow
The `scan()` method will now provide a "soft fail" mechanism where it returns as much data as it can along with a list of strings describing what went wrong.

## 4. Error Handling
Non-fatal errors (e.g., single directory permission denied) will be appended to the `warnings` list. Fatal errors (though unlikely for this logic) will still raise exceptions if they indicate a systemic failure.

## 5. Verification Plan
- Run `python -m pytest tests/test_skill_scanner.py` to ensure all tests pass.
- Manually verify that missing `SKILL.md` triggers a warning in the test suite.

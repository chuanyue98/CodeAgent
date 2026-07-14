# Task 2 Report: Graceful Subprocess Cleanup on Shutdown

## Status: DONE

## Files Modified
- [runner_service.py](file:///home/cy/github/chuanyue98/CodeAgent/core/services/runner_service.py) - Implemented `kill_all` on `TaskRunner`.
- [server.py](file:///home/cy/github/chuanyue98/CodeAgent/core/web/server.py) - Called `kill_all` on `chat_runner` and `tasks_runner` inside the lifespan shutdown handler.
- [test_runner_service.py](file:///home/cy/github/chuanyue98/CodeAgent/tests/test_runner_service.py) - Added TDD failing/passing test `test_task_runner_kill_all`.

## Implementation Details

1. **`TaskRunner.kill_all(self)`**:
   - Loops over all running processes in `self._processes`.
   - Attempts to terminate each process gracefully (`process.terminate()`) and waits with a timeout of 1.0 second.
   - Falls back to killing the process (`process.kill()`) if termination fails or raises an error.
   - Updates the status of terminated tasks in `self.active_runs` to `"stopped"`.

2. **Lifespan Shutdown Hook**:
   - Inside FastAPI's `lifespan` function, added imports for `chat_runner` (from `core.web.routers.chat`) and `tasks_runner` (from `core.web.routers.tasks`).
   - Invokes `chat_runner.kill_all()` and `tasks_runner.kill_all()` on application exit, cleaning up any orphaned subprocesses.

## Test Commands and Outputs

### 1. Failing Test Run (Before Implementation)
**Command**:
```bash
.venv/bin/python -m pytest tests/test_runner_service.py -k test_task_runner_kill_all
```
**Output**:
```
============================= test session starts ==============================
platform linux -- Python 3.14.5, pytest-9.0.2, pluggy-1.6.0
rootdir: /home/cy/github/chuanyue98/CodeAgent
configfile: pyproject.toml
plugins: anyio-4.13.0, asyncio-1.3.0, cov-7.0.0
asyncio: mode=Mode.STRICT, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collecting ... collected 5 items / 4 deselected / 1 selected                                  

tests/test_runner_service.py F                                           [100%]

=================================== FAILURES ===================================
__________________________ test_task_runner_kill_all ___________________________

tmp_path = PosixPath('/tmp/pytest-of-cy/pytest-54/test_task_runner_kill_all0')

    def test_task_runner_kill_all(tmp_path):
        from core.services.runner_service import TaskRunner
        import time
        from unittest.mock import MagicMock
        runner = TaskRunner(tmp_path)
        # Start a dummy long-running command (like sleep 10)
        import subprocess
        dummy_proc = subprocess.Popen(["sleep", "10"])
        runner.active_runs["dummy"] = MagicMock(pid=dummy_proc.pid, status="running")
        runner._processes["dummy"] = dummy_proc
    
>       runner.kill_all()
        ^^^^^^^^^^^^^^^
E       AttributeError: 'TaskRunner' object has no attribute 'kill_all'

tests/test_runner_service.py:81: AttributeError
=========================== short test summary info ============================
FAILED tests/test_runner_service.py::test_task_runner_kill_all - AttributeErr...
======================= 1 failed, 4 deselected in 0.03s ========================
```

### 2. Passing Test Run (After Implementation)
**Command**:
```bash
.venv/bin/python -m pytest tests/test_runner_service.py -k test_task_runner_kill_all
```
**Output**:
```
============================= test session starts ==============================
platform linux -- Python 3.14.5, pytest-9.0.2, pluggy-1.6.0
rootdir: /home/cy/github/chuanyue98/CodeAgent
configfile: pyproject.toml
plugins: anyio-4.13.0, asyncio-1.3.0, cov-7.0.0
asyncio: mode=Mode.STRICT, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collecting ... collected 5 items / 4 deselected / 1 selected                                  

tests/test_runner_service.py .                                           [100%]

======================= 1 passed, 4 deselected in 0.11s ========================
```

### 3. Full Test Suite Run
**Command**:
```bash
.venv/bin/python -m pytest
```
**Output**:
```
============================= test session starts ==============================
platform linux -- Python 3.14.5, pytest-9.0.2, pluggy-1.6.0
rootdir: /home/cy/github/chuanyue98/CodeAgent
configfile: pyproject.toml
plugins: anyio-4.13.0, asyncio-1.3.0, cov-7.0.0
asyncio: mode=Mode.STRICT, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collecting ... collected 182 items                                                            

tests/test_analytics.py .....                                            [  2%]
tests/test_ca_launcher.py ...............                                [ 10%]
tests/test_chat_router.py ...........                                    [ 17%]
tests/test_chat_service.py ..........                                    [ 22%]
tests/test_config_service.py ....                                        [ 24%]
tests/test_engine_base.py .................                              [ 34%]
tests/test_history_router.py ..........                                  [ 39%]
tests/test_hook_injection.py ..                                          [ 40%]
tests/test_hook_scanner.py ...                                           [ 42%]
tests/test_hook_scanner_dynamic.py ..                                    [ 43%]
tests/test_mcp_router.py ......                                          [ 46%]
tests/test_mcp_service.py .....................                          [ 58%]
tests/test_plugin.py .......                                             [ 62%]
tests/test_prompt_kit.py ....                                            [ 64%]
tests/test_prompt_scanner.py ....                                        [ 66%]
tests/test_resource_services.py ..                                       [ 67%]
tests/test_runner_service.py .....                                       [ 70%]
tests/test_schedule_service.py ..........                                [ 75%]
tests/test_scheduler_loop.py .....                                       [ 78%]
tests/test_schedules_router.py ........                                  [ 82%]
tests/test_session_history.py ................                           [ 91%]
tests/test_skill_scanner.py ...                                          [ 93%]
tests/test_web_api.py ............                                       [100%]

============================= 182 passed in 1.22s ==============================
```

## Commit
- **Commit Hash**: `3fbfb0093e70a843a965d20167b0eacd1083137a`
- **Commit Message**: `feat(backend): reap orphaned processes on shutdown`

## Concerns
- None.

## Fix Review and Issues Resolved

### Issues Addressed:
1. **Runner Service (`kill_all`) KeyError and zombie reaping**:
   - Fixed potential `KeyError` by checking `if task_id in self.active_runs` before modifying status.
   - Added `process.wait()` after calling `process.kill()` to reap zombie processes properly.
   - Added test `test_task_runner_kill_all_missing_from_active_runs` to verify that `kill_all` executes cleanly without `KeyError` and terminates the process when a task is in `_processes` but not in `active_runs`.
2. **FastAPI Lifespan Cleanup Try/Except Isolation**:
   - Wrapped `chat_runner.kill_all()` and `tasks_runner.kill_all()` in independent `try...except Exception: pass` blocks in `core/web/server.py` lifespan manager.
   - Added test `test_server_lifespan_cleanup_exceptions` in `tests/test_web_api.py` to verify that an exception raised by one runner's `kill_all()` does not prevent execution of the other's cleanup.

### Verification Runs:
**Command**:
```bash
.venv/bin/pytest tests/test_runner_service.py -k test_task_runner_kill_all_missing_from_active_runs
```
**Output**:
```
============================= test session starts ==============================
platform linux -- Python 3.14.5, pytest-9.0.2, pluggy-1.6.0
rootdir: /home/cy/github/chuanyue98/CodeAgent
configfile: pyproject.toml
plugins: anyio-4.13.0, asyncio-1.3.0, cov-7.0.0
asyncio: mode=Mode.STRICT, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collecting ... collected 6 items / 5 deselected / 1 selected

tests/test_runner_service.py .                                           [100%]

======================= 1 passed, 5 deselected in 0.12s ========================
```

**Command**:
```bash
.venv/bin/pytest tests/test_web_api.py -k test_server_lifespan_cleanup_exceptions
```
**Output**:
```
============================= test session starts ==============================
platform linux -- Python 3.14.5, pytest-9.0.2, pluggy-1.6.0
rootdir: /home/cy/github/chuanyue98/CodeAgent
configfile: pyproject.toml
plugins: anyio-4.13.0, asyncio-1.3.0, cov-7.0.0
asyncio: mode=Mode.STRICT, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collecting ... collected 13 items / 12 deselected / 1 selected

tests/test_web_api.py .                                                  [100%]

======================= 1 passed, 12 deselected in 0.19s =======================
```

**Full test suite verification command**:
```bash
.venv/bin/pytest
```
**Output**:
```
============================= test session starts ==============================
platform linux -- Python 3.14.5, pytest-9.0.2, pluggy-1.6.0
rootdir: /home/cy/github/chuanyue98/CodeAgent
configfile: pyproject.toml
plugins: anyio-4.13.0, asyncio-1.3.0, cov-7.0.0
asyncio: mode=Mode.STRICT, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collecting ... collected 184 items

tests/test_analytics.py .....                                            [  2%]
tests/test_ca_launcher.py ...............                                [ 10%]
tests/test_chat_router.py ...........                                    [ 16%]
tests/test_chat_service.py ..........                                    [ 22%]
tests/test_config_service.py ....                                        [ 24%]
tests/test_engine_base.py .................                              [ 33%]
tests/test_history_router.py ..........                                  [ 39%]
tests/test_hook_injection.py ..                                          [ 40%]
tests/test_hook_scanner.py ...                                           [ 41%]
tests/test_hook_scanner_dynamic.py ..                                    [ 42%]
tests/test_mcp_router.py ......                                          [ 46%]
tests/test_mcp_service.py .....................                          [ 57%]
tests/test_plugin.py .......                                             [ 61%]
tests/test_prompt_kit.py ....                                            [ 63%]
tests/test_prompt_scanner.py ....                                        [ 65%]
tests/test_resource_services.py ..                                       [ 66%]
tests/test_runner_service.py ......                                      [ 70%]
tests/test_schedule_service.py ..........                                [ 75%]
tests/test_scheduler_loop.py .....                                       [ 78%]
tests/test_schedules_router.py ........                                  [ 82%]
tests/test_session_history.py ................                           [ 91%]
tests/test_skill_scanner.py ...                                          [ 92%]
tests/test_web_api.py .............                                      [100%]

============================= 184 passed in 1.34s ==============================
```

### Git Commit for Fixes:
- **Commit Hash**: `c413d97a3355b978497043b82dca4c63512baf80`
- **Commit Message**: `fix: resolve KeyError in runner_service.py kill_all and isolate lifespan runner exceptions`

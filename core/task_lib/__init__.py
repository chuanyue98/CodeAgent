"""Common utility functions for tasks and prompts.

Split into focused submodules (paths, files, expressions, interactive,
selection) — this file just re-exports the combined public surface so
every existing `from core.task_lib import ...` / `core.task_lib.X` call
site keeps working unchanged.
"""

from __future__ import annotations

from core.task_lib.expressions import (
    parse_combination_expression,
    parse_range_expression,
    resolve_task_range,
)
from core.task_lib.files import (
    get_task_file_path,
    list_tasks,
    read_task_prompt,
    show_tasks,
    validate_task_file,
)
from core.task_lib.interactive import (
    _prompt_for_task_choice as _prompt_for_task_choice,
)
from core.task_lib.interactive import (
    select_task_interactively,
)
from core.task_lib.paths import (
    TASK_FILE_SUFFIX,
    TASKS_DIR,
    get_tasks_dir,
)
from core.task_lib.selection import handle_task_mode, load_multiple_tasks

__all__ = [
    "TASKS_DIR",
    "TASK_FILE_SUFFIX",
    "get_tasks_dir",
    "list_tasks",
    "parse_range_expression",
    "parse_combination_expression",
    "resolve_task_range",
    "show_tasks",
    "get_task_file_path",
    "validate_task_file",
    "read_task_prompt",
    "select_task_interactively",
    "handle_task_mode",
    "load_multiple_tasks",
]

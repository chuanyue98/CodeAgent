"""Common utility functions for tasks and prompts.

Split into focused submodules (paths, files, expressions, interactive,
selection) — this file just re-exports the combined public surface so
every existing `from core.task_lib import ...` / `core.task_lib.X` call
site keeps working unchanged.
"""

from __future__ import annotations

from core.console import configure_console_encoding

configure_console_encoding()

from core.task_lib.expressions import (  # noqa: E402
    parse_combination_expression,
    parse_range_expression,
    resolve_task_range,
)
from core.task_lib.files import (  # noqa: E402
    create_task_template,
    get_task_file_path,
    list_tasks,
    read_task_prompt,
    show_tasks,
    validate_task_file,
)
from core.task_lib.interactive import (  # noqa: E402
    _prompt_for_task_choice as _prompt_for_task_choice,
    select_task_interactively,
)
from core.task_lib.paths import (  # noqa: E402
    _ADDITIONAL_TEMPLATE_SEARCH_PATHS as _ADDITIONAL_TEMPLATE_SEARCH_PATHS,
    GENERAL_PROMPT_RELATIVE_PATH,
    TASK_FILE_SUFFIX,
    TASKS_DIR,
    get_general_prompt_path,
    get_tasks_dir,
    set_additional_template_search_paths,
)
from core.task_lib.selection import handle_task_mode, load_multiple_tasks  # noqa: E402

__all__ = [
    "TASKS_DIR",
    "TASK_FILE_SUFFIX",
    "GENERAL_PROMPT_RELATIVE_PATH",
    "get_general_prompt_path",
    "get_tasks_dir",
    "set_additional_template_search_paths",
    "list_tasks",
    "parse_range_expression",
    "parse_combination_expression",
    "resolve_task_range",
    "show_tasks",
    "get_task_file_path",
    "validate_task_file",
    "read_task_prompt",
    "create_task_template",
    "select_task_interactively",
    "handle_task_mode",
    "load_multiple_tasks",
]

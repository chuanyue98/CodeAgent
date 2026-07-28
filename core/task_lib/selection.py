"""Top-level task selection entrypoints used by the engine launchers."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

from core.task_lib.expressions import (
    parse_combination_expression,
    parse_range_expression,
    resolve_task_range,
)
from core.task_lib.files import list_tasks, read_task_prompt, validate_task_file
from core.task_lib.interactive import select_task_interactively
from core.task_lib.paths import TASK_FILE_SUFFIX, TASKS_DIR


def handle_task_mode(
    task_arg: Optional[str],
    directory: str = TASKS_DIR,
    label: str = "Task",
    file_suffix: str = TASK_FILE_SUFFIX,
    history: Optional[Dict[str, str]] = None,
    with_path: bool = False,
    allow_range: bool = False,
) -> Optional[Union[str, Tuple[str, Path], Tuple[List[str], List[Path]]]]:
    """Handles task selection and returns the corresponding prompt content.

    Args:
        task_arg: Task name, index, range, or empty string for interactive mode.
        directory: The tasks directory.
        label: Label for display purposes.
        file_suffix: The task file suffix.
        history: Task run history.
        with_path: If True, returns Path object(s) along with content.
        allow_range: Whether to allow range selection.

    Returns:
        The task prompt content (string), or a tuple containing content and Path.
    """
    if task_arg is None:
        return None

    selection: Union[str, List[str]]

    if task_arg == "":
        task_name = select_task_interactively(
            directory,
            file_suffix=file_suffix,
            history=history,
            allow_range=allow_range,
        )
        selection = task_name
    else:
        # A task literally named e.g. "deploy+rollback" or "3-5" must win
        # over the combination/range syntax below -- otherwise it can never
        # be selected by name, since "+"/range parsing runs unconditionally
        # on anything containing those characters.
        available_tasks = list_tasks(directory, file_suffix=file_suffix)
        is_literal_task_name = task_arg in available_tasks

        combination_selection: Optional[List[str]] = None
        if "+" in task_arg and not is_literal_task_name:
            if not available_tasks:
                print(
                    "❌ Error: No tasks available in current directory", file=sys.stderr
                )
                sys.exit(1)
            try:
                combination_selection = parse_combination_expression(
                    task_arg,
                    available_tasks,
                )
            except ValueError as exc:
                print(f"❌ Error: {exc}", file=sys.stderr)
                sys.exit(1)

        range_tuple = (
            parse_range_expression(task_arg)
            if (allow_range and not is_literal_task_name)
            else None
        )
        if combination_selection is not None:
            selection = combination_selection
        elif range_tuple is not None:
            selection = resolve_task_range(
                task_arg,
                directory,
                file_suffix,
            )
        else:
            selection = task_arg

    if allow_range and isinstance(selection, list):
        print(f"🔢 Selected {label} range: {', '.join(selection)}")
        prompts, files = load_multiple_tasks(
            selection,
            directory=directory,
            label=label,
            file_suffix=file_suffix,
        )
        if with_path:
            return prompts, files
        return "\n\n".join(prompts)

    if isinstance(selection, list):
        prompts, _ = load_multiple_tasks(
            selection,
            directory=directory,
            label=label,
            file_suffix=file_suffix,
        )
        merged_prompt = "\n\n".join(prompts)
        print(f"🧩 Merged {label}: {', '.join(selection)}")
        return merged_prompt

    task_file = validate_task_file(selection, directory, file_suffix)
    task_prompt = read_task_prompt(task_file)

    print(f"📝 Loaded {label}: {task_file.stem}")
    if with_path:
        return task_prompt, task_file
    return task_prompt


def load_multiple_tasks(
    task_names: List[str],
    directory: str,
    label: str,
    file_suffix: str,
) -> Tuple[List[str], List[Path]]:
    """Batch loads task prompts from multiple task names.

    Args:
        task_names: List of task names to load.
        directory: The tasks directory.
        label: Label for display purposes.
        file_suffix: The task file suffix.

    Returns:
        A tuple containing a list of prompts and a list of Path objects.
    """
    prompts: List[str] = []
    files: List[Path] = []

    for name in task_names:
        result = handle_task_mode(
            name,
            directory=directory,
            label=label,
            file_suffix=file_suffix,
            with_path=True,
        )

        if isinstance(result, tuple):
            prompt, path = result
            if isinstance(prompt, str) and isinstance(path, Path):
                prompts.append(prompt)
                files.append(path)
            else:
                raise TypeError("Expected a single task prompt and path")
        else:
            prompts.append(str(result))

    return prompts, files

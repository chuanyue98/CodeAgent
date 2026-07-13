"""Common utility functions for tasks and prompts."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple, Union

from core.console import configure_console_encoding
from core.resource_locator import get_bundled_resource_root, get_default_config_path

configure_console_encoding()

TASKS_DIR = "tasks"
TASK_FILE_SUFFIX = ".md"
GENERAL_PROMPT_RELATIVE_PATH = "prompt/general.basic.md"

_ADDITIONAL_TEMPLATE_SEARCH_PATHS: List[str] = []


def get_general_prompt_path() -> Path:
    """Returns the absolute path to the general.md prompt file.

    Returns:
        The Path object pointing to the general prompt file.
    """

    script_dir = Path(__file__).resolve().parent
    return script_dir / GENERAL_PROMPT_RELATIVE_PATH


def get_tasks_dir(directory: Union[str, Path] = TASKS_DIR) -> Path:
    """Returns the absolute path to the tasks directory.

    Args:
        directory: The relative or absolute path to the tasks directory. Defaults to TASKS_DIR.

    Returns:
        The absolute Path object for the tasks directory.
    """
    dir_path = Path(directory)

    if dir_path.is_absolute():
        return dir_path

    if str(directory) == TASKS_DIR:
        env_root = os.environ.get("CA_TASKS_ROOT")
        if env_root:
            return Path(env_root).expanduser().resolve()

        codeagent_root = Path(__file__).resolve().parent.parent
        config_path = get_default_config_path(codeagent_root)
        try:
            config = json.loads(config_path.read_text(encoding="utf-8-sig"))
            resource_root = config.get("paths", {}).get("resource_root")
            if resource_root:
                expanded = str(resource_root).replace(
                    "$CODEAGENT", codeagent_root.as_posix()
                )
                resolved_root = Path(expanded).expanduser()
                if not resolved_root.is_absolute():
                    resolved_root = codeagent_root / resolved_root
                return (resolved_root / TASKS_DIR).resolve()
        except (OSError, json.JSONDecodeError, TypeError):
            pass

        return get_bundled_resource_root(codeagent_root) / TASKS_DIR

    return (Path.cwd() / dir_path).resolve()


def set_additional_template_search_paths(paths: Iterable[Union[str, Path]]) -> None:
    """Configures additional search paths for task template rendering.

    Args:
        paths: An iterable of paths to add to the template search list.
    """

    resolved_paths: List[str] = []

    for raw_path in paths:
        path_obj = Path(raw_path).expanduser()
        if not path_obj.is_absolute():
            path_obj = Path(__file__).resolve().parent / path_obj
        resolved_paths.append(str(path_obj))

    # Use dict.fromkeys to maintain original order and remove duplicates
    unique_paths = list(dict.fromkeys(resolved_paths))
    _ADDITIONAL_TEMPLATE_SEARCH_PATHS[:] = unique_paths


def list_tasks(
    directory: str = TASKS_DIR, file_suffix: str = TASK_FILE_SUFFIX
) -> List[str]:
    """Lists the names of tasks in the specified directory.

    Args:
        directory: The tasks directory to scan.
        file_suffix: The file extension suffix for task files.

    Returns:
        A sorted list of task names (file stems).
    """
    tasks_dir = get_tasks_dir(directory)
    if not tasks_dir.exists():
        return []

    tasks = [file.stem for file in tasks_dir.glob(f"*{file_suffix}")]
    return sorted(tasks)


def parse_range_expression(expression: str) -> Optional[Tuple[int, int]]:
    """Parses a range expression like '3-5'.

    Args:
        expression: The range expression string.

    Returns:
        A tuple (start, end) if successfully parsed, otherwise None.
    """
    parts = expression.split("-", maxsplit=1)
    if len(parts) != 2:
        return None

    start_str, end_str = parts
    if not (start_str.isdigit() and end_str.isdigit()):
        return None

    start = int(start_str)
    end = int(end_str)

    if start <= 0 or end <= 0 or start > end:
        return None

    return start, end


def parse_combination_expression(
    expression: str,
    available_tasks: List[str],
) -> Optional[List[str]]:
    """Parses a combination expression like '1+2', supporting indices or task names.

    Args:
        expression: The combination expression string.
        available_tasks: List of available task names for reference.

    Returns:
        A list of selected task names if successful.

    Raises:
        ValueError: If the expression is invalid or task is not found.
    """
    if "+" not in expression:
        return None

    parts = [part.strip() for part in expression.split("+")]
    if any(not part for part in parts):
        raise ValueError("Combination expression contains empty items")

    combined: List[str] = []
    task_total = len(available_tasks)

    for part in parts:
        if part.isdigit():
            index = int(part) - 1
            if index < 0 or index >= task_total:
                raise ValueError(f"Index {part} out of range (1-{task_total})")
            combined.append(available_tasks[index])
            continue

        if part in available_tasks:
            combined.append(part)
            continue

        raise ValueError(f"Task not found: {part}")

    if len(combined) < 2:
        raise ValueError("Combination expression requires at least two tasks")

    return combined


def resolve_task_range(
    expression: str,
    directory: str,
    file_suffix: str,
) -> List[str]:
    """Resolves a task range expression into a list of task names.

    Args:
        expression: The range expression string.
        directory: The tasks directory.
        file_suffix: The task file suffix.

    Returns:
        A list of task names matching the range.
    """
    parsed = parse_range_expression(expression)
    if parsed is None:
        print(f"❌ Error: Invalid range expression '{expression}'", file=sys.stderr)
        sys.exit(1)

    start_index, end_index = parsed
    tasks = list_tasks(directory, file_suffix=file_suffix)

    if not tasks:
        print("❌ Error: No tasks available in current directory", file=sys.stderr)
        sys.exit(1)

    if end_index > len(tasks):
        print(
            f"❌ Error: Range {start_index}-{end_index} exceeds task count (total {len(tasks)})",
            file=sys.stderr,
        )
        sys.exit(1)

    selected = tasks[start_index - 1 : end_index]
    if not selected:
        print(f"❌ Error: Range {expression} matched no tasks", file=sys.stderr)
        sys.exit(1)

    return selected


def show_tasks(
    directory: str = TASKS_DIR,
    label: Optional[str] = None,
    file_suffix: str = TASK_FILE_SUFFIX,
    history: Optional[Dict[str, str]] = None,
    range_selection_hint: bool = False,
) -> None:
    """Displays the available tasks in the specified directory.

    Args:
        directory: The tasks directory to display.
        label: A label for the task list. Defaults to "Available Tasks".
        file_suffix: The task file suffix.
        history: A dictionary mapping task names to their last run timestamp.
        range_selection_hint: Whether to show a hint for range selection.
    """
    tasks = list_tasks(directory, file_suffix=file_suffix)

    if not tasks:
        prefix = f"📋 {label} No tasks available" if label else "📋 No tasks available"
        print(prefix)
        print(
            f"Please create task files in {directory}/ (e.g., {directory}/refactor{file_suffix})"
        )
        return

    header = label if label else "Available Tasks"
    print(f"📋 {header}:")
    for i, task in enumerate(tasks, 1):
        if history is not None:
            last_run = history.get(task)
            if last_run:
                print(f"  {i}. {task} (Last run: {last_run})")
            else:
                print(f"  {i}. {task} (Last run: Never)")
        else:
            print(f"  {i}. {task}")

    if range_selection_hint:
        print(
            "\n💡 Hint: Use '-cp 3-5' to select a range of tasks and run in non-interactive mode automatically."
        )


def get_task_file_path(
    task_name: str,
    directory: str = TASKS_DIR,
    file_suffix: str = TASK_FILE_SUFFIX,
) -> Path:
    """Returns the absolute path to a specific task file.

    Args:
        task_name: The name of the task.
        directory: The tasks directory.
        file_suffix: The task file suffix.

    Returns:
        The Path object for the task file.
    """
    tasks_dir = get_tasks_dir(directory)

    if task_name.endswith(file_suffix):
        filename = task_name
    else:
        filename = f"{task_name}{file_suffix}"

    return tasks_dir / filename


def validate_task_file(
    task_name: str,
    directory: str = TASKS_DIR,
    file_suffix: str = TASK_FILE_SUFFIX,
) -> Path:
    """Validates if a task file exists and returns its path.

    Args:
        task_name: The name of the task.
        directory: The tasks directory.
        file_suffix: The task file suffix.

    Returns:
        The Path object for the task file.
    """
    task_file = get_task_file_path(task_name, directory, file_suffix)

    if not task_file.exists():
        print(f"❌ Error: Task does not exist - {task_name}", file=sys.stderr)
        print(
            f"Hint: Please create {task_name}{file_suffix} in {directory}/",
            file=sys.stderr,
        )
        sys.exit(1)

    return task_file


def read_task_prompt(task_file: Path) -> str:
    """Reads the content of a task file.

    Args:
        task_file: The path to the task file.

    Returns:
        The content of the task file as a string.
    """

    try:
        return task_file.read_text(encoding="utf-8").strip()
    except OSError as exc:
        print(f"❌ Failed to read task file: {exc}", file=sys.stderr)
        sys.exit(1)


def create_task_template(task_name: str, directory: str = TASKS_DIR) -> Path:
    """Creates a new task template file in the specified directory.

    Args:
        task_name: The name of the new task.
        directory: The tasks directory.

    Returns:
        The Path object for the newly created task file.
    """
    tasks_dir = get_tasks_dir(directory)
    tasks_dir.mkdir(parents=True, exist_ok=True)

    file_path = tasks_dir / f"{task_name}{TASK_FILE_SUFFIX}"
    if file_path.exists():
        print(
            f"❌ Error: Task '{task_name}' already exists at {file_path}",
            file=sys.stderr,
        )
        sys.exit(1)

    template_content = f"""# Task: {task_name}

## Objective
Describe the goal of the task here.

## Context
List background information the AI needs to be aware of.

## Instructions
1. First step
2. Second step

## Verification
How to verify the task has been successfully completed.
"""
    try:
        file_path.write_text(template_content, encoding="utf-8")
        return file_path
    except OSError as exc:
        print(f"❌ Failed to create task template: {exc}", file=sys.stderr)
        sys.exit(1)


def select_task_interactively(
    directory: str = TASKS_DIR,
    file_suffix: str = TASK_FILE_SUFFIX,
    history: Optional[Dict[str, str]] = None,
    allow_range: bool = False,
) -> Union[str, List[str]]:
    """Interactively prompts the user to select one or more tasks.

    Args:
        directory: The tasks directory.
        file_suffix: The task file suffix.
        history: Task run history.
        allow_range: Whether to allow range selection (e.g., '1-3').

    Returns:
        A single task name or a list of task names if multiple are selected.
    """
    tasks = list_tasks(directory, file_suffix=file_suffix)

    if not tasks:
        print("❌ No tasks available", file=sys.stderr)
        print(
            f"Please create task files in {directory}/ (e.g., {directory}/refactor{file_suffix})",
            file=sys.stderr,
        )
        sys.exit(1)

    show_tasks(
        directory,
        file_suffix=file_suffix,
        history=history,
        range_selection_hint=allow_range,
    )

    if allow_range:
        print(
            "👉 Enter index, task name, range (e.g., 1-3), or combination (e.g., 1+2)"
        )
    else:
        print("👉 Enter index, task name, or combination (e.g., 1+2)")
    print()

    while True:
        try:
            choice = input("Select task (index or name): ").strip()

            if not choice:
                print("❌ Input cannot be empty")
                continue

            try:
                combination = parse_combination_expression(choice, tasks)
            except ValueError as exc:
                print(f"❌ {exc}")
                continue

            if combination is not None:
                return combination

            if choice.isdigit():
                index = int(choice) - 1
                if 0 <= index < len(tasks):
                    return tasks[index]
                print(f"❌ Index out of range (1-{len(tasks)})")
                continue

            if allow_range:
                range_tuple = parse_range_expression(choice)
                if range_tuple is not None:
                    return resolve_task_range(
                        choice,
                        directory,
                        file_suffix,
                    )

            if choice in tasks:
                return choice
            print(f"❌ Task does not exist: {choice}")
        except KeyboardInterrupt:
            print("\n\n👋 Cancelled")
            sys.exit(0)
        except EOFError:
            print("\n\n❌ Input ended")
            sys.exit(1)


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
        combination_selection: Optional[List[str]] = None
        if "+" in task_arg:
            available_tasks = list_tasks(directory, file_suffix=file_suffix)
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

        range_tuple = parse_range_expression(task_arg) if allow_range else None
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

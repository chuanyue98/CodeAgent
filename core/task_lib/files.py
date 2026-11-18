"""Listing, reading, and creating task files on disk."""

from __future__ import annotations

import sys
from pathlib import Path

from core.task_lib.paths import TASK_FILE_SUFFIX, TASKS_DIR, get_tasks_dir


def list_tasks(
    directory: str = TASKS_DIR, file_suffix: str = TASK_FILE_SUFFIX
) -> list[str]:
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


def show_tasks(
    directory: str = TASKS_DIR,
    label: str | None = None,
    file_suffix: str = TASK_FILE_SUFFIX,
    history: dict[str, str] | None = None,
    range_selection_hint: bool = False,
    tasks: list[str] | None = None,
) -> None:
    """Displays the available tasks in the specified directory.

    Args:
        directory: The tasks directory to display.
        label: A label for the task list. Defaults to "Available Tasks".
        file_suffix: The task file suffix.
        history: A dictionary mapping task names to their last run timestamp.
        range_selection_hint: Whether to show a hint for range selection.
        tasks: 可选的预扫描任务名列表，避免重复扫描目录。
    """
    if tasks is None:
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
        return task_file.read_text(encoding="utf-8", errors="replace").strip()
    except OSError as exc:
        raise FileNotFoundError(f"Failed to read task file: {exc}") from exc

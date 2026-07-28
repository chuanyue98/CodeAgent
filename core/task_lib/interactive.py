"""Interactive terminal prompting for task selection."""

from __future__ import annotations

import sys
from typing import Dict, List, Optional, Union

from core.task_lib.expressions import (
    parse_combination_expression,
    parse_range_expression,
    resolve_task_range,
)
from core.task_lib.files import list_tasks, show_tasks
from core.task_lib.paths import TASK_FILE_SUFFIX, TASKS_DIR


def _prompt_for_task_choice(tasks: List[str]) -> str:
    """Reads the user's raw task selection.

    In a real terminal this offers arrow-key browsing and incremental
    substring filtering over task names via questionary, while still
    accepting any free-form text (index, exact name, range, combination)
    the caller's parsing logic expects -- questionary's autocomplete only
    *suggests* matches, it never restricts what gets submitted. Falls back
    to a plain input() when stdin/stdout aren't TTYs (scripts, piped input,
    tests) or questionary isn't importable.
    """
    if sys.stdin.isatty() and sys.stdout.isatty():
        try:
            import questionary

            answer = questionary.autocomplete(
                "Select task (index or name, type to filter):",
                choices=tasks,
                match_middle=True,
            ).ask()
            if answer is None:
                print("\n\n👋 Cancelled")
                sys.exit(0)
            return answer.strip()
        except ImportError:
            pass
    return input("Select task (index or name): ").strip()


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
            choice = _prompt_for_task_choice(tasks)

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

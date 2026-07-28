"""Parsing and resolving task range/combination selection expressions."""

from __future__ import annotations

import sys
from typing import List, Optional, Tuple

from core.task_lib.files import list_tasks


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

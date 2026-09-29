"""Code plan management and directory selection for Codex engine."""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

from core.task_lib import (
    get_tasks_dir,
    list_tasks,
    parse_range_expression,
)

CODE_PLAN_DIR_PATTERN = "code_plan*"
CODE_PLAN_FILE_SUFFIX = ".md"
CODE_PLAN_HISTORY_FILENAME = "history.json"


def get_code_plan_history_path(directory: str | Path) -> Path:
    return get_tasks_dir(directory) / CODE_PLAN_HISTORY_FILENAME


def load_code_plan_history(directory: str | Path) -> dict[str, str]:
    history_path = get_code_plan_history_path(directory)

    if not history_path.exists():
        return {}

    try:
        with open(history_path, encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return {str(key): str(value) for key, value in data.items()}
    except json.JSONDecodeError as exc:
        print(f"Failed to parse code plan history: {exc}", file=sys.stderr)

    return {}


def save_code_plan_history(directory: str | Path, history: dict[str, str]) -> None:
    history_path = get_code_plan_history_path(directory)
    history_path.parent.mkdir(parents=True, exist_ok=True)

    with open(history_path, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2)


def update_code_plan_history(
    plan_file: Path,
    history: dict[str, str] | None = None,
) -> dict[str, str]:
    directory = plan_file.parent

    if history is None:
        history = load_code_plan_history(directory)

    history[plan_file.stem] = datetime.now().isoformat(timespec="seconds")
    save_code_plan_history(directory, history)
    return history


def list_code_plan_directories(pattern: str = CODE_PLAN_DIR_PATTERN) -> list[str]:
    script_dir = Path(__file__).resolve().parent
    directories = [path.name for path in script_dir.glob(pattern) if path.is_dir()]
    return sorted(directories)


def split_code_plan_argument(
    argument: str,
    directories: list[str],
) -> tuple[str | None, str]:
    trimmed = argument.strip()

    if not trimmed:
        return None, ""

    if trimmed in directories:
        return trimmed, ""

    for separator in (":", "/"):
        if separator in trimmed:
            dir_candidate, plan_part = trimmed.split(separator, 1)
            dir_candidate = dir_candidate.strip()
            plan_part = plan_part.strip()
            if dir_candidate in directories:
                return dir_candidate, plan_part

    return None, trimmed


def find_directories_for_plan(plan_name: str, directories: list[str]) -> list[str]:
    normalized = plan_name.strip()
    if not normalized:
        return []

    if parse_range_expression(normalized) is not None:
        return directories.copy()

    if normalized.endswith(CODE_PLAN_FILE_SUFFIX):
        normalized = normalized[: -len(CODE_PLAN_FILE_SUFFIX)]

    matches: list[str] = []

    for directory in directories:
        plans = list_tasks(directory, file_suffix=CODE_PLAN_FILE_SUFFIX)
        if normalized in plans:
            matches.append(directory)

    return matches


def select_code_plan_directory_interactively(directories: list[str]) -> str:
    print("Available code plan directories:")
    for i, directory in enumerate(directories, 1):
        print(f"  {i}. {directory}")

    while True:
        choice = input("Choose directory by index or name: ").strip()
        if not choice:
            print("Input cannot be empty")
            continue

        if choice.isdigit():
            index = int(choice) - 1
            if 0 <= index < len(directories):
                return directories[index]
            print(f"Index out of range (1-{len(directories)})")
            continue

        if choice in directories:
            return choice

        print(f"Directory not found: {choice}")

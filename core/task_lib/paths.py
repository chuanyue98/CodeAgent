"""Path resolution for the tasks directory and prompt templates."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Iterable, List, Union

from core.resource_locator import get_bundled_resource_root, get_default_config_path

TASKS_DIR = "tasks"
TASK_FILE_SUFFIX = ".md"
GENERAL_PROMPT_RELATIVE_PATH = "prompt/general.basic.md"

_ADDITIONAL_TEMPLATE_SEARCH_PATHS: List[str] = []


def get_general_prompt_path() -> Path:
    """Returns the absolute path to the general.md prompt file.

    Returns:
        The Path object pointing to the general prompt file.
    """

    script_dir = Path(__file__).resolve().parent.parent
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

        codeagent_root = Path(__file__).resolve().parent.parent.parent
        config_path = get_default_config_path(codeagent_root)
        try:
            config = json.loads(config_path.read_text(encoding="utf-8-sig"))
            if not isinstance(config, dict):
                raise TypeError("config.json must contain a JSON object")
            resource_root = config.get("paths", {}).get("resource_root")
            if resource_root:
                expanded = str(resource_root).replace(
                    "$CODEAGENT", codeagent_root.as_posix()
                )
                resolved_root = Path(expanded).expanduser()
                if not resolved_root.is_absolute():
                    resolved_root = codeagent_root / resolved_root
                return (resolved_root / TASKS_DIR).resolve()
        except (OSError, json.JSONDecodeError, TypeError, AttributeError):
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
            path_obj = Path(__file__).resolve().parent.parent / path_obj
        resolved_paths.append(str(path_obj))

    # Use dict.fromkeys to maintain original order and remove duplicates
    unique_paths = list(dict.fromkeys(resolved_paths))
    _ADDITIONAL_TEMPLATE_SEARCH_PATHS[:] = unique_paths

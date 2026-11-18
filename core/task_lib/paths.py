"""Path resolution for the tasks directory and prompt templates."""

from __future__ import annotations

import os
from pathlib import Path

from core.resource_locator import (
    CODE_ROOT,
    get_bundled_resource_root,
    get_default_config_path,
    resolve_resource_root_from_config,
)
from core.services.config_service import ConfigService

TASKS_DIR = "tasks"
TASK_FILE_SUFFIX = ".md"


def get_tasks_dir(directory: str | Path = TASKS_DIR) -> Path:
    """返回任务目录的绝对路径。

    Args:
        directory: 任务目录的相对或绝对路径，默认为 TASKS_DIR。

    Returns:
        任务目录对应的绝对 Path 对象。
    """
    dir_path = Path(directory).expanduser()

    if dir_path.is_absolute():
        return dir_path

    if str(directory) == TASKS_DIR:
        env_root = os.environ.get("CA_TASKS_ROOT")
        if env_root:
            return Path(env_root).expanduser().resolve()

        config_path = get_default_config_path(CODE_ROOT)
        config, _ = ConfigService(config_path).get_config()
        if isinstance(config, dict) and isinstance(config.get("paths"), dict):
            resolved_root = resolve_resource_root_from_config(config, CODE_ROOT)
            if resolved_root is not None:
                return (resolved_root / TASKS_DIR).resolve()

        return get_bundled_resource_root(CODE_ROOT) / TASKS_DIR

    return (Path.cwd() / dir_path).resolve()

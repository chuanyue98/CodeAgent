import json
import os
from pathlib import Path

from core.resource_locator import (
    CODE_ROOT,
    get_bundled_resource_root,
    get_default_config_path,
)

ROOT_DIR = CODE_ROOT


def _config_resource_root() -> Path:
    from core.resource_locator import resolve_resource_root_from_config

    config_path = get_default_config_path(ROOT_DIR)
    try:
        with open(config_path, encoding="utf-8-sig") as f:
            config = json.load(f)
        resolved = resolve_resource_root_from_config(config, ROOT_DIR)
        if resolved is not None:
            return resolved
    except Exception:
        pass
    return get_bundled_resource_root(ROOT_DIR)


def resolve_resource_path(subdir: str, env_var: str) -> Path:
    env_path = os.environ.get(env_var)
    if env_path:
        return Path(env_path)
    return _config_resource_root() / subdir

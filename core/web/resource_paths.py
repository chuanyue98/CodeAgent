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
    config_path = get_default_config_path(ROOT_DIR)
    try:
        with open(config_path, encoding="utf-8-sig") as f:
            resource_root = json.load(f).get("paths", {}).get("resource_root")
        if resource_root:
            expanded = str(resource_root).replace("$CODEAGENT", ROOT_DIR.as_posix())
            resource_path = Path(expanded).expanduser()
            resolved = (
                resource_path
                if resource_path.is_absolute()
                else ROOT_DIR / resource_path
            ).resolve()
            if resolved.is_dir():
                return resolved
    except Exception:
        pass
    return get_bundled_resource_root(ROOT_DIR)


def resolve_resource_path(subdir: str, env_var: str) -> Path:
    env_path = os.environ.get(env_var)
    if env_path:
        return Path(env_path)
    return _config_resource_root() / subdir

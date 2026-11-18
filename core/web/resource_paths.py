import json
import os
import threading
from pathlib import Path

from core.resource_locator import (
    CODE_ROOT,
    get_bundled_resource_root,
    get_default_config_path,
)

ROOT_DIR = CODE_ROOT

_CACHE_LOCK = threading.Lock()
_CACHE: tuple[tuple[Path, Path, int, int], Path] | None = None


def _config_resource_root() -> Path:
    global _CACHE
    from core.resource_locator import resolve_resource_root_from_config

    config_path = get_default_config_path(ROOT_DIR)
    try:
        resolved_config = config_path.resolve()
        resolved_root = ROOT_DIR.resolve()
        stat = resolved_config.stat()
        cache_key = (resolved_config, resolved_root, stat.st_mtime_ns, stat.st_size)
        with _CACHE_LOCK:
            if _CACHE is not None and _CACHE[0] == cache_key:
                return _CACHE[1]
        with open(resolved_config, encoding="utf-8-sig") as f:
            config = json.load(f)
        resolved = resolve_resource_root_from_config(config, ROOT_DIR)
        result = (
            resolved if resolved is not None else get_bundled_resource_root(ROOT_DIR)
        )
        with _CACHE_LOCK:
            _CACHE = (cache_key, result)
        return result
    except Exception:
        with _CACHE_LOCK:
            _CACHE = None
    return get_bundled_resource_root(ROOT_DIR)


def resolve_resource_path(subdir: str, env_var: str) -> Path:
    env_path = os.environ.get(env_var)
    if env_path:
        return Path(env_path)
    return _config_resource_root() / subdir

import json
import os
import threading
import traceback
from pathlib import Path

from core.utils.atomic_write import atomic_write
from core.utils.last_good import keep_last_good, looks_crash_damaged, read_with_fallback


def _parse_config(text: str) -> dict:
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("顶层不是 JSON 对象")
    return data


class ConfigService:
    """Service for managing configuration files and project registries."""

    _lock = threading.Lock()

    def __init__(self, config_path: Path):
        """Initializes the ConfigService with the given configuration path.

        Args:
            config_path: Path to the configuration file.
        """
        self.config_path = config_path
        self._cache: tuple[float, dict, list[str]] | None = None

    def _read(self) -> tuple[dict, list[str]]:
        """Read the config file from disk (caller must hold ``_lock`` if needed)."""
        """读不懂时改用上一份完好的副本（见 :mod:`core.utils.last_good`），
        并在 warnings 里说明，交给调用方提示用户。"""
        try:
            data, note, _intact = read_with_fallback(self.config_path, _parse_config)
        except Exception as e:
            if os.getenv("CA_DEBUG"):
                traceback.print_exc()
            return {}, [f"Failed to read config.json: {e}"]
        if note is None:
            return data or {}, []
        return data or {}, [f"Failed to parse config.json: {note}"]

    def _read_for_write(self) -> dict:
        """写之前读：文件读不懂就拒绝覆盖，除非它是断电留下的空文件/全 0 文件。

        手改出错的文件里有用户的改动，覆盖掉就丢了；断电损坏的文件里什么都
        没有，接着用上一份完好的副本写下去（损坏的文件会先另存一份）。
        """
        config, warnings = self._read()
        if warnings:
            try:
                damaged = looks_crash_damaged(self.config_path.read_bytes())
            except OSError:
                damaged = False
            if not damaged:
                raise ValueError(
                    f"Refusing to overwrite malformed configuration: {warnings[0]}"
                )
        return config

    def _atomic_write(self, config: dict) -> None:
        """Atomic write via temp+fsync+replace (caller must hold ``_lock``)."""
        keep_last_good(self.config_path, _parse_config)
        atomic_write(
            self.config_path,
            json.dumps(config, indent=2, ensure_ascii=False),
            fsync=True,
        )

    def _cached_read(self) -> tuple[dict, list[str]]:
        """Return cached config if the file mtime hasn't changed."""
        try:
            mtime = self.config_path.stat().st_mtime
        except OSError:
            self._cache = None
            return {}, []

        if self._cache and self._cache[0] == mtime:
            return self._cache[1], self._cache[2]

        result = self._read()
        self._cache = (mtime, result[0], result[1])
        return result

    def get_config(self) -> tuple[dict, list[str]]:
        """Retrieves the current configuration (no lock — read-only access)."""
        return self._cached_read()

    def update_config(self, config: dict):
        """Atomically replaces the entire config file.

        No read-modify-write — callers are responsible for supplying the
        complete new config.  Uses ``modify_config`` if a read-merge-write
        cycle is needed.
        """
        if not isinstance(config, dict):
            raise TypeError("Configuration must be a JSON object")
        with self._lock:
            self._read_for_write()
            self._atomic_write(config)
        self._cache = None

    def modify_config(self, modifier):
        """Atomically read, apply *modifier*, and write the config.

        The *modifier* callable receives the current ``dict`` and must
        return the (possibly mutated) ``dict`` to persist.

        Example::

            def add_skill(config):
                config.setdefault("skills", []).append("new-skill")
                return config

            config_service.modify_config(add_skill)
        """
        with self._lock:
            config = self._read_for_write()
            config = modifier(config)
            self._atomic_write(config)
        self._cache = None

    def add_project(self, path: str, group: str) -> list:
        """Adds or updates a project in the project registry (atomic RMW)."""

        def _modifier(config):
            registry = config.get("project_registry", [])
            updated = False
            for item in registry:
                # 注册表是用户可手改的文件：条目缺 path 或不是对象时跳过，
                # 而不是拿 KeyError 把 ca project 崩掉。
                if isinstance(item, dict) and item.get("path") == path:
                    item["group"] = group
                    updated = True
                    break
            if not updated:
                registry.append({"path": path, "group": group})
            config["project_registry"] = registry
            return config

        self.modify_config(_modifier)
        config, _ = self._read()
        return config.get("project_registry", [])

    def delete_project(self, path: str) -> list:
        """Deletes a project from the project registry (atomic RMW)."""

        def _modifier(config):
            registry = config.get("project_registry", [])
            # 只删除 path 匹配的条目；缺 path / 非对象（用户手改留下的脏数据）
            # 原样保留，避免 item["path"] 抛 KeyError。
            config["project_registry"] = [
                item
                for item in registry
                if not (isinstance(item, dict) and item.get("path") == path)
            ]
            return config

        self.modify_config(_modifier)
        config, _ = self._read()
        return config.get("project_registry", [])

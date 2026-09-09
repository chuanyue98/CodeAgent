import json
import os
import threading
import traceback
from pathlib import Path

from core.utils.atomic_write import atomic_write


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
        warnings = []
        if not self.config_path.exists():
            return {}, []
        try:
            with open(self.config_path, encoding="utf-8-sig") as f:
                return json.load(f), []
        except Exception as e:
            warnings.append(f"Failed to parse config.json: {e}")
            if os.getenv("CA_DEBUG"):
                traceback.print_exc()
            return {}, warnings

    def _atomic_write(self, config: dict) -> None:
        """Atomic write via temp+fsync+replace (caller must hold ``_lock``)."""
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
        existing, warnings = self._read()
        if warnings:
            raise ValueError(
                f"Refusing to overwrite malformed configuration: {warnings[0]}"
            )

        with self._lock:
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
            config, warnings = self._read()
            if warnings:
                raise ValueError(warnings[0])
            config = modifier(config)
            self._atomic_write(config)
        self._cache = None

    def add_project(self, path: str, group: str) -> list:
        """Adds or updates a project in the project registry (atomic RMW)."""

        def _modifier(config):
            registry = config.get("project_registry", [])
            updated = False
            for item in registry:
                if item["path"] == path:
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
            config["project_registry"] = [
                item for item in registry if item["path"] != path
            ]
            return config

        self.modify_config(_modifier)
        config, _ = self._read()
        return config.get("project_registry", [])

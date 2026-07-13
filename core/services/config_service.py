import json
import os
import tempfile
import threading
import traceback
from pathlib import Path


class ConfigService:
    """Service for managing configuration files and project registries."""

    _lock = threading.Lock()

    def __init__(self, config_path: Path):
        """Initializes the ConfigService with the given configuration path.

        Args:
            config_path: Path to the configuration file.
        """
        self.config_path = config_path

    def _read(self) -> tuple[dict, list[str]]:
        """Read the config file from disk (caller must hold ``_lock`` if needed)."""
        warnings = []
        if not self.config_path.exists():
            return {}, []
        try:
            with open(self.config_path, "r", encoding="utf-8-sig") as f:
                return json.load(f), []
        except Exception as e:
            warnings.append(f"Failed to parse config.json: {e}")
            if os.getenv("CA_DEBUG"):
                traceback.print_exc()
            return {}, warnings

    def _atomic_write(self, config: dict) -> None:
        """Atomic write via temp+fsync+replace (caller must hold ``_lock``)."""
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(
            dir=self.config_path.parent,
            prefix=f".{self.config_path.name}.",
            suffix=".tmp",
            text=True,
        )
        temp_path = Path(temp_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp_path, self.config_path)
        except Exception:
            temp_path.unlink(missing_ok=True)
            raise

    def get_config(self) -> tuple[dict, list[str]]:
        """Retrieves the current configuration (no lock — read-only access)."""
        return self._read()

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

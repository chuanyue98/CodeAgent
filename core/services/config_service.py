import json
import os
import tempfile
import threading
import traceback
from pathlib import Path


class ConfigService:
    """Service for managing configuration files and project registries."""

    _write_lock = threading.Lock()

    def __init__(self, config_path: Path):
        """Initializes the ConfigService with the given configuration path.

        Args:
            config_path: Path to the configuration file.
        """
        self.config_path = config_path

    def get_config(self) -> tuple[dict, list[str]]:
        """Retrieves the current configuration.

        Returns:
            A tuple of (configuration_dict, warnings_list).
        """
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

    def update_config(self, config: dict):
        """Updates the configuration file with the provided dictionary.

        Args:
            config: The configuration dictionary to save.
        """
        if not isinstance(config, dict):
            raise TypeError("Configuration must be a JSON object")
        if self.config_path.exists():
            _, warnings = self.get_config()
            if warnings:
                raise ValueError(
                    f"Refusing to overwrite malformed configuration: {warnings[0]}"
                )

        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        with self._write_lock:
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

    def add_project(self, path: str, group: str) -> list:
        """Adds or updates a project in the project registry.

        Args:
            path: Absolute path to the project directory.
            group: Group name for the project.

        Returns:
            The updated project registry list.
        """
        config, warnings = self.get_config()
        if warnings:
            raise ValueError(warnings[0])
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
        self.update_config(config)
        return registry

    def delete_project(self, path: str) -> list:
        """Deletes a project from the project registry.

        Args:
            path: Absolute path of the project to remove.

        Returns:
            The updated project registry list.
        """
        config, warnings = self.get_config()
        if warnings:
            raise ValueError(warnings[0])
        registry = config.get("project_registry", [])
        new_registry = [item for item in registry if item["path"] != path]
        config["project_registry"] = new_registry
        self.update_config(config)
        return new_registry

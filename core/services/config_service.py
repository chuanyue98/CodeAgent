import json
from pathlib import Path


class ConfigService:
    """Service for managing configuration files and project registries."""

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
            with open(self.config_path, "r", encoding="utf-8") as f:
                return json.load(f), []
        except Exception as e:
            import os

            warnings.append(f"Failed to parse config.json: {e}")
            if os.getenv("CA_DEBUG"):
                import traceback

                traceback.print_exc()
            return {}, warnings

    def update_config(self, config: dict):
        """Updates the configuration file with the provided dictionary.

        Args:
            config: The configuration dictionary to save.
        """
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)

    def add_project(self, path: str, group: str) -> list:
        """Adds or updates a project in the project registry.

        Args:
            path: Absolute path to the project directory.
            group: Group name for the project.

        Returns:
            The updated project registry list.
        """
        config, _ = self.get_config()
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
        config, _ = self.get_config()
        registry = config.get("project_registry", [])
        new_registry = [item for item in registry if item["path"] != path]
        config["project_registry"] = new_registry
        self.update_config(config)
        return new_registry

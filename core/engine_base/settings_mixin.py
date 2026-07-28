import json
import shutil
from pathlib import Path
from typing import TYPE_CHECKING, Any

from core.logging_config import get_logger

if TYPE_CHECKING:
    from core.settings_manager import SettingsManager

logger = get_logger(__name__)


class _SettingsMixin:
    """Injecting hooks/plugins into engine-specific settings files."""

    # Provided by BaseEngine.__init__ / _ConfigMixin.
    if TYPE_CHECKING:
        settings_manager: "SettingsManager"

        def get_plugins_to_mount(self) -> list[dict[str, Any]]: ...

    def inject_hooks_to_settings(
        self, settings_rel_path: str, hooks: list[dict[str, Any]]
    ):
        settings_path = (Path.cwd() / settings_rel_path).absolute()
        self.settings_manager.inject_hooks(settings_path, hooks)
        if hooks:
            logger.info("Injected %d hooks into %s", len(hooks), settings_rel_path)

    def inject_plugins_to_settings(self, settings_rel_path: str):
        """Orchestrates the injection of plugin configurations into a settings file.

        Manages backups and delegates loading, formatting, and saving to helper methods.

        Args:
            settings_rel_path (str): Relative path to the settings file.
        """
        plugins = self.get_plugins_to_mount()
        if not plugins:
            return

        settings_path = (Path.cwd() / settings_rel_path).absolute()
        settings_path.parent.mkdir(parents=True, exist_ok=True)

        backup_path = settings_path.with_suffix(settings_path.suffix + ".bak")
        if settings_path.exists() and not backup_path.exists():
            shutil.copy2(settings_path, backup_path)
            logger.info("Created safety backup: %s", backup_path.name)

        data = self._load_config(settings_path)
        data["_ca_injected"] = True

        data = self._format_plugins_for_settings(data, plugins)

        self._save_config(settings_path, data)

        logger.info("Registered plugins in %s", settings_rel_path)

    def _load_config(self, path: Path) -> Any:
        """Loads a configuration file.

        Default implementation handles JSON. Subclasses can override for other formats.

        Args:
            path (Path): The path to the configuration file.

        Returns:
            Any: The loaded configuration data.
        """
        if not path.exists():
            return {}
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _save_config(self, path: Path, data: Any):
        """Saves configuration data to a file.

        Default implementation handles JSON.

        Args:
            path (Path): The path to the configuration file.
            data (Any): The data to save.
        """
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def _format_plugins_for_settings(self, data: Any, plugins: list[dict]) -> Any:
        """Formats plugin metadata for the specific engine's settings.

        Args:
            data (Any): The existing configuration data.
            plugins (List[dict]): The list of plugins to format.

        Returns:
            Any: The updated configuration data with plugins registered.
        """
        return data

    def restore_settings(self, settings_rel_path: str):
        settings_path = (Path.cwd() / settings_rel_path).absolute()
        self.settings_manager.restore_settings(settings_path)

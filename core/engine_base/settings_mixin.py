from pathlib import Path
from typing import TYPE_CHECKING, Any

from core.logging_config import get_logger

if TYPE_CHECKING:
    from core.settings_manager import SettingsManager

logger = get_logger(__name__)


class _SettingsMixin:
    """Injecting hooks into engine-specific settings files."""

    # Provided by BaseEngine.__init__.
    if TYPE_CHECKING:
        settings_manager: "SettingsManager"

    def inject_hooks_to_settings(
        self, settings_rel_path: str, hooks: list[dict[str, Any]]
    ):
        settings_path = (Path.cwd() / settings_rel_path).absolute()
        self.settings_manager.inject_hooks(settings_path, hooks)
        if hooks:
            logger.info("Injected %d hooks into %s", len(hooks), settings_rel_path)

    def restore_settings(self, settings_rel_path: str):
        settings_path = (Path.cwd() / settings_rel_path).absolute()
        self.settings_manager.restore_settings(settings_path)

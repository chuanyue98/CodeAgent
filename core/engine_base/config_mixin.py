from pathlib import Path
from typing import TYPE_CHECKING, Any

from core.hook_scanner import get_hooks_to_inject
from core.logging_config import get_logger
from core.plugin_scanner import get_plugins_to_mount
from core.skill_scanner import get_skills_to_mount

if TYPE_CHECKING:
    from core.config_manager import ConfigManager
    from core.hook_scanner import HookScanner
    from core.plugin_scanner import PluginScanner
    from core.skill_scanner import SkillScanner

logger = get_logger(__name__)


class _ConfigMixin:
    """Project-group/config resolution and resource discovery (skills, plugins, hooks)."""

    # Provided by BaseEngine.__init__ -- declared here so mypy knows these
    # exist without this mixin owning their construction.
    if TYPE_CHECKING:
        config_manager: "ConfigManager"
        full_config: dict
        skill_scanner: "SkillScanner"
        plugin_scanner: "PluginScanner"
        hook_scanner: "HookScanner"

    def _get_skill_search_roots(self) -> list[Path]:
        resource_root = self.config_manager.resolve_resource_root()
        return self.config_manager.get_skill_search_roots(resource_root)

    def _get_plugin_search_roots(self) -> list[Path]:
        resource_root = self.config_manager.resolve_resource_root()
        return self.config_manager.get_plugin_search_roots(resource_root)

    def _get_hook_search_roots(self) -> list[Path]:
        resource_root = self.config_manager.resolve_resource_root()
        return self.config_manager.get_hook_search_roots(resource_root)

    def get_current_project_group(self) -> str:
        return self.config_manager.get_current_project_group()

    def get_skills_to_mount(self) -> list[str]:
        """Retrieves the list of skill names to be mounted for the current project.

        Returns:
            List[str]: A list of skill names.
        """
        project_type = self.get_current_project_group()
        return get_skills_to_mount(
            self.full_config, self.skill_scanner, project_type=project_type
        )

    def get_plugins_to_mount(self) -> list[dict[str, Any]]:
        """Retrieves the list of plugins to be mounted for the current project.

        Returns:
            List[Dict[str, Any]]: A list of plugin metadata dictionaries.
        """
        project_type = self.get_current_project_group()
        plugins, warnings = get_plugins_to_mount(
            self.full_config, self.plugin_scanner, project_type=project_type
        )
        self._print_scan_warnings("Plugin Scanner", warnings)
        return plugins

    def get_hooks_to_inject(self) -> list[dict[str, Any]]:
        """Retrieves the list of hooks to be injected for the current project.

        Returns:
            List[Dict[str, Any]]: A list of hook metadata dictionaries.
        """
        project_type = self.get_current_project_group()
        hooks, warnings = get_hooks_to_inject(
            self.full_config, self.hook_scanner, project_type=project_type
        )
        self._print_scan_warnings("Hook Scanner", warnings)
        return hooks

    def _print_scan_warnings(self, scanner_name: str, warnings: list[str]) -> None:
        """Logs non-fatal scan warnings so they are visible to the user."""
        for warning in warnings:
            logger.warning("%s: %s", scanner_name, warning)

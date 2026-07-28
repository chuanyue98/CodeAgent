import re
from pathlib import Path
from typing import Any

from core.hook_scanner import get_hooks_to_inject
from core.logging_config import get_logger
from core.plugin_scanner import get_plugins_to_mount
from core.prompt_scanner import get_prompts_to_inject
from core.skill_scanner import get_skills_to_mount

logger = get_logger(__name__)


class _ConfigMixin:
    """Project-group/config resolution and resource discovery (skills, plugins, prompts, hooks)."""

    def _resolve_resource_root(self) -> Path:
        return self.config_manager.resolve_resource_root()

    def _load_full_config(self) -> dict:
        return self.config_manager.full_config

    def _resolve_config_groups(self, section_name: str) -> list[str]:
        cfg = self.full_config.get(section_name, {})
        groups = cfg.get("groups", {})
        mappings = cfg.get("project_mapping", [])
        default_group = cfg.get("default_group", "common")

        cwd_str = str(Path.cwd().as_posix())
        selected_group_name = default_group

        for mapping in mappings:
            pattern = mapping.get("pattern")
            if pattern:
                if re.search(pattern, cwd_str, re.IGNORECASE):
                    selected_group_name = mapping.get("group")
                    break

        if section_name == "prompts":
            logger.info("Prompts matched group: [%s]", selected_group_name)

        def resolve(name, visited=None):
            if visited is None:
                visited = set()
            if name in visited:
                return []

            visited.add(name)

            result = []
            if name in groups:
                for item in groups.get(name, []):
                    result.extend(resolve(item, visited))
            else:
                result.append(name)
            return result

        return list(dict.fromkeys(resolve(selected_group_name)))

    def _get_mapped_config_value(
        self,
        section_name: str,
        mapping_key: str,
        value_key: str,
    ) -> str | None:
        cfg = self.full_config.get(section_name, {})
        mappings = cfg.get(mapping_key, [])
        cwd_str = str(Path.cwd().as_posix())

        for mapping in mappings:
            pattern = mapping.get("pattern")
            if pattern and re.search(pattern, cwd_str, re.IGNORECASE):
                value = mapping.get(value_key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
        return None

    def _resolve_path_token(self, raw_path: str) -> Path:
        return self.config_manager.resolve_path_token(raw_path)

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

    def get_prompts_to_inject(self) -> list[str]:
        """Retrieves the list of prompt groups to be injected for the current project.

        Returns:
            List[str]: A list of prompt group names.
        """
        project_type = self.get_current_project_group()
        prompts, warnings = get_prompts_to_inject(
            self.full_config, self.prompt_scanner, project_type=project_type
        )
        self._print_scan_warnings("Prompt Scanner", warnings)
        return prompts

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

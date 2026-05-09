"""Scanner for discovering plugins in the plugins directory."""

import json
import os
import traceback
from pathlib import Path
from typing import Dict, List, Any


class PluginScanner:
    """Scanner class to automatically discover plugin categories and metadata."""

    def __init__(self, plugins_root: Path):
        """Initializes the PluginScanner with a root directory.

        Args:
            plugins_root: The root directory containing plugin categories.
        """
        self.plugins_root = plugins_root

    def scan(self) -> tuple[Dict[str, Dict[str, Any]], List[str]]:
        """Scans the plugins root directory for categories and plugin metadata.

        Returns:
            A tuple containing:
            - A dictionary mapping category names to dictionaries of plugin metadata.
            - A list of warning strings.
        """
        result = {}
        warnings = []
        if not self.plugins_root.exists():
            return result, warnings

        for category_dir in self.plugins_root.iterdir():
            if not category_dir.is_dir():
                continue
            category = category_dir.name
            plugins = {}
            for item in category_dir.iterdir():
                if not item.is_dir():
                    continue

                # Validation: Look for metadata.json or some common markers
                metadata_path = item / "metadata.json"
                metadata = {}
                if metadata_path.exists():
                    try:
                        with open(metadata_path, "r", encoding="utf-8") as f:
                            metadata = json.load(f)
                    except Exception as e:
                        msg = f"Failed to load metadata from {metadata_path}: {e}"
                        warnings.append(msg)
                        if os.getenv("CA_DEBUG"):
                            traceback.print_exc()
                        continue

                # Basic info
                metadata["name"] = item.name
                metadata["_plugin_dir"] = str(item.resolve().as_posix())

                # Check for standard prompt files
                prompt_files = []
                for suffix in [".md", ".txt"]:
                    # Priority: Platform specific -> Generic
                    for name in ["GEMINI", "standards", "README"]:
                        p = item / f"{name}{suffix}"
                        if p.exists():
                            prompt_files.append(str(p.resolve().as_posix()))

                metadata["_prompt_files"] = prompt_files
                plugins[item.name] = metadata

            if plugins:
                result[category] = plugins
        return result, warnings


def get_plugins_to_mount(
    config: dict,
    scanner: PluginScanner,
    project_type: str = "common",
) -> tuple[List[Dict[str, Any]], List[str]]:
    """Determines which plugins should be mounted based on configuration and environment.

    Args:
        config: The application configuration dictionary.
        scanner: An instance of PluginScanner.
        project_type: The type of project (e.g., 'common', 'web').

    Returns:
        A tuple of plugin metadata dictionaries to mount and warning messages.
    """
    scanned, scan_warnings = scanner.scan()
    result_map = {}
    warnings = list(scan_warnings)

    def add_plugin(full_name: str):
        if "/" not in full_name:
            return
        cat, name = full_name.split("/", 1)
        if cat in scanned and name in scanned[cat]:
            result_map[full_name] = scanned[cat][name]

    # 1. Read from config.groups[project_type].plugins
    group_plugins = config.get("groups", {}).get(project_type, {}).get("plugins", [])
    for pn in group_plugins:
        add_plugin(pn)

    # 2. Automatically load local plugins/ subdirectory if it exists in CWD
    cwd = Path.cwd()
    if cwd.resolve() != Path(__file__).resolve().parent.parent.resolve():
        local_plugins = cwd / "plugins"
        if local_plugins.exists():
            # Scan local plugins
            local_scanner = PluginScanner(local_plugins)
            local_scanned, local_warnings = local_scanner.scan()
            warnings.extend(local_warnings)
            for cat, plugins in local_scanned.items():
                for name, metadata in plugins.items():
                    full_name = f"{cat}/{name}"
                    if full_name not in result_map:
                        result_map[full_name] = metadata

    return list(result_map.values()), warnings

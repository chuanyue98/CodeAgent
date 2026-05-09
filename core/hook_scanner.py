"""Scanner for discovering hooks in the hooks directory."""

import json
import os
import traceback
from pathlib import Path
from typing import Dict, Any


class HookScanner:
    """Scanner class to automatically discover hook categories and metadata."""

    def __init__(self, hooks_roots: Path | list[Path]):
        """Initializes the HookScanner with one or more root directories.

        Args:
            hooks_roots: A single Path or a list of Path objects pointing to hook roots.
        """
        if isinstance(hooks_roots, Path):
            self.hooks_roots = [hooks_roots]
        else:
            self.hooks_roots = hooks_roots

    def scan(self) -> tuple[Dict[str, Dict[str, Any]], list[str]]:
        """Scans the hook root directories for categories and hook metadata.

        Returns:
            A tuple containing:
            - A dictionary mapping category names to dictionaries of hook metadata.
            - A list of warning strings encountered during scanning.
        """
        result = {}
        warnings = []
        # Iterate in reverse order so that hooks in earlier roots override later ones
        for root in reversed(self.hooks_roots):
            if not root.exists():
                continue

            for category_dir in root.iterdir():
                if not category_dir.is_dir():
                    continue

                category = category_dir.name
                if category not in result:
                    result[category] = {}

                for item in category_dir.iterdir():
                    if item.is_dir() and (item / "metadata.json").exists():
                        metadata_path = item / "metadata.json"
                        try:
                            with open(metadata_path, "r", encoding="utf-8") as f:
                                metadata = json.load(f)
                                metadata["_hook_dir"] = str(item.resolve().as_posix())
                                # Use category/name as unique identifier for overriding
                                result[category][item.name] = metadata
                        except Exception as e:
                            if os.getenv("CA_DEBUG"):
                                traceback.print_exc()
                            warnings.append(
                                f"Failed to load hook metadata from {metadata_path}: {e}"
                            )
                            continue
        return result, warnings


def get_hooks_to_inject(
    config: dict,
    scanner: HookScanner,
    project_type: str = "common",
    extra_hooks: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Determines which hooks should be injected based on configuration and environment.

    Args:
        config: The application configuration dictionary.
        scanner: An instance of HookScanner.
        project_type: The type of project (e.g., 'common', 'web').
        extra_hooks: Additional hooks to inject.

    Returns:
        A list of hook metadata dictionaries to inject.
    """
    scanned, _ = scanner.scan()
    result_map = {}  # Use name as key to avoid duplicates

    def add_hook(full_name: str):
        if "/" not in full_name:
            return
        cat, name = full_name.split("/", 1)
        if cat in scanned and name in scanned[cat]:
            hook_data = scanned[cat][name].copy()
            # Replace placeholder in the command
            if "command" in hook_data and "{hook_dir}" in hook_data["command"]:
                hook_data["command"] = hook_data["command"].replace(
                    "{hook_dir}", hook_data["_hook_dir"]
                )
            result_map[full_name] = hook_data

    # 1. Read from config.groups[project_type].hooks
    group_hooks = config.get("groups", {}).get(project_type, {}).get("hooks", [])
    for hn in group_hooks:
        add_hook(hn)

    # 2. Compatibility with legacy config.hooks.project_hooks format
    legacy = config.get("hooks", {}).get("project_hooks", {}).get(project_type, [])
    for hn in legacy:
        add_hook(hn)

    # 3. Extra hooks passed by the caller
    if extra_hooks:
        for hn in extra_hooks:
            add_hook(hn)

    # 4. Automatic loading: include hooks from non-standard roots (e.g., project-local hooks)
    ca_root = Path(__file__).resolve().parent.parent
    ca_hooks_root = (ca_root / "hooks").resolve()

    for root in scanner.hooks_roots:
        resolved_root = root.resolve()
        if resolved_root != ca_hooks_root:
            # This is a local hooks directory, scan and add all
            for cat, hooks in scanned.items():
                for name, metadata in hooks.items():
                    hook_path = Path(metadata["_hook_dir"]).resolve()
                    if resolved_root in hook_path.parents:
                        full_name = f"{cat}/{name}"
                        if full_name not in result_map:
                            add_hook(full_name)

    return list(result_map.values())

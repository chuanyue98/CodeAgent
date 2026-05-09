"""Scanner for discovering prompt templates in the prompt directory."""

import os
import traceback
from pathlib import Path
from typing import Dict, List

DEFAULT_GROUP_PROMPTS: dict[str, list[str]] = {
    "common": ["base", "engineering", "coding"],
    "work": ["base", "engineering", "coding", "work"],
    "web": ["base", "engineering", "coding", "web"],
    "codeagent": ["base", "engineering", "coding", "self-dev"],
}


class PromptScanner:
    """Scanner class to automatically discover prompt groups and files."""

    def __init__(self, prompt_root: Path):
        """Initializes the PromptScanner with a root directory.

        Args:
            prompt_root: The root directory containing prompt group subdirectories.
        """
        self.prompt_root = prompt_root

    def scan(self) -> tuple[Dict[str, List[str]], List[str]]:
        """Scans the prompt root directory for prompt groups and files.

        Returns:
            A tuple containing:
            - A dictionary mapping group names to lists of prompt names (file stems).
            - A list of warning strings.
        """
        result = {}
        warnings = []
        if not self.prompt_root.exists():
            return result, warnings

        try:
            for group_dir in self.prompt_root.iterdir():
                if not group_dir.is_dir():
                    continue
                group = group_dir.name
                prompts = []
                try:
                    for md_file in group_dir.glob("*.md"):
                        if md_file.stem not in ("README", "IMPLEMENTATION_PLAN"):
                            prompts.append(md_file.stem)
                except Exception as e:
                    warnings.append(f"Failed to scan directory {group_dir}: {e}")
                    if os.getenv("CA_DEBUG"):
                        traceback.print_exc()
                    continue

                if prompts:
                    result[group] = prompts
        except Exception as e:
            warnings.append(f"Failed to iterate prompt root {self.prompt_root}: {e}")
            if os.getenv("CA_DEBUG"):
                traceback.print_exc()

        return result, warnings


def get_prompts_to_inject(
    config: dict,
    scanner: PromptScanner,
    project_type: str = "common",
    extra_prompts: List[str] = None,
) -> tuple[List[str], List[str]]:
    """Determines which prompt groups should be injected based on configuration.

    Args:
        config: The application configuration dictionary.
        scanner: An instance of PromptScanner.
        project_type: The type of project (e.g., 'common', 'web').
        extra_prompts: Additional prompt groups to inject.

    Returns:
        A tuple of prompt group names to inject and warning messages.
    """
    scanned, scan_warnings = scanner.scan()
    result: List[str] = []
    groups_cfg = config.get("groups", {})
    project_group_cfg = groups_cfg.get(project_type, {})
    group_prompts_configured = (
        project_type in groups_cfg and "prompts" in project_group_cfg
    )

    def add_items(items: List[str] | None):
        if not items:
            return
        for item in items:
            if item not in result:
                result.append(item)

    # 1. Read from config.groups[project_type].prompts (Configuration managed by Web UI)
    group_prompts = config.get("groups", {}).get(project_type, {}).get("prompts", [])
    add_items(group_prompts)

    # 2. Compatibility with legacy config.prompts.project_prompts format
    legacy = config.get("prompts", {}).get("project_prompts", {}).get(project_type, [])
    add_items(legacy)

    # 3. Use default mappings only if no explicit configuration exists
    if not result and not group_prompts_configured and not legacy:
        defaults = DEFAULT_GROUP_PROMPTS.get(
            project_type, DEFAULT_GROUP_PROMPTS["common"]
        )
        add_items([group for group in defaults if group in scanned])

    # 4. Extra prompts passed by the caller
    add_items(extra_prompts)

    return result, scan_warnings

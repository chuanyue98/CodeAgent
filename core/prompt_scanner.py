"""Scanner for discovering prompt templates in the prompt directory."""

import os
import traceback
from pathlib import Path

# 放在分组目录里、但不是规范正文的文档。
EXCLUDED_PROMPT_FILES = {"README.md", "IMPLEMENTATION_PLAN.md"}

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

    def scan(self) -> tuple[dict[str, list[str]], list[str]]:
        """Scans the prompt root directory for prompt groups and files.

        Returns:
            A tuple containing:
            - A dictionary mapping group names to lists of prompt names (file stems).
            - A list of warning strings.
        """
        result: dict[str, list[str]] = {}
        warnings: list[str] = []
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
                        if md_file.name not in EXCLUDED_PROMPT_FILES:
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

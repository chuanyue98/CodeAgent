from pathlib import Path
from core.prompt_scanner import PromptScanner


class PromptService:
    """Service for managing and scanning prompt templates."""

    def __init__(self, prompts_root: Path, root_dir: Path):
        """Initializes the PromptService with prompts root and project root.

        Args:
            prompts_root: Path to the directory containing prompt categories.
            root_dir: The absolute root directory of the project for path relativization.
        """
        self.prompts_root = prompts_root
        self.root_dir = root_dir
        self.scanner = PromptScanner(prompts_root)

    def get_prompt_groups(self) -> list[dict]:
        """Scans and groups prompt files by category.

        Returns:
            A list of dictionaries, each representing a prompt group/category.
            Each dictionary contains: id, name, description, readme (combined content),
            and a list of individual prompt files with their paths.
        """
        scanned = self.scanner.scan()
        prompt_groups = []
        excluded_files = {"README.md", "IMPLEMENTATION_PLAN.md"}

        for category in sorted(scanned.keys()):
            group_dir = self.prompts_root / category
            files = []
            combined_parts = []
            description = ""

            for prompt_file in sorted(group_dir.glob("*.md")):
                if prompt_file.name in excluded_files:
                    continue

                content = prompt_file.read_text(encoding="utf-8").strip()
                if not content:
                    continue

                files.append(
                    {
                        "name": prompt_file.stem,
                        "path": str(prompt_file.resolve().as_posix()),
                    }
                )
                combined_parts.append(f"## {prompt_file.stem}\n\n{content}")

                if not description:
                    for line in content.splitlines():
                        stripped = line.strip()
                        if stripped and not stripped.startswith("#"):
                            description = stripped
                            break

            prompt_groups.append(
                {
                    "id": category,
                    "name": category,
                    "description": description
                    or f"{len(files)} prompt files in '{category}'",
                    "readme": "\n\n".join(combined_parts),
                    "files": files,
                }
            )
        return prompt_groups

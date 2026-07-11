"""Scanner for discovering skills in the skills directory."""

import os
import traceback
from pathlib import Path
from typing import Dict, List, Optional


class SkillScanner:
    """Scanner class to automatically discover skill categories and individual skills."""

    def __init__(self, skills_root: Path):
        """Initializes the SkillScanner with a root directory.

        Args:
            skills_root: The root directory containing skill categories.
        """
        self.skills_root = skills_root

    def scan(self) -> tuple[Dict[str, List[str]], List[str]]:
        """Scans the skills root directory for categories and individual skill definitions.

        Returns:
            A tuple containing:
            - A dictionary mapping category names to lists of skill names.
            - A list of warning messages encountered during scanning.
        """
        result: Dict[str, List[str]] = {}
        warnings: List[str] = []
        if not self.skills_root.exists():
            return result, warnings

        try:
            for category_dir in self.skills_root.iterdir():
                if not category_dir.is_dir():
                    continue
                category = category_dir.name
                skills = []
                try:
                    for item in category_dir.iterdir():
                        if item.is_dir():
                            if (item / "SKILL.md").exists():
                                skills.append(item.name)
                            else:
                                warnings.append(
                                    f"Skill directory '{item}' does not contain SKILL.md"
                                )
                except Exception as e:
                    warnings.append(
                        f"Failed to scan category directory '{category_dir}': {e}"
                    )
                    if os.getenv("CA_DEBUG"):
                        traceback.print_exc()

                if skills:
                    result[category] = skills
        except Exception as e:
            warnings.append(f"Failed to iterate skills root '{self.skills_root}': {e}")
            if os.getenv("CA_DEBUG"):
                traceback.print_exc()

        return result, warnings


def get_skills_to_mount(
    config: dict,
    scanner: SkillScanner,
    project_type: str = "common",
    extra_skills: Optional[List[str]] = None,
) -> List[str]:
    """Determines which skills should be mounted based on configuration and environment.

    Args:
        config: The application configuration dictionary.
        scanner: An instance of SkillScanner.
        project_type: The type of project (e.g., 'common', 'web').
        extra_skills: Additional skills to mount.

    Returns:
        A list of unique skill identifiers to mount.
    """
    result: list[str] = []

    def _add(items):
        for item in items:
            if item not in result:
                result.append(item)

    # 1. Read from config.groups[project_type].skills (Configuration managed by Web UI)
    group_skills = config.get("groups", {}).get(project_type, {}).get("skills", [])
    _add(group_skills)

    # 2. Compatibility with legacy config.skills.project_skills format
    legacy = config.get("skills", {}).get("project_skills", {}).get(project_type, [])
    _add(legacy)

    # 3. Extra skills passed by the caller
    if extra_skills:
        _add(extra_skills)

    # 4. Automatically load skills from the local 'skills/' subdirectory
    cwd = Path.cwd()
    if cwd != Path(__file__).resolve().parent.parent:
        local_skills = cwd / "skills"
        if local_skills.exists():
            for item in local_skills.iterdir():
                if item.is_dir():
                    _add([item.name])

    return result

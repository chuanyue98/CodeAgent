"""Scanner for discovering skills in the skills directory."""

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

    def scan(self) -> Dict[str, List[str]]:
        """Scans the skills root directory for categories and individual skill definitions.

        Returns:
            A dictionary mapping category names to lists of skill names.
        """
        result: Dict[str, List[str]] = {}
        if not self.skills_root.exists():
            return result

        for category_dir in self.skills_root.iterdir():
            if not category_dir.is_dir():
                continue
            category = category_dir.name
            skills = []
            for item in category_dir.iterdir():
                if item.is_dir() and (item / "SKILL.md").exists():
                    skills.append(item.name)
            if skills:
                result[category] = skills
        return result


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
    result = set()

    # 1. Read from config.groups[project_type].skills (Configuration managed by Web UI)
    group_skills = config.get("groups", {}).get(project_type, {}).get("skills", [])
    result.update(group_skills)

    # 2. Compatibility with legacy config.skills.project_skills format
    legacy = config.get("skills", {}).get("project_skills", {}).get(project_type, [])
    result.update(legacy)

    # 3. Extra skills passed by the caller
    if extra_skills:
        result.update(extra_skills)

    # 4. Automatically load skills from the local 'skills/' subdirectory
    cwd = Path.cwd()
    if cwd != Path(__file__).resolve().parent.parent:
        local_skills = cwd / "skills"
        if local_skills.exists():
            for item in local_skills.iterdir():
                if item.is_dir():
                    result.add(item.name)

    return list(result)

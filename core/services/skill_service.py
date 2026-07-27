import yaml  # type: ignore[import-untyped]
from pathlib import Path
from core.skill_scanner import SkillScanner


class SkillService:
    """Service for managing and scanning agent skills."""

    def __init__(self, skills_root: Path):
        """Initializes the SkillService with the skills root directory.

        Args:
            skills_root: Path to the root directory containing skills.
        """
        self.skills_root = skills_root
        self.scanner = SkillScanner(skills_root)

    def get_detailed_skills(self) -> dict:
        """Retrieves a detailed dictionary of all scanned skills by category.

        Returns:
            A dictionary mapping categories to lists of skill details.
            Each skill detail includes: name, id, description, and readme (content).
        """
        scanned, warnings = self.scanner.scan()
        detailed_skills: dict[str, list[dict[str, object]]] = {}
        for category, skills in scanned.items():
            detailed_skills[category] = []
            for skill_name in skills:
                skill_dir = self.skills_root / category / skill_name
                skill_md_path = skill_dir / "SKILL.md"

                content = ""
                body = ""
                description = ""
                if skill_md_path.exists():
                    content = skill_md_path.read_text(encoding="utf-8")
                    body = content

                    # Extract description from YAML frontmatter, and strip it
                    # from the body so the detail view doesn't render the raw
                    # "name: ... description: ..." block above the real docs.
                    if content.startswith("---"):
                        try:
                            parts = content.split("---", 2)
                            if len(parts) >= 3:
                                frontmatter = yaml.safe_load(parts[1])
                                if isinstance(frontmatter, dict):
                                    description = frontmatter.get("description", "")
                                body = parts[2].lstrip("\n")
                        except Exception:
                            pass

                    # Fallback: find the first non-empty, non-markdown-control line
                    if not description:
                        for line in content.splitlines():
                            line = line.strip()
                            if (
                                line
                                and not line.startswith("---")
                                and not line.startswith("#")
                            ):
                                description = line
                                break

                # List scripts in the scripts/ subdirectory
                scripts = []
                scripts_dir = skill_dir / "scripts"
                if scripts_dir.is_dir():
                    try:
                        for script_file in scripts_dir.iterdir():
                            if (
                                script_file.is_file()
                                and not script_file.name.startswith(".")
                            ):
                                scripts.append(script_file.name)
                    except OSError:
                        # Silently ignore directory access errors during scan
                        pass

                detailed_skills[category].append(
                    {
                        "name": skill_name,
                        "id": f"{category}/{skill_name}",
                        "description": description,
                        "readme": body,
                        "scripts": sorted(scripts),
                    }
                )
        return detailed_skills

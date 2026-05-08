from __future__ import annotations

import re
from pathlib import Path


class TaskService:
    """Service for listing and reading tasks from the tasks directory."""

    def __init__(self, tasks_root: Path):
        self.tasks_root = tasks_root

    def list_tasks(self) -> list[dict]:
        if not self.tasks_root.exists():
            return []

        tasks = []
        for md_file in sorted(self.tasks_root.glob("*.md")):
            tasks.append(self._parse_task(md_file, full_content=False))
        return tasks

    def get_task(self, name: str) -> dict | None:
        path = self.tasks_root / f"{name}.md"
        if not path.exists():
            return None
        return self._parse_task(path, full_content=True)

    def _parse_task(self, path: Path, full_content: bool = False) -> dict:
        try:
            content = path.read_text(encoding="utf-8")
        except OSError:
            content = ""

        lines = content.splitlines()
        title = path.stem

        # First `# ` heading as title
        for line in lines:
            if line.startswith("# "):
                title = line[2:].strip()
                break

        # First non-empty, non-heading line as description
        description = ""
        for line in lines:
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                description = stripped[:120]
                break

        stages = _parse_stages(content)

        result: dict = {
            "name": path.stem,
            "title": title,
            "description": description,
            "hasStages": bool(stages),
            "stages": stages,
        }
        if full_content:
            result["content"] = content
        return result


def _parse_stages(content: str) -> list[dict]:
    stages = []
    sections = re.split(r"^##\s+", content, flags=re.MULTILINE)
    for section in sections:
        if not section.strip():
            continue
        lines = section.splitlines()
        name = lines[0].strip()
        goal = ""
        status = ""
        for line in lines:
            if "**目标**" in line and ":" in line:
                goal = line.split(":", 1)[1].strip()
            elif "**状态**" in line and ":" in line:
                raw = line.split(":", 1)[1].strip()
                status = raw.strip("[]").strip()
        if status or goal:
            stages.append({"name": name, "status": status, "goal": goal})
    return stages

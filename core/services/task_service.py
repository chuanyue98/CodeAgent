from __future__ import annotations

import collections
import os
import re
from pathlib import Path

_SAFE_NAME_RE = re.compile(r"^[\w.-]+$")


def is_valid_task_name(name: str) -> bool:
    return bool(_SAFE_NAME_RE.match(name))


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

    def create_task(
        self,
        name: str,
        title: str,
        objective: str = "",
        context: str = "",
        instructions: str = "",
        verification: str = "",
    ) -> dict:
        """Writes a new task blueprint as a plain ``.md`` file in the tasks root.

        Follows the four-section structure (Objective/Context/Instructions/
        Verification) documented in ``skills/base/task-authoring/SKILL.md``.
        """
        if not is_valid_task_name(name):
            raise ValueError("Task name must match [\\w.-]+")

        self.tasks_root.mkdir(parents=True, exist_ok=True)
        path = self.tasks_root / f"{name}.md"
        if not path.resolve().is_relative_to(self.tasks_root.resolve()):
            raise ValueError("Invalid task name")
        if path.exists():
            raise FileExistsError(f"Task '{name}' already exists")

        content = (
            f"# {title or name}\n\n"
            f"## Objective (目标)\n{objective}\n\n"
            f"## Context (背景)\n{context}\n\n"
            f"## Instructions (指令)\n{instructions}\n\n"
            f"## Verification (验证)\n{verification}\n"
        )
        path.write_text(content, encoding="utf-8")
        return self._parse_task(path, full_content=True)

    def get_task(self, name: str, log_path: str | None = None) -> dict | None:
        if not _SAFE_NAME_RE.match(name):
            return None
        path = self.tasks_root / f"{name}.md"
        if not path.resolve().is_relative_to(self.tasks_root.resolve()):
            return None
        if not path.exists():
            return None

        task_data = self._parse_task(path, full_content=True)

        if log_path and os.path.exists(log_path):
            try:
                # Only read last 100 lines for efficiency
                with open(log_path, "r", encoding="utf-8") as f:
                    task_data["logs"] = "".join(collections.deque(f, maxlen=100))
            except Exception:
                task_data["logs"] = "Failed to read logs."

        return task_data

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

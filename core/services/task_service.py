import re
from pathlib import Path


class TaskService:
    """Service for managing tasks and implementation plans."""

    def __init__(self, root_dir: Path):
        """Initializes the TaskService with the project root directory.

        Args:
            root_dir: Path to the project root directory.
        """
        self.root_dir = root_dir

    def get_plan_status(self) -> dict:
        """Parses the IMPLEMENTATION_PLAN.md file to retrieve task statuses.

        Returns:
            A dictionary containing the existence of the plan, a list of tasks,
            and any parsing errors. Each task includes: name, status, and goal.
        """
        plan_path = self.root_dir / "IMPLEMENTATION_PLAN.md"
        if not plan_path.exists():
            return {"exists": False, "tasks": []}

        try:
            content = plan_path.read_text(encoding="utf-8")
            tasks = []
            sections = re.split(r"^##\s+", content, flags=re.MULTILINE)
            for section in sections:
                if not section.startswith("阶段"):
                    continue

                lines = section.splitlines()
                name = lines[0].strip()
                goal = ""
                status = ""

                for line in lines:
                    if "**目标**:" in line:
                        goal = line.split("**目标**:", 1)[1].strip()
                    elif "**状态**:" in line:
                        status = line.split("**状态**:", 1)[1].strip()
                        status = status.strip("[]")

                tasks.append({"name": name, "status": status, "goal": goal})

            return {"exists": True, "tasks": tasks}
        except Exception:
            return {"exists": False, "tasks": [], "error": "Error parsing plan"}

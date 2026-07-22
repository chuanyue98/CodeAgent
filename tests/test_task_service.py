import pytest
from core.services.task_service import TaskService


def test_create_task_writes_expected_sections(tmp_path):
    service = TaskService(tmp_path)
    task = service.create_task(
        "daily-audit",
        "Daily Code Audit",
        objective="Check for regressions",
        context="Runs every morning",
        instructions="Run the linter and summarize",
        verification="No new lint errors",
    )

    path = tmp_path / "daily-audit.md"
    assert path.exists()
    assert task["name"] == "daily-audit"
    assert task["title"] == "Daily Code Audit"
    assert task["description"] == "Check for regressions"
    assert task["hasStages"] is False
    assert "## Objective (目标)" in task["content"]
    assert "## Verification (验证)" in task["content"]

    listed = service.list_tasks()
    assert [t["name"] for t in listed] == ["daily-audit"]


def test_create_task_rejects_duplicate_name(tmp_path):
    service = TaskService(tmp_path)
    service.create_task("daily-audit", "Daily Code Audit")

    with pytest.raises(FileExistsError):
        service.create_task("daily-audit", "Another Title")


def test_create_task_rejects_unsafe_name(tmp_path):
    service = TaskService(tmp_path)

    with pytest.raises(ValueError):
        service.create_task("../escape", "Escape Attempt")


def test_create_task_creates_tasks_root_if_missing(tmp_path):
    tasks_root = tmp_path / "nested" / "tasks"
    service = TaskService(tasks_root)

    service.create_task("bootstrap", "Bootstrap Task")

    assert (tasks_root / "bootstrap.md").exists()

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


def test_update_task_overwrites_content(tmp_path):
    service = TaskService(tmp_path)
    service.create_task("daily-audit", "Daily Code Audit", objective="old")

    new_content = "# New Title\n\n## Objective (目标)\nnew objective\n"
    updated = service.update_task("daily-audit", new_content)

    path = tmp_path / "daily-audit.md"
    assert path.read_text(encoding="utf-8") == new_content
    assert updated["name"] == "daily-audit"
    assert updated["title"] == "New Title"
    assert "new objective" in updated["content"]


def test_update_task_rejects_unsafe_name(tmp_path):
    service = TaskService(tmp_path)

    with pytest.raises(ValueError):
        service.update_task("../escape", "# content")


def test_update_task_rejects_missing_task(tmp_path):
    service = TaskService(tmp_path)

    with pytest.raises(FileNotFoundError):
        service.update_task("no-such-task", "# content")


def test_delete_task_removes_file(tmp_path):
    service = TaskService(tmp_path)
    service.create_task("daily-audit", "Daily Code Audit")

    assert service.delete_task("daily-audit") is True
    assert not (tmp_path / "daily-audit.md").exists()
    assert service.list_tasks() == []


def test_delete_task_missing_returns_false(tmp_path):
    service = TaskService(tmp_path)

    assert service.delete_task("no-such-task") is False


def test_delete_task_rejects_unsafe_name(tmp_path):
    service = TaskService(tmp_path)

    with pytest.raises(ValueError):
        service.delete_task("../escape")

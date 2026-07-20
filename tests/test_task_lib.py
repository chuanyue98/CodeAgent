from __future__ import annotations

import pytest

from core import task_lib


def test_get_tasks_dir_returns_default_when_no_env(tmp_path, monkeypatch):
    monkeypatch.delenv("CA_TASKS_ROOT", raising=False)
    monkeypatch.chdir(tmp_path)
    result = task_lib.get_tasks_dir()
    assert result.is_dir() or not result.exists()  # may not exist yet


def test_get_tasks_dir_env_override(tmp_path, monkeypatch):
    tasks = tmp_path / "my_tasks"
    tasks.mkdir()
    monkeypatch.setenv("CA_TASKS_ROOT", str(tasks))
    result = task_lib.get_tasks_dir()
    assert result == tasks.resolve()


def test_list_tasks_empty_dir(tmp_path, monkeypatch):
    tasks_dir = tmp_path / "tasks"
    tasks_dir.mkdir()
    monkeypatch.setenv("CA_TASKS_ROOT", str(tasks_dir))
    assert task_lib.list_tasks() == []


def test_list_tasks_sorted(tmp_path, monkeypatch):
    tasks_dir = tmp_path / "tasks"
    tasks_dir.mkdir()
    (tasks_dir / "zebra.md").write_text("# zebra")
    (tasks_dir / "alpha.md").write_text("# alpha")
    monkeypatch.setenv("CA_TASKS_ROOT", str(tasks_dir))
    assert task_lib.list_tasks() == ["alpha", "zebra"]


def test_parse_range_expression_valid():
    assert task_lib.parse_range_expression("1-3") == (1, 3)
    assert task_lib.parse_range_expression("10-20") == (10, 20)


def test_parse_range_expression_invalid():
    assert task_lib.parse_range_expression("abc") is None
    assert task_lib.parse_range_expression("3-1") is None
    assert task_lib.parse_range_expression("0-5") is None
    assert task_lib.parse_range_expression("1+2") is None


def test_parse_combination_expression_valid():
    assert task_lib.parse_combination_expression("1+2", ["a", "b", "c"]) == ["a", "b"]


def test_parse_combination_expression_with_names():
    assert task_lib.parse_combination_expression("a+c", ["a", "b", "c"]) == ["a", "c"]


def test_parse_combination_expression_invalid():
    with pytest.raises(ValueError):
        task_lib.parse_combination_expression("1+9", ["a", "b"])


def test_read_task_prompt_existing(tmp_path, monkeypatch):
    task_file = tmp_path / "my_task.md"
    task_file.write_text("# My Task\n\nDescription here.")
    monkeypatch.setenv("CA_TASKS_ROOT", str(tmp_path))
    content = task_lib.read_task_prompt(task_file)
    assert "My Task" in content


def test_read_task_prompt_missing(tmp_path):
    missing = tmp_path / "nonexistent.md"
    with pytest.raises(FileNotFoundError):
        task_lib.read_task_prompt(missing)


def test_handle_task_mode_literal_name_wins_over_combination_syntax(
    tmp_path, monkeypatch
):
    tasks_dir = tmp_path / "tasks"
    tasks_dir.mkdir()
    (tasks_dir / "deploy+rollback.md").write_text("# Deploy and rollback")
    monkeypatch.setenv("CA_TASKS_ROOT", str(tasks_dir))

    content = task_lib.handle_task_mode("deploy+rollback")

    assert content is not None
    assert "Deploy and rollback" in content


def test_handle_task_mode_still_combines_when_no_literal_match(tmp_path, monkeypatch):
    tasks_dir = tmp_path / "tasks"
    tasks_dir.mkdir()
    (tasks_dir / "a.md").write_text("# A")
    (tasks_dir / "b.md").write_text("# B")
    monkeypatch.setenv("CA_TASKS_ROOT", str(tasks_dir))

    content = task_lib.handle_task_mode("a+b")

    assert content is not None
    assert "# A" in content and "# B" in content


def test_handle_task_mode_literal_name_wins_over_range_syntax(tmp_path, monkeypatch):
    tasks_dir = tmp_path / "tasks"
    tasks_dir.mkdir()
    (tasks_dir / "3-5.md").write_text("# Literally named 3-5")
    monkeypatch.setenv("CA_TASKS_ROOT", str(tasks_dir))

    content = task_lib.handle_task_mode("3-5", allow_range=True)

    assert content is not None
    assert "Literally named 3-5" in content


def test_get_tasks_dir_falls_back_when_config_is_not_an_object(tmp_path, monkeypatch):
    monkeypatch.delenv("CA_TASKS_ROOT", raising=False)
    config_path = tmp_path / "config.json"
    config_path.write_text("[]")
    monkeypatch.setattr(task_lib, "get_default_config_path", lambda root: config_path)

    # Must fall back to the bundled resource root instead of raising
    # AttributeError from calling .get() on a non-dict parsed config.
    result = task_lib.get_tasks_dir()
    assert result is not None


def test_get_tasks_dir_falls_back_when_paths_section_is_not_an_object(
    tmp_path, monkeypatch
):
    monkeypatch.delenv("CA_TASKS_ROOT", raising=False)
    config_path = tmp_path / "config.json"
    config_path.write_text('{"paths": "oops"}')
    monkeypatch.setattr(task_lib, "get_default_config_path", lambda root: config_path)

    # config itself is a dict (passes the isinstance guard), but
    # config["paths"] is a string -- .get("resource_root") on it must not
    # raise AttributeError uncaught.
    result = task_lib.get_tasks_dir()
    assert result is not None


def test_set_additional_template_search_paths_appends(tmp_path):
    original = list(task_lib._ADDITIONAL_TEMPLATE_SEARCH_PATHS)
    try:
        task_lib.set_additional_template_search_paths([str(tmp_path)])
        assert str(tmp_path) in task_lib._ADDITIONAL_TEMPLATE_SEARCH_PATHS
    finally:
        task_lib._ADDITIONAL_TEMPLATE_SEARCH_PATHS[:] = original

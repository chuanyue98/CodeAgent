import os
from pathlib import Path

import pytest

from core.runtime_paths import get_run_dir, migrate_legacy_runs
from core.services.run_store import RunStore, TaskRunRecord
from core.services.runner_service import TaskRunner


def test_runner_writes_only_to_data_directory(tmp_path):
    code = tmp_path / "readonly-install"
    runner = TaskRunner(code)
    try:
        assert runner.log_dir == get_run_dir()
        assert runner._run_store.db_path.is_file()
        assert not code.exists()
    finally:
        runner.close()


def seed_legacy(path, *, running=False):
    path.mkdir()
    log = path / "old.log"
    log.write_text("历史中文日志", encoding="utf-8")
    store = RunStore(path / "runs.db")
    store.upsert(
        TaskRunRecord(
            "old",
            "codex",
            os.getpid() if running else None,
            "running" if running else "completed",
            str(log),
            1,
        )
    )
    store.close()


def test_migration_preserves_original_and_rewrites_log_paths(tmp_path):
    old, new = tmp_path / "old", tmp_path / "new"
    seed_legacy(old)
    original = (old / "runs.db").read_bytes()
    assert migrate_legacy_runs(old, new)
    store = RunStore(new / "runs.db")
    try:
        record = store.get("old")
        assert record is not None
        assert Path(record.log_path) == new / "old.log"
        assert Path(record.log_path).read_text(encoding="utf-8") == "历史中文日志"
    finally:
        store.close()
    assert (old / "runs.db").read_bytes() == original
    assert not migrate_legacy_runs(old, new)


def test_migration_refuses_live_legacy_tasks(tmp_path):
    old, new = tmp_path / "old", tmp_path / "new"
    seed_legacy(old, running=True)
    with pytest.raises(RuntimeError, match="活动任务"):
        migrate_legacy_runs(old, new)
    assert not new.exists()
    assert (old / "runs.db").exists()


def test_migration_missing_log_does_not_publish_partial_database(tmp_path):
    old, new = tmp_path / "old", tmp_path / "new"
    seed_legacy(old)
    (old / "old.log").unlink()
    with pytest.raises(RuntimeError, match="缺少日志"):
        migrate_legacy_runs(old, new)
    assert not new.exists()


def test_lazy_runner_import_does_not_create_database(tmp_path, monkeypatch):
    from core.web.routers.tasks import LazyTaskRunner

    monkeypatch.setenv("CA_DATA_DIR", str(tmp_path / "new-data"))
    runner = LazyTaskRunner()
    assert not get_run_dir().exists()
    runner.close()
    assert not get_run_dir().exists()

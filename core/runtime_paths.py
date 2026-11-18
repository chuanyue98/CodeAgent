"""可写运行数据与安装代码分离；旧目录只复制，不删除。"""

from __future__ import annotations

import os
import shutil
import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path

import psutil

from core.lock_manager import LockManager
from core.resource_locator import CODE_ROOT
from core.utils.process_tree import process_created_at


def get_data_dir() -> Path:
    return (
        Path(os.environ.get("CA_DATA_DIR", str(Path.home() / ".codeagent")))
        .expanduser()
        .resolve()
    )


def get_run_dir() -> Path:
    return get_data_dir() / "runs"


def migrate_legacy_runs(legacy: Path, destination: Path) -> bool:
    """首次启动复制旧数据库和日志；有活动进程时拒绝迁移，原件始终保留。"""
    source = legacy / "runs.db"
    if not source.is_file() or (destination / "runs.db").exists():
        return False
    destination.parent.mkdir(parents=True, exist_ok=True)
    locks = LockManager()
    handle = locks.acquire_resource_lock(destination.parent / "runs-migration.lock")
    try:
        if (destination / "runs.db").exists():
            return False
        with closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)) as old:
            columns = {
                row[1] for row in old.execute("PRAGMA table_info(runs)").fetchall()
            }
            if "process_created_at" in columns:
                running_rows = old.execute(
                    "SELECT pid, process_created_at FROM runs WHERE status = 'running'"
                ).fetchall()
            else:
                running_rows = [
                    (pid, None)
                    for (pid,) in old.execute(
                        "SELECT pid FROM runs WHERE status = 'running'"
                    ).fetchall()
                ]
            for pid, expected_created_at in running_rows:
                if not pid or not psutil.pid_exists(pid):
                    continue
                if expected_created_at is not None:
                    actual_created_at = process_created_at(pid)
                    if (
                        actual_created_at is None
                        or abs(actual_created_at - expected_created_at) > 0.5
                    ):
                        continue
                raise RuntimeError(
                    "旧运行目录仍有活动任务，请关闭旧版服务并结束任务后重试"
                )
            with tempfile.TemporaryDirectory(
                prefix="runs-migration-", dir=destination.parent
            ) as tmp:
                stage = Path(tmp) / "runs"
                stage.mkdir()
                with closing(sqlite3.connect(stage / "runs.db")) as new, new:
                    old.backup(new)
                    for task_id, raw_path in new.execute(
                        "SELECT task_id, log_path FROM runs"
                    ).fetchall():
                        if not raw_path:
                            continue
                        original = Path(raw_path)
                        if not original.is_file():
                            original = legacy / original.name
                        if not original.is_file():
                            raise RuntimeError(
                                f"迁移缺少日志文件：{raw_path}；原始数据库未改动"
                            )
                        copied = stage / original.name
                        if (
                            copied.exists()
                            and copied.read_bytes() != original.read_bytes()
                        ):
                            raise RuntimeError(f"迁移日志文件名冲突：{original.name}")
                        shutil.copy2(original, copied)
                        if copied.stat().st_size != original.stat().st_size:
                            raise RuntimeError(f"迁移日志校验失败：{original}")
                        new.execute(
                            "UPDATE runs SET log_path = ? WHERE task_id = ?",
                            (str(destination / original.name), task_id),
                        )
                    new.commit()
                    if new.execute("PRAGMA integrity_check").fetchone() != ("ok",):
                        raise RuntimeError("迁移数据库校验失败")
                if destination.exists():
                    # 不覆盖其他来源的数据；空目录可以安全接收已校验的副本。
                    if any(destination.iterdir()):
                        raise RuntimeError(
                            "目标运行目录非空，拒绝覆盖，请设置新的 CA_DATA_DIR"
                        )
                    destination.rmdir()
                stage.rename(destination)
        return True
    finally:
        locks.release_resource_lock(handle)


def prepare_run_dir(code_root: Path = CODE_ROOT) -> Path:
    destination = get_run_dir()
    # 显式数据目录代表隔离环境，不自动导入真实安装目录的历史。
    if not os.environ.get("CA_DATA_DIR"):
        migrate_legacy_runs((code_root / ".ca_task_logs").resolve(), destination)
    destination.mkdir(parents=True, exist_ok=True)
    return destination

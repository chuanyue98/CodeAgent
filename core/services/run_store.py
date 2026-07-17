from __future__ import annotations

import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class TaskRunRecord:
    task_id: str
    engine: str
    pid: Optional[int]
    status: str
    log_path: str
    start_time: float
    session_id: Optional[str] = None
    workspace: Optional[str] = None


class RunStore:
    """Persists TaskRunStatus rows to a SQLite database so runs survive restarts."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        with closing(sqlite3.connect(self.db_path)) as con:
            with con:
                con.execute(
                    """
                    CREATE TABLE IF NOT EXISTS runs (
                        task_id TEXT PRIMARY KEY,
                        engine TEXT,
                        pid INTEGER,
                        status TEXT,
                        log_path TEXT,
                        start_time REAL,
                        session_id TEXT,
                        workspace TEXT
                    )
                    """
                )
                con.execute(
                    "CREATE INDEX IF NOT EXISTS idx_runs_status ON runs(status)"
                )
                columns = {row[1] for row in con.execute("PRAGMA table_info(runs)")}
                if "workspace" not in columns:
                    con.execute("ALTER TABLE runs ADD COLUMN workspace TEXT")

    def upsert(self, run: TaskRunRecord):
        with closing(sqlite3.connect(self.db_path)) as con:
            with con:
                con.execute(
                    """
                    INSERT INTO runs (task_id, engine, pid, status, log_path, start_time, session_id, workspace)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(task_id) DO UPDATE SET
                        pid = excluded.pid,
                        status = excluded.status,
                        session_id = excluded.session_id,
                        workspace = excluded.workspace
                    """,
                    (
                        run.task_id,
                        run.engine,
                        run.pid,
                        run.status,
                        run.log_path,
                        run.start_time,
                        run.session_id,
                        run.workspace,
                    ),
                )

    def get(self, task_id: str) -> Optional[TaskRunRecord]:
        with closing(sqlite3.connect(self.db_path)) as con:
            with con:
                row = con.execute(
                    "SELECT task_id, engine, pid, status, log_path, start_time, session_id, workspace FROM runs WHERE task_id = ?",
                    (task_id,),
                ).fetchone()
        if row is None:
            return None
        return TaskRunRecord(*row)

    def list_running(self) -> list[TaskRunRecord]:
        with closing(sqlite3.connect(self.db_path)) as con:
            with con:
                rows = con.execute(
                    "SELECT task_id, engine, pid, status, log_path, start_time, session_id, workspace FROM runs WHERE status = 'running'"
                ).fetchall()
        return [TaskRunRecord(*r) for r in rows]

    def update_status(
        self, task_id: str, status: str, session_id: Optional[str] = None
    ):
        with closing(sqlite3.connect(self.db_path)) as con:
            with con:
                con.execute(
                    "UPDATE runs SET status = ?, session_id = COALESCE(?, session_id) WHERE task_id = ?",
                    (status, session_id, task_id),
                )

    def delete(self, task_id: str):
        with closing(sqlite3.connect(self.db_path)) as con:
            with con:
                con.execute("DELETE FROM runs WHERE task_id = ?", (task_id,))

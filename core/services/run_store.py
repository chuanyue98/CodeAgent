from __future__ import annotations

import sqlite3
import threading
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
    """Persists TaskRunStatus rows to a SQLite database so runs survive restarts.

    A single persistent SQLite connection is held for the lifetime of the
    instance and guarded by a :class:`threading.Lock` so it can be shared
    safely across threads (``check_same_thread=False``). Every database
    operation acquires the lock first, guaranteeing that only one thread
    touches the connection at a time. Call :meth:`close` to release the
    connection when the store is no longer needed.
    """

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._init_db()

    def _init_db(self):
        with self._lock:
            with self._conn:
                self._conn.execute(
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
                self._conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_runs_status ON runs(status)"
                )
                columns = {
                    row[1] for row in self._conn.execute("PRAGMA table_info(runs)")
                }
                if "workspace" not in columns:
                    self._conn.execute("ALTER TABLE runs ADD COLUMN workspace TEXT")

    def upsert(self, run: TaskRunRecord):
        with self._lock:
            with self._conn:
                self._conn.execute(
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
        with self._lock:
            row = self._conn.execute(
                "SELECT task_id, engine, pid, status, log_path, start_time, session_id, workspace FROM runs WHERE task_id = ?",
                (task_id,),
            ).fetchone()
        if row is None:
            return None
        return TaskRunRecord(*row)

    def list_running(self) -> list[TaskRunRecord]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT task_id, engine, pid, status, log_path, start_time, session_id, workspace FROM runs WHERE status = 'running'"
            ).fetchall()
        return [TaskRunRecord(*r) for r in rows]

    def update_status(
        self, task_id: str, status: str, session_id: Optional[str] = None
    ):
        with self._lock:
            with self._conn:
                self._conn.execute(
                    "UPDATE runs SET status = ?, session_id = COALESCE(?, session_id) WHERE task_id = ?",
                    (status, session_id, task_id),
                )

    def delete(self, task_id: str):
        with self._lock:
            with self._conn:
                self._conn.execute("DELETE FROM runs WHERE task_id = ?", (task_id,))

    def close(self) -> None:
        """Closes the persistent database connection and releases the lock.

        After this is called the store must not be used again.
        """
        with self._lock:
            self._conn.close()

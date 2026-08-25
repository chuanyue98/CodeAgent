from __future__ import annotations

import sqlite3
import threading
from dataclasses import dataclass
from pathlib import Path


@dataclass
class TaskRunRecord:
    task_id: str
    engine: str
    pid: int | None
    status: str
    log_path: str
    start_time: float
    session_id: str | None = None
    workspace: str | None = None
    end_time: float | None = None
    exit_code: int | None = None
    #: The blueprint this run came from. Derivable from ``task_id`` for task
    #: runs (``<name>_<ns>``) but not for chat turns, and a stored column is
    #: what lets history be queried per task without a LIKE scan.
    task_name: str | None = None
    #: Set when a schedule fired the run, so a schedule can report what
    #: actually happened rather than that it once launched something.
    schedule_id: str | None = None


#: Column order is the dataclass field order -- rows are unpacked positionally
#: into TaskRunRecord, so the two must not drift apart.
_COLUMNS = (
    "task_id",
    "engine",
    "pid",
    "status",
    "log_path",
    "start_time",
    "session_id",
    "workspace",
    "end_time",
    "exit_code",
    "task_name",
    "schedule_id",
)
_COLUMN_LIST = ", ".join(_COLUMNS)
_PLACEHOLDERS = ", ".join("?" for _ in _COLUMNS)


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
                if "end_time" not in columns:
                    self._conn.execute("ALTER TABLE runs ADD COLUMN end_time REAL")
                if "exit_code" not in columns:
                    self._conn.execute("ALTER TABLE runs ADD COLUMN exit_code INTEGER")
                if "task_name" not in columns:
                    self._conn.execute("ALTER TABLE runs ADD COLUMN task_name TEXT")
                if "schedule_id" not in columns:
                    self._conn.execute("ALTER TABLE runs ADD COLUMN schedule_id TEXT")
                # History is always read newest-first, and almost always
                # narrowed to one task or one schedule.
                self._conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_runs_task_name_start "
                    "ON runs(task_name, start_time DESC)"
                )
                self._conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_runs_schedule_start "
                    "ON runs(schedule_id, start_time DESC)"
                )
                self._backfill_task_names()

    def _backfill_task_names(self) -> None:
        """Derives ``task_name`` for rows written before the column existed.

        Without this the history of every run made before the migration is
        unreachable, because it is queried by task name. A task run's id is
        ``<name>_<time_ns>``; a chat turn's is ``chat_<engine>_<time_ns>`` and
        has no blueprint behind it, so those are left null.

        The caller already holds the lock and an open transaction.
        """
        rows = self._conn.execute(
            "SELECT task_id FROM runs WHERE task_name IS NULL"
        ).fetchall()
        for (task_id,) in rows:
            if not task_id or task_id.startswith("chat_"):
                continue
            name, _, suffix = task_id.rpartition("_")
            # Only the generated `<name>_<time_ns>` shape; anything else is
            # left alone rather than guessed at.
            if not name or not suffix.isdigit():
                continue
            self._conn.execute(
                "UPDATE runs SET task_name = ? WHERE task_id = ?", (name, task_id)
            )

    def upsert(self, run: TaskRunRecord):
        with self._lock:
            with self._conn:
                self._conn.execute(
                    f"""
                    INSERT INTO runs ({_COLUMN_LIST})
                    VALUES ({_PLACEHOLDERS})
                    ON CONFLICT(task_id) DO UPDATE SET
                        pid = excluded.pid,
                        status = excluded.status,
                        session_id = excluded.session_id,
                        workspace = excluded.workspace,
                        end_time = excluded.end_time,
                        exit_code = excluded.exit_code,
                        task_name = excluded.task_name,
                        schedule_id = excluded.schedule_id
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
                        run.end_time,
                        run.exit_code,
                        run.task_name,
                        run.schedule_id,
                    ),
                )

    def get(self, task_id: str) -> TaskRunRecord | None:
        with self._lock:
            row = self._conn.execute(
                f"SELECT {_COLUMN_LIST} FROM runs WHERE task_id = ?",
                (task_id,),
            ).fetchone()
        if row is None:
            return None
        return TaskRunRecord(*row)

    def list_running(self) -> list[TaskRunRecord]:
        with self._lock:
            rows = self._conn.execute(
                f"SELECT {_COLUMN_LIST} FROM runs WHERE status = 'running'"
            ).fetchall()
        return [TaskRunRecord(*r) for r in rows]

    def list_history(
        self,
        *,
        task_name: str | None = None,
        schedule_id: str | None = None,
        limit: int = 50,
    ) -> list[TaskRunRecord]:
        """Returns finished and running rows alike, newest first.

        Nothing read this table back before: rows were written on every status
        change and then only ever queried for ``status = 'running'``, so a
        completed run existed on disk but disappeared from the UI as soon as
        the process that produced it went away.
        """
        clauses: list[str] = []
        params: list[object] = []
        if task_name is not None:
            clauses.append("task_name = ?")
            params.append(task_name)
        if schedule_id is not None:
            clauses.append("schedule_id = ?")
            params.append(schedule_id)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(max(1, limit))

        with self._lock:
            rows = self._conn.execute(
                f"SELECT {_COLUMN_LIST} FROM runs {where} "
                "ORDER BY start_time DESC LIMIT ?",
                params,
            ).fetchall()
        return [TaskRunRecord(*r) for r in rows]

    def update_status(self, task_id: str, status: str, session_id: str | None = None):
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

    def clear(self) -> None:
        """Deletes every run row. Used to reset the isolated E2E backend."""
        with self._lock:
            with self._conn:
                self._conn.execute("DELETE FROM runs")

    def close(self) -> None:
        """Closes the persistent database connection and releases the lock.

        After this is called the store must not be used again.
        """
        with self._lock:
            self._conn.close()

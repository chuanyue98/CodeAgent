import pytest

from core.services.run_store import RunStore, TaskRunRecord


@pytest.fixture
def store(tmp_path):
    return RunStore(tmp_path / "runs.db")


def test_init_db_creates_parent_dirs_and_table(tmp_path):
    db_path = tmp_path / "nested" / "dir" / "runs.db"
    RunStore(db_path)

    assert db_path.parent.is_dir()
    # A second instantiation against the same path must not blow up
    # (CREATE TABLE IF NOT EXISTS / idempotent column migration).
    RunStore(db_path)


def test_upsert_then_get_round_trips_record(store):
    record = TaskRunRecord(
        task_id="task-1",
        engine="claude",
        pid=1234,
        status="running",
        log_path="/tmp/task-1.jsonl",
        start_time=1000.5,
        session_id="sess-1",
        workspace="/workspace",
    )

    store.upsert(record)
    fetched = store.get("task-1")

    assert fetched == record


def test_get_missing_task_returns_none(store):
    assert store.get("does-not-exist") is None


def test_upsert_conflict_updates_mutable_fields_only(store):
    original = TaskRunRecord(
        task_id="task-1",
        engine="claude",
        pid=1,
        status="running",
        log_path="/tmp/original.jsonl",
        start_time=1.0,
        session_id=None,
        workspace=None,
    )
    store.upsert(original)

    updated = TaskRunRecord(
        task_id="task-1",
        engine="claude",
        pid=2,
        status="completed",
        log_path="/tmp/should-not-change.jsonl",
        start_time=999.0,
        session_id="sess-new",
        workspace="/new-workspace",
    )
    store.upsert(updated)

    fetched = store.get("task-1")
    assert fetched is not None
    # pid/status/session_id/workspace are updated on conflict...
    assert fetched.pid == 2
    assert fetched.status == "completed"
    assert fetched.session_id == "sess-new"
    assert fetched.workspace == "/new-workspace"
    # ...but engine/log_path/start_time are excluded_from the UPDATE SET clause.
    assert fetched.engine == "claude"
    assert fetched.log_path == "/tmp/original.jsonl"
    assert fetched.start_time == 1.0


def test_list_running_returns_only_running_status(store):
    store.upsert(
        TaskRunRecord(
            task_id="running-1",
            engine="claude",
            pid=1,
            status="running",
            log_path="/tmp/a.jsonl",
            start_time=1.0,
        )
    )
    store.upsert(
        TaskRunRecord(
            task_id="completed-1",
            engine="codex",
            pid=2,
            status="completed",
            log_path="/tmp/b.jsonl",
            start_time=2.0,
        )
    )

    running = store.list_running()

    assert [r.task_id for r in running] == ["running-1"]


def test_list_running_empty_store_returns_empty_list(store):
    assert store.list_running() == []


def test_update_status_changes_status_and_preserves_session_id_when_none(store):
    store.upsert(
        TaskRunRecord(
            task_id="task-1",
            engine="claude",
            pid=1,
            status="running",
            log_path="/tmp/a.jsonl",
            start_time=1.0,
            session_id="original-session",
        )
    )

    store.update_status("task-1", "completed")

    fetched = store.get("task-1")
    assert fetched is not None
    assert fetched.status == "completed"
    assert fetched.session_id == "original-session"


def test_update_status_overwrites_session_id_when_provided(store):
    store.upsert(
        TaskRunRecord(
            task_id="task-1",
            engine="claude",
            pid=1,
            status="running",
            log_path="/tmp/a.jsonl",
            start_time=1.0,
            session_id="original-session",
        )
    )

    store.update_status("task-1", "completed", session_id="new-session")

    fetched = store.get("task-1")
    assert fetched is not None
    assert fetched.session_id == "new-session"


def test_update_status_on_missing_task_id_is_a_no_op(store):
    # No matching row: UPDATE affects zero rows, no exception raised.
    store.update_status("does-not-exist", "completed")
    assert store.get("does-not-exist") is None


def test_delete_removes_record(store):
    store.upsert(
        TaskRunRecord(
            task_id="task-1",
            engine="claude",
            pid=1,
            status="running",
            log_path="/tmp/a.jsonl",
            start_time=1.0,
        )
    )

    store.delete("task-1")

    assert store.get("task-1") is None


def test_delete_missing_task_id_is_a_no_op(store):
    store.delete("does-not-exist")


# ─── Reading history back ─────────────────────────────────────────────────
#
# Rows were written on every status change and then only ever queried for
# `status = 'running'`, so a completed run existed on disk but vanished from
# the UI as soon as the process that produced it went away.


def _run(task_id, *, task_name=None, status="completed", start_time=1000.0, **kw):
    return TaskRunRecord(
        task_id=task_id,
        engine="claude",
        pid=1,
        status=status,
        log_path=f"/tmp/{task_id}.log",
        start_time=start_time,
        task_name=task_name,
        **kw,
    )


def test_list_history_returns_finished_runs_newest_first(store):
    store.upsert(_run("review_1", task_name="review", start_time=100.0))
    store.upsert(_run("review_2", task_name="review", start_time=300.0))
    store.upsert(_run("review_3", task_name="review", start_time=200.0))

    history = store.list_history()

    assert [r.task_id for r in history] == ["review_2", "review_3", "review_1"]


def test_list_history_narrows_to_one_task(store):
    store.upsert(_run("review_1", task_name="review"))
    store.upsert(_run("deploy_1", task_name="deploy"))

    assert [r.task_id for r in store.list_history(task_name="review")] == ["review_1"]


def test_list_history_narrows_to_one_schedule(store):
    store.upsert(_run("review_1", task_name="review", schedule_id="sched-a"))
    store.upsert(_run("review_2", task_name="review", schedule_id="sched-b"))

    found = store.list_history(schedule_id="sched-a")

    assert [r.task_id for r in found] == ["review_1"]


def test_list_history_honours_the_limit(store):
    for i in range(5):
        store.upsert(_run(f"review_{i}", task_name="review", start_time=float(i)))

    assert len(store.list_history(limit=2)) == 2


def test_list_history_includes_running_rows(store):
    store.upsert(_run("review_1", task_name="review", status="running"))

    assert [r.status for r in store.list_history()] == ["running"]


def test_exit_code_and_end_time_survive_the_round_trip(store):
    store.upsert(_run("review_1", task_name="review", end_time=2000.0, exit_code=137))

    (found,) = store.list_history(task_name="review")

    # 137 is OOM-killed, and telling it apart from a plain rc=1 is the whole
    # reason the column exists.
    assert found.exit_code == 137
    assert found.end_time == 2000.0


def test_legacy_rows_get_a_task_name_on_migration(tmp_path):
    """Rows written before the column existed are keyed only by task_id.

    Without a backfill every run made before the migration is unreachable,
    because history is queried by task name.
    """
    import sqlite3

    db_path = tmp_path / "runs.db"
    con = sqlite3.connect(db_path)
    with con:
        con.execute(
            """
            CREATE TABLE runs (
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
        con.executemany(
            "INSERT INTO runs (task_id, engine, pid, status, log_path, start_time) "
            "VALUES (?, 'claude', 1, 'completed', '/tmp/x.log', 100.0)",
            [("nightly_review_1700000000123",), ("chat_claude_1700000000456",)],
        )
    con.close()

    store = RunStore(db_path)

    (found,) = store.list_history(task_name="nightly_review")
    assert found.task_id == "nightly_review_1700000000123"
    # A chat turn has no blueprint behind it, so it is left null rather than
    # being guessed at as a task called "chat_claude".
    chat = store.get("chat_claude_1700000000456")
    assert chat is not None and chat.task_name is None


def _record(task_id: str, **overrides) -> TaskRunRecord:
    fields = {
        "task_id": task_id,
        "engine": "claude",
        "pid": None,
        "status": "completed",
        "log_path": f"/logs/{task_id}.log",
        "start_time": 1000.0,
        "end_time": 1100.0,
    }
    fields.update(overrides)
    return TaskRunRecord(**fields)


def test_prune_drops_rows_that_ended_before_the_cutoff(store):
    store.upsert(_record("old", start_time=10.0, end_time=20.0))
    store.upsert(_record("recent", start_time=900.0, end_time=950.0))

    removed = store.prune(older_than=100.0, keep_latest=0)

    assert removed == ["/logs/old.log"]
    assert store.get("old") is None
    assert store.get("recent") is not None


def test_prune_never_touches_a_running_row(store):
    store.upsert(_record("alive", status="running", start_time=10.0, end_time=None))

    assert store.prune(older_than=100.0, keep_latest=0) == []
    assert store.get("alive") is not None


def test_prune_keeps_the_newest_runs_whatever_their_age(store):
    for index in range(5):
        store.upsert(_record(f"run-{index}", start_time=float(index), end_time=1.0))

    store.prune(older_than=1_000.0, keep_latest=2)

    assert [r.task_id for r in store.list_history()] == ["run-4", "run-3"]


def test_prune_judges_a_row_with_no_end_time_by_its_start(store):
    store.upsert(
        _record("never-finished", status="failed", start_time=10.0, end_time=None)
    )

    assert store.prune(older_than=100.0, keep_latest=0) == ["/logs/never-finished.log"]


def test_prune_reports_nothing_when_all_rows_are_recent(store):
    store.upsert(_record("recent", start_time=900.0, end_time=950.0))

    assert store.prune(older_than=100.0, keep_latest=0) == []


def test_log_paths_lists_what_the_table_still_points_at(store):
    store.upsert(_record("one"))
    store.upsert(_record("two"))

    assert sorted(store.log_paths()) == ["/logs/one.log", "/logs/two.log"]

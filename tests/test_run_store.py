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

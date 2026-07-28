from __future__ import annotations

from datetime import UTC

import pytest
from freezegun import freeze_time

from core.services.config_service import ConfigService
from core.services.schedule_service import ScheduleService


@pytest.fixture
def service(tmp_path):
    return ScheduleService(ConfigService(tmp_path / "config.json"))


def test_create_schedule_persists_and_computes_next_run(service):
    with freeze_time("2026-01-01 00:00:00"):
        record = service.create_schedule(
            "nightly-review", "claude", "common", "0 9 * * *"
        )

    assert record["task_name"] == "nightly-review"
    assert record["engine"] == "claude"
    assert record["enabled"] is True
    assert record["last_run_at"] is None
    assert record["last_run_status"] is None
    # Next 9am UTC after 2026-01-01 00:00 is the same day at 09:00.
    from datetime import datetime

    assert (
        datetime.fromtimestamp(record["next_run_at"], tz=UTC).isoformat()
        == "2026-01-01T09:00:00+00:00"
    )
    assert service.list_schedules() == [record]


def test_create_schedule_rejects_invalid_cron_expr(service):
    with pytest.raises(ValueError, match="Invalid cron expression"):
        service.create_schedule("task", "claude", "common", "not a cron")


def test_create_schedule_rejects_invalid_engine(service):
    with pytest.raises(ValueError, match="Invalid engine"):
        service.create_schedule("task", "shell", "common", "* * * * *")


def test_update_schedule_toggles_enabled(service):
    record = service.create_schedule("task", "claude", "common", "* * * * *")

    updated = service.update_schedule(record["id"], enabled=False)

    assert updated["enabled"] is False
    assert service.get_schedule(record["id"])["enabled"] is False


def test_update_schedule_recomputes_next_run_on_new_cron_expr(service):
    with freeze_time("2026-01-01 00:00:00"):
        record = service.create_schedule("task", "claude", "common", "0 9 * * *")
        original_next_run = record["next_run_at"]

        updated = service.update_schedule(record["id"], cron_expr="0 12 * * *")

    assert updated["cron_expr"] == "0 12 * * *"
    assert updated["next_run_at"] != original_next_run


def test_update_schedule_rejects_invalid_cron_expr(service):
    record = service.create_schedule("task", "claude", "common", "* * * * *")

    with pytest.raises(ValueError, match="Invalid cron expression"):
        service.update_schedule(record["id"], cron_expr="garbage")


def test_update_schedule_missing_id_raises_key_error(service):
    with pytest.raises(KeyError):
        service.update_schedule("does-not-exist", enabled=False)


def test_delete_schedule_removes_record(service):
    record = service.create_schedule("task", "claude", "common", "* * * * *")

    service.delete_schedule(record["id"])

    assert service.list_schedules() == []


def test_delete_schedule_missing_id_raises_key_error(service):
    with pytest.raises(KeyError):
        service.delete_schedule("does-not-exist")


def test_record_run_updates_status_and_advances_next_run(service):
    with freeze_time("2026-01-01 00:00:00"):
        record = service.create_schedule("task", "claude", "common", "0 9 * * *")
        original_next_run = record["next_run_at"]

    with freeze_time("2026-01-01 09:00:01"):
        service.record_run(record["id"], "started")

    updated = service.get_schedule(record["id"])
    assert updated["last_run_status"] == "started"
    assert updated["last_run_at"] is not None
    assert updated["next_run_at"] != original_next_run
    assert updated["next_run_at"] > original_next_run


def test_preview_next_runs_returns_requested_count(service):
    from datetime import datetime

    with freeze_time("2026-01-01 00:00:00"):
        runs = service.preview_next_runs("0 9 * * *", count=3)

    assert len(runs) == 3
    assert [datetime.fromtimestamp(r, tz=UTC).isoformat() for r in runs] == [
        "2026-01-01T09:00:00+00:00",
        "2026-01-02T09:00:00+00:00",
        "2026-01-03T09:00:00+00:00",
    ]


def test_preview_next_runs_rejects_invalid_cron_expr(service):
    with pytest.raises(ValueError, match="Invalid cron expression"):
        service.preview_next_runs("not a cron")

from __future__ import annotations

import time
import uuid
from typing import Any, Optional

from croniter import croniter

from core.services.config_service import ConfigService

_SCHEDULES_KEY = "schedules"
_VALID_ENGINES = {"claude", "gemini", "opencode", "codex"}


def _compute_next_run(cron_expr: str, base_time: Optional[float] = None) -> float:
    return croniter(
        cron_expr, base_time if base_time is not None else time.time()
    ).get_next(float)


class ScheduleService:
    """CRUD for cron-triggered task schedules, persisted in config.json.

    Reuses ConfigService's existing atomic-write, lock-guarded JSON store
    rather than a second persistence mechanism — schedules live under the
    ``schedules`` top-level key alongside ``project_registry``/``groups``.
    """

    def __init__(self, config_service: ConfigService):
        self.config_service = config_service

    def _load(self) -> dict:
        config, warnings = self.config_service.get_config()
        if warnings:
            raise ValueError(warnings[0])
        return config

    def list_schedules(self) -> list[dict]:
        return self._load().get(_SCHEDULES_KEY, [])

    def get_schedule(self, schedule_id: str) -> Optional[dict]:
        for record in self.list_schedules():
            if record["id"] == schedule_id:
                return record
        return None

    def _modify_schedules(self, modifier):
        """Atomically read, apply *modifier*(schedules), and write config."""

        def _wrapper(config):
            config[_SCHEDULES_KEY] = modifier(config.get(_SCHEDULES_KEY, []))
            return config

        self.config_service.modify_config(_wrapper)

    def create_schedule(
        self,
        task_name: str,
        engine: str,
        group: str,
        cron_expr: str,
        enabled: bool = True,
        workspace: str | None = None,
    ) -> dict:
        if engine not in _VALID_ENGINES:
            raise ValueError(f"Invalid engine: {engine!r}")
        if not croniter.is_valid(cron_expr):
            raise ValueError(f"Invalid cron expression: {cron_expr!r}")

        record = {
            "id": uuid.uuid4().hex,
            "task_name": task_name,
            "engine": engine,
            "group": group,
            "workspace": workspace,
            "cron_expr": cron_expr,
            "enabled": enabled,
            "created_at": time.time(),
            "last_run_at": None,
            "last_run_status": None,
            "next_run_at": _compute_next_run(cron_expr),
        }

        def _modifier(schedules):
            schedules.append(record)
            return schedules

        self._modify_schedules(_modifier)
        return record

    def update_schedule(self, schedule_id: str, **fields: Any) -> dict:
        if fields.get("engine") is not None and fields["engine"] not in _VALID_ENGINES:
            raise ValueError(f"Invalid engine: {fields['engine']!r}")
        new_cron_expr = fields.get("cron_expr")
        if new_cron_expr is not None and not croniter.is_valid(new_cron_expr):
            raise ValueError(f"Invalid cron expression: {new_cron_expr!r}")

        found: Optional[dict] = None

        def _modifier(schedules):
            nonlocal found
            for record in schedules:
                if record["id"] != schedule_id:
                    continue
                if new_cron_expr is not None:
                    record["next_run_at"] = _compute_next_run(new_cron_expr)
                elif fields.get("enabled") is True and not record.get("enabled"):
                    record["next_run_at"] = _compute_next_run(record["cron_expr"])
                for key in (
                    "cron_expr",
                    "enabled",
                    "task_name",
                    "engine",
                    "group",
                    "workspace",
                ):
                    if fields.get(key) is not None:
                        record[key] = fields[key]
                found = record
                break
            return schedules

        self._modify_schedules(_modifier)
        if found is None:
            raise KeyError(f"Schedule not found: {schedule_id}")
        return found

    def delete_schedule(self, schedule_id: str) -> None:
        removed = False

        def _modifier(schedules):
            nonlocal removed
            new_schedules = [r for r in schedules if r["id"] != schedule_id]
            removed = len(new_schedules) < len(schedules)
            return new_schedules

        self._modify_schedules(_modifier)
        if not removed:
            raise KeyError(f"Schedule not found: {schedule_id}")

    def record_run(
        self, schedule_id: str, status: str, advance_schedule: bool = True
    ) -> None:
        """Persists the outcome of a fired schedule (atomic RMW)."""

        def _modifier(schedules):
            for record in schedules:
                if record["id"] == schedule_id:
                    record["last_run_at"] = time.time()
                    record["last_run_status"] = status
                    if advance_schedule:
                        record["next_run_at"] = _compute_next_run(record["cron_expr"])
                    break
            return schedules

        self._modify_schedules(_modifier)

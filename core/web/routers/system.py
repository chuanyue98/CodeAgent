from __future__ import annotations

import asyncio
import time
from pathlib import Path

import psutil
from fastapi import APIRouter, HTTPException

from core.doctor import get_doctor_sections
from core.web.case_convert import ProtocolModel, wire

router = APIRouter(prefix="/api/system", tags=["system"])


class DoctorCheck(ProtocolModel):
    status: str
    label: str
    detail: str = ""
    fix_hint: str = ""


class DoctorSection(ProtocolModel):
    title: str
    checks: list[DoctorCheck]


class SystemHealth(ProtocolModel):
    status: str
    sections: list[DoctorSection]


class SystemMetrics(ProtocolModel):
    cpu_percent: float
    memory_percent: float
    memory_used_gb: float
    memory_total_gb: float
    disk_percent: float
    disk_used_gb: float
    disk_total_gb: float
    uptime_seconds: int
    history_file_size_mb: float
    log_file_count: int


def _sections(sections: list) -> list[DoctorSection]:
    return [
        DoctorSection(
            title=section.title,
            checks=[
                DoctorCheck(
                    status=check.status,
                    label=check.label,
                    detail=check.detail,
                    fix_hint=check.fix_hint,
                )
                for check in section.checks
            ],
        )
        for section in sections
    ]


@router.get("/health")
async def get_health():
    try:
        sections = await asyncio.to_thread(get_doctor_sections, fix=False)
        return wire(SystemHealth(status="ok", sections=_sections(sections)))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/metrics")
async def get_metrics():
    try:
        cpu = await asyncio.to_thread(psutil.cpu_percent, 0.1)
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage(str(Path.home().anchor))
        uptime = time.time() - psutil.boot_time()

        history_path = Path.home() / ".ca_analytics_history.jsonl"
        history_size = 0
        if history_path.exists():
            try:
                history_size = history_path.stat().st_size
            except OSError:
                pass

        logs_dir = Path(__file__).resolve().parent.parent.parent / ".ca_task_logs"
        log_count = 0
        if logs_dir.exists():
            log_count = len(list(logs_dir.glob("*.log")))

        return wire(
            SystemMetrics(
                cpu_percent=cpu,
                memory_percent=mem.percent,
                memory_used_gb=round(mem.used / 1e9, 2),
                memory_total_gb=round(mem.total / 1e9, 2),
                disk_percent=disk.percent,
                disk_used_gb=round(disk.used / 1e9, 2),
                disk_total_gb=round(disk.total / 1e9, 2),
                uptime_seconds=int(uptime),
                history_file_size_mb=round(history_size / 1e6, 2),
                log_file_count=log_count,
            )
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

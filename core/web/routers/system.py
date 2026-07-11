from __future__ import annotations

import time
from pathlib import Path

import psutil
from fastapi import APIRouter

from core.doctor import get_doctor_sections

router = APIRouter(prefix="/api/system", tags=["system"])


def _serialize_sections(sections) -> list[dict]:
    return [
        {
            "title": section.title,
            "checks": [
                {
                    "status": check.status,
                    "label": check.label,
                    "detail": check.detail,
                    "fix_hint": check.fix_hint,
                }
                for check in section.checks
            ],
        }
        for section in sections
    ]


@router.get("/health")
async def get_health():
    try:
        sections = get_doctor_sections(fix=False)
        return {"status": "ok", "sections": _serialize_sections(sections)}
    except Exception as e:
        return {"status": "error", "error": str(e)}


@router.get("/metrics")
async def get_metrics():
    try:
        cpu = psutil.cpu_percent(interval=0.1)
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage("/")
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

        return {
            "cpu_percent": cpu,
            "memory_percent": mem.percent,
            "memory_used_gb": round(mem.used / 1e9, 2),
            "memory_total_gb": round(mem.total / 1e9, 2),
            "disk_percent": disk.percent,
            "disk_used_gb": round(disk.used / 1e9, 2),
            "disk_total_gb": round(disk.total / 1e9, 2),
            "uptime_seconds": int(uptime),
            "history_file_size_mb": round(history_size / 1e6, 2),
            "log_file_count": log_count,
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}

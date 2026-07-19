from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from core.web.routers import system as system_router
from core.web.server import app


@pytest.mark.asyncio
async def test_health_returns_ok_with_doctor_sections(monkeypatch):
    fake_check = MagicMock(status="OK", label="Python", detail="3.13", fix_hint=None)
    fake_section = MagicMock(title="Runtime", checks=[fake_check])
    monkeypatch.setattr(
        system_router, "get_doctor_sections", lambda fix: [fake_section]
    )

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        response = await ac.get("/api/system/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["sections"][0]["title"] == "Runtime"
    assert body["sections"][0]["checks"][0]["label"] == "Python"


@pytest.mark.asyncio
async def test_health_returns_500_when_doctor_sections_raises(monkeypatch):
    def boom(fix):
        raise RuntimeError("doctor exploded")

    monkeypatch.setattr(system_router, "get_doctor_sections", boom)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        response = await ac.get("/api/system/health")

    assert response.status_code == 500
    assert "doctor exploded" in response.json()["detail"]


@pytest.mark.asyncio
async def test_metrics_returns_system_stats():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        response = await ac.get("/api/system/metrics")

    assert response.status_code == 200
    body = response.json()
    for key in (
        "cpu_percent",
        "memory_percent",
        "memory_used_gb",
        "memory_total_gb",
        "disk_percent",
        "disk_used_gb",
        "disk_total_gb",
        "uptime_seconds",
        "history_file_size_mb",
        "log_file_count",
    ):
        assert key in body


@pytest.mark.asyncio
async def test_metrics_returns_500_when_psutil_raises(monkeypatch):
    def boom(*_args, **_kwargs):
        raise OSError("psutil exploded")

    monkeypatch.setattr(system_router.psutil, "virtual_memory", boom)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        response = await ac.get("/api/system/metrics")

    assert response.status_code == 500
    assert "psutil exploded" in response.json()["detail"]

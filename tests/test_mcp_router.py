"""Tests for the /api/mcp endpoints, with mcp_service mocked out — no real
engine CLI or native config file is touched in CI."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from core.web.routers import mcp as mcp_router
from core.web.server import app


class _FakeMcpService:
    def __init__(self):
        self.added: list[dict] = []
        self.removed: list[dict] = []
        self._servers = [
            {
                "name": "srv1",
                "scope": "project",
                "transport": "stdio",
                "command": ["echo", "hi"],
                "url": None,
                "env": {},
            }
        ]
        self.raise_on_add: Exception | None = None
        self.raise_on_remove: Exception | None = None

    def list_servers(self, engine, project_path):
        if engine == "shell":
            raise ValueError("Invalid engine: 'shell'")
        return self._servers

    def add_server(
        self,
        engine,
        project_path,
        name,
        command=None,
        url=None,
        env=None,
        transport=None,
    ):
        if self.raise_on_add:
            raise self.raise_on_add
        self.added.append(
            {
                "engine": engine,
                "project_path": project_path,
                "name": name,
                "command": command,
                "url": url,
                "env": env,
                "transport": transport,
            }
        )

    def remove_server(self, engine, project_path, name):
        if self.raise_on_remove:
            raise self.raise_on_remove
        self.removed.append(
            {"engine": engine, "project_path": project_path, "name": name}
        )


@pytest.fixture
def fake_service(monkeypatch):
    fake = _FakeMcpService()
    monkeypatch.setattr(mcp_router, "mcp_service", fake)
    return fake


@pytest.mark.asyncio
async def test_list_mcp_servers(fake_service):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        response = await ac.get("/api/mcp/claude", params={"project": "/tmp/proj"})

    assert response.status_code == 200
    assert response.json() == fake_service._servers


@pytest.mark.asyncio
async def test_list_mcp_servers_invalid_engine_returns_400(fake_service):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        response = await ac.get("/api/mcp/shell", params={"project": "/tmp/proj"})

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_add_mcp_server(fake_service):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        response = await ac.post(
            "/api/mcp/claude",
            json={
                "project": "/tmp/proj",
                "name": "srv1",
                "command": ["echo", "hi"],
                "env": {"FOO": "bar"},
            },
        )

    assert response.status_code == 200
    assert fake_service.added == [
        {
            "engine": "claude",
            "project_path": "/tmp/proj",
            "name": "srv1",
            "command": ["echo", "hi"],
            "url": None,
            "env": {"FOO": "bar"},
            "transport": None,
        }
    ]


@pytest.mark.asyncio
async def test_add_mcp_server_cli_failure_returns_400(fake_service):
    fake_service.raise_on_add = RuntimeError("boom")
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        response = await ac.post(
            "/api/mcp/claude",
            json={"project": "/tmp/proj", "name": "srv1", "command": ["echo"]},
        )

    assert response.status_code == 400
    assert "boom" in response.json()["detail"]


@pytest.mark.asyncio
async def test_remove_mcp_server(fake_service):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        response = await ac.delete(
            "/api/mcp/claude/srv1", params={"project": "/tmp/proj"}
        )

    assert response.status_code == 200
    assert fake_service.removed == [
        {"engine": "claude", "project_path": "/tmp/proj", "name": "srv1"}
    ]


@pytest.mark.asyncio
async def test_remove_mcp_server_missing_returns_404(fake_service):
    fake_service.raise_on_remove = KeyError("MCP server not found: 'srv1'")
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        response = await ac.delete(
            "/api/mcp/claude/srv1", params={"project": "/tmp/proj"}
        )

    assert response.status_code == 404

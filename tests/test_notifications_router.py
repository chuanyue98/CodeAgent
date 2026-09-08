from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from core.services.run_store import RunStore
from core.web.server import app


@pytest.fixture
def run_store(tmp_path):
    store = RunStore(tmp_path / "test_notifications.db")
    app.state.run_store = store
    yield store
    store.close()
    app.state.run_store = None


@pytest.mark.asyncio
async def test_list_notifications(run_store: RunStore) -> None:
    run_store.add_notification(
        "s1", "t1", "hello", "claude", "completed", "hi", "ok"
    )
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        r = await ac.get("/api/notifications")
        assert r.status_code == 200
        items = r.json()
        assert len(items) == 1
        assert items[0]["title"] == "hi"
        assert items[0]["engine"] == "claude"


@pytest.mark.asyncio
async def test_unread_count(run_store: RunStore) -> None:
    run_store.add_notification(
        "s1", "t1", "hello", "claude", "completed", "hi", "ok"
    )
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        r = await ac.get("/api/notifications/unread-count")
        assert r.status_code == 200
        assert r.json()["count"] == 1


@pytest.mark.asyncio
async def test_mark_read(run_store: RunStore) -> None:
    run_store.add_notification(
        "s1", "t1", "hello", "claude", "completed", "hi", "ok"
    )
    nid = run_store.list_notifications(limit=10)[0]["id"]
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        r = await ac.post(f"/api/notifications/{nid}/read")
        assert r.status_code == 200
        assert run_store.count_unread() == 0


@pytest.mark.asyncio
async def test_mark_all_read(run_store: RunStore) -> None:
    run_store.add_notification(
        "s1", "t1", "h1", "claude", "completed", "hi", "ok"
    )
    run_store.add_notification(
        "s2", "t2", "h2", "codex", "failed", "h2", "err"
    )
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        r = await ac.post("/api/notifications/read-all")
        assert r.status_code == 200
        assert run_store.count_unread() == 0

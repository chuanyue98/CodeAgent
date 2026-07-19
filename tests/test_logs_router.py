from __future__ import annotations

import asyncio

import pytest
from httpx import ASGITransport, AsyncClient

from core.web.routers import logs as logs_router
from core.web.server import app


@pytest.fixture
def logs_dir(tmp_path, monkeypatch):
    directory = tmp_path / ".ca_task_logs"
    directory.mkdir()
    monkeypatch.setattr(logs_router, "CA_TASK_LOGS_DIR", directory)
    return directory


@pytest.mark.asyncio
async def test_list_log_files_returns_empty_when_dir_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(logs_router, "CA_TASK_LOGS_DIR", tmp_path / "nope")

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        response = await ac.get("/api/logs/files")

    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_list_log_files_reports_existing_logs(logs_dir):
    (logs_dir / "task-1.log").write_text("hello\n", encoding="utf-8")

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        response = await ac.get("/api/logs/files")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["task_id"] == "task-1"
    assert body[0]["name"] == "task-1.log"
    assert body[0]["size"] == len("hello\n")


@pytest.mark.asyncio
async def test_get_log_file_returns_content(logs_dir):
    (logs_dir / "task-1.log").write_text("line one\nline two\n", encoding="utf-8")

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        response = await ac.get("/api/logs/task-1")

    assert response.status_code == 200
    assert response.json() == {
        "task_id": "task-1",
        "content": "line one\nline two\n",
    }


@pytest.mark.asyncio
async def test_get_log_file_404s_for_missing_file(logs_dir):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        response = await ac.get("/api/logs/nonexistent")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_log_file_sanitizes_path_traversal(logs_dir):
    """task_id is attacker-controlled (comes straight off the URL path) —
    ../ segments must be stripped so a request can never escape
    CA_TASK_LOGS_DIR to read an arbitrary file on disk."""
    outside = logs_dir.parent / "secret.log"
    outside.write_text("top secret", encoding="utf-8")

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        response = await ac.get("/api/logs/..%2Fsecret")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_stream_log_file_404s_for_missing_file(logs_dir):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        response = await ac.get("/api/logs/nonexistent/stream")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_stream_log_file_emits_new_content_as_the_file_grows(logs_dir):
    """event_generator() is a lazy async generator — nothing in its body
    runs until the first anext(). Priming it with one in-flight anext()
    call before growing the file is what lets the *next* poll see a size
    change, matching how a real client tails a still-being-written log."""
    path = logs_dir / "task-1.log"
    path.write_text("first\n", encoding="utf-8")

    response = await logs_router.stream_log_file("task-1")
    body_iterator = response.body_iterator

    pending = asyncio.ensure_future(anext(body_iterator))
    await asyncio.sleep(0)  # let it capture last_size from "first\n" first
    with path.open("a", encoding="utf-8") as fh:
        fh.write("second\n")

    chunk = await asyncio.wait_for(pending, timeout=2)
    assert "second" in chunk

    await body_iterator.aclose()


@pytest.mark.asyncio
async def test_stream_log_file_emits_error_and_stops_when_file_is_removed(logs_dir):
    path = logs_dir / "task-1.log"
    path.write_text("first\n", encoding="utf-8")

    response = await logs_router.stream_log_file("task-1")
    body_iterator = response.body_iterator

    pending = asyncio.ensure_future(anext(body_iterator))
    await asyncio.sleep(0)  # let it capture last_size successfully first
    path.unlink()

    chunk = await asyncio.wait_for(pending, timeout=2)
    assert "file removed" in chunk
    with pytest.raises(StopAsyncIteration):
        await asyncio.wait_for(anext(body_iterator), timeout=2)

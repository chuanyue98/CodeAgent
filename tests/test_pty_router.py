from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from fastapi.websockets import WebSocketDisconnect

from core.web.routers import pty as pty_router

FAKE_ENGINE = Path(__file__).parent / "fixtures" / "fake_pty_engine.py"


def _app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> FastAPI:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps({"project_registry": [{"path": str(workspace), "group": "common"}]}),
        encoding="utf-8",
    )
    monkeypatch.setattr(pty_router, "get_config_path", lambda: config_path)
    monkeypatch.setattr(pty_router, "_CA_LAUNCHER", FAKE_ENGINE)

    app = FastAPI()
    app.include_router(pty_router.router)
    app.state.workspace = str(workspace)
    return app


def test_pty_status_reports_available_on_posix():
    app = FastAPI()
    app.include_router(pty_router.router)
    with TestClient(app) as client:
        response = client.get("/api/pty/status")
    assert response.status_code == 200
    body = response.json()
    if sys.platform == "win32":
        assert body["available"] is False
    else:
        assert body == {"available": True, "reason": None}


def test_pty_websocket_streams_output_and_accepts_input(tmp_path, monkeypatch):
    if sys.platform == "win32":
        pytest.skip("PTY sessions are POSIX-only")
    app = _app(tmp_path, monkeypatch)
    with TestClient(app) as client:
        with client.websocket_connect(
            "/api/pty/ws",
            params={"engine": "claude", "cwd": app.state.workspace},
        ) as ws:
            message = ws.receive_json()
            while "READY" not in message["data"]:
                message = ws.receive_json()

            ws.send_json({"type": "input", "data": "hello world\n"})
            message = ws.receive_json()
            while "ECHO:hello world" not in message["data"]:
                message = ws.receive_json()

            ws.send_json({"type": "resize", "cols": 120, "rows": 40})
            ws.send_json({"type": "input", "data": "exit\n"})


def test_pty_websocket_notifies_and_closes_when_process_exits_on_its_own(
    tmp_path, monkeypatch
):
    if sys.platform == "win32":
        pytest.skip("PTY sessions are POSIX-only")
    app = _app(tmp_path, monkeypatch)
    with TestClient(app) as client:
        with client.websocket_connect(
            "/api/pty/ws",
            params={"engine": "claude", "cwd": app.state.workspace},
        ) as ws:
            message = ws.receive_json()
            while "READY" not in message["data"]:
                message = ws.receive_json()

            # The fake engine exits on its own once it sees "exit" on stdin,
            # without the client ever closing the socket itself.
            ws.send_json({"type": "input", "data": "exit\n"})

            message = ws.receive_json()
            while message.get("type") != "exit":
                message = ws.receive_json()
            assert message["code"] == 0

            with pytest.raises(WebSocketDisconnect):
                ws.receive_json()


def test_pty_websocket_drains_buffered_output_before_exit_message(
    tmp_path, monkeypatch
):
    """A process that writes output and exits immediately must not have
    its trailing output truncated by a race between the process dying and
    pty.py still draining the PTY master's buffer. This locks in the
    correct end-to-end behavior (full output arrives before "exit"); the
    race itself depends on OS/event-loop scheduling timing this harness
    can't force deterministically, so this isn't a guaranteed repro of the
    old bug on every run/platform -- see the router's pump_exit comment
    for why waiting on the natural EOF drain (vs. tearing the reader down
    immediately on process exit) is the actual fix."""
    if sys.platform == "win32":
        pytest.skip("PTY sessions are POSIX-only")
    app = _app(tmp_path, monkeypatch)
    with TestClient(app) as client:
        with client.websocket_connect(
            "/api/pty/ws",
            params={"engine": "claude", "cwd": app.state.workspace},
        ) as ws:
            message = ws.receive_json()
            while "READY" not in message["data"]:
                message = ws.receive_json()

            ws.send_json({"type": "input", "data": "burst\n"})

            collected = ""
            message = ws.receive_json()
            while message.get("type") != "exit":
                collected += message["data"]
                message = ws.receive_json()
            assert message["code"] == 0

    assert "BURST_DONE" in collected
    assert collected.count("X") == 2_000


def test_pty_websocket_rejects_non_dict_client_messages(tmp_path, monkeypatch):
    """A client can send any valid JSON over the socket, not just an
    object -- a bare string/number/list must be ignored rather than crash
    the connection with AttributeError from message.get(...)."""
    if sys.platform == "win32":
        pytest.skip("PTY sessions are POSIX-only")
    app = _app(tmp_path, monkeypatch)
    with TestClient(app) as client:
        with client.websocket_connect(
            "/api/pty/ws",
            params={"engine": "claude", "cwd": app.state.workspace},
        ) as ws:
            message = ws.receive_json()
            while "READY" not in message["data"]:
                message = ws.receive_json()

            ws.send_json("just a string, not an object")
            ws.send_json([1, 2, 3])

            # The connection must still be alive and processing real
            # messages after the malformed ones.
            ws.send_json({"type": "input", "data": "still alive\n"})
            message = ws.receive_json()
            while "ECHO:still alive" not in message["data"]:
                message = ws.receive_json()

            ws.send_json({"type": "input", "data": "exit\n"})


def test_pty_websocket_terminates_process_on_abrupt_disconnect(tmp_path, monkeypatch):
    if sys.platform == "win32":
        pytest.skip("PTY sessions are POSIX-only")
    app = _app(tmp_path, monkeypatch)
    with TestClient(app) as client:
        with client.websocket_connect(
            "/api/pty/ws",
            params={"engine": "claude", "cwd": app.state.workspace},
        ) as ws:
            ws.receive_json()

    result = subprocess.run(
        ["pgrep", "-f", "fake_pty_engine.py"], capture_output=True, text=True
    )
    assert result.stdout.strip() == ""


def test_pty_websocket_closes_cleanly_when_spawn_fails(tmp_path, monkeypatch):
    """If create_subprocess_exec itself fails (e.g. EMFILE/ENOMEM), the PTY
    master fd opened just before it must still be closed rather than
    leaking for the life of the server process, and the client must get a
    clean close instead of a hung/aborted connection."""
    if sys.platform == "win32":
        pytest.skip("PTY sessions are POSIX-only")
    app = _app(tmp_path, monkeypatch)

    import pty as stdlib_pty

    opened_fds: list[int] = []
    real_openpty = stdlib_pty.openpty

    def _tracking_openpty():
        master_fd, slave_fd = real_openpty()
        opened_fds.append(master_fd)
        return master_fd, slave_fd

    async def _boom(*args, **kwargs):
        raise OSError("fork failed")

    # pty.py does `import pty` lazily inside the handler, which resolves to
    # this same cached sys.modules entry -- patching it here reaches that
    # local binding too.
    monkeypatch.setattr(stdlib_pty, "openpty", _tracking_openpty)
    monkeypatch.setattr(pty_router.asyncio, "create_subprocess_exec", _boom)

    with TestClient(app) as client:
        with pytest.raises(WebSocketDisconnect) as exc_info:
            with client.websocket_connect(
                "/api/pty/ws",
                params={"engine": "claude", "cwd": app.state.workspace},
            ) as ws:
                ws.receive_json()
    assert exc_info.value.code == 1011

    assert len(opened_fds) == 1
    with pytest.raises(OSError):
        os.close(opened_fds[0])


def test_pty_websocket_rejects_unknown_engine(tmp_path, monkeypatch):
    if sys.platform == "win32":
        pytest.skip("PTY sessions are POSIX-only")
    app = _app(tmp_path, monkeypatch)
    with TestClient(app) as client:
        with pytest.raises(WebSocketDisconnect) as exc_info:
            with client.websocket_connect(
                "/api/pty/ws",
                params={"engine": "not-a-real-engine", "cwd": app.state.workspace},
            ) as ws:
                ws.receive_json()
    assert exc_info.value.code == 4400


def test_pty_websocket_rejects_unregistered_workspace(tmp_path, monkeypatch):
    if sys.platform == "win32":
        pytest.skip("PTY sessions are POSIX-only")
    app = _app(tmp_path, monkeypatch)
    with TestClient(app) as client:
        with pytest.raises(WebSocketDisconnect) as exc_info:
            with client.websocket_connect(
                "/api/pty/ws",
                params={"engine": "claude", "cwd": str(tmp_path)},
            ) as ws:
                ws.receive_json()
    assert exc_info.value.code == 4400

"""Direct coverage of the Web UI's local-origin gates.

``tests/conftest.py`` relaxes these for every other test (see the
``web_security_test_env`` fixture and the reasons documented there); this
module re-enables them and asserts the real behaviour. The threat being
defended against is a page the user merely *visits* reaching this server:
WebSocket handshakes skip the same-origin policy entirely, and the PTY
route hands out an interactive shell, so a gap here is remote code
execution rather than an information leak.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI, WebSocket
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from core.web.security import (
    HostHeaderMiddleware,
    is_allowed_origin,
    is_loopback_hostname,
    require_token,
    reset_token_cache,
    verify_websocket,
)

TOKEN = "test-ui-token"


@pytest.fixture
def auth_on(monkeypatch):
    """Re-enables the gates that conftest's autouse fixture switches off."""
    monkeypatch.setenv("CA_UI_AUTH", "1")
    monkeypatch.setenv("CA_UI_TOKEN", TOKEN)
    monkeypatch.delenv("CA_UI_ALLOWED_HOSTS", raising=False)
    reset_token_cache()
    yield
    reset_token_cache()


def _app() -> FastAPI:
    from fastapi import Depends

    app = FastAPI()
    app.add_middleware(HostHeaderMiddleware)

    @app.get("/api/thing", dependencies=[Depends(require_token)])
    async def thing() -> dict:
        return {"ok": True}

    @app.websocket("/api/ws")
    async def ws(websocket: WebSocket) -> None:
        if not await verify_websocket(websocket):
            return
        await websocket.accept()
        await websocket.send_json({"ok": True})

    return app


def _client() -> TestClient:
    # Loopback base_url so the Host header is a legitimate one and each
    # test isolates the single gate it is actually exercising.
    return TestClient(_app(), base_url="http://127.0.0.1")


# ── Host header (DNS rebinding) ──────────────────────────────────────────


def test_non_loopback_host_is_rejected(auth_on):
    with TestClient(_app(), base_url="http://evil.test") as client:
        response = client.get("/api/thing", headers={"X-CA-Token": TOKEN})
    assert response.status_code == 421


def test_allowed_hosts_env_permits_a_real_hostname(auth_on, monkeypatch):
    monkeypatch.setenv("CA_UI_ALLOWED_HOSTS", "codeagent.internal")
    with TestClient(_app(), base_url="http://codeagent.internal") as client:
        response = client.get("/api/thing", headers={"X-CA-Token": TOKEN})
    assert response.status_code == 200


@pytest.mark.parametrize(
    "hostname,expected",
    [
        ("127.0.0.1", True),
        ("localhost", True),
        ("::1", True),
        ("[::1]", True),
        ("127.0.0.2", True),  # the whole 127/8 block is loopback
        ("evil.test", False),
        # Must not be resolved: resolution is exactly what rebinding
        # subverts, so a name that *points* at loopback is still untrusted.
        ("localtest.me", False),
    ],
)
def test_loopback_hostname_classification(hostname, expected):
    assert is_loopback_hostname(hostname) is expected


# ── Token ────────────────────────────────────────────────────────────────


def test_request_without_token_is_rejected(auth_on):
    with _client() as client:
        assert client.get("/api/thing").status_code == 401


def test_request_with_wrong_token_is_rejected(auth_on):
    with _client() as client:
        response = client.get("/api/thing", headers={"X-CA-Token": "nope"})
    assert response.status_code == 401


def test_token_accepted_via_header(auth_on):
    with _client() as client:
        response = client.get("/api/thing", headers={"X-CA-Token": TOKEN})
    assert response.status_code == 200


def test_token_accepted_via_query_param(auth_on):
    # EventSource and WebSocket cannot set headers, so this path must work.
    with _client() as client:
        response = client.get(f"/api/thing?ca_token={TOKEN}")
    assert response.status_code == 200


def test_auth_can_be_disabled_for_proxied_deployments(monkeypatch):
    monkeypatch.setenv("CA_UI_AUTH", "off")
    reset_token_cache()
    with _client() as client:
        assert client.get("/api/thing").status_code == 200


# ── Origin ───────────────────────────────────────────────────────────────


def test_cross_origin_request_is_rejected(auth_on):
    with _client() as client:
        response = client.get(
            "/api/thing",
            headers={"X-CA-Token": TOKEN, "Origin": "https://evil.test"},
        )
    assert response.status_code == 403


@pytest.mark.parametrize(
    "origin,expected",
    [
        ("http://127.0.0.1:8524", True),
        ("http://localhost:5173", True),  # the Vite dev server
        ("http://[::1]:8524", True),
        ("https://evil.test", False),
        ("null", False),  # sandboxed iframe / file:// document
        (None, True),  # non-browser client; the token still gates it
    ],
)
def test_origin_classification(origin, expected):
    assert is_allowed_origin(origin, "127.0.0.1:8524") is expected


# ── WebSocket ────────────────────────────────────────────────────────────


@pytest.fixture
def ws_auth_on(auth_on, monkeypatch):
    """``auth_on``, plus a Host allowance for a TestClient quirk.

    Starlette's TestClient hardcodes ``Host: testserver`` on WebSocket
    handshakes and ignores ``base_url`` there (it honours base_url for
    plain HTTP, which is why the Host tests above can use it). Without
    this the Host gate would fire first and mask the token/Origin gates
    these tests are actually about.
    """
    monkeypatch.setenv("CA_UI_ALLOWED_HOSTS", "testserver")
    reset_token_cache()


def test_websocket_without_token_is_closed_before_accept(ws_auth_on):
    with _client() as client, pytest.raises(WebSocketDisconnect) as excinfo:
        with client.websocket_connect("/api/ws"):
            pass
    assert excinfo.value.code == 4401


def test_websocket_from_foreign_origin_is_closed(ws_auth_on):
    """The drive-by attack: a random page opening a socket to this server.

    It can present neither a valid token nor a loopback Origin, and the
    browser will not let it forge either.
    """
    with _client() as client, pytest.raises(WebSocketDisconnect) as excinfo:
        with client.websocket_connect(
            f"/api/ws?ca_token={TOKEN}", headers={"Origin": "https://evil.test"}
        ):
            pass
    assert excinfo.value.code == 4403


def test_websocket_with_token_connects(ws_auth_on):
    with _client() as client:
        with client.websocket_connect(f"/api/ws?ca_token={TOKEN}") as socket:
            assert socket.receive_json() == {"ok": True}


def test_websocket_rejects_a_wrong_token(ws_auth_on):
    with _client() as client, pytest.raises(WebSocketDisconnect) as excinfo:
        with client.websocket_connect("/api/ws?ca_token=nope"):
            pass
    assert excinfo.value.code == 4401


# ── Router-level dependency on a WebSocket route ─────────────────────────
#
# The app in _app() registers its WS route directly, so it only exercises
# the inline verify_websocket() guard. The real server instead mounts
# whole routers with dependencies=[Depends(require_token)], and those DO
# run for WebSocket handshakes -- a require_token that asks for a
# `Request` blows up there with a TypeError -> 500 while every test above
# still passes. These two pin that path down.


def _router_app() -> FastAPI:
    from fastapi import APIRouter, Depends

    router = APIRouter(prefix="/api/guarded")

    @router.websocket("/ws")
    async def ws(websocket: WebSocket) -> None:
        await websocket.accept()
        await websocket.send_json({"ok": True})

    app = FastAPI()
    app.include_router(router, dependencies=[Depends(require_token)])
    return app


def test_router_dependency_authenticates_a_websocket(ws_auth_on):
    with TestClient(_router_app()) as client:
        with client.websocket_connect(f"/api/guarded/ws?ca_token={TOKEN}") as socket:
            assert socket.receive_json() == {"ok": True}


def test_router_dependency_rejects_an_unauthenticated_websocket(ws_auth_on):
    with (
        TestClient(_router_app()) as client,
        pytest.raises(WebSocketDisconnect) as excinfo,
    ):
        with client.websocket_connect("/api/guarded/ws"):
            pass
    # Not 500: the handshake must be refused, not crash the route.
    assert excinfo.value.code == 4401

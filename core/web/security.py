"""Local-origin authentication for the CodeAgent Web UI.

Binding to loopback is *not* a security boundary on its own, and the UI
hands out far more authority than a typical localhost dev server: an
authenticated caller can register a workspace and open a PTY running a
provider CLI with the user's own credentials. Three independent gaps make
"it only listens on 127.0.0.1" insufficient:

1. **The same-origin policy does not apply to WebSocket handshakes.** Any
   page the user happens to visit can ``new WebSocket("ws://127.0.0.1:
   8524/api/pty/ws?...")`` and, once connected, drive an interactive shell.
   No CORS preflight is involved, so the absence of CORS middleware does
   not help here.
2. **DNS rebinding** lets an attacker-controlled name resolve to 127.0.0.1
   after the page loads, so the browser treats requests to this server as
   same-origin against the attacker's document.
3. ``CA_UI_HOST`` can bind a non-loopback interface, putting everything on
   the LAN.

So three checks are applied, each of which is bypassable alone:

============  ==========================  =====================================
Check         Blocks                      Where
============  ==========================  =====================================
Host header   DNS rebinding               :class:`HostHeaderMiddleware` (all)
Origin        drive-by WebSocket/fetch    :func:`require_token` (HTTP API),
Token         everything else, incl.      :func:`verify_websocket` (WS) --
              non-browser clients         both apply Origin *and* token
============  ==========================  =====================================

The first two always run. The third follows the bind address (see
:func:`auth_enabled`): on loopback the Host and Origin checks are what
actually stop a hostile page, and the token's remaining band -- other
processes on this machine, which can read the token file anyway -- did not
justify carrying a secret into the browser on every launch. Bind anywhere
else and the token becomes mandatory, because Origin stops being a
boundary the moment non-browser clients can reach the port.

Static assets and ``/api/health`` stay unauthenticated on purpose: the
browser must be able to load ``index.html`` *before* it has a token (it
reads the token out of the URL the launcher opens), and ``/api/health`` is
the readiness probe used by the launcher and by the E2E harness.

Environment variables
---------------------
``CA_UI_TOKEN``
    Use this exact token instead of the generated one. Intended for test
    harnesses and for deployments that inject the secret themselves.
``CA_UI_AUTH``
    Forces *token* checking on (``1``) or off (``0``) instead of letting it
    follow the bind address -- see :func:`auth_enabled`. Turning it off has
    no effect on a non-loopback bind, where the token is the only remaining
    boundary. The Host and Origin checks always run either way.

``CA_UI_HOST``
    The bind address, read here (not just by the launcher) because the
    token requirement follows it.
``CA_UI_ALLOWED_HOSTS``
    Comma-separated extra Host header values to accept, for deployments
    reached under a real hostname. ``*`` accepts any Host, which disables
    the rebinding defence -- see :func:`is_allowed_host`.
"""

from __future__ import annotations

import ipaddress
import os
import secrets
import stat
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import HTTPException, Request, WebSocket, WebSocketException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import HTTPConnection
from starlette.responses import PlainTextResponse
from starlette.types import ASGIApp

from core.logging_config import get_logger

logger = get_logger(__name__)

TOKEN_HEADER = "X-CA-Token"
TOKEN_QUERY_PARAM = "ca_token"

#: WebSocket close code for a rejected handshake. 4401/4403 sit in the
#: application-defined range (4000-4999) so they survive the proxy layer
#: and are distinguishable from transport-level closes on the client.
WS_CLOSE_UNAUTHORIZED = 4401
WS_CLOSE_FORBIDDEN_ORIGIN = 4403

_LOOPBACK_HOSTNAMES = {"localhost", "127.0.0.1", "::1", "[::1]"}

_token_cache: str | None = None


def _token_path() -> Path:
    """Where the generated token lives. Shares ~/.codeagent with the agent DB."""
    return Path.home() / ".codeagent" / "ui-token"


def get_ui_token() -> str:
    """Returns this install's UI token, creating and persisting one if needed.

    ``CA_UI_TOKEN`` wins so a harness or container can pin the value. The
    generated file is created with owner-only permissions; on Windows the
    chmod is a no-op, which is why the containing directory is created
    under the user profile rather than anywhere world-readable.

    The result is cached per process: every authenticated request calls
    this, and re-reading the file each time would put a disk hit on the hot
    path for a value that cannot change without a restart.
    """
    global _token_cache
    if _token_cache is not None:
        return _token_cache

    override = os.environ.get("CA_UI_TOKEN")
    if override and override.strip():
        _token_cache = override.strip()
        return _token_cache

    path = _token_path()
    try:
        existing = path.read_text(encoding="utf-8").strip()
        if existing:
            _token_cache = existing
            return _token_cache
    except OSError:
        pass  # Missing or unreadable -- fall through and mint a new one.

    token = secrets.token_urlsafe(32)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(token, encoding="utf-8")
        path.chmod(stat.S_IRUSR | stat.S_IWUSR)
    except OSError as exc:
        # A read-only or otherwise unwritable home must not break startup:
        # the token still works for this process, it just won't survive a
        # restart (which only costs the user a re-opened browser tab).
        logger.warning(
            "Could not persist the UI token to %s (%s); using an in-memory "
            "token for this process only.",
            path,
            exc,
        )
    _token_cache = token
    return _token_cache


def reset_token_cache() -> None:
    """Clears the memoized token. For tests that swap HOME or CA_UI_TOKEN."""
    global _token_cache
    _token_cache = None


def bind_host() -> str:
    """The address the server was told to bind, defaulting to loopback."""
    return os.environ.get("CA_UI_HOST", "").strip() or "127.0.0.1"


def auth_enabled() -> bool:
    """Whether the token check runs.

    The requirement follows the bind address, because that is what decides
    who can reach the port at all:

    * **Loopback (the default).** Off. The Host and Origin checks already
      reject the browser attacks -- a drive-by page always sends an Origin
      the check refuses, and a rebound name always sends a Host it refuses.
      What the token adds on top is stopping *other processes on this
      machine*, and anything running as this user can simply read the token
      file, so on a single-user desktop that band is narrow. Paying for it
      with a secret that has to be carried into the browser on every launch
      is a bad trade: the token is delivered only by the URL ``ca ui``
      opens, so any other way of starting the server produced a UI that
      401'd with no way forward.

    * **Anything else.** On, and ``CA_UI_AUTH=0`` cannot turn it off. Once
      the port answers the network, Origin is no longer a boundary --
      non-browser clients simply omit the header, and the check has to let
      them through for the CLI and the health probe to work.

    An explicitly pinned ``CA_UI_TOKEN`` also turns it on: supplying a
    token is how a harness says it intends to authenticate.
    """
    override = os.environ.get("CA_UI_AUTH", "").strip().lower()
    exposed = not is_loopback_hostname(bind_host())

    if override in {"0", "off", "false", "no"}:
        return exposed
    if override in {"1", "on", "true", "yes"}:
        return True
    return exposed or bool(os.environ.get("CA_UI_TOKEN", "").strip())


def _hostname_of(value: str) -> str:
    """Extracts a bare hostname from a Host header or an Origin URL.

    Handles ``example.com:8524``, ``http://example.com:8524``, and the
    bracketed IPv6 forms (``[::1]:8524``) that a naive ``split(":")``
    would mangle into ``[``.
    """
    candidate = value.strip()
    if "://" in candidate:
        candidate = urlsplit(candidate).netloc
    if candidate.startswith("["):
        end = candidate.find("]")
        if end != -1:
            return candidate[: end + 1].lower()
    return (
        candidate.rsplit(":", 1)[0].lower() if ":" in candidate else candidate.lower()
    )


def is_loopback_hostname(hostname: str) -> bool:
    """True when *hostname* unambiguously refers to this machine.

    Name resolution is deliberately not performed: resolving is exactly the
    step DNS rebinding subverts, so only literal loopback addresses and the
    reserved name ``localhost`` are trusted.
    """
    normalized = hostname.strip().lower()
    if normalized in _LOOPBACK_HOSTNAMES:
        return True
    try:
        return ipaddress.ip_address(normalized.strip("[]")).is_loopback
    except ValueError:
        return False


def _extra_allowed_hosts() -> set[str]:
    raw = os.environ.get("CA_UI_ALLOWED_HOSTS", "")
    return {
        part.strip() if part.strip() == "*" else _hostname_of(part)
        for part in raw.split(",")
        if part.strip()
    }


def is_allowed_host(host_header: str | None) -> bool:
    """Whether *host_header* names this server.

    ``CA_UI_ALLOWED_HOSTS="*"`` accepts anything, which **switches off the
    DNS-rebinding defence**. That is only appropriate when a trusted proxy
    in front of this server already validates Host (the containerized
    deployment in docs/deployment.md), or in a test harness where the
    client's Host is a fixture artifact. The Origin and token checks are
    unaffected and still apply.
    """
    allowed = _extra_allowed_hosts()
    if "*" in allowed:
        return True
    if not host_header:
        # Pre-HTTP/1.1 clients only. Nothing legitimate reaches this server
        # without a Host header, so treat its absence as hostile.
        return False
    hostname = _hostname_of(host_header)
    return is_loopback_hostname(hostname) or hostname in allowed


def is_allowed_origin(origin: str | None, host_header: str | None) -> bool:
    """Validates a browser-supplied ``Origin`` against this server's identity.

    A missing Origin is allowed: non-browser clients (curl, the Python
    test client, a native app) legitimately omit it, and they still have to
    present a token. Browsers, which are the threat model here, *always*
    send Origin on cross-origin fetches and on every WebSocket handshake,
    and cannot be made to omit or forge it -- so a present-but-wrong Origin
    is the signal that matters.
    """
    if origin is None or not origin.strip():
        return True
    if origin.strip().lower() == "null":
        # Sandboxed iframes and `file://` documents. Never legitimate here.
        return False
    hostname = _hostname_of(origin)
    if is_loopback_hostname(hostname) or hostname in _extra_allowed_hosts():
        return True
    # Same-host access under a real hostname (reverse-proxy deployments).
    if host_header is None:
        return False
    return hostname == _hostname_of(host_header)


def _token_from_scope(request: HTTPConnection) -> str | None:
    """Reads the token from the header, falling back to the query string.

    The query fallback exists because two transports the UI already relies
    on cannot set request headers: ``EventSource`` (used by the log and
    chat streams) and ``WebSocket``. Query strings can land in logs, which
    is acceptable for a loopback-scoped, per-install secret but is the
    reason the header is preferred wherever it is available.
    """
    header = request.headers.get(TOKEN_HEADER)
    if header and header.strip():
        return header.strip()
    query = request.query_params.get(TOKEN_QUERY_PARAM)
    return query.strip() if query and query.strip() else None


def token_is_valid(candidate: str | None) -> bool:
    if not auth_enabled():
        return True
    if not candidate:
        return False
    return secrets.compare_digest(candidate, get_ui_token())


async def require_token(connection: HTTPConnection) -> None:
    """FastAPI dependency guarding every ``/api`` router.

    Mounted at the router level in ``core/web/server.py`` so that static
    assets, the SPA fallback, and ``/api/health`` stay reachable without a
    token -- see this module's docstring for why that is required rather
    than an oversight.

    Typed as :class:`HTTPConnection`, the common base of ``Request`` and
    ``WebSocket``, because router-level dependencies **do** also run for
    WebSocket routes. Declaring ``request: Request`` here instead makes
    every WebSocket handshake on a guarded router fail with a 500
    (``TypeError: missing 1 required positional argument``) rather than
    authenticate -- and that failure is invisible to any test that mounts
    the route without the router-level dependency.

    The exception type has to match the protocol too: a raised
    ``HTTPException`` means nothing to a client waiting on a handshake, so
    WebSocket scopes get a ``WebSocketException`` carrying the same close
    codes :func:`verify_websocket` uses.
    """
    is_websocket = connection.scope.get("type") == "websocket"

    def reject(status: int, ws_code: int, detail: str) -> None:
        if is_websocket:
            raise WebSocketException(code=ws_code, reason=detail)
        raise HTTPException(status_code=status, detail=detail)

    if not is_allowed_origin(
        connection.headers.get("origin"), connection.headers.get("host")
    ):
        reject(403, WS_CLOSE_FORBIDDEN_ORIGIN, "Origin not allowed")
    if not token_is_valid(_token_from_scope(connection)):
        reject(401, WS_CLOSE_UNAUTHORIZED, "Missing or invalid UI token")


class HostHeaderMiddleware(BaseHTTPMiddleware):
    """Rejects requests whose ``Host`` header is not this server's identity.

    This is the DNS-rebinding defence. An attacker page on
    ``http://evil.test`` whose DNS flips to 127.0.0.1 reaches this server
    with ``Host: evil.test``; the browser considers it same-origin (so
    neither CORS nor the Origin check fires), but the Host header still
    carries the attacker's name and is rejected here.

    Applied to *every* route including static assets and ``/api/health``,
    since rebinding does not care which path it targets.
    """

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next):
        if not is_allowed_host(request.headers.get("host")):
            return PlainTextResponse(
                "Host header is not allowed. Set CA_UI_ALLOWED_HOSTS if this "
                "server is reached under a real hostname.",
                status_code=421,  # Misdirected Request
            )
        return await call_next(request)


async def verify_websocket(websocket: WebSocket) -> bool:
    """Authenticates a WebSocket handshake, closing it on failure.

    Must be awaited *before* ``websocket.accept()``. Returns True when the
    caller should proceed; on False the socket has already been closed and
    the handler must return immediately.

    Starlette permits ``close()`` before ``accept()``, which rejects the
    handshake outright -- the browser sees a failed connection rather than
    an accepted socket that immediately hangs up, so a hijack attempt never
    gets a usable channel even momentarily.
    """
    host_header = websocket.headers.get("host")
    if not is_allowed_host(host_header):
        await websocket.close(code=WS_CLOSE_FORBIDDEN_ORIGIN, reason="Host not allowed")
        return False
    if not is_allowed_origin(websocket.headers.get("origin"), host_header):
        await websocket.close(
            code=WS_CLOSE_FORBIDDEN_ORIGIN, reason="Origin not allowed"
        )
        return False
    if not token_is_valid(_token_from_scope(websocket)):
        await websocket.close(
            code=WS_CLOSE_UNAUTHORIZED, reason="Missing or invalid UI token"
        )
        return False
    return True

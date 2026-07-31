import os
from pathlib import Path

import pytest

from core.web.security import reset_token_cache


@pytest.fixture(autouse=True)
def web_security_test_env(monkeypatch):
    """Relaxes the Web UI's local-origin gates for unit tests.

    Two adjustments, for different reasons:

    ``CA_UI_ALLOWED_HOSTS=*``
        Test clients send a synthetic Host (``testserver``, ``test``, and
        others depending on each file's ``base_url``), which the rebinding
        defence in :class:`~core.web.security.HostHeaderMiddleware`
        correctly rejects. That is a test-harness artifact, not a behaviour
        worth asserting in every router test.
    ``CA_UI_AUTH=off``
        Router tests build their own bare FastAPI app (no router-level
        ``Depends``), so the token gate only reaches them through the two
        WebSocket routes that check it inline. Disabling it keeps those
        tests about the transport they actually cover.

    The gates themselves are verified directly in ``test_web_security.py``,
    which re-enables both, and end-to-end by the Playwright suite, which
    runs against a server with auth fully on (see e2e/start-server.sh).
    """
    monkeypatch.setenv("CA_UI_ALLOWED_HOSTS", "*")
    monkeypatch.setenv("CA_UI_AUTH", "off")
    reset_token_cache()
    yield
    reset_token_cache()


@pytest.fixture
def fake_bin(tmp_path, monkeypatch):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")
    return bin_dir


@pytest.fixture
def home(tmp_path, monkeypatch):
    home_dir = tmp_path / "home"
    home_dir.mkdir()
    monkeypatch.setattr(Path, "home", lambda: home_dir)
    return home_dir

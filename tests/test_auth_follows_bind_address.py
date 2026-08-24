"""The token requirement follows the bind address.

Loopback is the default posture and does not ask for a token: the Host and
Origin checks are what actually reject a hostile page, and those run either
way. Bind anywhere the network can reach and the token becomes mandatory,
because a non-browser client simply omits Origin and the check has to let
that through for the CLI and the health probe to work.

The trade being locked in here is deliberate: on loopback the token's only
remaining band is other processes on this machine, and anything running as
this user can read the token file anyway.
"""

from __future__ import annotations

import pytest

from core.web.security import auth_enabled, bind_host, reset_token_cache


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """conftest pins CA_UI_AUTH=off globally; this module sets it itself."""
    for name in ("CA_UI_AUTH", "CA_UI_TOKEN", "CA_UI_HOST"):
        monkeypatch.delenv(name, raising=False)
    reset_token_cache()
    yield
    reset_token_cache()


# ── the default posture ──────────────────────────────────────────────────────
def test_bind_host_defaults_to_loopback():
    assert bind_host() == "127.0.0.1"


def test_loopback_does_not_require_a_token():
    assert auth_enabled() is False


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "::1", "127.0.0.5"])
def test_every_loopback_spelling_is_treated_the_same(monkeypatch, host):
    monkeypatch.setenv("CA_UI_HOST", host)
    assert auth_enabled() is False


def test_blank_ca_ui_host_is_loopback(monkeypatch):
    # An empty value is how a shell exports a variable it did not set.
    monkeypatch.setenv("CA_UI_HOST", "   ")
    assert bind_host() == "127.0.0.1"
    assert auth_enabled() is False


# ── exposure forces the check on ─────────────────────────────────────────────
@pytest.mark.parametrize("host", ["0.0.0.0", "192.168.1.10", "::"])
def test_non_loopback_requires_a_token(monkeypatch, host):
    monkeypatch.setenv("CA_UI_HOST", host)
    assert auth_enabled() is True


def test_ca_ui_auth_off_cannot_disable_the_check_when_exposed(monkeypatch):
    # The one setting that must not be honourable. Off the loopback the token
    # is the only boundary left, so "turn it off" is a request to serve an
    # unauthenticated shell to the network.
    monkeypatch.setenv("CA_UI_HOST", "0.0.0.0")
    monkeypatch.setenv("CA_UI_AUTH", "0")
    assert auth_enabled() is True


# ── explicit overrides ───────────────────────────────────────────────────────
def test_ca_ui_auth_on_forces_the_check_on_loopback(monkeypatch):
    monkeypatch.setenv("CA_UI_AUTH", "1")
    assert auth_enabled() is True


def test_a_pinned_token_turns_the_check_on(monkeypatch):
    # Supplying a token is how a harness says it intends to authenticate --
    # the E2E server does exactly this and sets no CA_UI_AUTH.
    monkeypatch.setenv("CA_UI_TOKEN", "codeagent-e2e-token")
    assert auth_enabled() is True


def test_ca_ui_auth_off_still_wins_over_a_pinned_token_on_loopback(monkeypatch):
    monkeypatch.setenv("CA_UI_TOKEN", "pinned")
    monkeypatch.setenv("CA_UI_AUTH", "off")
    assert auth_enabled() is False


def test_a_blank_pinned_token_does_not_turn_the_check_on(monkeypatch):
    # Otherwise `CA_UI_TOKEN=` in a .env file would silently arm a check
    # whose secret is the empty string.
    monkeypatch.setenv("CA_UI_TOKEN", "  ")
    assert auth_enabled() is False

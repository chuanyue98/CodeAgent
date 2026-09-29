"""概览页启动引擎时带的首条提示：暂存、取走、拼进启动参数。"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.engine_base.launch_args import split_passthrough
from core.web.routers import pty


@pytest.fixture(autouse=True)
def _clean_pending():
    pty._PENDING_PROMPTS.clear()
    yield
    pty._PENDING_PROMPTS.clear()


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.include_router(pty.router)
    return TestClient(app)


# ── _engine_argv ─────────────────────────────────────────────────────────────


def test_fresh_session_gets_the_prompt_as_the_launchers_first_message(tmp_path: Path):
    argv = pty._engine_argv("claude", tmp_path, None, "fix the login redirect")

    assert argv[-2] == "claude"
    assert argv[-1].strip() == "fix the login redirect"
    # 拼成的首条消息保持原样，不会被当成引擎参数
    assert split_passthrough([argv[-1]]) == ("fix the login redirect", [])


def test_no_prompt_leaves_the_launch_command_as_it_was(tmp_path: Path):
    plain = pty._engine_argv("claude", tmp_path, None)

    assert pty._engine_argv("claude", tmp_path, None, None) == plain
    assert pty._engine_argv("claude", tmp_path, None, "") == plain
    assert pty._engine_argv("claude", tmp_path, None, "   \n ") == plain
    assert len(plain) == 3  # python、启动器、引擎名


@pytest.mark.parametrize("prompt", ["-x", "--model", "resume", "exec", "fix"])
def test_a_one_word_prompt_is_still_a_message_not_an_engine_flag(
    tmp_path: Path, prompt: str
):
    argv = pty._engine_argv("codex", tmp_path, None, prompt)

    message, passthrough = split_passthrough([argv[-1]], {"resume", "exec", "review"})
    assert message == prompt
    assert passthrough == []


def test_a_multiline_prompt_survives_as_one_argument(tmp_path: Path):
    prompt = "step one\nstep two"
    argv = pty._engine_argv("claude", tmp_path, None, prompt)

    assert argv.count(argv[-1]) == 1
    assert split_passthrough([argv[-1]]) == (prompt, [])


def test_resuming_a_session_ignores_the_prompt(tmp_path: Path):
    argv = pty._engine_argv("claude", tmp_path, "abc-123", "should not appear")

    assert not any("should not appear" in part for part in argv)


def test_a_plain_shell_ignores_the_prompt(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(pty, "_shell_command", lambda: ["/bin/sh"])

    assert pty._engine_argv(pty.SHELL_ENGINE, tmp_path, None, "ls") == ["/bin/sh"]


# ── 暂存与取走 ────────────────────────────────────────────────────────────────


def test_a_staged_prompt_is_taken_once():
    pty._stage_prompt("tab1", "hello")

    assert pty._take_prompt("tab1") == "hello"
    assert pty._take_prompt("tab1") is None


def test_prompts_are_kept_per_tab():
    pty._stage_prompt("tab1", "one")
    pty._stage_prompt("tab2", "two")

    assert pty._take_prompt("tab2") == "two"
    assert pty._take_prompt("tab1") == "one"


def test_a_prompt_nobody_picked_up_expires():
    pty._stage_prompt("tab1", "hello", now=100.0)

    assert pty._take_prompt("tab1", now=100.0 + pty._PROMPT_TTL_SECONDS + 1) is None


def test_a_fresh_prompt_is_still_there_just_inside_the_ttl():
    pty._stage_prompt("tab1", "hello", now=100.0)

    assert pty._take_prompt("tab1", now=100.0 + pty._PROMPT_TTL_SECONDS - 1) == "hello"


def test_staging_sweeps_out_expired_entries():
    pty._stage_prompt("old", "stale", now=0.0)
    pty._stage_prompt("new", "fresh", now=pty._PROMPT_TTL_SECONDS + 10)

    assert "old" not in pty._PENDING_PROMPTS


def test_taking_without_a_tab_key_gives_nothing():
    pty._stage_prompt("tab1", "hello")

    assert pty._take_prompt(None) is None


# ── POST /api/pty/prompt ─────────────────────────────────────────────────────


def test_endpoint_stages_the_prompt(client: TestClient):
    response = client.post(
        "/api/pty/prompt", json={"tabKey": "tab1", "prompt": "fix the login redirect"}
    )

    assert response.status_code == 200
    assert response.json() == {"success": True}
    assert pty._take_prompt("tab1") == "fix the login redirect"


def test_endpoint_rejects_a_malformed_tab_key(client: TestClient):
    response = client.post(
        "/api/pty/prompt", json={"tabKey": "bad key!", "prompt": "hello"}
    )

    assert response.status_code == 400
    assert pty._PENDING_PROMPTS == {}


def test_endpoint_rejects_an_empty_prompt(client: TestClient):
    response = client.post("/api/pty/prompt", json={"tabKey": "tab1", "prompt": "  \n"})

    assert response.status_code == 400
    assert pty._PENDING_PROMPTS == {}


def test_endpoint_rejects_an_oversized_prompt(client: TestClient):
    response = client.post(
        "/api/pty/prompt",
        json={"tabKey": "tab1", "prompt": "x" * (pty._MAX_PROMPT_CHARS + 1)},
    )

    assert response.status_code == 400
    assert pty._PENDING_PROMPTS == {}


def test_endpoint_accepts_a_prompt_at_the_limit(client: TestClient):
    response = client.post(
        "/api/pty/prompt",
        json={"tabKey": "tab1", "prompt": "x" * pty._MAX_PROMPT_CHARS},
    )

    assert response.status_code == 200

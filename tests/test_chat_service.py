import json
import os
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from core.services.runner_service import TaskRunner
from tests._helpers import write_fake_chat_cli


class _FakeChatEngine:
    """Stands in for a real Engine subclass: only build_chat_command() and
    env_manager.get_env() are exercised by run_chat_turn(), so the fake
    only needs those two — mirroring how test_runner_service.py fakes the
    ca_launcher.py subprocess target rather than the whole launch pipeline.
    """

    def __init__(self, script_path: Path, session_field: str):
        self.env_manager = SimpleNamespace(get_env=lambda: os.environ.copy())
        self._script_path = script_path
        self._session_field = session_field

    def build_chat_command(self, message: str, session_id: str | None = None):
        cmd = [sys.executable, str(self._script_path), self._session_field, message]
        if session_id:
            cmd.append(session_id)
        return cmd


def _wait_for_completion(runner: TaskRunner, task_id: str, timeout: float = 5.0):
    deadline = time.time() + timeout
    status = None
    while time.time() < deadline:
        status = runner.get_status(task_id)
        if status and status.status != "running":
            return status
        time.sleep(0.01)
    return status


def test_run_chat_turn_writes_jsonl_log_and_extracts_session_id(tmp_path, monkeypatch):
    script = write_fake_chat_cli(tmp_path)
    fake_engine = _FakeChatEngine(script, "session_id")
    runner = TaskRunner(tmp_path)
    monkeypatch.setattr(runner, "_build_engine", lambda engine: fake_engine)

    run = runner.run_chat_turn("claude", "hello there", project_path=str(tmp_path))
    status = _wait_for_completion(runner, run.task_id)

    assert status is not None
    assert status.status == "completed"
    assert status.log_path.endswith(".jsonl")
    assert status.session_id == "new-session-123"

    payload = json.loads(Path(status.log_path).read_text(encoding="utf-8"))
    assert payload["echo"] == "hello there"


def test_run_chat_turn_resume_passes_session_id_through(tmp_path, monkeypatch):
    script = write_fake_chat_cli(tmp_path)
    fake_engine = _FakeChatEngine(script, "thread_id")
    runner = TaskRunner(tmp_path)
    monkeypatch.setattr(runner, "_build_engine", lambda engine: fake_engine)

    run = runner.run_chat_turn(
        "codex",
        "what did I say?",
        session_id="existing-thread-1",
        project_path=str(tmp_path),
    )
    status = _wait_for_completion(runner, run.task_id)

    assert status is not None
    assert status.status == "completed"
    # The fake CLI echoes back whatever session id it was resumed with.
    assert status.session_id == "existing-thread-1"


def test_run_chat_turn_rejects_unknown_engine(tmp_path):
    runner = TaskRunner(tmp_path)
    with pytest.raises(ValueError, match="Invalid engine"):
        runner.run_chat_turn("shell", "hello", project_path=str(tmp_path))


def test_run_chat_turn_rejects_empty_message(tmp_path):
    runner = TaskRunner(tmp_path)
    with pytest.raises(ValueError, match="message must not be empty"):
        runner.run_chat_turn("claude", "   ", project_path=str(tmp_path))


def test_run_chat_turn_requires_project_path(tmp_path):
    runner = TaskRunner(tmp_path)
    with pytest.raises(ValueError, match="project_path is required"):
        runner.run_chat_turn("claude", "hello")


def test_run_chat_turn_uses_resumed_session_project(tmp_path, monkeypatch):
    script = write_fake_chat_cli(tmp_path)
    fake_engine = _FakeChatEngine(script, "session_id")
    runner = TaskRunner(tmp_path)
    monkeypatch.setattr(runner, "_build_engine", lambda engine: fake_engine)

    project = tmp_path / "other-project"
    project.mkdir()
    run = runner.run_chat_turn("claude", "hello", project_path=str(project))
    status = _wait_for_completion(runner, run.task_id)

    assert status is not None
    assert status.status == "completed"
    payload = json.loads(Path(status.log_path).read_text(encoding="utf-8"))
    assert payload["cwd"] == str(project)


def test_run_chat_turn_rejects_missing_project(tmp_path, monkeypatch):
    script = write_fake_chat_cli(tmp_path)
    fake_engine = _FakeChatEngine(script, "session_id")
    runner = TaskRunner(tmp_path)
    monkeypatch.setattr(runner, "_build_engine", lambda engine: fake_engine)

    with pytest.raises(ValueError, match="Invalid project path"):
        runner.run_chat_turn(
            "claude", "hello", project_path=str(tmp_path / "missing-project")
        )


def test_extract_chat_session_id_uses_engine_specific_field(tmp_path):
    runner = TaskRunner(tmp_path)

    claude_log = tmp_path / "claude.jsonl"
    claude_log.write_text(
        '{"type": "system", "session_id": "abc-1"}\n', encoding="utf-8"
    )
    assert runner._extract_chat_session_id("claude", claude_log) == "abc-1"

    codex_log = tmp_path / "codex.jsonl"
    codex_log.write_text(
        '{"type": "thread.started", "thread_id": "thread-42"}\n', encoding="utf-8"
    )
    assert runner._extract_chat_session_id("codex", codex_log) == "thread-42"

    opencode_log = tmp_path / "opencode.jsonl"
    opencode_log.write_text('{"sessionID": "ses_xyz"}\n', encoding="utf-8")
    assert runner._extract_chat_session_id("opencode", opencode_log) == "ses_xyz"


def test_extract_chat_session_id_skips_malformed_lines(tmp_path):
    runner = TaskRunner(tmp_path)
    log = tmp_path / "mixed.jsonl"
    log.write_text(
        'not json at all\n{"type": "status"}\n{"session_id": "found-it"}\n',
        encoding="utf-8",
    )
    assert runner._extract_chat_session_id("claude", log) == "found-it"


def test_extract_chat_session_id_returns_none_when_absent(tmp_path):
    runner = TaskRunner(tmp_path)
    log = tmp_path / "empty.jsonl"
    log.write_text('{"type": "status"}\n', encoding="utf-8")
    assert runner._extract_chat_session_id("claude", log) is None


def test_legacy_chat_commands_use_restricted_defaults():
    from engines.start_claude_code import ClaudeEngine
    from engines.start_codex import CodexEngine
    from engines.start_opencode import OpenCodeEngine

    claude = ClaudeEngine().build_chat_command("hello")
    assert "--dangerously-skip-permissions" not in claude
    assert claude[claude.index("--permission-mode") + 1] == "dontAsk"

    codex = CodexEngine().build_chat_command("hello")
    assert "--dangerously-bypass-approvals-and-sandbox" not in codex
    assert codex[codex.index("--sandbox") + 1] == "workspace-write"

    opencode = OpenCodeEngine().build_chat_command("hello")
    assert "--auto" not in opencode

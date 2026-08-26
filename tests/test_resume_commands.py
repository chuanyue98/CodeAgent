"""Tests for the shared session-resume argv.

Both the history endpoints and the browser PTY build on this, and the session
id it embeds arrives from a URL, so the guard against an id that would read as
a CLI flag is the part that matters most here.
"""

from pathlib import Path

import pytest

from core.services.resume_commands import is_safe_session_id, resume_command

PROJECT = Path("/work/project-a")


@pytest.mark.parametrize(
    ("engine", "expected"),
    [
        ("claude", ["claude", "--resume", "sess-1"]),
        ("codex", ["codex", "resume", "sess-1"]),
        ("codebuddy", ["codebuddy", "--resume", "sess-1"]),
    ],
)
def test_each_engine_gets_its_own_spelling(engine, expected):
    assert resume_command(engine, "sess-1", PROJECT) == expected


def test_opencode_takes_the_project_as_an_argument():
    """Unlike the others, OpenCode names the directory rather than inheriting it."""
    assert resume_command("opencode", "sess-1", PROJECT) == [
        "opencode",
        str(PROJECT),
        "-s",
        "sess-1",
    ]


def test_unknown_engine_is_rejected():
    with pytest.raises(ValueError, match="Unknown engine"):
        resume_command("gemini", "sess-1", PROJECT)


@pytest.mark.parametrize(
    "session_id",
    [
        "--resume-all",
        "-r",
        "",
        "sess 1",
        "sess/../../etc",
        "sess;whoami",
        "sess|id",
    ],
)
def test_ids_that_could_be_read_as_flags_or_paths_are_rejected(session_id):
    assert not is_safe_session_id(session_id)
    with pytest.raises(ValueError, match="Unsafe session id"):
        resume_command("claude", session_id, PROJECT)


@pytest.mark.parametrize(
    "session_id",
    [
        "0199a1b2-c3d4-7e8f-9012-3456789abcde",  # claude / codex uuid
        "ses_8f2a1c4b9d",  # opencode
        "abc.123_XYZ-9",
    ],
)
def test_real_engine_ids_pass(session_id):
    assert is_safe_session_id(session_id)

"""A project deep enough to blow past Windows' MAX_PATH must still convert.

Claude and CodeBuddy name a session directory after the *whole* project path
with the separators replaced, so ``E:/a/b/c/...`` becomes one ~200-character
directory component. Past 260 characters the ordinary Windows API refuses the
path, and conversion used to die with a bare ``FileNotFoundError [WinError 3]``
naming a path that plainly existed.
"""

from __future__ import annotations

import sys

import pytest

from core.utils.atomic_write import atomic_write
from core.utils.long_paths import WINDOWS_MAX_PATH, list_files, long_path


def test_a_short_path_is_left_exactly_as_it_was(tmp_path):
    target = tmp_path / "a.txt"

    assert long_path(target) == str(target)


@pytest.mark.skipif(sys.platform != "win32", reason="MAX_PATH is a Windows limit")
def test_a_long_path_gets_the_extended_prefix(tmp_path):
    deep = tmp_path / ("d" * 120) / ("e" * 120) / "f.txt"

    assert long_path(deep).startswith("\\\\?\\")


@pytest.mark.skipif(sys.platform != "win32", reason="MAX_PATH is a Windows limit")
def test_an_already_prefixed_path_is_not_prefixed_twice(tmp_path):
    already = "\\\\?\\" + "C:\\" + "x" * 300

    from pathlib import Path

    assert long_path(Path(already)).count("\\\\?\\") == 1


@pytest.mark.skipif(sys.platform != "win32", reason="MAX_PATH is a Windows limit")
def test_writing_through_a_component_longer_than_max_path_succeeds(tmp_path):
    # The exact shape the converters produce: one enormous directory name.
    encoded = "E--" + "-".join(["segment"] * 30)
    assert len(encoded) > 200
    target = tmp_path / encoded / "session.jsonl"

    atomic_write(target, "line\n")

    # Read back through the same escape hatch: pathlib's ordinary open hits
    # the identical limit, which is exactly why the parsers need it too.
    with open(long_path(target), encoding="utf-8") as handle:
        assert handle.read() == "line\n"


def test_a_normal_write_still_round_trips(tmp_path):
    target = tmp_path / "nested" / "s.jsonl"

    atomic_write(target, "hello\n")

    assert target.read_text(encoding="utf-8") == "hello\n"


@pytest.mark.skipif(sys.platform != "win32", reason="MAX_PATH is a Windows limit")
def test_a_deep_project_converts_and_parses_back(tmp_path, monkeypatch):
    """The end the user actually sees: convert, then read the result back.

    Both halves have to cope -- fixing only the write leaves the session on
    disk and invisible, which is worse than failing loudly.
    """
    from pathlib import Path

    from core.session_history.models import EngineType, UnifiedMessage, UnifiedSession
    from core.session_history.parsers.claude_parser import parse_claude_session
    from core.session_history.writers.claude_writer import write_claude_session

    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(
        "core.session_history.writers.claude_writer._git_branch", lambda _p: "main"
    )
    deep_project = "E:/" + "/".join(["segment"] * 30)

    session_id = write_claude_session(
        UnifiedSession(
            session_id="orig",
            engine=EngineType.CLAUDE,
            project_path=deep_project,
            messages=[UnifiedMessage(role="user", content="hello")],
        )
    )

    # list_files, not Path.glob: glob cannot see into a directory past
    # MAX_PATH even when handed the prefixed spelling, which is exactly why
    # the session finders had to stop using it.
    found = list_files(tmp_path / ".claude" / "projects", ".jsonl", recursive=True)
    written = next(p for p in found if p.stem == session_id)
    assert len(str(written)) > WINDOWS_MAX_PATH

    parsed = parse_claude_session(written)
    assert parsed is not None
    assert parsed.messages[0].content == "hello"


def test_no_temporary_file_is_left_behind_on_failure(tmp_path, monkeypatch):
    target = tmp_path / "s.jsonl"
    monkeypatch.setattr(
        "core.utils.atomic_write.os.replace",
        lambda *_a, **_k: (_ for _ in ()).throw(OSError("boom")),
    )

    with pytest.raises(OSError):
        atomic_write(target, "x")

    assert list(tmp_path.iterdir()) == []

"""Tests for the per-file session parse cache.

The cache is what lets the analytics title map drop its 120 s TTL, so the two
properties that matter are: an unchanged file is not re-read, and a changed
one is.
"""

import json

import pytest

from core.session_history.parse_cache import (
    clear_parse_cache,
    parse_cache_size,
)
from core.session_history.parsers import claude_parser
from core.session_history.parsers.claude_parser import parse_claude_session


@pytest.fixture(autouse=True)
def _clean_cache():
    clear_parse_cache()
    yield
    clear_parse_cache()


def _write_session(path, session_id, text):
    """Writes a minimal Claude JSONL session file."""
    lines = [
        {
            "type": "user",
            "sessionId": session_id,
            "cwd": "E:/demo/test",
            "timestamp": "2026-07-11T10:00:00.000Z",
            "message": {"role": "user", "content": text},
        }
    ]
    path.write_text(
        "\n".join(json.dumps(line) for line in lines) + "\n", encoding="utf-8"
    )


def test_unchanged_file_is_not_reparsed(tmp_path, monkeypatch):
    target = tmp_path / "sess.jsonl"
    _write_session(target, "s-1", "hello")

    # The parser opens through the builtin rather than ``Path.read_text`` (it
    # needs ``long_path``), so count opens on the parser module itself -- a
    # module-level name shadows the builtin only inside that module, which
    # keeps pytest's own file access out of the count.
    opens = []
    real_open = open

    def counting_open(file, *args, **kwargs):
        opens.append(str(file))
        return real_open(file, *args, **kwargs)

    monkeypatch.setattr(claude_parser, "open", counting_open, raising=False)

    first = parse_claude_session(target)
    assert len(opens) == 1, "first parse should read the file exactly once"
    second = parse_claude_session(target)

    assert first is not None and second is not None
    assert first.session_id == second.session_id
    assert len(opens) == 1, "cache hit still re-read the file"


def test_changed_file_is_reparsed(tmp_path):
    target = tmp_path / "sess.jsonl"
    _write_session(target, "s-1", "hello")
    first = parse_claude_session(target)
    assert first is not None
    assert first.messages[0].content == "hello"

    # Different length as well as different content: the key is (mtime, size),
    # and a same-size rewrite inside one filesystem timestamp tick is exactly
    # the case a size-only key would miss.
    _write_session(target, "s-1", "hello again, at greater length")
    second = parse_claude_session(target)

    assert second is not None
    assert second.messages[0].content == "hello again, at greater length"


def test_caller_mutation_does_not_leak_into_cache(tmp_path):
    """``find_claude_sessions`` assigns ``project_path`` on what it gets back."""
    target = tmp_path / "sess.jsonl"
    _write_session(target, "s-1", "hello")

    first = parse_claude_session(target)
    assert first is not None
    original_path = first.project_path
    first.project_path = "E:/somewhere/else"
    first.messages.append(first.messages[0])

    second = parse_claude_session(target)
    assert second is not None
    assert second.project_path == original_path
    assert len(second.messages) == 1


def test_missing_file_is_not_cached(tmp_path):
    missing = tmp_path / "nope.jsonl"
    assert parse_claude_session(missing) is None
    assert parse_cache_size() == 0


def test_clear_parse_cache_empties_it(tmp_path):
    target = tmp_path / "sess.jsonl"
    _write_session(target, "s-1", "hello")
    parse_claude_session(target)
    assert parse_cache_size() == 1

    clear_parse_cache()
    assert parse_cache_size() == 0

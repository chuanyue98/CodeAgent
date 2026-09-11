"""Tests for the per-file session parse cache.

The cache is what lets the analytics title map drop its 120 s TTL, so the two
properties that matter are: an unchanged file is not re-read, and a changed
one is.
"""

import json
import pickle

import pytest

from core.session_history import parse_cache
from core.session_history.parse_cache import (
    ENV_DISABLE,
    ENV_PATH,
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
    # 落盘是全局开关：上一个用例打开的必须关掉，否则会把 tmp 路径带进后面
    # 的用例，或写到真实的缓存文件上。
    parse_cache.disable_persistence()
    parse_cache._parser_fingerprint_cache = None


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


def test_persistence_is_off_by_default(tmp_path, monkeypatch):
    """没显式打开时绝不能写磁盘。"""
    monkeypatch.delenv(ENV_DISABLE, raising=False)
    target = tmp_path / "sess.jsonl"
    _write_session(target, "s-1", "hello")
    parse_claude_session(target)
    assert parse_cache._persist_path is None


def test_enable_persistence_survives_restart(tmp_path, monkeypatch):
    """重启后应先从磁盘恢复，而不是重新解析。"""
    monkeypatch.delenv(ENV_DISABLE, raising=False)
    monkeypatch.delenv(ENV_PATH, raising=False)
    cache_file = tmp_path / "cache.pkl"
    target = tmp_path / "sess.jsonl"
    _write_session(target, "s-1", "hello")

    parse_cache.enable_persistence(cache_file)
    parse_claude_session(target)
    parse_cache.flush_parse_cache()
    assert cache_file.exists()

    # 模拟进程重启：内存清空、磁盘文件留着，重新 enable 应恢复条目。
    parse_cache._cache.clear()
    parse_cache.enable_persistence(cache_file)
    assert parse_cache_size() == 1


def test_clear_also_drops_the_disk_copy(tmp_path, monkeypatch):
    monkeypatch.delenv(ENV_DISABLE, raising=False)
    monkeypatch.delenv(ENV_PATH, raising=False)
    cache_file = tmp_path / "cache.pkl"
    target = tmp_path / "sess.jsonl"
    _write_session(target, "s-1", "hello")

    parse_cache.enable_persistence(cache_file)
    parse_claude_session(target)
    parse_cache.flush_parse_cache()
    assert cache_file.exists()

    clear_parse_cache()
    assert not cache_file.exists()


def test_parser_change_invalidates_disk_copy(tmp_path, monkeypatch):
    """改了解析器就必须重建，不能拿旧解析结果继续用。"""
    monkeypatch.delenv(ENV_DISABLE, raising=False)
    monkeypatch.delenv(ENV_PATH, raising=False)
    cache_file = tmp_path / "cache.pkl"
    target = tmp_path / "sess.jsonl"
    _write_session(target, "s-1", "hello")

    parse_cache.enable_persistence(cache_file)
    parse_claude_session(target)
    parse_cache.flush_parse_cache()

    # 模拟解析器源码变化：指纹变了，旧副本必须被忽略。
    parse_cache._parser_fingerprint_cache = "changed"
    parse_cache._cache.clear()
    parse_cache.enable_persistence(cache_file)
    assert parse_cache_size() == 0


def test_incompatible_schema_is_ignored(tmp_path, monkeypatch):
    """旧版本写的副本不能反序列化出来用。"""
    monkeypatch.delenv(ENV_DISABLE, raising=False)
    monkeypatch.delenv(ENV_PATH, raising=False)
    cache_file = tmp_path / "cache.pkl"
    cache_file.write_bytes(pickle.dumps({"schema": 9999, "entries": {"x": (1, None)}}))

    parse_cache.enable_persistence(cache_file)
    assert parse_cache_size() == 0

"""agy 摘要缓存 jetbox_summaries_proto.pb 的条目删除。"""

from __future__ import annotations

import os
import stat
from pathlib import Path

from core.session_history.antigravity_cache import (
    CACHE_NAME,
    remove_from_summaries_cache,
)


def _len(field: int, payload: bytes) -> bytes:
    return bytes([(field << 3) | 2, len(payload)]) + payload


def _entry(session_id: str, summary: bytes = b"\x10\x07") -> bytes:
    return _len(1, _len(1, session_id.encode()) + _len(2, summary))


def _cache(tmp_path: Path, *entries: bytes) -> Path:
    path = tmp_path / CACHE_NAME
    path.write_bytes(b"".join(entries))
    os.chmod(path, 0o600)
    return path


def test_removes_only_the_matching_entry_byte_for_byte(tmp_path):
    keep_a, drop, keep_b = _entry("a"), _entry("gone"), _entry("b", b"\x10\x09")
    path = _cache(tmp_path, keep_a, drop, keep_b)

    assert remove_from_summaries_cache(tmp_path, "gone") is True
    assert path.read_bytes() == keep_a + keep_b
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_unknown_id_or_missing_file_changes_nothing(tmp_path):
    assert remove_from_summaries_cache(tmp_path, "x") is False
    original = _entry("a")
    path = _cache(tmp_path, original)
    assert remove_from_summaries_cache(tmp_path, "x") is False
    assert path.read_bytes() == original


def test_unrecognised_layout_is_left_untouched(tmp_path):
    """结构和实测的对不上（比如 agy 升级改了格式）时一个字节都不改。"""
    odd = _entry("a") + _len(3, b"something else")
    path = _cache(tmp_path, odd)
    assert remove_from_summaries_cache(tmp_path, "a") is False
    assert path.read_bytes() == odd

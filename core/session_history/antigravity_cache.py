"""Antigravity 的会话摘要缓存 ``jetbox_summaries_proto.pb``。

agy 除了 ``conversation_summaries.db`` 还在这里存一份摘要，并会据此把 sqlite
里被删掉的行重新生成出来——只删 sqlite 的话，删掉的会话会回到 agy 自己的会话
列表里。

格式（实测）：顶层是重复的字段 1，每条是一个 map 条目，其字段 1 为会话 id、
字段 2 为摘要。删一个会话就是去掉对应的那条顶层记录，其余字节原样保留；结构对
不上时不动文件。
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from core.logging_config import get_logger

logger = get_logger(__name__)

CACHE_NAME = "jetbox_summaries_proto.pb"

_WIRE_VARINT = 0
_WIRE_LEN = 2


def _varint(data: bytes, pos: int) -> tuple[int, int]:
    value = shift = 0
    while True:
        if pos >= len(data):
            raise ValueError("truncated varint")
        byte = data[pos]
        pos += 1
        value |= (byte & 0x7F) << shift
        shift += 7
        if byte < 0x80:
            return value, pos
        if shift > 63:
            raise ValueError("varint too long")


def _len_field(data: bytes, pos: int) -> tuple[int, bytes, int]:
    """读一个 length-delimited 字段：(字段号, 内容, 结束位置)。"""
    key, pos = _varint(data, pos)
    if key & 7 != _WIRE_LEN:
        raise ValueError(f"unexpected wire type {key & 7}")
    size, pos = _varint(data, pos)
    end = pos + size
    if end > len(data):
        raise ValueError("truncated field")
    return key >> 3, data[pos:end], end


def _entries(data: bytes) -> list[tuple[str, bytes]]:
    """(会话 id, 该条记录的原始字节)。结构不符时抛 ValueError。"""
    entries: list[tuple[str, bytes]] = []
    pos = 0
    while pos < len(data):
        start = pos
        field, entry, pos = _len_field(data, pos)
        if field != 1:
            raise ValueError(f"unexpected top-level field {field}")
        key_field, key, _ = _len_field(entry, 0) if entry else (1, b"", 0)
        if key_field != 1:
            raise ValueError("map entry does not start with its key")
        entries.append((key.decode("utf-8"), data[start:pos]))
    return entries


def remove_from_summaries_cache(cli_root: Path, session_id: str) -> bool:
    """从缓存里删掉 *session_id* 那一条，返回是否真的删了。"""
    path = cli_root / CACHE_NAME
    try:
        data = path.read_bytes()
    except FileNotFoundError:
        return False
    try:
        entries = _entries(data)
    except (ValueError, UnicodeDecodeError) as exc:
        logger.warning("Unrecognised %s, left untouched: %s", CACHE_NAME, exc)
        return False

    kept = [raw for key, raw in entries if key != session_id]
    if len(kept) == len(entries):
        return False

    fd, tmp = tempfile.mkstemp(dir=cli_root, prefix=f".{CACHE_NAME}.")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(b"".join(kept))
        os.chmod(tmp, path.stat().st_mode & 0o777)
        os.replace(tmp, path)
    except OSError:
        Path(tmp).unlink(missing_ok=True)
        raise
    return True

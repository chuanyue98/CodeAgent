"""Memoizes per-session parsing across calls.

Every consumer of :func:`find_all_sessions` re-reads the entire engine
history. On a working machine that is ~900 MB of JSONL and ~2.2 s per call,
and the analytics title map paid it every 120 s just to rebuild a
``session id -> title`` table.

Session data is append-only, so an entry whose version token is unchanged
parses to the same result. The token is the file's ``(mtime, size)`` for the
file-backed engines and the per-session ``time_updated`` for OpenCode, which
keeps every session in one SQLite database -- either way a session that grew
re-parses on the next call instead of going stale.

The parsers keep text summaries rather than the raw JSON, so retaining every
parsed session costs ~175 MB against the ~900 MB it was read from.

That memoization is per-process, so every server restart paid the whole scan
again -- seconds before the first page could render. :func:`enable_persistence`
additionally mirrors the cache onto disk, keyed by the same version tokens, so
a restart stats the files and reuses the stored parses instead of re-reading
them (~0.1 s to load against ~2.8 s to re-parse). It is off by default: tests
and one-shot CLI commands must not read or write the user's cache file.
"""

from __future__ import annotations

import atexit
import copy
import hashlib
import os
import pickle
import threading
from collections.abc import Callable
from pathlib import Path

from core.logging_config import get_logger
from core.session_history.models import UnifiedSession
from core.utils.long_paths import long_path

logger = get_logger(__name__)

#: Entries to retain before the oldest are dropped. Comfortably above the
#: session count of a busy machine; the bound exists so a long-lived server
#: cannot grow without limit, not to ration a scarce resource.
_MAX_ENTRIES = 8192

#: 落盘格式的版本：UnifiedSession / UnifiedMessage 的字段一旦变化，旧缓存
#: 就不能再反序列化（会缺字段），直接丢弃重建。
_PERSIST_SCHEMA_VERSION = 1

#: 解析器源码所在目录，用于源码指纹。
_PARSER_DIR = Path(__file__).resolve().parent / "parsers"
_parser_fingerprint_cache: str | None = None

#: 落盘防抖。快照是 28 MB，一次活跃会话里同一个文件会被反复重解析，所以这里
#: 宁可迟钝：安静 30 s 才写一次。启动预热会显式 flush 一次、进程退出还有
#: atexit 兜底，真正可能丢的只是"最后一次写盘之后又开始活动"的那几秒。
_SAVE_DEBOUNCE_SECONDS = 30.0

#: 关掉落盘的开关，以及替换存储位置的开关。
ENV_DISABLE = "CA_SESSION_CACHE"
ENV_PATH = "CA_SESSION_CACHE_PATH"

_lock = threading.Lock()
#: cache key -> (version token, parsed session or None). The token is
#: whatever the caller uses to tell "unchanged" from "changed": ``(mtime_ns,
#: size)`` for the file-backed engines, OpenCode's per-session
#: ``time_updated`` for the one that keeps everything in a single database.
_cache: dict[str, tuple[object, UnifiedSession | None]] = {}

# 持久化状态。_persist_path 为 None 表示关闭。
_persist_lock = threading.Lock()
_persist_path: Path | None = None
_dirty = False
_save_timer: threading.Timer | None = None
_atexit_registered = False

#: Every engine's file-backed parser has this shape.
FileParser = Callable[[Path], UnifiedSession | None]


def _stat_key(file_path: Path) -> tuple[int, int] | None:
    """Returns ``(mtime_ns, size)`` for *file_path*, or None if unreadable.

    ``long_path`` keeps this working for the deep per-project directories
    Claude Code and CodeBuddy name after the whole project path.
    """
    try:
        stat = os.stat(long_path(file_path))
    except OSError:
        return None
    return (stat.st_mtime_ns, stat.st_size)


def _detach(session: UnifiedSession | None) -> UnifiedSession | None:
    """Returns a copy safe for the caller to mutate.

    Callers do write to what a parser hands back -- ``find_claude_sessions``
    and ``find_codebuddy_sessions`` assign ``project_path``, and the agent
    gateway assigns ``model`` -- which would otherwise edit the cached object
    and leak into the next caller. The message list is copied too, so a future
    in-place append cannot corrupt the entry; the messages themselves are only
    ever read.
    """
    if session is None:
        return None
    detached = copy.copy(session)
    detached.messages = list(session.messages)
    return detached


def cached_parse(
    cache_key: str,
    version: object,
    parse: Callable[[], UnifiedSession | None],
) -> UnifiedSession | None:
    """Memoizes one session's parse under a caller-supplied version token.

    *version* must change whenever the underlying session does, and compare
    equal whenever it has not.
    """
    with _lock:
        entry = _cache.get(cache_key)
        if entry is not None and entry[0] == version:
            return _detach(entry[1])

    # Parsed outside the lock: parsing is the slow part, and two threads
    # racing on the same session cost a duplicate parse, not a wrong answer.
    session = parse()

    _store(cache_key, version, session)
    # 有新条目才需要回写；命中缓存时上面已经 return，不会走到这里。
    _schedule_save()
    return _detach(session)


def _store(cache_key: str, version: object, session: UnifiedSession | None) -> None:
    """Writes one entry and keeps the cache within its bound."""
    with _lock:
        _cache[cache_key] = (version, session)
        while len(_cache) > _MAX_ENTRIES:
            _cache.pop(next(iter(_cache)))


def cached_file_parser(parse: FileParser) -> FileParser:
    """Wraps a ``parse_*_session(file_path)`` parser with the stat-keyed cache.

    A file that cannot be stat'ed is parsed uncached, so the wrapper never
    turns a readable file into a missing one.
    """

    def wrapper(file_path: Path) -> UnifiedSession | None:
        key = _stat_key(file_path)
        if key is None:
            return parse(file_path)
        return cached_parse(str(file_path), key, lambda: parse(file_path))

    wrapper.__name__ = parse.__name__
    wrapper.__doc__ = parse.__doc__
    wrapper.__wrapped__ = parse  # type: ignore[attr-defined]
    return wrapper


def clear_parse_cache() -> None:
    """Drops every entry. Used by the analytics ``/refresh`` endpoint and tests.

    持久化开启时连磁盘副本一并删除：refresh 的语义是"从头再来"，留着旧副本
    会让下一次重启又把刚丢掉的结果加载回来。
    """
    global _dirty
    with _lock:
        _cache.clear()
    with _persist_lock:
        _dirty = False
        _cancel_timer_locked()
        path = _persist_path
    if path is not None:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            logger.debug(
                "Failed to remove session parse cache at %s", path, exc_info=True
            )


def parse_cache_size() -> int:
    """Number of retained entries, for tests and diagnostics."""
    with _lock:
        return len(_cache)


# ---------------------------------------------------------------------------
# 可选落盘
# ---------------------------------------------------------------------------


def default_persist_path() -> Path:
    """磁盘副本的默认位置，与 agent-gateway.sqlite3 同目录。"""
    return Path.home() / ".codeagent" / "session-parse-cache.pkl"


def enable_persistence(path: Path | None = None) -> None:
    """打开落盘并从磁盘恢复上次的解析结果。

    只在长驻服务里调用；默认关闭是为了让测试和一次性命令绝不触碰用户真实
    的缓存文件。``CA_SESSION_CACHE=0`` 可显式关掉，``CA_SESSION_CACHE_PATH``
    可换存储位置（测试或排查用）。
    """
    global _persist_path, _atexit_registered
    if os.environ.get(ENV_DISABLE, "").strip().lower() in {"0", "false", "no", "off"}:
        return
    override = os.environ.get(ENV_PATH)
    with _persist_lock:
        _persist_path = Path(override) if override else (path or default_persist_path())
    _load_persisted()
    if not _atexit_registered:
        atexit.register(flush_parse_cache)
        _atexit_registered = True


def disable_persistence() -> None:
    """先落盘再关闭落盘。"""
    global _persist_path
    flush_parse_cache()
    with _persist_lock:
        _persist_path = None


def flush_parse_cache() -> None:
    """立即把当前内容写入磁盘（若有改动）。供预热结束和进程退出调用。"""
    global _dirty
    with _persist_lock:
        _cancel_timer_locked()
        if _persist_path is None or not _dirty:
            return
        _dirty = False
    _save_persisted()


def _cancel_timer_locked() -> None:
    """调用方须持有 _persist_lock。"""
    global _save_timer
    if _save_timer is not None:
        _save_timer.cancel()
        _save_timer = None


def _schedule_save() -> None:
    """标记有改动，并推迟一次合并写入。"""
    global _dirty, _save_timer
    with _persist_lock:
        if _persist_path is None:
            return
        _dirty = True
        _cancel_timer_locked()
        timer = threading.Timer(_SAVE_DEBOUNCE_SECONDS, flush_parse_cache)
        timer.daemon = True
        _save_timer = timer
        timer.start()


def _parser_fingerprint() -> str:
    """解析器源码的指纹。

    内存缓存随进程消失，改解析器代码重启就自然重来；磁盘副本会跨重启，若不
    作废就会出现"修了解析 bug、重启却看不到变化"。用源码内容而不是 mtime，
    这样换台机器 checkout 也不会平白触发一次全量重解析。
    """
    global _parser_fingerprint_cache
    if _parser_fingerprint_cache is None:
        digest = hashlib.sha1()
        for source in sorted(_PARSER_DIR.glob("*.py")):
            try:
                digest.update(source.read_bytes())
            except OSError:
                continue
        _parser_fingerprint_cache = digest.hexdigest()[:16]
    return _parser_fingerprint_cache


def _load_persisted() -> None:
    """把磁盘副本并回内存缓存；版本不符或文件损坏时安静地当作没有。"""
    with _persist_lock:
        path = _persist_path
    if path is None or not path.exists():
        return
    try:
        with open(path, "rb") as f:
            doc = pickle.load(f)
    except Exception:
        # 副本可能被旧版本写过、写到一半或根本不是本模块的文件。它不是真相
        # 来源，读不出来就重建，不能因此让服务起不来。
        logger.debug(
            "Ignoring unreadable session parse cache at %s", path, exc_info=True
        )
        return
    if not isinstance(doc, dict) or doc.get("schema") != _PERSIST_SCHEMA_VERSION:
        return
    if doc.get("parsers") != _parser_fingerprint():
        return
    entries = doc.get("entries")
    if not isinstance(entries, dict):
        return
    # setdefault：启动后若已有并发解析写入，以内存中的为准。
    restored = 0
    with _lock:
        for key, entry in entries.items():
            if key not in _cache:
                _cache[key] = entry
                restored += 1
        while len(_cache) > _MAX_ENTRIES:
            _cache.pop(next(iter(_cache)))
    logger.info("Restored %d session parses from %s", restored, path)


def _save_persisted() -> None:
    """原子地把缓存快照写到磁盘。"""
    with _persist_lock:
        path = _persist_path
    if path is None:
        return
    with _lock:
        snapshot = dict(_cache)
    doc = {
        "schema": _PERSIST_SCHEMA_VERSION,
        "parsers": _parser_fingerprint(),
        "entries": snapshot,
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_name(path.name + ".tmp")
        with open(tmp_path, "wb") as f:
            pickle.dump(doc, f, protocol=pickle.HIGHEST_PROTOCOL)
        os.replace(tmp_path, path)
    except OSError:
        logger.debug("Failed to persist session parse cache to %s", path, exc_info=True)

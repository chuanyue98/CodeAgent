"""Memoizes per-file session parsing across calls.

Every consumer of :func:`find_all_sessions` re-reads the entire engine
history. On a working machine that is ~900 MB of JSONL and ~2.2 s per call,
and the analytics title map paid it every 120 s just to rebuild a
``session id -> title`` table.

Session files are append-only, so a file whose ``(mtime, size)`` is unchanged
parses to the same result. Retaining the parsed objects is cheap: the parsers
keep text summaries rather than the raw JSON, so the whole history occupies
~22 MB in memory against the ~900 MB it was read from.

The key is the file's stat rather than its path alone, so a session that was
appended to re-parses on the next call instead of going stale.
"""

from __future__ import annotations

import copy
import os
import threading
from collections.abc import Callable
from pathlib import Path

from core.session_history.models import UnifiedSession
from core.utils.long_paths import long_path

#: Entries to retain before the oldest are dropped. Comfortably above the
#: session count of a busy machine; the bound exists so a long-lived server
#: cannot grow without limit, not to ration a scarce resource.
_MAX_ENTRIES = 8192

_lock = threading.Lock()
#: path -> ((mtime_ns, size), parsed session or None)
_cache: dict[str, tuple[tuple[int, int], UnifiedSession | None]] = {}

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


def cached_file_parser(parse: FileParser) -> FileParser:
    """Wraps a ``parse_*_session(file_path)`` parser with the stat-keyed cache.

    A file that cannot be stat'ed is parsed uncached, so the wrapper never
    turns a readable file into a missing one.
    """

    def wrapper(file_path: Path) -> UnifiedSession | None:
        key = _stat_key(file_path)
        if key is None:
            return parse(file_path)

        path_text = str(file_path)
        with _lock:
            entry = _cache.get(path_text)
            if entry is not None and entry[0] == key:
                return _detach(entry[1])

        # Parsed outside the lock: parsing is the slow part, and two threads
        # racing on the same file cost a duplicate parse, not a wrong answer.
        session = parse(file_path)

        with _lock:
            _cache[path_text] = (key, session)
            while len(_cache) > _MAX_ENTRIES:
                _cache.pop(next(iter(_cache)))
        return _detach(session)

    wrapper.__name__ = parse.__name__
    wrapper.__doc__ = parse.__doc__
    wrapper.__wrapped__ = parse  # type: ignore[attr-defined]
    return wrapper


def clear_parse_cache() -> None:
    """Drops every entry. Used by the analytics ``/refresh`` endpoint and tests."""
    with _lock:
        _cache.clear()


def parse_cache_size() -> int:
    """Number of retained entries, for tests and diagnostics."""
    with _lock:
        return len(_cache)

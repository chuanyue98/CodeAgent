from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from core.analytics import history as _history
from core.analytics.pricing import pricing_fingerprint
from core.logging_config import get_logger

logger = get_logger(__name__)

# Bumped when the cached aggregate's shape changes. Also part of the
# invalidation key below, so an upgrade drops the previous cache instead of
# serving it with fields the current code no longer writes.
CACHE_SCHEMA_VERSION = 6

#: 缓存的最长存活时间。它不只是"怕陈旧"：归档文件只会被采集本身写入，所以只
#: 按输入失效的话，第一次采集之后输入永远不会再变，新用量就再也进不来了。
#: 有了它，陈旧数据由后台刷新兜住（见 service.get_analytics_data），请求路径
#: 不必为这 ~4s 的采集买单。
CACHE_MAX_AGE_SECONDS = 600  # 10 minutes


def _default_cache_path() -> Path:
    """Returns the default path for the analytics cache file.

    Returns:
        Path: The default path (~/.ca_analytics_cache.json).
    """
    return Path.home() / ".ca_analytics_cache.json"


def _source_key() -> str:
    """Fingerprint of everything the cached aggregate is derived from.

    This used to be a 5-minute TTL, so a restart after any idle spell re-ran
    the whole collection (~3.3 s) even when nothing had changed. Keying on the
    inputs instead keeps the cache valid for exactly as long as they are: the
    archive's ``(mtime, size)`` moves whenever a collector appends, and the
    pricing fingerprint moves when a rate is edited.
    """
    parts = [f"schema={CACHE_SCHEMA_VERSION}", f"pricing={pricing_fingerprint()}"]
    try:
        stat = os.stat(_history._history_path())
    except OSError:
        parts.append("history=absent")
    else:
        parts.append(f"history={stat.st_mtime_ns}:{stat.st_size}")
    return "|".join(parts)


def load_cache(path: Path | None = None, *, allow_stale: bool = False) -> Any | None:
    """Loads cached analytics data from a JSON file.

    Two independent reasons to reject a cache:

    *the inputs moved*
        ``source_key`` no longer matches, so the cached aggregate was derived
        from something that has since changed.
    *it is too old*
        older than :data:`CACHE_MAX_AGE_SECONDS`. This one is load-bearing: the
        archive is only ever written *by* a collection, so an input-key-only
        check can never fire again after the first run -- new usage would never
        be collected and the dashboard would freeze.

    ``allow_stale`` tolerates the second reason only, so a caller can serve the
    old numbers while a refresh runs in the background.

    Args:
        path: Optional specific path to load from. Defaults to ~/.ca_analytics_cache.json.
        allow_stale: Accept a cache whose only problem is its age.

    Returns:
        The cached data if usable, otherwise None.
    """
    p = path or _default_cache_path()
    if not p.exists():
        return None
    try:
        with open(p, encoding="utf-8") as f:
            doc = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None

    if doc.get("version") != CACHE_SCHEMA_VERSION:
        return None

    if doc.get("source_key") != _source_key():
        return None

    if not allow_stale:
        age = time.time() - doc.get("saved_at", 0)
        if age > CACHE_MAX_AGE_SECONDS:
            return None
    return doc.get("data")


def save_cache(data: Any, path: Path | None = None) -> None:
    """Saves analytics data to a JSON file.

    Args:
        data: The data to cache.
        path: Optional specific path to save to. Defaults to ~/.ca_analytics_cache.json.
    """
    p = path or _default_cache_path()
    doc = {
        "version": CACHE_SCHEMA_VERSION,
        "saved_at": time.time(),
        "source_key": _source_key(),
        "data": data,
    }
    try:
        with open(p, "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False)
    except OSError:
        logger.debug("Failed to write analytics cache to %s", p, exc_info=True)


def invalidate_cache(path: Path | None = None) -> None:
    """Deletes the analytics cache file.

    Args:
        path: Optional specific path to invalidate. Defaults to ~/.ca_analytics_cache.json.
    """
    p = path or _default_cache_path()
    if p.exists():
        try:
            p.unlink()
        except OSError:
            logger.debug("Failed to remove analytics cache at %s", p, exc_info=True)

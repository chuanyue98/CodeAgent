from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

CACHE_SCHEMA_VERSION = 3
CACHE_TTL_SECONDS = 300  # 5 minutes


def _default_cache_path() -> Path:
    """Returns the default path for the analytics cache file.

    Returns:
        Path: The default path (~/.ca_analytics_cache.json).
    """
    return Path.home() / ".ca_analytics_cache.json"


def load_cache(path: Path | None = None) -> Optional[Any]:
    """Loads cached analytics data from a JSON file.

    Returns cached data if it exists, has a compatible schema version, and is
    within TTL. Returns None if the cache is missing, corrupt, incompatible, or expired.

    Args:
        path: Optional specific path to load from. Defaults to ~/.ca_analytics_cache.json.

    Returns:
        The cached data if valid and fresh, otherwise None.
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

    age = time.time() - doc.get("saved_at", 0)
    if age > CACHE_TTL_SECONDS:
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

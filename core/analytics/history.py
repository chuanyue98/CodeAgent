from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Dict, List

from core.analytics.models import RawUsageEntry


def _history_path() -> Path:
    return Path.home() / ".ca_analytics_history.jsonl"


def load_history() -> List[RawUsageEntry]:
    """Loads all historical usage entries from the local JSONL file."""
    path = _history_path()
    if not path.exists():
        return []

    entries: List[RawUsageEntry] = []
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    entries.append(RawUsageEntry(**data))
                except (json.JSONDecodeError, TypeError):
                    continue
    except OSError:
        pass
    return entries


def append_history(new_entries: List[RawUsageEntry]) -> None:
    """Appends new usage entries to the local JSONL history file."""
    if not new_entries:
        return
    path = _history_path()
    try:
        with open(path, "a", encoding="utf-8") as f:
            for e in new_entries:
                f.write(json.dumps(asdict(e), ensure_ascii=False) + "\n")
    except OSError:
        pass


def get_last_timestamps() -> Dict[str, str]:
    """Returns the latest timestamp seen for each engine target."""
    last_ts: Dict[str, str] = {}
    path = _history_path()
    if not path.exists():
        return last_ts

    try:
        # We could optimize this by reading from the end, but for now a full scan is okay
        # since we need to distinguish by target.
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    target = data.get("target", "unknown")
                    ts = data.get("timestamp", "")
                    if ts and ts > last_ts.get(target, ""):
                        last_ts[target] = ts
                except (json.JSONDecodeError, KeyError):
                    continue
    except OSError:
        pass
    return last_ts

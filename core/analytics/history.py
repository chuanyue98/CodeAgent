from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict
from pathlib import Path

from core.analytics.models import RawUsageEntry


def _history_path() -> Path:
    return Path.home() / ".ca_analytics_history.jsonl"


def load_history() -> list[RawUsageEntry]:
    """Loads all historical usage entries from the local JSONL file."""
    path = _history_path()
    if not path.exists():
        return []

    entries: list[RawUsageEntry] = []
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


def append_history(new_entries: list[RawUsageEntry]) -> None:
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


def save_history(entries: list[RawUsageEntry]) -> None:
    """Atomically replaces the history file with the supplied entries."""
    path = _history_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        text=True,
    )
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            for entry in entries:
                f.write(json.dumps(asdict(entry), ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp_path, path)
    except OSError:
        temp_path.unlink(missing_ok=True)


def get_last_timestamps() -> dict[str, str]:
    """Returns the latest timestamp seen for each engine target."""
    last_ts: dict[str, str] = {}
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

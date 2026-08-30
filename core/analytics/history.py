from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict
from pathlib import Path

from core.analytics.models import RawUsageEntry


def _history_path() -> Path:
    return Path.home() / ".ca_analytics_history.jsonl"


def _state_path() -> Path:
    """Sits beside the archive it describes.

    Derived from :func:`_history_path` rather than from ``Path.home()`` so that
    redirecting the archive -- what every test does -- redirects the marker
    with it, instead of recording a backfill against the developer's real one.
    """
    return _history_path().with_name(".ca_analytics_state.json")


def _entry_key(entry: RawUsageEntry) -> tuple:
    """Identity of one usage record, for merging a rescan into the archive."""
    return (
        entry.target,
        entry.session_id,
        entry.timestamp,
        entry.model,
        entry.input_tokens,
        entry.output_tokens,
        entry.cache_creation_tokens,
        entry.cache_read_tokens,
    )


def merge_history(
    existing: list[RawUsageEntry], rescanned: list[RawUsageEntry]
) -> list[RawUsageEntry]:
    """Folds a rescan into the archive, letting the rescan win on collisions.

    Additive on purpose: engines prune their own transcripts, so the archive
    holds sessions no rescan can reproduce. Rescanned records take precedence
    for the fields outside the identity key -- that is how a session already on
    file learns which parent spawned it.
    """
    merged = {_entry_key(entry): entry for entry in existing}
    merged.update({_entry_key(entry): entry for entry in rescanned})
    return list(merged.values())


def backfill_pending(version: int) -> bool:
    """True until :func:`mark_backfill_done` records *version* or newer."""
    try:
        with open(_state_path(), encoding="utf-8") as f:
            state = json.load(f)
    except (OSError, json.JSONDecodeError):
        return True
    recorded = state.get("backfill_version", 0)
    return not isinstance(recorded, int) or recorded < version


def mark_backfill_done(version: int) -> None:
    """Records that the archive has been rebuilt up to *version*."""
    try:
        with open(_state_path(), "w", encoding="utf-8") as f:
            json.dump({"backfill_version": version}, f)
    except OSError:
        pass


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

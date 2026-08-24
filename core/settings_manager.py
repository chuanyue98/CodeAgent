from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any

from core.logging_config import get_logger
from core.utils.atomic_write import atomic_write

logger = get_logger(__name__)


class SettingsFile:
    """Reads and writes a settings file with atomic backup.

    Defaults to JSON, but switches to TOML for ``.toml`` paths — codex keeps
    its hook configuration in ``config.toml`` rather than a JSON settings
    file, and writing JSON there produced a file codex never read.
    """

    def __init__(self, path: Path):
        self.path = path
        self.is_toml = path.suffix.lower() == ".toml"

    def load(self) -> Any:
        if not self.path.exists():
            return {}
        try:
            text = self.path.read_text(encoding="utf-8")
        except Exception:
            return {}
        try:
            if self.is_toml:
                import tomlkit

                return tomlkit.parse(text)
            return json.loads(text)
        except Exception:
            return {}

    def save(self, data: Any):
        if self.is_toml:
            import tomlkit

            atomic_write(self.path, tomlkit.dumps(data))
            return
        atomic_write(self.path, json.dumps(data, indent=2, ensure_ascii=False))

    def is_injected(self) -> bool:
        """True if this file is one CodeAgent wrote, not the user's own."""
        data = self.load()
        return isinstance(data, dict) and data.get("_ca_injected") is True

    def create_backup(self) -> Path | None:
        backup_path = self.path.with_suffix(self.path.suffix + ".bak")
        if not self.path.exists() or backup_path.exists():
            return None

        # Never back up a file CodeAgent itself injected. That state is left
        # behind by a crashed run, and backing it up poisons the backup
        # permanently: every later restore would put the injection straight
        # back, so `ca doctor` keeps reporting stale injections and --fix
        # cannot clear them. Skipping the backup instead lets restore fall
        # through to deleting the orphan, which self-heals on the next run.
        if self.is_injected():
            logger.info(
                "Not backing up %s: it is a leftover CodeAgent injection, "
                "not user content",
                self.path.name,
            )
            return None

        shutil.copy2(self.path, backup_path)
        return backup_path

    def restore_backup(self) -> bool:
        backup_path = self.path.with_suffix(self.path.suffix + ".bak")
        if backup_path.exists():
            self.path.parent.mkdir(parents=True, exist_ok=True)
            os.replace(str(backup_path), str(self.path))
            return True
        return False


class SettingsManager:
    """Manages backup, injection, and restoration of engine settings files.

    Handles hook injection, plugin registration, and settings backup/restore
    for all engine types (Claude, Codex, OpenCode, CodeBuddy).
    """

    def __init__(self, event_map: dict[str, str]):
        self.event_map = event_map

    def inject_hooks(self, settings_path: Path, hooks: list[dict[str, Any]]):
        """Injects hook configurations into a settings file."""
        if not hooks:
            return

        settings_path.parent.mkdir(parents=True, exist_ok=True)

        sf = SettingsFile(settings_path)
        backup = sf.create_backup()
        if backup:
            logger.info("Created safety backup: %s", backup.name)

        data = sf.load()

        if "hooks" not in data:
            data["hooks"] = {}

        data["_ca_injected"] = True

        for hook in hooks:
            event_name = hook.get("event")
            if not event_name:
                continue
            event = self.event_map.get(event_name, event_name)
            if event not in data["hooks"]:
                data["hooks"][event] = [{"matcher": "*", "hooks": []}]

            target_group = next(
                (g for g in data["hooks"][event] if g.get("matcher") == "*"), None
            )
            if not target_group:
                target_group = {"matcher": "*", "hooks": []}
                data["hooks"][event].append(target_group)

            event_hooks = target_group["hooks"]
            existing = next(
                (h for h in event_hooks if h.get("name") == hook["name"]), None
            )

            hook_entry = {
                "name": hook["name"],
                "type": "command",
                "command": hook["command"],
            }

            if existing:
                existing.update(hook_entry)
            else:
                event_hooks.append(hook_entry)

        sf.save(data)

    def restore_settings(self, settings_path: Path):
        """Restores a settings file from its backup or removes injected files."""
        sf = SettingsFile(settings_path)
        if sf.restore_backup():
            logger.info("Restored %s from backup", settings_path.name)
            return

        if settings_path.exists():
            try:
                data = sf.load()
                if isinstance(data, dict) and data.get("_ca_injected") is True:
                    settings_path.unlink()
                    logger.info("Removed injected %s", settings_path.name)
            except Exception:
                pass

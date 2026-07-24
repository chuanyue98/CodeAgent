from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.utils.atomic_write import atomic_write


class SettingsFile:
    """Reads and writes a JSON settings file with atomic backup."""

    def __init__(self, path: Path):
        self.path = path

    def load(self) -> Any:
        if not self.path.exists():
            return {}
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def save(self, data: Any):
        atomic_write(self.path, json.dumps(data, indent=2, ensure_ascii=False))

    def create_backup(self) -> Optional[Path]:
        backup_path = self.path.with_suffix(self.path.suffix + ".bak")
        if self.path.exists() and not backup_path.exists():
            shutil.copy2(self.path, backup_path)
            return backup_path
        return None

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
    for all engine types (Gemini, Claude, Codex, OpenCode).
    """

    def __init__(self, event_map: Dict[str, str]):
        self.event_map = event_map

    def inject_hooks(self, settings_path: Path, hooks: List[Dict[str, Any]]):
        """Injects hook configurations into a settings file."""
        if not hooks:
            return

        settings_path.parent.mkdir(parents=True, exist_ok=True)

        sf = SettingsFile(settings_path)
        backup = sf.create_backup()
        if backup:
            print(f"💾 Created safety backup: {backup.name}")

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
            print(f"♻️ Restored {settings_path.name} from backup")
            return

        if settings_path.exists():
            try:
                data = sf.load()
                if isinstance(data, dict) and data.get("_ca_injected") is True:
                    settings_path.unlink()
                    print(f"♻️ Removed injected {settings_path.name}")
            except Exception:
                pass

import json
from pathlib import Path
from core.hook_scanner import HookScanner


class HookService:
    """Service for managing and scanning hooks."""

    def __init__(self, hooks_root: Path, config_path: Path):
        """Initializes the HookService with hooks root and configuration path.

        Args:
            hooks_root: Path to the root directory containing hooks.
            config_path: Path to the configuration file.
        """
        self.hooks_root = hooks_root
        self.config_path = config_path
        self.scanner = HookScanner(hooks_root)

    def get_detailed_hooks(self) -> list[dict]:
        """Retrieves a detailed list of all scanned hooks with their activation status.

        Returns:
            A list of dictionaries, each containing hook metadata:
            id, name, event, description, path, and isActive.
        """
        scanned, _ = self.scanner.scan()

        # Load config to check active hooks
        active_hooks = set()
        if self.config_path.exists():
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    config = json.load(f)
                    project_hooks = config.get("hooks", {}).get("project_hooks", {})
                    for hooks in project_hooks.values():
                        if isinstance(hooks, list):
                            active_hooks.update(hooks)
            except Exception:
                pass

        hooks_list = []
        for category, hooks in scanned.items():
            for hook_name, metadata in hooks.items():
                hook_id = f"{category}/{hook_name}"
                hooks_list.append(
                    {
                        "id": hook_id,
                        "name": metadata.get("name", hook_name),
                        "event": metadata.get("event", "Unknown"),
                        "description": metadata.get("description", ""),
                        "path": metadata.get("_hook_dir", ""),
                        "isActive": hook_id in active_hooks,
                    }
                )
        return hooks_list

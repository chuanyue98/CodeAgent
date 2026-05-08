from pathlib import Path
from core.plugin_scanner import PluginScanner


class PluginService:
    """Service for managing and scanning plugins."""

    def __init__(self, plugins_root: Path):
        """Initializes the PluginService with the plugins root directory.

        Args:
            plugins_root: Path to the root directory containing plugins.
        """
        self.plugins_root = plugins_root
        self.scanner = PluginScanner(plugins_root)

    def get_detailed_plugins(self) -> dict:
        """Retrieves a detailed dictionary of all scanned plugins by category.

        Returns:
            A dictionary mapping categories to lists of plugin details.
            Each plugin detail includes: name, id, description, and readme.
        """
        scanned = self.scanner.scan()
        detailed_plugins = {}
        for category, plugins in scanned.items():
            detailed_plugins[category] = []
            for plugin_name in plugins:
                plugin_dir = self.plugins_root / category / plugin_name
                readme_path = plugin_dir / "README.md"
                content = ""
                description = ""
                if readme_path.exists():
                    content = readme_path.read_text(encoding="utf-8")
                    for line in content.splitlines():
                        line = line.strip()
                        if line and not line.startswith("#"):
                            description = line
                            break

                detailed_plugins[category].append(
                    {
                        "name": plugin_name,
                        "id": f"{category}/{plugin_name}",
                        "description": description or f"Plugin from {category}",
                        "readme": content or f"# {plugin_name}\n\nNo README available.",
                    }
                )
        return detailed_plugins

from __future__ import annotations

import os
import re
from pathlib import Path

from core.logging_config import get_logger
from core.project_groups import resolve_project_group
from core.resource_locator import get_bundled_resource_root, get_default_config_path
from core.services.config_service import ConfigService

logger = get_logger(__name__)

# Config-supplied regex patterns are user/admin-editable text, not code we
# control. Reject anything implausibly long up front as a cheap guard against
# pathological patterns before even attempting to compile them.
_MAX_SKILL_ROOT_PATTERN_LENGTH = 200


class ConfigManager:
    """Manages configuration loading, resolution, and path token substitution.

    Handles group resolution, project registry matching, and search root
    discovery for skills, prompts, hooks, and plugins.
    """

    def __init__(self, root_dir: Path):
        self.root_dir = root_dir
        self.full_config = self._load_full_config()

    def _load_full_config(self) -> dict:
        config_service = ConfigService(get_default_config_path(self.root_dir))
        config, _ = config_service.get_config()
        return config

    def resolve_resource_root(self) -> Path:
        """Returns the resource root, respecting ``resource_root`` in config.json."""
        resolved = __import__(
            "core.resource_locator", fromlist=["resolve_resource_root_from_config"]
        ).resolve_resource_root_from_config(self.full_config, self.root_dir)
        if resolved is not None:
            return resolved
        return get_bundled_resource_root(self.root_dir)

    def resolve_path_token(self, raw_path: str) -> Path:
        """Resolves path tokens (``$CWD``, ``$CODEAGENT``) in a raw path string."""
        expanded = raw_path.replace("$CWD", str(Path.cwd().as_posix()))
        expanded = expanded.replace("$CODEAGENT", str(self.root_dir.as_posix()))
        path_obj = Path(expanded)
        if path_obj.is_absolute():
            return path_obj
        return (self.root_dir / path_obj).resolve()

    def get_current_project_group(self) -> str:
        """Determines the unified project group name for the current CWD."""
        explicit_group = os.environ.get("CA_PROJECT_GROUP", "").strip()
        if explicit_group:
            return explicit_group

        cwd = Path.cwd().resolve()

        # The registry is consulted first: it is the only place the user says
        # what they want. Registering CodeAgent's own tree under a different
        # group used to be silently ignored by the fallback below, which meant
        # an explicit rule lost to a hardcoded name.
        matched = resolve_project_group(cwd, self.full_config.get("project_registry"))
        if matched:
            return matched

        # Working inside CodeAgent's own checkout still resolves without the
        # user having to register it -- a convenience, not an override.
        root = self.root_dir.resolve()
        if cwd == root or root in cwd.parents:
            return "codeagent"

        return str(self.full_config.get("default_group", "common"))

    def get_skill_search_roots(self, resource_root: Path) -> list[Path]:
        """Identifies all root directories where skills should be searched."""
        skill_path_cfg = self.full_config.get("paths", {}).get("skills", "skills")
        default_root = (resource_root / skill_path_cfg).resolve()

        cfg = self.full_config.get("skills", {})
        mappings = cfg.get("project_skill_root_mapping", [])
        cwd = Path.cwd().resolve()
        cwd_str = str(cwd.as_posix())

        roots = []
        for mapping in mappings:
            pattern = mapping.get("pattern")
            if not pattern:
                continue
            if len(pattern) > _MAX_SKILL_ROOT_PATTERN_LENGTH:
                logger.warning(
                    "Skipping project_skill_root_mapping pattern longer than "
                    "%d characters",
                    _MAX_SKILL_ROOT_PATTERN_LENGTH,
                )
                continue
            try:
                matched = re.search(pattern, cwd_str, re.IGNORECASE)
            except re.error:
                logger.warning(
                    "Skipping invalid project_skill_root_mapping pattern: %r",
                    pattern,
                )
                continue
            if matched:
                mapped_path = mapping.get("path")
                if mapped_path:
                    roots.append(self.resolve_path_token(mapped_path).resolve())

        if cwd != self.root_dir.resolve():
            project_skills = cwd / "skills"
            if project_skills.is_dir():
                if project_skills.resolve() not in roots:
                    roots.append(project_skills.resolve())

        if default_root not in roots:
            roots.append(default_root)

        return roots

    def get_plugin_search_roots(self, resource_root: Path) -> list[Path]:
        """Identifies all root directories where plugins should be searched."""
        plugin_path_cfg = self.full_config.get("paths", {}).get("plugins", "plugins")
        default_root = (resource_root / plugin_path_cfg).resolve()

        roots = []
        cwd = Path.cwd().resolve()

        if cwd != self.root_dir.resolve():
            project_plugins = cwd / "plugins"
            if project_plugins.is_dir():
                roots.append(project_plugins.resolve())

        if default_root not in roots:
            roots.append(default_root)

        return roots

    def get_hook_search_roots(self, resource_root: Path) -> list[Path]:
        """Identifies all root directories where hooks should be searched."""
        hook_path_cfg = self.full_config.get("paths", {}).get("hooks", "hooks")
        default_root = (resource_root / hook_path_cfg).resolve()

        roots = []
        cwd = Path.cwd().resolve()

        if cwd != self.root_dir.resolve():
            project_hooks = cwd / "hooks"
            if project_hooks.is_dir():
                roots.append(project_hooks.resolve())

        if default_root not in roots:
            roots.append(default_root)

        return roots

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import List

from core.resource_locator import get_bundled_resource_root, get_default_config_path
from core.services.config_service import ConfigService

logger = logging.getLogger(__name__)

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
        resource_root = self.full_config.get("paths", {}).get("resource_root")
        if resource_root:
            expanded = str(resource_root).replace(
                "$CODEAGENT", self.root_dir.as_posix()
            )
            resource_path = Path(expanded).expanduser()
            resolved = (
                resource_path
                if resource_path.is_absolute()
                else self.root_dir / resource_path
            ).resolve()
            if resolved.is_dir():
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
        root = self.root_dir.resolve()

        if cwd == root or root in cwd.parents:
            return "codeagent"

        registry = self.full_config.get("project_registry", [])
        best_match_group = None
        max_match_len = -1

        for item in registry:
            raw_path = item.get("path")
            if not raw_path:
                continue

            try:
                mapping_path = Path(raw_path).resolve()
                if cwd == mapping_path or mapping_path in cwd.parents:
                    match_len = len(str(mapping_path.as_posix()))
                    if match_len > max_match_len:
                        max_match_len = match_len
                        best_match_group = item.get("group")
            except Exception:
                continue

        return best_match_group or self.full_config.get("default_group", "common")

    def get_skill_search_roots(self, resource_root: Path) -> List[Path]:
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

    def get_plugin_search_roots(self, resource_root: Path) -> List[Path]:
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

    def get_hook_search_roots(self, resource_root: Path) -> List[Path]:
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

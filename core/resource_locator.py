"""Locate runtime assets and writable configuration in source and wheel installs."""

from __future__ import annotations

import os
import site
import sys
from pathlib import Path

CODE_ROOT = Path(__file__).resolve().parent.parent


def is_source_tree(root: Path = CODE_ROOT) -> bool:
    return (root / "pyproject.toml").is_file() and (root / "core").is_dir()


def get_bundled_resource_root(code_root: Path = CODE_ROOT) -> Path:
    """Return the directory containing prompts, skills, hooks, and web assets."""
    override = os.environ.get("CODEAGENT_RESOURCE_ROOT")
    if override:
        return Path(override).expanduser().resolve()

    if is_source_tree(code_root):
        return code_root

    candidates = [
        Path(sys.prefix) / "share" / "codeagent",
        Path(sys.executable).resolve().parent.parent / "share" / "codeagent",
    ]
    if site.USER_BASE:
        candidates.append(Path(site.USER_BASE) / "share" / "codeagent")
    for installed in candidates:
        if installed.is_dir():
            return installed
    return code_root


def get_default_config_path(code_root: Path = CODE_ROOT) -> Path:
    """Use repository config in source checkouts and user config in installs."""
    override = os.environ.get("CA_CONFIG_PATH")
    if override:
        return Path(override).expanduser()
    if is_source_tree(code_root) or (code_root / "config.json").is_file():
        return code_root / "config.json"
    return Path.home() / ".config" / "codeagent" / "config.json"


#: Tracked defaults used to seed a missing config.json. config.json itself is
#: gitignored (it holds machine-specific project paths), so a fresh clone had
#: nothing at all -- and the in-memory fallback carries no ``groups``, which
#: silently mounted zero skills.
CONFIG_TEMPLATE_NAME = "config.example.json"


def get_config_template_path(code_root: Path = CODE_ROOT) -> Path:
    """Path to the tracked config template shipped with the resources."""
    return get_bundled_resource_root(code_root) / CONFIG_TEMPLATE_NAME


def resolve_resource_root_from_config(
    config: dict, code_root: Path = CODE_ROOT
) -> Path | None:
    """Resolve ``paths.resource_root`` from a loaded config dict.

    Handles ``$CODEAGENT`` expansion, ``~`` expansion, and relative-
    vs-absolute logic. Returns ``None`` if no valid directory is configured,
    so callers can fall back to ``get_bundled_resource_root``.
    """

    raw = config.get("paths", {}).get("resource_root") if isinstance(config, dict) else None
    if not raw:
        return None
    expanded = str(raw).replace("$CODEAGENT", code_root.as_posix())
    resource_path = Path(expanded).expanduser()
    resolved = (
        resource_path if resource_path.is_absolute() else code_root / resource_path
    ).resolve()
    if resolved.is_dir():
        return resolved
    return None


def seed_config_if_missing(code_root: Path = CODE_ROOT) -> Path | None:
    """Creates config.json from the tracked template when it does not exist.

    Returns the path written, or None if a config was already there (or the
    template is missing, which means an incomplete install rather than
    something to paper over).

    Deliberately never overwrites: the file holds the user's groups and
    project registry.
    """
    config_path = get_default_config_path(code_root)
    if config_path.exists():
        return None

    template = get_config_template_path(code_root)
    if not template.is_file():
        return None

    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(template.read_text(encoding="utf-8"), encoding="utf-8")
    return config_path

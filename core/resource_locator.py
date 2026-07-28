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

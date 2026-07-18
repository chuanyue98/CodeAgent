from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from core.services.config_service import ConfigService


class WorkspaceResolutionError(ValueError):
    """Base error for invalid or unavailable registered workspaces."""


class WorkspaceNotRegisteredError(WorkspaceResolutionError):
    """Raised when a directory is not present in the project registry."""


class WorkspaceConfigError(RuntimeError):
    """Raised when the project registry cannot be read safely."""


@dataclass(frozen=True)
class RegisteredWorkspace:
    path: str
    group: str


def resolve_registered_workspace(
    config_service: ConfigService, workspace: str
) -> RegisteredWorkspace:
    """Resolve a workspace and return its authoritative registered group."""
    try:
        requested = Path(workspace).expanduser().resolve()
    except (OSError, ValueError) as exc:
        raise WorkspaceResolutionError("Workspace path is invalid") from exc
    if not requested.is_dir():
        raise WorkspaceResolutionError("Workspace is not an existing directory")

    config, warnings = config_service.get_config()
    if warnings:
        raise WorkspaceConfigError(warnings[0])

    for item in config.get("project_registry", []):
        if not isinstance(item, dict):
            continue
        path = item.get("path")
        group = item.get("group")
        if not isinstance(path, str) or not isinstance(group, str) or not group:
            continue
        try:
            resolved_path = Path(path).expanduser().resolve()
        except (OSError, ValueError):
            continue
        if resolved_path == requested:
            return RegisteredWorkspace(path=str(requested), group=group)

    raise WorkspaceNotRegisteredError(
        "Workspace must be registered in Settings before running a task"
    )

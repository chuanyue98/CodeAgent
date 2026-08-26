from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from core.project_groups import resolve_project_group
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
    """Resolve a workspace and return its authoritative registered group.

    A registry entry is a rule covering everything beneath it, not an
    inventory row -- see ``core.project_groups``, which owns that matching and
    is what the CLI and the agent gateway already use. This function used to
    compare for equality instead, so in a subdirectory of a registered project
    you could start an agent session and resolve a resource group, but could
    not run a task or create a schedule: the same config answered differently
    depending on which half of the app asked.

    ``path`` is the directory actually asked for -- that is where the work
    runs; ``group`` comes from the nearest enclosing rule.
    """
    try:
        requested = Path(workspace).expanduser().resolve()
    except (OSError, ValueError) as exc:
        raise WorkspaceResolutionError("Workspace path is invalid") from exc
    if not requested.is_dir():
        raise WorkspaceResolutionError("Workspace is not an existing directory")

    config, warnings = config_service.get_config()
    if warnings:
        raise WorkspaceConfigError(warnings[0])

    # An entry naming no group is malformed rather than a rule for "no
    # resources"; drop it so a valid enclosing rule can still win.
    registry = [
        entry
        for entry in config.get("project_registry", [])
        if isinstance(entry, dict) and entry.get("group")
    ]
    group = resolve_project_group(requested, registry)
    if group is None:
        raise WorkspaceNotRegisteredError(
            "Workspace must be registered in Settings before running a task"
        )
    return RegisteredWorkspace(path=str(requested), group=group)

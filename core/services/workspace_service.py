from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from core.project_groups import resolve_project_group
from core.services.config_service import ConfigService


def _bound_to_loopback() -> bool:
    """Whether the Web UI is only reachable from this machine."""
    from core.web.security import is_loopback_hostname

    return is_loopback_hostname(os.environ.get("CA_UI_HOST", "127.0.0.1"))


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
    config_service: ConfigService,
    workspace: str,
    *,
    interactive: bool = False,
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
    if group is not None:
        return RegisteredWorkspace(path=str(requested), group=group)

    # Nothing matched. Whether that is fatal depends on who is asking and on
    # who can reach this port.
    #
    # Unattended work -- scheduled runs, batch tasks -- always needs an entry.
    # There the registry is not a security control but a statement of intent:
    # removing a project is how you say "stop acting here on your own", and a
    # schedule that kept firing afterwards would ignore that.
    #
    # An interactive request on a loopback bind is the opposite case. Someone
    # is sitting here having just named this directory, and the registry
    # blocks nobody: a drive-by page is refused by the Host and Origin checks
    # (see core.web.security), and another process running as this user can
    # already execute commands regardless of what ``cwd`` this endpoint
    # accepts. So an entry buys no safety and charges a setup step for it --
    # which is why opening a session in a fresh directory used to fail the
    # PTY handshake with an unexplained 403.
    #
    # Bind anywhere else and it is a boundary again: the port is reachable
    # from the network, the token is the only thing in front of it, and
    # confining ``cwd`` to configured trees limits the damage if it leaks.
    if not interactive or not _bound_to_loopback():
        raise WorkspaceNotRegisteredError(
            "Workspace must be registered in Settings before it can be used"
        )

    config_default = config.get("default_group")
    default_group = config_default if isinstance(config_default, str) else "common"
    return RegisteredWorkspace(path=str(requested), group=default_group)
